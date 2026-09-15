"""Experiment 04: candidate resolution for generic landmark mentions
("flyover", "underpass", "temple", "mandi", ...), step 3 continued.

Small cached sample: reuses the exact same 150-record seeded sample as
experiments 02 and 03 (seed=20260913) and, within it, every mention experiment
03 classified GAZETTEER_GENERIC_AMBIGUOUS (17 mentions in that sample). This is
a small, already-audited, non-arbitrary sample -- not a new draw.

For each generic mention:
  1. Find the nearest preceding GAZETTEER_RESOLVED mention in the same tweet
     (the "qualifier") by character position in the doc.
  2. Geocode the qualifier (cached) to get an anchor coordinate.
  3. Geocode the bare generic term (cached), restricted to a small bounding box
     around the anchor.
  4. Rank the returned candidates by two independent, evidenced signals:
       - name_match: does the candidate's formatted name literally contain the
         generic term? (grounded in the live test that motivated this design:
         a bounded bare "flyover" query returned "Mangolpuri Flyover", etc.)
       - corroborated: does a local network_nodes_data.csv node with the
         matching structural flag (bridge for flyover, tunnel for underpass)
         fall within 150 m? Only checked for flyover/underpass -- no local
         source exists for temple/mandi/garden/boulevard.

Makes real OpenCage calls only on a cache miss; the cache file is committed so
every reported number here is reproducible from the cache alone.

Run: python -B experiments/04_generic_mention_candidate_resolution.py
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

import spacy
from spacy.matcher import PhraseMatcher

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.entity_resolution import (  # noqa: E402
    GAZETTEER_GENERIC_AMBIGUOUS,
    GAZETTEER_RESOLVED,
    classify_mention,
    load_gazetteer,
)
from src.geocoding import (  # noqa: E402
    DELHI_CENTER,
    GeocodeCache,
    corroborate,
    geocode,
    make_bbox,
)

GAZETTEER = ROOT / 'Data/tweet_location_terms.txt'
CANONICAL = ROOT / 'results/canonical_parser_input.csv'
CACHE_PATH = ROOT / 'experiments/04_opencage_cache.json'
SAMPLE_SIZE = 150
SEED = 20260913

# Generic term -> local structural-corroboration feature, where one exists.
CORROBORATION_FEATURE = {'flyover': 'bridge', 'underpass': 'tunnel'}


def build_pipeline():
    nlp = spacy.load('en_core_web_sm')
    terms = [line.strip() for line in GAZETTEER.read_text(encoding='utf-8').splitlines() if line.strip()]
    ruler = nlp.add_pipe('entity_ruler', before='ner')
    ruler.add_patterns([{'label': 'GAZ', 'pattern': t} for t in terms])
    matcher = PhraseMatcher(nlp.vocab, attr='LOWER')
    matcher.add('GAZ', [nlp.make_doc(t) for t in terms])

    def nlp_tweet(text):
        doc = nlp(text)
        base_ner_spans = [e for e in doc.ents if e.label_ in ('LOC', 'GPE', 'ORG', 'FAC')]
        gaz_spans = [spacy.tokens.Span(doc, s, e, label='GAZ') for _, s, e in matcher(doc)]
        gaz_from_ruler = [e for e in doc.ents if e.label_ == 'GAZ']
        doc.ents = spacy.util.filter_spans(base_ner_spans + gaz_spans + gaz_from_ruler)
        return doc
    return nlp_tweet


def load_sample():
    with CANONICAL.open(encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['parser_status'] == 'READY_ORIGINAL_EN']
    ranked = sorted(rows, key=lambda r: hashlib.sha256((str(SEED) + ':' + r['dataset_record_id']).encode()).hexdigest())
    return ranked[:SAMPLE_SIZE]


def find_generic_mentions_with_qualifiers(nlp_tweet, records, gazetteer_by_lower):
    """Reproduces experiment 03's classification, but keeps character offsets so
    each GAZETTEER_GENERIC_AMBIGUOUS mention can be paired with the nearest
    preceding GAZETTEER_RESOLVED mention in the same tweet.
    """
    found = []
    for r in records:
        text = r['text_for_parser']
        doc = nlp_tweet(text)
        classified = []
        for ent in doc.ents:
            result = classify_mention(ent.text, gazetteer_by_lower)
            classified.append((ent.start_char, ent.end_char, ent.text, result))
        classified.sort(key=lambda t: t[0])
        for i, (start, end, text_span, result) in enumerate(classified):
            if result['candidate_status'] != GAZETTEER_GENERIC_AMBIGUOUS:
                continue
            qualifier = None
            for j in range(i - 1, -1, -1):
                prev_start, prev_end, prev_text, prev_result = classified[j]
                if prev_result['candidate_status'] == GAZETTEER_RESOLVED:
                    qualifier = prev_result['gazetteer_match']
                    break
            found.append({
                'dataset_record_id': r['dataset_record_id'],
                'tweet_text': text,
                'generic_term': text_span,
                'qualifier': qualifier,
            })
    return found


def resolve_candidates(item, cache):
    term = item['generic_term'].lower()
    qualifier = item['qualifier']
    result = dict(item, anchor=None, candidates=[])
    if qualifier is None:
        result['note'] = 'NO_LOCAL_QUALIFIER: falls back to O/D corridor anchoring, not implemented here.'
        return result

    anchor_query = f'{qualifier}, Delhi'
    proximity = f'{DELHI_CENTER[0]},{DELHI_CENTER[1]}'
    anchor_resp = geocode(anchor_query, cache, proximity=proximity)
    anchor_results = anchor_resp.get('results', [])
    if not anchor_results:
        result['note'] = f'Qualifier "{qualifier}" did not geocode; cannot anchor a bounding box.'
        return result
    anchor = anchor_results[0]['geometry']
    result['anchor'] = {'query': anchor_query, 'lat': anchor['lat'], 'lng': anchor['lng'],
                         'confidence': anchor_results[0].get('confidence'),
                         'formatted': anchor_results[0].get('formatted')}

    bbox = make_bbox(anchor['lat'], anchor['lng'])
    term_resp = geocode(term, cache, bounds=bbox)
    feature = CORROBORATION_FEATURE.get(term)
    for cand in term_resp.get('results', []):
        formatted = cand.get('formatted', '')
        name_match = term in formatted.lower()
        corrob = None
        if feature:
            hit = corroborate(cand['geometry']['lat'], cand['geometry']['lng'], feature)
            if hit:
                corrob = {'matched_local_node': hit[0], 'distance_m': round(hit[1], 1)}
        result['candidates'].append({
            'formatted': formatted, 'lat': cand['geometry']['lat'], 'lng': cand['geometry']['lng'],
            'opencage_confidence': cand.get('confidence'),
            'name_match': name_match, 'corroborated': corrob,
        })
    result['candidates'].sort(key=lambda c: (c['corroborated'] is not None, c['name_match']), reverse=True)
    return result


def main():
    nlp_tweet = build_pipeline()
    gazetteer_by_lower = load_gazetteer()
    records = load_sample()
    mentions = find_generic_mentions_with_qualifiers(nlp_tweet, records, gazetteer_by_lower)
    print(f'{len(mentions)} generic mentions found in the {len(records)}-record sample (seed={SEED})\n')

    cache = GeocodeCache(CACHE_PATH)
    results = []
    for item in mentions:
        res = resolve_candidates(item, cache)
        results.append(res)
        top = res['candidates'][0] if res['candidates'] else None
        print(f"\"{item['generic_term']}\" qualified by \"{item['qualifier']}\"")
        if res.get('note'):
            print('  ', res['note'])
        elif top:
            corrob = f" corroborated by {top['corroborated']['matched_local_node']} ({top['corroborated']['distance_m']}m)" if top['corroborated'] else ''
            print(f"   top candidate: {top['formatted']}  name_match={top['name_match']}{corrob}")
        else:
            print('   no candidates returned')

    with_qualifier = [r for r in results if r.get('anchor')]
    with_candidates = [r for r in with_qualifier if r['candidates']]
    top_name_match = [r for r in with_candidates if r['candidates'][0]['name_match']]
    corroborated = [r for r in with_candidates if r['candidates'][0]['corroborated']]

    print('\n=== Summary ===')
    print(f'Generic mentions with a local qualifier found: {len(with_qualifier)}/{len(mentions)}')
    print(f'  of those, qualifier geocoded + generic term returned candidates: {len(with_candidates)}')
    print(f'  of those, top-ranked candidate name-matches the generic term: {len(top_name_match)}')
    print(f'  of those, top-ranked candidate is corroborated by local bridge/tunnel data: {len(corroborated)}')

    out_path = Path(__file__).with_suffix('.json')
    out_path.write_text(json.dumps({'sample_size': len(records), 'seed': SEED, 'results': results},
                                    indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nWrote {out_path}')
    print(f'OpenCage response cache: {CACHE_PATH}')


if __name__ == '__main__':
    main()
