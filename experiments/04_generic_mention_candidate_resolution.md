# Experiment 04: Candidate resolution for generic landmark mentions

Date: 2026-09-16. Follows experiment 03. Scope unchanged: `READY_ORIGINAL_EN`
records only. First experiment in this project to make live external API calls
(OpenCage), every response cached to disk and committed.

## Motivation

Experiment 03 found that generic mentions ("flyover", "underpass", "temple",
"mandi"...) cannot be resolved from the gazetteer alone, and that in the audited
150-record sample every one of them (17/17) sits immediately next to an
already-resolved specific mention ("Peeragarhi flyover", "Azadpur Mandi"). The
user asked whether that adjacency could be used for disambiguation, and
specifically proposed ranking geocoder candidates for a generic mention by
whether they match a real structural feature (e.g., preferring a candidate that
is an actual flyover).

Two design candidates were discussed and tested live against OpenCage before
building anything:

1. **Compound-query merging** — send `"Peeragarhi Flyover, Delhi"` as one
   search string. Tested live: **failed**, fell back to a city-level match
   (confidence 3/10). OSM does not index this as one named entity.
2. **Bounded bare-term search** — send the bare generic word (`"flyover"`)
   restricted to a small bounding box around the qualifier's own resolved
   location. Tested live: **worked** — returned real, correctly-typed named
   candidates (`Mangolpuri Flyover`, `Shalimar Bagh Flyover`).

This experiment builds and audits approach 2, plus the user's proposed
structural cross-check using `Data/network_nodes_data.csv`'s local `bridge`/
`tunnel` flags (152/23 of 53,691 nodes respectively), which is free, has no API
cost, and is independent evidence from a different source than OpenCage.

## Method

`src/geocoding.py`:
- `GeocodeCache` — a flat JSON cache keyed by exact request parameters
  (`experiments/04_opencage_cache.json`, committed). A cache hit never makes a
  network call; every number reported below is reproducible from this file
  alone without an API key.
- `geocode(query, cache, proximity=None, bounds=None)` — cached OpenCage
  forward geocode.
- `make_bbox(lat, lon, half_width_deg=0.02)` — an ~2.2 km-wide box (urban
  corridor scale, not city-wide) centered on an anchor point.
- `load_bridge_tunnel_nodes()` — reprojects `Data/network_nodes_data.csv`
  geometry from its native UTM zone 43N (EPSG:32643, verified against known
  Delhi coordinates) to WGS84, keeping only nodes flagged `bridge=1` or
  `tunnel=1` with a non-empty name.
- `corroborate(lat, lon, feature, radius_m=150)` — nearest local node with a
  matching structural flag within `radius_m`, or `None`. `None` is explicitly
  documented as "no evidence either way," never "candidate rejected" — this
  local source only tags a small fraction of nodes.

`experiments/04_generic_mention_candidate_resolution.py`: reuses the exact same
150-record seeded sample and NER pipeline as experiments 02-03. For every
mention experiment 03 classified `GAZETTEER_GENERIC_AMBIGUOUS`, it finds the
nearest preceding `GAZETTEER_RESOLVED` mention in the same tweet (the
"qualifier") by character position, geocodes the qualifier to get an anchor,
geocodes the bare generic term bounded to a box around that anchor, and ranks
returned candidates by two signals:
- `name_match` — does the candidate's formatted name literally contain the
  generic term (e.g. "Mangolpuri **Flyover**")? This is the signal the live
  compound-vs-bounded test above showed actually works, not a guessed OSM
  category taxonomy.
- `corroborated` — a `corroborate()` hit against the local bridge/tunnel data,
  checked only for `flyover`→bridge and `underpass`→tunnel (no local source
  exists for temple/mandi/garden/boulevard).

Records with no preceding resolved qualifier are explicitly marked
`NO_LOCAL_QUALIFIER` and left unresolved rather than silently guessed — this is
the free-standing case the user's original O/D-corridor idea targets, not
implemented in this round (none occurred in this sample; see Findings).

## Findings

17 generic mentions in the sample; results, not assumptions:

| Stage | Count |
| --- | ---: |
| Generic mentions total | 17 |
| ...with a local qualifier found | 15/17 |
| ...qualifier geocoded and bare-term search returned candidates | 12/15 |
| ...top-ranked candidate's name contains the generic term | 12/12 |
| ...top-ranked candidate corroborated by local bridge/tunnel data | 0/12 |

**The bounded bare-term approach works well on name-match**: every case that
returned any candidate had its top-ranked result literally named after the
generic term (`Mangolpuri Flyover`, `Shri Hans Maharaj Flyover`, `Dwarka
Flyover`, `Outer Ring Road Underpass`, `Moolchand Flyover`, `Shalimar Bagh
Flyover`, `Shahdara Flyover`, `Yakshini Chowk Underpass`, `DGD, Gur Mandi`).

**Structural corroboration found zero hits**, as the sparse-coverage caveat in
the design discussion predicted: only 12 distinct named bridge segments exist
in the local network dataset, and none happened to fall within 150 m of these
12 candidates. This is not evidence the candidates are wrong — it confirms the
corroboration signal is real but rare, exactly as scoped going in.

### Two real gaps the audit surfaced

1. **2/17 mentions had no local qualifier**: both are the same tweet, *"Breakdown
   bus removed from Kalka Ji flyover flyover."* (a duplicated-word artifact in
   the source text). "Kalka Ji" (two words, as written in the tweet) does not
   match the gazetteer's `Kalkaji` (one word) — confirmed by grep: the
   gazetteer has `Kalkaji`, `Kalkaji Flyover`, `Kalkaji Mandir`, `Kalkaji
   Temple`, but not the two-word spelling. This is exactly the "weak alias
   handling" / "no systematic spelling normalization" gap the handoff names —
   real evidence for step 4, not fixed here.
2. **3/15 qualified mentions (all "Akshardham Temple") returned zero candidates**
   for the bare bounded `"temple"` query, even though the qualifier itself
   ("Akshardham") geocoded correctly at confidence 9. Checked directly: an
   *unbounded* `"temple"` query near the same anchor does return results
   (`Temple, Rohini`; `Temple, Alaknanda`; etc.), but none fall inside the tight
   ~2.2 km box — genuine data sparsity for this category in this micro-area, not
   a bug. Worth noting for step 4: the 2.2 km box size that worked well for
   flyovers may be too tight for sparser categories like temples.

## Tests

`tests/test_geocoding.py`, 10 tests, no live API calls: cache hit/miss/
collision behavior, `haversine_m` against a known Delhi distance (India Gate to
Connaught Place), `make_bbox` geometry, UTM reprojection sanity-checked against
Delhi's real coordinate range, `Dwarka Flyover` corroborating a point at its own
location, and explicit checks that "no corroboration" (far-away point, sparse
tunnel data) returns `None` rather than raising or fabricating a match.

Full suite: **58/58 passing** (10 new here, 48 unchanged).

## Design decision

Bounded bare-term search + name-match ranking is adopted as the working
mechanism for the adjacent-qualifier case (the dominant case in this corpus).
Structural corroboration is kept as an additive signal in the ranking (never a
gate — see `corroborate()`'s docstring), even though it produced zero hits
here; it is real, independently-sourced evidence when it does fire, and costs
nothing to check.

## Known limitations (still open, explicit)

- **Free-standing generic mentions** (no adjacent qualifier) are not handled —
  none occurred in this 150-record sample, so the O/D-corridor fallback the
  user originally proposed remains a documented but unimplemented design, not
  yet needed or tested.
- **Uniqueness is not guaranteed**: two different qualifiers ("Manglapuri" and
  "Palam") both returned `Dwarka Flyover` as their top candidate. This is
  plausible — both areas are in southwest Delhi, genuinely near Dwarka — but the
  method has no mechanism to detect or flag when two distinct real-world
  mentions resolve to the same place. Not fixed this round.
- **Box size (0.02°, ~2.2 km) is a single fixed choice**, not tuned per
  category. It worked for every flyover/underpass/mandi case tested but
  returned zero candidates for all three temple cases. A category- or
  density-aware box size is a candidate future refinement, not built here.
- **`name_match` is a literal substring check**, so it would miss a
  correctly-resolved candidate whose OSM name uses different wording (e.g. a
  translated or abbreviated form) — no such case was observed in this sample,
  but it is not proven absent from the full corpus.
- Audited on the same 150 of 4,325 `READY_ORIGINAL_EN` records as experiments 02
  and 03. A full-corpus pass, and the API budget it would require, has not been
  run.

## Decision: **KEEP**

Both candidate designs (compound-query vs. bounded bare-term) were tested live
before committing to one, the corroboration signal was scoped honestly (kept
even after producing zero hits, because the reasoning for why it would be rare
was stated in advance and held), and both real gaps found (the Kalkaji spelling
mismatch, the temple box-size miss) are documented as step-4-relevant findings
rather than silently patched.

## Reviewer-response link

Same as experiments 01-03 (R2.4, R2.3, R1.4) — first experiment to touch actual
geocoding, directly targeting the handoff's "no joint disambiguation across
co-mentioned places" and "alias handling is weak" findings.
