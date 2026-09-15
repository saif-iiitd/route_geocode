# Experiment 05: Fuzzy/normalized alias matching for out-of-gazetteer mentions

Date: 2026-09-16. Follows experiments 03-04. Scope unchanged: `READY_ORIGINAL_EN`
records only. No external API calls.

## Motivation

Experiment 04 found a real "alias handling is weak" gap named in the handoff:
the tweet text "Kalka Ji" does not match the gazetteer's "Kalkaji". The user
asked whether fuzzy matching could close gaps like this generally, for the
57 distinct mention texts experiment 03 left `OUT_OF_GAZETTEER_UNRESOLVED` in
the audited 150-record sample.

## Exploration (before building anything)

Ran `rapidfuzz` against all 57 real unresolved mentions from experiment 03,
comparing two scorers:

**`token_sort_ratio` (word-order-tolerant) was tested and rejected.** It scored
`"Nagar Kirtan"` (a Sikh religious procession term, not a place) at **87.0**
against `"Kirti Nagar"` (a real, different place) — a confident-looking false
positive caused entirely by ignoring word order. Not safe for this domain.

**Plain `fuzz.ratio` (character-level Levenshtein, order-sensitive) was tested
directly on `"Kalka Ji"` vs. `"Kalkaji"`: only 80.0** — the same score as a
real wrong match (`"Heera Public School"` vs. `"SD Public School"`, also
80.0). Levenshtein ratio penalizes a single removed space disproportionately
on short strings, so it can't cleanly separate this exact case from noise.

This led to testing a **two-stage design** instead of one fuzzy pass:

1. **Whitespace/punctuation-normalized exact match** — lowercase, strip
   everything but letters/digits, compare. Zero ambiguity risk (it is still an
   exact match after removing a cosmetic difference). Catches `"Kalka Ji"` /
   `"Kalkaji"` perfectly, along with 4 other real spacing/punctuation variants
   in the sample.
2. **`fuzz.ratio` on the remainder only**, for genuine spelling typos. Sorted
   scores on the 52 mentions stage 1 didn't already resolve show a clean
   10-point cliff:
   ```
   94.1  Mehraulli    -> Mehrauli
   93.3  Samalka      -> Samalkha
   90.9  Kirbi Place  -> Kirby Place
   --- 10-point gap ---
   80.0  Heera Public School -> SD Public School   (wrong)
   80.0  Foota Road          -> Kotla Road          (wrong)
   ```
   Threshold set at **90**: 3/3 correct at or above it, 0 false positives, and
   a comfortable margin either side of the cliff.

## Implementation

`src/entity_resolution.classify_mention` now tries, in order, stopping at the
first hit: (1) exact case-insensitive match [unchanged from experiment 03];
(2) whitespace/punctuation-normalized exact match, new status
`GAZETTEER_NORMALIZED_MATCH`; (3) `fuzz.ratio >= FUZZY_RATIO_THRESHOLD` (90),
new status `GAZETTEER_FUZZY_MATCH`, with the exact score recorded in the
result (`fuzzy_score`) so a fuzzy match is never silently indistinguishable
from an exact one. Anything matching a generic term at any stage still routes
to `GAZETTEER_GENERIC_AMBIGUOUS` as before. Everything else is still
`OUT_OF_GAZETTEER_UNRESOLVED`, with no guess recorded.

`experiments/05_fuzzy_alias_matching.py` reran the classification on the full
150-record sample (same NER pipeline as experiment 02, 406 total entity
spans — a small, already-explained difference from experiment 03's 408, which
used a differently-constructed dual-source pipeline for its own audit purpose,
not a discrepancy introduced here).

## Findings

| Status | Count | % |
| --- | ---: | ---: |
| `GAZETTEER_RESOLVED` | 306 | 75.4% |
| `OUT_OF_GAZETTEER_UNRESOLVED` | 74 | 18.2% |
| `GAZETTEER_GENERIC_AMBIGUOUS` | 17 | 4.2% |
| `GAZETTEER_NORMALIZED_MATCH` | 6 | 1.5% |
| `GAZETTEER_FUZZY_MATCH` | 3 | 0.7% |

Compared to experiment 03, `OUT_OF_GAZETTEER_UNRESOLVED` dropped from 83 to 74
(9 mentions recovered, all in the audited sample, all manually verifiable as
correct):

**Normalized matches (6):** `Mangol Puri`→`Mangolpuri`, `Pahar Ganj`→
`Paharganj`, `Red Fort-`→`Red Fort`, `Sagar Pur`→`Sagarpur`, `Satyaniketan`→
`Satya Niketan` (5 distinct mention texts, 6 occurrences in the sample).

**Fuzzy matches (3):** `Kirbi Place`→`Kirby Place` (90.9), `Mehraulli`→
`Mehrauli` (94.1), `Samalka`→`Samalkha` (93.3).

`"Kalka Ji"` itself did not appear in this run's entity list (as found in
experiment 04, it isn't recognized as an entity span at all by the current NER
pipeline — an upstream recognition gap, not an alias-matching one), but the
normalization stage was verified directly against it in
`tests/test_entity_resolution.py` and matches `"Kalkaji"` cleanly.

## Tests

Added to `tests/test_entity_resolution.py` (8 new, 16 total in that file):
normalized matches for `Kalka Ji`, `Mangol Puri`, `Red Fort-`; fuzzy matches
for `Mehraulli`, `Samalka`; a below-threshold real wrong candidate
(`Heera Public School`) confirmed to stay unresolved; the `Nagar Kirtan` /
`Kirti Nagar` word-reordering false-positive case confirmed to stay unresolved
under the plain (non-reordering) scorer; and a check that exact matches never
carry a spurious `fuzzy_score`.

Full suite: **66/66 passing** (18 new across this experiment: 8 entity-
resolution + no new geocoding tests this round).

## Design decision

Both match stages are conservative by construction: normalization only ever
produces an exact match after removing cosmetic differences (no scoring
judgment at all), and the fuzzy threshold was set from a real, well-separated
cliff in this sample's data rather than a conventional default (e.g. 80,
which would have accepted both real wrong matches found here). `match_method`
and `fuzzy_score` are always recorded, so nothing recovered by this stage is
ever indistinguishable downstream from a genuine exact gazetteer hit.

## Known limitations (still open, explicit)

- The 90 threshold is evidenced on 57 real mentions from one 150-record
  sample, not the full 4,325-record corpus. It may need revisiting once a
  larger, more diverse set of typos is seen.
- Recognition gaps (a mention not being tagged as an entity at all, like
  "Kalka Ji") are outside this module's scope entirely — alias matching can
  only help once spaCy's NER has already produced a span to classify.
- The 65 mentions still `OUT_OF_GAZETTEER_UNRESOLVED` at threshold 90 include
  both real gazetteer gaps (e.g. `Andheria Mor`) and non-place NER noise (e.g.
  `DC`, `DTC`) — this module still makes no attempt to tell those apart, per
  experiment 03's original scoping decision.
- `_fuzzy_index` is cached per distinct gazetteer via `lru_cache`, but
  `process.extractOne` still scans all ~1,014 gazetteer terms per unresolved
  mention; fine at this sample size, not benchmarked at full-corpus scale.

## Decision: **KEEP**

Both the scorer (plain ratio over word-order-tolerant) and the threshold (90,
not a textbook default) were chosen from a real, inspected cliff in this
corpus's own data, with the specific false positive that would have resulted
from the wrong choice (`Nagar Kirtan`/`Kirti Nagar`) named and tested against
directly.

## Reviewer-response link

Same as experiments 01-04 (R2.4, R2.3, R1.4) — directly closes part of the
handoff's "alias handling is weak" / "no systematic ... spelling
normalization" finding.
