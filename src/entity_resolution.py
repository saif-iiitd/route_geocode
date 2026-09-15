"""Step 3: candidate-based entity resolution.

Classifies each recognized mention (from the notebook's C10/C12 NER pipeline,
reproduced in experiments/02_entity_dependency_audit.py) by what local evidence
is available to resolve it, *before* any external geocoder is consulted. This
module does not geocode and does not call any external API — it only decides,
from local data (Data/tweet_location_terms.txt), which mentions have enough
evidence to be resolved with confidence and which do not.

Motivation (handoff, "Entity resolution" section):
    "Each place is resolved independently. The code generally accepts the first
    acceptable OpenCage result within broad Delhi bounds. It does not implement
    the manuscript's implied contextual confidence/ranking logic. No joint
    disambiguation across co-mentioned places. Alias handling is weak."

This module addresses the piece of that problem answerable without an external
geocoder: (a) a mention that exactly matches a specific gazetteer entry has
strong local evidence; (b) a mention that matches a *generic* single-word
gazetteer entry (e.g. "Temple", "Flyover") names a feature type, not a specific
place, and must not be silently geocoded to "the nearest Temple"; (c) a mention
recognized only by spaCy's base NER (not in the gazetteer at all) has no local
evidence and must be marked unresolved rather than passed to a geocoder with a
false appearance of confidence.

Alias handling (step 4 preview): the handoff also flags "alias handling is
weak." Experiment 04 found a real case of this ("Kalka Ji" vs. gazetteer's
"Kalkaji") and experiment 05 explored fuzzy matching to close gaps like it.
Two additional, more conservative match methods are layered in below, each
only tried after the stronger ones fail, and each evidenced empirically (see
experiments/05_fuzzy_alias_matching.md) rather than assumed safe:

- Whitespace/punctuation-normalized exact match ("Kalka Ji" == "Kalkaji" once
  normalized) — zero ambiguity risk, since it is still an exact match once a
  cosmetic difference is removed.
- Character-level fuzzy match (`rapidfuzz.fuzz.ratio`) at a >=90 score, found
  by testing against every real out-of-gazetteer mention in the audited
  150-record sample: 3/3 matches at or above 90 were correct spelling variants
  and 0 were false positives, with a clean 10-point gap to the next (wrong)
  candidate at 80. Word-order-tolerant scorers (e.g. `token_sort_ratio`) were
  tested and rejected: they produced a confident-looking but wrong match
  ("Nagar Kirtan", not a place, scored 87 against "Kirti Nagar", a real one).
"""
import re
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
GAZETTEER_PATH = ROOT / 'Data/tweet_location_terms.txt'

# Single-word gazetteer entries that name a *feature type* rather than a specific
# place. Found by auditing Data/tweet_location_terms.txt for single-word terms
# that are common generic nouns (see experiments/03_entity_resolution_audit.md).
# Curated, not inferred, because "generic" is a property of the word's meaning,
# not something derivable from string shape alone.
GENERIC_SINGLE_WORD_TERMS = frozenset({
    'Boulevard', 'Flyover', 'Garden', 'Mandi', 'Temple', 'Underpass',
})

# Evidenced in experiments/05_fuzzy_alias_matching.md: the lowest score among
# correct matches (94.1) minus enough margin to keep 90.9 ("Kirbi Place" ->
# "Kirby Place") in, while excluding the highest wrong match found (80.0).
FUZZY_RATIO_THRESHOLD = 90

GAZETTEER_RESOLVED = 'GAZETTEER_RESOLVED'
GAZETTEER_GENERIC_AMBIGUOUS = 'GAZETTEER_GENERIC_AMBIGUOUS'
GAZETTEER_NORMALIZED_MATCH = 'GAZETTEER_NORMALIZED_MATCH'
GAZETTEER_FUZZY_MATCH = 'GAZETTEER_FUZZY_MATCH'
OUT_OF_GAZETTEER_UNRESOLVED = 'OUT_OF_GAZETTEER_UNRESOLVED'


def load_gazetteer(path=GAZETTEER_PATH):
    terms = [line.strip() for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    by_lower = {t.lower(): t for t in terms}
    return by_lower


def _normalize(text):
    """Lowercase, strip everything but letters/digits -- collapses spacing and
    punctuation variants ("Kalka Ji" / "Kalkaji", "Red Fort-" / "Red Fort")
    to the same key without touching actual spelling.
    """
    return re.sub(r'[^a-z0-9]', '', text.lower())


@lru_cache(maxsize=8)
def _fuzzy_index(canonical_terms):
    """canonical_terms must be a hashable (tuple) sequence for lru_cache; built
    once per distinct gazetteer and reused across every classify_mention call
    in a run instead of rebuilt per mention.
    """
    by_normalized = {}
    for term in canonical_terms:
        by_normalized.setdefault(_normalize(term), term)
    return by_normalized, list(canonical_terms)


def classify_mention(text, gazetteer_by_lower, generic_terms=GENERIC_SINGLE_WORD_TERMS,
                      fuzzy_threshold=FUZZY_RATIO_THRESHOLD):
    """Classify a single recognized mention span's local resolution evidence.

    Does not geocode. Returns a dict with no coordinates and no invented
    disambiguation — only the evidence class and, where relevant, which
    gazetteer entry matched, by which method, and (for a fuzzy match) at what
    score, so a match is never silently indistinguishable from an exact one.
    """
    key = text.strip().lower()
    matched = gazetteer_by_lower.get(key)
    method, score = ('EXACT', None) if matched is not None else (None, None)

    if matched is None:
        canonical_terms = tuple(sorted(set(gazetteer_by_lower.values())))
        by_normalized, terms_list = _fuzzy_index(canonical_terms)
        norm_key = _normalize(text)
        if norm_key in by_normalized:
            matched, method = by_normalized[norm_key], 'NORMALIZED'
        else:
            hit = process.extractOne(text, terms_list, scorer=fuzz.ratio, score_cutoff=fuzzy_threshold)
            if hit is not None:
                matched, score, _ = hit
                method = 'FUZZY'

    if matched is None:
        return {
            'text': text,
            'gazetteer_match': None,
            'candidate_status': OUT_OF_GAZETTEER_UNRESOLVED,
            'reason': 'No exact, normalized, or high-confidence fuzzy gazetteer entry; '
                      'recognized only by base spaCy NER. No local evidence to '
                      'disambiguate before geocoding.',
        }

    if matched in generic_terms:
        return {
            'text': text,
            'gazetteer_match': matched,
            'candidate_status': GAZETTEER_GENERIC_AMBIGUOUS,
            'match_method': method,
            'reason': f'"{matched}" names a feature type, not a specific place. '
                      'Many real locations share this name; resolving it requires '
                      'a qualifying neighbor mention or co-occurring named road, '
                      'not implemented here.',
        }

    status = {'EXACT': GAZETTEER_RESOLVED, 'NORMALIZED': GAZETTEER_NORMALIZED_MATCH,
              'FUZZY': GAZETTEER_FUZZY_MATCH}[method]
    if method == 'EXACT':
        reason = f'Exact match to a specific gazetteer entry ("{matched}").'
    elif method == 'NORMALIZED':
        reason = (f'Matches gazetteer entry "{matched}" once whitespace/punctuation '
                   'differences are removed (e.g. a missing or extra space).')
    else:
        reason = (f'Character-level fuzzy match to gazetteer entry "{matched}" '
                   f'(rapidfuzz ratio {score:.1f}, threshold {fuzzy_threshold}).')
    result = {'text': text, 'gazetteer_match': matched, 'candidate_status': status,
              'match_method': method, 'reason': reason}
    if score is not None:
        result['fuzzy_score'] = round(score, 1)
    return result


def classify_mentions(mentions, gazetteer_by_lower=None, generic_terms=GENERIC_SINGLE_WORD_TERMS,
                       fuzzy_threshold=FUZZY_RATIO_THRESHOLD):
    gazetteer_by_lower = gazetteer_by_lower if gazetteer_by_lower is not None else load_gazetteer()
    return [classify_mention(m, gazetteer_by_lower, generic_terms, fuzzy_threshold) for m in mentions]
