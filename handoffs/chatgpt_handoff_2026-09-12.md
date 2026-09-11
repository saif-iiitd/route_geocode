# Route-Geocoder Manuscript Revision — Chat Handoff

_Last updated: 12 September 2026_

## Project

Manuscript under revision for the **International Journal of Geographical Information Science (IJGIS)**:

**“Route-based Geocoding of Traffic Congestion-Related Social Media Texts on a Complex Network”**

The paper proposes route-based geocoding of traffic-related social-media text using a 12-configuration spatial ontology and a syntactic geocoder.

The editor rejected the current version but invited a **substantially reworked resubmission** addressing reviewer comments. The resubmission requires a point-by-point response/rebuttal and visibly tracked manuscript changes. The editor also asked that the paper not become longer. The deadline in the letter is **13 September 2026**.

## Main files

- `Revised Identifiable Manuscript July 2026.docx`
- `Reviews_March2026.docx`
- `The_Geocoder.ipynb`
- `routes_batch1_highlighted.xlsx`
- `route_geocoder_validation_metrics.csv`
- `code_manuscript_review_audit.md`
- `text_translation_provenance_audit.md`

## Reviewer priorities

### Reviewer 1
1. No comparison with state-of-the-art / representative baselines.
2. Too much procedural description and insufficient scientific interpretation.
3. Table 1 Point example (“Chirag Delhi”) is ambiguous.
4. Originality of the 12-category ontology is inconsistently described.

### Reviewer 2
1. Position novelty against recent LLM / hybrid geocoding.
2. Tighten “primitive” vs “complex” definitions and information content.
3. Justify fixed rule precedence with ablation/sensitivity analysis.
4. Existing hotspot validation does not measure route correctness; add manually annotated gold routes with precision/recall/path-similarity metrics.
5. Quantify added value over point-based geocoding.
6. Explore severity weighting.
7. Add simple temporal slicing.
8. Sharpen interpretation of Figures 5/6 with named corridors/intersections and a policy scenario.

The strongest methodological weakness is **route-level correctness validation**.

## Gold-route validation already completed

Current validation workbook:
- 50 annotation records.
- 34 with both golden and inferred routes.
- 15 with inferred route but no gold.
- 1 with neither.
- 49 mappable.

For the 34 comparable routes:
- **Any geometric contact/intersection:** 76.5%
- **Shared positive-length segment:** 55.9%
- **Mean golden-route recovery @25 m:** 41.1%
- **Median golden-route recovery @25 m:** 20.9%
- **Mean inferred-route precision @25 m:** 31.3%
- **Mean overlap F1 @25 m:** 28.7%

Interpretation:
- The system often reaches the correct general corridor.
- Some failures are catastrophic entity/location-resolution errors.
- Some recover much of the gold route but over-extend dramatically.
- Low precision therefore comes from multiple stages, not a single cause.

Representative failure classes:
- Catastrophic displacement: A003, A013, A057, A079, A086, A098.
- Severe over-extension: A025, A036, A048, A052, A056.
- Good / near-good cases: A029, A047, A051, A055, A065, A085, A089.

Examples:
- A048: gold ≈ 3.79 km, inferred ≈ 64.2 km.
- A052: gold ≈ 5.45 km, inferred ≈ 76.4 km.

## Major notebook problems found by Codex audit

### Parser / semantic-role instability
- `extract_origin_destination` is defined more than once with incompatible contracts.
- Notebook behavior can depend on execution order.
- Different handlers infer roles differently.
- `starting at` is not robustly handled.
- `via`, `between`, and multiple route clauses are not represented systematically.

### Entity resolution
- Each place is resolved independently.
- The code generally accepts the first acceptable OpenCage result within broad Delhi bounds.
- It does not implement the manuscript’s implied contextual confidence/ranking logic.
- No joint disambiguation across co-mentioned places.
- Alias handling is weak.

### Road resolution
- Named roads are matched using brittle exact equality such as `edges['name'] == road_name`.
- No systematic use of aliases, `alt_name`, `official_name`, `ref`, spelling normalization, etc.

### Named-road constraints are not truly enforced
For O2DonL, endpoints may be moved near the named road, but shortest-path routing runs over the full Delhi graph. The route can therefore leave the named road even though the manuscript says the route is clipped/traced along it.

### Fallbacks can masquerade as successful routes
On failure the notebook may:
- connect surviving resolved points;
- route between geocoder bounding-box corners;
- use legacy tweet bounding boxes.

This can generate plausible-looking geometry even when the intended route has not been resolved.

### Nondeterminism
Origin-only and destination-only configurations generate random sample points.

### Multipart geometry is flattened
Coordinates from distinct routes/components can be concatenated into one path representation.

### Coordinate/interface inconsistencies
Different APIs/functions use different coordinate-order conventions and the code uses brittle flipping heuristics.

## Manuscript-code fidelity issues

The July manuscript describes several behaviors that the supplied notebook does not fully implement:
- confidence/ranking-based candidate selection;
- universal bounded network snapping with required-role rejection;
- named-road clipping;
- direct Nominatim fallback;
- deterministic route selection;
- structured confidence/provenance output.

There is also still a wording problem: some parts correctly distinguish seven adapted configurations and five new ones, while another methods sentence calls the entire 12-configuration ontology “novel.” This should eventually be corrected.

## Translation / text-provenance audit — major new finding

The full corpus has **5,144 records**.

The current geocoder passes **`translated_text` to the parser for every record**, even English tweets.

Codex found that `translated_text` is not a clean translation field. It mixes:
- translation;
- prefix/punctuation edits;
- spelling/alias normalization;
- undocumented substantive edits;
- toponym substitutions;
- relation and direction changes.

### Corpus counts
- Identical original and translated: 63
- Benign textual differences: 4,289
- Severe spatial discrepancies directly inspected: 78
- Possible toponym changes: 107
- Possible spatial-relation changes: 57
- Unresolved cross-language comparisons: 548
- Source/data corruption: 2

Summary:
- **242 records** have affirmative evidence of possible changes in spatial meaning.
- **78** are directly inspected severe discrepancies.
- **548** additional cross-language records remain unresolved.
- **792** records require adjudication or explicit handling before treating them as trustworthy parser input.

### Public tweet verification
- 5,143 valid status URLs / exact IDs were available.
- All 5,143 were successfully retrieved from the referenced public source.
- Only **one** public-source tweet materially disagreed with the dataset’s original `text`.
- Therefore the dataset `text` field is substantially more trustworthy as source text than the legacy `translated_text`.

### Important examples

#### Jail Road → Tilak Nagar
Public tweet and dataset original:
- **Jail Road towards Hari Nagar**

Legacy `translated_text`:
- **Tilak Nagar towards Hari Nagar**

This is an undocumented substitution in the translated/edited field. The source tweet is already English.

#### R.K. Puram / Keshav Puram
Public tweet and dataset original mention:
- AIIMS towards **R.K. Puram**

Legacy `translated_text` also preserves R.K. Puram.

But old `address` metadata says:
- **Keshav Puram**

This is not a translation problem. It is legacy location/geocoding metadata contamination. Multiple records show the same pattern.

#### Other severe examples
- Delhi Cantt → “Delhi from Kentucky”
- Sapna Cinema → Dream Cinema
- Raja Garden → King Garden
- Rajdoot Hotel → Ambassador Hotel
- Loha Mandi → Iron Maiden
- Outer Ring Road → Ring Road
- Sansad Marg → Parliament
- `near X` becoming `to X`
- `between X and Y` losing its relation
- `via` landmarks becoming destinations or disappearing
- explicit direction reversals
- one route status changing from **reopened** to **closed**
- one `#NAME?` record with translated text copied from the previous row
- one field-spill/corruption record

## Correct revision order now

1. **Canonical text / provenance layer**
2. **Semantic-role parser stabilization**
3. **Candidate-based entity resolution**
4. **Delhi traffic gazetteer / alias layer**
5. **Road resolver**
6. **Constraint-preserving route construction**
7. **Remove bad fallbacks / add explicit unresolved states**
8. **Gold-route validation**
9. **Baseline comparison**
10. **Precedence-rule ablation**
11. **Severity / temporal analyses**
12. **Manuscript updates**
13. **Reviewer-response letter**
14. **Tracked-changes manuscript**

Semantic-role work is currently **paused until the parser-input layer is fixed**.

## Immediate next Codex task

The next Codex task is:

# CANONICAL PARSER INPUT AND TEXT-PROVENANCE LAYER

Use `text_translation_provenance_audit.md` as the specification.

### Required schema
Create explicit fields such as:
- `dataset_record_id`
- `tweet_id`
- `tweet_url`
- `text_original`
- `text_from_verified_source`
- `language_original`
- `text_translated_legacy`
- `text_translated`
- `translation_method`
- `translation_version`
- `translation_review_status`
- `text_for_parser`
- `parser_text_origin`
- `normalization_version`
- `data_quality_flags`
- `existing_location_metadata`

### Identifier policy
- Extract exact tweet IDs from permalinks and store them as strings.
- Do not use the current scientific-notation numeric `id` field as a join key.
- Do not use positional row joins.

### English parser policy
For English originals:
`text_for_parser = spatially_safe_normalization(text_original)`

Do **not** use legacy `translated_text`.

Safe normalization may include:
- whitespace cleanup;
- harmless punctuation normalization;
- removing a generic Traffic Alert prefix.

It must not:
- replace proper names;
- change road identities;
- reorder locations;
- alter `from`, `to`, `towards`, `via`, `on`, `near`, `between`;
- infer a “better” place.

### Non-English policy
Do not silently use the legacy translation.

Instead:
- preserve original Hindi/non-English text;
- mark translation as required;
- preserve toponyms and their order;
- later build a controlled translation layer that protects toponyms and spatial relations.

### Quarantine known bad records
Flag, do not delete:
- Jail Road → Tilak Nagar;
- `#NAME?` / previous-row contamination;
- field-spill record;
- severe translation discrepancies;
- unresolved translation cases.

### Codex outputs
- `src/text_provenance.py`
- `src/parser_input.py`
- `results/canonical_parser_input.csv`
- `tests/test_parser_input.py`
- `experiments/00_parser_input_provenance.md`

### Required tests
- English tweets use original verified wording.
- Jail Road remains Jail Road.
- R.K. Puram cannot be rewritten from Keshav Puram legacy metadata.
- Tweet IDs survive at full precision.
- Known bad records receive explicit flags.
- Non-English unresolved records do not silently pass as valid English parser input.
- Repeated clean runs produce identical output.
- Original source fields remain unchanged.

### Codex final report should show only
1. files created/changed;
2. test results;
3. parser-ready vs translation-required counts;
4. `text_for_parser` for Jail Road;
5. handling of R.K. Puram/Keshav Puram;
6. handling of the `#NAME?` record;
7. confirmation that `translated_text` is no longer the canonical parser input.

## Semantic roles — for later

Semantic roles describe the job each place plays in the route:
- `origin`
- `destination`
- `landmark`
- `named_road`
- `via_point`
- `via_road`

Example:
“from Patel Chowk towards Jantar Mantar on Sansad Marg”

- Patel Chowk → origin
- Jantar Mantar → destination
- Sansad Marg → named road

The manuscript conceptualizes this as a constraint tuple `C = (O, D, A, L)`.

Future code should preserve each mention with its role rather than maintaining separate name and coordinate arrays.

## Planned baseline comparison

Eventually compare:

### Baseline A — Point geocoder
Resolve the principal place and return a point.

### Baseline B — Syntax-blind endpoint router
Resolve origin and destination and request a normal route, without ontology or route constraints.

### Model C — Proposed route geocoder
Full ontology + route constraints.

Compare using:
- recovery;
- precision;
- F1;
- Hausdorff;
- length ratio;
- constraint satisfaction.

This directly tests whether the ontology adds value beyond ordinary endpoint routing.

## Planned precedence sensitivity

Test:
- current complex → primitive order;
- primitive → complex;
- order by number of constraints;
- random valid permutations.

Report:
- fraction of classifications that change;
- distributional changes by configuration;
- downstream route metrics on gold data.

Do this only after parser behavior is deterministic.

## Planned revised validation structure

### Validation 1 — Ontology generalizability
Delhi vs New Jersey traffic/nontraffic using SII.

### Validation 2 — Route correctness
Gold-route sample using:
- intersection;
- recovery;
- precision;
- F1;
- Hausdorff;
- length ratio;
- possibly direction/constraint satisfaction.

### Validation 3 — Aggregate external validity
Existing Delhi Traffic Police hotspot comparison:
- 50 ground-truth hotspots;
- 50 random controls;
- GTH mean ≈ 102;
- random-control mean ≈ 33;
- Welch t-test p ≈ 0.0044.

These answer:
1. Can the ontology recognize route-bearing spatial language?
2. Can the geocoder recover the intended route?
3. Do aggregated route outputs align with observed congestion geography?

## Manuscript framing

Do not hide current route-level weakness.

A useful eventual interpretation is:

> Errors propagate through three stages: toponym resolution, syntactic role assignment, and network-route delineation. Toponym resolution accounts for the most catastrophic spatial displacements, while route delineation accounts for many low-precision cases where the correct corridor is partially or substantially recovered but the inferred geometry is too long.

## Codex working discipline

Every substantive change should produce an experiment note, for example:
`experiments/E03_road_resolution.md`

Each experiment record should include:
- reviewer motivation;
- hypothesis;
- code change;
- parameters;
- baseline metrics;
- new metrics;
- improved cases;
- regressions;
- KEEP / REJECT decision;
- manuscript impact;
- reviewer-response link.

Nothing should move directly from code into the manuscript without:
1. tests;
2. validation;
3. experiment record.

## Recommended repository structure

```text
route-geocoder-revision/
├── AGENTS.md
├── README.md
├── manuscript/
│   ├── submitted/
│   ├── revised/
│   ├── tracked/
│   └── figures/
├── reviews/
│   ├── reviewer_1.md
│   ├── reviewer_2.md
│   ├── editor.md
│   └── revision_matrix.csv
├── baseline/
│   ├── The_Geocoder_submitted.ipynb
│   └── baseline_metrics.json
├── src/
│   ├── text_provenance.py
│   ├── parser_input.py
│   ├── models.py
│   ├── semantic_parser.py
│   ├── entity_resolution.py
│   ├── gazetteer.py
│   ├── road_resolver.py
│   ├── routing.py
│   └── evaluation.py
├── notebooks/
├── data/
│   ├── validation/
│   ├── gazetteer/
│   └── cached_geocoder/
├── experiments/
├── results/
├── tests/
└── response_to_reviewers/
```

## Scientific/reproducibility principles

- Do not fabricate routes merely to avoid unresolved output.
- Preserve ambiguity explicitly.
- Separate coverage from conditional accuracy.
- Do not optimize directly against gold-route geometry.
- Use gold data for evaluation, not as runtime evidence.
- Preserve candidate lists and provenance.
- Use exact tweet IDs as strings.
- Keep legacy metadata separate from new geocoder outputs.
- Cache external geocoder responses used in final experiments.
- Record provider/API versions, dates, CRS, tolerances and software environment.
- Never claim manuscript behavior that the frozen code does not implement.

## Current stopping point

Latest completed Codex output:
`text_translation_provenance_audit.md`

**Next action in Codex:** implement the canonical parser-input and text-provenance layer.

Do not yet:
- implement semantic roles;
- improve geocoder candidate ranking;
- rerun full route inference;
- edit the manuscript.

Once Codex completes that parser-input layer and reports the tests/counts, return to ChatGPT and continue from this handoff.
