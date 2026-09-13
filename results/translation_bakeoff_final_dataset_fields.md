# Final translation bake-off dataset: field reference

Generated from `results/canonical_parser_input.csv` (or `results/translation_work_queue.csv` where a canonical row is absent), joined by `dataset_record_id` with every translation arm's candidates.csv, validate.py screen output, and the 25-record human blind ballot. 815 rows, one per Hindi-original record in the translation queue.

## Provenance / source-field columns

Every column present in `results/canonical_parser_input.csv` (or, for the two records only in the work queue, `results/translation_work_queue.csv`) is carried through unmodified — including `text_original`, `text_translated_legacy`, `existing_location_metadata`, `audit_class`, `discrepancy_tags`, `review_note`, and every other field documented in `experiments/00_parser_input_provenance.md`. None of these are touched or overwritten by this script.

## Per-arm candidate columns (`<arm>_*`)

One block per arm in `indictrans2`, `google`, `openai`, `chatgpt_manual`:

- `<arm>_model`, `<arm>_model_version_or_revision` — exact model/revision string reported at generation time

- `<arm>_generated_translation` — the candidate English translation; empty if not attempted or blocked

- `<arm>_generation_status` — `SUCCESS`, `GENERATION_FAILED`, or `BLOCKED_NOT_ATTEMPTED` (Google/OpenAI are blocked in this run — no credentials configured)

- `<arm>_runtime_seconds`, `<arm>_error_code` — empty for blocked/unattempted records

- `<arm>_metadata_json` — full provider response metadata (model id, usage, timestamps, etc.) as a JSON string

## Per-arm validation columns (`<arm>_*`, indictrans2 and chatgpt_manual only)

Google/OpenAI have no validation columns since they produced no candidates to screen. Fields match `src/translation_bakeoff/validate.py`'s `screen()` output exactly: `validation_state`, `flags`, `place_drop`, `place_addition`, `mention_order`, `direction_reversal`, `route_clause_count`, `relation_loss`, `feature_type`, `numeric_time`, `traffic_status`, `residual_devanagari`, `auto_approval`. These are conservative structural/cue screens, not gold semantic accuracy — see the module docstring.

## Human ballot columns

- `human_ballot_sampled` — true for the 25 records in the blind human preference ballot (2026-09-13), false otherwise

- `human_ballot_category` — the audit category used to stratify the 25-record sample (5 per category)

- `human_ballot_pick_letter` — which randomized position (A/B) the rater chose

- `human_ballot_picked_system` — which system that resolves to (`indictrans2` or `chatgpt`), revealed only after the rater finished all 25

- `human_ballot_generated_at` — ISO timestamp the ballot results were exported

## What this dataset does not establish

Automated screens and one blind human ballot on 25 records are evidence, not gold-standard bilingual adjudication. No translator is approved for production use by this dataset alone — see `experiments/spatial_translation_bakeoff/reports/indictrans2_vs_chatgpt_manual_comparison.md` for the full caveats.
