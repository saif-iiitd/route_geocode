"""Experiment 06: full-corpus entity-recognition + resolution audit (step 4 prep).

Experiments 02, 03, and 05 all explicitly flagged "audited on 150 of 4,325
READY_ORIGINAL_EN records, not the full corpus" as an open limitation. This
runs the same NER + classify_mention pipeline (exact / generic-ambiguous /
normalized / fuzzy / unresolved) across the FULL 4,325-record corpus, and
-- the actual purpose of this pass -- aggregates every distinct
OUT_OF_GAZETTEER_UNRESOLVED mention by frequency, so gazetteer/alias-layer
additions (step 4) can be prioritized by real evidence of how often a gap
actually occurs, not by whatever happened to turn up in a 150-record sample.

Read-only, no external API calls, no changes to the gazetteer file.

Run: python -B experiments/06_full_corpus_entity_audit.py
"""
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

import spacy
from spacy.matcher import PhraseMatcher

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.entity_resolution import classify_mention, load_gazetteer  # noqa: E402

GAZETTEER = ROOT / 'Data/tweet_location_terms.txt'
CANONICAL = ROOT / 'results/canonical_parser_input.csv'
ACCEPTED_LABELS = {'LOC', 'GPE', 'ORG', 'FAC'}


def build_pipeline():
    nlp = spacy.load('en_core_web_sm')
    terms = [line.strip() for line in GAZETTEER.read_text(encoding='utf-8').splitlines() if line.strip()]
    ruler = nlp.add_pipe('entity_ruler', before='ner')
    ruler.add_patterns([{'label': 'LOC', 'pattern': t} for t in terms])
    matcher = PhraseMatcher(nlp.vocab, attr='LOWER')
    matcher.add('LOC', [nlp.make_doc(t) for t in terms])

    def nlp_tweet(text):
        doc = nlp(text)
        spans = [spacy.tokens.Span(doc, s, e, label=mid) for mid, s, e in matcher(doc)]
        doc.ents = spacy.util.filter_spans(list(doc.ents) + spans)
        return doc
    return nlp_tweet


def load_all_ready_records():
    with CANONICAL.open(encoding='utf-8-sig') as f:
        return [r for r in csv.DictReader(f) if r['parser_status'] == 'READY_ORIGINAL_EN']


def main():
    t0 = time.time()
    nlp_tweet = build_pipeline()
    gazetteer_by_lower = load_gazetteer()
    records = load_all_ready_records()
    print(f'{len(records)} READY_ORIGINAL_EN records (full corpus, not a sample)\n')

    status_counts = Counter()
    method_counts = Counter()
    unresolved_freq = Counter()
    unresolved_example_ctx = {}
    normalized_freq = Counter()
    fuzzy_freq = Counter()
    total = 0
    zero_entity_records = 0

    for i, r in enumerate(records, 1):
        text = r['text_for_parser']
        doc = nlp_tweet(text)
        ents = [e for e in doc.ents if e.label_ in ACCEPTED_LABELS]
        if not ents:
            zero_entity_records += 1
        for ent in ents:
            total += 1
            result = classify_mention(ent.text, gazetteer_by_lower)
            status_counts[result['candidate_status']] += 1
            method_counts[result.get('match_method')] += 1
            if result['candidate_status'] == 'OUT_OF_GAZETTEER_UNRESOLVED':
                unresolved_freq[ent.text] += 1
                unresolved_example_ctx.setdefault(ent.text, text[:160])
            elif result.get('match_method') == 'NORMALIZED':
                normalized_freq[(ent.text, result['gazetteer_match'])] += 1
            elif result.get('match_method') == 'FUZZY':
                fuzzy_freq[(ent.text, result['gazetteer_match'])] += 1
        if i % 500 == 0:
            print(f'  ...{i}/{len(records)} records processed ({time.time()-t0:.0f}s elapsed)')

    elapsed = time.time() - t0
    print(f'\nDone in {elapsed:.0f}s.\n')

    print('=== Candidate-resolution status (full corpus) ===')
    for status, n in status_counts.most_common():
        print(f'{n:5d}  ({100*n/total:5.1f}%)  {status}')
    print(f'\nRecords with zero recognized entities: {zero_entity_records}/{len(records)} '
          f'({100*zero_entity_records/len(records):.1f}%)')

    print(f'\n=== Top 40 distinct unresolved mentions by frequency ({len(unresolved_freq)} distinct, '
          f'{sum(unresolved_freq.values())} total occurrences) ===')
    for mention, count in unresolved_freq.most_common(40):
        print(f'  {count:4d}x  {mention!r:30} e.g. "{unresolved_example_ctx[mention]}"')

    out = {
        'corpus_size': len(records),
        'total_entities': total,
        'zero_entity_records': zero_entity_records,
        'candidate_status_counts': dict(status_counts),
        'match_method_counts': dict(method_counts),
        'unresolved_mention_frequency': [
            {'mention': m, 'count': c, 'example_context': unresolved_example_ctx[m]}
            for m, c in unresolved_freq.most_common()
        ],
        'normalized_match_frequency': [
            {'mention': m, 'gazetteer_match': g, 'count': c}
            for (m, g), c in normalized_freq.most_common()
        ],
        'fuzzy_match_frequency': [
            {'mention': m, 'gazetteer_match': g, 'count': c}
            for (m, g), c in fuzzy_freq.most_common()
        ],
        'elapsed_seconds': round(elapsed, 1),
    }
    out_path = Path(__file__).with_suffix('.json')
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nWrote {out_path}')


if __name__ == '__main__':
    main()
