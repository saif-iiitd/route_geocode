# Text and data provenance audit

Date: 12 September 2026. Corpus: `Data/tweets_data.csv`, all **5,144 records**. Context files: `Data/routes_data.csv`, `Data/tweet_location_terms.txt`, the other Data files, and `The_Geocoder.ipynb`.

The geocoder receives **`translated_text` for every record**, including English tweets. This field combines translation, prefix removal, punctuation changes, spelling/alias normalization, and some substantial undocumented edits. It is not a trustworthy verbatim translation layer. The existing `address`, `locations`, coordinates, confidence and bounding boxes are already present before the notebook runs. Most are not consumed by its routing logic, but the four existing bounding-box fields can generate a fallback route.

The audit found **242 records with affirmative screening evidence of possible spatial-meaning changes**, including **78 directly inspected severe discrepancies**. An additional **548 cross-language records remain unresolved**, not verified as semantically equivalent. The combined figures must not be presented as a complete human-annotated translation error rate.

Public-source verification succeeded for **all 5,143 available status URLs**. The dataset original differs materially from its referenced public tweet in **one verified record**, whose original is `#NAME?` and whose translation duplicates the preceding row. One other record has no usable URL/ID and contains apparent source-text spill into metadata columns. No inaccessible or missing record was assumed to be incorrect or deleted.

No source data, translation, notebook, semantic parser, manuscript, or prior audit was changed. No route geocoding was run. Audit scripts write only the new evidence and report outputs.

## Outputs and reproducibility

- [Full record-level screening ledger](../results/translation_discrepancies.csv): one record for **every** input tweet, including unchanged and unresolved cases, so the denominator is reproducible. Contains original text, existing translated text, actual current parser input, URL/exact ID, flags, audit classification, inspected-case notes and selected legacy location fields.
- [Original tweet verification](../results/provenance_audit/original_tweet_verification.csv): requested source-text evidence and final retrieval/match statuses for all 5,144 records.
- [Minimal public-source evidence cache](../results/provenance_audit/public_tweet_evidence.jsonl): one entry per request attempt; contains status URL/ID, official oEmbed request/returned URL, returned tweet text, author URL, UTC request timestamp, status and response digest. Five transient failures and their successful retries are retained. No media, profiles, credentials, or unrelated page data were cached.
- [Field inventory](../results/provenance_audit/field_inventory.csv): every one of the **1,716 input columns**, including empty columns, with nonempty counts, likely provenance and notebook usage.
- [Audit summary and input hashes](../results/provenance_audit/audit_summary.json): machine-readable counts and source fingerprints.
- Audit-only reproduction scripts: [corpus screen](../results/provenance_audit/audit_corpus.py), [public retrieval](../results/provenance_audit/retrieve_public_tweets.py), and [evidence summarization](../results/provenance_audit/finalize_reporting_data.py). These are not proposed production parser code. Public retrieval resumes from its cache and allows only one retry for a transient failure.

All row references below are **logical CSV record numbers counting the header as row 1**. They are not guaranteed to be physical text-file line numbers. Notebook C42 means one-based physical cell 42, including Markdown cells; L numbers refer to its source lines. Original IDs, strings and source fields remain unchanged in the input files.

## What the current geocoder actually reads

The operative call is C42:L230–235:

```python
route_coordinates = process_tweet(
    row['translated_text'],
    row['bbox_ne_lat'],
    row['bbox_ne_lon'],
    row['bbox_sw_lat'],
    row['bbox_sw_lon']
)
```

C15 also classifies `df['translated_text']`. The batch covers `df.iloc[0:5144]`, which is the full input corpus here. Inside `process_tweet`, `nlp_tweet(tweet)`, NLTK tagging, regex classification, and the configuration handlers receive that same translated/edited string. Removing punctuation from a list of printed tokens does **not** replace the actual string sent to the classifier or handlers. There is no separate cleaned-text column selected at runtime, no translation API in this notebook, and no original-versus-translated quality gate.

The current input lineage is therefore:

**Public tweet → dataset `text` → undocumented `translated_text` creation/editing → unchanged string passed as `tweet` → recognition/classification/routing.**

A separate branch is:

**Undocumented pre-existing location lookup → stored bounding box → final fallback routing if the intended route is unresolved.**

C42:L184–185 uses `[bbox_sw_lon, bbox_sw_lat]` and `[bbox_ne_lon, bbox_ne_lat]` as routing endpoints. Existing `address`, `locations`, `lat`, `lon`, `osm_id`, `confidence` and `accuracy` are not read to select or rank the new candidates. Their values survive because the entire DataFrame is exported. C42:L221 writes the newly computed coordinate string into `route_coordinates`; C42:L224 saves `routes_data.csv` containing both old metadata and new output without a provenance boundary.

## Field provenance

“Likely source” is an inference from names, values and code. The collection, translation and earlier geocoding programs, method versions, prompts and edit histories are not supplied. No undocumented field is declared manually derived solely because it looks edited.

| Field or field group | Nonempty records | Likely source and provenance class | Current notebook use | Interpretation |
| --- | ---: | --- | --- | --- |
| `text` | 5,144 | Collected tweet text, with at least one corrupted cell and another apparent field-spill case | Not passed to classifier/handlers | Dataset-original candidate, independently verified where a URL exists; not immutable proof of the source by itself |
| `translated_text` | 5,144 | Undocumented translated **and edited/normalized** text; human versus automated changes unknown | Direct input for every tweet | Includes English edits, one still-Hindi record, and an unrelated previous-row copy |
| `detected_lang` | 5,144 | Derived language classification, method unknown | Not used for text selection | 4,326 `en`, 816 `hi`, 2 `id`; the two `id` samples are visibly English traffic alerts |
| A dedicated cleaned/normalized text field | Absent | No distinct field | None | Normalization is mixed into `translated_text`; logging token lists is not a persisted cleaning stage |
| `locations` | 5,144 | Earlier location extraction output as comma-separated strings | Carried through, not used by `nlp_tweet` | Can contain generic tokens, nested/repeated names and terms from an earlier text version; not a role assignment or canonical gazetteer |
| `address` | 5,144 | Pre-existing geocoding/address output, provider/version unknown | Carried through only | May refer to a wrong or over-broad place; not a new result of the audited notebook |
| `osm_id` | 5,144 | Legacy gazetteer identifier, probably OSM-linked | Carried through only | Identifier namespace/type and selecting query are undocumented; not a tweet ID |
| `lat`, `lon` | 5,144 each | Legacy selected-place coordinates | Carried through only | Not used as new route endpoints in the inspected code |
| `bbox_ne_lat`, `bbox_ne_lon`, `bbox_sw_lat`, `bbox_sw_lon` | 5,144 each | Legacy bounding box associated with earlier lookup | **Read by `process_tweet` and usable in fallback** | Can change output geometry even though the existing address string is ignored |
| `confidence` | 5,144 | Legacy geocoding confidence-like measure; values 6–10 | Not read for new candidate selection | Its existence does not prove confidence ranking in the current notebook |
| `accuracy` | 5,144 | Legacy score, definition unknown | Carried through only | Cannot be interpreted as route accuracy or validated positional error |
| `route_coordinates` in `tweets_data.csv` | **0** | Existing output slot, entirely empty | Written with new route string; not used as input | Empty input slot does not establish that all later results are valid or attributable |
| `classification_dummies` | 5,143 | First token in what appears to be an exported derived token list | Carried through only | Values such as `normal`, `carriageway`, `avoid`; not the twelve-configuration result |
| `Unnamed: 25` through `Unnamed: 49` | Varying, all 25 columns used somewhere | Apparent continuation of the token list, construction unknown | Carried through only | Not safe to silently discard as empty columns; first rows include `now`, `road`, `towards` |
| `Unnamed: 51` through `Unnamed: 1715` | **0** in every input row | 1,665 empty export-padding columns | Carried through only | Residue, not latent route evidence in the input |
| `Unnamed: 0` | 5,144, all unique | Likely retained row index from a larger upstream table | Not used as current DataFrame index explicitly | Useful preserved source-row key; do not interpret as tweet ID |
| `id` | 5,143 | Collected ID subsequently serialized in rounded scientific notation | Carried through only | Only **335 distinct nonempty strings**; **zero full-precision decimal IDs**. Unsafe join key |
| `permalink` | 5,143, all unique | Public tweet status URL | Carried through only | Supplies the recoverable exact status ID, stored as a string in this audit |
| `username`, `date`, `retweets`, `favorites` | 5,144 each | Likely collection metadata | Carried through only | Collection method and timezone provenance unknown; not new geocoder outputs |
| `geo` | 1 | Intended collection metadata, but sole value is `शेरशाह रोड` | Not used | Text spill in row 2635, not a trustworthy tweet geotag |
| `mentions` | 2 | Intended collection metadata; inspected values are `@` and `1/2"` | Not used | Both require provenance review; one accompanies `#NAME?`, one source-text spill |
| `hashtags` | 0 | Collection metadata slot | Not used | Entirely empty |
| `Data/tweet_location_terms.txt` | 1,014 nonempty lines | Local recognition vocabulary, construction undocumented | EntityRuler and case-insensitive PhraseMatcher input | Recognition aid, not per-tweet metadata, coordinate gazetteer, or canonical alias mapping |

The other Data files contain the original Karduni network, node-ID route sequences, counts/centralities, and enriched network tables. They do not contain a translation method/version or a source-text revision log. Their relevance is downstream lineage: corrupted input text or fallback geometry can propagate into their network measures. This audit did not recompute those measures.

## Full-corpus text comparison

### Method and limits

The audit reads CSV values as strings to avoid introducing further ID precision loss. It checks every original/translated pair, inventories URLs and field contents, compares the corresponding input/output records by exact permalink, and compares retrieved source text **first to the dataset original**, then separately to the translated field.

The text screen uses:

1. Exact original/translated string equality.
2. Conservative comparison after removing the “Traffic Alert” label, URL strings, whitespace/punctuation and case distinctions. Matching characters in the same order generally indicate benign presentation differences, not proof that every formatting change is irrelevant to a particular tokenizer. This is an audit comparison only; source fields are not normalized in place.
3. Direct inspection of **all 31 non-Hindi pairs** differing beyond that comparison. This distinguishes plausible spelling/alias normalization from substantive substitution, unsupported added specificity and source corruption. The substantive English edits are concentrated in the first 655 records; the responsible process is unknown.
4. A bounded bilingual glossary of known place surface forms/aliases, explicit spatial-cue checks, and occurrence-count checks across all Hindi-containing originals. The glossary finds at least one known Hindi name in **532 of 816** Hindi records. It is not exhaustive NER. Missing Latin aliases can reflect harmless transliteration variants. A missing explicit preposition can leave a relationship implicit. These are **possible-change flags**, not automatically confirmed mistranslations.
5. Direct bilingual inspection of representative early records, a systematic later-corpus sample, name-translation families, and residual flagged/unresolved cases. The scripts retain explicit record-level adjudications and notes, including **78 severe cases**. This is a single-analyst audit, not independent annotator agreement or an exhaustive bilingual gold standard. Review also removed known screening false positives, such as treating “starting from” as a missing via relation.

No new translations were generated. The audit glossary is used only to screen and compare the stored strings. It is not installed into the geocoder.

### Counts

The following primary classes are mutually exclusive and sum to **5,144**:

| Primary audit class | Count | Meaning |
| --- | ---: | --- |
| Identical original and translated text | **63** | Literal text equality; spatial meaning unchanged between these two fields |
| Benign textual differences | **4,289** | Conservative text-equivalence pass or inspected preservation of place identity/relations; includes 29 Hindi cases and plausible English alias/spelling edits |
| Severe spatial discrepancies, directly inspected | **78** | Material name/constraint/direction changes or serious loss of named-place identity; 77 Hindi and 1 English |
| Possible toponym change, not already severe | **107** | Screening or inspected uncertainty requiring adjudication |
| Possible spatial-relation change, not already severe/name-flagged | **57** | Screening or inspected uncertainty requiring adjudication |
| Unresolved cross-language comparison | **548** | Screen did not establish either a specific discrepancy or equivalence; **not a pass** |
| Source/data corruption | **2** | Rows 136 and 2635; do not classify these automatically as translation errors |
| **Total** | **5,144** | |

Required overlapping summary counts:

| Measure | Count | Denominator / interpretation |
| --- | ---: | --- |
| Records with a populated translated-text field | **5,144** | All input records; field presence is not proof of completed translation |
| No spatial change detected or equivalence inspected | **4,352** | 63 identical + 4,289 benign; provisional audit result, not a bilingual error-free certification |
| Possible change in spatial meaning | **242** | 78 severe + 107 other name cases + 57 relation-only cases, about 4.7% of the corpus |
| Possible toponym change including severe cases | **175** | Overlaps relation changes; excludes plausible inspected alias/spelling corrections |
| Possible spatial-relation change including severe cases | **117** | Overlaps name changes; includes direction/attachment concerns |
| Severe discrepancies directly inspected | **78** | Subset of 242; not extrapolated to the unreviewed corpus |
| Records requiring manual inspection/adjudication before trusting parser input | **792** | 242 flagged + 548 unresolved + 2 corrupted; already inspected severe cases still require author adjudication/remediation |
| Translated field still containing Devanagari | **1** | Row 1012; text is preserved, but the current English classifier is not thereby validated |

The 175 name flags and 117 relation flags are **not additive**. Some severe cases also concern feature type or route status. The 242 figure counts records once. The 548 unresolved cases are an explicit limitation, not silently included in “identical spatial meaning.” A complete adjudicated prevalence estimate would require finishing bilingual review of the uncertain set; these numbers must not be reported as all translation errors in the corpus.

By recorded language: `en` has 63 identical, 4,258 benign, 1 severe substitution, 3 possible name-specificity additions, and 1 corrupted original. `hi` has 29 benign/equivalent, 77 severe, 104 other possible name changes, 57 relation-only flags, 548 unresolved, and 1 source-spill case. Both `id` records are benign text differences and visibly English; do not infer an Indonesian corpus from those labels.

## Representative inspected cases

The evidence CSVs contain complete original, translated and retrieved source text. Excerpts below focus on the relevant discrepancy. “Severe” describes text/identity fidelity, not a newly measured geocoding error.

| Class | Dataset row(s) | Original versus translated evidence | Assessment |
| --- | --- | --- | --- |
| Identical text | 62 | “TRAFFIC ALERT Now Sansad Marg has opened for traffic.” matches in both fields | No original-to-translated change; source verification is a separate check |
| Benign prefix/punctuation | 3 | R.K Puram → R.K. Puram; Traffic Alert removed | Same place and direction; the Keshav Puram address is a separate issue |
| Plausible abbreviation/alias normalization | 30; 116, 125, 130 | Delhi Cantt → Delhi Cantonment; Red Fort → Lal Quila | Same apparent location identity; still preserve original surface and record the transformation |
| Benign bilingual route preservation | 8; 196; 209; 3221 | Shyamlal College → Bihari Colony on Road 57; Naraina → Dhaula Kuan; between Aurobindo Chowk/Tughlaq Road; Uttam Nagar → Tilak Nagar near Ganesh Nagar | Representative equivalence controls, despite awkward nonspatial English in some records |
| Place substitution in English | **2** | Jail Road → Tilak Nagar | Confirmed difference at dataset-original → edited `translated_text` stage; not attributable to Hindi translation |
| Added toponym specificity | 101; 333; 656 | Sanjay T-point flyover → Sanjay **colony** T-point flyover; Chandgi Ram Akhara → **Master** Chandgiram Akhara | May be valid canonicalization, but justification/version is absent; keep as possible change, not proven wrong location |
| Removed place | 642; 1293; 431 | Rafi Marg omitted; Rawta Mod omitted; Pul Prahladpur omitted | Required origin/landmark can disappear before NER |
| Added place through proper-name corruption | 271 | Delhi Cantt (`दिल्ली केंट`) becomes Delhi **from Kentucky** to Dwarka | Kentucky is introduced by the transformation; original surface must have been protected |
| Literal translation of proper names | 183; 184; 217; 225; 226 | Sapna Cinema → Dream Cinema; Raja Garden → King Garden; Rajdoot Hotel → Ambassador Hotel; Loha Mandi → Iron Maiden; Samrat Hotel → Emperor Hotel | Translation changes the gazetteer query surface even if the words have a literal English meaning |
| Repeated name inconsistently transformed | 539; 1183; 1204; 2031 | Azad Market appears in one position, “free market” in another | Simple presence of the correct name once is insufficient to prove every mention/role is preserved |
| Road identity loses defining qualifier | 81 | Outer Ring Road → Ring Road | Two road names must not be treated as automatically equivalent |
| Road/feature-type loss | 155; 373 | Rao Tula Ram **Marg** loses Marg; Sansad Marg becomes **Parliament** | Road becomes a person-like/general label or building/institution reference. No exhaustive road↔neighbourhood switch count is claimed |
| Feature semantics corrupted | 94; 2071 | Pusa/Jaswant Singh roundabout → round-the-clock/round-trip | A physical junction becomes a temporal/travel expression |
| Neighbourhood name/type transformed | 189 | Western Patel Nagar → Western Patel city | The neighbourhood's proper-name component is translated as a generic city label |
| Near/landmark relation changed | 5; 214 | Near Lajpat Nagar police station becomes traffic at the station; near Masoodpur becomes **to** Masoodpur | Proximity versus endpoint roles are altered or made ambiguous |
| Between relation lost | 208 | Between Aurobindo Chowk and Tughlaq Road becomes an unstructured list | Both names remain, but their relationship disappears |
| Via/waypoint role changed | 2860; 3176; 4551 | NH8 via Dhaula Kuan to Ramlila Maidan reverses and reassigns Dhaula Kuan; return via Modi flyover is omitted; via Nizamuddin flyover becomes to Nizamuddin flyover | A named intermediate place becomes an origin/destination or disappears from one leg |
| Direction reversal | **494**; 851; 288, 290; 5021; 5101 | Delhi → Noida becomes Noida → Delhi; Moti Nagar → Inder Lok reverses; Jasola/Sain Bagh reverse; Mathura/Purana Qila Road reorder; Idgah/Tis Hazari reverse | Preserving a bag of place names cannot detect or prevent these failures |
| Multiple routes and location count/attachment | 2783; 3746; 5110 | Two separate airport-bound routes become Moti Bagh → Munirka; Modi Mill flyover disappears from a list; Tis Hazari becomes “Thane to Hazari” | Endpoints, distinct clauses, count and ordering are corrupted |
| GPO fragmented | 4; 14 | `जी. पी. ओ.` becomes “Got … P.O.” | Proper-name segmentation and destination relation are lost |
| Chirag Delhi fragmented/substituted | 150; 1170; 5144 | “lamp … Delhi,” “Chirag traffic from Delhi,” or “Delhi Delhi” | Same original name has multiple incompatible transformed surfaces |
| Time confused with locations | 1780 | 5 pm–8 pm restrictions become vehicles “from Sector 8 and 5” | Numbers are attached to the wrong semantic class |
| Route status reversed | 4153 | Maharani Bagh → Sarai Kale Khan road **now reopened** becomes **now closed** | Not a toponym replacement, but reverses the interpretation of the affected route |
| No translation despite field name | 1012 | Hindi text retained after removing Traffic Alert | Spatial meaning is preserved; current English-only relation patterns still lack a validated input |
| Unresolved example | 11 | Bal Bhavan/Gurdwara/Mata Sunderi Mandor and a market “near which” | Attachment/name segmentation remains uncertain; kept unresolved rather than counted correct |
| Corrupted original and previous-row copy | **135–136** | Row 136 `text=#NAME?`; its translation exactly matches row 135; public source identifies ISBT → Shastri Park | Source-cell corruption plus local text alignment/copy contamination; not ordinary translation |
| Field spill | **2635** | `text` ends at Purana Qila; `geo=शेरशाह रोड`; `mentions=1/2"`; ID and URL empty | Evidence of an upstream quoting/import/export problem; no reconstruction performed |

These examples cover removal, addition, substitution, road identity/type loss, relation changes, directionality, count/order changes, and improper translation of names. They do not establish that every surface mismatch is a spatial error. For example, Marg→Road and Red Fort→Lal Quila can be legitimate identity-preserving transformations, while shortening Outer Ring Road to Ring Road cannot be presumed safe.

## Original public tweet verification

### Retrieval procedure

Direct web opens initially returned tool-level cache failures. A public official Twitter/X oEmbed request successfully returned the referenced tweet text. That endpoint was then queried for **every valid URL**, without logging in, using an API key, or querying a geocoder. The returned status ID was checked against the requested ID before accepting the text. Only the tweet paragraph was extracted from the embed HTML; author attribution and display controls were not concatenated into the tweet text.

There were **5,143 unique valid status URLs**, all containing an exact recoverable ID. The rounded numeric `id` column was never used to construct a tweet URL. Eight concurrent public requests were used with timeouts and a stop-on-rate-limit policy. Five transient connection/time-out failures succeeded on one retry. A preliminary Internet Archive index lookup for the Jail Road URL returned no snapshots; live official retrieval subsequently made archive recovery unnecessary. No deleted/private tweet was inferred or reconstructed.

Evidence timestamps span **2026-09-11 19:00:09 to 19:10:44 UTC**, equivalent to **12 September 2026, 00:30:09–00:40:44 IST**. They are the recorded request-start times for accepted/final attempts, not original tweet dates.

### Results

| Verification measure | Count |
| --- | ---: |
| Corpus records | 5,144 |
| Nonempty status URLs / unique exact IDs recoverable from URLs | **5,143 / 5,143** |
| Nonempty raw `id` fields | 5,143 |
| Full-precision IDs in raw `id` fields | **0** |
| Successfully retrieved and compared | **5,143** |
| Literal exact source/dataset-original text matches | **60** |
| Minor whitespace/punctuation differences | **5,080** |
| Link-rendering differences with otherwise matching tweet wording | **2** |
| Material source-to-dataset-original difference | **1** |
| No usable URL/ID (`URL_INVALID` in evidence ledger) | **1** |
| Final `RETRIEVAL_FAILED`, `NOT_PUBLICLY_ACCESSIBLE`, or `DELETED` | **0 each** |
| Possible spatial changes isolated to original → translated/edited field, with original verified | **242** |
| Directly inspected severe subset isolated to that transformation stage | **78** |

`TEXT_DIFFERENCE` remains the match status for the two URL-string differences and the material corrupt-original case. A separate `source_difference_class` distinguishes them. The initial strict comparison found five non-whitespace differences: rows 48, 136, 299, 453 and 2539. Inspection resolved row 48 as GPO/G.P.O. punctuation, row 2539 as misplaced quotation marks, rows 299/453 as displayed fb.me versus t.co link strings, and row 136 as material corruption. Link targets were not expanded and are not asserted to be identical; their surrounding spatial wording matches.

The one `URL_INVALID` row has a **missing** URL, not an attempted malformed public page. There is no claim that it is deleted. The public retrieval results verify the text returned by the official embed service on the retrieval date; they do not establish translation correctness, original collection timestamps, or the history of edits within the local dataset.

### The two initially observed examples

**Jail Road → Tilak Nagar, dataset row 2, status 549389894830030848.** The [official referenced tweet](https://x.com/dtptraffic/status/549389894830030848) says Jail Road towards Hari Nagar. The dataset original agrees after whitespace normalization. `translated_text` says Tilak Nagar towards Hari Nagar. This is **stage B: an undocumented substitution in the translated/edited field**, with stage A verified. Because the original is already English, it should not be called a demonstrated machine-translation error. There is no evidence of row misalignment for this record; the exact producing edit mechanism remains unknown. The stored address is Hari Nagar, which is actually mentioned, and does not explain the Jail/Tilak substitution.

**R.K. Puram / Keshav Puram, dataset row 3, status 548889847658975232.** The [official referenced tweet](https://x.com/dtptraffic/status/548889847658975232) says AIIMS towards R.K Puram. The dataset original agrees. The translated field retains R.K. Puram, adding a dot. Keshav Puram occurs in **stage D: pre-existing address metadata**, with associated legacy coordinates/bounds. This is not a translation substitution and there is no evidence of row misalignment here. Six input records—rows **3, 1552, 2116, 2469, 2606 and 3100**—mention R.K. Puram while carrying that Keshav Puram address, suggesting a repeated legacy-resolution problem rather than a one-off translated-name change. No fresh geocoding was used to test that hypothesis.

**A distinct alignment case, row 136, status 659764100164136960.** The [referenced source](https://x.com/dtptraffic/status/659764100164136960) reports traffic from ISBT towards Shastri Park. The dataset original contains `#NAME?`. Its `locations`, address and token metadata remain compatible with ISBT/Shastri Park, while its translated text exactly duplicates **row 135**, which reports Ashoka Road, Patel Chowk and Boota Singh roundabout. This supports **source-cell corruption plus local previous-row text contamination/alignment**, not a normal translation. Whether the copy occurred manually or through an import/fill operation is unknown.

### Stage attribution

| Stage | Finding | Consequence |
| --- | --- | --- |
| A. Public source → dataset original | 5,142 retrieved originals have no material wording discrepancy; 1 is materially corrupt; 1 unverified due to missing identifier | Retain originals and source evidence separately; quarantine exceptions |
| B. Dataset original → translated/edited field | 242 flagged possible spatial changes, including 78 inspected severe cases; 548 remain unresolved | Do not equate “translated field populated” with trustworthy parser text |
| C. Translated field → parser input | **0 additional string substitutions in the inspected call path**; all 5,144 current parser inputs equal the stored translated field | This is a static dataflow finding, not proof of correct entity recognition or semantic parsing |
| D. Unrelated pre-existing location metadata | Legacy fields populated in all rows; some conflict with actual mentions; four bbox fields feed fallback | Separate legacy evidence from newly resolved entities and prevent silent bbox promotion into a resolved route |

## Additional row and output provenance findings

`tweets_data.csv` is structurally parseable as **5,144 records × 1,716 columns**, with equal parsed width in every record. Equal width does not undo the already-spilled content in row 2635. `#NAME?` is a stored CSV string, not a formula calculated by this audit.

`routes_data.csv` has **5,150 parsed records**, not 5,144. Six records—output rows **2859, 3430, 4616, 4695, 4697 and 5028**—contain fragments of coordinate sequences in columns that should hold tweet metadata. These are not six additional tweets. The exact writing/editing process responsible is not supplied.

The remaining 5,144 output records match input records by their exact permalink, including a separately handled shared missing-URL record. For those matches there are **zero differences** in original text, translated text, address, lat/lon, all four bounding-box fields, and locations. This strongly argues against a general input-to-output row shift when joined correctly, but **positional row joins are unsafe after the first fragment**. Of matched tweet records, **5,050 have a nonempty `route_coordinates` value and 94 do not**; nonempty does not mean well-formed or correct geometry. This audit did not parse or regenerate routes.

The scientific-notation tweet IDs are an independent provenance defect: they collapse 5,143 available identifiers into 335 distinct strings. The exact URL IDs, not float-converted `id` values or CSV positions, should anchor verified joins. For the missing-ID record, preserve a dataset-record key based on source snapshot and source row; do not invent a tweet ID.

## Recommended canonical schema

Use a schema with immutable source evidence, explicit text derivations, separately preserved legacy metadata, and a versioned namespace for new geocoding. Do not flatten these into one ambiguous latitude/address/confidence record.

| Field | Definition / rule |
| --- | --- |
| `dataset_record_id` | Stable key from source snapshot/hash and source-row key; exists even if no tweet ID |
| `tweet_id` | Full exact decimal **string** extracted from verified status URL, otherwise null; never a floating-point number |
| `tweet_id_raw` | Original stored ID value, including rounded scientific notation, unchanged |
| `tweet_url` | Original supplied permalink; retain normalized/verified URL separately if needed |
| `source_file`, `source_sha256`, `source_row_key` | Immutable ingestion provenance |
| `text_original` | Exact dataset `text` value, never overwritten |
| `language_original` | Validated language or explicit unknown; retain `language_detected_legacy` separately |
| `text_from_verified_source` | Retrieved public-source wording, with source URL/time/match status; never silently replaces dataset original |
| `text_translated_legacy` | Exact current `translated_text`, including English edits and defects |
| `text_translated` | Future approved translation, nullable; separate from the legacy field and populated only by a documented transformation |
| `translation_method`, `translation_version` | Service/model/manual process and version; current values **unknown**, not guessed |
| `translation_timestamp`, `translation_review_status` | When produced and how approved; unknown where not supplied |
| `text_for_parser` | Explicitly selected derived input, with its source field/version and policy; no hidden overwrites |
| `parser_text_origin`, `normalization_version` | Original/verified-source/approved-translation selection and reversible normalization lineage |
| `toponyms_original` | Mention IDs, exact original-language surfaces and character spans; maintain repeats and order |
| `toponyms_parser` | Corresponding parser spans, original mention ID and transliteration/canonical alias; do not discard Hindi surface forms |
| `translation_alignment` | Explicit mapping between original mentions, translated spans and protected placeholders, plus uncertainties |
| `existing_location_metadata` | Nested untouched `osm_id`, address, locations, lat/lon, bbox, confidence, accuracy, their source-field names and unknown/known producer metadata |
| `source_verification` | Retrieval status/source/date, original-first comparison, translated comparison, and material-difference assessment |
| `data_quality_flags` | Corrupt cell, missing ID, field spill, name substitution, relation discrepancy, unresolved bilingual review, and other audit flags |
| `new_geocoder_output` | A separate versioned result: resolved mentions/candidates, semantic roles, selected coordinates, constraints, snap distances, route components, CRS, status and any newly defined scores |
| `geocoder_run_id`, `geocoder_version`, `input_text_sha256` | Identifies the exact code/configuration and text that generated a new result |

The **new geocoder must never overwrite** legacy `address`, `locations`, `lat`, `lon`, bounding boxes, confidence or original/legacy translated text. Its outputs belong only under `new_geocoder_output` or an independently keyed results table. Each output must join through `dataset_record_id` plus exact `tweet_id` where available. A fallback derived from legacy metadata must be explicitly labeled as a proxy and retain that provenance; it must not masquerade as a newly resolved intended route.

## Recommended parser text policy

Recommend **C: both original and translated text in parallel**, with an explicit canonical **`text_for_parser`** field, rather than unconditionally using either existing field.

- **English original:** derive `text_for_parser` from validated original text using only documented, spatially safe normalization. Keep place-name corrections as separate alias mappings with evidence. Do not use the present `translated_text` by default. Row 2 must not silently substitute Tilak Nagar for Jail Road.
- **Non-English original:** retain the original as the authority for mention identity, count, order, polarity and spatial relations. A future English parsing representation may translate the surrounding sentence while protecting each original toponym using stable mention placeholders or aligned spans. Store the original Hindi surface, transliteration and optional canonical alias separately. Compare role-bearing cues across both representations before accepting the result.
- **Untranslated Hindi in `translated_text`:** label it as untranslated; do not mistake a populated cell for an English parser-ready sentence.
- **Conflicts/corruption:** hold the record for adjudication. Verified public text is additional evidence, not permission to overwrite the original. Any future decision to use corrected source text must create a new documented derivative. Do not use the unrelated translated field as an automatic replacement for `#NAME?`.
- **Legacy metadata:** it may be inspected as fallible contextual evidence under an explicit policy, but must not define or rewrite the canonical text or original toponyms.

This policy preserves the original-language evidence while accommodating the current English-oriented parsing approach. It does not require a new route query to detect these upstream failures. Implementation should follow provenance adjudication, not precede it.

## Validation of this audit

The audit checked the full 5,144-record denominator, class totals, URL uniqueness, all current parser-input strings, source/translated comparisons, and input/output common fields. All public-source differences beyond whitespace were individually inspected. Representative bilingual discrepancies and equivalence controls were reviewed; all uncertain records retain explicit unresolved/possible status.

SHA-256 checks confirm that **all Data files, the notebook, both manuscript/review DOCX files, and the validation workbook remained unchanged** relative to the audit's recorded fingerprints. The new report and evidence files are the only task outputs. The existing code–manuscript audit was not rewritten; this report adds upstream provenance evidence that was outside its original four-file scope.

The strongest conclusions are the exact current input field, the independently verified Jail Road substitution, the separate R.K. Puram/Keshav Puram metadata problem, the previous-row copied translation, and the unsafe ID/positional-join conditions. The screen counts are reproducible prioritization evidence, while the remaining bilingual uncertainty is explicitly preserved for the next revision step.
