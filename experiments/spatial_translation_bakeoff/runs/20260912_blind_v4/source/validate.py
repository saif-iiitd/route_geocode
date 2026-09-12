"""Conservative structural screens, not a gold semantic evaluator.

No clean screen confers automatic approval. Worded numbers, synonyms, implicit
relations and opaque place identity need independent bilingual adjudication.
"""
import re
from collections import Counter
from .common import dumps

RELATIONS = {
    'via': (r'होकर|होते हुए|के रास्ते', r'\bvia\b|\bthrough\b|\bby way of\b'),
    'near': (r'के पास|के नजदीक|के नज़दीक|निकट', r'\bnear\b|\bclose to\b|\bnearby\b'),
    'between': (r'के बीच|के मध्य', r'\bbetween\b'),
    'under': (r'के नीचे', r'\bunder\b|\bbeneath\b|\bbelow\b'),
    'towards': (r'की ओर|की तरफ|कि ओर', r'\btowards?\b|\bin the direction of\b'),
}
FEATURES = {
    'road': (r'रोड|सड़क', r'\broad\b'),
    'marg': (r'मार्ग', r'\bmarg\b|\broad\b|\broute\b'),
    'chowk': (r'चौक', r'\bchowk\b|\bsquare\b|\bintersection\b'),
    'flyover': (r'फ्लाईओवर|फ्लाई ओवर', r'\bflyover\b|\bfly over\b'),
    'underpass': (r'अंडरपास|अंडर पास', r'\bunderpass\b|\bunder pass\b'),
    'bridge': (r'पुल', r'\bbridge\b|\bpul\b'),
    'police_station': (r'थाना', r'\bpolice station\b|\bthana\b'),
    'carriageway': (r'कैरिजवे|कैरिज वे|कैरिजवे', r'\bcarriageway\b|\bcarriage way\b'),
}
STATUS = {
    'closed': (r'बंद', r'\bclosed\b|\bclosure\b|\bshut\b|\bblocked\b'),
    'normal': (r'सामान्य|नार्मल|नॉर्मल', r'\bnormal\b'),
    'open': (r'खोल|खुल', r'\bopen\w*\b|\breopen\w*\b'),
    'jam': (r'जाम', r'\bjam\b|\bcongest\w*\b|\bheavy\b'),
    'diverted': (r'डायवर्ट', r'\bdivert\w*\b'),
    'restricted': (r'प्रतिबंध', r'\brestrict\w*\b|\bprohibit\w*\b|\bban\w*\b'),
}


def digit_tokens(text):
    text = text.translate(str.maketrans('०१२३४५६७८९', '0123456789'))
    return Counter(re.findall(r'\d+(?:[.:/]\d+)*', text))


def time_tokens(text):
    text = text.translate(str.maketrans('०१२३४५६७८९', '0123456789'))
    return Counter(re.findall(r'\b\d{1,2}:\d{2}\b', text))


def screen(original, candidate, alignment=None):
    base = {'validation_state': 'GENERATION_FAILED', 'flags': [],
            'place_drop': 'NOT_ASSESSED', 'place_addition': 'NOT_ASSESSED',
            'mention_order': 'NOT_ASSESSED', 'direction_reversal': 'NOT_ASSESSED',
            'route_clause_count': 'NOT_ASSESSED', 'relation_loss': 'NOT_ASSESSED',
            'feature_type': 'NOT_ASSESSED', 'numeric_time': 'NOT_ASSESSED',
            'traffic_status': 'NOT_ASSESSED', 'residual_devanagari': 'NOT_ASSESSED',
            'auto_approval': False}
    if candidate['generation_status'] != 'SUCCESS':
        base['flags'] = ['NO_GENERATED_TRANSLATION']
        return base
    translated = candidate['generated_translation']
    flags = ['TOPONYM_REVIEW_REQUIRED', 'DIRECTION_REVIEW_REQUIRED', 'ROUTE_CLAUSE_REVIEW_REQUIRED']
    base.update(validation_state='REVIEW_REQUIRED', place_drop='REQUIRES_BILINGUAL_REVIEW',
                place_addition='REQUIRES_BILINGUAL_REVIEW', mention_order='REQUIRES_BILINGUAL_REVIEW',
                direction_reversal='REQUIRES_BILINGUAL_REVIEW', route_clause_count='REQUIRES_BILINGUAL_REVIEW')
    for mapping, key in ((RELATIONS, 'relation_loss'), (FEATURES, 'feature_type'), (STATUS, 'traffic_status')):
        missing = [name for name, (hi, en) in mapping.items()
                   if re.search(hi, original) and not re.search(en, translated, re.I)]
        base[key] = 'POSSIBLE_DISCREPANCY' if missing else 'NO_TRIGGER_REVIEW_STILL_REQUIRED'
        flags.extend(key.upper() + '_CUE_MISSING_' + name for name in missing)
    negation = bool(re.search(r'नहीं|मत\s', original)) and not bool(re.search(r'\bnot\b|\bno\b|\bavoid\b|\bdon.t\b', translated, re.I))
    if negation:
        flags.append('NEGATION_CUE_MISSING')
        base['traffic_status'] = 'POSSIBLE_DISCREPANCY'
    mismatch = digit_tokens(original) != digit_tokens(translated) or time_tokens(original) != time_tokens(translated)
    base['numeric_time'] = 'POSSIBLE_DISCREPANCY' if mismatch else 'DIGIT_TOKENS_MATCH_NOT_SEMANTIC_PROOF'
    if mismatch:
        flags.append('NUMERIC_OR_TIME_TOKEN_MISMATCH')
    residual = bool(re.search('[\u0900-\u097f]', translated))
    base['residual_devanagari'] = 'PRESENT_REQUIRES_REVIEW' if residual else 'ABSENT'
    if residual:
        flags.append('RESIDUAL_DEVANAGARI')
    if alignment is not None:
        # This tests the candidate against its own claimed alignment, not against gold.
        # A match does not establish mention completeness or correct place identity.
        cursor = 0
        for mention in alignment.get('place_mentions', []):
            surface = mention.get('english_surface', '')
            start = translated.casefold().find(surface.casefold(), cursor) if surface else -1
            if start < 0:
                flags.append('SELF_ALIGNMENT_MENTION_MISSING_OR_ORDER_COUNT_MISMATCH')
                base['validation_state'] = 'STRUCTURAL_MISMATCH'
                break
            cursor = start + len(surface)
    base['flags'] = flags
    return base
