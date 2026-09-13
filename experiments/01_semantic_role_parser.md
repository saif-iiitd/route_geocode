# Experiment 01: Semantic-role parser (stabilization)

Date: 2026-09-13. Scope decision made with the user this session: set the new
Hindi translation candidates aside for now (see `results/writing/translation_layer_supplementary.md`
for that work); resume the revision order from the ChatGPT-session handoff
(`handoffs/chatgpt_handoff_2026-09-12.md`), which lists "semantic-role parser
stabilization" as the next step once the canonical parser-input layer was done. This
experiment works exclusively against the **4,325 `READY_ORIGINAL_EN` records** in
`results/canonical_parser_input.csv` (`text_for_parser`, safely-normalized original
English text — never the legacy `translated_text`, and none of this session's
IndicTrans2/ChatGPT Hindi work). No Hindi record is touched here.

## Reviewer motivation

| ID | Request | How this experiment addresses it |
| --- | --- | --- |
| R2.4 | Manually annotated gold routes and route precision/recall | Prerequisite: role/relation extraction must be stable and deterministic before route-level gold comparison means anything |
| R2.3 | Precedence-rule ablation / sensitivity analysis | This design has no precedence table to ablate — roles are derived per-mention from its own relation cue, not from a fixed global classification order, which is itself a response to the fragility R2.3 flags |
| R1.4 | Attribute the ontology; clarify which configurations are original | A role/relation set, not a pre-committed category label, is extracted; which of the manuscript's 12 configurations applies can be *derived* from the extracted roles later, rather than asserted by regex first |
| R1.3 | Clarify the Chirag Delhi point-vs-line example | Directly tested (see below) — a bare "at X" with no from/to/road cue resolves to one `POINT` mention, never a fabricated route |

## Hypothesis

The notebook's role-assignment failures (two incompatible definitions of
`extract_origin_destination`, behavior depending on execution order, `via`/`between`/
multi-clause text unrepresented, roles silently overwritten as a token loop
progresses) are not inherent to the problem — they come from not having one
canonical function with one execution path and an explicit per-mention role field.
A single deterministic pass over already-recognized mentions, keyed on the nearest
preceding relation cue within the same clause, should handle the corpus's actual
sentence patterns correctly and testably.

## What this experiment does *not* do

Entity recognition (which text spans are place mentions) is explicitly out of
scope — this is "semantic-role parser stabilization" (step 2 of the revision
order), not "candidate-based entity resolution" (step 3). `assign_roles()` takes
mention spans as input; a caller (spaCy + the existing gazetteer, or a test
fixture) is responsible for finding them. `feature_type` (road vs. junction vs.
unknown) is likewise supplied by the caller, not inferred here — that belongs to
the gazetteer/alias layer (step 4).

## Design

`src/semantic_roles.py`, one function (`assign_roles`) with one execution path:

1. Split text into clauses only on explicit numbered-list markers ("1.", "01)",
   ...) — never on bare periods, since abbreviations ("Rd.", "No.", "T-point.")
   are common in this corpus and a wrong split would silently sever an origin
   from its destination.
2. For each mention (processed in a caller-independent, position-sorted order),
   find the nearest relation cue word before it in the same clause: `from`,
   `to`/`towards`, `via`/`through`, `on`/`along`, `near`, `under`, `at`,
   `between`.
3. A bare separator since the previous mention (`,`, `&`, `and`) reuses the
   previous mention's cue, so a list ("via A, B and C") assigns every item the
   same role through one code path, not a second divergent one.
4. No cue at all: look ahead in the same clause for a directional cue ("to"/
   "towards", excluding "due to") before any competing "from" — this is an
   implicit origin (`"BRT towards Press Enclave Road"`), common in this corpus,
   marked `uncertain=True` because it is inferred rather than stated. Otherwise
   default by feature type (road-shaped → `NAMED_ROAD`, else `POINT`), also
   marked uncertain.
5. Output mirrors `src/translation_bakeoff/schema.py`'s structured-alignment
   shape (`mention_order`, `feature_type`, `uncertain`, relations by
   `mention_order`) deliberately — both describe the same underlying thing
   (mentions + relations extracted from one sentence).

## Tests

`tests/test_semantic_roles.py`, 9 tests, **all against real sentences copied
verbatim from the corpus** (not synthetic examples), covering:

- simple origin → destination (`from X to Y`)
- the Chirag Delhi point case (Reviewer 1's own example): must stay one `POINT`
  mention with zero relations
- a three-item `via` road list sharing one role across commas
- `X between A and B` (named road plus two segment boundaries)
- a three-clause numbered list, each clause with an implicit origin
- `near` attaching as a landmark to the correct (most recent) endpoint, not the
  origin by default
- a named-road closure with `&` (no fabricated route between the two roads)
- output-shape parity with the translation bake-off's schema
- mention numbering stays consecutive and position-ordered regardless of the
  order spans are supplied in

Result: **9/9 passing.** Full project suite (translation bake-off + parser-input
+ this): **37/37 passing.**

## Known limitations (explicit, not hidden)

- No entity recognition yet — every test supplies mention spans by hand. Real
  coverage against the 4,325-record corpus requires wiring in spaCy + the
  existing gazetteer/EntityRuler (step 3), which has not happened yet.
- `feature_type` is caller-supplied; without a real gazetteer behind it, `on X`/
  `at X` with an unknown feature type falls back to a marked-uncertain default
  rather than a confident classification.
- Clause-splitting only recognizes numbered-list markers, not general
  multi-sentence structure — deliberate (see Design §1), but means a truly
  independent second sentence with no numbered marker and no shared mentions is
  still treated as one clause. Not observed as a problem in the sampled
  sentences; worth revisiting once run against the full 4,325 records.
- Not yet wired into `The_Geocoder.ipynb` or any routing code. This is
  intentional per the user's decision to build new, testable code before
  touching the notebook.

## Decision: **KEEP**

Isolated, deterministic, fully tested against real corpus text, and does not
touch the notebook, manuscript, or any Hindi-translation work. Next steps this
unblocks: wire in real entity recognition (step 3, candidate-based entity
resolution) so `assign_roles` can run over the full 4,325-record English subset
and produce a coverage/error report, rather than nine hand-picked sentences.

## Manuscript impact

None yet — no manuscript text should change until this is validated at corpus
scale and reviewed, per this project's standing rule (nothing moves from code
into the manuscript without tests + validation + an experiment record, all
three of which this file is).

## Reviewer-response link

Directly informs the eventual response to R1.4, R2.3, R2.4; indirectly supports
R1.3 (Chirag Delhi) once integrated with real entity recognition and cited in
the manuscript text.
