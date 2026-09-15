"""Experiment 05: fuzzy/normalized alias matching for out-of-gazetteer mentions.

Reruns the exact same 150-record seeded sample and NER pipeline as experiments
02-04 (seed=20260913), reclassifying every entity span with the two new match
stages added to src/entity_resolution.classify_mention: whitespace/punctuation
normalization, then a >=90 character-level fuzzy ratio (rapidfuzz.fuzz.ratio).
Both thresholds and the choice of scorer were determined by exploration against
this same sample's real out-of-gazetteer mentions before being built in (see
experiments/05_fuzzy_alias_matching.md for the exploration log).

Read-only, no external API calls.

Run: python -B experiments/05_fuzzy_alias_matching.py
"""
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import spacy
from spacy.matcher import PhraseMatcher

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.entity_resolution import classify_mention, load_gazetteer  # noqa: E402

GAZETTEER = ROOT / 'Data/tweet_location_terms.txt'
CANONICAL = ROOT / 'results/canonical_parser_input.csv'
SAMPLE_SIZE = 150
SEED = 20260913
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


def load_sample():
    with CANONICAL.open(encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['parser_status'] == 'READY_ORIGINAL_EN']
    ranked = sorted(rows, key=lambda r: hashlib.sha256((str(SEED) + ':' + r['dataset_record_id']).encode()).hexdigest())
    return ranked[:SAMPLE_SIZE]


def main():
    nlp_tweet = build_pipeline()
    gazetteer_by_lower = load_gazetteer()
    records = load_sample()
    print(f'Sample: {len(records)} records, seed={SEED} (same sample as experiments 02-04)\n')

    status_counts = Counter()
    method_counts = Counter()
    normalized_hits, fuzzy_hits = [], []
    total = 0
    for r in records:
        text = r['text_for_parser']
        doc = nlp_tweet(text)
        for ent in doc.ents:
            if ent.label_ not in ACCEPTED_LABELS:
                continue
            total += 1
            result = classify_mention(ent.text, gazetteer_by_lower)
            status_counts[result['candidate_status']] += 1
            method_counts[result.get('match_method')] += 1
            if result.get('match_method') == 'NORMALIZED':
                normalized_hits.append((ent.text, result['gazetteer_match']))
            elif result.get('match_method') == 'FUZZY':
                fuzzy_hits.append((ent.text, result['gazetteer_match'], result['fuzzy_score']))

    print('=== Candidate-resolution status (all entities in sample) ===')
    for status, n in status_counts.most_common():
        print(f'{n:4d}  ({100*n/total:5.1f}%)  {status}')

    print('\n=== Match method ===')
    for method, n in method_counts.most_common():
        print(f'{n:4d}  {method}')

    print(f'\n=== NORMALIZED matches recovered ({len(normalized_hits)}) ===')
    for mention, matched in sorted(set(normalized_hits)):
        print(f'  {mention!r:25} -> {matched!r}')

    print(f'\n=== FUZZY matches recovered (>= 90) ({len(fuzzy_hits)}) ===')
    for mention, matched, score in sorted(set(fuzzy_hits)):
        print(f'  {score:5.1f}  {mention!r:25} -> {matched!r}')

    out = {
        'sample_size': len(records), 'seed': SEED, 'total_entities': total,
        'candidate_status_counts': dict(status_counts),
        'match_method_counts': {k: v for k, v in method_counts.items()},
        'normalized_hits': sorted(set(normalized_hits)),
        'fuzzy_hits': sorted(set(fuzzy_hits)),
    }
    out_path = Path(__file__).with_suffix('.json')
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nWrote {out_path}')


if __name__ == '__main__':
    main()
