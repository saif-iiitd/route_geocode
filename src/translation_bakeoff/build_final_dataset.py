"""Build the final joined translation-bakeoff dataset for the 815-record Hindi queue.

Joins, by dataset_record_id, the canonical parser-input/provenance fields (from
results/canonical_parser_input.csv and results/translation_work_queue.csv) with every
translation candidate produced this session (IndicTrans2, ChatGPT-manual, plus the
still-blocked Google/OpenAI arms) and their automated validate.py screens, and the
25-record human blind ballot where it exists.

Follows this project's standing rule: never overwrite or flatten legacy/source
fields. Every new column is added under an explicit <arm>_ prefix; nothing already
in canonical_parser_input.csv or translation_work_queue.csv is modified or dropped.
Run from the repository root:

    python -B -m src.translation_bakeoff.build_final_dataset
"""
import json
from pathlib import Path
from .common import ROOT, EXPERIMENT, read_csv, write_csv_once, write_text_once, dumps

OUT_CSV = ROOT / 'results/translation_bakeoff_final_dataset.csv'
OUT_DICT = ROOT / 'results/translation_bakeoff_final_dataset_fields.md'

ARM_CANDIDATE_PATHS = {
    'indictrans2': EXPERIMENT / 'runs/indictrans2/20260912_blind_v5/candidates.csv',
    'google': EXPERIMENT / 'runs/google/20260912_blind_v5/candidates.csv',
    'openai': EXPERIMENT / 'runs/openai/20260912_blind_v5/candidates.csv',
    'chatgpt_manual': EXPERIMENT / 'chatgpt_manual/candidates.csv',
}
ARM_VALIDATION_PATHS = {
    'indictrans2': EXPERIMENT / 'validation/20260912_blind_v5/validation_results.csv',
    'chatgpt_manual': EXPERIMENT / 'chatgpt_manual/validation_results.csv',
}
VALIDATION_FIELDS = ['validation_state', 'flags', 'place_drop', 'place_addition', 'mention_order',
    'direction_reversal', 'route_clause_count', 'relation_loss', 'feature_type', 'numeric_time',
    'traffic_status', 'residual_devanagari', 'auto_approval']
CANDIDATE_FIELDS = ['model', 'model_version_or_revision', 'generated_translation', 'generation_status',
    'runtime_seconds', 'error_code', 'metadata_json']


def load_indexed(path, key='dataset_record_id'):
    return {r[key]: r for r in read_csv(path)} if Path(path).exists() else {}


def build():
    canonical = load_indexed(ROOT / 'results/canonical_parser_input.csv')
    queue = load_indexed(ROOT / 'results/translation_work_queue.csv')
    ballot = json.loads((ROOT / 'experiments/spatial_translation_bakeoff/reports/blind_ballot_results.json')
                        .read_text(encoding='utf-8'))
    ballot_by_id = {item['dataset_record_id']: item for item in ballot['items']}

    candidates = {arm: load_indexed(path) for arm, path in ARM_CANDIDATE_PATHS.items()}
    validations = {arm: load_indexed(path) for arm, path in ARM_VALIDATION_PATHS.items()}

    rows, fieldnames_seen = [], []
    for rid, queue_row in queue.items():
        canon = canonical.get(rid, {})
        row = dict(canon) if canon else dict(queue_row)
        row['dataset_record_id'] = rid

        for arm in ARM_CANDIDATE_PATHS:
            cand = candidates[arm].get(rid, {})
            for field in CANDIDATE_FIELDS:
                row[f'{arm}_{field}'] = cand.get(field, '')

        for arm in ARM_VALIDATION_PATHS:
            val = validations[arm].get(rid, {})
            for field in VALIDATION_FIELDS:
                row[f'{arm}_{field}'] = val.get(field, '')

        b = ballot_by_id.get(rid)
        row['human_ballot_sampled'] = bool(b)
        row['human_ballot_category'] = b['category'] if b else ''
        row['human_ballot_pick_letter'] = b['pick'] if b else ''
        row['human_ballot_picked_system'] = b['picked_system'] if b else ''
        row['human_ballot_generated_at'] = ballot['generated_at'] if b else ''

        rows.append(row)
        if not fieldnames_seen:
            fieldnames_seen = list(row.keys())

    for row in rows:
        for k in fieldnames_seen:
            row.setdefault(k, '')

    write_csv_once(OUT_CSV, rows, fields=fieldnames_seen)

    doc = ['# Final translation bake-off dataset: field reference\n',
           f'Generated from `results/canonical_parser_input.csv` (or `results/translation_work_queue.csv` '
           'where a canonical row is absent), joined by `dataset_record_id` with every translation arm\'s '
           'candidates.csv, validate.py screen output, and the 25-record human blind ballot. '
           f'{len(rows)} rows, one per Hindi-original record in the translation queue.\n',
           '## Provenance / source-field columns\n',
           'Every column present in `results/canonical_parser_input.csv` (or, for the two records only in '
           'the work queue, `results/translation_work_queue.csv`) is carried through unmodified — including '
           '`text_original`, `text_translated_legacy`, `existing_location_metadata`, `audit_class`, '
           '`discrepancy_tags`, `review_note`, and every other field documented in '
           '`experiments/00_parser_input_provenance.md`. None of these are touched or overwritten by this '
           'script.\n',
           '## Per-arm candidate columns (`<arm>_*`)\n',
           'One block per arm in `indictrans2`, `google`, `openai`, `chatgpt_manual`:\n',
           '- `<arm>_model`, `<arm>_model_version_or_revision` — exact model/revision string reported at '
           'generation time\n',
           '- `<arm>_generated_translation` — the candidate English translation; empty if not attempted or '
           'blocked\n',
           '- `<arm>_generation_status` — `SUCCESS`, `GENERATION_FAILED`, or `BLOCKED_NOT_ATTEMPTED` (Google/'
           'OpenAI are blocked in this run — no credentials configured)\n',
           '- `<arm>_runtime_seconds`, `<arm>_error_code` — empty for blocked/unattempted records\n',
           '- `<arm>_metadata_json` — full provider response metadata (model id, usage, timestamps, etc.) as '
           'a JSON string\n',
           '## Per-arm validation columns (`<arm>_*`, indictrans2 and chatgpt_manual only)\n',
           'Google/OpenAI have no validation columns since they produced no candidates to screen. Fields '
           'match `src/translation_bakeoff/validate.py`\'s `screen()` output exactly: `validation_state`, '
           '`flags`, `place_drop`, `place_addition`, `mention_order`, `direction_reversal`, '
           '`route_clause_count`, `relation_loss`, `feature_type`, `numeric_time`, `traffic_status`, '
           '`residual_devanagari`, `auto_approval`. These are conservative structural/cue screens, not gold '
           'semantic accuracy — see the module docstring.\n',
           '## Human ballot columns\n',
           '- `human_ballot_sampled` — true for the 25 records in the blind human preference ballot '
           '(2026-09-13), false otherwise\n',
           '- `human_ballot_category` — the audit category used to stratify the 25-record sample (5 per '
           'category)\n',
           '- `human_ballot_pick_letter` — which randomized position (A/B) the rater chose\n',
           '- `human_ballot_picked_system` — which system that resolves to (`indictrans2` or `chatgpt`), '
           'revealed only after the rater finished all 25\n',
           '- `human_ballot_generated_at` — ISO timestamp the ballot results were exported\n',
           '## What this dataset does not establish\n',
           'Automated screens and one blind human ballot on 25 records are evidence, not gold-standard '
           'bilingual adjudication. No translator is approved for production use by this dataset alone — '
           'see `experiments/spatial_translation_bakeoff/reports/indictrans2_vs_chatgpt_manual_comparison.md` '
           'for the full caveats.\n']
    write_text_once(OUT_DICT, '\n'.join(doc))
    print(f'{len(rows)} rows -> {OUT_CSV}')
    print(f'Field reference -> {OUT_DICT}')
    return rows


if __name__ == '__main__':
    build()
