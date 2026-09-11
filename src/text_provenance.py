"""Read immutable corpus and audit evidence; never geocode or translate."""
import csv
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

CORPUS_SHA256 = '156c71a3adf5603888c2d4db8ca218cf5da67d5c3811edc9ac79c9d4d5ac25d8'
SOURCE_NAME = 'Data/tweets_data.csv'
LOCATION_FIELDS = ('geo', 'mentions', 'osm_id', 'address', 'locations', 'lat', 'lon',
                   'bbox_ne_lat', 'bbox_ne_lon', 'bbox_sw_lat', 'bbox_sw_lon',
                   'confidence', 'accuracy', 'route_coordinates')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def exact_tweet_id(url):
    """Extract decimal characters only; the lossy numeric dataset id is ignored."""
    parts = urlsplit(url)
    if parts.scheme not in ('https', 'http') or parts.netloc.lower() not in (
            'twitter.com', 'www.twitter.com', 'x.com', 'www.x.com'):
        return ''
    match = re.fullmatch(r'/[^/]+/status/([0-9]+)/?', parts.path)
    return match.group(1) if match else ''


def unique_index(rows, key):
    result = {}
    for row in rows:
        identity = key(row)
        if identity in result:
            raise ValueError('Duplicate evidence identity: ' + str(identity))
        result[identity] = row
    return result


def load_bound_records(root):
    """Join by immutable source key / permalink ID, validating exact source text.

    The URL-less evidence row is matched by its complete original and legacy text,
    never by an ordinal. A changed corpus requires a new audit, not silent reuse.
    """
    root = Path(root)
    source = root / SOURCE_NAME
    if digest(source) != CORPUS_SHA256:
        raise ValueError('Corpus fingerprint differs from the audited source')
    rows = read_csv(source)
    audit_path = root / 'results/translation_discrepancies.csv'
    evidence_path = root / 'results/provenance_audit/original_tweet_verification.csv'
    audits = unique_index(read_csv(audit_path), lambda r: r['source_row_key'])
    evidence = unique_index(read_csv(evidence_path), lambda r: (
        ('tweet', r['tweet_id']) if r['tweet_id'] else
        ('text', r['text_from_dataset_original'], r['text_from_dataset_translated'])))
    unique_index(rows, lambda r: r['Unnamed: 0'])
    if len(rows) != len(audits) or len(rows) != len(evidence):
        raise ValueError('Evidence coverage differs from corpus')
    seen = set()
    bound = []
    for row in rows:
        key = row['Unnamed: 0']
        if not key:
            raise ValueError('Missing original source row key')
        tweet_id = exact_tweet_id(row['permalink'])
        identity = ('tweet', tweet_id) if tweet_id else ('text', row['text'], row['translated_text'])
        if identity in seen:
            raise ValueError('Duplicate corpus tweet identity')
        seen.add(identity)
        a, e = audits[key], evidence[identity]
        if (a['tweet_id'] != tweet_id or a['tweet_url'] != row['permalink'] or
                a['text_original'] != row['text'] or a['text_translated'] != row['translated_text'] or
                e['text_from_dataset_original'] != row['text'] or
                e['text_from_dataset_translated'] != row['translated_text'] or
                e['tweet_url'] != row['permalink']):
            raise ValueError('Audit/source alignment mismatch at source key ' + key)
        bound.append((row, a, e))
    return bound, {'source_sha256': CORPUS_SHA256,
                   'audit_sha256': digest(audit_path),
                   'verification_sha256': digest(evidence_path)}


def record_id(source_row_key):
    return 'record:' + hashlib.sha256(
        (SOURCE_NAME + '\0' + CORPUS_SHA256 + '\0' + source_row_key).encode('utf-8')).hexdigest()
