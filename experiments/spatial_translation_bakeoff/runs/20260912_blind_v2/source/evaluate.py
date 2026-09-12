"""Post-freeze-only audit reveal, conservative regression tables and reports."""
import argparse
import json
from collections import Counter
from pathlib import Path
from .common import (ROOT, EXPERIMENT, SYSTEMS, STRUCTURED_SYSTEMS, verify_freeze, file_sha, read_csv,
                     load_blind, write_csv_once, write_json_once, write_text_once, dumps, now)
from .validate import screen

EXPECTED_SUBSETS = {'SEVERE_SPATIAL_DISCREPANCY': 77, 'POSSIBLE_TOPONYM_CHANGE': 104,
                    'POSSIBLE_SPATIAL_RELATION_CHANGE': 57, 'UNRESOLVED_CROSS_LANGUAGE': 548,
                    'BENIGN_TEXTUAL_DIFFERENCE': 29}


def protected_integrity(root, experiment):
    manifest = json.loads((experiment / 'preparation_manifest.json').read_text(encoding='utf-8'))
    mismatches = [p for p, h in manifest['protected_files'].items() if file_sha(root / p) != h]
    if mismatches:
        raise ValueError('Protected source changed: ' + ','.join(mismatches))
    return manifest


def join_audit(blind, audit):
    by_id = {}
    for row in audit:
        if row['tweet_id']:
            if row['tweet_id'] in by_id:
                raise ValueError('Duplicate exact audit tweet ID')
            by_id[row['tweet_id']] = row
    joined = {}
    for record in blind:
        row = by_id[record['tweet_id']]
        if row['text_original'] != record['text_original'] or row['tweet_url'] != record['tweet_url'] or row['language_recorded'] != 'hi':
            raise ValueError('Audit reveal identity/text mismatch')
        joined[record['dataset_record_id']] = row
    counts = dict(Counter(r['audit_class'] for r in joined.values()))
    if counts != EXPECTED_SUBSETS:
        raise ValueError('Audit subset reconciliation failed: ' + str(counts))
    return joined


def representative_ids(blind, audit, candidates):
    """Post-evaluation coverage selection. No selected examples enter generation."""
    families = {
        'proper_names': ('NAME', 'TOPONYM', 'PLACE', 'LITERAL'),
        'directionality': ('DIRECTION', 'REVERS', 'ORIGIN', 'DESTINATION'),
        'via': ('VIA', 'WAYPOINT'), 'near': ('NEAR', 'PROXIMITY'),
        'between': ('BETWEEN',), 'multi_route': ('MULTI', 'CLAUSE'),
        'feature_type': ('FEATURE', 'ROAD'), 'time_numeric': ('TIME', 'NUMBER', 'NUMERIC'),
        'route_status': ('STATUS', 'POLARITY', 'NEGATION'),
    }
    chosen = {}
    for family, cues in families.items():
        matches = [r for r in blind if any(cue in (audit[r['dataset_record_id']]['discrepancy_tags'] + ' ' +
                   audit[r['dataset_record_id']]['review_note']).upper() for cue in cues)]
        for record in matches[:2]:
            chosen.setdefault(record['dataset_record_id'], []).append(family)
    for record in blind:
        key = record['dataset_record_id']
        outputs = {candidates[s][key]['generated_translation'] for s in SYSTEMS
                   if candidates[s][key]['generation_status'] == 'SUCCESS'}
        if len(outputs) > 1:
            chosen.setdefault(key, []).append('systems_disagree_not_error_proof')
            break
    for record in sorted(blind, key=lambda r: (audit[r['dataset_record_id']]['audit_class'] != 'SEVERE_SPATIAL_DISCREPANCY', r['dataset_record_id'])):
        if len(chosen) >= 20:
            break
        chosen.setdefault(record['dataset_record_id'], ['coverage_fill'])
    return chosen


def evaluate(run_id, root=ROOT, experiment=EXPERIMENT):
    root, experiment = Path(root), Path(experiment)
    frozen = verify_freeze(experiment, run_id)  # Must succeed before audit file is opened.
    manifest = protected_integrity(root, experiment)
    blind = load_blind(experiment / 'blind_translation_input.csv')
    candidates = {}
    for system in SYSTEMS:
        rows = read_csv(experiment / 'runs' / system / run_id / 'candidates.csv')
        index = {r['dataset_record_id']: r for r in rows}
        if len(rows) != 815 or set(index) != {r['dataset_record_id'] for r in blind}:
            raise ValueError('Frozen candidate coverage mismatch')
        for record in blind:
            candidate = index[record['dataset_record_id']]
            if candidate['tweet_id'] != record['tweet_id'] or candidate['input_sha256'] != frozen['input_sha256']:
                raise ValueError('Frozen candidate identity/input mismatch')
        candidates[system] = index
    audit = join_audit(blind, read_csv(root / 'results/translation_discrepancies.csv'))
    alignments = {}
    for system in STRUCTURED_SYSTEMS:
        alignment_path = experiment / 'runs' / system / run_id / 'alignment.jsonl'
        by_record = {}
        for line in alignment_path.read_text(encoding='utf-8').splitlines():
            item = json.loads(line)
            if item['dataset_record_id'] in by_record:
                raise ValueError('Duplicate ' + system + ' alignment identity')
            by_record[item['dataset_record_id']] = item['alignment']
        if set(by_record) != {r['dataset_record_id'] for r in blind}:
            raise ValueError(system + ' alignment coverage mismatch')
        alignments[system] = by_record
    validation, regression, metrics, subsets = [], [], [], []
    for system in SYSTEMS:
        system_validation = []
        for record in blind:
            key = record['dataset_record_id']
            candidate, evidence = candidates[system][key], audit[key]
            result = screen(record['text_original'], candidate, alignments[system][key] if system in STRUCTURED_SYSTEMS else None)
            result['flags'] = dumps(result['flags'])
            row = {'dataset_record_id': key, 'tweet_id': record['tweet_id'], 'system': system,
                   'run_id': run_id, 'generation_status': candidate['generation_status'],
                   **result, 'legacy_audit_class': evidence['audit_class'],
                   'known_original_toponyms_audit_hints': evidence['known_original_toponyms'],
                   'audit_hints_exhaustive': False}
            validation.append(row)
            system_validation.append(row)
            if evidence['audit_class'] == 'SEVERE_SPATIAL_DISCREPANCY':
                regression.append({'dataset_record_id': key, 'tweet_id': record['tweet_id'], 'system': system,
                    'run_id': run_id, 'original_hindi': record['text_original'],
                    'legacy_translation': evidence['text_translated'],
                    'candidate': candidate['generated_translation'], 'failure_family': evidence['discrepancy_tags'],
                    'documented_legacy_failure': evidence['review_note'],
                    'regression_outcome': 'UNCERTAIN_REQUIRES_REVIEW',
                    'reason': 'NO_CANDIDATE_GENERATION_BLOCKED' if candidate['generation_status'] != 'SUCCESS' else
                              'INDEPENDENT_BILINGUAL_ADJUDICATION_REQUIRED',
                    'validation_flags': result['flags']})
        outputs = list(candidates[system].values())
        successes = [r for r in outputs if r['generation_status'] == 'SUCCESS']
        attempted = [r for r in outputs if r['attempted'] == 'True']
        elapsed = [float(r['runtime_seconds']) for r in attempted if r['runtime_seconds']]
        count = len(successes)
        metrics.append({'system': system, 'run_id': run_id, 'records_scheduled': 815,
            'records_attempted': len(attempted), 'records_successfully_translated': count,
            'blocked_or_failed': 815 - count, 'automatically_validated_pct': 0 if count else 'NA',
            'review_required_pct': 100 if count else 'NA',
            'structural_mismatch_pct': round(100 * sum(v['validation_state'] == 'STRUCTURAL_MISMATCH' for v in system_validation) / count, 3) if count else 'NA',
            'place_drop_rate': 'NA', 'place_addition_rate': 'NA', 'mention_order_discrepancy_rate': 'NA',
            'direction_reversal_rate': 'NA', 'relation_loss_rate': 'NA', 'feature_type_discrepancy_rate': 'NA',
            'numeric_time_discrepancy_rate': 'NA', 'traffic_status_discrepancy_rate': 'NA',
            **{f'{key}_possible_cue_discrepancy_pct': round(100 * sum(v[key] == 'POSSIBLE_DISCREPANCY' for v in system_validation) / count, 3) if count else 'NA'
               for key in ('relation_loss', 'feature_type', 'numeric_time', 'traffic_status')},
            'known_severe_failures_fixed_of_77': 'NA', 'known_severe_still_failing': 'NA',
            'known_severe_not_adjudicated': 77,
            'average_runtime_seconds_per_attempt': round(sum(elapsed) / len(elapsed), 6) if elapsed else 'NA',
            'approximate_api_cost_usd': 0 if not attempted or system == 'huggingface' else 'NA_SEE_REQUEST_USAGE',
            'metric_denominator': 'successful candidates for screen percentages; semantic rates require adjudicated gold',
            'environment_metadata': f'runs/{run_id}/environment.json',
            'candidate_file_sha256': file_sha(experiment / 'runs' / system / run_id / 'candidates.csv')})
        for label, expected in EXPECTED_SUBSETS.items():
            matching = [v for v in system_validation if v['legacy_audit_class'] == label]
            subsets.append({'system': system, 'audit_class': label, 'records': len(matching),
                'expected_records': expected, 'successful_candidates': sum(v['generation_status'] == 'SUCCESS' for v in matching),
                'automatically_approved': 0, 'interpretation': 'legacy regression/review subset, not new gold truth'})
    chosen = representative_ids(blind, audit, candidates)
    representatives = []
    by_id = {r['dataset_record_id']: r for r in blind}
    for key, reasons in chosen.items():
        record, evidence = by_id[key], audit[key]
        representatives.append({'dataset_record_id': key, 'tweet_id': record['tweet_id'],
            'selection_families': ';'.join(reasons), 'original_hindi': record['text_original'],
            'legacy_translation': evidence['text_translated'],
            **{s + '_candidate': candidates[s][key]['generated_translation'] for s in SYSTEMS},
            **{s + '_generation_status': candidates[s][key]['generation_status'] for s in SYSTEMS},
            'audit_note': evidence['review_note'],
            'validation_assessment': 'NO_COMPARISON_AVAILABLE' if not any(candidates[s][key]['generation_status'] == 'SUCCESS' for s in SYSTEMS)
                                     else 'INDEPENDENT_REVIEW_REQUIRED'})
    vdir, rdir = experiment / 'validation' / run_id, experiment / 'reports' / run_id
    artifacts = [(vdir / 'validation_results.csv', validation), (vdir / 'legacy_regression_analysis.csv', regression),
                 (rdir / 'system_comparison.csv', metrics), (rdir / 'representative_cases.csv', representatives),
                 (rdir / 'legacy_subset_comparison.csv', subsets)]
    for path, rows in artifacts:
        write_csv_once(path, rows)
    available = sum(m['records_successfully_translated'] for m in metrics)
    report = f'''# Blind spatial-translation bake-off: {run_id}

## Outcome

Completed blind-input preparation, three-arm preflight/smoke execution, immutable full-run status ledgers, candidate freeze and post-freeze audit reveal. **{available} translations were generated.** A status ledger with 815 entries is not a completed translation arm. Unavailable providers were not substituted. No translation was fabricated, rewritten, or promoted to production.

The same 20 IDs, selected by seeded SHA-256 rank without labels, were assigned to every smoke arm. See `runs/{run_id}/smoke_report.json`. Blocked smoke gates are not successful API integration tests. The configuration is frozen for reproducibility of this blocked attempt; service integration must still pass a new smoke run after setup.

## System comparison

| System | Scheduled | Attempted translations | Successful | Missing/blocked |
| --- | ---: | ---: | ---: | ---: |
'''
    for m in metrics:
        report += f"| {m['system']} | 815 | {m['records_attempted']} | {m['records_successfully_translated']} | {m['blocked_or_failed']} |\n"
    report += '\n## Exact blockers\n\n'
    for system, blockers in frozen['blocked_systems'].items():
        report += f'- {system}: ' + ('; '.join(blockers) or 'No preflight blocker; inspect request outcomes') + '\n'
    report += f'''
## Findings and limits

Quality rates and severe-failure repair rates are NA when unmeasured, not zero-error claims. The 77 severe Hindi cases each have a regression row per system, marked uncertain/requires review where there is no candidate or independent adjudication. The 548 unresolved legacy cases are not counted as translation failures. Legacy subsets reconcile to 77 + 104 + 57 + 548 + 29 = 815; they are not exhaustive new gold labels or a representative prevalence estimate.

The representative table contains {len(representatives)} post-reveal selections covering documented failure families. Empty candidate columns explicitly mean unavailable generation. No cross-system disagreements or successes can be inferred from empty cells. These are review cases, not evidence of comparative quality.

Validation uses transparent Hindi/English cue screens for selected relations, features, numeric/time tokens, negation, status and residual Devanagari. Cue mismatch means possible discrepancy. Cross-script place identity, added/missing places, mention ordering, reversals and route-clause equivalence require independent bilingual review. Self-reported structured alignment (OpenAI, Hugging Face) is not gold; it only tests a candidate against its own claimed mentions. No record receives AUTO_VALIDATED solely because heuristic checks are quiet. Incomplete audit toponym hints are joined only as QA evidence after freezing and are never treated as exhaustive annotations.

## Recommendations

1. No default translator can be selected without successful candidates and comparative adjudication.
2. Conventional MT followed by deterministic screening and blinded LLM/human adjudication is a hypothesis to test, not a demonstrated superior workflow.
3. No Hindi record is safe to approve automatically from this run.
4. All 815 remain pending translation and review; prioritize the 77 severe regression cases once candidates exist, without treating them as prevalence evidence.
5. Before canonical integration, obtain genuine outputs, independent bilingual span/relation/status annotations, repeated-mention and multi-clause tests, reviewer agreement, precision estimates for any approval gate, and held-out evaluation. Repeat technical smoke checks with actual credentials and pin the installed environment.

## Reproducibility

Blind input SHA-256: `{frozen['input_sha256']}`. Source commit: `{manifest['source_commit']}`; working tree was dirty from the prior authorized task. The run snapshots generator source, schema, resolved configuration, prompt and library/Python versions. `freeze.json` hashes every frozen run artifact, including candidate CSVs and the OpenAI/Hugging Face alignment JSONL files. Per-row output_sha256 hashes the UTF-8 translation, not the containing CSV. Missing outputs have empty output hashes. Timestamps are UTC; no timestamps are invented for unattempted generation.

Protected source/audit/canonical/queue hashes matched preparation at reveal. Python generation denies reads from repository data/docs/results directories; adapters receive only the four-field blind record and cannot request tools. This enforces input/pipeline blinding, not personnel blinding: the implementing assistant had prior audit context. The prompt contains generic fidelity rules, no corpus-specific corrected examples. Evaluation output never flows back into generation. Repeating serialization is deterministic; external service model outputs are not guaranteed deterministic. IndicTrans2 fixes revision/seed/beam decoding but hardware/library reproducibility still matters.

No API translation requests occurred where credentials failed preflight, so incurred API cost for those arms is zero. Costs for any actual requests require usage/billing evidence. No unsupported model substitutions, implicit retries or auto-approval occurred. Production input, semantic parser, geocoder, route outputs and manuscript remain unchanged.

See the experiment README for exact setup, official implementation references and rerun commands. After credentials/setup, use a **new run ID**. Never overwrite the frozen run or tune its prompt using revealed examples. Root candidate/report CSVs are first-run discovery copies; versioned directories are authoritative.
'''
    write_text_once(rdir / 'spatial_translation_bakeoff.md', report)
    write_json_once(rdir / 'evaluation_manifest.json', {'revealed_at': now(), 'run_id': run_id,
        'generation_freeze_sha256': file_sha(experiment / 'runs' / run_id / 'freeze.json'),
        'audit_sha256': file_sha(root / 'results/translation_discrepancies.csv'),
        'protected_source_hashes_match': True, 'subset_counts': EXPECTED_SUBSETS,
        'report_hashes': {p.name: file_sha(p) for p, _ in artifacts}})
    for path, _ in artifacts:
        alias = path.parent.parent / path.name
        if not alias.exists():
            write_text_once(alias, path.read_text(encoding='utf-8'))
    alias = experiment / 'reports/spatial_translation_bakeoff.md'
    if not alias.exists():
        write_text_once(alias, report)
    print(f'Evaluated frozen run: {available} generated translations; no automatic approvals.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    evaluate(parser.parse_args().run_id)
