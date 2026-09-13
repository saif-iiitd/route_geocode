"""Empirical audit of step 1 (entity recognition, as the notebook actually implements
it) and the dependency-parse signal step 2 could use instead of regex-over-raw-text.

Read-only: does not modify the notebook, gazetteer, or any source file. Runs the
notebook's own NER approach (C10/C12: en_core_web_sm + EntityRuler + PhraseMatcher
from Data/tweet_location_terms.txt, labels LOC/GPE/ORG/FAC, spacy.util.filter_spans
for overlap resolution) exactly as implemented, against a seeded sample of the
4,325 READY_ORIGINAL_EN records, and separately measures how often each relation-cue
word's dependency label would let a redesigned assign_roles skip real corpus false
positives (due to / up to / infinitival to) without a text-level blacklist.

Run: python -B experiments/02_entity_dependency_audit.py
"""
import csv
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

import spacy
from spacy.matcher import PhraseMatcher

ROOT = Path(__file__).resolve().parents[1]
GAZETTEER = ROOT / 'Data/tweet_location_terms.txt'
CANONICAL = ROOT / 'results/canonical_parser_input.csv'
SAMPLE_SIZE = 150
SEED = 20260913


def build_pipeline():
    """Reproduces notebook cells C10/C12 exactly: EntityRuler (exact match) plus a
    case-insensitive PhraseMatcher, both from the same gazetteer file, combined with
    the base model's own NER and de-overlapped with spacy.util.filter_spans.
    """
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


ACCEPTED_LABELS = {'LOC', 'GPE', 'ORG', 'FAC'}


def audit_entities(nlp_tweet, records):
    """Step 1: how many recognized entities per tweet, and how many tweets get none."""
    counts = []
    zero_examples = []
    for r in records:
        doc = nlp_tweet(r['text_for_parser'])
        ents = [e for e in doc.ents if e.label_ in ACCEPTED_LABELS]
        counts.append(len(ents))
        if not ents and len(zero_examples) < 10:
            zero_examples.append(r['text_for_parser'])
    return counts, zero_examples


def audit_dependency_signal(nlp_tweet, records):
    """Step 2 signal: for every 'to'/'towards' token, what dependency label does it
    get, and would that label alone correctly separate a real destination from
    due-to / up-to / infinitival-to -- without any phrase blacklist.
    """
    dep_counts = Counter()
    examples = {}
    for r in records:
        text = r['text_for_parser']
        doc = nlp_tweet(text)
        for tok in doc:
            if tok.text.lower() in ('to', 'towards'):
                key = (tok.text.lower(), tok.dep_, tok.pos_)
                dep_counts[key] += 1
                examples.setdefault(key, text[:140])
    return dep_counts, examples


def main():
    nlp_tweet = build_pipeline()
    records = load_sample()
    print(f'Sample: {len(records)} of {SAMPLE_SIZE} requested, seed={SEED}\n')

    counts, zero_examples = audit_entities(nlp_tweet, records)
    zero = sum(1 for c in counts if c == 0)
    print('=== Step 1: entity recognition (notebook\'s actual C10/C12 pipeline) ===')
    print(f'Records with zero recognized LOC/GPE/ORG/FAC entities: {zero}/{len(records)} ({100*zero/len(records):.1f}%)')
    print(f'Mean entities/record: {sum(counts)/len(counts):.2f}  Max: {max(counts)}')
    print('Distribution:', dict(Counter(counts)))
    if zero_examples:
        print('\nExample zero-entity records (real, not fabricated):')
        for ex in zero_examples:
            print(' -', ex)

    print('\n=== Step 2 signal: dependency label of every to/towards token ===')
    dep_counts, examples = audit_dependency_signal(nlp_tweet, records)
    for key, n in dep_counts.most_common():
        word, dep, pos = key
        print(f'{n:4d}  {word!r:10} dep={dep:8} pos={pos:6}  e.g. "{examples[key]}"')

    out = {'sample_size': len(records), 'seed': SEED,
           'entity_count_distribution': dict(Counter(counts)),
           'zero_entity_rate': zero / len(records),
           'zero_entity_examples': zero_examples,
           'to_towards_dependency_distribution': {f'{k[0]}|{k[1]}|{k[2]}': v for k, v in dep_counts.items()}}
    out_path = Path(__file__).with_suffix('.json')
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nWrote {out_path}')


if __name__ == '__main__':
    main()
