# Canonical parser input and text provenance

Implemented 12 September 2026 from `docs/text_translation_provenance_audit.md`.
This is a standalone input layer. The notebook, manuscript, source corpus, existing
audit, translations and route outputs are unchanged. No models, translation services,
semantic parser or route geocoder are invoked.

## Reproduce

From the repository root, with Python 3 (standard library only):

```console
python -B -m src.parser_input
python -B -m unittest discover -s tests -v
```

The default output is `results/canonical_parser_input.csv`. For a clean build use
`--output <new-file.csv>`; an existing alternate destination is rejected. UTF-8 CSV,
fixed column order, LF record separators, sorted JSON keys/flags and cached evidence
timestamps make output independent of execution time. Read `tweet_id` as a string
when importing CSV into pandas or Excel; CSV itself cannot enforce spreadsheet types.

Input corpus SHA-256:
`156c71a3adf5603888c2d4db8ca218cf5da67d5c3811edc9ac79c9d4d5ac25d8`.

Canonical output SHA-256:
`8d897a0de3ddb9fada788b2dd4e9b1b1e269edbb05a6b98ee0e687c787f428d5`.

Each output record carries the source, screening-ledger and verification-CSV
fingerprints. A changed source snapshot fails closed and needs a new audit. Input
and evidence duplicates, missing coverage, and text/URL misalignment are rejected.
Evidence may be reordered without changing results. No external evidence is fetched.

## Identity and source hierarchy

`dataset_record_id` is SHA-256 of the relative source-file identity, complete source
snapshot hash and original `Unnamed: 0` key, separated by NUL characters. This key is
stable within the audited snapshot, including the URL-less record with original key
`10235`. A new snapshot intentionally has new dataset-record IDs. Cross-snapshot
tweet joins use the exact permalink ID, when available.

`tweet_id` is extracted as decimal characters from a validated Twitter/X status URL.
The old rounded `id` is retained only as `dataset_id_raw`. Audit records bind through
the original source key, checked against exact URL and both text fields. Public
verification binds through exact tweet ID; the one URL-less evidence record binds
through its complete original/legacy text pair, uniquely validated. Logical CSV
positions are never join keys.

Public evidence is preserved in `text_from_verified_source` with source URL,
retrieval date and comparison status. It checks the dataset original; it does not
automatically replace it. Material corruption is held for adjudication even if a
public text is available. Current eligible English records derive from dataset `text`.

## Text and translation contract

`text_original` is verbatim dataset `text`. `text_translated_legacy` is verbatim
dataset `translated_text`, with unknown production method/version. No legacy text
is copied to `text_translated` or used to construct `text_for_parser`.

Normalization version `original-whitespace-prefix-v1` collapses whitespace and
removes only an exact initial `Traffic Alert` token prefix. It preserves punctuation,
proper-name spelling, relations and location order. It does not correct aliases,
translate, extract entities or infer locations. Consequently the original spelling
`R.K Puram` remains unchanged; even an apparently harmless extra full stop from the
legacy translation is not imported.

`language_original` uses `detected_lang`, except two individually reviewed English
tweets mislabelled `id`: `852748238775922688` and `1032480895557660672`. Their recorded
labels remain in `language_recorded`; `language_origin=AUDIT_REVIEW` and a quality flag
document the correction. A non-English label or Devanagari script blocks English
readiness. This is an audited-corpus policy, not a general language detector.

Future translation infrastructure consists of reserved, separate fields:
`text_translated`, `translation_method`, `translation_version`,
`translation_review_status`, `protected_mentions_original`,
`protected_mentions_status`, and `translation_alignment`. No approved translations
exist here: text/method/version are empty, review status is `NOT_PRODUCED`, mention
status is `NOT_ANNOTATED`, and annotation/alignment arrays are empty. Empty annotations
mean **not annotated**, not that the tweet contains no place names. The complete
original string preserves all original-language surfaces and their sequence.

A future approved-translation implementation must bind to dataset-record ID and
original-text hash, record producer/version and reviewer/approval evidence, and store
ordered mention IDs with exact original surface strings and character spans. Repeated
mentions require separate IDs. Aligned target spans or protected placeholders must
retain that correspondence, with explicit review of spatial relations and direction.
Alias/transliteration suggestions belong in separate fields. The current builder
does not accept translations or infer that a populated legacy cell satisfies this
contract. Adding approved translation ingestion and validation is a later revision.

## Quality gates and counts

| Measure | Count |
| --- | ---: |
| Corpus/output records | 5,144 |
| English parser-ready (`READY`) | 4,327 |
| Translation-required, without corrupt source (`PARSER_TRANSLATION_REQUIRED`) | 815 |
| Corrupt source (`QUARANTINED`, blank parser input) | 2 |
| All non-English requiring translation, including one quarantined record | 816 |
| Legacy translations quarantined for audit review | 792 |
| Audit-screened possible legacy spatial changes across full corpus | 242 |
| Ready English originals with possible legacy spatial changes | 4 |
| Remaining possible-change cases awaiting translation | 238 |

Exclusive parser-status counts sum to 5,144. Translation-needed and quarantine flags
are orthogonal: the field-spill Hindi record counts in both. There are **817 records
excluded from READY**: 815 pending translation, one corrupt English original, and one
corrupt Hindi source requiring both adjudication and translation.

Quarantine has two explicit scopes. The **source record** is blocked when original
text is corrupt. The **legacy translation** is quarantined when the audit calls for
inspection (78 severe + 107 possible toponym + 57 possible relation + 548 unresolved
cross-language + 2 corrupt = 792). Safe English original text remains usable when
only its legacy derivative is defective. Other legacy translations remain `UNTRUSTED`
and are equally ineligible as parser input. No record is deleted.

The 242 is the prior audit's screening count, not a new semantic error measurement.
Only four of those records currently have canonical English parser text to compare;
the other 238 have blank parser input pending translation. The 548 unresolved cases
are not declared semantically equivalent or silently accepted. Flags and audit notes
preserve the uncertainty. No gold-route measurements inform these decisions.

## Representative records

| Record | Treatment |
| --- | --- |
| `549389894830030848`, Jail Road | READY original: `Traffic is now normal at Jail Road towards Hari Nagar.` Legacy Tilak Nagar substitution is explicitly flagged and its translation quarantined. |
| `548889847658975232`, AIIMS/R.K Puram | READY: `Now Traffic is normal at AIIMS , in the carriageway running from AIIMS towards R.K Puram .` The Keshav Puram address remains verbatim within `existing_location_metadata`; a metadata mismatch flag records it. |
| `659764100164136960`, `#NAME?` | Original and duplicated legacy translation retained; corrupt-cell and previous-row contamination flags; QUARANTINED with blank parser text. Retrieved ISBT/Shastri Park wording remains evidence only, pending explicit adjudication. |
| Original key `10235`, field spill | Stable dataset ID; blank tweet ID; original Hindi and geo/mentions spill preserved, explicit missing-URL/spill flags, QUARANTINED plus translation-required flag. No reconstruction. |

`existing_location_metadata` retains original string values and field names for
geo, mentions, OSM ID, address, locations, coordinates, bounding boxes, confidence,
accuracy and previous route coordinates. Producer provenance remains unknown; these
are exclusively source metadata, never new geocoder results. Other original columns
remain intact in the fingerprinted input CSV. A future geocoder must use a separate
output namespace/table keyed by `dataset_record_id` and exact `tweet_id`.

## Validation and integration boundary

Result: **11 tests passed** (`unittest`, 25.966 seconds). Both fresh-process outputs
were byte-identical; all source hashes checked before/after the test builds matched.

The test suite checks full coverage and unique keys, exact long IDs, preserved source
values and metadata, original-only English input, all named problem cases, non-English
gating, all severe/unresolved flags, normalization order/relations, evidence reordering
and misalignment rejection. It launches two clean Python processes and compares
output bytes, and hashes source Data files, notebook, Word documents and workbook
before and after builds. No third-party dependencies or network are needed.

The new canonical interface is `build_records(root)` or its generated CSV. Future
consumers must explicitly select `parser_status == 'READY'` and use `text_for_parser`;
all other statuses have empty parser input. The existing notebook still reads
`translated_text` because modifying the geocoder is outside this task. Connecting
that notebook to the new interface is a separate authorized revision; this experiment
does not claim its current execution path has changed.
