# IndicTrans2 vs. ChatGPT-manual: side-by-side screen comparison

Generated 2026-09-13, comparing `runs/indictrans2/20260912_blind_v5/candidates.csv`
(the frozen harness run) against `chatgpt_manual/candidates.csv` (the manual
paste-into-a-fresh-chat arm), both screened with the harness's own `validate.py`
over the identical 815-record blind Hindi corpus.

**These are conservative structural/cue screens, not gold semantic accuracy.** A
clean screen does not mean a translation is correct; a flag does not mean it is
wrong. Cross-script place identity, added/missing places, mention ordering,
reversals and route-clause equivalence still require independent bilingual
adjudication, exactly as the rest of this experiment's caveats state.

| Metric | IndicTrans2 | ChatGPT-manual | Note |
| --- | ---: | ---: | --- |
| Successful candidates | 815/815 | 815/815 | Both complete, no generation failures |
| `STRUCTURAL_MISMATCH` (self-alignment contradicts own translation) | 0 (0.0%) | 56 (6.9%) | Not directly comparable: IndicTrans2 reports no structure to be self-inconsistent with, so 0% here is a structural non-applicability, not evidence of higher quality |
| Numeric/time cue possible-discrepancy | 145 (17.8%) | 39 (4.8%) | IndicTrans2 notably higher |
| Relation-loss cue (via/near/between/under/towards) | 78 (9.6%) | 8 (1.0%) | IndicTrans2 notably higher |
| Feature-type cue (road/marg/chowk/flyover/etc.) | 79 (9.7%) | 37 (4.5%) | IndicTrans2 higher |
| Traffic-status cue (open/closed/normal/jam/etc.) | 46 (5.6%) | 37 (4.5%) | Comparable |
| Residual Devanagari left in output | 27 | 0 | IndicTrans2-specific |
| Known-severe legacy cases (of 77) with a candidate | 77/77 | 77/77 | Both cover the full severe subset |

## IndicTrans2-specific defect found this session

A **systematic transliteration bug**: Devanagari nukta letters (ख़, ड़, ज़, फ़ — used
for Persian/Arabic-origin sounds, e.g. ख़राब/"kharab"="damaged") leak into the English
output as literal garbage tokens like `Kh़` or `093C` instead of being
transliterated. Confirmed present in **40/815 (4.9%)** of IndicTrans2 candidates by
direct string search. This is independent of (and partially overlapping with) the
numeric/time and residual-Devanagari flags above, and was not previously documented
anywhere in this project.

## Qualitative spot checks (both fix real legacy errors)

Both arms independently corrected known severe legacy-translation failures, e.g.:

- Legacy "free market" → both correctly render "Azad Market"
- Legacy "Ice Cliff Chowk" (ChatGPT) / no direct IndicTrans2 match checked → "Baraf Khana Chowk"
- Legacy "Delhi Delhi to Kalkaji" → IndicTrans2 correctly resolves "Chirag Delhi towards Kalkaji"
- Legacy "Bhairon Progress on the Road Traffic Ground No. 2" → IndicTrans2 correctly resolves "Bhairon Marg...Pragati Maidan Gate No. 2"

## Human blind preference ballot (2026-09-13)

Beyond the automated screen above, a human rater judged 25 records blind — same
sample, 5 per audit category, translations shown in randomized order with no system
label, then revealed only after all 25 were rated. Full per-item data:
`blind_ballot_results.json` / `blind_ballot_results_per_tweet.csv` (this folder).

| Category | ChatGPT picked | IndicTrans2 picked |
| --- | ---: | ---: |
| Possible toponym change | 5 | 0 |
| Unresolved (needs review) | 4 | 1 |
| Severe spatial discrepancy | 4 | 1 |
| Possible spatial-relation change | 4 | 1 |
| Benign / likely fine | 4 | 1 |
| **Total** | **21/25 (84%)** | **4/25 (16%)** |

ChatGPT was preferred in every category, most decisively on toponym-change cases
(5/5) — consistent with the automated screen's finding that IndicTrans2 has a higher
feature-type/toponym cue-discrepancy rate. This is one rater's blind judgment on 25
records, not a substitute for the independent bilingual adjudication this project's
audits have consistently required, but it is a real, methodologically blind (not
merely automated-heuristic) signal, and it points the same direction as the
automated screen above.

## What this does and does not establish

This shows both arms are large, real improvements over the legacy machine
translation on the known-severe subset, and gives a first quantitative read on
relative cue-discrepancy rates. It does **not** establish which arm is more accurate
overall — that requires the same independent bilingual adjudication this project's
audits have consistently required before any translator is approved for production
use. Google and OpenAI remain blocked (no ADC credential / no API key) in this same
frozen run; Ollama's model choice remains undecided.
