"""Tests for src/entity_resolution.py, using real corpus mentions found by
experiments/03_entity_resolution_audit.py (seed=20260913, 150-record sample)
as fixtures rather than invented examples.
"""
import unittest

from src.entity_resolution import (
    GAZETTEER_FUZZY_MATCH,
    GAZETTEER_GENERIC_AMBIGUOUS,
    GAZETTEER_NORMALIZED_MATCH,
    GAZETTEER_RESOLVED,
    OUT_OF_GAZETTEER_UNRESOLVED,
    classify_mention,
    load_gazetteer,
)


class TestEntityResolution(unittest.TestCase):
    def setUp(self):
        self.gazetteer = load_gazetteer()

    def test_specific_gazetteer_entry_is_resolved(self):
        # From: "...carriageway from Madhuban Chowk towards Peeragarhi..."
        result = classify_mention('Madhuban Chowk', self.gazetteer)
        self.assertEqual(result['candidate_status'], GAZETTEER_RESOLVED)
        self.assertEqual(result['gazetteer_match'], 'Madhuban Chowk')

    def test_match_is_case_insensitive(self):
        result = classify_mention('madhuban chowk', self.gazetteer)
        self.assertEqual(result['candidate_status'], GAZETTEER_RESOLVED)
        self.assertEqual(result['gazetteer_match'], 'Madhuban Chowk')

    def test_generic_single_word_term_is_flagged_ambiguous_not_resolved(self):
        # From: "...near Peeragarhi flyover." -- "flyover" alone names a feature
        # type; treating it as GAZETTEER_RESOLVED would silently pick one of many
        # real flyovers.
        result = classify_mention('flyover', self.gazetteer)
        self.assertEqual(result['candidate_status'], GAZETTEER_GENERIC_AMBIGUOUS)
        self.assertNotEqual(result['candidate_status'], GAZETTEER_RESOLVED)

    def test_generic_term_flagged_regardless_of_case(self):
        result = classify_mention('Flyover', self.gazetteer)
        self.assertEqual(result['candidate_status'], GAZETTEER_GENERIC_AMBIGUOUS)

    def test_mandi_generic_term_is_ambiguous(self):
        # From: "Water logging in front of Azadpur Mandi." -- here "Mandi" alone
        # would have been a separate span if the NER pipeline had split it from
        # "Azadpur"; the multi-word "Azadpur Mandi" match takes precedence via
        # filter_spans, but the bare generic term must still not resolve alone.
        result = classify_mention('Mandi', self.gazetteer)
        self.assertEqual(result['candidate_status'], GAZETTEER_GENERIC_AMBIGUOUS)

    def test_out_of_gazetteer_mention_is_not_fabricated_into_a_match(self):
        # From: "...breakdown of a DTC bus near Masoodpur..." -- a real place
        # (per experiment 03's audit) absent from the current gazetteer file.
        result = classify_mention('Andheria Mor', self.gazetteer)
        self.assertEqual(result['candidate_status'], OUT_OF_GAZETTEER_UNRESOLVED)
        self.assertIsNone(result['gazetteer_match'])

    def test_non_place_ner_noise_is_also_left_unresolved_not_guessed(self):
        # From: "Traffic is affected from DC office Nand Nagri..." -- base spaCy
        # NER tagged the acronym "DC" as an entity; it is not a place at all.
        # The module makes no attempt to distinguish this from a genuine
        # gazetteer gap -- both are surfaced as unresolved, not silently dropped
        # or silently geocoded.
        result = classify_mention('DC', self.gazetteer)
        self.assertEqual(result['candidate_status'], OUT_OF_GAZETTEER_UNRESOLVED)

    def test_every_result_carries_a_reason(self):
        for text in ('Madhuban Chowk', 'flyover', 'Andheria Mor'):
            result = classify_mention(text, self.gazetteer)
            self.assertTrue(result['reason'])

    # -- Alias handling (experiment 05): normalized and fuzzy match stages --

    def test_whitespace_variant_matches_via_normalization_not_fuzzy(self):
        # Real case from experiment 04: tweet text "Kalka Ji flyover" vs.
        # gazetteer's "Kalkaji". A plain fuzzy ratio scores this only 80 (the
        # same score as a real wrong match), but exact-after-normalization
        # catches it with zero ambiguity.
        result = classify_mention('Kalka Ji', self.gazetteer)
        self.assertEqual(result['candidate_status'], GAZETTEER_NORMALIZED_MATCH)
        self.assertEqual(result['gazetteer_match'], 'Kalkaji')
        self.assertEqual(result['match_method'], 'NORMALIZED')

    def test_spacing_variant_matches_via_normalization(self):
        # From experiment 03/05's unresolved-mention list: "Mangol Puri" vs.
        # gazetteer's "Mangolpuri".
        result = classify_mention('Mangol Puri', self.gazetteer)
        self.assertEqual(result['candidate_status'], GAZETTEER_NORMALIZED_MATCH)
        self.assertEqual(result['gazetteer_match'], 'Mangolpuri')

    def test_trailing_punctuation_matches_via_normalization(self):
        result = classify_mention('Red Fort-', self.gazetteer)
        self.assertEqual(result['candidate_status'], GAZETTEER_NORMALIZED_MATCH)
        self.assertEqual(result['gazetteer_match'], 'Red Fort')

    def test_real_typo_matches_via_high_confidence_fuzzy(self):
        # From experiment 05's audit: "Mehraulli" (typo) vs. gazetteer's
        # "Mehrauli", rapidfuzz ratio 94.1 -- well above the evidenced 90
        # threshold.
        result = classify_mention('Mehraulli', self.gazetteer)
        self.assertEqual(result['candidate_status'], GAZETTEER_FUZZY_MATCH)
        self.assertEqual(result['gazetteer_match'], 'Mehrauli')
        self.assertEqual(result['match_method'], 'FUZZY')
        self.assertGreaterEqual(result['fuzzy_score'], 90)

    def test_another_real_typo_matches_via_fuzzy(self):
        result = classify_mention('Samalka', self.gazetteer)
        self.assertEqual(result['candidate_status'], GAZETTEER_FUZZY_MATCH)
        self.assertEqual(result['gazetteer_match'], 'Samalkha')

    def test_below_threshold_fuzzy_candidate_is_left_unresolved_not_guessed(self):
        # From experiment 05's audit: "Heera Public School" scores 80 against
        # "SD Public School" -- a real wrong match at the same score band as
        # some correct ones. Below the evidenced 90 threshold, it must not be
        # silently accepted.
        result = classify_mention('Heera Public School', self.gazetteer)
        self.assertEqual(result['candidate_status'], OUT_OF_GAZETTEER_UNRESOLVED)
        self.assertIsNone(result['gazetteer_match'])

    def test_word_reordering_alone_does_not_produce_a_match(self):
        # "Nagar Kirtan" (a religious procession, not a place) is character-
        # similar-when-reordered to "Kirti Nagar" (a real place) -- a
        # word-order-tolerant scorer (token_sort_ratio) was tested and found
        # to score this 87, a dangerous false positive. The plain
        # character-level ratio used here must not match it.
        result = classify_mention('Nagar Kirtan', self.gazetteer)
        self.assertEqual(result['candidate_status'], OUT_OF_GAZETTEER_UNRESOLVED)

    def test_exact_match_still_reports_no_fuzzy_score(self):
        result = classify_mention('Madhuban Chowk', self.gazetteer)
        self.assertNotIn('fuzzy_score', result)
        self.assertEqual(result['match_method'], 'EXACT')


if __name__ == '__main__':
    unittest.main()
