"""Source, time, dynasty-scope and historical-name checks for the offline maps."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from shapely.geometry import Point, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from history_periods import CATALOG, YEARS, DEFAULT_YEAR, period_at, reference_years, reference_layer_available
from historical_territories import CN_POLITIES
from korean_boundaries import GORYEO_YEAR, load_upper_areas, SOURCE_BASES
from boundary_topology import decode_geometry

APP = ROOT / 'data/processed/android'

def snapshot(year):
    with (APP / 'snapshots' / f'{year}.jsonl').open() as stream:
        rows = [json.loads(line) for line in stream]
    networks = {}
    for row in rows:
        if 'boundary_set' in row:
            key = row['boundary_set']
            if key not in networks:
                networks[key] = json.loads((APP/'boundaries'/f'{key}.json').read_text())['arcs']
            row['geometry'] = decode_geometry(row['geometry'], networks[key])
    return rows


class HistoricalDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = sqlite3.connect(ROOT / 'data/processed/history.sqlite')
        cls.rows = snapshot(DEFAULT_YEAR)
        cls.source = {r[0]: (r[1], r[2], r[3], json.loads(r[4])) for r in cls.con.execute(
            'SELECT id,source,begin_year,end_year,attributes_json FROM feature')}

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_database_integrity_and_source_retention(self):
        self.assertEqual(self.con.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.con.execute('PRAGMA foreign_key_check').fetchall(), [])
        for source, expected in [('chgis-county',10522),('chgis-pref-point',5226),('chgis-pref-polygon',3830),('ming-military',375),('zheng-wu-prefecture',1070)]:
            self.assertEqual(self.con.execute('SELECT count(*) FROM feature WHERE source=?',(source,)).fetchone()[0], expected)

    def test_region_catalog_and_qing_removed(self):
        self.assertEqual(set(p['region'] for p in CATALOG), {'cn','kr','jp'})
        self.assertEqual([(p['titles']['zh'],p['year']) for p in CATALOG if p['region']=='cn'], [('汉',2),('唐',742),('宋',1102),('明',1585)])
        self.assertEqual(len(CATALOG), len({p['id'] for p in CATALOG}))
        self.assertFalse(any(p['id']=='qing' or p['titles']['zh']=='清' for p in CATALOG))
        for p in CATALOG:
            self.assertTrue((APP/'snapshots'/f"{p['year']}.jsonl").is_file())
            self.assertLessEqual(p['start'],p['year'])
            self.assertGreaterEqual(p['end'],p['year'])
        self.assertEqual((APP/'map.jsonl').read_bytes(),(APP/'snapshots'/f'{DEFAULT_YEAR}.jsonl').read_bytes())

    def test_all_snapshots_have_auditable_dates_and_scope(self):
        reference_metadata = json.loads((APP/'reference-years.json').read_text())
        for anchor in YEARS:
            rows = snapshot(anchor)
            refs = reference_years(anchor)
            self.assertEqual(reference_metadata[str(anchor)], refs)
            self.assertEqual(len(rows),len({f['id'] for f in rows}))
            self.assertEqual({(f['id'],f['year']) for f in rows},set(self.con.execute(
                'SELECT feature_id,reference_year FROM display_snapshot WHERE context_year=?',(anchor,))))
            cn_period = period_at('cn',refs['cn']) if refs['cn'] is not None else None
            allowed = CN_POLITIES.get(cn_period['id'],set()) if cn_period else set()
            for f in rows:
                with self.subTest(anchor=anchor,feature=f['id']):
                    self.assertEqual(f['year'],refs[f['time_region']])
                    self.assertEqual(f['context_year'],anchor)
                    source,begin,end,attrs = self.source[f['id']]
                    if source.startswith('chgis') or source in {'ming-military','cliopatria'}:
                        self.assertLessEqual(begin,f['year']);self.assertGreaterEqual(end,f['year'])
                    if source.startswith('chgis') or source=='ming-military':
                        self.assertLessEqual(end,1914)
                    if source=='hisgeo':
                        self.assertIn(f"s{f['year']}",attrs['base_year'].split('/'))
                    if source=='codh':self.assertEqual(f['year'],1864)
                    if source=='cliopatria':
                        self.assertEqual(attrs['Type'],'POLITY')
                        self.assertFalse(attrs.get('Components'))
                        self.assertFalse(attrs['Name'].startswith('('))
                        self.assertNotIn(attrs['Name'], {'Qing Dynasty','Later Jin Dynasty'})
                        if f['region']=='cn':self.assertIn(attrs['Name'],allowed)
                    if refs['cn'] is None:self.assertNotEqual(f['region'],'cn')

    def test_only_local_features_ship_and_each_menu_has_local_data(self):
        for year in YEARS:
            rows = snapshot(year)
            self.assertTrue(all(f['layer'] == 'administrative' and f['rank'] >= 1 for f in rows))
            self.assertFalse(any(f['id'].startswith('cliopatria:') for f in rows))
        for period in CATALOG:
            rows = snapshot(period['year'])
            local = [f for f in rows if f['region'] == period['region'] and f['rank'] >= 2]
            self.assertGreater(len(local), 0, period['id'])
        military = [f for f in self.rows if f['system'] == '军事' and 120 < f['center'][0] < 126 and 38 < f['center'][1] < 43]
        self.assertTrue(military)
        self.assertTrue(all(f['geometry']['type'] == 'Point' for f in military if f['id'].startswith('ming-military:')))
        self.assertTrue(any(f['name']=='辽东都司' and f['geometry']['type']!='Point' for f in military))

    def test_ming_dusi_boundaries_and_daning_city_reference(self):
        liaodong=next(f for f in self.rows if f['name']=='辽东都司')
        self.assertEqual(liaodong['geometry_year'],1582)
        self.assertEqual(liaodong['year'],1585)
        self.assertEqual(liaodong['system'],'军事')
        self.assertEqual(liaodong['rank'],1)
        g=shape(liaodong['geometry'])
        for p in [(123.17,41.27),(123.43,41.8),(124.39,40.13),(124.78,40.73),(121.61,38.92)]:
            self.assertTrue(g.covers(Point(*p)),p)
        self.assertFalse(g.covers(Point(124.53,40.2)))
        yongping=next(f for f in self.rows if f['name']=='永平府' and f['geometry']['type']!='Point')
        shuntian=next(f for f in self.rows if f['name']=='顺天府' and f['geometry']['type']!='Point')
        self.assertEqual(yongping['geometry_year'],1582)
        self.assertTrue(yongping['id'].startswith('atlas-ming-liaodong:'))
        self.assertLess(g.distance(shape(yongping['geometry'])),.001)
        self.assertLess(shape(yongping['geometry']).distance(shape(shuntian['geometry'])),.001)
        original=json.loads((ROOT/'data/raw/ming-admin-1582.geojson').read_text())['features']
        for feature in (liaodong,yongping):
            src=shape(next(f['geometry'] for f in original if f['properties']['name']==feature['name']))
            # Display geometry is deliberately coarser; source geometry stays in
            # SQLite. Bound changes by the simplification scale along the outline.
            self.assertLess(src.symmetric_difference(shape(feature['geometry'])).area, src.length * .008)
        korea=unary_union([shape(f['geometry']) for f in self.rows if f['region']=='kr' and f['rank']==2])
        self.assertLess(g.distance(korea),.01)
        # Keep the different-source border discrepancy visible and bounded; do not
        # clip or expand either source geometry to manufacture a perfect seam.
        self.assertLess(g.intersection(korea).area/g.area,.005)
        tieling=next(f for f in self.rows if f['name']=='铁岭卫')
        self.assertTrue(123.7<tieling['center'][0]<124 and 42.2<tieling['center'][1]<42.4)
        self.assertTrue(g.covers(Point(*tieling['center'])))
        original_point=json.loads(self.con.execute('SELECT geometry_json FROM feature WHERE id=?',(tieling['id'],)).fetchone()[0])
        self.assertLess(original_point['coordinates'][1],41)  # Original error remains auditable.
        wanquan=next(f for f in self.rows if f['name']=='万全都司')
        self.assertTrue(shape(wanquan['geometry']).covers(Point(115.06,40.61)))
        daning=next(f for f in self.rows if f['name']=='大宁都司')
        self.assertEqual(daning['geometry']['type'],'Point')
        self.assertEqual(daning['parent'],'保定府')
        self.assertTrue(115.4<daning['center'][0]<115.6 and 38.7<daning['center'][1]<39.0)
        for y in (2,742,1102,1864):
            self.assertFalse(any(f['id'].startswith(('atlas-ming-liaodong:','ming-daning-seat:')) for f in snapshot(y)))

    def test_regional_reference_matching_does_not_choose_missing_years(self):
        for year in range(1392, 1898):
            self.assertIn(reference_years(year)['kr'], {1864})
        for year in range(1336,1868):
            self.assertEqual(reference_years(year)['jp'],1864)
        self.assertIsNone(reference_years(617)['jp'])
        self.assertEqual(reference_years(741)['jp'],1864)
        self.assertEqual(reference_years(1335)['jp'],1864)
        self.assertEqual(reference_years(1391)['kr'],GORYEO_YEAR)
        self.assertIsNone(reference_years(1868)['jp'])
        self.assertIsNone(reference_years(1898)['kr'])
        self.assertEqual([p['id'] for p in CATALOG if p['region']=='jp'],['jp_early_modern'])
        self.assertEqual(reference_years(741)['kr'],757)
        self.assertTrue(all(reference_years(year)['vn'] is None for year in YEARS))

    def test_chinese_primary_names_and_original_scripts(self):
        for anchor in [DEFAULT_YEAR,1864,2]:
            for f in snapshot(anchor):
                if f['region'] in {'kr','vn'}:
                    self.assertRegex(f['name'],r'[\u3400-\u9fff]',f['id'])
        self.assertTrue(any(f['name']=='漢城' and f['native_name']=='한성' for f in self.rows))
        self.assertTrue(any(f['name']=='漢城' and '汉城' in f['search_names'] for f in self.rows))
        self.assertTrue(all(f['native_name']=='한성' for f in self.rows if f['name']=='漢城'))
        self.assertTrue(any(f['name']=='始興' and f['native_name']=='시흥' for f in snapshot(1864)))
        self.assertTrue(any(f['name']=='公忠' and f['native_name']=='공충' for f in snapshot(1864)))
        self.assertFalse(any(f['name']=='長津' for f in snapshot(1864) if f['region']=='kr'))

    def test_four_dynasties_have_prefecture_boundaries(self):
        for year,minimum,name in [(2,103,'南阳郡'),(742,307,'邓州'),(1102,313,'邓州'),(1585,200,'南阳府')]:
            rows = [f for f in snapshot(year) if f['region']=='cn' and f['geometry']['type']!='Point']
            self.assertGreaterEqual(len(rows), minimum)
            self.assertTrue(any(f['name']==name and shape(f['geometry']).covers(Point(112.5283,32.9908)) for f in rows),year)
            for f in rows:
                if f['id'].startswith('zheng-wu-prefecture:'):
                    attrs=self.source[f['id']][3]
                    self.assertEqual(attrs['layer'],'ResearchArea')
                    self.assertEqual(int(attrs['YEAR'].removesuffix('AD')),year)
                    self.assertTrue(attrs['name_evidence'])
                    self.assertNotIn(',',attrs['PrefNAM'])
                    self.assertEqual(f['rank'],1)
                    self.assertRegex(f['name'],r'[\u3400-\u9fff]')

    def test_points_never_supply_county_boundaries(self):
        for f in self.rows:
            if f['id'].startswith(('chgis-county:','ming-military:','hisgeo:seat:')):
                self.assertEqual(f['geometry']['type'],'Point')
            if f['layer']=='territory':self.assertEqual(f['rank'],0)

    def test_shared_japanese_reference_keeps_source_date(self):
        self.assertEqual(sum(f['region']=='jp' for f in self.rows),783)
        self.assertTrue(all(f['year']==1864 for f in self.rows if f['region']=='jp'))
        for year in YEARS:
            korean = [f for f in snapshot(year) if f['region']=='kr']
            if reference_years(year)['kr'] is None:
                self.assertEqual(korean,[])
                continue
            if reference_years(year)['kr'] in {757,GORYEO_YEAR}:
                expected_points = 14 if reference_years(year)['kr'] == 757 else 8
                expected_areas = len(load_upper_areas(ROOT / 'data/raw', reference_years(year)['kr'], bundled=ROOT / 'data/reference/korean-upper', require_complete=True))
                self.assertEqual(sum(f['geometry']['type']=='Point' for f in korean),expected_points)
                self.assertEqual(sum(f['geometry']['type']!='Point' for f in korean),expected_areas)
                self.assertTrue(all(f['year']==reference_years(year)['kr'] for f in korean))
                self.assertFalse(any(f['id'].startswith('hisgeo:') for f in korean))
                continue
            self.assertEqual(len(korean),343)
            self.assertEqual(sum(f['rank']==2 for f in korean),334)
            self.assertTrue(all(f['geometry']['type'] in {'Polygon','MultiPolygon'} and f['year']==1864 for f in korean))
            self.assertTrue(any(f['name']=='漢城' and f['rank']==2 and shape(f['geometry']).covers(Point(126.978,37.5665)) for f in korean))
        late=snapshot(1864)
        jp={f['name'] for f in late if f['region']=='jp' and f['rank']==1}
        self.assertEqual(len(jp),68)
        self.assertTrue({'陸奥国','出羽国'}.issubset(jp))
        self.assertFalse(jp.intersection({'岩代国','磐城国','羽前国','羽後国','石狩国'}))
        self.assertTrue(any(f['name']=='山城国' and shape(f['geometry']).covers(Point(135.7681,35.0116)) for f in late))
        self.assertTrue(any(f['name']=='漢城' and f['rank']==2 and shape(f['geometry']).covers(Point(126.978,37.5665)) for f in late))

    def test_ancient_northeast_has_no_joseon_overlay(self):
        for year in (2,742,1102):
            rows=snapshot(year)
            self.assertFalse(any(f['id'].startswith('hisgeo:') for f in rows))
            for rank in (1,2):
                self.assertEqual(any(f['region']=='jp' and f['rank']==rank for f in rows),
                                 reference_layer_available('jp',rank,year))
        han=snapshot(2)
        self.assertTrue(any(f['name']=='乐浪郡' and shape(f['geometry']).covers(Point(125.754,39.033)) for f in han))

    def test_three_korean_periods_have_distinct_administrative_references(self):
        self.assertEqual([p['titles']['zh'] for p in CATALOG if p['region']=='kr'], ['新羅','高麗','朝鮮'])
        silla = [f for f in snapshot(757) if f['region']=='kr']
        goryeo = [f for f in snapshot(GORYEO_YEAR) if f['region']=='kr' and f['geometry']['type']=='Point']
        self.assertEqual(sum(f['kind']=='州治参考' for f in silla),9)
        self.assertEqual(sum(f['kind']=='小京参考' for f in silla),5)
        self.assertEqual({f['name'] for f in goryeo}, {'廣州牧','忠州牧','淸州牧','晉州牧','尙州牧','全州牧','羅州牧','黃州牧'})
        for f in [f for f in silla if f['geometry']['type']=='Point'] + goryeo:
            self.assertTrue(f['native_name'])
            self.assertIn('未提供完整郡县或辖界',f['note'])
            self.assertIn('citation',self.source[f['id']][3])

    def test_early_korean_boundaries_require_documented_sources(self):
        self.assertEqual(self.con.execute("SELECT count(*) FROM feature WHERE source='korea-upper-inferred'").fetchone()[0], 0)
        for period in [p for p in CATALOG if p['region']=='kr']:
            rows=[f for f in snapshot(period['year']) if f['region']=='kr']
            upper=[f for f in rows if f['rank']==1 and f['geometry']['type']!='Point']
            self.assertFalse(any(f.get('inferred') for f in rows))
            if period['id']=='joseon_late':
                self.assertTrue(upper)
                continue
            imported=load_upper_areas(ROOT / 'data/raw', period['year'], bundled=ROOT / 'data/reference/korean-upper', require_complete=True)
            self.assertEqual(len(upper), 9 if period['year'] == 757 else 8)
            self.assertEqual({f['name'] for f in upper}, {a['name'] for a in imported})
            self.assertFalse(any(f['rank']>=2 and f['geometry']['type']!='Point' for f in rows))
            for f in upper:
                source,begin,end,attrs=self.source[f['id']]
                self.assertEqual(source, f"korea-upper-source:{period['year']}")
                self.assertEqual((begin,end), (period['year'],period['year']))
                self.assertIn(attrs['provenance']['boundary_basis'], SOURCE_BASES)
                self.assertIn(f['boundary_basis'], SOURCE_BASES)
                self.assertEqual(f['geometry_year'], attrs['provenance'].get('map_year'))
                self.assertNotIn('control_points', attrs)
                self.assertNotIn('推定', f['note'])

    def test_area_names_use_identified_dated_seats(self):
        for year in YEARS:
            rows = snapshot(year)
            anchored = [f for f in rows if 'label_anchor_id' in f]
            if year in (2,742,1102,757,GORYEO_YEAR,1585,1864):
                self.assertTrue(anchored,year)
            for f in anchored:
                seat = self.con.execute('SELECT geometry_json FROM feature WHERE id=?',(f['label_anchor_id'],)).fetchone()
                self.assertIsNotNone(seat)
                point = shape(json.loads(seat[0]))
                self.assertAlmostEqual(f['label_center'][0],point.x,places=5)
                self.assertAlmostEqual(f['label_center'][1],point.y,places=5)
                self.assertNotEqual(f['geometry']['type'],'Point')

    def test_lightweight_display_geometry_keeps_units_valid(self):
        report=json.loads((ROOT/'data/processed/display-geometry.json').read_text())
        networks=json.loads((ROOT/'data/processed/boundary-topology.json').read_text())
        for key, metrics in report.items():
            if metrics['after']['vertices'] >= metrics['before']['vertices'] and key != 'land':
                # Already compact source maps can gain shared junctions during
                # noding. Verify the coordinates actually stored in the APK.
                region, context_year = key.split('-')
                local_year = reference_years(int(context_year))[region]
                self.assertLess(networks[f'{region}-{local_year}']['vertices_stored'],
                                metrics['before']['vertices'], key)
            else:
                self.assertLess(metrics['after']['vertices'], metrics['before']['vertices'], key)
            if key != 'land':self.assertTrue(metrics['coverage_valid'],key)
        for year in YEARS:
            for row in snapshot(year):
                geometry=shape(row['geometry'])
                self.assertTrue(geometry.is_valid and not geometry.is_empty,row['id'])
                if geometry.geom_type != 'Point':
                    self.assertTrue(geometry.covers(Point(row['center'])),row['id'])

    def test_shipped_areas_reference_shared_boundary_files(self):
        keys = set()
        for year in YEARS:
            for line in (APP/'snapshots'/f'{year}.jsonl').read_text().splitlines():
                row = json.loads(line)
                if row['geometry']['type'] == 'Point':
                    continue
                self.assertIn('arcs',row['geometry'])
                self.assertNotIn('coordinates',row['geometry'])
                self.assertTrue((APP/'boundaries'/f"{row['boundary_set']}.json").is_file())
                keys.add(row['boundary_set'])
        report=json.loads((ROOT/'data/processed/boundary-topology.json').read_text())
        self.assertEqual(keys,set(report))
        self.assertTrue(all(stats['shared_arcs'] > 0 for stats in report.values()))

    def test_no_qing_taiwan_backprojection(self):
        for f in self.rows:
            if f['region']=='cn':self.assertNotIn(f['name'],{'台湾府','台湾县','鳳山縣','凤山县','诸罗县'})
        self.assertFalse(any(f['layer']=='administrative' and f['geometry']['type']!='Point' and
                             shape(f['geometry']).covers(Point(121.5654,25.033)) for f in self.rows))

    def test_published_geometries_are_valid(self):
        with (ROOT/'data/processed/published.jsonl').open() as stream:
            seen=set()
            for line in stream:
                f=json.loads(line);g=shape(f['geometry'])
                self.assertNotIn(f['id'],seen);seen.add(f['id'])
                self.assertTrue(g.is_valid,f['id']);self.assertFalse(g.is_empty,f['id'])
                a,b,c,d=g.bounds
                self.assertTrue(-180<=a<=c<=180 and -90<=b<=d<=90,f['id'])


if __name__=='__main__':unittest.main()
