"""Lightweight reference-map geometry; source geometries stay in the research DB.

Simplify a noded planar partition, then reassemble each area's faces. Shared edges
are processed once, including edges shared by coarse and fine administrative layers.
This preserves existing memberships rather than introducing new overlaps or cracks.
"""
from collections import defaultdict
from math import cos, radians

import shapely as s
from shapely.geometry import Polygon, Point, mapping

GRID = .001  # About 100 m: collapse insignificant digitisation differences.
TOLERANCE = .008  # Coverage VW triangle-area tolerance, in geographic degrees.
MIN_ISLAND_KM2 = 10


def polygons(geometry):
    return [p for p in s.get_parts(geometry) if p.geom_type == "Polygon"]


def area_km2(polygon):
    return polygon.area * 111.32 ** 2 * cos(radians(polygon.centroid.y))


def counts(geometries):
    return dict(vertices=sum(int(s.get_num_coordinates(g)) for g in geometries),
                parts=sum(len(polygons(g)) for g in geometries),
                holes=sum(len(p.interiors) for g in geometries for p in polygons(g)))


def clean(geometries, ranks, min_island_km2=MIN_ISLAND_KM2):
    # Every named unit keeps its principal landmass, even if the entire unit is a
    # small island. Also retain that island in any enclosing coarser layer.
    anchors = s.STRtree([max(polygons(g), key=lambda p: p.area).representative_point()
                        for g in geometries])
    by_rank = {rank: s.STRtree([g for g, r in zip(geometries, ranks) if r == rank])
               for rank in set(ranks)}
    result = []
    for geom, rank in zip(geometries, ranks):
        parts = []
        for part in polygons(geom):
            if area_km2(part) < min_island_km2 and not len(anchors.query(part, predicate="covers")):
                continue
            holes = []
            for ring in part.interiors:
                hole = Polygon(ring)
                # A lake/river void may disappear; an administrative enclave must
                # remain a hole in its neighbour, otherwise lookup would overlap.
                tree = by_rank[rank]
                if any(hole.intersection(tree.geometries[i]).area > 1e-10
                       for i in tree.query(hole)):
                    holes.append(ring)
            parts.append(Polygon(part.exterior, holes))
        result.append(s.union_all(parts))
    return result


def simplify_areas(rows, tolerance=TOLERANCE):
    """Return display rows plus auditable counts; input rows are never modified."""
    if not rows:
        return [], {}
    originals = [s.geometry.shape(row["geometry"]) for row in rows]
    cleaned = clean(originals, [row["rank"] for row in rows])
    # A coarse grid can collapse a very thin source sliver into an unmatched
    # junction. Refine the grid until both named units and the partition survive.
    for grid in (GRID, GRID / 2, GRID / 10, GRID / 100, 0):
        rounded = [s.set_precision(s.set_precision(g, grid), 0) for g in cleaned]
        if any(g.is_empty for g in rounded):
            continue
        edges = s.union_all([g.boundary for g in rounded])
        faces = list(s.get_parts(s.polygonize(s.get_parts(edges))))
        if s.coverage_is_valid(faces):
            break
    else:
        raise ValueError("Administrative partition is not edge-matched")
    reduced = s.coverage_simplify(faces, tolerance)
    if not s.coverage_is_valid(reduced):
        raise ValueError("Simplification broke administrative topology")
    tree = s.STRtree(rounded)
    members = defaultdict(list)
    source_overlaps = {}
    conflicts = 0
    for face, small in zip(faces, reduced):
        owners = [int(i) for i in tree.query(face.representative_point(), predicate="within")]
        accepted = []
        # Grid rounding can create sub-pixel overlap slivers between neighbours
        # that did not overlap in the source. Give each such face to the unit
        # covering most of its original area. Preserve genuine source overlaps
        # and the intentional containment between different ranks.
        if len({rows[i]['rank'] for i in owners}) < len(owners):
            owners.sort(key=lambda i: (-cleaned[i].intersection(face).area, rows[i]['id']))
        for i in owners:
            compatible = True
            for j in accepted:
                if rows[i]['rank'] != rows[j]['rank']:
                    continue
                pair = tuple(sorted((i, j)))
                if pair not in source_overlaps:
                    source_overlaps[pair] = originals[i].intersection(originals[j]).area > 1e-10
                if not source_overlaps[pair]:
                    compatible = False
                    conflicts += 1
                    break
            if compatible:
                accepted.append(i)
                members[i].append(small)
    output = []
    for i, row in enumerate(rows):
        geometry = s.union_all(members[i])
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Lost/invalid display unit: {row['id']}")
        center = Point(row["center"])
        if not geometry.covers(center):
            center = max(polygons(geometry), key=lambda p: p.area).representative_point()
        output.append(dict(row, geometry=mapping(geometry), center=[round(center.x, 6), round(center.y, 6)]))
    return output, dict(before=counts(originals), after=counts([s.geometry.shape(r["geometry"]) for r in output]),
                        partition_faces=len(faces), grid_degrees=grid, coverage_valid=True,
                        rounding_overlap_faces_resolved=conflicts)


def simplify_land(geometries):
    # Land is only a background outline, with no locality lookup semantics.
    parts = [Polygon(p.exterior) for g in geometries for p in polygons(g)
             if area_km2(p) >= MIN_ISLAND_KM2]
    return [s.simplify(g, .01, preserve_topology=True) for g in parts]
