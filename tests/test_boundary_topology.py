from pathlib import Path
import sys
import unittest

from shapely.geometry import Polygon, MultiPolygon, box, mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from boundary_topology import encode, decode_geometry


class BoundaryTopologyTests(unittest.TestCase):
    def test_neighbours_reference_one_arc_in_opposite_directions(self):
        rows = [dict(id=str(i), geometry=mapping(box(i, 0, i+1, 1))) for i in range(2)]
        encoded, arcs = encode(rows, 'test')
        left = encoded['0']['geometry']['arcs'][0]
        right = encoded['1']['geometry']['arcs'][0]
        shared = [i for i in left if ~i in right]
        self.assertEqual(len(shared), 1)
        for row in rows:
            self.assertTrue(shape(row['geometry']).equals(shape(decode_geometry(encoded[row['id']]['geometry'], arcs))))

    def test_hole_enclave_and_disconnected_island_round_trip(self):
        enclave = box(1, 1, 2, 2)
        area = MultiPolygon([Polygon(box(0, 0, 3, 3).exterior, [enclave.exterior]), box(5, 0, 6, 1)])
        rows = [dict(id='outer', geometry=mapping(area)), dict(id='enclave', geometry=mapping(enclave))]
        encoded, arcs = encode(rows, 'test')
        for row in rows:
            self.assertTrue(shape(row['geometry']).equals(shape(decode_geometry(encoded[row['id']]['geometry'], arcs))))
        outer_indices = {i if i >= 0 else ~i for polygon in encoded['outer']['geometry']['arcs'] for ring in polygon for i in ring}
        enclave_indices = {i if i >= 0 else ~i for ring in encoded['enclave']['geometry']['arcs'] for i in ring}
        self.assertTrue(enclave_indices.issubset(outer_indices))


if __name__ == '__main__':
    unittest.main()
