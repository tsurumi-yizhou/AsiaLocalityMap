"""Display reduction must preserve real units, enclaves and shared edges."""
import copy
from pathlib import Path
import sys
import unittest

from shapely.geometry import Polygon, MultiPolygon, box, mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from display_geometry import simplify_areas


def row(name, geometry, rank=1):
    center = geometry.representative_point()
    return dict(id=name, rank=rank, geometry=mapping(geometry), center=[center.x, center.y])


class DisplayGeometryTests(unittest.TestCase):
    def test_water_removed_enclave_and_small_named_island_retained(self):
        lake = box(1, 1, 2, 2)
        enclave = box(3, 3, 4, 4)
        mainland = Polygon(box(0, 0, 6, 6).exterior, [lake.exterior, enclave.exterior])
        rock = box(7, 0, 7.002, .002)
        island = box(8, 0, 8.005, .005)
        rows = [row('mainland', MultiPolygon([mainland, rock, island])),
                row('enclave', enclave), row('named island', island, 2)]
        original = copy.deepcopy(rows)
        result, report = simplify_areas(rows)
        areas = {r['id']: shape(r['geometry']) for r in result}
        self.assertEqual(rows, original)
        self.assertTrue(areas['mainland'].covers(lake.representative_point()))
        self.assertEqual(areas['mainland'].intersection(areas['enclave']).area, 0)
        self.assertFalse(areas['mainland'].intersects(rock))
        self.assertTrue(areas['mainland'].covers(areas['named island']))
        self.assertGreater(areas['named island'].area, 0)
        self.assertTrue(report['coverage_valid'])

    def test_shared_zigzag_reduced_without_gap_or_overlap(self):
        edge = [(1 + (.002 if i % 2 else 0), i / 100) for i in range(101)]
        a = Polygon([(0, 0), *edge, (0, 1)])
        b = Polygon([*reversed(edge), (2, 0), (2, 1)])
        result, report = simplify_areas([row('a', a), row('b', b)])
        left, right = [shape(r['geometry']) for r in result]
        self.assertLess(report['after']['vertices'], report['before']['vertices'] / 2)
        self.assertEqual(left.intersection(right).area, 0)
        self.assertAlmostEqual(left.union(right).area, 2)
        self.assertGreater(left.boundary.intersection(right.boundary).length, .99)

    def test_existing_hierarchy_and_source_overlap_remain_identical(self):
        result, _ = simplify_areas([row('coarse', box(0, 0, 4, 4)),
                                   row('fine', box(1, 1, 2, 2), 2),
                                   row('source overlap', box(3, 0, 5, 4))])
        coarse, fine, overlap = [shape(r['geometry']) for r in result]
        self.assertTrue(coarse.covers(fine))
        self.assertEqual(coarse.intersection(overlap).area, 4)

    def test_rounding_does_not_create_overlap_at_unequally_sampled_edge(self):
        # Identical straight shared edge, with an extra collinear source vertex
        # on one side. Rounding that midpoint alone would bend it into its neighbour.
        left = Polygon([(0, 0), (1, 0), (1.0006, .5), (1.0012, 1), (0, 1)])
        right = Polygon([(1, 0), (2, 0), (2, 1), (1.0012, 1)])
        self.assertLess(left.intersection(right).area, 1e-10)
        result, report = simplify_areas([row('left', left), row('right', right)])
        left, right = [shape(r['geometry']) for r in result]
        self.assertEqual(left.intersection(right).area, 0)
        self.assertGreater(left.boundary.intersection(right.boundary).length, .99)
        self.assertGreater(report['rounding_overlap_faces_resolved'], 0)


if __name__ == '__main__':
    unittest.main()
