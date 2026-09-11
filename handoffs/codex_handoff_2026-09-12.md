# Codex handoff — 2026-09-12

## Project and current state

Workspace: `C:\Users\hp\Dropbox\root\work\iiitd\Projects\route-geocode\code\submission_v1_july2026`.

This is a manuscript-revision project connecting the actual geocoder implementation,
manuscript claims, reviewer requests and route validation. The latest completed
implementation is the **canonical parser input and text-provenance layer**. No
semantic-role parser has been implemented. The current user request is only to
prepare this handoff; no further implementation is authorized by that request.

## Read first

- `docs/code_manuscript_review_audit.md`: implementation/manuscript/review fidelity audit.
- `docs/text_translation_provenance_audit.md`: full corpus provenance audit and specification.
- `experiments/00_parser_input_provenance.md`: implemented policy, counts, reproducibility and limitations.
- `src/text_provenance.py` and `src/parser_input.py`: actual new implementation.
- `tests/test_parser_input.py`: corpus-backed tests.

Original project inputs are `The_Geocoder.ipynb`,
`routes_batch1_highlighted.xlsx`, `Revised Identifiable Manuscript July 2026.docx`,
`Reviews_March2026.docx`, and the `data` folder. The full corpus is
`data/tweets_data.csv` (code refers to `Data`, equivalent on this Windows filesystem).

## Completed work

1. Audited code/manuscript/review fidelity without modifying the inputs.
2. Audited text and metadata provenance across all 5,144 corpus records. Supporting
   screening and public-source evidence are retained in
   `results/translation_discrepancies.csv` and `results/provenance_audit/`.
3. Built the standalone canonical input layer and generated
   `results/canonical_parser_input.csv`, one row per corpus record.

The new layer uses original English wording, with whitespace normalization and
removal of an exact initial `Traffic Alert` prefix. It performs no alias correction,
translation, location reordering, spatial inference or entity extraction.

Exact tweet IDs are extracted as strings from valid status permalinks. The original
numeric/scientific-notation `id` is lossy and must never be used as a join key.
Dataset-record IDs hash relative source identity, source snapshot SHA-256 and the
original `Unnamed: 0` row key. Audit/evidence joins validate source text and URL;
they do not rely on positional row numbers. The URL-less record uses original key
`10235` and has a stable dataset-record ID, without an invented tweet ID.

Public evidence is retained separately and checks dataset originals. It does not
automatically replace a corrupt dataset cell. Legacy translations are preserved as
`text_translated_legacy`; existing location/address/coordinate/bounding-box/confidence
metadata is isolated in `existing_location_metadata` and cannot influence parser text.

No new translations exist. Approved-translation fields and mention-alignment slots
are reserved, with explicit `NOT_PRODUCED` / `NOT_ANNOTATED` statuses. Empty mention
arrays mean unannotated, not absence of place names. Future approved translation
ingestion and validation still need implementation under a separate request.

## Counts and scope of quarantine

| Measure | Count |
| --- | ---: |
| All corpus/output records | 5,144 |
| English `READY` records | 4,327 |
| Exclusive `PARSER_TRANSLATION_REQUIRED` status | 815 |
| Exclusive `QUARANTINED` source status | 2 |
| All non-English requiring translation, including one quarantined source | 816 |
| All records excluded from READY | 817 |
| Quarantined legacy translations | 792 |
| Audit-screened possible legacy spatial changes | 242 |
| Ready originals with possible legacy spatial changes | 4 |

Source quarantine blocks parser input. Legacy-translation quarantine does not block
a verified, usable English original. All legacy translations remain ineligible for
canonical input, even those not flagged. The 242 count is a screening result, not a
new measured translation-error rate. Another 548 cross-language cases are unresolved.

Two individually audited English tweets were incorrectly labelled Indonesian (`id`):
`852748238775922688` and `1032480895557660672`. Their canonical language is English,
with explicit audit correction flags and their recorded labels retained. This is a
fixed audited-corpus policy, not a general language detector.

## Important examples

- **Jail Road**, tweet `549389894830030848`: parser text is
  `Traffic is now normal at Jail Road towards Hari Nagar.` The legacy Tilak Nagar
  substitution is flagged and its translation quarantined; original is READY.
- **R.K Puram**, tweet `548889847658975232`: parser text is
  `Now Traffic is normal at AIIMS , in the carriageway running from AIIMS towards R.K Puram .`
  Original punctuation is preserved. Keshav Puram remains only in legacy address
  metadata, with a mismatch flag. It does not replace the original mention.
- **#NAME?**, tweet `659764100164136960`: corrupt original and previous-row copied
  legacy translation are retained and explicitly flagged. Parser input is blank and
  record quarantined. Retrieved public text mentioning ISBT/Shastri Park remains
  separate evidence, pending source adjudication.
- **Field spill**, original key `10235`: missing URL/ID; Hindi original and apparent
  spill into `geo`/`mentions` retained. Quarantined, translation-required, no reconstruction.

## Public verification already completed

The prior audit verified all 5,143 available public status URLs. One corpus record
has no usable URL. One retrieved source differs materially from the dataset original:
the `#NAME?` record. Formatting and link-rendering differences are separately recorded.
Do not repeat retrieval unless a later task requires it. Evidence and retrieval dates
are cached; inability to retrieve any future source is not proof its dataset text is wrong.

## Validation and reproduction

The completed implementation passed **11 unittest tests** in 25.966 seconds. Two
fresh-process builds produced byte-identical output. Tests cover immutable fields,
long exact IDs, known cases, non-English gating, safe normalization, shuffled evidence,
misalignment rejection and source hashes. All **33 original source hashes** also
matched the prior audit after implementation. No geocoding or route execution occurred.

From the workspace root:

```powershell
& 'C:/Users/hp/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -B -m src.parser_input
& 'C:/Users/hp/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -B -m unittest discover -s tests -v
```

Standard library only. `--output <new-file.csv>` permits a separate clean build.
Load CSV tweet IDs explicitly as strings in downstream tools. The builder rejects
corpus changes against its pinned fingerprint; a different snapshot requires an audit.

Corpus SHA-256:
`156c71a3adf5603888c2d4db8ca218cf5da67d5c3811edc9ac79c9d4d5ac25d8`.

Canonical output SHA-256:
`8d897a0de3ddb9fada788b2dd4e9b1b1e269edbb05a6b98ee0e687c787f428d5`.

## Constraints and next-step boundary

The user prohibited changes to the geocoder, routing, candidate selection, manuscript,
source fields and translations during the completed step. Those files remain unchanged.
Do not implement semantic roles, regenerate translations, optimize against gold routes,
or execute route geocoding without a new request authorizing that work.

**The existing notebook still reads `translated_text`.** Only the new standalone
layer establishes the canonical input policy. Do not claim the notebook execution
path has been migrated. Future integration must explicitly select `parser_status ==
'READY'` and consume `text_for_parser`; all other records have empty parser input.

Potential subsequent work, subject to the next user instruction: integrate the input
interface, adjudicate corrupt source records, implement protected/aligned approved
translation support, or implement semantic-role parsing. These are not completed.
Future generated geocoder results must have a separate namespace keyed by stable
record identity and must not overwrite legacy location metadata.

## Standing handoff preference

Whenever the user asks for a handoff, create or update
`handoffs/codex_handoff_<date>.md`, using today's local date in `YYYY-MM-DD` format
(Asia/Calcutta). Preserve useful prior context in same-day updates. This convention is
also recorded in the workspace `AGENTS.md` so later sessions can follow it.
