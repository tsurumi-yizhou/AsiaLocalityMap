"""Documentary geometry imports must preserve boundaries and reject model output."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from shapely import coverage_is_valid
from shapely.geometry import box, mapping, Point

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from korean_boundaries import load_upper_areas, GORYEO_YEAR, EXPECTED_NAMES
from fileutil import sha256_file


class KoreanUpperBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raw = Path(self.temp.name)

    def write_source(self, year=757, properties=None, geometry=None, manifest=None):
        # Synthetic fixture only, never an app input or historical-data assertion.
        feature = dict(type='Feature', id='source-1', properties=dict(
            name='尙州' if year == 757 else '楊廣道', native_name='상주', year=year))
        feature['properties'].update(properties or {})
        feature['geometry'] = geometry or mapping(box(128, 36, 129, 37))
        path = self.raw / f'korea-upper-{year}.geojson'
        path.write_text(json.dumps(dict(type='FeatureCollection', features=[feature])))
        provenance = dict(year=year, source_url='https://example.org/boundary-dataset',
                          rights='Test fixture only', boundary_basis='published_boundary_geometry',
                          sha256=sha256_file(path))
        provenance.update(manifest or {})
        (self.raw / f'korea-upper-{year}.source.json').write_text(json.dumps(provenance))
        return feature

    def test_missing_data_never_generates_a_partition(self):
        self.assertEqual(load_upper_areas(self.raw, 757), [])
        self.assertEqual(load_upper_areas(self.raw, GORYEO_YEAR), [])
        with self.assertRaises(ValueError):
            load_upper_areas(self.raw, 757, require_complete=True)

    def test_source_geometry_and_provenance_are_retained_without_gap_filling(self):
        for year in (757, GORYEO_YEAR):
            feature = self.write_source(year)
            areas = load_upper_areas(self.raw, year)
            self.assertEqual(len(areas), 1)
            self.assertEqual(mapping(areas[0]['geometry']), feature['geometry'])
            self.assertEqual(areas[0]['source']['year'], year)
            self.assertEqual(areas[0]['key'], 'source-1')

    def test_inferred_geometry_and_estimated_controls_are_rejected(self):
        for properties in ({'inferred': True}, {'control_points': [[128, 36]]},
                           {'capital_radius_km': 25}, {'northern_cutoff_lat': 39.05},
                           {'scope_ids': ['cliopatria:1']}):
            self.write_source(properties=properties)
            with self.assertRaises(ValueError): load_upper_areas(self.raw, 757)
        self.write_source(manifest={'boundary_basis': 'voronoi'})
        with self.assertRaises(ValueError): load_upper_areas(self.raw, 757)

    def test_wrong_year_checksum_or_missing_evidence_is_rejected(self):
        for manifest in ({'year': 1864}, {'sha256': 'wrong'}, {'source_url': ''}, {'rights': ''}):
            self.write_source(manifest=manifest)
            with self.assertRaises(ValueError): load_upper_areas(self.raw, 757)
        self.write_source(properties={'year': 1864})
        with self.assertRaises(ValueError): load_upper_areas(self.raw, 757)
        (self.raw / 'korea-upper-757.source.json').unlink()
        with self.assertRaises(ValueError): load_upper_areas(self.raw, 757)

    def test_nonpolygon_geometry_is_rejected(self):
        self.write_source(geometry={'type': 'Point', 'coordinates': [128, 36]})
        with self.assertRaises(ValueError): load_upper_areas(self.raw, 757)

    def test_partial_source_cannot_satisfy_complete_app_coverage(self):
        self.write_source()
        with self.assertRaises(ValueError):
            load_upper_areas(self.raw, 757, require_complete=True)

    def test_bundled_maps_cover_both_frameworks_and_preserve_unknown_source_date(self):
        bundled = Path(__file__).resolve().parents[1] / 'data/reference/korean-upper'
        for year in (757, GORYEO_YEAR):
            areas = load_upper_areas(self.raw, year, bundled=bundled, require_complete=True)
            self.assertEqual({a['name'] for a in areas}, EXPECTED_NAMES[year])
            self.assertTrue(coverage_is_valid([a['geometry'] for a in areas]))
            self.assertTrue(all(a['source']['boundary_basis'] == 'digitized_published_map' for a in areas))
            source = areas[0]['source']
            self.assertEqual(source['map_year'], 757 if year == 757 else None)
            self.assertTrue(source['georeferencing']['residual_meters'])
            self.assertTrue(source['source_image_sha256'])
            trace = bundled / source['trace_file']
            self.assertEqual(sha256_file(trace), source['trace_sha256'])

    def test_goryeo_capital_and_southern_seats_have_the_expected_source_regions(self):
        bundled = Path(__file__).resolve().parents[1] / 'data/reference/korean-upper'
        areas = load_upper_areas(bundled, GORYEO_YEAR, require_complete=True)
        for (lon, lat), expected in [((126.55, 37.97), '京畿'), ((126.978, 37.5665), '楊廣道'),
                                     ((128.084, 35.180), '慶尙道'), ((126.717, 35.032), '全羅道')]:
            names = [a['name'] for a in areas if a['geometry'].covers(Point(lon, lat))]
            self.assertEqual(names, [expected])


if __name__ == '__main__': unittest.main()
