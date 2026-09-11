"""Read-only source verification. Writes evidence only under results/provenance_audit.

Uses public official Twitter/X oEmbed for each supplied status URL. No login,
geocoding, translation, or source edits. Resume from the JSONL evidence cache.
"""
import concurrent.futures as futures
import csv
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'results' / 'provenance_audit'
CACHE = OUT / 'public_tweet_evidence.jsonl'
csv.field_size_limit(10000000)

class TweetText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.inside = False
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == 'p': self.inside = True
        elif tag == 'br' and self.inside: self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag == 'p': self.inside = False
    def handle_data(self, data):
        if self.inside: self.parts.append(data)

def formatting(text):
    return re.sub(r'\s+', ' ', html.unescape(text).replace('\u00a0', ' ')).strip()

def retrieve(url):
    sid = re.search(r'/status/(\d+)', url).group(1)
    endpoint = 'https://publish.twitter.com/oembed?' + urlencode({'url': url, 'omit_script': 'true', 'dnt': 'true'})
    result = dict(tweet_id=sid, tweet_url=url, retrieval_source=endpoint,
                  retrieved_at=datetime.now(timezone.utc).isoformat(),
                  text_from_live_or_archived_source='', retrieval_status='RETRIEVAL_FAILED',
                  http_status='', error='', evidence_sha256='')
    try:
        req = Request(endpoint, headers={'User-Agent': 'Mozilla/5.0 (compatible; ManuscriptProvenanceAudit/1.0)'})
        with urlopen(req, timeout=25) as response:
            raw = response.read(1000000)
            result['http_status'] = response.status
        body = json.loads(raw)
        source_url = body.get('url', '')
        if not re.search(r'/status/' + sid + r'(?:\D|$)', source_url):
            raise ValueError('oEmbed response status ID does not match requested status ID')
        parser = TweetText()
        parser.feed(body.get('html', ''))
        text = ''.join(parser.parts)
        if not text.strip(): raise ValueError('No tweet paragraph in oEmbed response')
        result.update(text_from_live_or_archived_source=text, retrieval_status='RETRIEVED',
                      evidence_sha256=hashlib.sha256(raw).hexdigest(),
                      returned_url=source_url, author_url=body.get('author_url', ''))
    except HTTPError as error:
        result['http_status'] = error.code
        result['error'] = str(error)
        if error.code in (401, 403, 404, 410): result['retrieval_status'] = 'NOT_PUBLICLY_ACCESSIBLE'
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    return result

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'Data/tweets_data.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    cached = {}; attempts = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding='utf-8').splitlines():
            record = json.loads(line); cached[record['tweet_url']] = record
            attempts[record['tweet_url']] = attempts.get(record['tweet_url'], 0) + 1
    urls = [r['permalink'] for r in rows if re.fullmatch(r'https://(?:twitter\.com|x\.com)/[^/]+/status/\d+', r['permalink'])]
    pending = [u for u in dict.fromkeys(urls) if u not in cached or
               (cached[u]['retrieval_status'] == 'RETRIEVAL_FAILED' and attempts.get(u, 0) < 2)]
    print(f'Available URLs: {len(urls)}; cached: {len(cached)}; pending: {len(pending)}', flush=True)
    # Bounded concurrency. On rate limiting, stop adding requests and retain
    # truthful NOT_ATTEMPTED_RATE_LIMIT records rather than claiming deletion.
    with CACHE.open('a', encoding='utf-8') as cache, futures.ThreadPoolExecutor(max_workers=8) as pool:
        it = iter(pending)
        active = {pool.submit(retrieve, u): u for u in [next(it, None) for _ in range(8)] if u}
        count = 0; stopped = False
        while active:
            done, _ = futures.wait(active, return_when=futures.FIRST_COMPLETED)
            for task in done:
                active.pop(task)
                record = task.result(); cached[record['tweet_url']] = record
                cache.write(json.dumps(record, ensure_ascii=False) + '\n'); cache.flush()
                count += 1
                if record['http_status'] == 429: stopped = True
                if count % 100 == 0:
                    print(f'Completed {count}/{len(pending)}; retrieved {sum(v["retrieval_status"] == "RETRIEVED" for v in cached.values())}', flush=True)
                if not stopped:
                    u = next(it, None)
                    if u: active[pool.submit(retrieve, u)] = u
    output = []
    for row_number, row in enumerate(rows, 2):
        url = row['permalink']; rec = dict(cached.get(url, {}))
        if not rec:
            rec = dict(tweet_id='', tweet_url=url, retrieval_source='', retrieved_at='',
                       text_from_live_or_archived_source='', retrieval_status='URL_INVALID' if not url else 'NOT_ATTEMPTED_RATE_LIMIT',
                       http_status='', error='No usable status URL/precise ID' if not url else 'Batch stopped after rate limiting', evidence_sha256='')
        source = rec['text_from_live_or_archived_source']
        def compare(text):
            if rec['retrieval_status'] != 'RETRIEVED': return 'NOT_EVALUATED'
            if source == text: return 'EXACT_MATCH'
            if formatting(source) == formatting(text): return 'MINOR_FORMATTING_DIFFERENCE'
            return 'TEXT_DIFFERENCE'
        rec.update(dataset_row=row_number, dataset_id_raw=row['id'], text_from_dataset_original=row['text'],
                   text_from_dataset_translated=row['translated_text'], text_match_status=compare(row['text']),
                   translated_text_match_status=compare(row['translated_text']))
        output.append(rec)
    fields = ['dataset_row','tweet_id','dataset_id_raw','tweet_url','text_from_dataset_original','text_from_live_or_archived_source',
              'retrieval_status','retrieval_source','retrieved_at','text_match_status','text_from_dataset_translated',
              'translated_text_match_status','http_status','error','returned_url','author_url','evidence_sha256']
    with (OUT / 'original_tweet_verification.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(output)
    from collections import Counter
    print('Retrieval:', dict(Counter(r['retrieval_status'] for r in output)), flush=True)
    print('Original matches:', dict(Counter(r['text_match_status'] for r in output)), flush=True)

if __name__ == '__main__': main()
