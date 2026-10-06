"""Import published or source-map-digitized geometry; never synthesize missing areas.

Optional WGS84 GeoJSON inputs: korea-upper-{year}.geojson, accompanied by
korea-upper-{year}.source.json with year, source_url, rights, boundary_basis
('published_boundary_geometry' or 'digitized_published_map') and sha256.
Source suitability still requires historical review; a citation about the
institution alone is not evidence for its polygon geometry.
"""
import json
from urllib.parse import urlparse

from shapely.geometry import shape
from fileutil import sha256_bytes

SILLA_YEAR = 757
GORYEO_YEAR = 1370
SOURCE_BASES = {'published_boundary_geometry', 'digitized_published_map'}
EXPECTED_NAMES = {
    SILLA_YEAR: {'尙州', '良州', '康州', '漢州', '朔州', '溟州', '熊州', '全州', '武州'},
    GORYEO_YEAR: {'楊廣道', '慶尙道', '全羅道', '西海道', '交州道', '西北面', '東北面', '京畿'},
}


def load_upper_areas(raw, year, bundled=None, require_complete=False):
    """Retain source coordinates and provenance, with no fallback or gap filling."""
    if year not in EXPECTED_NAMES:
        raise ValueError(f'Unsupported early Korean reference: {year}')
    path = raw / f'korea-upper-{year}.geojson'
    provenance = raw / f'korea-upper-{year}.source.json'
    if not path.exists() and not provenance.exists():
        if bundled is not None:
            return load_upper_areas(bundled, year, require_complete=require_complete)
        if require_complete:
            raise ValueError(f'Missing required early Korean boundary source: {year}')
        return []
    if not path.is_file() or not provenance.is_file():
        raise ValueError(f'Boundary geometry and source manifest must both exist: {year}')
    source = json.loads(provenance.read_text())
    if source.get('year') != year:
        raise ValueError(f'Boundary source year mismatch: {year}')
    url = urlparse(source.get('source_url', ''))
    if url.scheme not in {'https', 'http'} or not url.netloc or not source.get('rights', '').strip():
        raise ValueError(f'Missing boundary source URL or rights: {year}')
    if source.get('boundary_basis') not in SOURCE_BASES or source.get('inferred'):
        raise ValueError(f'Only published boundary geometry is accepted: {year}')
    if source['boundary_basis'] == 'digitized_published_map':
        if source.get('date_precision') not in {'reference_year', 'historical_period'} or not source.get('dating_evidence'):
            raise ValueError(f'Missing source-map dating evidence: {year}')
        if not source.get('source_image_sha256') or not source.get('georeferencing', {}).get('points'):
            raise ValueError(f'Missing source-map trace evidence: {year}')
    contents = path.read_bytes()
    if source.get('sha256') != sha256_bytes(contents):
        raise ValueError(f'Boundary source checksum mismatch: {year}')
    collection = json.loads(contents)
    if collection.get('type') != 'FeatureCollection' or not collection.get('features') or collection.get('inferred'):
        raise ValueError(f'Expected nonempty boundary FeatureCollection: {year}')
    crs = collection.get('crs', {}).get('properties', {}).get('name')
    if crs is not None and crs not in {'EPSG:4326', 'urn:ogc:def:crs:OGC:1.3:CRS84', 'urn:ogc:def:crs:EPSG::4326'}:
        raise ValueError(f'Boundary input must use WGS84 longitude/latitude: {year}')
    areas = []
    ids, names = set(), set()
    for feature in collection['features']:
        if feature.get('type') != 'Feature' or feature.get('inferred'):
            raise ValueError(f'Invalid or inferred source feature: {year}')
        attrs = feature['properties']
        key = str(feature.get('id', attrs.get('source_id', '')))
        name = attrs.get('name')
        if not key or key in ids or name in names or name not in EXPECTED_NAMES[year]:
            raise ValueError(f'Invalid or duplicate historical area identity: {year}/{key}')
        if attrs.get('year') != year or attrs.get('inferred') or any(
                marker in attrs for marker in ('control_points', 'capital_radius_km', 'northern_cutoff_lat', 'scope_ids')):
            raise ValueError(f'Undocumented or inferred boundary: {year}/{key}')
        geometry = shape(feature['geometry'])
        if geometry.geom_type not in {'Polygon', 'MultiPolygon'} or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f'Invalid source boundary geometry: {year}/{key}')
        west, south, east, north = geometry.bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError(f'Boundary coordinates are not WGS84 degrees: {year}/{key}')
        if not attrs.get('native_name', '').strip():
            raise ValueError(f'Missing native area name: {year}/{key}')
        ids.add(key); names.add(name)
        areas.append(dict(key=key, name=name, native=attrs['native_name'], geometry=geometry,
                          source=source, attributes=attrs))
    if require_complete and names != EXPECTED_NAMES[year]:
        raise ValueError(f'Incomplete upper boundary coverage: {year}: {EXPECTED_NAMES[year] - names}')
    return areas
