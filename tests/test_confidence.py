"""Tests for src/confidence.py, using a fake in-memory geocode cache so no
live API calls happen. Fixture coordinates are drawn from real OpenCage
responses recorded in experiments/06_candidate_confidence_ranking.json.
"""
import unittest

from src.confidence import (
    CLUSTER_RADIUS_M,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    UNRESOLVED_NO_GEOCODE,
    rank_candidates,
)


class FakeCache:
    """Stands in for GeocodeCache: geocode() calls cache.get()/.set(); a
    pre-populated FakeCache makes rank_candidates fully offline and deterministic.
    """

    def __init__(self, responses):
        self._responses = responses  # {query: raw_opencage_response_dict}
        self.set_calls = []

    def get(self, query, **params):
        return self._responses.get(query)

    def set(self, query, response, **params):
        self.set_calls.append(query)
        self._responses[query] = response


def _result(lat, lng, confidence, formatted='Test Place'):
    return {'geometry': {'lat': lat, 'lng': lng}, 'confidence': confidence, 'formatted': formatted}


class TestRankCandidates(unittest.TestCase):
    def test_tight_cluster_is_high_confidence(self):
        # Real Madhuban Chowk candidates, max pairwise spread 348m.
        cache = FakeCache({'Madhuban Chowk, Delhi': {'results': [
            _result(28.7032676, 77.1322497, 8, 'Madhuban Chowk A'),
            _result(28.7035532, 77.1300884, 9, 'Madhuban Chowk B'),
            _result(28.7022919, 77.1333063, 9, 'Madhuban Chowk C'),
            _result(28.65381, 77.22897, 3, 'Delhi, North Delhi, India'),
        ]}})
        r = rank_candidates('Madhuban Chowk', 'EXACT', cache)
        self.assertEqual(r['confidence'], CONFIDENCE_HIGH)
        self.assertEqual(r['method'], 'CLUSTERED')
        self.assertLessEqual(r['spread_m'], CLUSTER_RADIUS_M)

    def test_fallback_low_confidence_candidate_is_excluded(self):
        cache = FakeCache({'Anywhere, Delhi': {'results': [
            _result(28.70, 77.13, 9, 'Real Place'),
            _result(28.65381, 77.22897, 3, 'Delhi, North Delhi, India'),  # fallback noise
        ]}})
        r = rank_candidates('Anywhere', 'EXACT', cache)
        self.assertEqual(len(r['candidates']), 1)
        self.assertEqual(r['candidates'][0]['formatted'], 'Real Place')

    def test_wide_spread_without_anchor_stays_low_confidence_and_keeps_all_candidates(self):
        # Real Krishna Nagar candidates, ~14km apart.
        cache = FakeCache({'Krishna Nagar, Delhi': {'results': [
            _result(28.6578127, 77.2901199, 8, 'Krishna Nagar, Preet Vihar'),
            _result(28.5637017, 77.1934098, 9, 'Krishna Nagar, South Delhi'),
        ]}})
        r = rank_candidates('Krishna Nagar', 'EXACT', cache)
        self.assertEqual(r['confidence'], CONFIDENCE_LOW)
        self.assertEqual(r['method'], 'BEST_GUESS_AMBIGUOUS')
        self.assertEqual(len(r['candidates']), 2)

    def test_wide_spread_with_valid_anchor_resolves_to_medium_confidence(self):
        cache = FakeCache({'Krishna Nagar, Delhi': {'results': [
            _result(28.6578127, 77.2901199, 8, 'Krishna Nagar, Preet Vihar'),
            _result(28.5637017, 77.1934098, 9, 'Krishna Nagar, South Delhi'),
        ]}})
        # Anchor near the Preet Vihar candidate, not the South Delhi one.
        anchor_coord = (28.6549, 77.2938)
        r = rank_candidates('Krishna Nagar', 'EXACT', cache, anchors=[anchor_coord])
        self.assertEqual(r['confidence'], CONFIDENCE_MEDIUM)
        self.assertEqual(r['method'], 'JOINT_DISAMBIGUATION')
        self.assertIn('Preet Vihar', r['chosen']['formatted'])

    def test_no_real_candidates_is_unresolved_not_an_error(self):
        cache = FakeCache({'Nowhere, Delhi': {'results': [
            _result(28.65381, 77.22897, 3, 'Delhi, North Delhi, India'),
        ]}})
        r = rank_candidates('Nowhere', 'EXACT', cache)
        self.assertEqual(r['confidence'], UNRESOLVED_NO_GEOCODE)
        self.assertIsNone(r['chosen'])

    def test_empty_results_is_unresolved(self):
        cache = FakeCache({'Nothing, Delhi': {'results': []}})
        r = rank_candidates('Nothing', 'EXACT', cache)
        self.assertEqual(r['confidence'], UNRESOLVED_NO_GEOCODE)

    def test_fuzzy_match_is_capped_below_high_even_when_clustered(self):
        cache = FakeCache({'Mehrauli, Delhi': {'results': [
            _result(28.5185, 77.1868, 9, 'Mehrauli A'),
            _result(28.5190, 77.1870, 8, 'Mehrauli B'),
        ]}})
        r = rank_candidates('Mehrauli', 'FUZZY', cache)
        self.assertNotEqual(r['confidence'], CONFIDENCE_HIGH)
        self.assertEqual(r['confidence'], CONFIDENCE_MEDIUM)

    def test_normalized_match_is_not_capped(self):
        cache = FakeCache({'Kalkaji, Delhi': {'results': [
            _result(28.5411, 77.2585, 9, 'Kalkaji'),
        ]}})
        r = rank_candidates('Kalkaji', 'NORMALIZED', cache)
        self.assertEqual(r['confidence'], CONFIDENCE_HIGH)

    def test_every_result_carries_a_reason(self):
        cache = FakeCache({'X, Delhi': {'results': [_result(28.6, 77.2, 9)]}})
        r = rank_candidates('X', 'EXACT', cache)
        self.assertTrue(r['reason'])


if __name__ == '__main__':
    unittest.main()
