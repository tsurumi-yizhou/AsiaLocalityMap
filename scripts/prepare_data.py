"""Build a local research database and small, explicitly approximate demo map.

The database retains source attributes and original geometries. The phone receives
only baseline features, simplified to 0.0003 degrees for display and lookup.
No modern border, nearest seat, or undocumented temporal join becomes a county.
"""
from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import zipfile

import openpyxl
import shapefile
from pyproj import Transformer
from shapely.geometry import shape, mapping, box
from shapely.ops import transform, unary_union
from shapely import make_valid

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
OUT = ROOT / "data/processed"
APP = OUT / "android"
SCHEMA = """
CREATE TABLE source(id TEXT PRIMARY KEY, url TEXT NOT NULL, rights TEXT NOT NULL);
CREATE TABLE feature(id TEXT PRIMARY KEY, source TEXT REFERENCES source(id),
 source_id TEXT, region TEXT, kind TEXT, name TEXT, begin_year INTEGER, end_year INTEGER,
 attributes_json TEXT NOT NULL, geometry_json TEXT NOT NULL, quality_json TEXT NOT NULL);
CREATE INDEX by_time ON feature(region,begin_year,end_year);
CREATE INDEX by_name ON feature(name);
CREATE TABLE document_row(id INTEGER PRIMARY KEY, source TEXT REFERENCES source(id),
 document TEXT, sheet TEXT, row_number INTEGER, attributes_json TEXT NOT NULL);
CREATE TABLE baseline(feature_id TEXT REFERENCES feature(id), profile TEXT,
 UNIQUE(feature_id,profile));
"""


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def read_shp(archive, token=None):
    z = zipfile.ZipFile(archive)
    names = [n for n in z.namelist() if n.endswith(".shp") and (token is None or token in n)]
    if len(names) != 1:
        raise ValueError(f"Ambiguous layer {archive}: {names}")
    stem = names[0][:-4]
    reader = shapefile.Reader(**{ext: io.BytesIO(z.read(stem + "." + ext))
                                for ext in ("shp", "shx", "dbf")}, encoding="utf-8")
    projection = z.read(stem + ".prj").decode()
    converter = Transformer.from_crs(projection, "EPSG:4326", always_xy=True)
    for i, record in enumerate(reader.iterShapeRecords()):
        geom = shape(record.shape.__geo_interface__)
        if "PROJCS" in projection:
            geom = transform(converter.transform, geom)
        yield i, record.record.as_dict(), geom


def main():
    APP.mkdir(parents=True, exist_ok=True)
    temp_db = OUT / "history.build.sqlite"
    if temp_db.exists():
        temp_db.unlink()
    con = sqlite3.connect(temp_db)
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    sources = [
        ("chgis-county", "https://doi.org/10.7910/DVN/Q9VOF5", "CC0 metadata; bundled README restricts redistribution; local research only pending clarification"),
        ("chgis-pref-point", "https://doi.org/10.7910/DVN/WW1PD6", "CHGIS EULA; no public redistribution"),
        ("chgis-pref-polygon", "https://doi.org/10.7910/DVN/I0Q7SM", "CHGIS EULA; no public redistribution"),
        ("codh", "https://geoshape.ex.nii.ac.jp/kg/", "CC-BY-NC-4.0; CODH / NIHU attribution"),
        ("hisgeo", "https://www.hisgeo.info/wiki/조선_행정구역_DB", "Nonprofit research with attribution; rehosting entire database restricted"),
        ("ming-military", "https://doi.org/10.7910/DVN/5RUXK8", "CC0 metadata conflicts with Academic Use Only / GPL README; local research pending clarification"),
    ]
    con.executemany("INSERT INTO source VALUES (?,?,?)", sources)
    source_urls = {s[0]: s[1] for s in sources}
    features, issues, stats = [], [], Counter()

    def store(fid, src, sid, region, kind, name, attributes, geom, start=None, end=None,
              flags=None, include=False, parent="", subtitle="", history=None, rank=1, system="民政"):
        flags = list(flags or [])
        if not geom.is_valid:
            flags.append("invalid_source_geometry")
        if geom.is_empty:
            flags.append("empty_geometry")
        if start is not None and end is not None:
            if start > end:
                flags.append("reversed_years")
            if start > 1914 or end > 1914:
                flags.append("implausible_chgis_year")
        con.execute("INSERT INTO feature VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            fid, src, str(sid), region, kind, name, start, end,
            dump(attributes), dump(mapping(geom)), dump(flags)))
        stats[src + ":raw"] += 1
        if flags:
            issues.append({"id": fid, "name": name, "issues": flags})
        blocked = {"empty_geometry", "reversed_years", "implausible_chgis_year", "duplicate_source_id"}
        if not include or blocked.intersection(flags):
            return
        if not geom.is_valid:
            geom = make_valid(geom)
        if geom.geom_type not in {"Point", "Polygon", "MultiPolygon"}:
            issues.append({"id": fid, "issues": ["unsupported_repaired_geometry"]})
            return
        small = geom.simplify(0.0003, preserve_topology=True)
        center = small.representative_point()
        con.execute("INSERT INTO baseline VALUES (?,?)", (fid, region))
        features.append({"id": fid, "name": name, "region": region, "kind": kind,
            "rank": rank, "parent": parent, "note": subtitle, "system": system,
            "source": source_urls[src], "history": history or [],
            "center": [round(center.x, 6), round(center.y, 6)],
            "geometry": mapping(small)})
        stats[src + ":baseline"] += 1

    # Preserve complete point time series; select records intersecting 1644.
    for key, kind, src, rank in [
        ("county-points", "县级治所", "chgis-county", 2),
        ("pref-points", "府级治所", "chgis-pref-point", 1),
        ("pref-polygons", "府级辖区", "chgis-pref-polygon", 1),
    ]:
        path = RAW / ("chgis-" + key + ".zip")
        if not zipfile.is_zipfile(path):
            raise RuntimeError(f"Incomplete required download: {path}")
        rows = list(read_shp(path))
        ids = Counter(str(a.get("SYS_ID")) for _, a, _ in rows)
        for i, a, geom in rows:
            begin, end = a.get("BEG_YR"), a.get("END_YR")
            flags = []
            if ids[str(a.get("SYS_ID"))] > 1:
                flags.append("duplicate_source_id")
            if begin == 1644 or end == 1644:
                flags.append("baseline_transition_year")
            if not a.get("NAME_CH"):
                flags.append("missing_name")
            if a.get("TYPE_CH") == "非政区国土":
                flags.append("non_administrative_geography")
            include = begin is not None and end is not None and begin <= 1644 <= end and a.get("TYPE_CH") != "非政区国土"
            history = [f"{begin}—{end}：{a.get('NAME_CH', '')}"]
            if a.get("BEG_CHG_TY"):
                history.append("此段记录起因：" + a["BEG_CHG_TY"])
            if a.get("END_CHG_TY"):
                history.append("此段记录终因：" + a["END_CHG_TY"])
            note = "明代县府资料。"
            note += "治所点不能用于判定县界。" if geom.geom_type == "Point" else "边界经过简化，附近归属仅供参考。"
            if "baseline_transition_year" in flags:
                note += "此地在基线年内有变更，具体日期待核。"
            typename = a.get("TYPE_CH", "")
            system = "土司" if any(t in typename for t in ("宣抚", "宣慰", "安抚", "招讨", "长官", "土", "羁縻", "御夷")) else "军事" if any(t in typename for t in ("卫", "所", "都司")) else "民政"
            label_kind = typename + ("治所" if geom.geom_type == "Point" else "辖区") if typename else kind
            store(f"{src}:{i}", src, a.get("SYS_ID"), "cn", label_kind,
                  a.get("NAME_CH") or a.get("NAME_PY") or "未名", a, geom,
                  begin, end, flags, include, subtitle=note, history=history, rank=rank, system=system)

    for i, a, geom in read_shp(RAW / "ming-garrisons.zip"):
        begin, end = a.get("beg_yr"), a.get("end_yr")
        store(f"ming-military:{i}", "ming-military", a.get("wei_id"), "cn",
              "卫所驻地", a.get("name_ch") or a.get("name_py"), a, geom, begin, end,
              include=begin is not None and end is not None and begin <= 1644 <= end,
              subtitle="明代军事驻地点，未提供辖区边界；不能据此推断民政归属。原数据终年可能为明末截止标记。",
              history=[f"{begin}—{end}：{a.get('name_ch', '')}"], rank=2, system="军事")

    # Preserve all modernly digitized old countries/districts. Restore only country
    # groupings for Mutsu/Dewa; these remain reference reconstructions, not surveys.
    jp = []
    for path in sorted((RAW / "japan/geojson").glob("*.geojson")):
        rows = json.loads(path.read_text())["features"]
        # Several islands are separate features with the same administrative ID.
        # Union by the publisher's ID; never discard all but the first island.
        assert {f["properties"]["id"] for f in rows} == {path.stem}
        jp.append((rows[0]["properties"], unary_union([make_valid(shape(f["geometry"])) for f in rows])))
    if len(jp) != 891:
        raise ValueError(f"Incomplete Japan download: {len(jp)} / 891")
    country_names = {a["id"]: a["name"] for a, _ in jp if a["id"].startswith("K")}
    mergers = {**{f"K{i:02d}": "陸奥" for i in range(27, 32)}, "K32": "出羽", "K33": "出羽"}
    merged = defaultdict(list)
    for a, geom in jp:
        code = a["id"]
        country = code if code.startswith("K") else a["kuni_id"]
        include = int(country[1:]) < 74
        if code.startswith("K") and code in mergers:
            merged[mergers[code]].append(geom)
            include = False
        name = a["name"] + ("国" if code.startswith("K") else "郡")
        parent = "" if code.startswith("K") else mergers.get(country, country_names[country]) + "国"
        store("codh:" + code, "codh", code, "jp",
              "令制国" if code.startswith("K") else "旧郡", name, a, geom,
              include=include, parent=parent, rank=1 if code.startswith("K") else 2,
              subtitle="江户末期国郡参考边界。原数据含明治成分，郡界尚待逐项核校。")
    for name, geometries in merged.items():
        store("codh:restored:" + name, "codh", "restored:" + name, "jp", "令制国", name + "国",
              {"operation": "union", "members": [k for k, v in mergers.items() if v == name]},
              unary_union([make_valid(g) for g in geometries]), include=True,
              subtitle="依明治分国前名称合并的国界参考图，尚未逐段核校。")

    # Retain original workbook rows; histories are evidence, not invented events.
    histories = defaultdict(list)
    for doc in ("history", "summary", "seats"):
        book = openpyxl.load_workbook(RAW / f"korea-joseon-{doc}.xlsx", read_only=True, data_only=True)
        for sheet in book:
            rows = iter(sheet.values)
            header = next(rows)
            for i, row in enumerate(rows, 2):
                a = dict(zip(header, row))
                if not any(v is not None for v in row):
                    continue
                con.execute("INSERT INTO document_row(source,document,sheet,row_number,attributes_json) VALUES (?,?,?,?,?)",
                            ("hisgeo", doc, sheet.title, i, dump(a)))
                stats["hisgeo:" + doc + "_rows"] += 1
                if doc == "history":
                    histories[a.get("admid_group")].append(f"{a.get('base_year')}：{a.get('hist_contents', '')}")
    for level in ("lv1", "lv2"):
        for i, a, geom in read_shp(RAW / "korea-joseon-spatial.zip", level + "_pg"):
            group = a.get("admid_grp", "")
            # Publisher explicitly says to use base_year, NOT begin/end intervals.
            include = "s1864" in a.get("base_year", "").split("/")
            # nm_kr_1864 has observed conflicting province labels. Use entity key;
            # keep original attributes and expose Korean script without guessing.
            parts = group.split("_")
            name = parts[-1]
            parent = parts[0] if len(parts) > 1 else ""
            store(f"hisgeo:{level}:{i}", "hisgeo", a.get("admid_gis"), "kr",
                  "道级辖区" if level == "lv1" else "府郡县辖区", name, a, geom,
                  include=include, parent=parent, rank=1 if level == "lv1" else 2,
                  subtitle="李氏朝鲜后期参考边界；地名保留原文，汉字名及邑格待校。",
                  history=histories.get(group, []),
                  flags=["source_name_conflict"] if level == "lv1" and a.get("nm_kr_1864", "").rstrip("도") not in ("", group) else [])

    con.commit()
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    temp_db.replace(OUT / "history.sqlite")
    # One feature per line lets Android parse incrementally on small heaps.
    with (APP / "map.jsonl").open("w") as stream:
        for feature in features:
            stream.write(dump(feature) + "\n")
    if (APP / "map.json").exists():
        (APP / "map.json").unlink()
    land = json.loads((RAW / "natural-earth-land-10m.geojson").read_text())
    coast = []
    for f in land["features"]:
        g = shape(f["geometry"]).intersection(box(70, 0, 160, 65))
        if not g.is_empty and g.geom_type in ("Polygon", "MultiPolygon"):
            coast.append(mapping(g.simplify(0.001, preserve_topology=True)))
    (APP / "land.json").write_text(dump(coast))
    (OUT / "quality.json").write_text(json.dumps({
        "counts": stats, "issues": issues,
        "baseline": {"cn": "1644 year-intersection candidates, not a daily snapshot", "jp": "late Edo reference", "kr": "s1864"},
        "limitations": ["China county boundaries missing", "No Taiwan Qing backprojection", "No complete polity/province hierarchy",
                        "Boundary simplification 0.0003 degrees; no survey accuracy", "Japan post-Meiji district changes not fully resolved"],
    }, ensure_ascii=False, indent=2))
    manifest = [{"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in sorted(RAW.iterdir()) if p.is_file()]
    (OUT / "input-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Android features: {len(features)}; map: {(APP / 'map.jsonl').stat().st_size / 1024**2:.1f} MiB")


if __name__ == "__main__":
    main()
