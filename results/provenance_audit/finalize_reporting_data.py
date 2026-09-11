"""Summarize cached evidence and audit results; no network or source writes."""
import csv,json,re,hashlib
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'results/provenance_audit'
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

rows=read(ROOT/'Data/tweets_data.csv')
audit=read(ROOT/'results/translation_discrepancies.csv')
verify=read(OUT/'original_tweet_verification.csv')
for r in verify:
    rn=int(r['dataset_row']);r.setdefault('text_match_status_initial',r['text_match_status'])
    if r['retrieval_status']!='RETRIEVED':
        r['source_difference_class']='NOT_EVALUATED';r['material_source_text_difference']='NOT_EVALUATED'
    elif rn==136:
        r['source_difference_class']='MATERIAL_ORIGINAL_CELL_CORRUPTION';r['material_source_text_difference']='True'
    elif rn in (48,2539):
        r['source_difference_class']='MINOR_PUNCTUATION_DIFFERENCE';r['material_source_text_difference']='False'
        r['text_match_status']='MINOR_FORMATTING_DIFFERENCE'
    elif rn in (299,453):
        r['source_difference_class']='LINK_RENDERING_DIFFERENCE';r['material_source_text_difference']='False'
        # URLs differ. Keep TEXT_DIFFERENCE; do not assert their targets equal.
    elif r['text_match_status'] in ('EXACT_MATCH','MINOR_FORMATTING_DIFFERENCE'):
        r['source_difference_class']=r['text_match_status'];r['material_source_text_difference']='False'
    else:
        r['source_difference_class']='REQUIRES_INSPECTION';r['material_source_text_difference']='UNKNOWN'
    r['possible_translation_stage_spatial_change']=audit[rn-2]['possible_spatial_meaning_change']
    r['severe_translation_stage_inspected']=audit[rn-2]['severe_inspected']
write(OUT/'original_tweet_verification.csv',verify)

# One row per actual input column, including every unnamed spill/padding field.
inventory=[]
for k in rows[0]:
    count=sum(bool(r[k].strip()) for r in rows)
    kind='unknown';source='Undocumented upstream process';usage='Carried through CSV only; not read for routing'
    if k=='text':kind='dataset_original_text';source='Likely tweet collection; verified against official oEmbed';usage='Not consumed by current classifier/route handlers'
    elif k=='translated_text':kind='translated_or_edited_parser_text';source='Undocumented translation plus English normalization/editing';usage='Direct classifier and process_tweet input for all 5144 records'
    elif k=='detected_lang':kind='derived_language_label';usage='Not used to select parser text or pipeline'
    elif k in ('username','date','retweets','favorites','id','permalink','geo','mentions','hashtags'):
        kind='collection_metadata_or_contaminated_field';source='Likely tweet collection; exact collector/version unknown'
    elif k in ('osm_id','address','lat','lon','bbox_ne_lat','bbox_ne_lon','bbox_sw_lat','bbox_sw_lon','confidence','accuracy'):
        kind='legacy_geocoding_metadata';source='Pre-existing lookup/scoring; provider and version not established'
        if k.startswith('bbox_'):usage='Read as input to process_tweet; supplies final corner-to-corner fallback'
    elif k=='locations':kind='legacy_extracted_location_strings';source='Undocumented earlier location extraction; not current nlp_tweet output'
    elif k=='classification_dummies' or k.startswith('Unnamed: ') and 25<=int(k.split(': ')[1])<=49:
        kind='derived_token_column';source='Appears to be a token-list export spread across columns; construction unknown'
    elif k=='route_coordinates':kind='existing_route_output_slot';source='Entirely empty in tweets_data; populated by geocoder in routes_data';usage='Written, not used as a route input'
    elif k=='Unnamed: 0':kind='legacy_row_identifier';source='Likely retained index from a larger source table';usage='Carried through; notebook uses DataFrame position/index instead'
    elif not count:kind='empty_export_padding';source='Export residue; no content in input'
    inventory.append(dict(field_name=k,nonempty_records=count,likely_source=source,provenance_class=kind,current_notebook_use=usage))
write(OUT/'field_inventory.csv',inventory)

summary=json.loads((OUT/'corpus_summary.json').read_text(encoding='utf-8'))
summary['verification']={
    'retrieval_status':dict(Counter(r['retrieval_status'] for r in verify)),
    'text_match_status':dict(Counter(r['text_match_status'] for r in verify)),
    'initial_text_match_status':dict(Counter(r['text_match_status_initial'] for r in verify)),
    'source_difference_class':dict(Counter(r['source_difference_class'] for r in verify)),
    'material_source_text_difference':sum(r['material_source_text_difference']=='True' for r in verify),
    'possible_changes_only_translation_stage':sum(r['retrieval_status']=='RETRIEVED' and r['material_source_text_difference']=='False' and r['possible_translation_stage_spatial_change']=='True' for r in verify),
    'severe_inspected_changes_only_translation_stage':sum(r['retrieval_status']=='RETRIEVED' and r['material_source_text_difference']=='False' and r['severe_translation_stage_inspected']=='True' for r in verify),
    'retrieval_start_utc':min(r['retrieved_at'] for r in verify if r['retrieved_at']),
    'retrieval_end_utc':max(r['retrieved_at'] for r in verify if r['retrieved_at'])}
summary['no_detected_spatial_change']=summary['class_counts']['IDENTICAL_TEXT']+summary['class_counts']['BENIGN_TEXTUAL_DIFFERENCE']
summary['screen_class_by_language']={lang:dict(Counter(r['audit_class'] for r in audit if r['language_recorded']==lang)) for lang in ('en','hi','id')}
summary['manually_reviewed_severe_rows']=[int(r['dataset_row']) for r in audit if r['severe_inspected']=='True']
summary['explicit_record_review_rows']=[int(r['dataset_row']) for r in audit if r['review_level']!='automated_screen']
summary['translated_contains_devanagari']=[int(r['dataset_row']) for r in audit if re.search('[\u0900-\u097f]',r['text_translated'])]
summary['field_nonempty_counts']={r['field_name']:r['nonempty_records'] for r in inventory if not r['field_name'].startswith('Unnamed')}
summary['source_integrity_verified']=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in summary['original_hashes'].items())
assert summary['source_integrity_verified']
assert len(audit)==len(rows)==len(verify)==5144
assert len({r['tweet_url'] for r in verify if r['tweet_url']})==5143
assert sum(summary['class_counts'].values())==5144
assert all(a['text_for_current_parser']==r['translated_text'] for a,r in zip(audit,rows))
assert not any(r['source_difference_class']=='REQUIRES_INSPECTION' for r in verify)
(OUT/'audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k in ['class_counts','possible_spatial_meaning_change','possible_toponym_change','possible_spatial_relation_change','severe_inspected','requires_manual_inspection','verification','no_detected_spatial_change','screen_class_by_language','translated_contains_devanagari','source_integrity_verified']},ensure_ascii=False,indent=2))
