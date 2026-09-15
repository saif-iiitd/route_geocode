# Claude Code handoff — 2026-09-12

> Naming note: prior handoffs in this folder used `codex_handoff_<date>.md` /
> `chatgpt_handoff_<date>.md`, one per implementing agent. This one follows the same
> pattern for the Claude Code session. `AGENTS.md`'s handoff convention (create/update
> `handoffs/codex_handoff_<date>.md` on request) was written by/for the Codex agent;
> this file keeps that spirit (Markdown, dated, in `handoffs/`) under an
> agent-distinguishing name instead of literally reusing "codex".

## Project and current state

Workspace: `C:\Users\hp\Dropbox\root\work\iiitd\Projects\route-geocode\code\submission_v1_july2026\route_geocode`.
Manuscript-revision project connecting the actual geocoder implementation, manuscript
claims, reviewer requests, and route validation (see `docs/code_manuscript_review_audit.md`
and `docs/text_translation_provenance_audit.md` for the two audits that precede this
session's work; `experiments/00_parser_input_provenance.md` for the canonical
parser-input layer that precedes the translation bake-off).

**Current objective**: run the blind spatial-translation bake-off
(`experiments/spatial_translation_bakeoff/`) for real, across as many arms as can be
made to work, then compare quality against the legacy machine-translation pipeline the
provenance audit flagged (77 known-severe cases, 815 total Hindi originals).

**As of this handoff**: a real IndicTrans2 run (`run-id 20260912_blind_v5`) is
**still in progress in the background** — smoke passed, full 815-record generation
started ~21:05 IST. A ChatGPT-manual arm (815/815) is complete and screened. Ollama is
paused pending a model decision. OpenAI/Google remain credential-blocked.

## Read first

- `experiments/spatial_translation_bakeoff/README.md` — updated this session with
  Ollama/IndicTrans2/manual-arm setup notes; read before touching any arm.
- `src/translation_bakeoff/adapters.py` — all four automated arms
  (openai, google, indictrans2, ollama).
- `src/translation_bakeoff/chatgpt_manual.py` — the manual (non-API) ChatGPT arm.
- `tests/test_translation_bakeoff.py` — 28 tests total (project), all passing as of
  this handoff.

## Completed this session

1. **Added a Hugging Face free-tier arm**, then **replaced it with a local Ollama arm**
   after the HF arm proved unreliable (see "Rejected/abandoned" below) — this is a real
   pivot, not additive. `SYSTEMS`/`STRUCTURED_SYSTEMS` in `common.py` now read
   `('indictrans2', 'google', 'openai', 'ollama')`.
2. **Fixed the IndicTrans2 environment end-to-end**:
   - Diagnosed that Visual Studio Installer's `modify --quiet` needs an interactive
     UAC click the automated tool session can't grant; the user re-ran it themselves
     and it registered as `isComplete: true` (verified via
     `vswhere.exe -all -products * -format json`, not just checking the MSVC folder
     exists on disk — file presence alone was misleading earlier in this session).
   - Installed `IndicTransToolkit` (needed the C++ compiler; required
     `DISTUTILS_USE_SDK=1`/`MSSdk=1` plus manually-constructed
     `PATH`/`INCLUDE`/`LIB` env vars pointing at
     `VC\Tools\MSVC\14.51.36231` and Windows SDK `10.0.26100.0`, because
     `vswhere`/distutils' own detection doesn't reliably see this VS "18" (2026)
     Build Tools instance).
   - Downgraded `transformers` in `.venv-indictrans` from 4.57.6 → **4.40.2** (with
     `tokenizers` auto-resolving to 0.19.1). The bleeding-edge version's `DynamicCache`
     refactor breaks IndicTrans2's pinned `trust_remote_code` modeling code
     (`past_key_values[0][0]` on what should be `None`/legacy-tuple on the first
     decode step). 4.28.1 (IndicTrans2's originally-documented pin) doesn't work here
     because its `tokenizers` dependency has no Python 3.12 wheel and needs Rust to
     build from source (not installed) — 4.40.2 is the practical compromise: new
     enough for cp312 wheels, old enough to predate the breaking Cache refactor.
   - Verified real translation output quality (place names preserved correctly, e.g.
     "Jail Road" stayed "Jail Road"; same literal-meaning quirk as other arms on
     "सांसद मार्ग" → "MP Marg" instead of "Sansad Marg").
3. **Built a manual ChatGPT-in-a-new-chat arm** (`src/translation_bakeoff/chatgpt_manual.py`)
   since the user wanted a ChatGPT comparison without an API key:
   - 14 batch files (~60 records each) under
     `experiments/spatial_translation_bakeoff/chatgpt_manual/batches/`, each
     self-contained (blind prompt + that batch's 4-field records), meant to be pasted
     into a **fresh** ChatGPT chat each time (this is what keeps it blind — no prior
     context, no corpus hints).
   - User pasted all 14 replies back; ingested into
     `experiments/spatial_translation_bakeoff/chatgpt_manual/candidates.csv` —
     **815/815 SUCCESS** after fixing a real ingestion bug (see below).
   - Ran the harness's `validate.py` screen over all 815:
     `validation_results.csv` / `subset_comparison.csv` in the same folder.
     759 `REVIEW_REQUIRED`, 56 `STRUCTURAL_MISMATCH` (self-alignment inconsistency,
     not proof of a wrong translation — see caveats below). All 77 known-severe
     legacy-failure cases got a successful candidate; spot checks show ChatGPT
     correctly fixing real legacy errors (e.g. "Baraf Khana Chowk" not "Ice Cliff
     Chowk", "Azad Market" not "free market", "Pusa Gol Chakkar" not
     "round-the-clock").
4. **Started a real 815-record IndicTrans2 run** through the harness
   (`run-id 20260912_blind_v5`) — smoke passed 20/20; full generation in progress as
   of this handoff. Ollama's config was deliberately set to `"host": ""` for this run
   (see below) so it wouldn't get pulled in before its model choice is finalized;
   Google/OpenAI remain genuinely credential-blocked.

## Rejected / abandoned this session (with reasons, so they aren't retried blindly)

- **Hugging Face free-tier arm** (`meta-llama/Llama-3.1-8B-Instruct` via
  `huggingface_hub` auto-routed Inference Providers): built, tested, then **replaced**
  after repeated real runs (`runs/huggingface/20260912_blind_v{1,2,3,4}`, now stale
  relative to the current `SYSTEMS` tuple) showed a persistent ~10-45% per-smoke
  failure rate (`HfHubHTTPError`, likely free-tier rate limiting, plus occasional
  `MALFORMED_STRUCTURED_OUTPUT`) even after adding request pacing and a one-shot
  worked example to the prompt. The harness's smoke gate demands 0/20 failures by
  default; a documented `smoke_failure_tolerance` mechanism was added to
  `generate.py` to accommodate a free/best-effort backend, but the user then decided
  to switch to local Ollama instead once they mentioned having it installed — the
  tolerance mechanism is still in the code (inert, defaults to 0/unused) in case a
  future arm needs it.
- **`gemma4:e4b` (8B) as the Ollama model**: accurate (correctly kept "Jail Road"),
  but this machine is CPU-only (Intel Iris Xe integrated GPU only — confirmed via
  `Get-CimInstance Win32_VideoController`; no NVIDIA hardware exists, so "can we use
  NVIDIA" is a dead end here) and took **~276s/record** → ~50-60 hours for 815.
- **`qwen2.5:3b-instruct` as the Ollama model**: ~5x faster (~57s/record → ~13 hours)
  but noticeably worse structurally — dropped "Sansad Marg" entirely from one
  translation and misclassified "12:30" and "बंद" (closed) as place mentions.
- User was asked to pick between keeping gemma4:e4b (slow, accurate), trying another
  small model (e.g. llama3.2:3b), or accepting qwen 3B's quality — **dismissed the
  question and has not yet decided**. Both models remain pulled locally
  (`ollama list`: `gemma4:e4b`, `qwen2.5:3b-instruct`). The Ollama arm's config
  (`experiments/spatial_translation_bakeoff/config/run_config.json`) currently has
  `"model": "qwen2.5:3b-instruct"` but `"host": ""` (deliberately blank, with a
  `"host_note"` explaining why) so it's excluded from the current run rather than
  silently running an undecided choice.

## Bugs found and fixed this session (in code written this session, not upstream)

- `chatgpt_manual.py`'s `ingest()` originally passed the raw ChatGPT reply item
  (which includes `dataset_record_id`) straight to `validate_alignment()`, which
  requires an object with *exactly* the 5 schema fields — every one of the first
  815 ingested records failed as `MALFORMED_STRUCTURED_OUTPUT` until this was fixed
  to strip `dataset_record_id` before validating. Already fixed and re-ingested
  (815/815 SUCCESS now).
- The 14 ChatGPT output files were initially saved by the user to
  `route_geocode/chatgpt_manual/outputs/` (repo root) instead of
  `experiments/spatial_translation_bakeoff/chatgpt_manual/outputs/`; moved into place.
  One file (`batch_003_output.json`) was a 0-byte duplicate next to a correctly-sized
  `batch_003_output(1).json` (browser download naming collision) — resolved by using
  the non-empty one.

## Validation

- Full test suite: **28/28 passing** (`python -B -m unittest discover -s tests`, run
  from `.venv-indictrans`).
- `chatgpt_manual` arm: 815/815 ingested, 815/815 screened, matches the harness's own
  `screen()` semantics exactly (imported, not reimplemented).
- IndicTrans2 real-run: smoke 20/20 PASS; full run outcome not yet known (see below).

## Update 2026-09-13: IndicTrans2 run finished

`run-id 20260912_blind_v5` completed overnight: **815/815 SUCCESS, 0 failures**,
avg 21.5s/record (~4.86h total — real corpus records took much longer than the
2-record sanity check suggested). `evaluate.py` was run against this frozen run
(`experiments/spatial_translation_bakeoff/reports/20260912_blind_v5/`).

A genuine new defect was found and quantified: IndicTrans2 has a **systematic
transliteration bug** — Devanagari nukta letters (ख़, ड़, ज़, फ़) leak into English
output as literal garbage (`Kh़`/`093C`) instead of being transliterated.
Confirmed in **40/815 (4.9%)** of candidates by direct string search. Not previously
documented anywhere in this project.

A side-by-side screen comparison against the ChatGPT-manual arm (both 815/815) is at
`experiments/spatial_translation_bakeoff/reports/indictrans2_vs_chatgpt_manual_comparison.md`.
Headline: IndicTrans2 has higher cue-discrepancy rates across the board (numeric/time
17.8% vs 4.8%, relation-loss 9.6% vs 1.0%, feature-type 9.7% vs 4.5%) and 27 records
with residual untranslated Devanagari (ChatGPT: 0). Both fix real legacy errors on
spot-checked severe cases and cover all 77 known-severe cases with a candidate. This
is still a conservative structural/cue screen, not gold semantic accuracy — no
translator has been approved for production use.

## Update 2026-09-13: human blind ballot + final joined dataset

**Human blind preference ballot.** Built an interactive Artifact
("Blind Translation Ballot", https://claude.ai/code/artifact/bc4d5eb4-4481-4bbc-9204-e94d183282ce)
showing the user 25 records (5 per audit category, deterministically sampled,
`seed=20260913`) with IndicTrans2 vs ChatGPT-manual translations in randomized
A/B order and no system label; source was revealed only after all 25 were rated.
**Result: ChatGPT preferred 21/25 (84%), IndicTrans2 4/25 (16%)** — ChatGPT won in
every one of the 5 categories, most decisively on "possible toponym change" (5/5).
This lines up with the automated screen's finding that IndicTrans2 has a higher
toponym/feature-type cue-discrepancy rate. One real hiccup: the user's first
completed ballot was lost (likely a republish or reload clobbered `localStorage`
before an export existed); an export button (copy-to-clipboard + visible textarea
fallback) was added to the artifact so results could be captured, and the user
redid the identical 25-item ballot and pasted the JSON back. Saved to
`experiments/spatial_translation_bakeoff/reports/blind_ballot_results.json` and
`..._per_tweet.csv`; comparison doc updated with a full breakdown table.

**Final joined dataset.** Built `src/translation_bakeoff/build_final_dataset.py`,
which joins (by `dataset_record_id`, never overwriting any source field) the
canonical provenance columns from `results/canonical_parser_input.csv` /
`results/translation_work_queue.csv` with every arm's candidate translation +
validate.py screen output (`<arm>_*` columns for `indictrans2`, `google`, `openai`,
`chatgpt_manual`) and the human ballot (`human_ballot_*` columns, populated only for
the 25 sampled records). Output: **815 rows × 123 columns** at
`results/translation_bakeoff_final_dataset.csv`, with a full field reference at
`results/translation_bakeoff_final_dataset_fields.md`. Verified: 815/815 SUCCESS for
indictrans2 and chatgpt_manual, 815/815 BLOCKED_NOT_ATTEMPTED for google/openai
(honest, not fabricated), 25 rows correctly flagged `human_ballot_sampled=True`.
Rerunnable: `python -B -m src.translation_bakeoff.build_final_dataset`.

## Update 2026-09-13 (continued): revision-order pivot + semantic-role parser

**Scope decision made with the user**: set the new translation candidates
(IndicTrans2/ChatGPT) aside for now. Resumed the revision order from
`handoffs/chatgpt_handoff_2026-09-12.md`, which lists "semantic-role parser
stabilization" as the step right after the canonical parser-input layer (done).
All work below touches only the 4,325 `READY_ORIGINAL_EN` records via
`text_for_parser` — no Hindi record, no `translated_text`, no this-session
translation-bakeoff artifact is touched.

**Two new writing artifacts** (unrelated to the code below, done earlier in the
day): `results/writing/translation_layer_supplementary.md` (manuscript-SI-ready
writeup of the whole translation bake-off: legacy-translation deficiencies, models
evaluated, the automated screen, the human ballot, and the ChatGPT-manual
selection recommendation with explicit non-approval caveats) and
`results/writing/chatgpt_translation_prompt.md` (the exact prompt used).

**Experiment 01 — semantic-role parser** (`experiments/01_semantic_role_parser.md`,
`src/semantic_roles.py`, `tests/test_semantic_roles.py`): one deterministic
function (`assign_roles`) replacing the notebook's two-conflicting-definitions-of-
`extract_origin_destination` bug. Takes a sentence plus caller-supplied mention
spans (does NOT do entity recognition itself) and assigns
ORIGIN/DESTINATION/NAMED_ROAD/VIA_ROAD/VIA_POINT/LANDMARK/SEGMENT_BOUND/POINT roles
plus the relations between them. Every test fixture is a real corpus sentence, not
synthetic, including Reviewer 1's own Chirag Delhi point-vs-line example (proven:
resolves to one `POINT`, zero fabricated relations).

**Experiment 02 — entity-recognition audit + dependency-based role assignment**
(`experiments/02_entity_dependency_audit.{md,py,json}`): user asked to audit and
improve steps 1 (entity recognition) and 2 (role assignment) rather than just
step 2 alone.
- **Step 1 audit**: reproduced the notebook's actual C10/C12 NER pipeline
  (spaCy `en_core_web_sm` + `EntityRuler` + `PhraseMatcher`, both built from
  `Data/tweet_location_terms.txt`) and ran it read-only against 150 sampled
  `READY_ORIGINAL_EN` records. 2.0% zero-entity rate, 2.71 mean entities/record —
  a starting baseline, not a corpus-wide certified rate.
- **Step 2 improvement**: the notebook already computes real dependency parses
  (`token.dep_`) in cell 42 but only prints them, never uses them. Empirically
  confirmed `dep_` cleanly distinguishes real spatial "to"/"towards" (`dep_=prep`)
  from "due to" (`dep_=pcomp`) and infinitival "to VERB" (`dep_=aux`) — no
  phrase-blacklist needed. Added `assign_roles(text, mentions, doc=None)`: an
  optional third argument that, when a spaCy `Doc` is supplied, tightens cue
  detection using this signal; omitting it preserves experiment 01's behavior
  exactly (backward compatible, not a rewrite).
- **A real parser-error was found and fixed, not hidden**: on this corpus's
  terse, proper-noun-heavy style, `en_core_web_sm` mistagged "Modi" (part of the
  real place "Modi Mill") as a verb, which would have made a real destination
  look like an infinitive phrase and gotten silently dropped. Fixed with a
  guard — an `aux` veto is only honored when the supposed "verb" token does
  *not* fall inside an already-recognized mention span — and verified against
  the full 150-record sample (not just the one hand-found case): 4 `aux`-tagged
  tokens total, 3 correctly excluded as real infinitives, 1 correctly caught by
  the guard.
- **Installed this session**: `spacy` 3.8.16 and `en_core_web_sm` 3.8.0 in
  `.venv-indictrans` (notebook was pinned to spaCy 3.7.2; close enough for this
  exploratory audit, not yet reconciled). Tests using spaCy are `unittest.skipIf`
  guarded, so the module has no hard runtime dependency on it.

Full suite: **40/40 passing** (was 37 before experiment 01, +9 there, +2 more in
experiment 02, minus one superseded/rewritten case — net effect documented in each
experiment's own file, not just this summary).

**Still open / explicitly not done**: "up to X" remains an unresolved ambiguity
(lexically identical to a real destination at the `dep_` level; would need a
`prt`-particle check not yet implemented). Real entity recognition has not been
wired into `assign_roles` end-to-end — experiment 02's audit script builds spans
directly from the notebook's pipeline for *auditing* purposes, but `assign_roles`
itself still takes mentions as a parameter in production usage, by design (role
assignment and entity-finding are being kept as separable, independently testable
concerns). Nothing has been changed in `The_Geocoder.ipynb` itself.

## Outstanding / next-step boundaries

1. ~~Check on `run-id 20260912_blind_v5`~~ — **done, see update above.**
2. **Ollama model decision still open** — user must pick between gemma4:e4b (slow,
   accurate), another small model to try, or accepting qwen 3B's quality tradeoff.
   Once decided, restore `"host": "http://localhost:11434"` in `run_config.json`.
3. ~~No cross-arm final report has been generated yet~~ — **done, see update above**;
   `evaluate.py` ran against `20260912_blind_v5` and a manual comparison report exists.
   Still outstanding: independent bilingual adjudication before any translator is
   approved for production use — no screen-based comparison substitutes for that.
4. Per the user's original manuscript-revision constraints (still in force, carried
   from earlier handoffs): do not implement semantic-role parsing, optimize against
   gold routes, or touch the geocoder/manuscript/route outputs. This session's work
   stayed entirely within the translation bake-off.

## Reproduce

```powershell
& '.\.venv-indictrans\Scripts\python.exe' -B -m unittest discover -s tests -v
& '.\.venv-indictrans\Scripts\python.exe' -B -m src.translation_bakeoff.chatgpt_manual validate
```

Git state at handoff time: `HEAD` at `c643506` ("translation with ChatGPT Done"),
working tree clean except for the in-progress run's artifacts under
`experiments/spatial_translation_bakeoff/runs/{20260912_blind_v5,indictrans2,google,openai,ollama}/`
(untracked, expected — the run hasn't finished/frozen yet).

## Update 2026-09-16: git push resolved, entity resolution built (step 3)

**Git.** The prior session's commit (`d487beb`, semantic-role parser +
entity-dependency audit + translation bake-off eval) failed to push at the time
(`403`, local user `safe-ali` lacked write access to
`saif-iiitd/route_geocode`). This has since resolved itself — `HEAD` is now
`d487beb` and `origin/main` reports up to date. **Nothing has been committed or
pushed this session yet** (see git state at the end of this section);
everything below is new, uncommitted work.

**Scope carried forward from the previous update**: still working the
`chatgpt_handoff_2026-09-12.md` "Correct revision order," resumed at step 3
(candidate-based entity resolution), 4,325 `READY_ORIGINAL_EN` records only.
Translation-bakeoff work remains set aside, untouched.

### Experiment 03 — candidate-based entity resolution (`src/entity_resolution.py`)

Classifies every recognized mention (from experiment 02's NER pipeline) by
local resolution evidence, with no geocoding and no invented disambiguation:
`GAZETTEER_RESOLVED` (exact gazetteer match), `GAZETTEER_GENERIC_AMBIGUOUS`
(matches a bare feature-type noun like "Flyover"/"Temple"/"Mandi" — many real
places share these; curated list of 6 found by manual review, not inferred),
or `OUT_OF_GAZETTEER_UNRESOLVED` (recognized only by base spaCy NER, no
gazetteer evidence). Audited on the same seeded 150-record sample as
experiment 02: 75.5% resolved, 4.2% generic-ambiguous, 20.3% unresolved. The
unresolved bucket was shown to mix two real, different causes — genuine
gazetteer gaps (e.g. "Andheria Mor", a real place missing from
`Data/tweet_location_terms.txt`) and NER noise (acronyms like "DC"/"DTC"
mistagged as locations) — both left unresolved rather than guessed apart.
Full write-up: `experiments/03_entity_resolution_audit.md`.

### Live geocoding turned on (OpenCage)

The user added `secrets/opencage_token.txt` (already gitignored via the
`secrets/` rule). **Two earlier drafts of this key were invalid**: the first
(`apl_mcp_live_...`) was checked and turned out to belong to a different
service entirely (not even a text geocoder), the second was actually an
**IPStack** key (IP-address geolocation, not place-name geocoding — wrong tool
class regardless of validity) — both confirmed by live 401s / by inspecting
the format, not assumed. The current key (32-char hex) was tested live and
works. **Budget note for whoever picks this up**: OpenCage's free tier is
2,500 requests/day; nothing in this session's experiments has needed more than
a few dozen cached calls, but a full-corpus pass would.

### Experiment 04 — generic-mention candidate resolution (`src/geocoding.py`)

User asked whether generic mentions ("flyover" etc.) could be disambiguated
using their co-mentioned origin/destination context. Before building anything,
two designs were tested live against OpenCage: **compound-query merging**
(`"Peeragarhi Flyover, Delhi"`) failed (fell back to a city-level match,
confidence 3); **bounding-box-restricted bare-term search** (`"flyover"`
restricted to a small box around the qualifier's own resolved location)
worked (returned real, correctly-named candidates). Built on the second
approach: for every `GAZETTEER_GENERIC_AMBIGUOUS` mention, find the nearest
preceding `GAZETTEER_RESOLVED` mention in the same tweet as a "qualifier",
geocode the qualifier for an anchor, then geocode the bare generic term
bounded to ~2.2 km around it. Candidates ranked by (a) whether the returned
name literally contains the generic term (12/12 hit rate in the sample) and
(b) a **free, local, zero-API cross-check** against `Data/network_nodes_data.csv`'s
real `bridge`/`tunnel` flags, reprojected from UTM zone 43N to WGS84
(`load_bridge_tunnel_nodes()`/`corroborate()` in `src/geocoding.py`) — found
zero hits in this small sample (only 12 distinct named bridge segments exist
locally), which is expected sparse coverage, not a failure. Two real gaps
surfaced: a spelling mismatch ("Kalka Ji" in tweet text vs. gazetteer's
"Kalkaji" — motivated experiment 05 below) and a too-tight bounding box for
sparser categories (all 3 "Temple" cases returned zero candidates). Every
OpenCage response is cached to disk and committed
(`experiments/04_opencage_cache.json`) — verified it contains no key material.
Full write-up: `experiments/04_generic_mention_candidate_resolution.md`.

### Experiment 05 — fuzzy/normalized alias matching

Explored whether fuzzy matching could recover the "Kalka Ji"/"Kalkaji"-style
gaps generally. Real findings, not assumptions: `token_sort_ratio`
(word-order-tolerant) was tested and **rejected** — it scored "Nagar Kirtan"
(a religious term, not a place) at 87 against "Kirti Nagar" (a real, different
place), a dangerous false positive. Plain `fuzz.ratio` on "Kalka Ji" vs.
"Kalkaji" alone only scored 80 (same band as a real wrong match) because
Levenshtein ratio over-penalizes a single space on short strings. Landed on a
**two-stage design**, now in `classify_mention`: (1) whitespace/punctuation-
normalized exact match — zero ambiguity risk, catches spacing/punctuation
variants like "Kalka Ji"/"Kalkaji", "Mangol Puri"/"Mangolpuri"; (2)
`fuzz.ratio >= 90` on the remainder, threshold set from a real 10-point cliff
found in this sample's data (94.1/93.3/90.9 correct vs. 80.0/80.0 wrong, no
threshold in between). Two new statuses: `GAZETTEER_NORMALIZED_MATCH`,
`GAZETTEER_FUZZY_MATCH`; every match records its method and (for fuzzy) exact
score. On the 150-record sample: `OUT_OF_GAZETTEER_UNRESOLVED` dropped from 83
to 74 (9 mentions recovered, 0 false positives). Full write-up:
`experiments/05_fuzzy_alias_matching.md`.

### New dependencies installed this session

`pyproj` (UTM↔WGS84 reprojection for the local network-node corroboration
check) and `rapidfuzz` (fuzzy string matching). No `requirements.txt` exists in
this repo to update.

### Validation

Full suite: **66/66 passing** (`python -B -m unittest discover -s tests -v`;
was 40 at the end of the previous handoff — 8 in `test_entity_resolution.py`
from experiment 03, +10 in `test_geocoding.py` from experiment 04, +8 more in
`test_entity_resolution.py` from experiment 05, +net 0 elsewhere).

### Outstanding / next-step boundaries

1. **Nothing from this session is committed yet** — git state below is the
   actual current state; the previous session's `d487beb` did make it to
   `origin/main` (confirmed this session via `git status`).
2. **Free-standing generic mentions** (no adjacent qualifier) are not handled
   by experiment 04's design — none occurred in the 150-record sample, so the
   user's original O/D-corridor-anchoring idea remains a documented but
   unimplemented fallback.
3. **Uniqueness is not guaranteed** in experiment 04's candidate ranking: two
   different qualifiers ("Manglapuri", "Palam") both returned "Dwarka Flyover"
   as their top candidate — plausible given real Delhi geography, but nothing
   currently flags this kind of collision.
4. **The 90 fuzzy threshold is evidenced on one 150-record sample**, not the
   full 4,325-record corpus — may need revisiting with more data.
5. **Kalkaji-style vs. Kalka-Ji-style is an alias/spelling gap; "Kalka Ji" as a
   recognized entity span at all is a separate, upstream NER-recognition gap**
   not touched by any of this session's work (it isn't tagged as an entity by
   the current pipeline in the first place).
6. Ollama model decision (translation bake-off, carried from the prior
   handoff) is still open and still out of scope for the current thread of
   work.
7. Next roadmap item per `chatgpt_handoff_2026-09-12.md`: step 4, the Delhi
   traffic gazetteer/alias layer proper — this session's experiments 03-05
   found several concrete candidates for it (missing entries like "Andheria
   Mor", spelling variants like "Kalka Ji") but did not build the layer
   itself, by design (kept as a separable, auditable next step).

### Reproduce

```powershell
python -B -m unittest discover -s tests -v
python -B experiments/03_entity_resolution_audit.py
python -B experiments/04_generic_mention_candidate_resolution.py   # uses cached OpenCage responses; needs secrets/opencage_token.txt only on a cache miss
python -B experiments/05_fuzzy_alias_matching.py
```

Git state at this handoff: `HEAD` at `d487beb`, up to date with `origin/main`.
Working tree has the following **new, uncommitted** files: `src/entity_resolution.py`,
`src/geocoding.py`, `tests/test_entity_resolution.py`, `tests/test_geocoding.py`,
`experiments/03_entity_resolution_audit.{py,md,json}`,
`experiments/04_generic_mention_candidate_resolution.{py,md,json}`,
`experiments/04_opencage_cache.json`, `experiments/05_fuzzy_alias_matching.{py,md,json}`.
No secrets among them (`secrets/opencage_token.txt` stays gitignored; the
committed cache file was checked for key leakage — none found).
