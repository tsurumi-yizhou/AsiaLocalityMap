"""Checks for errors that would misidentify a visitor's historical jurisdiction."""
import json
from pathlib import Path
import sqlite3
import unittest
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = sqlite3.connect(ROOT / "data/processed/history.sqlite")
        with (ROOT / "data/processed/android/map.jsonl").open() as stream:
            cls.rows = [json.loads(line) for line in stream]
        cls.geometries = [(f, shape(f["geometry"])) for f in cls.rows]

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def containing(self, lon, lat):
        return [f for f, g in self.geometries if g.geom_type != "Point" and g.covers(Point(lon, lat))]

    def test_database_integrity(self):
        self.assertEqual(self.con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_source_retention(self):
        for source, expected in [("chgis-county", 10522), ("chgis-pref-point", 5226), ("chgis-pref-polygon", 3830), ("ming-military", 375)]:
            self.assertEqual(self.con.execute("SELECT count(*) FROM feature WHERE source=?", (source,)).fetchone()[0], expected)

    def test_japan_islands_are_not_duplicate_units(self):
        self.assertEqual(len(self.rows), len({f["id"] for f in self.rows}))
        self.assertEqual(self.con.execute("SELECT count(*) FROM feature WHERE source='codh' AND source_id NOT LIKE 'restored:%'").fetchone()[0], 891)
        self.assertEqual(sum(f["region"] == "jp" and f["kind"] == "令制国" for f in self.rows), 68)

    def test_no_meiji_countries_in_edo_baseline(self):
        names = {f["name"] for f in self.rows if f["region"] == "jp" and f["rank"] == 1}
        self.assertTrue({"陸奥国", "出羽国"}.issubset(names))
        self.assertFalse(names.intersection({"岩代国", "磐城国", "羽前国", "羽後国", "石狩国"}))

    def test_no_qing_taiwan_backprojection(self):
        self.assertFalse([f for f in self.rows if f["region"] == "cn" and f["name"] in {"台湾府", "台湾县", "鳳山縣", "凤山县", "诸罗县"}])
        self.assertFalse(self.containing(121.5654, 25.033))

    def test_points_never_supply_boundaries(self):
        county_points = [f for f in self.rows if f["id"].startswith("chgis-county:")]
        self.assertTrue(county_points)
        self.assertTrue(all(f["geometry"]["type"] == "Point" for f in county_points))
        self.assertTrue(all(f["geometry"]["type"] == "Point" for f in self.rows if f["system"] == "军事" and f["id"].startswith("ming-military:")))

    def test_known_locations_and_projection(self):
        self.assertIn("山城国", {f["name"] for f in self.containing(135.7681, 35.0116)})
        seoul = self.containing(126.978, 37.5665)
        self.assertTrue(any(f["region"] == "kr" and f["rank"] == 2 for f in seoul))
        for f, g in self.geometries:
            self.assertTrue(g.is_valid, f["id"])
            self.assertFalse(g.is_empty, f["id"])
            minx, miny, maxx, maxy = g.bounds
            self.assertTrue(-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90, f["id"])

    def test_bad_years_not_published(self):
        query = """SELECT f.id FROM feature f JOIN baseline b ON b.feature_id=f.id
                   WHERE f.begin_year>f.end_year OR f.end_year>1914"""
        self.assertEqual(self.con.execute(query).fetchall(), [])


if __name__ == "__main__":
    unittest.main()
