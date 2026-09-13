# Blind spatial-translation bake-off: 20260912_blind_v5

## Outcome

Completed blind-input preparation, three-arm preflight/smoke execution, immutable full-run status ledgers, candidate freeze and post-freeze audit reveal. **815 translations were generated.** A status ledger with 815 entries is not a completed translation arm. Unavailable providers were not substituted. No translation was fabricated, rewritten, or promoted to production.

The same 20 IDs, selected by seeded SHA-256 rank without labels, were assigned to every smoke arm. See `runs/20260912_blind_v5/smoke_report.json`. Blocked smoke gates are not successful API integration tests. The configuration is frozen for reproducibility of this blocked attempt; service integration must still pass a new smoke run after setup.

## System comparison

| System | Scheduled | Attempted translations | Successful | Missing/blocked |
| --- | ---: | ---: | ---: | ---: |
| indictrans2 | 815 | 815 | 815 | 0 |
| google | 815 | 0 | 0 | 815 |
| openai | 815 | 0 | 0 | 815 |
| ollama | 815 | 0 | 0 | 815 |

## Exact blockers

- google: GOOGLE_CLOUD_TRANSLATE_LIBRARY_NOT_INSTALLED; GOOGLE_CLOUD_PROJECT_NOT_CONFIGURED; GOOGLE_ADC_NOT_CONFIGURED_ON_THIS_LOCAL_HOST
- indictrans2: No preflight blocker; inspect request outcomes
- ollama: HOST_NOT_CONFIGURED
- openai: OPENAI_API_KEY_NOT_CONFIGURED

## Findings and limits

Quality rates and severe-failure repair rates are NA when unmeasured, not zero-error claims. The 77 severe Hindi cases each have a regression row per system, marked uncertain/requires review where there is no candidate or independent adjudication. The 548 unresolved legacy cases are not counted as translation failures. Legacy subsets reconcile to 77 + 104 + 57 + 548 + 29 = 815; they are not exhaustive new gold labels or a representative prevalence estimate.

The representative table contains 20 post-reveal selections covering documented failure families. Empty candidate columns explicitly mean unavailable generation. No cross-system disagreements or successes can be inferred from empty cells. These are review cases, not evidence of comparative quality.

Validation uses transparent Hindi/English cue screens for selected relations, features, numeric/time tokens, negation, status and residual Devanagari. Cue mismatch means possible discrepancy. Cross-script place identity, added/missing places, mention ordering, reversals and route-clause equivalence require independent bilingual review. Self-reported structured alignment (OpenAI, Hugging Face) is not gold; it only tests a candidate against its own claimed mentions. No record receives AUTO_VALIDATED solely because heuristic checks are quiet. Incomplete audit toponym hints are joined only as QA evidence after freezing and are never treated as exhaustive annotations.

## Recommendations

1. No default translator can be selected without successful candidates and comparative adjudication.
2. Conventional MT followed by deterministic screening and blinded LLM/human adjudication is a hypothesis to test, not a demonstrated superior workflow.
3. No Hindi record is safe to approve automatically from this run.
4. All 815 remain pending translation and review; prioritize the 77 severe regression cases once candidates exist, without treating them as prevalence evidence.
5. Before canonical integration, obtain genuine outputs, independent bilingual span/relation/status annotations, repeated-mention and multi-clause tests, reviewer agreement, precision estimates for any approval gate, and held-out evaluation. Repeat technical smoke checks with actual credentials and pin the installed environment.

## Reproducibility

Blind input SHA-256: `8d8f5fcab9e03c6a1dfc90d5a2bfc7a3f92959df7f202b8e9bd65a169f2d9337`. Source commit: `62160b09b5d7dafee5e8d72912c9bda3cdb9d904`; working tree was dirty from the prior authorized task. The run snapshots generator source, schema, resolved configuration, prompt and library/Python versions. `freeze.json` hashes every frozen run artifact, including candidate CSVs and the OpenAI/Hugging Face alignment JSONL files. Per-row output_sha256 hashes the UTF-8 translation, not the containing CSV. Missing outputs have empty output hashes. Timestamps are UTC; no timestamps are invented for unattempted generation.

Protected source/audit/canonical/queue hashes matched preparation at reveal. Python generation denies reads from repository data/docs/results directories; adapters receive only the four-field blind record and cannot request tools. This enforces input/pipeline blinding, not personnel blinding: the implementing assistant had prior audit context. The prompt contains generic fidelity rules, no corpus-specific corrected examples. Evaluation output never flows back into generation. Repeating serialization is deterministic; external service model outputs are not guaranteed deterministic. IndicTrans2 fixes revision/seed/beam decoding but hardware/library reproducibility still matters.

No API translation requests occurred where credentials failed preflight, so incurred API cost for those arms is zero. Costs for any actual requests require usage/billing evidence. No unsupported model substitutions, implicit retries or auto-approval occurred. Production input, semantic parser, geocoder, route outputs and manuscript remain unchanged.

See the experiment README for exact setup, official implementation references and rerun commands. After credentials/setup, use a **new run ID**. Never overwrite the frozen run or tune its prompt using revealed examples. Root candidate/report CSVs are first-run discovery copies; versioned directories are authoritative.
