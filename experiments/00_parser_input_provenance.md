# Canonical parser input and translation work queue

Updated 12 September 2026. This revision supersedes the earlier production language corrections and status names. Source corpus and the audit ledger are immutable. No translation, semantic-role extraction, geocoding, routing or manuscript editing was performed.

## Counts and exceptions

| Parser status | Records |
| --- | ---: |
| READY_ORIGINAL_EN | 4,325 |
| NEEDS_APPROVED_TRANSLATION | 815 |
| LANGUAGE_REVIEW | 2 |
| SOURCE_REPAIR_REQUIRED | 1 |
| QUARANTINE_SOURCE_CORRUPTION | 1 |
| Total | 5,144 |

The builder raises ValueError before writing outputs if exact status counts, total or unique record coverage fail reconciliation. The queue contains all and only the 815 intact Hindi originals, including benign-audit legacy translations. There are 819 records without parser-ready text. The two recorded `id` labels are unchanged, pending language review. Hindi field-spill corruption is excluded from the translation queue: source repair/adjudication comes first.

Row 2 (tweet 549389894830030848) uses `Traffic is now normal at Jail Road towards Hari Nagar.` Its legacy Tilak Nagar substitution remains QA evidence. Row 3 (tweet 548889847658975232) uses `Now Traffic is normal at AIIMS , in the carriageway running from AIIMS towards R.K Puram .` Keshav Puram is retained only in legacy metadata and cannot affect input.

Row 136 (tweet 659764100164136960) retains `#NAME?`, copied legacy translation and verified public wording separately; SOURCE_REPAIR_REQUIRED prevents automatic replacement. Row 2635 (original source key 10235, no valid permalink) is QUARANTINE_SOURCE_CORRUPTION with original field-spill evidence intact. Row numbers here are audit locators, never join keys.

## Provenance and normalization

Exact original and translated strings are preserved. `text_translated` retains the ledger-supplied legacy string and `text_translated_legacy` explicitly exposes its legacy status. Neither is approved input. `text_translated_approved` is empty; no translation method/version or approval is invented. All audit columns are retained verbatim, including `text_for_current_parser` (historical evidence only), relation flags, tags, review notes and toponym hints. `audit_evidence` also stores the complete original ledger record as JSON. Future consumers must use only `text_for_parser` on READY_ORIGINAL_EN rows.

Normalization version `original-whitespace-prefix-v1` collapses whitespace and removes only the exact leading `Traffic Alert` token prefix. It preserves internal punctuation, place/road names, numbers, relations, directionality, repetition, order and route status. Alias correction is not performed. Blocked input is Python None, serialized as an empty CSV cell; status distinguishes a blocked input from a usable string.

Dataset IDs hash the relative source-file identity, audited source snapshot hash and original `Unnamed: 0` key. Exact tweet IDs come from permalinks as strings; rounded numeric `id` is evidence only. The URL-less record also has a stable dataset ID. Joins bind original source keys and exact tweet IDs, validate both texts, URL and recorded language, and reject duplicates or mismatches. CSV imports must explicitly preserve ID string types.

Existing address, locations, coordinates, bounding boxes, confidence, accuracy and other location fields are retained as strings in `existing_location_metadata`. They cannot construct parser text. Verified public-source text, source URL, timestamp and comparison status remain separate evidence; no new retrieval was necessary.

## Translation queue and outstanding work

`results/translation_work_queue.csv` includes stable identity, exact Hindi original, legacy comparison text, audit class/tags/relations, known original-toponym hints, unmatched-toponym evidence, audit review indicators/notes, fingerprints and explicit pending translation/review status. `known_original_toponyms` is incomplete QA evidence, explicitly labelled INCOMPLETE_AUDIT_HINTS_NOT_ANNOTATIONS. Pending translation review is distinct from prior audit inspection.

No new translations or exhaustive mention annotations exist. The next separately authorized translation revision should protect original toponym surfaces, align Hindi spans with the parsing representation, and preserve mention order/repetition, numbers, status and from/to/towards/via/near/between/under relations. Proper names such as Raja Garden must not be literally translated. Only after approved input exists should semantic-role extraction resume.

## Reproduce and validate

From the repository root, using Python 3 standard library only:

```console
python -B -m src.parser_input
python -B -m unittest discover -s tests -v
```

Optional `--output <new-canonical.csv> --queue-output <new-queue.csv>` supports clean builds. Alternate existing files and identical output paths are rejected. Input fingerprint and count validation precede writes. Deterministic field ordering, sorted JSON and cached timestamps produce byte-equivalent canonical and queue outputs.

Tests cover source/metadata immutability, exact IDs, all requested examples, Hindi blocking, unchanged id language labels, full audit retention, exact queue membership, reconciliation failure, shuffled evidence, alignment rejection and two clean-process output comparisons. Protected source and previous audit hashes are checked before/after builds. The notebook still consumes legacy translated_text: its migration is outside this task. No changes are made to that execution path.

## SHA-256 fingerprints

- `Data/tweets_data.csv`: `156c71a3adf5603888c2d4db8ca218cf5da67d5c3811edc9ac79c9d4d5ac25d8`
- `results/translation_discrepancies.csv`: `a0c954837406177c676c3bff7a3df92567955ab8be509299bac4c2bd73f542a6`
- `results/provenance_audit/original_tweet_verification.csv`: `fcb65561dc59ea4b2af2d86f45c6f6bc5722ec867ae5359b58992cd6da8d6638`
- `results/canonical_parser_input.csv`: `08853defee20577aba8be637e2ca1a773d7744a489594a98f12519f6d91a8811`
- `results/translation_work_queue.csv`: `c47bf98fb36fdf5416b1b4d0903d5d9faee8849f7b5c6283444b976d1c71f919`

Validation result: all 12 tests passed (27.419 seconds). Canonical and queue outputs were byte-equivalent across clean runs; protected source and audit hashes were unchanged.
