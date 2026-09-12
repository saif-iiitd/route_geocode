"""Run blind smoke/full arms, then close generation before any evaluation.

Usage: python -B -m src.translation_bakeoff.generate --run-id <unique-id>
No audit/canonical/queue file is read by this module or an adapter.
"""
import argparse
import importlib.metadata
import json
import os
import platform
import re
import sys
import time
from pathlib import Path
from .common import (ROOT, EXPERIMENT, SYSTEMS, now, dumps, sha, file_sha, load_blind,
                     smoke_sample, write_csv_once, write_json_once, write_text_once)
from .adapters import ARMS, preflight, ProviderFailure
from .schema import SCHEMA


def environment():
    packages = {}
    for package in ('torch', 'transformers', 'IndicTransToolkit', 'sentencepiece',
                    'google-cloud-translate', 'google-auth', 'huggingface-hub'):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = 'NOT_INSTALLED'
    return {'python': sys.version, 'platform': platform.platform(), 'packages': packages}


def install_source_read_guard(root):
    """Deny corpus/QA reads in generation process, including provider library code.

    This is defense in depth, not an OS sandbox. Remote providers receive no tools.
    """
    root = Path(root).resolve()
    forbidden_dirs = [root / 'data', root / 'docs', root / 'results']
    def guard(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        lower = str(path).casefold()
        if any(lower == str(d).casefold() or lower.startswith(str(d).casefold() + os.sep) for d in forbidden_dirs):
            raise PermissionError('Blind generation source/QA read guard')
    sys.addaudithook(guard)


def candidate_rows(records, system, config, adapter, blocked, run_id, input_hash):
    rows, events, aligned = [], [], []
    for record in records:
        translation, structured, metadata = '', None, {}
        status, error = 'BLOCKED_NOT_ATTEMPTED', ';'.join(blocked)
        elapsed, timestamp, attempted = '', '', False
        if adapter is not None and not blocked:
            start, timestamp, attempted = time.perf_counter(), now(), True
            try:
                translation, structured, metadata = adapter.translate(record)
                if not isinstance(translation, str) or not translation.strip():
                    raise ProviderFailure('EMPTY_OUTPUT')
                status, error = 'SUCCESS', ''
            except Exception as exc:
                # Never stringify provider exceptions: URLs/bodies may contain secrets.
                status = 'GENERATION_FAILED'
                error = exc.code if isinstance(exc, ProviderFailure) else 'PROVIDER_EXCEPTION_' + type(exc).__name__
                translation, structured = '', None
            elapsed = round(time.perf_counter() - start, 6)
        row = {'dataset_record_id': record['dataset_record_id'], 'tweet_id': record['tweet_id'],
               'system': system, 'model': config['model'],
               'model_version_or_revision': metadata.get('actual_model') or config.get('revision') or 'UNAVAILABLE_NOT_RETURNED',
               'generated_translation': translation, 'generation_status': status,
               'generation_timestamp': timestamp, 'run_id': run_id,
               'input_sha256': input_hash, 'record_input_sha256': sha(dumps(record).encode()),
               'output_sha256': sha(translation.encode()) if status == 'SUCCESS' else '',
               'attempted': attempted, 'runtime_seconds': elapsed, 'error_code': error,
               'metadata_json': dumps(metadata)}
        rows.append(row)
        events.append({'dataset_record_id': record['dataset_record_id'], 'event_timestamp': now(),
                       'attempt_number': 1 if attempted else 0, 'status': status,
                       'error_code': error, 'metadata': metadata, 'runtime_seconds': elapsed})
        if system == 'openai':
            aligned.append({'dataset_record_id': record['dataset_record_id'],
                            'generation_status': status, 'alignment': structured, 'metadata': metadata})
    return rows, events, aligned


def save_phase(directory, records, system, config, adapter, blocked, run_id, input_hash):
    rows, events, aligned = candidate_rows(records, system, config, adapter, blocked, run_id, input_hash)
    write_csv_once(directory / 'candidates.csv', rows)
    write_text_once(directory / 'requests.jsonl', ''.join(dumps(e) + '\n' for e in events))
    if system == 'openai':
        write_text_once(directory / 'alignment.jsonl', ''.join(dumps(e) + '\n' for e in aligned))
    return rows


def run(run_id, experiment=EXPERIMENT):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('Invalid run ID')
    experiment = Path(experiment)
    run_root = experiment / 'runs' / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    config = json.loads((experiment / 'config/run_config.json').read_text(encoding='utf-8'))
    if config['retries'] != 0:
        raise ValueError('This harness uses exactly one logged attempt; no hidden retries')
    project_var = config['systems']['google']['project_environment_variable']
    config['systems']['google']['project'] = config['systems']['google']['project'] or os.getenv(project_var)
    prompt = (experiment / 'prompts/openai_spatial_translation.txt').read_text(encoding='utf-8')
    records = load_blind(experiment / 'blind_translation_input.csv')
    input_hash = file_sha(experiment / 'blind_translation_input.csv')
    sample = smoke_sample(records, config['smoke_seed'])
    write_csv_once(run_root / 'smoke_input.csv', sample)
    write_json_once(run_root / 'environment.json', environment())
    # Snapshot implementation, not just the already-dirty repository commit.
    code_files = sorted(Path(__file__).parent.glob('*.py'))
    for path in code_files:
        write_text_once(run_root / 'source' / path.name, path.read_text(encoding='utf-8'))
    write_json_once(run_root / 'schema.json', SCHEMA)
    adapters, blockers, smoke = {}, {}, {}
    for system in SYSTEMS:
        cfg = config['systems'][system]
        blocked = preflight(system, cfg)
        adapter = None
        if not blocked:
            try:
                adapter = ARMS[system](cfg, prompt)
            except Exception as exc:
                blocked.append('INITIALIZATION_FAILED_' + type(exc).__name__)
        base = experiment / 'runs' / system / run_id
        smoke_rows = save_phase(base / 'smoke', sample, system, cfg, adapter, blocked,
                                run_id, input_hash)
        failures = sum(r['generation_status'] != 'SUCCESS' for r in smoke_rows)
        smoke[system] = {'selected_records': len(sample), 'successful': len(sample) - failures,
                         'technical_gate': 'PASS' if failures == 0 else 'BLOCKED' if blocked else 'FAIL',
                         'blockers': blocked, 'audit_labels_inspected': False}
        if failures and not blocked:
            blocked = ['FULL_RUN_NOT_STARTED_SMOKE_TECHNICAL_FAILURE']
        adapters[system], blockers[system] = adapter, blocked
        print(system + ': smoke ' + smoke[system]['technical_gate'], flush=True)
    # No semantic tuning: freeze after the common smoke gate, including blocked gates.
    write_json_once(run_root / 'smoke_report.json', smoke)
    write_json_once(run_root / 'frozen_config.json', config)
    write_text_once(run_root / 'frozen_prompt.txt', prompt)
    write_json_once(run_root / 'config_freeze.json', {
        'frozen_at': now(), 'configuration_sha256': file_sha(run_root / 'frozen_config.json'),
        'prompt_sha256': file_sha(run_root / 'frozen_prompt.txt'),
        'schema_sha256': file_sha(run_root / 'schema.json'), 'input_sha256': input_hash,
        'smoke_integration_proven': {s: smoke[s]['technical_gate'] == 'PASS' for s in SYSTEMS},
        'prompt_tuning_after_smoke': False})
    for system in SYSTEMS:
        base = experiment / 'runs' / system / run_id
        full = save_phase(base, records, system, config['systems'][system], adapters[system],
                          blockers[system], run_id, input_hash)
        if len(full) != 815 or len({r['dataset_record_id'] for r in full}) != 815:
            raise ValueError('Full arm coverage mismatch')
    files = [p for p in run_root.rglob('*') if p.is_file()]
    for system in SYSTEMS:
        files += [p for p in (experiment / 'runs' / system / run_id).rglob('*') if p.is_file()]
    files += [experiment / 'blind_translation_input.csv']
    write_json_once(run_root / 'freeze.json', {
        'run_id': run_id, 'frozen_at': now(), 'candidate_generation_closed': True,
        'systems': list(SYSTEMS), 'input_sha256': input_hash,
        'files': {p.relative_to(experiment).as_posix(): file_sha(p) for p in files},
        'blocked_systems': blockers, 'quality_comparison_available': any(not b for b in blockers.values())})
    # First-run discovery copies are write-once, never updated for later runs.
    for system in SYSTEMS:
        destination = experiment / 'runs' / system / 'candidates.csv'
        if not destination.exists():
            write_text_once(destination, (experiment / 'runs' / system / run_id / 'candidates.csv').read_text(encoding='utf-8'))
    print('Candidate generation closed and hashes frozen: ' + run_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    install_source_read_guard(ROOT)
    run(args.run_id)


if __name__ == '__main__':
    main()
