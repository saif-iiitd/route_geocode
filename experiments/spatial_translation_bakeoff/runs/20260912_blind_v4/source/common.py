"""Artifact contracts shared by blind generation and post-freeze evaluation."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / 'experiments/spatial_translation_bakeoff'
BLIND_FIELDS = ['dataset_record_id', 'tweet_id', 'tweet_url', 'text_original']
SYSTEMS = ('indictrans2', 'google', 'openai', 'huggingface')
# Arms that return a self-reported structured alignment alongside the translation.
STRUCTURED_SYSTEMS = ('openai', 'huggingface')


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return sha(Path(path).read_bytes())


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_text_once(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='') as f:
        f.write(text)


def write_json_once(path, value):
    write_text_once(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def write_csv_once(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def blind_record(record):
    if set(record) != set(BLIND_FIELDS):
        raise ValueError('Blind input must have exactly the four allowed fields')
    if any(not isinstance(record[k], str) or not record[k] for k in BLIND_FIELDS):
        raise ValueError('Empty or non-string blind field')
    if not record['tweet_id'].isdigit() or not record['tweet_url'].rstrip('/').endswith('/status/' + record['tweet_id']):
        raise ValueError('Exact tweet ID does not match status permalink')
    return {k: record[k] for k in BLIND_FIELDS}


def load_blind(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != BLIND_FIELDS:
            raise ValueError('Forbidden or unexpected blind CSV columns')
        records = [blind_record(r) for r in reader]
    if len(records) != 815 or len({r['dataset_record_id'] for r in records}) != 815:
        raise ValueError('Blind input coverage must be 815 unique records')
    if len({r['tweet_id'] for r in records}) != 815:
        raise ValueError('Duplicate exact tweet ID')
    return records


def smoke_sample(records, seed=20260912):
    return sorted(records, key=lambda r: sha((str(seed) + ':' + r['dataset_record_id']).encode()))[:20]


def verify_freeze(experiment, run_id):
    run_root = Path(experiment) / 'runs' / run_id
    frozen = json.loads((run_root / 'freeze.json').read_text(encoding='utf-8'))
    if not frozen.get('candidate_generation_closed'):
        raise ValueError('Candidates are not frozen; audit reveal is forbidden')
    if set(frozen['systems']) != set(SYSTEMS):
        raise ValueError('Missing frozen arm')
    for rel, expected in frozen['files'].items():
        if file_sha(Path(experiment) / rel) != expected:
            raise ValueError('Frozen artifact hash mismatch: ' + rel)
    return frozen
