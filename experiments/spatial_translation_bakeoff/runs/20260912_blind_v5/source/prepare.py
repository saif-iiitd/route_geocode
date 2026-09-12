"""Prepare input projection. This module is never imported by generation adapters."""
import re
import subprocess
from pathlib import Path
from .common import (ROOT, EXPERIMENT, BLIND_FIELDS, file_sha, read_csv,
                     write_csv_once, write_json_once, now, load_blind)


def prepare(root=ROOT, experiment=EXPERIMENT):
    root, experiment = Path(root), Path(experiment)
    canonical = read_csv(root / 'results/canonical_parser_input.csv')
    queue = read_csv(root / 'results/translation_work_queue.csv')
    eligible = {r['dataset_record_id']: r for r in canonical
                if r['parser_status'] == 'NEEDS_APPROVED_TRANSLATION'}
    if len(queue) != 815 or len(eligible) != 815 or len({r['dataset_record_id'] for r in queue}) != 815:
        raise ValueError('Queue coverage mismatch')
    if set(eligible) != {r['dataset_record_id'] for r in queue}:
        raise ValueError('Queue is not exactly the eligible canonical set')
    blind = []
    for q in queue:
        c = eligible[q['dataset_record_id']]
        if c['language_recorded'] != 'hi' or c['text_for_parser']:
            raise ValueError('Ineligible source record')
        if not re.search('[\u0900-\u097f]', c['text_original']):
            raise ValueError('Hindi source lacks Devanagari')
        if any(q[k] != c[k] for k in BLIND_FIELDS):
            raise ValueError('Queue/canonical mismatch')
        blind.append({k: q[k] for k in BLIND_FIELDS})
    blind.sort(key=lambda r: r['dataset_record_id'])
    path = experiment / 'blind_translation_input.csv'
    write_csv_once(path, blind, BLIND_FIELDS)
    load_blind(path)
    protected = [root / 'results/canonical_parser_input.csv', root / 'results/translation_work_queue.csv',
                 root / 'results/translation_discrepancies.csv', root / 'experiments/00_parser_input_provenance.md']
    for folder in ('data', 'docs', 'results/provenance_audit'):
        protected += [p for p in (root / folder).rglob('*') if p.is_file()]
    for pattern in ('*.ipynb', '*.docx', '*.xlsx'):
        protected += list(root.glob(pattern))
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True)
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=root, capture_output=True, text=True)
    write_json_once(experiment / 'preparation_manifest.json', {
        'prepared_at': now(), 'queue_count': len(blind), 'allowed_columns': BLIND_FIELDS,
        'blind_input_sha256': file_sha(path), 'source_commit': commit.stdout.strip(),
        'working_tree_dirty': bool(dirty.stdout.strip()),
        'protected_files': {p.relative_to(root).as_posix(): file_sha(p) for p in protected},
        'blinding': 'allowlist projection; generation has no audit imports; API requests have no tools or source URLs to fetch',
    })
    print('Prepared 815 blind records; no labels or legacy translations in generation input.')


if __name__ == '__main__':
    prepare()
