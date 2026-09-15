"""Cached OpenCage geocoding + local structural corroboration.

Every external call is cached to disk keyed by its exact request parameters, so
reruns are free and the exact API responses behind any reported result are
reproducible and inspectable (handoff principle: "cache external geocoder
responses used in final experiments").

Corroboration against Data/network_nodes_data.csv is entirely local (no API
call): that file carries real bridge/tunnel flags on a subset of named road
segments, reprojected here from its native UTM zone 43N (EPSG:32643, verified
against known Delhi coordinates) to WGS84 to compare against geocoder output.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
KEY_PATH = ROOT / 'secrets/opencage_token.txt'
NETWORK_NODES_PATH = ROOT / 'Data/network_nodes_data.csv'
DELHI_CENTER = (28.6139, 77.2090)

_UTM43N_TO_WGS84 = Transformer.from_crs('EPSG:32643', 'EPSG:4326', always_xy=True)


def load_key(path=KEY_PATH):
    return Path(path).read_text(encoding='utf-8').strip()


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * r * asin(sqrt(a))


class GeocodeCache:
    """Flat JSON cache: {request_key: raw_api_response}. request_key is a
    deterministic string built from the exact request parameters, so a changed
    bbox or query never collides with a stale cached answer.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}

    @staticmethod
    def key(query, **params):
        parts = [f'q={query}'] + [f'{k}={v}' for k, v in sorted(params.items()) if v is not None]
        return '|'.join(parts)

    def get(self, query, **params):
        return self.data.get(self.key(query, **params))

    def set(self, query, response, **params):
        self.data[self.key(query, **params)] = response
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False, sort_keys=True), encoding='utf-8')


def geocode(query, cache, key=None, proximity=None, bounds=None, countrycode='in', limit=5):
    """Cached OpenCage forward geocode. Returns the raw parsed JSON response.
    Makes a live HTTP call only on a cache miss.
    """
    cached = cache.get(query, proximity=proximity, bounds=bounds)
    if cached is not None:
        return cached
    key = key if key is not None else load_key()
    params = {'q': query, 'key': key, 'countrycode': countrycode, 'limit': limit}
    if proximity:
        params['proximity'] = proximity
    if bounds:
        params['bounds'] = bounds
    url = 'https://api.opencagedata.com/geocode/v1/json?' + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            response = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        response = {'status': {'code': exc.code, 'message': str(exc)}, 'results': [], 'total_results': 0}
    cache.set(query, response, proximity=proximity, bounds=bounds)
    return response


def make_bbox(lat, lon, half_width_deg=0.02):
    """A small bounding box centered on (lat, lon). ~0.02 deg is roughly 2.2 km
    at Delhi's latitude -- an urban-corridor-sized box, not city-wide.
    """
    return f'{lon - half_width_deg},{lat - half_width_deg},{lon + half_width_deg},{lat + half_width_deg}'


_bridge_tunnel_nodes_cache = None


def load_bridge_tunnel_nodes(path=NETWORK_NODES_PATH):
    """Local, API-free structural evidence: named road segments flagged
    bridge=1 or tunnel=1 in the project's own road-network dataset, reprojected
    to WGS84. Returns a list of (name, feature, lat, lon). Computed once and
    cached in-process since it never changes across a run.
    """
    global _bridge_tunnel_nodes_cache
    if _bridge_tunnel_nodes_cache is not None:
        return _bridge_tunnel_nodes_cache
    import csv
    import re

    point_re = re.compile(r'POINT \(([-\d.]+) ([-\d.]+)\)')
    nodes = []
    seen = set()
    with Path(path).open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            name = row['name'].strip()
            if not name:
                continue
            feature = 'bridge' if row['bridge'] == '1' else ('tunnel' if row['tunnel'] == '1' else None)
            if feature is None:
                continue
            match = point_re.match(row['geometry'])
            if not match:
                continue
            easting, northing = float(match.group(1)), float(match.group(2))
            lon, lat = _UTM43N_TO_WGS84.transform(easting, northing)
            dedupe_key = (name, feature, round(lat, 5), round(lon, 5))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            nodes.append((name, feature, lat, lon))
    _bridge_tunnel_nodes_cache = nodes
    return nodes


def corroborate(lat, lon, feature, radius_m=150, nodes=None):
    """Is there a local network node with this structural feature within
    radius_m of (lat, lon)? Returns the nearest match as
    (name, distance_m) or None. A None result is not evidence against the
    candidate -- this local dataset only tags 152/53,691 (bridge) and
    23/53,691 (tunnel) nodes, so absence here is common and uninformative.
    """
    nodes = nodes if nodes is not None else load_bridge_tunnel_nodes()
    best = None
    for name, node_feature, node_lat, node_lon in nodes:
        if node_feature != feature:
            continue
        dist = haversine_m(lat, lon, node_lat, node_lon)
        if dist <= radius_m and (best is None or dist < best[1]):
            best = (name, dist)
    return best
