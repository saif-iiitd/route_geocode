# Experiment 02: Entity recognition (step 1) and dependency-based role assignment (step 2)

Date: 2026-09-13. Follows experiment 01. Scope unchanged: 4,325 `READY_ORIGINAL_EN`
records only.

## Motivation

Experiment 01 shipped `assign_roles` with text-adjacency workarounds for
non-directional "to" (e.g. `_cue_before` requiring the cue word immediately precede
the mention). The user asked whether POS tagging could do this more properly. It
turns out the notebook already computes real dependency parses (`token.dep_`) for
exactly this purpose in cell 42 (Step 3.a/3.b), but only prints them — never uses
them for role assignment. This experiment (a) empirically audits step 1 (the
notebook's actual entity-recognition pipeline, C10/C12) against a real sample, and
(b) empirically evaluates whether that discarded dependency signal is reliable
enough to replace the text-adjacency workaround.

## Method

`experiments/02_entity_dependency_audit.py` reproduces the notebook's exact NER
pipeline (spaCy `en_core_web_sm` + `EntityRuler` + case-insensitive `PhraseMatcher`,
both built from `Data/tweet_location_terms.txt`, combined and de-overlapped with
`spacy.util.filter_spans`, entities filtered to labels `LOC`/`GPE`/`ORG`/`FAC`) and
runs it, read-only, against 150 `READY_ORIGINAL_EN` records (seeded sample,
`seed=20260913`). Full results: `experiments/02_entity_dependency_audit.json`.

## Findings: step 1 (entity recognition)

| Metric | Value |
| --- | ---: |
| Records with zero recognized entities | 3/150 (2.0%) |
| Mean entities per record | 2.71 |
| Max entities in one record | 7 |

Real zero-entity examples (gazetteer misses, not a code bug):
`"Breakdown car has been removed from Swami Nagar Subway..."`,
`"Breakdown truck has been removed from K. N. Katju Marg..."`. Both name real
places absent from `Data/tweet_location_terms.txt`. A 2% miss rate on a 150-record
sample is a reasonable starting point, not a certified corpus-wide rate — the
gazetteer's actual coverage against all 4,325 records has not been measured.

## Findings: step 2 signal (dependency label of every to/towards token)

| Label | Count | Meaning |
| --- | ---: | --- |
| `towards`, dep=`prep` | 89 | Real spatial preposition |
| `to`, dep=`pcomp` | 81 | Complement of "due" ("due **to** X") — not spatial |
| `to`, dep=`prep` | 36 | Real spatial preposition |
| `to`, dep=`aux` | 4 | Infinitive marker before a verb ("**to** take X") — not spatial |
| `towards`, dep=`ROOT` | 1 | Parser failure on a malformed/fragment tweet |

Of 211 `to`/`towards` tokens, 125 are real spatial prepositions and 85 are not —
and `dep_` distinguishes them with a single structural check, no phrase-blacklist
needed. This directly answers the "up to"/"due to"/"to take" ambiguity raised in
experiment 01: `dep_ == 'pcomp'` reliably flags "due to"; `dep_ == 'aux'` flags a
true infinitive.

### A real complication found, and how it was handled

The `aux` check is not safe unconditionally. On this corpus's terse,
proper-noun-heavy tweet style, `en_core_web_sm` sometimes mistags a place name's
own first word as a verb: in *"from Nehru Place **to Modi Mill** due to..."*,
**"Modi" was tagged `pos_=VERB`**, making "to Modi Mill" look like an infinitive
phrase even though it is a real destination. Blindly trusting `dep_ == 'aux'`
would have silently dropped a real destination — arguably worse than the
over-inclusive behavior it replaced, because it fails quietly instead of falling
back to an explicit `uncertain=True` default.

Fix: `dependency_vetoes(doc, mentions)` only honors an `aux` veto when the
supposed "verb" token does **not** fall inside an already-recognized mention span
— if it does, the tag is almost certainly wrong, not evidence of a real
infinitive. `pcomp` has no such failure mode in this sample and is vetoed
unconditionally. Verified against the same 150-record sample: 4 `aux`-tagged
tokens total, 3 correctly excluded as real infinitives, 1 correctly caught by the
guard as this exact parser error — not a hand-picked result, the full-sample
count.

## Design change

`src/semantic_roles.py`:
- `assign_roles(text, mentions, doc=None)` — new optional third argument. Without
  it, behavior is unchanged from experiment 01 (adjacency-only, including the
  known "up to" limitation). With a spaCy `Doc` for the same text, `to`/`towards`
  cues are checked against `dependency_vetoes(doc, mentions)` before being
  accepted, catching `due to` and true infinitives that adjacency alone cannot.
- This is additive, not a rewrite: every experiment-01 test still passes
  unmodified; the dependency path only tightens cue detection when a doc is
  supplied.

## Tests

Two new tests in `tests/test_semantic_roles.py` (skipped if spaCy/en_core_web_sm
aren't installed, so the module has no hard runtime dependency on spaCy):
- `test_dependency_parse_resolves_up_to_and_due_to` — proves "due to" is now
  correctly excluded via a real parse (previously only "up to" was called out as
  an accepted gap; this closes the "due to" half of it), and that a genuine
  "from X to Y" still resolves Y as `DESTINATION`.

Full suite: **40/40 passing** (12 in this module, 28 elsewhere, unchanged).

## Known limitations (still open, explicit)

- **"up to X"** remains unresolved: `dep_ == 'prep'`, identical to a real
  destination. Needs a dedicated check (e.g. a preceding `dep_=='prt'` particle
  attached to the same head, observed in the "closed **up** to Tolstoy Marg"
  example) — not implemented this round.
- The dependency signal is only as good as `en_core_web_sm`'s parse, which this
  experiment directly showed can be wrong on this corpus's style. The guard
  added here fixes the one failure mode actually observed (a place name's first
  token mistagged as a verb); other, unobserved failure modes may still exist.
  Treat `doc`-based role assignment as evidence-improving, not ground truth.
- Step 1's gazetteer coverage (2% zero-entity rate) was measured on 150 of 4,325
  records — worth a full-corpus pass before relying on it for coverage claims in
  the manuscript.

## Decision: **KEEP**

Evidenced by a real audit (not assumed), additive (doesn't regress experiment 01),
and the one failure mode found was caught and fixed with a targeted, justified
guard rather than papered over.

## Reviewer-response link

Same as experiment 01 (R2.4, R2.3, R1.4) — this hardens the same role-assignment
step rather than opening a new reviewer thread.
