"""Tests for src/geocoding.py. No live API calls: GeocodeCache/haversine/bbox/
corroborate are pure or read only the local, checked-in network dataset.
"""
import json
import tempfile
import unittest
from pathlib import Path

from src.geocoding import GeocodeCache, corroborate, haversine_m, load_bridge_tunnel_nodes, make_bbox


class TestGeocodeCache(unittest.TestCase):
    def test_miss_then_hit_after_set(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'cache.json'
            cache = GeocodeCache(path)
            self.assertIsNone(cache.get('flyover', bounds='1,2,3,4'))
            cache.set('flyover', {'total_results': 1}, bounds='1,2,3,4')
            self.assertEqual(cache.get('flyover', bounds='1,2,3,4'), {'total_results': 1})

    def test_different_params_do_not_collide(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'cache.json'
            cache = GeocodeCache(path)
            cache.set('flyover', {'v': 'box_a'}, bounds='1,2,3,4')
            cache.set('flyover', {'v': 'box_b'}, bounds='5,6,7,8')
            self.assertEqual(cache.get('flyover', bounds='1,2,3,4')['v'], 'box_a')
            self.assertEqual(cache.get('flyover', bounds='5,6,7,8')['v'], 'box_b')

    def test_cache_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'cache.json'
            GeocodeCache(path).set('temple', {'x': 1}, proximity='28.6,77.2')
            reloaded = GeocodeCache(path)
            self.assertEqual(reloaded.get('temple', proximity='28.6,77.2'), {'x': 1})
            self.assertTrue(path.exists())
            json.loads(path.read_text(encoding='utf-8'))  # valid JSON on disk


class TestGeometryHelpers(unittest.TestCase):
    def test_haversine_zero_distance(self):
        self.assertAlmostEqual(haversine_m(28.6, 77.2, 28.6, 77.2), 0.0, places=3)

    def test_haversine_known_delhi_distance(self):
        # India Gate to Connaught Place, roughly 3 km apart.
        d = haversine_m(28.6129, 77.2295, 28.6315, 77.2167)
        self.assertGreater(d, 1500)
        self.assertLess(d, 4000)

    def test_make_bbox_centers_on_point(self):
        bbox = make_bbox(28.6, 77.2, half_width_deg=0.02)
        west, south, east, north = (float(v) for v in bbox.split(','))
        self.assertAlmostEqual((west + east) / 2, 77.2, places=6)
        self.assertAlmostEqual((south + north) / 2, 28.6, places=6)
        self.assertLess(west, east)
        self.assertLess(south, north)


class TestLocalCorroboration(unittest.TestCase):
    def test_bridge_nodes_reproject_into_plausible_delhi_coordinates(self):
        nodes = load_bridge_tunnel_nodes()
        self.assertGreater(len(nodes), 0)
        for name, feature, lat, lon in nodes:
            self.assertIn(feature, ('bridge', 'tunnel'))
            # Delhi NCR bounding box, generously.
            self.assertTrue(28.0 <= lat <= 29.2, f'{name} lat {lat} outside Delhi NCR')
            self.assertTrue(76.5 <= lon <= 77.6, f'{name} lon {lon} outside Delhi NCR')

    def test_dwarka_flyover_is_present_and_corroborates_nearby_point(self):
        nodes = load_bridge_tunnel_nodes()
        dwarka = next(n for n in nodes if n[0] == 'Dwarka Flyover')
        _, _, lat, lon = dwarka
        hit = corroborate(lat, lon, 'bridge', radius_m=10, nodes=nodes)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[0], 'Dwarka Flyover')

    def test_far_away_point_is_not_corroborated(self):
        # A point far outside Delhi NCR should find no bridge node within range.
        hit = corroborate(19.0760, 72.8777, 'bridge', radius_m=150)  # Mumbai
        self.assertIsNone(hit)

    def test_absence_of_corroboration_is_not_an_error(self):
        # Tunnel data is sparse (23/53,691 nodes); a real Delhi point with no
        # nearby tunnel must return None quietly, not raise.
        hit = corroborate(28.6139, 77.2090, 'tunnel', radius_m=10)
        self.assertIsNone(hit)


if __name__ == '__main__':
    unittest.main()
