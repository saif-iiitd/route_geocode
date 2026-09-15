# Supplementary Information: Semantic-Role Parsing for Route-Relevant Mentions

Prepared 2026-09-16. Scope: `src/semantic_roles.py`, which assigns a semantic
role (origin, destination, named road, via-point, landmark, segment boundary,
or standalone point) to each place mention already found in a tweet, and
builds the directional/topological relations between them. It does **not**
perform entity recognition (see the companion document, *Entity Recognition
and Resolution*, for that separate step) and does not touch the geocoder,
routing, or any manuscript claim beyond this one parsing stage.

## S1. Background and problem in the existing notebook

`The_Geocoder.ipynb` contains a function, `extract_origin_destination`,
responsible for turning a list of recognized place mentions into an
origin/destination pair (and, in later cells, a landmark). A code-fidelity
audit found this function **defined twice, with incompatible contracts**
(cells 29 and 31), so the notebook's behavior depended on which definition
happened to run last in a given session — a form of nondeterminism invisible
to a reader of either definition alone. Both versions built the role
assignment with ad hoc, order-dependent logic: iterating over recognized
mentions and mutating shared `origin`/`destination` variables based on
counters and text-position checks, so a role could be silently overwritten or
left unset depending on iteration order. Neither definition represented `via`,
`between`, or a tweet containing more than one route clause (e.g. a numbered
list of unrelated closures) as anything other than an accidental side effect
of however the mention list happened to be ordered.

The manuscript's own methodology implies a richer role vocabulary than the
notebook actually computes (origin, destination, named road, via-road,
via-point, landmark, at minimum), and Reviewer 1's Table 1 specifically
raises the case of a tweet naming only one point (no route at all), which the
notebook's pattern of always producing an origin/destination pair risks
fabricating into a route that was never stated.

## S2. Design overview

`assign_roles(text, mentions, doc=None)` is the single entry point,
replacing both prior definitions. It performs **no entity recognition** —
callers (currently, test fixtures reproducing the notebook's own recognized
spans; in production, the entity-resolution layer described in the companion
document) supply a list of mention spans (`start`, `end`, `text`, and an
optional `feature_type` hint such as `'road'`). The function returns three
values:

- `mentions` — the same mentions, sorted by position in `text`, numbered
  `mention_order = 1..N` (consecutive, no gaps or reuse), each now carrying a
  `role` and an `uncertain` flag.
- `relations` — a list of `Relation(relation, source_mention_order,
  target_mention_order, uncertain)` objects referencing that numbering, never
  raw text spans.
- `route_clause_count` — how many distinct route clauses the tweet contains
  (see clause-splitting, S3).

**Role vocabulary** (`ORIGIN`, `DESTINATION`, `NAMED_ROAD`, `VIA_ROAD`,
`VIA_POINT`, `LANDMARK`, `SEGMENT_BOUND`, `POINT`, `UNCLEAR`) and **relation
vocabulary** (`from`, `to`, `towards`, `via`, `through`, `between`, `on`,
`near`, `under`, `at`) are both fixed, closed sets, chosen to match every
distinct spatial construction observed in the corpus's traffic-alert
phrasing, not a general-purpose parse of arbitrary English.

`to_dict(mentions, relations, route_clause_count)` projects the result into
the same field shape (`place_mentions`, `spatial_relations`,
`mention_order`, `feature_type`, `uncertain`) used by the translation
bake-off's structured-alignment schema, so both processes can share
downstream tooling and QA code rather than each inventing their own.

## S3. How it works, precisely

### S3.1 Clause splitting

`_clause_spans(text)` splits a tweet into route clauses **only** on explicit
numbered-list markers (`"1."`, `"01)"`, etc.). Splitting on bare sentence
periods was deliberately not attempted: abbreviations are extremely common in
this corpus ("Rd.", "No.", "T-point."), and a wrong sentence split would
silently sever an origin from its destination. A tweet with no numbered list
is therefore always treated as exactly one clause, even if it reads as
several English sentences. Every mention and every relation is scoped to the
clause it falls in — a `from`/`to` pair in clause 2 can never attach to a
mention in clause 1.

### S3.2 Cue detection: adjacency, not nearest-match

For each mention, `_cue_before(text, mention_start, clause_start, prev_end,
vetoes)` looks for a relation cue word (`from`, `to`, `towards`, `via`,
`through`, `between`, `on`/`along`, `near`, `under`, `at`) **immediately**
before it — meaning only whitespace may separate the cue word from the
mention, not "the closest cue occurring anywhere earlier in the clause."

This distinction is load-bearing. In *"kindly avoid this route to take Ring
Road"*, the word `"to"` appears in the text before `"Ring Road,"` but the verb
`"take"` sits between them. A naive nearest-cue scan over the whole clause
would incorrectly read this as `"to Ring Road"` and mark Ring Road a
destination; requiring strict adjacency prevents this without needing a
hand-written blacklist of phrases.

If the gap since the previous mention in the same clause is only a bare
separator (`,`, `&`, or `and` — a list continuation, as in `"via A, B and
C"`), the cue is not re-searched: the previous mention's cue carries forward,
so a list of via-roads shares one role instead of each subsequent item
silently losing its relation.

### S3.3 The dependency-parse veto (optional, additive)

Adjacency alone cannot distinguish a genuine directional `"to"` from `"due
to"` or an infinitival `"to VERB"` (`"a route **to take** Ring Road"`) when
the intervening word is itself absent or very short. `dependency_vetoes(doc,
mentions)` closes this gap **when a spaCy `Doc` with a dependency parse is
supplied**: `dep_ == 'pcomp'` reliably marks the complement of "due"
(`"due **to** the demonstration"`), and `dep_ == 'aux'` marks a true
infinitive marker before a verb. This signal is empirically grounded, not
assumed — see the companion entity-recognition document (S3) for the audit
that measured it directly against 150 real corpus tweets: of every `to`/
`towards` token sampled, 81 were `due to` (`pcomp`), 4 were infinitival
(`aux`), and the remaining 125 were real spatial prepositions (`prep`).

**A real complication was found and fixed, not hidden.** On this corpus's
terse, proper-noun-heavy tweet style, the small spaCy model sometimes mistags
the first word of a place name as a verb. In *"from Nehru Place **to Modi
Mill** due to ongoing Delhi Jal Board work,"* the word "Modi" (part of the
real place "Modi Mill") was tagged `pos_ = VERB`, which would make a genuine
destination look infinitival and get silently vetoed. The fix: an `aux` veto
is only honored when the supposed "verb" token does **not** fall inside an
already-recognized mention span — because a "verb" inside a known mention is
almost certainly a mistagging, not evidence of a real infinitive. `pcomp` has
no such failure mode observed in this corpus and is vetoed unconditionally.
Verified against a full 150-record sample, not just this one hand-found case:
4 `aux`-tagged tokens total, 3 correctly excluded as real infinitives, 1
correctly caught by the guard as this exact mistagging pattern.

When no `Doc` is supplied, `assign_roles` falls back to adjacency alone —
this is a documented, accepted degradation (see S7), not a silent one.

### S3.4 Per-cue role assignment

Each detected cue routes to exactly one code path in `apply_cue`, shared
between a direct cue match and a `CONTINUE` list-continuation, so a
comma-separated list is never handled by a second, divergently-maintained
implementation:

| Cue | Assigned role | Notes |
| --- | --- | --- |
| `from` | `ORIGIN` | Becomes the clause's "last endpoint" for the next relation. |
| `to` / `towards` | `DESTINATION` | Emits a `to`/`towards` relation from the last endpoint, if any. |
| `via` / `through` | `VIA_ROAD` or `VIA_POINT` | Chosen by the mention's `feature_type` hint (road-type features vs. point-type features). Becomes the new "last endpoint," so a destination stated after a via-mention links to the via-mention, not the original origin. |
| `between` | `SEGMENT_BOUND` | The first `between`-cued mention in a clause is held pending; the second closes a `between` relation between them. |
| `on` / `along` | `NAMED_ROAD` or `POINT` | Chosen by `feature_type`; with no feature-type evidence either way, defaults to `NAMED_ROAD` but is marked `uncertain`. |
| `near` | `LANDMARK` | Attaches to whichever endpoint (or, failing that, named road) was most recently seen in the clause — never silently picks an arbitrary one. |
| `under` | `LANDMARK` | Attaches to the last endpoint, if any. |
| `at` | `POINT` or `LANDMARK` | A bare `"at X"` with no prior endpoint or road in the clause names a single point location, not a route — see S4's Chirag Delhi example. |

### S3.5 No-cue fallback: implicit origins

Two real corpus patterns produce a mention with no cue word directly before
it: a bare named road stated with nothing preceding it (`"X is closed due
to..."`), and — very common in this corpus — an **implicit origin** with no
stated `"from"` (`"BRT towards Press Enclave Road"`). These are distinguished
by re-using `_cue_before` on the *next* mention in the same clause, rather
than a second, separately-implemented adjacency scan: if that next mention's
own cue resolves to `to`/`towards`, the current (cue-less) mention is treated
as its implicit origin and marked `uncertain = True`. Otherwise, the mention
defaults to `NAMED_ROAD` (if its `feature_type` says so) or `POINT`, also
marked `uncertain`. No cue-less mention is ever assigned a role without this
flag — the parser never claims false certainty about an inferred role.

## S4. Worked examples

All examples below are real corpus tweets (`results/canonical_parser_input.csv`,
`parser_status == READY_ORIGINAL_EN`), used directly as test fixtures in
`tests/test_semantic_roles.py` — not invented for illustration.

**Simple origin/destination.**
> *"Obstruction in traffic from Kali Bari Marg to Gol Market(both carriageways)
> due to procession. Kindly avoid the stretch."*

`Kali Bari Marg` → `ORIGIN`, `Gol Market` → `DESTINATION`, one `to` relation
between them, one route clause.

**A single point, not a fabricated route** (Reviewer 1's Table 1
point-vs-line example).
> *"Traffic is now normal at Chirag Delhi."*

`Chirag Delhi` → `POINT`, `uncertain = False`, **zero relations**. No
origin/destination pair is invented for a tweet that never named a route.

**Via-list sharing one role across commas.**
> *"Now traffic is normal from Balmiki Mandir to Patel Chowk via Mandir Marg,
> Peshwa Road, Bhai Veer Singh Marg."*

`Balmiki Mandir` → `ORIGIN`, `Patel Chowk` → `DESTINATION`; `Mandir Marg`,
`Peshwa Road`, and `Bhai Veer Singh Marg` all → `VIA_ROAD`, with three
separate `via` relations (one per road), not one relation covering an
unstructured list.

**A named-road segment bounded `between` two points.**
> *"Traffic is moving slow on Yamuna Bridge between ISBT Kashmere Gate and
> Shastri Park."*

`Yamuna Bridge` → `NAMED_ROAD`; `ISBT Kashmere Gate` and `Shastri Park` →
`SEGMENT_BOUND`, with one `between` relation connecting them.

**Multiple route clauses in one tweet (numbered list), with implicit
origins.**
> *"Traffic will remain heavy on following roads due to Christmas
> Celebration. 01. BRT towards Press Enclave Road. 02. Malviya Nagar towards
> Saket court Road. 03. M.B. Road towards Mandir Marg."*

Three route clauses recognized. `BRT`, `Malviya Nagar`, and `M.B. Road` are
each assigned `ORIGIN` with `uncertain = True` (no explicit `"from"`, inferred
only because a `towards` cue follows in the same clause); `Press Enclave
Road`, `Saket court Road`, and `Mandir Marg` → `DESTINATION`. Three relations,
one per clause — clauses never leak into each other.

**A landmark attaching to the correct endpoint.**
> *"Traffic is heavy in the carriageway from Patel Nagar towards Moti Nagar
> due to breakdown of a bus near Shadipur metro station."*

`Patel Nagar` → `ORIGIN`, `Moti Nagar` → `DESTINATION`, `Shadipur metro
station` → `LANDMARK`, attaching to `Moti Nagar` (the most recently seen
endpoint) — not silently attached to whichever endpoint happened to be first.

**A closure with no route (list continuation via `&`, not a relation).**
> *"Tolstoy Marg & Parliament Street is closed due to demonstration. Kindly
> avoid the stretch."*

Both roads → `NAMED_ROAD`, **zero relations** — `"&"` here lists two roads
under the same closure, it does not describe a route between them.

**Non-directional "to" is not fabricated into a route** (three real
constructions in one corpus, none of them a destination):
- *"...closed due to demonstration"* — `"due to"` never produces a
  `DESTINATION`; `Tolstoy Marg` / `Parliament Street` stay `NAMED_ROAD` with
  zero relations.
- *"Sansad Marg is closed up to Tolstoy Marg crossing due to demonstration"*
  — `"up to"` is a **documented, open limitation** (S7): adjacency alone
  reads it the same as a real destination, so `Sansad Marg` is marked
  `ORIGIN` with `uncertain = True` rather than silently treated as certain.
- *"...kindly avoid this route to take Ring Road"* — `"to take"` (an
  infinitive) does not produce a destination; `Ring Road` is not marked
  `DESTINATION`.

**Dependency-parse veto in action** (requires a spaCy `Doc`):
> *"Obstruction in traffic from Nehru Place to Modi Mill due to ongoing Delhi
> Jal Board work."*

With the dependency parse supplied, `Modi Mill` correctly resolves to
`DESTINATION` despite the "Modi" mistagging risk described in S3.3 — the
mention-span guard prevents the false veto.

## S5. Improvements over the notebook baseline

| Notebook baseline | This module |
| --- | --- |
| `extract_origin_destination` defined twice, incompatible, behavior depends on execution order | One function, one execution path |
| Roles inferred by ad hoc, order-dependent counters mutating shared variables | Explicit, closed role vocabulary assigned per mention from its own cue |
| `via`, `between`, and multi-clause tweets have no systematic representation | Explicit `VIA_ROAD`/`VIA_POINT`/`SEGMENT_BOUND` roles and `route_clause_count`; each clause independently scoped |
| A tweet naming only one point risks being fabricated into an origin/destination pair | A bare point with no cues produces one `POINT` mention and zero relations (S4, Reviewer 1's example) |
| Naive text scanning for `"to"` would treat `"due to"`/`"to take"` as destinations | Adjacency-based cue matching plus an optional, empirically-grounded dependency-parse veto |
| No `uncertain`/confidence signal on inferred roles | Every inferred (non-explicit-cue) role is explicitly marked `uncertain = True` |

## S6. Validation

`tests/test_semantic_roles.py`: **12 tests**, every fixture a real corpus
sentence (not synthetic), including Reviewer 1's own point-vs-line example.
Tests cover: simple origin/destination, the bare-point non-fabrication case,
via-road lists sharing role across commas, `between` boundaries, multi-clause
numbered lists with implicit origins, landmark attachment to the correct
endpoint, named-road closures producing no route, the `to_dict` schema shape,
all three non-directional "to" constructions above, the dependency-parse veto
(both the "due to" case and the "Modi Mill" guard), and mention-order
stability regardless of input order. Two of the twelve are `skipIf`-guarded
on spaCy/`en_core_web_sm` being installed, so the module carries no hard
runtime dependency on spaCy for its core (adjacency-only) behavior.

Full project test suite (this module plus all others): **66/66 passing** as
of 2026-09-16.

## S7. Known limitations (explicit, not fixed this round)

- **"up to X" is a genuine, unresolved ambiguity.** At the dependency-parse
  level, `"up to X"` is structurally identical to a real destination
  (`dep_ == 'prep'`), so it is currently read the same way (marked
  `uncertain = True`, but not distinguished). A dedicated check — a preceding
  `dep_ == 'prt'` particle attached to the same head — was identified as the
  likely fix but has not been implemented.
- **This module performs no entity recognition.** Every example above uses
  manually-specified mention spans (test fixtures) or, in the audits referenced
  above, spans produced by the existing notebook pipeline. Wiring real,
  production entity recognition into `assign_roles` end-to-end is a separate,
  later integration step (see the companion Entity Recognition and Resolution
  document).
- **Dependency-parse reliability is bounded by the underlying spaCy model.**
  The "Modi Mill" mistagging (S3.3) is the one failure mode found and fixed;
  other, unobserved failure modes in `en_core_web_sm`'s parse may still exist
  on this corpus's terse, proper-noun-heavy style.
- **spaCy version note:** `spacy` 3.8.16 / `en_core_web_sm` 3.8.0 were
  installed for this work; the notebook itself is pinned to spaCy 3.7.2. This
  version difference has not been reconciled and is not expected to change
  the dependency labels relied on here, but has not been independently
  verified against the older pin.
- Audited and tested against a seeded 150-record sample and hand-picked
  fixtures, not the full 4,325-record `READY_ORIGINAL_EN` corpus.

## S8. Reviewer-response link

Addresses R1.4 (route representation fidelity), R2.3 (parser instability —
the double-defined-function bug), and R2.4 (semantic-role ambiguity handling)
from the reviewer priorities list. Directly resolves Reviewer 1's Table 1
point-vs-line concern (S4).

## S9. Reproducibility

```powershell
python -B -m unittest tests.test_semantic_roles -v
```

Source: `src/semantic_roles.py`. Tests: `tests/test_semantic_roles.py`.
Experiment notes with full audit detail: `experiments/01_semantic_role_parser.md`,
`experiments/02_entity_dependency_audit.md`.
