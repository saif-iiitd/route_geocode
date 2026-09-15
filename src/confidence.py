"""Unified confidence scoring and candidate ranking/selection for a resolved
mention (step 3, continued). Directly targets the handoff's named gap:

    "It does not implement the manuscript's implied contextual
    confidence/ranking logic. No joint disambiguation across co-mentioned
    places."

Two live OpenCage tests motivated this design (see
experiments/06_candidate_confidence_ranking.md for the full record):

- `"Madhuban Chowk, Delhi"` returns 3 candidates, all within ~350 m of each
  other -- the same real intersection described via different nearby roads,
  not genuine ambiguity about *which place* is meant.
- `"Krishna Nagar, Delhi"` returns 2 candidates ~14 km apart, both at
  OpenCage confidence 8-9 -- two real, different places sharing a name, with
  nothing in the mention text alone to tell them apart.

A single scalar "confidence" cannot honestly represent both situations. This
module instead measures the *spread* between a mention's returned candidates
(after dropping OpenCage's generic city-level fallback, consistently seen at
confidence <= 3 across every query tested) and uses that to decide whether
one place is being described (tight cluster) or several real candidates
genuinely compete (wide spread) -- and, only in the wide-spread case, uses
another already-confidently-resolved mention in the same tweet as a
proximity anchor to choose between them. When no such anchor exists, every
candidate is kept and reported rather than one being silently guessed.
"""
from pathlib import Path

from .geocoding import DELHI_CENTER, geocode, haversine_m

# Evidenced from every live query run in this project so far: a specific,
# real candidate is always returned at confidence >= 7; OpenCage's generic
# city-level fallback ("Delhi, North Delhi, India") is always confidence 3.
# A margin above that observed fallback value, not a guessed round number.
FALLBACK_CONFIDENCE_MAX = 4

# Evidenced from the "Madhuban Chowk" cluster (max pairwise spread 344 m,
# genuinely one place) vs. "Krishna Nagar" (14,094 m, genuinely two places) --
# a wide, unambiguous margin between the two real cases found.
CLUSTER_RADIUS_M = 500

CONFIDENCE_HIGH = 'CONFIDENCE_HIGH'
CONFIDENCE_MEDIUM = 'CONFIDENCE_MEDIUM'
CONFIDENCE_LOW = 'CONFIDENCE_LOW'
UNRESOLVED_NO_GEOCODE = 'UNRESOLVED_NO_GEOCODE'

_TIER_RANK = {CONFIDENCE_LOW: 0, CONFIDENCE_MEDIUM: 1, CONFIDENCE_HIGH: 2}

# A FUZZY gazetteer match means the mention *text itself* was inferred, not
# exact -- so even a perfectly clustered geocode result must not be reported
# as fully certain. NORMALIZED is a punctuation/whitespace-only difference
# from an exact match and is not capped.
_MATCH_METHOD_CAP = {'EXACT': CONFIDENCE_HIGH, 'NORMALIZED': CONFIDENCE_HIGH, 'FUZZY': CONFIDENCE_MEDIUM}


def _cap(tier, method_cap):
    if _TIER_RANK[tier] > _TIER_RANK[method_cap]:
        return method_cap
    return tier


def _real_candidates(response):
    return [r for r in response.get('results', []) if (r.get('confidence') or 0) > FALLBACK_CONFIDENCE_MAX]


def _max_spread_m(candidates):
    coords = [(c['geometry']['lat'], c['geometry']['lng']) for c in candidates]
    if len(coords) < 2:
        return 0.0
    return max(haversine_m(*a, *b) for i, a in enumerate(coords) for b in coords[i + 1:])


def rank_candidates(gazetteer_term, match_method, cache, anchors=(), query_suffix=', Delhi'):
    """Geocode `gazetteer_term` (cached) and return a ranked-confidence result.

    anchors: coordinates of other mentions in the same tweet already resolved
    at CONFIDENCE_HIGH, used only when this mention's own candidates spread
    too widely to trust on their own.

    Returns a dict: always carries `confidence`, `reason`, and `candidates`
    (every real candidate kept, so nothing is lost even at low confidence);
    `chosen` is the selected candidate dict, or None if truly unresolved.
    """
    response = geocode(f'{gazetteer_term}{query_suffix}', cache, proximity=f'{DELHI_CENTER[0]},{DELHI_CENTER[1]}')
    candidates = _real_candidates(response)
    method_cap = _MATCH_METHOD_CAP.get(match_method, CONFIDENCE_MEDIUM)

    if not candidates:
        return {'confidence': UNRESOLVED_NO_GEOCODE, 'chosen': None, 'candidates': [],
                'spread_m': None, 'method': None,
                'reason': f'No candidate above the fallback confidence threshold for "{gazetteer_term}".'}

    spread = _max_spread_m(candidates)
    candidates_sorted = sorted(candidates, key=lambda c: c.get('confidence', 0), reverse=True)

    if spread <= CLUSTER_RADIUS_M:
        chosen = candidates_sorted[0]
        tier = _cap(CONFIDENCE_HIGH, method_cap)
        reason = (f'{len(candidates)} candidate(s) cluster within {spread:.0f} m '
                   f'(<= {CLUSTER_RADIUS_M} m) -- treated as one real place.')
        method = 'CLUSTERED'
    else:
        if anchors:
            chosen, best_dist, best_anchor_idx = None, None, None
            for cand in candidates:
                lat, lng = cand['geometry']['lat'], cand['geometry']['lng']
                for i, (a_lat, a_lng) in enumerate(anchors):
                    d = haversine_m(lat, lng, a_lat, a_lng)
                    if best_dist is None or d < best_dist:
                        chosen, best_dist, best_anchor_idx = cand, d, i
            tier = _cap(CONFIDENCE_MEDIUM, method_cap)
            reason = (f'{len(candidates)} candidates spread {spread:.0f} m (> {CLUSTER_RADIUS_M} m) -- '
                       f'genuine ambiguity. Resolved via proximity to another already-confident '
                       f'mention in the same tweet ({best_dist:.0f} m away).')
            method = 'JOINT_DISAMBIGUATION'
        else:
            chosen = candidates_sorted[0]
            tier = _cap(CONFIDENCE_LOW, method_cap)
            reason = (f'{len(candidates)} candidates spread {spread:.0f} m (> {CLUSTER_RADIUS_M} m) -- '
                       'genuine ambiguity, and no other confidently-resolved mention in this tweet to '
                       'disambiguate against. Highest-OpenCage-confidence candidate kept as a best guess; '
                       'all candidates retained rather than one being silently treated as certain.')
            method = 'BEST_GUESS_AMBIGUOUS'

    return {
        'confidence': tier, 'chosen': {'formatted': chosen.get('formatted'),
                                        'lat': chosen['geometry']['lat'], 'lng': chosen['geometry']['lng'],
                                        'opencage_confidence': chosen.get('confidence')},
        'candidates': [{'formatted': c.get('formatted'), 'lat': c['geometry']['lat'], 'lng': c['geometry']['lng'],
                         'opencage_confidence': c.get('confidence')} for c in candidates],
        'spread_m': round(spread, 1), 'method': method, 'reason': reason,
    }
