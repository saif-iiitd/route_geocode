"""Corpus-backed provenance tests; no translation, models, network or geocoding."""
import copy
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import text_provenance as provenance
from src.parser_input import build_records, canonical_record, normalize_original, summary, translation_queue, validate_counts, EXPECTED_COUNTS

ROOT = Path(__file__).resolve().parents[1]


class ParserInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bound, cls.fingerprints = provenance.load_bound_records(ROOT)
        cls.records = build_records(ROOT)
        cls.by_id = {r['tweet_id']: r for r in cls.records if r['tweet_id']}

    def test_coverage_and_unique_stable_keys(self):
        self.assertEqual(len(self.records), 5144)
        self.assertEqual(len({r['dataset_record_id'] for r in self.records}), 5144)
        self.assertEqual(len(self.by_id), 5143)
        missing = next(r for r in self.records if not r['tweet_id'])
        self.assertEqual(missing['source_row_key'], '10235')
        self.assertEqual(missing['dataset_record_id'], provenance.record_id('10235'))

    def test_exact_ids_never_numeric(self):
        for record in self.records:
            self.assertIsInstance(record['tweet_id'], str)
            self.assertEqual(record['tweet_id'], provenance.exact_tweet_id(record['tweet_url']))
        self.assertIn('1032480895557660672', self.by_id)
        self.assertEqual(provenance.exact_tweet_id('https://evil.test/a/status/123'), '')
        self.assertEqual(provenance.exact_tweet_id('https://twitter.com/a/status/1e18'), '')

    def test_ready_uses_original_and_ignores_other_fields(self):
        for row, audit, evidence in self.bound:
            before = copy.deepcopy(row)
            record = canonical_record(row, audit, evidence, self.fingerprints)
            self.assertEqual(row, before)
            if record['parser_status'] == 'READY_ORIGINAL_EN':
                self.assertEqual(record['text_for_parser'], normalize_original(row['text']))
                poisoned = dict(row, translated_text='WRONG PLACE via WRONG ROAD', address='OTHER PLACE')
                self.assertEqual(canonical_record(poisoned, audit, evidence, self.fingerprints)['text_for_parser'],
                                 record['text_for_parser'])
            self.assertEqual(record['text_original'], row['text'])
            self.assertEqual(record['text_translated_legacy'], row['translated_text'])
            self.assertEqual(json.loads(record['existing_location_metadata']),
                             {k: row[k] for k in provenance.LOCATION_FIELDS})

    def test_jail_road_legacy_quarantined_original_ready(self):
        record = self.by_id['549389894830030848']
        self.assertEqual(record['text_for_parser'], 'Traffic is now normal at Jail Road towards Hari Nagar.')
        self.assertEqual(record['parser_status'], 'READY_ORIGINAL_EN')
        self.assertEqual(record['legacy_translation_status'], 'QUARANTINED')
        self.assertIn('LEGACY_JAIL_ROAD_TILAK_NAGAR_SUBSTITUTION', record['data_quality_flags'])

    def test_rk_puram_metadata_is_isolated(self):
        record = self.by_id['548889847658975232']
        self.assertIn('R.K Puram', record['text_for_parser'])
        self.assertNotIn('Keshav Puram', record['text_for_parser'])
        self.assertIn('Keshav Puram', json.loads(record['existing_location_metadata'])['address'])

    def test_source_corruption_blocked_even_with_verified_evidence(self):
        record = self.by_id['659764100164136960']
        self.assertEqual(record['text_original'], '#NAME?')
        self.assertIn('Shastri Park', record['text_from_verified_source'])
        self.assertIn('LEGACY_TRANSLATION_PREVIOUS_ROW_CONTAMINATION', record['data_quality_flags'])
        for record in (record, next(r for r in self.records if not r['tweet_id'])):
            self.assertIn(record['parser_status'], ('SOURCE_REPAIR_REQUIRED', 'QUARANTINE_SOURCE_CORRUPTION'))
            self.assertIsNone(record['text_for_parser'])
        spill = next(r for r in self.records if not r['tweet_id'])
        self.assertIn('SOURCE_FIELD_SPILL', spill['data_quality_flags'])
        self.assertTrue(json.loads(spill['existing_location_metadata'])['geo'])

    def test_non_english_has_no_implicit_translation(self):
        for record in self.records:
            if record['language_original'] == 'hi':
                self.assertTrue(record['translation_required'])
                self.assertIn('PARSER_TRANSLATION_REQUIRED', record['data_quality_flags'])
                self.assertIsNone(record['text_for_parser'])
                self.assertEqual(record['text_translated_approved'], '')
                self.assertEqual(record['protected_mentions_status'], 'NOT_ANNOTATED')
        counts = summary(self.records)
        self.assertEqual(counts['parser_status'], EXPECTED_COUNTS)

    def test_queue_and_audit_preservation(self):
        queue = translation_queue(self.records)
        self.assertEqual(len(queue), 815)
        for record, (_, audit, _) in zip(self.records, self.bound):
            self.assertEqual(json.loads(record['audit_evidence']), audit)
            for key, value in audit.items():
                self.assertEqual(record[key], value)
            if record['language_recorded'] == 'id':
                self.assertEqual(record['parser_status'], 'LANGUAGE_REVIEW')
                self.assertEqual(record['language_original'], 'id')
        self.assertEqual({r['dataset_record_id'] for r in queue},
                         {r['dataset_record_id'] for r in self.records if r['parser_status'] == 'NEEDS_APPROVED_TRANSLATION'})
        with self.assertRaisesRegex(ValueError, 'reconciliation'):
            validate_counts(self.records[:-1])

    def test_all_audit_severe_and_unresolved_are_flagged(self):
        for record in self.records:
            if record['audit_class'] in ('SEVERE_SPATIAL_DISCREPANCY', 'UNRESOLVED_CROSS_LANGUAGE'):
                self.assertEqual(record['legacy_translation_status'], 'QUARANTINED')
                self.assertIn('LEGACY_REQUIRES_MANUAL_INSPECTION', record['data_quality_flags'])

    def test_safe_normalization_preserves_names_order_relations(self):
        text = 'Traffic Alert\n from Jail Road to R.K Puram towards AIIMS via A on B along C near D between E and F'
        self.assertEqual(normalize_original(text),
                         'from Jail Road to R.K Puram towards AIIMS via A on B along C near D between E and F')
        self.assertEqual(normalize_original('Traffic Alertness on A'), 'Traffic Alertness on A')

    def test_evidence_reordering_is_safe_and_misalignment_rejected(self):
        real_reader = provenance.read_csv
        def reordered(path):
            rows = real_reader(path)
            return rows if Path(path).name == 'tweets_data.csv' else list(reversed(rows))
        with patch.object(provenance, 'read_csv', side_effect=reordered):
            self.assertEqual(build_records(ROOT), self.records)
        def damaged(path):
            rows = real_reader(path)
            if Path(path).name == 'translation_discrepancies.csv':
                rows[0]['text_original'] = 'misaligned text'
            return rows
        with patch.object(provenance, 'read_csv', side_effect=damaged):
            with self.assertRaisesRegex(ValueError, 'alignment mismatch'):
                build_records(ROOT)

    def test_clean_processes_are_byte_identical_and_sources_unchanged(self):
        paths = list((ROOT / 'docs').glob('*')) + list((ROOT / 'results/provenance_audit').glob('*')) + [ROOT / 'results/translation_discrepancies.csv'] + list((ROOT / 'Data').glob('*')) + list(ROOT.glob('*.ipynb')) + list(ROOT.glob('*.docx')) + list(ROOT.glob('*.xlsx'))
        before = {p: provenance.digest(p) for p in paths if p.is_file()}
        with tempfile.TemporaryDirectory() as folder:
            outputs = [Path(folder) / f'canonical-{n}.csv' for n in range(2)]
            for output in outputs:
                subprocess.run([sys.executable, '-B', '-m', 'src.parser_input', '--output', str(output), '--queue-output', str(output.with_suffix('.queue.csv'))],
                               cwd=ROOT, check=True, capture_output=True,
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            self.assertEqual(outputs[0].with_suffix('.queue.csv').read_bytes(), outputs[1].with_suffix('.queue.csv').read_bytes())
            with outputs[0].open(encoding='utf-8', newline='') as stream:
                reread = list(csv.DictReader(stream))
            self.assertEqual(reread[0]['tweet_id'], '549389894830030848')
        self.assertEqual(before, {p: provenance.digest(p) for p in before})


if __name__ == '__main__':
    unittest.main()
