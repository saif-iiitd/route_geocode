"""Manual ChatGPT-in-a-new-chat arm: batch preparation and output ingestion.

This is not a live API adapter (no key, no automated request) -- the user pastes
each batch's prompt into a fresh ChatGPT chat themselves and hands back the JSON
reply. It is still blind: each batch carries only the four allowed fields plus the
same generic rules used by every other arm, and each paste happens in a chat with
no prior context. Ingestion applies the identical schema/reference validation as
every automated arm; a malformed or incomplete batch reply is a recorded failure
for those records, never silently patched, reordered or invented.
"""
import argparse
import json
from pathlib import Path
from .common import EXPERIMENT, BLIND_FIELDS, dumps, load_blind, write_text_once, write_csv_once
from .schema import validate_alignment

BATCH_DIR = EXPERIMENT / 'chatgpt_manual/batches'
OUTPUT_DIR = EXPERIMENT / 'chatgpt_manual/outputs'
BATCH_SIZE = 60


def prepare_batches(batch_size=BATCH_SIZE):
    records = load_blind(EXPERIMENT / 'blind_translation_input.csv')
    prompt = (EXPERIMENT / 'prompts/chatgpt_manual_batch_prompt.txt').read_text(encoding='utf-8')
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        index = start // batch_size + 1
        path = BATCH_DIR / f'batch_{index:03d}.txt'
        body = prompt + json.dumps([{k: r[k] for k in BLIND_FIELDS} for r in batch],
                                    ensure_ascii=False, indent=2)
        if not path.exists():
            write_text_once(path, body)
        manifest.append({'batch': index, 'file': path.name, 'record_count': len(batch),
                          'dataset_record_ids': [r['dataset_record_id'] for r in batch],
                          'output_expected_at': f'chatgpt_manual/outputs/batch_{index:03d}_output.json'})
    manifest_path = BATCH_DIR.parent / 'batch_manifest.json'
    if not manifest_path.exists():
        write_text_once(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(f'{len(manifest)} batches ready under {BATCH_DIR}')
    print(f'Paste each batch_NNN.txt into a NEW ChatGPT chat; save the raw JSON reply as '
          f'{OUTPUT_DIR}/batch_NNN_output.json (matching filename), then run ingest.')
    return manifest


def ingest(manifest=None):
    manifest = manifest or json.loads((BATCH_DIR.parent / 'batch_manifest.json').read_text(encoding='utf-8'))
    records = {r['dataset_record_id']: r for r in load_blind(EXPERIMENT / 'blind_translation_input.csv')}
    rows, missing_batches = [], []
    for entry in manifest:
        out_path = OUTPUT_DIR / f"batch_{entry['batch']:03d}_output.json"
        expected_ids = entry['dataset_record_ids']
        if not out_path.exists():
            missing_batches.append(entry['batch'])
            for rid in expected_ids:
                rows.append(_failed_row(rid, records[rid], 'BATCH_OUTPUT_NOT_YET_PROVIDED'))
            continue
        try:
            items = json.loads(out_path.read_text(encoding='utf-8'))
            if not isinstance(items, list):
                raise ValueError('not a JSON array')
        except (ValueError, TypeError):
            for rid in expected_ids:
                rows.append(_failed_row(rid, records[rid], 'BATCH_OUTPUT_NOT_VALID_JSON_ARRAY'))
            continue
        by_id = {}
        for item in items:
            rid = item.get('dataset_record_id') if isinstance(item, dict) else None
            if rid in expected_ids and rid not in by_id:
                by_id[rid] = item
        for rid in expected_ids:
            item = by_id.get(rid)
            if item is None:
                rows.append(_failed_row(rid, records[rid], 'RECORD_MISSING_FROM_BATCH_OUTPUT'))
                continue
            try:
                validate_alignment(item, records[rid]['text_original'])
                if not item['translation'].strip():
                    raise ValueError('empty translation')
            except (ValueError, TypeError, KeyError):
                rows.append(_failed_row(rid, records[rid], 'MALFORMED_STRUCTURED_OUTPUT'))
                continue
            rows.append({'dataset_record_id': rid, 'tweet_id': records[rid]['tweet_id'],
                         'system': 'chatgpt_manual', 'model': 'chatgpt-web-manual-paste',
                         'model_version_or_revision': 'UNKNOWN_NOT_REPORTED_BY_WEB_UI',
                         'generated_translation': item['translation'], 'generation_status': 'SUCCESS',
                         'generation_timestamp': '', 'run_id': 'manual', 'input_sha256': '',
                         'record_input_sha256': '', 'output_sha256': '', 'attempted': True,
                         'runtime_seconds': '', 'error_code': '', 'metadata_json': dumps({'alignment': item})})
    if missing_batches:
        print('Batches not yet provided:', missing_batches)
    out_csv = OUTPUT_DIR.parent / 'candidates.csv'
    write_csv_once(out_csv, rows) if not out_csv.exists() else _rewrite(out_csv, rows)
    successes = sum(r['generation_status'] == 'SUCCESS' for r in rows)
    print(f'{successes}/{len(rows)} records successfully ingested -> {out_csv}')
    return rows


def _failed_row(rid, record, code):
    return {'dataset_record_id': rid, 'tweet_id': record['tweet_id'], 'system': 'chatgpt_manual',
            'model': 'chatgpt-web-manual-paste', 'model_version_or_revision': 'UNKNOWN_NOT_REPORTED_BY_WEB_UI',
            'generated_translation': '', 'generation_status': 'GENERATION_FAILED', 'generation_timestamp': '',
            'run_id': 'manual', 'input_sha256': '', 'record_input_sha256': '', 'output_sha256': '',
            'attempted': code != 'BATCH_OUTPUT_NOT_YET_PROVIDED', 'runtime_seconds': '', 'error_code': code,
            'metadata_json': '{}'}


def _rewrite(path, rows):
    # Ingestion is re-run as more batches come back; unlike frozen harness arms this
    # file is explicitly a live-updating working copy, not a one-shot frozen artifact.
    path.unlink()
    write_csv_once(path, rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'ingest'])
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare_batches(args.batch_size)
    else:
        ingest()


if __name__ == '__main__':
    main()
