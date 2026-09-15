# Supplementary Information: Entity Recognition and Candidate-Based Resolution

Prepared 2026-09-16. Scope: how place mentions are recognized in tweet text
(the notebook's existing pipeline, audited but not changed) and how each
recognized mention is classified by local resolution evidence before any
external geocoder is consulted (`src/entity_resolution.py`, `src/geocoding.py`
— new this revision). Does not cover semantic-role assignment (see the
companion *Semantic-Role Parsing* document) or route/network construction,
which are separate, later pipeline stages.

## S1. Background and scope

A code-fidelity audit of `The_Geocoder.ipynb` found specific, named
deficiencies in how the notebook resolves recognized place mentions to actual
locations:

> "Each place is resolved independently. The code generally accepts the first
> acceptable OpenCage result within broad Delhi bounds. It does not implement
> the manuscript's implied contextual confidence/ranking logic. No joint
> disambiguation across co-mentioned places. Alias handling is weak."

Concretely, cell 17 (`extract_point_route`) calls
`geocoder.geocode(place, proximity=delhi_center)` for each mention and accepts
the first result within Delhi bounds — with no check on whether the mention
text is even resolvable in principle, no ranking of alternative candidates,
and no use of any co-mentioned place to disambiguate. This document describes
the audit of entity recognition itself, and the new candidate-resolution
layer built to address the parts of the above finding answerable with local
data, live geocoding, and evidence-based alias matching.

All work below is scoped to the 4,325 `READY_ORIGINAL_EN` (English-original)
records only, using the canonical `text_for_parser` field.

## S2. Step 1 audit: entity recognition as currently implemented

The notebook's actual entity-recognition pipeline (cells C10/C12) was
reproduced exactly and run, read-only, against a seeded sample of 150
`READY_ORIGINAL_EN` records (`seed=20260913`, deterministic and reproducible):
spaCy `en_core_web_sm`'s base NER, combined with an `EntityRuler` and a
case-insensitive `PhraseMatcher`, both built from the project's gazetteer file
(`Data/tweet_location_terms.txt`, 1,014 place-name entries), de-overlapped
with `spacy.util.filter_spans`, keeping entities labeled `LOC`, `GPE`, `ORG`,
or `FAC`.

| Metric | Value |
| --- | ---: |
| Records with zero recognized entities | 3/150 (2.0%) |
| Mean entities per record | 2.71 |
| Max entities in one record | 7 |

The three zero-entity records name real Delhi locations absent from the
gazetteer (e.g. *"Swami Nagar Subway"*, *"K. N. Katju Marg"*) — a gazetteer
coverage gap, not a code defect. This is a starting baseline on 150 of 4,325
records, not a certified corpus-wide rate.

## S3. Step 2 signal: the notebook's own unused dependency parse

The notebook already computes a full dependency parse (`token.dep_`) in cell
42, but only prints it — it is never used for role assignment. An audit of
every `to`/`towards` token across the same 150-record sample found this
signal cleanly separates real spatial prepositions from two look-alike
constructions with no phrase-blacklist required:

| Label | Count | Meaning |
| --- | ---: | --- |
| `towards`, `dep_=prep` | 89 | Real spatial preposition |
| `to`, `dep_=pcomp` | 81 | Complement of "due" (**not** spatial) |
| `to`, `dep_=prep` | 36 | Real spatial preposition |
| `to`, `dep_=aux` | 4 | Infinitive marker before a verb (**not** spatial) |
| `towards`, `dep_=ROOT` | 1 | Parser failure on a malformed fragment |

This is used by the semantic-role parser (see the companion document, S3.3),
not by the entity-resolution layer described below; it is recapped here
because it was discovered in the same audit pass as S2 and because it
motivated the "verify before trusting a signal empirically" methodology
followed throughout this document.

## S4. Candidate-based entity resolution (`src/entity_resolution.py`)

Before any mention reaches a geocoder, `classify_mention(text,
gazetteer_by_lower, ...)` classifies it into one of five statuses, using only
local data — no network call, no invented disambiguation:

| Status | Meaning | Method |
| --- | --- | --- |
| `GAZETTEER_RESOLVED` | Exact (case-insensitive) match to a specific gazetteer entry | Direct dictionary lookup |
| `GAZETTEER_GENERIC_AMBIGUOUS` | Matches a gazetteer entry, but that entry names a *feature type* shared by many real places (e.g. "Flyover", "Temple"), not one specific place | Curated list of 6 single-word generic entries, found by manually reviewing all 250 single-word gazetteer terms: `Boulevard`, `Flyover`, `Garden`, `Mandi`, `Temple`, `Underpass` |
| `GAZETTEER_NORMALIZED_MATCH` | Matches a gazetteer entry once whitespace/punctuation differences are stripped | Lowercase, strip all non-alphanumeric characters, exact-match |
| `GAZETTEER_FUZZY_MATCH` | Character-level fuzzy match at or above an evidenced confidence threshold | `rapidfuzz.fuzz.ratio >= 90` |
| `OUT_OF_GAZETTEER_UNRESOLVED` | None of the above; recognized only by spaCy's base NER | No match found |

Every result records which method matched (`match_method`) and, for a fuzzy
match, the exact score (`fuzzy_score`) — a fuzzy or normalized match is never
silently indistinguishable downstream from a genuine exact gazetteer hit.

### S4.1 Why a generic term is not auto-resolved

A mention like `"flyover"` cannot be geocoded on its own text alone — Delhi
has many flyovers. Treating it as resolved to "the nearest flyover" would
silently fabricate a specific location the tweet never named. Instead it is
flagged `GAZETTEER_GENERIC_AMBIGUOUS` and handled by the co-mentioned-place
disambiguation described in S6.

### S4.2 Why normalized and fuzzy matching exist, and how their thresholds were set

Both stages exist because a plain exact match misses real spelling/spacing
variants between tweet text and the gazetteer — a concrete instance of the
"alias handling is weak" finding. Rather than assume a threshold, both were
set empirically against this corpus's own data (full exploration log in
`experiments/05_fuzzy_alias_matching.md`):

**Word-order-tolerant fuzzy scoring (`token_sort_ratio`) was tested and
rejected.** It scored `"Nagar Kirtan"` (a religious procession term, not a
place at all) at **87** against `"Kirti Nagar"` (a real, different place) —
a confident-looking but entirely wrong match, caused by ignoring word order.

**Plain character-level `fuzz.ratio` on `"Kalka Ji"` (as written in tweet
text) vs. the gazetteer's `"Kalkaji"` scored only 80** — the same score as a
real wrong match (`"Heera Public School"` vs. `"SD Public School"`, also 80).
Levenshtein-style ratio over-penalizes a single removed space on a short
string. This motivated splitting alias matching into two stages instead of
one fuzzy pass:

1. **Normalization first** (strip whitespace/punctuation, compare exactly) —
   zero ambiguity risk, since it is still an exact match once a cosmetic
   difference is removed. Catches `"Kalka Ji"`/`"Kalkaji"`,
   `"Mangol Puri"`/`"Mangolpuri"`, `"Red Fort-"`/`"Red Fort"`, and similar.
2. **Fuzzy matching only on what remains**, with the threshold read directly
   off a real cliff in the data:
   ```
   94.1  Mehraulli    -> Mehrauli      (correct)
   93.3  Samalka      -> Samalkha      (correct)
   90.9  Kirbi Place  -> Kirby Place   (correct)
   --- 10-point gap ---
   80.0  Heera Public School -> SD Public School   (wrong)
   80.0  Foota Road          -> Kotla Road          (wrong)
   ```
   Threshold set at **90**: correct on every case at or above it, wrong on
   every case tested below it, in this sample.

## S5. Findings: combined classification over the audited sample

Reclassifying all 406 entity spans found across the same 150-record sample
(experiment 05, which includes the normalized/fuzzy stages; a very slightly
different pipeline construction used for an earlier, narrower audit in
experiment 03 found 408 — a documented, explained, immaterial difference, not
a discrepancy in these findings):

| Status | Count | % |
| --- | ---: | ---: |
| `GAZETTEER_RESOLVED` | 306 | 75.4% |
| `OUT_OF_GAZETTEER_UNRESOLVED` | 74 | 18.2% |
| `GAZETTEER_GENERIC_AMBIGUOUS` | 17 | 4.2% |
| `GAZETTEER_NORMALIZED_MATCH` | 6 | 1.5% |
| `GAZETTEER_FUZZY_MATCH` | 3 | 0.7% |

**A real complication inside "unresolved," surfaced rather than hidden:** the
74 out-of-gazetteer mentions mix two genuinely different situations —
uncatalogued real places (e.g. `"Andheria Mor"`, a real Delhi location absent
from the gazetteer file) and non-place NER noise (e.g. `"DC"`, `"DTC"` —
organization acronyms spaCy's base NER mistagged as locations). This module
makes no attempt to separate the two; both are left honestly unresolved
rather than one being guessed away.

## S6. Live candidate geocoding and ranking for generic mentions (`src/geocoding.py`)

The handoff explicitly flags "no joint disambiguation across co-mentioned
places" as missing from the notebook. This was addressed for the common case
found in the audited sample: **every one of the 17 generic mentions in the
150-record sample sits immediately next to an already-resolved specific
mention** (e.g. *"Peeragarhi flyover"*, *"Azadpur Mandi"*, *"Akshardham
Temple"*) — no free-standing generic mention (with no nearby qualifying name)
occurred in this sample.

Two designs were tested live against the OpenCage geocoding API before either
was built into the codebase:

- **Compound-query merging** (`"Peeragarhi Flyover, Delhi"` as one search
  string) — tested, **failed**: fell back to a city-level match at confidence
  3/10. This specific two-word combination is not indexed as one named entity.
- **Bounding-box-restricted bare-term search** — geocode the qualifying
  specific mention (e.g. `"Peeragarhi"`) first to get an anchor coordinate,
  build a small (~2.2 km) bounding box around it, then geocode the bare
  generic word (`"flyover"`) restricted to that box — tested, **worked**:
  returned real, correctly-named candidates (`"Mangolpuri Flyover"`,
  `"Shalimar Bagh Flyover"`).

The second approach was adopted. Candidates are ranked by two independent
signals:

1. **Name match** — does the candidate's returned name literally contain the
   generic term (e.g. `"Mangolpuri **Flyover**"`)? 12/12 candidates that
   returned any result matched on this signal in the audited sample.
2. **Local structural corroboration** — a free, zero-API cross-check against
   `Data/network_nodes_data.csv`, the project's own Delhi road-network
   dataset, which carries real `bridge`/`tunnel` flags on a subset of named
   road segments (152 and 23 of 53,691 nodes, respectively; 12 distinct named
   bridge segments, including two literally named `"Dwarka Flyover"` and
   `"Dhaula Kuan Flyover"`). Coordinates are reprojected from the dataset's
   native UTM zone 43N to WGS84 to compare against geocoder output. A
   candidate within 150 m of a matching flagged node is corroborated by two
   independent sources rather than one. In the audited sample this produced
   **zero hits** — expected, given how sparse the local flag coverage is
   (only 12 distinct named segments); absence here is documented as
   uninformative, not as evidence against a candidate.

Every OpenCage response used in these experiments is cached to disk
(`experiments/04_opencage_cache.json`, checked for and confirmed free of any
key material) so every reported number is reproducible from the cache alone,
without re-querying the API.

Two further real gaps were surfaced by this process, both left as documented
findings rather than silently patched:
- **A too-tight bounding box for sparser categories**: all three
  `"Akshardham Temple"` cases in the sample returned zero candidates for the
  bounded bare `"temple"` query, even though the qualifier ("Akshardham")
  geocoded correctly. An unbounded query near the same anchor does return
  results, just none inside the ~2.2 km box — a real data-sparsity limitation
  for this category, not a bug.
- **Candidate uniqueness is not guaranteed**: two different qualifiers
  (`"Manglapuri"` and `"Palam"`) both returned `"Dwarka Flyover"` as their top
  candidate — geographically plausible (both areas are near Dwarka in
  southwest Delhi) but currently undetected as a potential collision.

## S7. Improvements over the notebook baseline

| Notebook baseline | This work |
| --- | --- |
| Every mention geocoded independently, first OpenCage result accepted within broad Delhi bounds | Every mention classified by local evidence *before* any geocoder call; a mention with no local evidence is marked unresolved, not silently geocoded |
| No candidate ranking or confidence logic | Candidates ranked by name match and independent local structural corroboration when a geocoder call is made |
| No joint disambiguation across co-mentioned places | Generic/ambiguous mentions resolved using an adjacent already-resolved mention as a geocoding anchor |
| Weak alias handling, no spelling/spacing normalization | Two-stage normalized + fuzzy alias matching, with thresholds set from real, inspected data rather than defaults, and a specific false-positive risk (word-order-tolerant scoring) tested and explicitly rejected |
| No record of *why* a place was or wasn't resolved | Every classification carries a `reason`, `match_method`, and (where applicable) a `fuzzy_score` — never a bare accept/reject |

## S8. Validation

`tests/test_entity_resolution.py`: **16 tests**, all using real corpus
mentions found by the audits above as fixtures — exact match, case
insensitivity, generic-term flagging, out-of-gazetteer handling for both a
real missing place and NER noise, normalized matches (`Kalka Ji`,
`Mangol Puri`, `Red Fort-`), fuzzy matches (`Mehraulli`, `Samalka`), a
below-threshold real wrong candidate confirmed to stay unresolved, and the
`Nagar Kirtan`/`Kirti Nagar` word-reordering false-positive guard.

`tests/test_geocoding.py`: **10 tests**, no live API calls required — cache
hit/miss/collision behavior, a haversine-distance check against a known Delhi
distance (India Gate to Connaught Place), bounding-box geometry, UTM
reprojection sanity-checked against Delhi's real coordinate range, structural
corroboration against the real `"Dwarka Flyover"` node, and explicit checks
that the absence of corroboration returns `None` rather than raising or
fabricating a match.

Full project test suite: **66/66 passing** as of 2026-09-16.

## S9. Known limitations (explicit, not fixed this round)

- **Free-standing generic mentions** (no adjacent already-resolved qualifier)
  are not handled — none occurred in the audited 150-record sample, so the
  fallback of anchoring to the tweet's overall origin/destination corridor
  instead of a single qualifier remains a documented but unimplemented design.
- **Candidate uniqueness across different mentions is not checked** (S6).
- **Bounding-box size (~2.2 km) is a single fixed choice**, not tuned per
  generic-mention category; it returned zero results for every "temple" case
  tested.
- **The fuzzy-match threshold (90) is evidenced on 57 real mentions from one
  150-record sample**, not the full 4,325-record corpus.
- **`OUT_OF_GAZETTEER_UNRESOLVED` does not distinguish** a genuine gazetteer
  coverage gap from non-place NER noise (S5) — both require different fixes
  (gazetteer expansion vs. an NER-noise filter), neither implemented here.
- **A full-corpus (4,325-record) pass has not been run** for either the entity-
  recognition audit or the resolution/geocoding layers — everything above is
  reported against the same seeded 150-record sample for direct comparability
  across experiments, not corpus-wide coverage.
- **OpenCage's free tier (2,500 requests/day)** has not been budgeted against
  a full-corpus run; this session's experiments used only a few dozen cached
  calls.

## S10. Reviewer-response link

Addresses R1.4 (entity/location resolution fidelity), R2.3 (candidate
ranking / no joint disambiguation), and R2.4 (alias handling) from the
reviewer priorities list.

## S11. Reproducibility

```powershell
python -B -m unittest tests.test_entity_resolution tests.test_geocoding -v
python -B experiments/03_entity_resolution_audit.py
python -B experiments/04_generic_mention_candidate_resolution.py   # uses the committed OpenCage cache; a live key is needed only on a cache miss
python -B experiments/05_fuzzy_alias_matching.py
```

Source: `src/entity_resolution.py`, `src/geocoding.py`. Tests:
`tests/test_entity_resolution.py`, `tests/test_geocoding.py`. Experiment
notes with full audit detail: `experiments/02_entity_dependency_audit.md`,
`experiments/03_entity_resolution_audit.md`,
`experiments/04_generic_mention_candidate_resolution.md`,
`experiments/05_fuzzy_alias_matching.md`.
