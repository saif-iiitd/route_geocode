"""Deterministic, standalone canonical input builder. No legacy translation fallback.

Run from the repository root: python -B -m src.parser_input
Approved translations are deliberately not accepted in this version. Their reserved
fields and protected-mention contract require a separately reviewed implementation.
"""
import argparse
import csv
import re
from collections import Counter
from pathlib import Path

from .text_provenance import (LOCATION_FIELDS, SOURCE_NAME, digest, exact_tweet_id,
                              json_text, load_bound_records, record_id)

NORMALIZATION_VERSION = 'original-whitespace-prefix-v1'
# Individually inspected English originals incorrectly labelled Indonesian in audit.
ENGLISH_LANGUAGE_CORRECTIONS = {'852748238775922688', '1032480895557660672'}


def normalize_original(text):
    text = ' '.join(text.split())
    return re.sub(r'^Traffic Alert(?:\s+|$)', '', text).strip()


def canonical_record(row, audit, evidence, fingerprints):
    tweet_id = exact_tweet_id(row['permalink'])
    flags = []
    language = row['detected_lang']
    if tweet_id in ENGLISH_LANGUAGE_CORRECTIONS:
        language = 'en'
        flags.append('AUDIT_LANGUAGE_LABEL_CORRECTED')
    # An unexpected script/label combination must never be accepted as English.
    non_english = language != 'en' or bool(re.search('[\u0900-\u097f]', row['text']))
    corrupt = audit['audit_class'] == 'SOURCE_DATA_CORRUPTION'
    if row['text'].strip() == '#NAME?':
        corrupt = True
        flags += ['ORIGINAL_CELL_CORRUPTION', 'LEGACY_TRANSLATION_PREVIOUS_ROW_CONTAMINATION']
    if not tweet_id:
        flags.append('MISSING_VALID_TWEET_URL')
        if corrupt:
            flags.append('SOURCE_FIELD_SPILL')
    if evidence['material_source_text_difference'] == 'True':
        corrupt = True
        flags.append('MATERIAL_SOURCE_TEXT_DIFFERENCE')
    possible = audit['possible_spatial_meaning_change'] == 'True'
    if possible:
        flags.append('LEGACY_POSSIBLE_SPATIAL_MEANING_CHANGE')
    if audit['severe_inspected'] == 'True':
        flags.append('LEGACY_SEVERE_SPATIAL_DISCREPANCY')
    if audit['requires_manual_inspection'] == 'True':
        flags.append('LEGACY_REQUIRES_MANUAL_INSPECTION')
    if audit['audit_class'] == 'UNRESOLVED_CROSS_LANGUAGE':
        flags.append('LEGACY_TRANSLATION_UNRESOLVED')
    if tweet_id == '549389894830030848':
        flags.append('LEGACY_JAIL_ROAD_TILAK_NAGAR_SUBSTITUTION')
    if re.search(r'R\.?\s*K\.?\s+Puram', row['text'], re.I) and 'Keshav Puram' in row['address']:
        flags.append('LEGACY_ADDRESS_RK_KESHAV_PURAM_MISMATCH')
    if non_english:
        flags.append('PARSER_TRANSLATION_REQUIRED')
    if corrupt:
        flags.append('SOURCE_RECORD_QUARANTINED')
    status = 'QUARANTINED' if corrupt else 'PARSER_TRANSLATION_REQUIRED' if non_english else 'READY'
    verified = evidence['text_from_live_or_archived_source'] if evidence['retrieval_status'] == 'RETRIEVED' else ''
    return {
        'dataset_record_id': record_id(row['Unnamed: 0']),
        'tweet_id': tweet_id, 'tweet_url': row['permalink'],
        'source_file': SOURCE_NAME, 'source_row_key': row['Unnamed: 0'],
        **fingerprints,
        'text_original': row['text'], 'text_from_verified_source': verified,
        'language_original': language, 'language_recorded': row['detected_lang'],
        'language_origin': 'AUDIT_REVIEW' if language != row['detected_lang'] else 'DATASET_LABEL',
        'text_translated_legacy': row['translated_text'],
        'text_translated': '', 'translation_method': '', 'translation_version': '',
        'translation_review_status': 'NOT_PRODUCED',
        'protected_mentions_original': '[]', 'protected_mentions_status': 'NOT_ANNOTATED',
        'translation_alignment': '[]',
        'text_for_parser': normalize_original(row['text']) if status == 'READY' else '',
        'parser_text_origin': 'DATASET_ORIGINAL_SOURCE_CHECKED' if status == 'READY' and verified else
                              'DATASET_ORIGINAL' if status == 'READY' else 'NONE',
        'normalization_version': NORMALIZATION_VERSION, 'parser_status': status,
        'translation_required': non_english, 'record_quarantined': corrupt,
        'legacy_translation_status': 'QUARANTINED' if audit['requires_manual_inspection'] == 'True' else 'UNTRUSTED',
        'data_quality_flags': json_text(sorted(set(flags))),
        'existing_location_metadata': json_text({k: row[k] for k in LOCATION_FIELDS}),
        'dataset_id_raw': row['id'], 'audit_class': audit['audit_class'],
        'audit_possible_spatial_meaning_change': possible,
        'audit_tags': audit['discrepancy_tags'], 'audit_note': audit['review_note'],
        'source_retrieval_status': evidence['retrieval_status'],
        'source_retrieval_url': evidence['retrieval_source'],
        'source_retrieved_at': evidence['retrieved_at'],
        'source_text_match_status': evidence['text_match_status'],
        'source_difference_class': evidence['source_difference_class'],
    }


def build_records(root):
    bound, fingerprints = load_bound_records(root)
    return [canonical_record(*record, fingerprints) for record in bound]


def write_records(records, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)


def summary(records):
    return {'total_records': len(records),
            'parser_status': dict(Counter(r['parser_status'] for r in records)),
            'translation_required_including_quarantined': sum(r['translation_required'] for r in records),
            'quarantined_source_records': sum(r['record_quarantined'] for r in records),
            'quarantined_legacy_translations': sum(r['legacy_translation_status'] == 'QUARANTINED' for r in records),
            'audit_possible_spatial_changes': sum(r['audit_possible_spatial_meaning_change'] for r in records),
            'parser_ready_with_audit_possible_legacy_spatial_changes': sum(
                r['parser_status'] == 'READY' and r['audit_possible_spatial_meaning_change'] for r in records)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = (args.output or root / 'results/canonical_parser_input.csv').resolve()
    # Alternate paths are for clean-run reproducibility; never replace any other file.
    default = (root / 'results/canonical_parser_input.csv').resolve()
    if output != default and output.exists():
        parser.error('Alternate output must be a new file')
    records = build_records(root)
    write_records(records, output)
    print(json_text(summary(records)))
    print('output_sha256=' + digest(output))


if __name__ == '__main__':
    main()
