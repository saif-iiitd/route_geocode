# Supplementary Information: Translation Layer for the Hindi-Language Subset of the Tweet Corpus

Prepared 2026-09-13. Scope: the corpus's Hindi-original records that require translation before entering the spatial-classification pipeline. This document describes the deficiencies found in the legacy translation field, the systems evaluated as replacements, the validation methodology (an automated structural screen and a blind human preference ballot), and the current selection recommendation. It does not describe the geocoder, routing, or manuscript revisions, which are out of scope here.

## S1. Background and scope

The corpus contains 5,144 collected tweets. A prior full-corpus provenance audit classified every record by parser readiness:

| Status | Records |
| --- | ---: |
| Ready (English original) | 4,325 |
| Needs approved translation (intact Hindi original) | 815 |
| Language-label review required | 2 |
| Source repair required (corrupt cell) | 1 |
| Quarantined (source corruption) | 1 |
| **Total** | **5,144** |

The 815 intact Hindi-original records are the subject of this document. The existing pipeline reads a pre-supplied `translated_text` field for these records; the provenance audit found this field is not a faithful translation layer, prompting the work described below.

## S2. Deficiencies identified in the legacy translation field

A full-corpus comparison of each Hindi original against its pre-supplied `translated_text` classified every one of the 815 records into one of five mutually exclusive categories:

| Class | Records | Share | Meaning |
| --- | ---: | ---: | --- |
| Severe spatial discrepancy | 77 | 9.4% | Material name, constraint, or direction change; directly inspected |
| Possible toponym change | 104 | 12.8% | Screening or inspection flagged a possible place-name change, not already severe |
| Possible spatial-relation change | 57 | 7.0% | Screening or inspection flagged a possible relation change (from/to/via/near/between), not already flagged above |
| Unresolved cross-language comparison | 548 | 67.2% | Screen did not establish either a discrepancy or equivalence — **not a pass** |
| Benign textual difference | 29 | 3.6% | Conservative equivalence check or inspection found no spatial-meaning change |
| **Total** | **815** | **100%** | |

These counts are a screening result, not an exhaustive bilingual gold-standard error rate; the 548 unresolved records are an explicit limitation, not evidence of correctness.

Representative defect types found on direct bilingual inspection of the legacy translations, by category:

| Defect type | Example (legacy translation vs. actual meaning) |
| --- | --- |
| Place-name substitution | "Ice Cliff Chowk" for बारापुला (actual: Baraf Khana Chowk) |
| Literal (compositional) mistranslation of a proper name | "free market" for आज़ाद मार्किट (Azad Market); "round-the-clock" for पूसा गोल चक्कर (Pusa Gol Chakkar) |
| Road/feature-type identity loss | Sansad Marg rendered as "Parliament"; "Outer Ring Road" shortened to "Ring Road" |
| Spatial-relation loss or reinterpretation | "between X and Y" collapsed to an unstructured list; "near" reinterpreted as "at" |
| Directionality reversal | an origin/destination pair rendered in reverse order |
| Multiple-route or mention-count corruption | two distinct route clauses or a named-place list merged into one |
| Feature-semantics corruption | a junction/roundabout name transformed into a temporal expression |
| Source/data-integrity defects unrelated to translation | one record's translated field was an exact copy of the preceding row's translation, traced to a corrupted original cell (`#NAME?`) |

These are illustrative, directly-inspected instances, not an exhaustive per-type count across all 815 records.

## S3. Canonical input layer

Before any new translation was generated, a canonical parser-input layer was built (`src/text_provenance.py`, `src/parser_input.py`) that never overwrites the original tweet text, the legacy translation, or any pre-existing geocoding metadata (address, coordinates, bounding box, confidence). It exposes the legacy translation as `text_translated_legacy`, explicitly not canonical, and gates every Hindi-original record behind `parser_status = NEEDS_APPROVED_TRANSLATION` pending a decision. This document reports on the work done to reach that decision.

## S4. Translation candidate generation

### S4.1 Systems evaluated

| System | Model / method | Outcome |
| --- | --- | --- |
| **IndicTrans2** | `ai4bharat/indictrans2-indic-en-1B`, pinned revision `ac3daf0ecd37be3b6957764a9179ab2b07fa9d6a` | 815/815 candidates generated; reported below |
| **ChatGPT (manual)** | Blind paste-into-a-new-chat protocol, no API | 815/815 candidates generated; reported below |
| Hugging Face free tier | `meta-llama/Llama-3.1-8B-Instruct`, auto-routed Inference Providers | Abandoned: persistent free-tier request failures (10–45% of a 20-record smoke sample per attempt across four attempts), inconsistent with a usable production arm |
| Ollama (local) — `gemma4:e4b` | 8B, CPU inference (no GPU present on the evaluation host) | Abandoned: ≈276 s/record measured, implying ≈50–60 h for all 815 records |
| Ollama (local) — `qwen2.5:3b-instruct` | 3B, CPU inference | Abandoned: ≈57 s/record (≈13 h total) but materially weaker output on inspection (a named road dropped entirely from one translation; numeric and status tokens misclassified as place mentions) |
| Google Cloud Translation Advanced v3 | `general/nmt` | Not run: no Application Default Credentials configured on the evaluation host |
| OpenAI (`gpt-5.6-sol`) | Responses API, structured JSON schema output | Not run: no API key configured |

All systems shared one blinding protocol: each translation request received only four fields (a stable record identifier, the exact tweet ID, its public URL, and the original Hindi text) and a generic rule set with no corpus-specific examples or corrected answers, so no system's translation was informed by this project's own audit findings.

### S4.2 IndicTrans2 configuration

| Parameter | Value |
| --- | --- |
| Model / revision | `ai4bharat/indictrans2-indic-en-1B` @ `ac3daf0ecd37be3b6957764a9179ab2b07fa9d6a` |
| Device | CPU (float32, eager attention) |
| Decoding | Beam search, 5 beams, no sampling |
| Source / output token limits | 256 / 256 |
| Seed | 20260912 |
| `transformers` version | 4.40.2 (downgraded from a newer default; see below) |
| `IndicTransToolkit` version | 1.1.1 |

The pinned model's custom (`trust_remote_code`) inference code assumes an older key-value cache representation. Under a current `transformers` release, the first decoding step failed with `AttributeError: 'NoneType' object has no attribute 'shape'`, because the newer release always passes an initialized cache object rather than `None`. `transformers` was pinned to 4.40.2 — new enough to have a prebuilt `tokenizers` wheel for the evaluation host's Python version, old enough to predate this cache-representation change — which resolved the fault without modifying the model's own code.

Full-run outcome: **815/815 candidates generated, 0 failures**, mean 21.5 s/record (≈4.9 h total).

### S4.3 ChatGPT (manual) protocol

No ChatGPT API key was available, so candidates were produced by pasting each of 14 batches (≤60 records each) of the same blind four-field records, plus the same generic rule set, into a **new** ChatGPT chat with no prior conversation history — reproducing the blinding an API call would have provided, without an API. Replies were required to return one JSON object per record, validated against the same structural schema used for the automated arms (exact mention alignment to the original text, consecutive mention ordering, and reference-only relation fields); a reply that failed this validation was recorded as a failure rather than repaired.

Full-run outcome: **815/815 candidates generated, 0 failures** after one ingestion-tooling defect was fixed (an internal validation bug that initially rejected every reply; corrected and re-validated).

## S5. Automated structural validation

Every candidate translation, from every system, was passed through the same conservative screen (`src/translation_bakeoff/validate.py`), independent of which system produced it. The screen checks, by regex cue comparison against the Hindi original: preserved spatial relations (via/near/between/under/towards), feature-type terms (road/marg/chowk/flyover/underpass/bridge/police station/carriageway), traffic-status terms (open/closed/normal/jam/diverted/restricted), negation, and digit/time-token preservation; it also flags any residual untranslated Devanagari script in the output. For systems that return a self-reported structured breakdown of their own translation (ChatGPT), an additional internal-consistency check verifies the translation text actually contains the mentions the system itself claims to have produced.

**This is a conservative structural screen, not a semantic-accuracy or gold-standard measurement.** A clean screen does not certify a translation correct, and a flag does not certify it wrong; cross-script place identity, added or dropped mentions, mention reordering, and route-clause equivalence still require bilingual adjudication.

| Metric (of 815 successful candidates) | IndicTrans2 | ChatGPT (manual) |
| --- | ---: | ---: |
| Self-alignment structural mismatch | 0.0% | 6.9% |
| Numeric/time token possible discrepancy | 17.8% | 4.8% |
| Spatial-relation cue possible discrepancy | 9.6% | 1.0% |
| Feature-type cue possible discrepancy | 9.7% | 4.5% |
| Traffic-status cue possible discrepancy | 5.6% | 4.5% |
| Residual untranslated Devanagari | 27 records | 0 records |
| Coverage of the 77 known-severe legacy-failure cases | 77/77 | 77/77 |

The structural-mismatch row is not directly comparable between systems: IndicTrans2 reports no internal structure to be inconsistent with, so 0.0% reflects non-applicability rather than a stronger result.

A systematic IndicTrans2-specific defect was identified during this screening and is not previously documented: Devanagari **nukta**-marked letters (ख़, ड़, ज़, फ़ — used for Persian/Arabic-derived sounds, e.g. ख़राब, "damaged") are transliterated as literal escape-like tokens (for example `Kh़` or `093C`) rather than being rendered correctly. Confirmed present in **40/815 (4.9%)** of IndicTrans2 candidates by direct string search.

## S6. Blind human preference ballot

Because the automated screen cannot establish which translation is more accurate — only which is more internally consistent with surface cues — a second, independent evaluation was run: a blind pairwise human preference ballot.

**Sampling.** 25 records were drawn, 5 from each of the five discrepancy classes in Section S2 (deterministic seeded selection, `seed = 20260913`), restricted to records where both systems produced a successful candidate.

**Procedure.** For each of the 25 records, both candidate translations were displayed in a randomized left/right position (independently seeded per record) with no system label. The rater selected the translation they judged better, with no way to see which system produced either option. System identity was revealed only after all 25 records had been rated.

**Result.**

| Category | ChatGPT preferred | IndicTrans2 preferred |
| --- | ---: | ---: |
| Possible toponym change | 5/5 | 0/5 |
| Unresolved (needs review) | 4/5 | 1/5 |
| Severe spatial discrepancy | 4/5 | 1/5 |
| Possible spatial-relation change | 4/5 | 1/5 |
| Benign / likely fine | 4/5 | 1/5 |
| **Overall** | **21/25 (84%)** | **4/25 (16%)** |

ChatGPT was preferred in every category, most decisively on toponym-change cases — consistent with the automated screen's higher feature-type/toponym cue-discrepancy rate for IndicTrans2 in Section S5. This is one rater's blind judgment on 25 of 815 records (3.1%); it is directional evidence, not a substitute for independent bilingual adjudication at scale.

## S7. Candidate selection

Based on the combined evidence in Sections S5–S6 — lower cue-discrepancy rates on every measured dimension, no residual untranslated source text, and a consistent blind human preference across every discrepancy category — **the ChatGPT-manual candidate translations are recommended as the working translation for this corpus's 815 Hindi-original records**, ahead of IndicTrans2, subject to the limitations below.

This recommendation is **not** a claim of validated accuracy, and it does not constitute approval for production use under this project's own evidentiary standard (Section S3). Specifically outstanding before that standard is met:

1. Independent bilingual adjudication of at minimum the 77 known-severe cases, and a representative sample of the 548 currently unresolved records.
2. A documented, dated approval decision populating `text_translated_approved` and `translation_review_status` in the canonical schema (Section S3), rather than treating this recommendation as a substitute for that record.
3. Integration of the approved translation into the actual geocoding pipeline's input path — at the time of writing, the geocoder notebook still reads the legacy `translated_text` field directly, and the canonical/candidate layers described here exist alongside it, not in place of it.

## S8. Reproducibility

| Artifact | Path |
| --- | --- |
| Full-corpus provenance audit | `docs/text_translation_provenance_audit.md` |
| Canonical input layer / translation queue | `src/parser_input.py`, `src/text_provenance.py`, `results/canonical_parser_input.csv`, `results/translation_work_queue.csv` |
| Bake-off harness (automated arms) | `src/translation_bakeoff/adapters.py`, `generate.py`, `validate.py`, `evaluate.py` |
| ChatGPT manual-arm tooling | `src/translation_bakeoff/chatgpt_manual.py` |
| IndicTrans2 frozen run | `experiments/spatial_translation_bakeoff/runs/indictrans2/20260912_blind_v5/` |
| ChatGPT-manual candidates and screen | `experiments/spatial_translation_bakeoff/chatgpt_manual/` |
| Cross-system comparison report | `experiments/spatial_translation_bakeoff/reports/indictrans2_vs_chatgpt_manual_comparison.md` |
| Human ballot raw results | `experiments/spatial_translation_bakeoff/reports/blind_ballot_results.json`, `..._per_tweet.csv` |
| Final joined per-record dataset (all candidates, screens, and ballot outcomes) | `results/translation_bakeoff_final_dataset.csv`, field reference in `results/translation_bakeoff_final_dataset_fields.md` |

No source file, legacy translation, geocoder, routing code, or manuscript text was modified in the course of this work.
