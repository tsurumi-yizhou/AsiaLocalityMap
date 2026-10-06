"""Reproduce early Korean upper boundaries from the cited, checksum-pinned maps.

No Voronoi, polity clipping, province-radius estimates, later administrative
borders or nearest-government-seat assignment is used. Silla fields follow the
printed province colors; Goryeo interior arcs follow manually reviewed visible
lines. Shorelines come from the source pixels. Image label positions identify
already bounded map faces; they never construct a territorial partition.

Run after scripts/download_sources.py. Outputs are versioned under
 data/reference/korean-upper; review overlays go to build/korean-upper-review.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from pyproj import Geod, Transformer
from scipy import ndimage
from shapely import coverage_simplify, coverage_is_valid, set_precision, STRtree
from shapely.geometry import box, Polygon, MultiPolygon, Point, LineString, mapping, shape
from shapely.ops import polygonize, unary_union
from boundary_topology import encode, decode_geometry
from fileutil import sha256_file

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'data/reference/korean-upper'
REVIEW = ROOT / 'build/korean-upper-review'
NATIVE = {
    '漢州': '한주', '朔州': '삭주', '溟州': '명주', '尙州': '상주', '良州': '양주',
    '康州': '강주', '熊州': '웅주', '全州': '전주', '武州': '무주',
    '楊廣道': '양광도', '慶尙道': '경상도', '全羅道': '전라도', '西海道': '서해도',
    '交州道': '교주도', '西北面': '서북면', '東北面': '동북면', '京畿': '경기',
}


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def crop_mask(mask, config):
    left, top, right, bottom = config['source_crop']
    mask[:top] = 0; mask[bottom:] = 0; mask[:, :left] = 0; mask[:, right:] = 0
    for x0, y0, x1, y1 in config['exclusions']:
        mask[y0:y1, x0:x1] = 0
    return mask


def raster_polygon(mask):
    runs = []
    for y, row in enumerate(mask):
        transitions = np.flatnonzero(np.diff(np.r_[False, row, False]))
        runs.extend(box(int(x0), y, int(x1), y + 1)
                    for x0, x1 in zip(transitions[::2], transitions[1::2]))
    return unary_union(runs)


def polygon_parts(geometry, minimum=4):
    if geometry.geom_type == 'Polygon':
        return [geometry] if geometry.area >= minimum else []
    if geometry.geom_type not in {'MultiPolygon', 'GeometryCollection'}:
        return []
    return [part for child in geometry.geoms for part in polygon_parts(child, minimum)]


def node_source_rings(polygons):
    """Insert shared T-junctions; rounding is less than a millionth of one pixel."""
    coordinates = np.unique(np.array([coordinate for polygon in polygons
        for part in polygon_parts(polygon, 0) for ring in [part.exterior, *part.interiors]
        for coordinate in ring.coords]), axis=0)
    points = [Point(coordinate) for coordinate in coordinates]
    tree = STRtree(points)
    def ring_vertices(ring):
        result = []
        vertices = list(ring.coords)
        for start, end in zip(vertices, vertices[1:]):
            segment = LineString([start, end])
            indexes = tree.query(segment, predicate='dwithin', distance=3e-7)
            ordered = sorted(indexes, key=lambda index: segment.project(points[index]))
            result.append(start)
            result.extend(tuple(coordinates[index]) for index in ordered
                          if 1e-8 < segment.project(points[index]) < segment.length - 1e-8)
        result.append(vertices[-1])
        return result
    result = []
    for polygon in polygons:
        parts = [Polygon(ring_vertices(part.exterior), [ring_vertices(ring) for ring in part.interiors])
                 for part in polygon_parts(polygon, 0)]
        result.append(parts[0] if len(parts) == 1 else MultiPolygon(parts))
    return result


def trace_silla(pixels, config):
    palette = np.array(config['palette'])
    distances = np.sum((pixels[:, :, None, :] - palette[None, None, :, :]) ** 2, axis=-1)
    labels = np.argmin(distances, axis=-1).astype(np.uint8) + 1
    known = (np.min(distances, axis=-1) < config['known_distance'] ** 2) & (pixels.max(axis=-1) > 120)
    sea = config['sea_palette_index']
    known[(labels == sea + 1) & (distances[:, :, sea] > config['sea_known_distance'] ** 2)] = False
    indices = ndimage.distance_transform_edt(~known, return_distances=False, return_indices=True)
    labels = ndimage.median_filter(labels[tuple(indices)], size=3)
    labels = crop_mask(labels, config)
    cleaned = labels.copy()
    for value in range(1, 10):
        components, count = ndimage.label(labels == value)
        sizes = np.bincount(components.ravel()); sizes[0] = 0
        main = int(sizes.argmax())
        for component in range(1, count + 1):
            if component == main:
                continue
            mask = components == component
            adjacent = labels[ndimage.binary_dilation(mask) & ~mask]
            # Remove color speckles within other fields; keep visible isolated islands.
            if sizes[component] < 8 or np.any((adjacent > 0) & (adjacent < 10)):
                cleaned[mask] = 0
    unknown = (cleaned == 0) & (labels > 0)
    indices = ndimage.distance_transform_edt(cleaned == 0, return_distances=False, return_indices=True)
    cleaned[unknown] = cleaned[tuple(indices)][unknown]
    land = (cleaned >= 1) & (cleaned <= 9)
    # Narrow blue river ink and text holes are cartographic annotations, not area borders.
    filled = ndimage.binary_fill_holes(ndimage.binary_closing(land, structure=np.ones((3, 3))))
    indices = ndimage.distance_transform_edt(~land, return_distances=False, return_indices=True)
    cleaned[filled & ~land] = cleaned[tuple(indices)][filled & ~land]
    # Bound the northern colors by the actual printed political line; river
    # lettering north of that line must not turn into detached province islands.
    domain = Polygon(config['northern_outline'] + [[768, 270], [768, 850], [0, 850], [0, 381]])
    for vertices in config.get('annotation_exclusions', []):
        # Keep a small stroke-width margin along the traced coast.
        domain = domain.difference(Polygon(vertices).buffer(-3))
    return [unary_union(polygon_parts(raster_polygon(cleaned == value).intersection(domain), 8))
            for value in range(1, 10)]


def trace_goryeo(pixels, config):
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    sea = (green - red > 20) & (blue - red > 15)
    clear_land = ((red - blue > 10) | (red - green > 10) |
                  ((pixels.max(axis=-1) - pixels.min(axis=-1)) < 25)) & ~sea
    known = (sea | clear_land) & (pixels.max(axis=-1) > 125)
    indices = ndimage.distance_transform_edt(~known, return_distances=False, return_indices=True)
    land_mask = clear_land[tuple(indices)]
    land_mask = ndimage.binary_fill_holes(ndimage.binary_closing(land_mask, structure=np.ones((3, 3))))
    land = raster_polygon(crop_mask(land_mask, config))
    # The north line is traced from the map's political outline, not an arbitrary cutoff.
    domain = Polygon(config['northern_outline'] + [[437, 323], [437, 800], [0, 800], [0, 299]])
    land = land.intersection(domain)
    mesh = unary_union([domain.boundary] + [LineString(arc) for arc in config['source_boundary_lines']])
    faces = list(polygonize(mesh))
    if len(faces) != 7:
        raise ValueError(f'Goryeo source arcs must enclose seven non-capital fields, got {len(faces)}')
    capital = Polygon(config['capital_outline'])
    polygons = []
    for region in config['regions'][:-1]:
        matches = [face for face in faces if face.covers(Point(region['pixel_label']))]
        if len(matches) != 1:
            raise ValueError(f"Ambiguous bounded source field: {region['name']}")
        polygons.append(unary_union(polygon_parts(matches[0].intersection(land).difference(capital))))
    polygons.append(capital.intersection(land))
    return polygons


def georeference(config, height):
    settings = config['georeferencing']
    width = config['working_width']
    def design(x, y):
        x, y = np.asarray(x) / width, np.asarray(y) / height
        columns = [x, y, np.ones_like(x)]
        if settings['degree'] == 2:
            columns += [x * x, x * y, y * y]
        return np.stack(columns, axis=-1)
    forward = Transformer.from_crs('EPSG:4326', settings['projection'], always_xy=True)
    reverse = Transformer.from_crs(settings['projection'], 'EPSG:4326', always_xy=True)
    points = settings['points']
    coordinates = np.array([p['pixel'] for p in points])
    ground = np.array([forward.transform(*p['lonlat']) for p in points])
    matrix = design(coordinates[:, 0], coordinates[:, 1])
    coefficients, _, rank, _ = np.linalg.lstsq(matrix, ground, rcond=None)
    if rank != matrix.shape[1]:
        raise ValueError('Georeferencing points do not determine the image transform')
    def convert(x, y, z=None):
        result = design(x, y) @ coefficients
        return reverse.transform(result[..., 0], result[..., 1])
    predicted = convert(coordinates[:, 0], coordinates[:, 1])
    geod = Geod(ellps='WGS84')
    residuals = [float(geod.inv(*point['lonlat'], lon, lat)[2])
                 for point, lon, lat in zip(points, *predicted)]
    return convert, dict(settings, residual_meters=residuals,
                         rms_meters=float(np.sqrt(np.mean(np.square(residuals)))),
                         maximum_meters=max(residuals))


def main():
    REVIEW.mkdir(parents=True, exist_ok=True)
    for period in ('silla', 'goryeo'):
        config = json.loads((REFERENCE / f'{period}.trace.json').read_text())
        source_path = ROOT / 'data/raw' / config['source_image']
        if sha256_file(source_path) != config['source_image_sha256']:
            raise ValueError(f'Source image changed: {source_path}')
        original = Image.open(source_path).convert('RGB')
        if list(original.size) != config['source_dimensions']:
            raise ValueError('Unexpected source map dimensions')
        width = config['working_width']
        image = original.resize((width, round(original.height * width / original.width)), Image.Resampling.LANCZOS)
        pixels = ndimage.median_filter(np.asarray(image).astype(float), size=(3, 3, 1))
        polygons = trace_silla(pixels, config) if period == 'silla' else trace_goryeo(pixels, config)
        # Simplify the shared pixel coverage together; never independently shift adjacent edges.
        polygons = [set_precision(polygon, 1e-7) for polygon in polygons]
        polygons = node_source_rings(polygons)
        if not coverage_is_valid(polygons):
            raise ValueError('Source pixel fields do not share exactly matched boundaries')
        polygons = list(coverage_simplify(polygons, 0.5))
        convert, registration = georeference(config, image.height)
        # Transform each shared arc once. Transforming polygon rings separately
        # can bend collinear vertices differently under nonlinear registration.
        pixel_rows = [dict(id=str(index), geometry=mapping(polygon)) for index, polygon in enumerate(polygons)]
        encoded, arcs = encode(pixel_rows, 'source-pixel')
        geographic_arcs = []
        for arc in arcs:
            coordinates = np.array(arc)
            lon, lat = convert(coordinates[:, 0], coordinates[:, 1])
            geographic_arcs.append(np.column_stack([lon, lat]).tolist())
        geographic_shapes = [shape(decode_geometry(encoded[str(index)]['geometry'], geographic_arcs))
                             for index in range(len(polygons))]
        if not coverage_is_valid(geographic_shapes):
            raise ValueError('Georeferencing broke shared boundary topology')
        features = []
        overlay = image.resize((width * 2, image.height * 2))
        draw = ImageDraw.Draw(overlay)
        for index, (region, polygon) in enumerate(zip(config['regions'], polygons)):
            if polygon.is_empty or not polygon.is_valid:
                raise ValueError(f"Invalid traced source field: {region['name']}")
            geometry = geographic_shapes[index]
            if not geometry.is_valid:
                raise ValueError(f"Georeferencing damaged source geometry: {region['name']}")
            for part in polygon_parts(polygon, 0):
                draw.line([(x * 2, y * 2) for x, y in part.exterior.coords], fill=(230, 0, 0), width=2)
            features.append(dict(type='Feature', id=f'{period}-{index + 1}', geometry=mapping(geometry), properties=dict(
                name=region['name'], native_name=NATIVE[region['name']], year=config['year'],
                source_map_label=region['source_label'], source_label_pixel=region['pixel_label'],
                map_year=config['map_year'], date_precision=config['date_precision'],
                boundary_basis='digitized_published_map')))
        output = REFERENCE / f"korea-upper-{config['year']}.geojson"
        write_json(output, dict(type='FeatureCollection', features=features))
        write_json(output.with_suffix('.source.json'), dict(
            year=config['year'], source_url=config['source_url'], rights=f"{config['license']}; {config['author']}; traced and georeferenced adaptation",
            boundary_basis='digitized_published_map', sha256=sha256_file(output),
            source_image_sha256=config['source_image_sha256'], source_image_url=config['download_url'],
            source_dimensions=config['source_dimensions'], author=config['author'], license=config['license'],
            license_url=config['license_url'], map_year=config['map_year'], date_precision=config['date_precision'],
            dating_evidence=config['dating_evidence'], tracing_method=config['mode'],
            trace_file=f'{period}.trace.json', trace_sha256=sha256_file(REFERENCE / f'{period}.trace.json'),
            georeferencing=registration, feature_count=len(features)))
        overlay.save(REVIEW / f'{period}-source-overlay.png')
        print(f"{period}: {len(features)} source areas; registration RMS {registration['rms_meters'] / 1000:.2f} km", flush=True)


if __name__ == '__main__':
    main()
