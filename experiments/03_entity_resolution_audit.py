"""Empirical audit of step 3: candidate-based entity resolution.

Reuses the exact same NER pipeline and seeded 150-record sample as
experiments/02_entity_dependency_audit.py (seed=20260913) for direct
comparability. For every entity span that survives filter_spans, this script
additionally tracks *which pipeline component* claimed it (the gazetteer-driven
EntityRuler/PhraseMatcher vs. spaCy's own base NER), then classifies it with
src/entity_resolution.classify_mention.

Read-only: does not modify the notebook, gazetteer, or any source file, and
makes no external API calls.

Run: python -B experiments/03_entity_resolution_audit.py
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
    """Same construction as experiment 02 (C10/C12), but keeps base-NER spans and
    gazetteer-matched spans separately labeled before filter_spans de-overlaps
    them, so the audit can tell which source produced each surviving entity.
    """
    nlp = spacy.load('en_core_web_sm')
    terms = [line.strip() for line in GAZETTEER.read_text(encoding='utf-8').splitlines() if line.strip()]
    ruler = nlp.add_pipe('entity_ruler', before='ner')
    ruler.add_patterns([{'label': 'GAZ', 'pattern': t} for t in terms])
    matcher = PhraseMatcher(nlp.vocab, attr='LOWER')
    matcher.add('GAZ', [nlp.make_doc(t) for t in terms])

    def nlp_tweet(text):
        doc = nlp(text)
        base_ner_spans = [e for e in doc.ents if e.label_ in ACCEPTED_LABELS]
        gaz_spans = [spacy.tokens.Span(doc, s, e, label='GAZ') for _, s, e in matcher(doc)]
        gaz_from_ruler = [e for e in doc.ents if e.label_ == 'GAZ']
        all_spans = base_ner_spans + gaz_spans + gaz_from_ruler
        doc.ents = spacy.util.filter_spans(all_spans)
        gaz_texts = {s.text.lower() for s in gaz_spans + gaz_from_ruler}
        return doc, gaz_texts
    return nlp_tweet


def load_sample():
    with CANONICAL.open(encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['parser_status'] == 'READY_ORIGINAL_EN']
    ranked = sorted(rows, key=lambda r: hashlib.sha256((str(SEED) + ':' + r['dataset_record_id']).encode()).hexdigest())
    return ranked[:SAMPLE_SIZE]


def audit(nlp_tweet, records, gazetteer_by_lower):
    status_counts = Counter()
    source_counts = Counter()
    examples = {}
    total_entities = 0
    for r in records:
        text = r['text_for_parser']
        doc, gaz_texts = nlp_tweet(text)
        for ent in doc.ents:
            total_entities += 1
            source = 'GAZETTEER_MATCHER' if ent.text.lower() in gaz_texts else 'BASE_SPACY_NER'
            source_counts[source] += 1
            result = classify_mention(ent.text, gazetteer_by_lower)
            status = result['candidate_status']
            status_counts[status] += 1
            examples.setdefault((status, source), []).append((ent.text, text[:140]))
    return total_entities, status_counts, source_counts, examples


def main():
    nlp_tweet = build_pipeline()
    gazetteer_by_lower = load_gazetteer()
    records = load_sample()
    print(f'Sample: {len(records)} of {SAMPLE_SIZE} requested, seed={SEED} (same sample as experiment 02)\n')

    total, status_counts, source_counts, examples = audit(nlp_tweet, records, gazetteer_by_lower)
    print(f'Total surviving entity spans across sample: {total}\n')

    print('=== Candidate-resolution status ===')
    for status, n in status_counts.most_common():
        print(f'{n:4d}  ({100*n/total:5.1f}%)  {status}')

    print('\n=== Which pipeline component produced each span ===')
    for source, n in source_counts.most_common():
        print(f'{n:4d}  ({100*n/total:5.1f}%)  {source}')

    print('\n=== Examples per status/source ===')
    out_examples = {}
    for (status, source), exs in examples.items():
        key = f'{status}|{source}'
        shown = exs[:6]
        out_examples[key] = shown
        print(f'\n--- {key} ({len(exs)} total) ---')
        for mention, ctx in shown:
            print(f'  "{mention}"  <-  {ctx}')

    out = {
        'sample_size': len(records), 'seed': SEED,
        'total_entities': total,
        'candidate_status_counts': dict(status_counts),
        'pipeline_source_counts': dict(source_counts),
        'examples': out_examples,
    }
    out_path = Path(__file__).with_suffix('.json')
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nWrote {out_path}')


if __name__ == '__main__':
    main()
