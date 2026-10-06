"""Store locality records separately from shared TopoJSON boundary arcs.

No quantization or further simplification here: this step must preserve the
validated display areas exactly. A negative arc index means reverse (~index).
"""
from collections import defaultdict
import json
from pathlib import Path

from shapely.geometry import shape
from topojson import Topology
from fileutil import json_text, write_json


def decode_geometry(geometry, arcs):
    if 'arcs' not in geometry:
        return geometry

    def ring(indices):
        coordinates = []
        for index in indices:
            points = arcs[index] if index >= 0 else list(reversed(arcs[~index]))
            if coordinates and coordinates[-1] != points[0]:
                raise ValueError('Disconnected boundary references')
            coordinates.extend(points if not coordinates else points[1:])
        if not coordinates or coordinates[0] != coordinates[-1]:
            raise ValueError('Unclosed administrative ring')
        return coordinates

    polygons = geometry['arcs'] if geometry['type'] == 'MultiPolygon' else [geometry['arcs']]
    coordinates = [[ring(indices) for indices in polygon] for polygon in polygons]
    return dict(type=geometry['type'], coordinates=coordinates if geometry['type'] == 'MultiPolygon' else coordinates[0])


def encode(rows, key):
    topology = Topology(dict(type='FeatureCollection', features=[
        dict(type='Feature', id=row['id'], properties={}, geometry=row['geometry']) for row in rows
    ]), prequantize=False, winding_order=None).to_dict()
    assert 'transform' not in topology  # Absolute geographic coordinates on disk.
    areas = {g['id']: dict(type=g['type'], arcs=g['arcs'])
             for g in topology['objects']['data']['geometries']}
    assert set(areas) == {row['id'] for row in rows}, 'Topology compiler dropped an area'
    arcs = topology['arcs']
    for row in rows:
        original = shape(row['geometry'])
        restored = shape(decode_geometry(areas[row['id']], arcs))
        equivalent = original.equals(restored) or (
            original.symmetric_difference(restored).area < 1e-12 and original.hausdorff_distance(restored) < 1e-10)
        if not restored.is_valid or not equivalent:
            raise ValueError(f"Boundary topology changed {row['id']}")
    return {row['id']: dict(row, geometry=areas[row['id']], boundary_set=key) for row in rows}, arcs


def compile_directory(app):
    snapshots = {}
    groups = defaultdict(dict)
    old_networks = {}
    for file in sorted((app / 'snapshots').glob('*.jsonl')):
        rows = [json.loads(line) for line in file.read_text().splitlines()]
        snapshots[file] = rows
        for row in rows:
            if row['geometry']['type'] == 'Point':
                continue
            if 'boundary_set' in row:
                previous = row.pop('boundary_set')
                if previous not in old_networks:
                    old_networks[previous] = json.loads((app / 'boundaries' / f'{previous}.json').read_text())['arcs']
                row['geometry'] = decode_geometry(row['geometry'], old_networks[previous])
            key = f"{row['region']}-{row['year']}"
            prior = groups[key].get(row['id'])
            if prior is not None and prior['geometry'] != row['geometry']:
                raise ValueError(f"Inconsistent shared reference: {row['id']}")
            groups[key][row['id']] = row
    networks = app / 'boundaries'
    networks.mkdir(exist_ok=True)
    encoded, report = {}, {}
    for key, features in groups.items():
        rows = list(features.values())
        encoded[key], arcs = encode(rows, key)
        write_json(networks / f'{key}.json', dict(arcs=arcs), compact=True)
        references = defaultdict(set)
        before = 0
        for row in rows:
            geometry = row['geometry']
            polygons = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
            before += sum(len(ring) for polygon in polygons for ring in polygon)
            geometry = encoded[key][row['id']]['geometry']
            polygons = geometry['arcs'] if geometry['type'] == 'MultiPolygon' else [geometry['arcs']]
            for polygon in polygons:
                for ring in polygon:
                    for index in ring:
                        references[index if index >= 0 else ~index].add(row['id'])
        report[key] = dict(areas=len(rows), arcs=len(arcs), shared_arcs=sum(len(ids) > 1 for ids in references.values()),
                           vertices_before=before, vertices_stored=sum(len(arc) for arc in arcs))
        print(f'Shared boundaries {key}: {report[key]}', flush=True)
    for file, rows in snapshots.items():
        with file.open('w') as stream:
            for row in rows:
                if row['geometry']['type'] != 'Point':
                    shared = encoded[f"{row['region']}-{row['year']}"][row['id']]
                    # Context year and names belong to the snapshot, not the network.
                    row = dict(row, geometry=shared['geometry'], boundary_set=shared['boundary_set'])
                stream.write(json_text(row, compact=True) + '\n')
    from history_periods import DEFAULT_YEAR
    (app / 'map.jsonl').write_bytes((app / 'snapshots' / f'{DEFAULT_YEAR}.jsonl').read_bytes())
    for old in networks.glob('*.json'):
        if old.stem not in groups:
            old.unlink()
    write_json(app.parent / 'boundary-topology.json', report)


if __name__ == '__main__':
    compile_directory(Path(__file__).resolve().parents[1] / 'data/processed/android')
