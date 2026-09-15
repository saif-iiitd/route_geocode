# Experiment 06: Unified candidate confidence scoring + joint disambiguation

Date: 2026-09-16. Follows experiments 03-05. Scope: entity/candidate-level
confidence only (see "Relationship to route-level confidence" below for what
this is *not*).

## Motivation

The code-fidelity audit (`docs/code_manuscript_review_audit.md`) names this
gap directly, and distinguishes it from a separate, larger gap:

> "There is no local confidence/context ranking, no joint entity resolution,
> no low-confidence trigger, and no saved candidate list. The code relies on
> whatever order OpenCage returns, then uses the first coordinate passing the
> local region test." (line 120)

> Row 5 (CRITICAL): "No code reads confidence, compares candidate context,
> jointly resolves mentions, checks candidate route consistency, or records
> alternatives... Retain alternatives and candidate metadata; evaluate
> context/feature-type/role compatibility and deterministic selection against
> annotated identities."

This experiment builds the candidate/entity half of that requirement:
deterministic, evidenced confidence scoring for a single resolved mention,
retaining every real candidate rather than silently keeping only the first.

## Exploration (before building anything)

Two live OpenCage queries, tested directly, motivated the whole design:

- `"Madhuban Chowk, Delhi"` → 3 candidates, all within **348 m** of each
  other. Different nearby-road addressings of the *same* real intersection —
  not genuine ambiguity about which place is meant.
- `"Krishna Nagar, Delhi"` → 2 candidates **14,094 m** apart, both at OpenCage
  confidence 8-9. Two real, different Delhi locations sharing a name — no way
  to tell which from the mention text alone.

A single scalar confidence cannot honestly represent both situations, so the
design measures **candidate spread** (max pairwise distance among a mention's
real candidates, after dropping OpenCage's generic city-level fallback,
consistently observed at confidence <= 3-4 across every query run in this
project) and uses that to decide between two different resolutions.

## Design

`src/confidence.rank_candidates(gazetteer_term, match_method, cache,
anchors=())`:

1. Geocode the term (cached), drop fallback-confidence candidates
   (`opencage_confidence <= 4`, a margin above the observed fallback value of
   3).
2. No real candidates left → `UNRESOLVED_NO_GEOCODE`.
3. Spread `<= 500 m` (`CLUSTER_RADIUS_M`, set from the 348 m real safe case)
   → `CONFIDENCE_HIGH`, pick the candidate with the highest OpenCage
   confidence — treated as one real place.
4. Spread `> 500 m` (genuine ambiguity) and an `anchors` coordinate is
   supplied (another mention in the same tweet already resolved at
   `CONFIDENCE_HIGH`) → pick whichever candidate is closest to an anchor,
   `CONFIDENCE_MEDIUM`, method `JOINT_DISAMBIGUATION`.
5. Same wide spread, no anchor available → `CONFIDENCE_LOW`, method
   `BEST_GUESS_AMBIGUOUS`: the highest-confidence candidate is kept as a
   best guess, but **every candidate is retained** in the result, not
   discarded.
6. A `FUZZY`-tier gazetteer match (the mention *text* itself was inferred,
   not exact) is capped at `CONFIDENCE_MEDIUM` even when its geocoded
   candidates cluster tightly — the result must never look more certain than
   the weakest link that produced it.

## Findings: four real cases, all cached and reproducible

**Case 1 (control, clustered).** `"Madhuban Chowk"` → `CONFIDENCE_HIGH`,
spread 348 m, as expected from the exploration above.

**Case 2a (an anchor candidate that correctly failed the bar).** Tested
`"Shahdara"` (from the real tweet *"Traffic is normal at Road no. 57 from
Krishna Nagar towards Shahdra."*) as a candidate anchor. Its own 4 candidates
span **888 m** — just over the 500 m threshold, mostly the same East Delhi
locality with one outlier pair pulling the max-pairwise spread over the line.
Per the design's own contract (an anchor must itself be `CONFIDENCE_HIGH`),
this was correctly refused as an anchor rather than used anyway — the
experiment script enforces this itself rather than silently loosening the
rule to make a convenient test pass.

**Case 2b (joint disambiguation, with a genuinely valid anchor).** From the
real tweet *"Traffic is heavy in the carriageway from Krishna Nagar towards
Jagatpuri due to ongoing PWD work."* `"Jagatpuri"` geocodes to a single
candidate (spread 0 m, `CONFIDENCE_HIGH`), whose own formatted address
independently names `"Preet Vihar"`. Using it as an anchor, `"Krishna
Nagar"` correctly resolves to the East Delhi candidate
(`"Krishna Nagar, Road Number 57, Preet Vihar..."`, `CONFIDENCE_MEDIUM`) over
the unrelated South Delhi candidate 14 km away — **independently verifiable**:
both the chosen candidate and the anchor candidate name the same real
neighborhood, confirmed by string match, not by construction.

**Case 3 (ambiguous, no anchor).** `"Krishna Nagar"` alone (no other mention
to disambiguate against) → `CONFIDENCE_LOW`, both real candidates kept and
reported, neither silently discarded.

**Case 4 (fuzzy cap).** `"Mehrauli"` supplied with `match_method='FUZZY'`
clusters tightly but is capped to `CONFIDENCE_MEDIUM`, not `CONFIDENCE_HIGH`.

## Tests

`tests/test_confidence.py`, 9 tests, no live API calls (a `FakeCache`
pre-populated with real recorded OpenCage responses makes every test
deterministic and offline): tight-cluster high confidence, fallback-candidate
exclusion, wide-spread-no-anchor stays low confidence with all candidates
kept, wide-spread-with-valid-anchor resolves to medium confidence and picks
the geographically correct candidate, no-real-candidates is unresolved (not
an error), empty results is unresolved, the fuzzy-match cap, confirmation
that a normalized match is *not* capped, and a check that every result
carries a `reason`.

Full project test suite: **75/75 passing** as of 2026-09-16 (9 new here).

## Relationship to route-level confidence (explicitly out of scope here)

The same audit distinguishes this candidate-level work from a separate,
larger, **not-yet-buildable** requirement:

> "M P144 correctly says per-route confidence is absent, contradicting
> Appendix output claims... Appendix A nevertheless promises stored
> confidence and a `compute_confidence` function that does not exist."

Per-route confidence — one score summarizing a whole constructed route,
across all of its resolved mentions plus road resolution and route
construction, with an explicit "no feasible route" state when a required
mention or road segment cannot be resolved — is a manuscript-promised output
that genuinely depends on pipeline stages that do not exist yet in this
revision (road resolver, step 5; constraint-preserving route construction,
step 6; explicit unresolved-route states, step 7). Building it now would mean
stubbing those stages, which risks exactly the kind of "claims behavior the
frozen code does not implement" problem this whole revision effort exists to
fix.

What this experiment does provide toward that future requirement: every
mention's confidence result already carries an explicit, closed-vocabulary
tier (`CONFIDENCE_HIGH` / `CONFIDENCE_MEDIUM` / `CONFIDENCE_LOW` /
`UNRESOLVED_NO_GEOCODE`) rather than a bare accept/reject or a silently-picked
first result — the natural input a future route-level rollup (e.g., a route's
confidence bounded by its weakest-resolved constituent mention, and an
explicit no-route state triggered by any `UNRESOLVED_NO_GEOCODE` mention)
would need, without requiring rework of this layer when that stage is built.

## Known limitations (explicit, not fixed this round)

- **Max-pairwise spread is sensitive to a single outlier candidate.** Case 2a
  (Shahdara, 888 m) shows most candidate pairs well under 500 m, with one
  outlier pair pulling the whole set's spread over the cluster threshold. A
  more robust metric (e.g., distance-to-centroid, or a real clustering
  algorithm) might handle this better, but only two clean real data points
  (348 m safe, 14,094 m clearly ambiguous) support the current threshold —
  888 m sits in a genuinely untested boundary zone, and the threshold was not
  retuned to force this specific case through.
- **`CLUSTER_RADIUS_M` (500 m) and `FALLBACK_CONFIDENCE_MAX` (4) are both
  evidenced on a small number of live queries** run across experiments 04-06,
  not a systematic calibration study.
- **Joint disambiguation only tries geographic proximity to another anchor.**
  It does not yet use feature-type/road-name compatibility between mentions
  (a possible refinement named in the review audit's row 5 recommendation),
  and only supports one candidate anchor list, not a weighted combination of
  several.
- **Not run at corpus scale.** Every case here is a hand-selected real
  example, chosen because it demonstrates a specific mechanism cleanly, not a
  seeded random sample — unlike experiments 02-05, this one intentionally
  traded sample breadth for depth on the specific mechanism (joint
  disambiguation) the review audit calls out.

## Decision: **KEEP**

Both threshold constants are evidenced from real, live-tested cases named
explicitly, and the one case that didn't cleanly fit the model (Shahdara,
888 m) was surfaced and handled by the design's own contract (refusing to use
a non-`CONFIDENCE_HIGH` anchor) rather than adjusted away.

## Reviewer-response link

Directly addresses R2.4/R1.1/R2.1 (row 5, CRITICAL, in the code-fidelity
audit): candidate confidence, joint entity resolution, and a saved candidate
list (alternatives retained, never discarded). Route-level confidence (row
24) remains open, tracked as a dependency on steps 5-7 of the revision order.

## Reproducibility

```powershell
python -B -m unittest tests.test_confidence -v
python -B experiments/06_candidate_confidence_ranking.py   # uses the committed OpenCage cache; a live key is needed only on a cache miss
```

Source: `src/confidence.py`. Tests: `tests/test_confidence.py`. Cache:
`experiments/06_opencage_cache.json` (checked for and confirmed free of key
material).
