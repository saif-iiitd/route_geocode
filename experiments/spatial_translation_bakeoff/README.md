# Blind Hindi → English spatial translation experiment

This isolated experiment compares IndicTrans2, Google Cloud Translation Advanced v3
and OpenAI GPT-5.6 Sol. It never writes production parser input. The requested
translation run is blocked until provider credentials/dependencies are available;
status artifacts are not substitute translations. See the generated report for the
actual outcome and per-provider blockers.

## Pipeline and reruns

Run from the repository root with Python 3:

```console
python -B -m src.translation_bakeoff.prepare
python -B -m unittest discover -s tests -p test_translation_bakeoff.py -v
python -B -m src.translation_bakeoff.generate --run-id 20260912_blind_v1
python -B -m src.translation_bakeoff.evaluate --run-id 20260912_blind_v1
```

Preparation is write-once: do not repeat it over the existing blind input. After
provider setup, run generation and evaluation with a **new run ID**. Never overwrite
a completed or blocked attempt. A crash also reserves its run ID; its partial request
logs remain evidence and a fresh ID is required. This harness performs no retries.

Use a separate environment for provider dependencies. The local bundled interpreter
used for offline implementation is
`C:/Users/hp/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.
No third-party packages are required for preparation, OpenAI REST requests, offline
tests or evaluation. The Google and IndicTrans2 adapters import their libraries lazily.

`blind_translation_input.csv` has exactly four columns and 815 unique records:
dataset_record_id, tweet_id, tweet_url, text_original. Preparation checks these
against canonical eligibility. Generation rejects additional columns and denies
reads under the repository's data/docs/results directories. Provider requests have
no retrieval/tools and never include audit hints, legacy translations or metadata.
This is pipeline/input blinding, not a claim the implementing assistant had no prior
audit context. The prompt has generic requirements without corrected corpus examples.

Every arm receives the same deterministic 20-record smoke sample: SHA-256 ranking of
the configured seed plus stable dataset ID. Smoke checks integration/schema/encoding
only. Failed or blocked smoke gates prevent full translation requests for that arm.
Full status ledgers still cover all 815 records without silently dropping any.

Generation freezes config, prompt, schema, source snapshots, environment and all
candidate/request/alignment files. Evaluation verifies these hashes before reading
the ledger. Candidate output_sha256 is the hash of the generated translation string;
the complete CSV hash is in freeze.json. Empty outputs carry failure/blocker statuses,
not fake text. External APIs do not guarantee deterministic translation outputs.
Re-serializing identical records is byte deterministic; genuine new requests have new
timestamps and may differ. `runs/<system>/<run-id>/` is authoritative. Root candidate
and report CSVs are write-once discovery copies for the first run.

## Enable IndicTrans2

Requested model: `ai4bharat/indictrans2-indic-en-1B`, pinned revision
`ac3daf0ecd37be3b6957764a9179ab2b07fa9d6a` (public model metadata checked during setup).
The repository is gated. The account owner must accept its access conditions on
[the model page](https://huggingface.co/ai4bharat/indictrans2-indic-en-1B), then configure
HF_TOKEN or authenticated Hugging Face token storage. This experiment does not accept
access terms on the user's behalf or replace this model with distilled/other weights.

Install PyTorch, a compatible Transformers 4.x release, sentencepiece, and
IndicTransToolkit according to the [AI4Bharat inference instructions](https://github.com/AI4Bharat/IndicTrans2/tree/main/huggingface_interface).
Use an isolated environment and record exact installed versions; no compatible stack
has yet been integration-validated here. The pinned model's custom code is loaded
with trust_remote_code. CPU float32/eager attention, seed 20260912, deterministic
PyTorch algorithms, no sampling, five beams and a 256-token source limit are frozen.
Over-limit sources fail explicitly rather than truncating. A device/dependency change
requires a new run and successful smoke test; hardware changes can change outputs.

## Enable Google Cloud Translation Advanced v3

Install the official client with `python -m pip install google-cloud-translate` in
the experiment environment. Configure GOOGLE_CLOUD_PROJECT and OAuth-based Application
Default Credentials with permission to translate in a billing-enabled project with
the Cloud Translation API enabled. For local user authentication, use:

```console
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

Alternatively set GOOGLE_APPLICATION_CREDENTIALS to an external service-account JSON
file, and set GOOGLE_CLOUD_PROJECT to its authorized translation project. Never paste
credential contents or commit them. The client uses v3, explicit hi→en, text/plain,
global/general/nmt and no glossary. Project/location/request metadata are recorded;
Google does not expose a pin-able backend revision for standard NMT.

The user supplied a file containing an ordinary Google API key during implementation.
Only its format was inspected; the key was not copied, logged or sent. **Advanced v3
does not support API-key authentication.** It cannot enable this specified arm.
Switching to Basic v2 would be a different experiment and requires explicit approval.
See [Google authentication](https://docs.cloud.google.com/translate/docs/authentication)
and [v3 text translation](https://docs.cloud.google.com/translate/docs/translate-text).

## Enable OpenAI

Set OPENAI_API_KEY securely in the execution environment with access/billing for
`gpt-5.6-sol`. The Codex session is not used as a replacement for the requested API
arm. The REST adapter sends a fresh Responses v1 request per record with strict JSON
schema, no tools, store=false, low reasoning effort and 8192 maximum output tokens.
Temperature/seed are omitted; deterministic service behavior is not claimed. Requested
and returned model identifiers and usage/request IDs are recorded. No alternate model
is selected if access fails. Verify availability with the actual account in the smoke
test. See [model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

Never put keys in config, CLI literals, markdown or CSVs. Provider exceptions are
logged by safe error code/type only, not raw body text. There are no hidden retries.

## Evaluation interpretation

The 77/104/57/548/29 legacy subsets are regression/review strata, not exhaustive gold
annotations. The 548 unresolved records are not labelled failures. Selection of at
least 20 illustrative cases happens only after the freeze and audit reveal.

Automatic screens flag possible numeric/time, relation, feature, negation/status
and residual-script discrepancies. Missing cue words are not proven semantic errors.
OpenAI self-alignment can reveal an internal mention-order/count inconsistency but
cannot independently establish correctness. Place identity, additions/drops, direction
and route-clause equivalence require bilingual adjudication. Quiet heuristics never
earn AUTO_VALIDATED. Severe regression classifications remain uncertain until evidence
supports fixed/persistent/different-error outcomes. NA metrics mean unmeasured, not 0%.

No default translator, hybrid superiority or automatic approvals can be justified
when all arms are blocked. Before production integration, complete real runs and an
independent adjudicated evaluation with precision estimates and held-out cases.
