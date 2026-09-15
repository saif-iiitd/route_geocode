# Experiment 03: Candidate-based entity resolution (step 3)

Date: 2026-09-15. Follows experiments 01 and 02. Scope unchanged: `READY_ORIGINAL_EN`
records only. No external geocoder calls made or required.

## Motivation

Handoff (`handoffs/chatgpt_handoff_2026-09-12.md`), "Entity resolution" section:

> Each place is resolved independently. The code generally accepts the first
> acceptable OpenCage result within broad Delhi bounds. It does not implement the
> manuscript's implied contextual confidence/ranking logic. No joint
> disambiguation across co-mentioned places. Alias handling is weak.

The notebook (cell 17, `extract_point_route`) calls `geocoder.geocode(place,
proximity=delhi_center)` and accepts the first result within Delhi bounds, for
every recognized mention, with no local check on whether the mention text is
even resolvable in principle. This experiment builds and empirically audits the
piece of "candidate-based resolution" answerable from data already in the repo,
*before* any external geocoder is involved: given a recognized mention, what
local evidence exists that it names one specific place rather than a feature
type or nothing recognizable at all?

This repository has no OpenCage (or other geocoder) API key in `secrets/`, so
live geocoding candidate-ranking is out of scope for this round and is not
claimed to be solved. What is testable locally is mention-to-gazetteer
canonicalization, which the notebook does not do explicitly (the gazetteer is
only used to seed NER, never consulted again downstream).

## Method

`src/entity_resolution.py` classifies each recognized mention (spans produced
by the same NER pipeline as experiment 02: `en_core_web_sm` + `EntityRuler` +
`PhraseMatcher`, both built from `Data/tweet_location_terms.txt`) into one of
three candidate-resolution statuses, using only the gazetteer file — no
geocoding, no coordinates, no invented disambiguation:

| Status | Meaning |
| --- | --- |
| `GAZETTEER_RESOLVED` | Exact (case-insensitive) match to a specific gazetteer entry. |
| `GAZETTEER_GENERIC_AMBIGUOUS` | Matches a gazetteer entry, but that entry is a bare feature-type noun (e.g. "Flyover", "Temple") shared by many real places — cannot be resolved to one place from text alone. |
| `OUT_OF_GAZETTEER_UNRESOLVED` | Recognized only by spaCy's base NER, not present in the gazetteer at all. No local evidence either way. |

`GENERIC_SINGLE_WORD_TERMS` was found by manually reviewing the 250 single-word
entries in the 1,014-term gazetteer for common generic nouns, not inferred
automatically: `Boulevard`, `Flyover`, `Garden`, `Mandi`, `Temple`, `Underpass`.

`experiments/03_entity_resolution_audit.py` reruns the audit against the exact
same seeded 150-record sample as experiment 02 (`seed=20260913`), and for every
entity span that survives spaCy's `filter_spans` overlap resolution, records
which pipeline component produced it (gazetteer `EntityRuler`/`PhraseMatcher`
vs. base spaCy NER) before classifying it. Full results:
`experiments/03_entity_resolution_audit.json`.

## Findings

408 entity spans survived across the 150-record sample.

| Status | Count | % |
| --- | ---: | ---: |
| `GAZETTEER_RESOLVED` | 308 | 75.5% |
| `OUT_OF_GAZETTEER_UNRESOLVED` | 83 | 20.3% |
| `GAZETTEER_GENERIC_AMBIGUOUS` | 17 | 4.2% |

Pipeline source of each span:

| Source | Count | % |
| --- | ---: | ---: |
| Gazetteer `EntityRuler`/`PhraseMatcher` | 325 | 79.7% |
| Base spaCy NER only | 83 | 20.3% |

The `GAZETTEER_RESOLVED` and `GAZETTEER_MATCHER`-source counts differ (308 vs.
325) because 17 gazetteer-matched spans are the generic-term entries pulled out
into their own bucket.

### `GAZETTEER_GENERIC_AMBIGUOUS` examples (real, from the sample)

- `"flyover"` in *"...near Peeragarhi flyover."* and *"...on Punjabi Bagh
  flyover."* — two different flyovers, same bare noun.
- `"Flyover"` in *"Water logging reported under Manglapuri Flyover..."*
- `"Mandi"` in *"Water logging in front of Azadpur Mandi."* — here the fuller
  span `"Azadpur Mandi"` is what actually survives `filter_spans` (the specific,
  resolvable multi-word match correctly wins over the bare generic one), but the
  bare term is still tested directly in `tests/test_entity_resolution.py` to
  prove the classifier does not silently resolve it if it ever appears alone.

### `OUT_OF_GAZETTEER_UNRESOLVED` examples, and a real complication found

Two genuinely different situations land in this one bucket, and the audit
surfaced both:

1. **Real places missing from the gazetteer** — `"Andheria Mor"`, `"Subhash
   Place Depot"`, `"Shadi Pur DMS"` are real, specific Delhi locations that
   spaCy's base NER correctly flagged as entities, but that do not appear in
   `Data/tweet_location_terms.txt`. These are genuine gazetteer-coverage gaps
   (relevant to step 4, the gazetteer/alias layer).
2. **NER noise that is not a place at all** — `"DC"` (from *"DC office Nand
   Nagri"*) and `"DTC"` (from *"a DTC bus near Masoodpur"*) are organization
   acronyms that `en_core_web_sm` mistagged as location-like entities. These are
   not missing gazetteer entries; they are false positives from the upstream
   NER step (a known limitation carried over from experiment 02, not something
   this experiment fixes).

Both cases are left as `OUT_OF_GAZETTEER_UNRESOLVED` by design: this module
makes no claim to distinguish "real place we haven't catalogued" from "not a
place." Collapsing them into one honest "no local evidence" status is correct
for this step; splitting them further would require either a curated
non-place stoplist (not built) or an external knowledge source (not available),
and guessing would violate the project's no-fabrication principle.

## Tests

`tests/test_entity_resolution.py`, 8 tests, all using real corpus mentions found
by this audit as fixtures (not invented examples): exact-match resolution,
case-insensitivity, generic-term flagging (`flyover`, `Flyover`, `Mandi`),
out-of-gazetteer mentions for both a real missing place (`Andheria Mor`) and
NER noise (`DC`), and a check that every result carries a human-readable reason.

Full suite: **48/48 passing** (8 new here, 40 unchanged from before).

## Design decision

This module is deliberately conservative: it adds a classification layer with
no coordinates and no attempt at candidate ranking, disambiguation, or alias
matching. Those are explicitly out of scope here and belong to step 4 (gazetteer
build-out) and the eventual geocoder-candidate-ranking work the handoff flags as
missing. What this experiment establishes is the *evidence class* every mention
should carry before it reaches a geocoder, so that step 4 and the eventual
geocoder integration have a principled input rather than a flat list of strings.

## Known limitations (still open, explicit)

- No external geocoder is called or available in this environment (no OpenCage
  key in `secrets/`). "Candidate ranking" in the full sense the handoff
  describes — multiple geocoder results scored and disambiguated — is not
  implemented and cannot be validated without API access. This experiment only
  prepares clean local input for that later step.
- `GENERIC_SINGLE_WORD_TERMS` was curated by manual review of the 250
  single-word gazetteer entries, not derived from an automated check. It may be
  incomplete; only the six confirmed by inspection are included.
- `OUT_OF_GAZETTEER_UNRESOLVED` deliberately does not distinguish "real,
  uncatalogued place" from "NER noise, not a place." Splitting these would need
  new evidence (a stoplist or a second data source), not implemented this round.
- Audited on the same 150 of 4,325 `READY_ORIGINAL_EN` records as experiment 02.
  A full-corpus pass has not been run.

## Decision: **KEEP**

Evidenced by a real audit on the same seeded sample used in experiment 02 (not
assumed), makes no geocoding claim beyond what local data supports, and both
real complications found (generic terms, and the two distinct causes behind
"out of gazetteer") are documented rather than silently resolved.

## Reviewer-response link

Same as experiments 01 and 02 (R2.4, R2.3, R1.4) — continues hardening the
entity/role-assignment pipeline steps 1-2 feed into, ahead of geocoder
integration (step 3 proper) and the gazetteer/alias layer (step 4).
