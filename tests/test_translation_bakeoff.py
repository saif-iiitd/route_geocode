"""No real translation services called by tests; mocks stay in temporary fixtures."""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.translation_bakeoff.common import (EXPERIMENT, BLIND_FIELDS, SYSTEMS, blind_record, dumps, file_sha,
    load_blind, smoke_sample, write_csv_once, write_json_once, write_text_once, verify_freeze)
from src.translation_bakeoff.schema import validate_alignment
from src.translation_bakeoff.adapters import (openai_request, OpenAIArm, GoogleArm, OllamaArm,
    ollama_request, strip_code_fence, ProviderFailure)
from src.translation_bakeoff.generate import run, candidate_rows
from src.translation_bakeoff.validate import screen
from src.translation_bakeoff.evaluate import evaluate


def record(n=1):
    return {'dataset_record_id': f'record:{n:064d}', 'tweet_id': str(1000000000000000000+n),
            'tweet_url': f'https://twitter.com/example/status/{1000000000000000000+n}',
            'text_original': 'दिल्ली से दिल्ली की ओर 12:30 बजे यातायात बंद है।'}


def alignment():
    return {'translation': 'Traffic from Delhi towards Delhi is closed at 12:30.',
            'place_mentions': [dict(original_surface='दिल्ली', english_surface='Delhi',
                mention_order=n, feature_type='place', uncertain=False) for n in (1, 2)],
            'spatial_relations': [dict(relation='towards', source_mention_order=1, target_mention_order=2, uncertain=False)],
            'route_clause_count': 1, 'translation_uncertainties': []}


class BlindContractTests(unittest.TestCase):
    def test_forbidden_columns_fail(self):
        for key in ('text_translated_legacy', 'audit_class', 'discrepancy_tags', 'relation_flags',
                    'review_note', 'known_original_toponyms', 'address'):
            with self.assertRaises(ValueError):
                blind_record(dict(record(), **{key: 'forbidden'}))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'bad.csv'
            write_csv_once(p, [dict(record(), audit_class='forbidden')])
            with self.assertRaisesRegex(ValueError, 'columns'):
                load_blind(p)

    def test_exact_ids_and_sample_independent_of_order(self):
        records = [record(n) for n in range(815)]
        self.assertEqual(smoke_sample(records), smoke_sample(list(reversed(records))))
        self.assertEqual(len(smoke_sample(records)), 20)
        self.assertIsInstance(blind_record(record())['tweet_id'], str)
        with self.assertRaises(ValueError):
            blind_record(dict(record(), tweet_id=1e18))

    def test_openai_payload_is_blind_and_tool_free(self):
        cfg = {'model': 'gpt-5.6-sol', 'max_output_tokens': 8192, 'reasoning_effort': 'low'}
        payload = openai_request(record(), cfg, 'Generic rules only.')
        self.assertEqual(json.loads(payload['input']), record())
        self.assertNotIn('tools', payload)
        self.assertNotIn('temperature', payload)
        self.assertEqual(payload['model'], 'gpt-5.6-sol')
        self.assertTrue(payload['text']['format']['strict'])

    def test_structured_alignment_repeats_schema_and_reference_errors(self):
        good = alignment()
        validate_alignment(good, record()['text_original'])
        for mutate in ('invalid_ref', 'extra', 'reversed', 'missing_repeat', 'wrong_type'):
            bad = alignment()
            if mutate == 'invalid_ref': bad['spatial_relations'][0]['target_mention_order'] = 3
            if mutate == 'extra': bad['coordinates'] = []
            if mutate == 'reversed': bad['place_mentions'][0]['mention_order'] = 2
            if mutate == 'missing_repeat': bad['place_mentions'].append(dict(bad['place_mentions'][0], mention_order=3))
            if mutate == 'wrong_type': bad['route_clause_count'] = True
            with self.assertRaises(ValueError):
                validate_alignment(bad, record()['text_original'])

    def test_writes_immutable_and_serialization_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d)/'a.csv', Path(d)/'b.csv'
            write_csv_once(a, [record()]); write_csv_once(b, [record()])
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with self.assertRaises(FileExistsError):
                write_csv_once(a, [record(2)])

    def test_errors_never_log_exception_secrets(self):
        class Bad:
            def translate(self, r):
                raise RuntimeError('SECRET_TEST_API_KEY=never-output')
        rows, events, _ = candidate_rows([record()], 'google', {'model': 'general/nmt'},
                                         Bad(), [], 'test', 'inputhash')
        self.assertNotIn('never-output', dumps([rows, events]))
        self.assertEqual(rows[0]['generation_status'], 'GENERATION_FAILED')
        self.assertEqual(rows[0]['generated_translation'], '')

    def test_no_auto_validation_without_gold(self):
        candidate = {'generation_status': 'SUCCESS', 'generated_translation': alignment()['translation']}
        result = screen(record()['text_original'], candidate)
        self.assertEqual(result['validation_state'], 'REVIEW_REQUIRED')
        self.assertFalse(result['auto_approval'])
        self.assertEqual(result['numeric_time'], 'DIGIT_TOKENS_MATCH_NOT_SEMANTIC_PROOF')
        bad = screen(record()['text_original'], dict(candidate, generated_translation='Traffic is open at 13:30.'))
        self.assertEqual(bad['numeric_time'], 'POSSIBLE_DISCREPANCY')
        self.assertEqual(bad['traffic_status'], 'POSSIBLE_DISCREPANCY')
        failed = screen(record()['text_original'], {'generation_status': 'BLOCKED_NOT_ATTEMPTED'})
        self.assertEqual(failed['validation_state'], 'GENERATION_FAILED')

    def test_alignment_cannot_approve_but_can_flag_internal_inconsistency(self):
        candidate = {'generation_status': 'SUCCESS', 'generated_translation': 'Traffic from Delhi is closed at 12:30.'}
        result = screen(record()['text_original'], candidate, alignment())
        self.assertEqual(result['validation_state'], 'STRUCTURAL_MISMATCH')
        self.assertFalse(result['auto_approval'])

    def test_evaluation_refuses_unfrozen_before_audit_read(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('src.translation_bakeoff.evaluate.read_csv') as reader:
                with self.assertRaises(FileNotFoundError):
                    evaluate('not-frozen', Path(d), Path(d))
                reader.assert_not_called()

    def test_offline_full_harness_blocks_without_fake_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            exp = Path(d)
            write_csv_once(exp/'blind_translation_input.csv', [record(n) for n in range(815)], BLIND_FIELDS)
            write_text_once(exp/'config/run_config.json', (EXPERIMENT/'config/run_config.json').read_text())
            write_text_once(exp/'prompts/openai_spatial_translation.txt', 'Generic translation instructions.')
            write_text_once(exp/'prompts/ollama_spatial_translation.txt', 'Generic translation instructions.')
            with patch('src.translation_bakeoff.generate.preflight', return_value=['TEST_NO_CREDENTIALS']):
                run('test-only', exp)
            freeze = verify_freeze(exp, 'test-only')
            self.assertTrue(freeze['candidate_generation_closed'])
            for system in SYSTEMS:
                with (exp/f'runs/{system}/test-only/candidates.csv').open(encoding='utf-8',newline='') as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(len(rows), 815)
                self.assertTrue(all(r['generation_status'] == 'BLOCKED_NOT_ATTEMPTED' for r in rows))
                self.assertTrue(all(r['generated_translation'] == '' and r['attempted'] == 'False' for r in rows))
            with self.assertRaises(FileExistsError):
                run('test-only', exp)
            (exp/'runs/openai/test-only/candidates.csv').write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                verify_freeze(exp, 'test-only')

    def test_openai_real_adapter_contract_with_mock_transport(self):
        class Response:
            headers = {'x-request-id': 'test-id'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return dumps({'status': 'completed', 'model': 'gpt-5.6-sol', 'id': 'test-response',
                    'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': dumps(alignment())}]}]}).encode()
        cfg = {'model': 'gpt-5.6-sol', 'max_output_tokens': 8192, 'reasoning_effort': 'low'}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'TEST_ONLY'}):
            with patch('urllib.request.urlopen', return_value=Response()) as request:
                translated, structured, metadata = OpenAIArm(cfg, 'Generic instructions').translate(record())
        self.assertEqual(translated, alignment()['translation'])
        self.assertEqual(metadata['actual_model'], 'gpt-5.6-sol')
        self.assertEqual(json.loads(request.call_args.args[0].data)['input'], dumps(record()))

    def test_ollama_payload_is_blind_schema_enforced_and_tool_free(self):
        cfg = {'model': 'gemma4:e4b', 'temperature': 0, 'seed': 1}
        payload = ollama_request(record(), cfg, 'Generic rules only.')
        self.assertEqual(json.loads(payload['messages'][1]['content']), record())
        self.assertEqual(payload['messages'][0], {'role': 'system', 'content': 'Generic rules only.'})
        self.assertEqual(payload['model'], 'gemma4:e4b')
        self.assertIn('translation', payload['format']['properties'])
        self.assertFalse(payload['stream'])
        with self.assertRaises(ValueError):
            ollama_request(dict(record(), extra_field='forbidden'), cfg, 'x')

    def test_strip_code_fence_removes_single_fence_only(self):
        self.assertEqual(strip_code_fence('```json\n{"a": 1}\n```'), '{"a": 1}')
        self.assertEqual(strip_code_fence('{"a": 1}'), '{"a": 1}')
        self.assertEqual(strip_code_fence('```\n{"a": 1}\n```'), '{"a": 1}')

    def test_ollama_real_adapter_contract_with_mock_transport(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return dumps({'done': True, 'model': 'gemma4:e4b',
                    'message': {'role': 'assistant', 'content': dumps(alignment())},
                    'eval_count': 5, 'eval_duration': 1000, 'load_duration': 0, 'total_duration': 1000}).encode()
        cfg = {'model': 'gemma4:e4b', 'host': 'http://localhost:11434', 'temperature': 0, 'seed': 1}
        with patch('urllib.request.urlopen', return_value=Response()) as request:
            translated, structured, metadata = OllamaArm(cfg, 'Generic instructions').translate(record())
        self.assertEqual(translated, alignment()['translation'])
        self.assertEqual(metadata['actual_model'], 'gemma4:e4b')
        sent = json.loads(request.call_args.args[0].data)
        self.assertEqual(json.loads(sent['messages'][1]['content']), record())
        self.assertEqual(request.call_args.args[0].full_url, 'http://localhost:11434/api/chat')

    def test_ollama_malformed_output_is_a_status_not_a_crash_or_repair(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return dumps({'done': True, 'model': 'gemma4:e4b',
                              'message': {'role': 'assistant', 'content': 'not json at all'}}).encode()
        cfg = {'model': 'gemma4:e4b', 'host': 'http://localhost:11434', 'temperature': 0, 'seed': 1}
        with patch('urllib.request.urlopen', return_value=Response()):
            with self.assertRaises(ProviderFailure) as ctx:
                OllamaArm(cfg, 'x').translate(record())
        self.assertEqual(ctx.exception.code, 'MALFORMED_STRUCTURED_OUTPUT')

    def test_google_request_contract_no_glossary(self):
        class Translation:
            translated_text, model = 'test output', 'general/nmt'
        class Response:
            translations = [Translation()]
        from unittest.mock import Mock
        arm = GoogleArm.__new__(GoogleArm)
        arm.config = {'project': 'test-project', 'location': 'global'}
        arm.client = Mock()
        arm.client.translate_text.return_value = Response()
        arm.translate(record())
        kwargs = arm.client.translate_text.call_args.kwargs
        self.assertEqual(kwargs['request']['contents'], [record()['text_original']])
        self.assertNotIn('glossary_config', kwargs['request'])
        self.assertIsNone(kwargs['retry'])


if __name__ == '__main__':
    unittest.main()
