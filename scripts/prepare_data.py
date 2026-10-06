"""Build a local research database and small, explicitly approximate demo map.

The database retains source attributes and original geometries. The phone receives
selected reference-year features with lightweight, shared-edge display geometry.
No modern border, nearest seat, or undocumented temporal join becomes a county.
"""
from collections import Counter, defaultdict
import io
import json
from pathlib import Path
import sqlite3
import zipfile

import openpyxl
import shapefile
from pyproj import Transformer
from shapely.geometry import shape, mapping, box, Point
from shapely.ops import transform, unary_union
from shapely import make_valid
from shapely.prepared import prep
from history_periods import CATALOG, YEARS, REGION_CODES, DEFAULT_YEAR, period_at, reference_years, reference_layer_available
from historical_territories import region as territory_region, CN_POLITIES, VIETNAM_CONTEXT
from prefecture_names import PrefectureNames
from korean_boundaries import load_upper_areas, SILLA_YEAR, GORYEO_YEAR, SOURCE_BASES
from korean_periods import ROWS as KOREAN_CENTERS, SILLA_SOURCE, GORYEO_SOURCE
from historical_names import korean_name, korean_native, search_names, GROUP_ALIASES
from display_geometry import simplify_areas, simplify_land, counts as geometry_counts
from boundary_topology import compile_directory
from fileutil import json_text, sha256_file, write_json

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
OUT = ROOT / "data/processed"
APP = OUT / "android"
CHGIS_OPEN_END_YEAR = 1914  # CHGIS and Ming military rows past this year are open-ended placeholders.
SUPERSEDED_PREFECTURES = {"永平府"}  # Replaced by the adjoining Ming atlas reference pair at DEFAULT_YEAR.
JOSEON_REFERENCE_YEAR = 1864  # Single dated snapshot used for the Japan and Korea references.
# Reference years, not dynasty-wide unions or claims of political ownership.
PERIODS = {p["id"]: p["year"] for p in CATALOG if p["region"] == "cn"}
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
CREATE TABLE snapshot(feature_id TEXT REFERENCES feature(id), year INTEGER,
 UNIQUE(feature_id,year));
CREATE TABLE display_snapshot(feature_id TEXT REFERENCES feature(id), context_year INTEGER, reference_year INTEGER,
 UNIQUE(feature_id,context_year));
"""


def dump(value):
    return json_text(value, compact=True, default=str)


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
        ("korea-silla", SILLA_SOURCE, "AKS historical facts; manually reviewed reference city points, no source map redistribution"),
        ("korea-goryeo", GORYEO_SOURCE, "NIKH historical facts; manually reviewed reference city points, no source map redistribution"),
        ("atlas-ming-liaodong", "https://geojsoncn.com/cn-historical-atlas/#f=ming", "Yutu public map; underlying Historical Atlas copyright retained. Single-area local research reference, not a redistribution license."),
        ("ming-daning-seat", "https://www.chnmuseum.cn/zp/zpml/csp/202008/t20200826_247448.shtml", "National Museum historical account; city-reference coordinates from CHGIS, subject to CHGIS source terms"),
        ("zheng-wu-prefecture", "https://doi.org/10.6084/m9.figshare.30518417", "CC BY 4.0; Yichen Zheng and Tinghai Wu; ResearchArea prefectures only, not simulated counties"),
        ("chgis-county", "https://doi.org/10.7910/DVN/Q9VOF5", "CC0 metadata; bundled README restricts redistribution; local research only pending clarification"),
        ("chgis-pref-point", "https://doi.org/10.7910/DVN/WW1PD6", "CHGIS EULA; no public redistribution"),
        ("chgis-pref-polygon", "https://doi.org/10.7910/DVN/I0Q7SM", "CHGIS EULA; no public redistribution"),
        ("codh", "https://geoshape.ex.nii.ac.jp/kg/", "CC-BY-NC-4.0; CODH / NIHU attribution"),
        ("hisgeo", "https://www.hisgeo.info/wiki/조선_행정구역_DB", "Nonprofit research with attribution; rehosting entire database restricted"),
        ("ming-military", "https://doi.org/10.7910/DVN/5RUXK8", "CC0 metadata conflicts with Academic Use Only / GPL README; local research pending clarification"),
        ("cliopatria", "https://github.com/Seshat-Global-History-Databank/cliopatria/tree/v0.2.1", "CC BY 4.0; Seshat Global History Databank; approximate polity reference outlines"),
    ]
    con.executemany("INSERT INTO source VALUES (?,?,?)", sources)
    source_urls = {s[0]: s[1] for s in sources}
    features, issues, stats = [], [], Counter()

    def store(fid, src, sid, region, kind, name, attributes, geom, start=None, end=None,
              flags=None, include=False, parent="", subtitle="", history=None, rank=1, system="民政",
              periods=None, years=None, layer="administrative", names_by_year=None, native_name="", label_id=None,
              parents_by_year=None, time_region=None, native_names_by_year=None, geometry_year=None, display_geometry=None):
        flags = list(flags or [])
        if not geom.is_valid:
            flags.append("invalid_source_geometry")
        if geom.is_empty:
            flags.append("empty_geometry")
        if start is not None and end is not None:
            if start > end:
                flags.append("reversed_years")
            if (src.startswith("chgis") or src == "ming-military") and (start > CHGIS_OPEN_END_YEAR or end > CHGIS_OPEN_END_YEAR):
                flags.append("implausible_chgis_year")
        con.execute("INSERT INTO feature VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            fid, src, str(sid), region, kind, name, start, end,
            dump(attributes), dump(mapping(geom)), dump(flags)))
        stats[src + ":raw"] += 1
        if flags:
            issues.append({"id": fid, "name": name, "issues": flags})
        blocked = {"empty_geometry", "reversed_years", "implausible_chgis_year", "duplicate_source_id", "ambiguous_polity_identity"}
        if not (include or periods or years) or blocked.intersection(flags):
            return
        if display_geometry is not None:
            geom = display_geometry
        if not geom.is_valid:
            geom = make_valid(geom)
        if geom.geom_type not in {"Point", "Polygon", "MultiPolygon"}:
            issues.append({"id": fid, "issues": ["unsupported_repaired_geometry"]})
            return
        small = geom.simplify(0.0003, preserve_topology=True)
        center = small.representative_point()
        if layer == "territory":
            # Place the label within the study region without clipping the source territory.
            focal_area = small.intersection(study_geometry)
            if not focal_area.is_empty and focal_area.area > 0:
                center = focal_area.representative_point()
        if years is None:
            years = [JOSEON_REFERENCE_YEAR] if region in {"jp", "kr"} else [y for y in YEARS if start <= y <= end]
        for profile in periods or [region]:
            con.execute("INSERT INTO baseline VALUES (?,?)", (fid, profile))
        con.executemany("INSERT INTO snapshot VALUES (?,?)", [(fid, year) for year in years])
        features.append({"id": fid, "name": name, "region": region, "kind": kind,
            "years": years, "layer": layer,
            "time_region": time_region or region, "names_by_year": names_by_year or {},
            "parents_by_year": parents_by_year or {}, "native_names_by_year": native_names_by_year or {}, "native_name": native_name, "label_id": label_id or fid,
            "source_name": attributes.get("Name", name), "source_wikipedia": attributes.get("Wikipedia", ""),
            "periods": periods or [], "begin_year": start, "end_year": end, "geometry_year": geometry_year,
            "rank": rank, "parent": parent, "note": subtitle, "system": system,
            "source": source_urls[src], "history": history or [],
            "center": [round(center.x, 6), round(center.y, 6)],
            "geometry": mapping(small)})
        stats[src + ":published"] += 1
        if DEFAULT_YEAR in years:
            stats[src + ":baseline"] += 1

    # Preserve complete time series; export the union of supported reference years.
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
            if begin in PERIODS.values() or end in PERIODS.values():
                flags.append("reference_transition_year")
            if not a.get("NAME_CH"):
                flags.append("missing_name")
            if a.get("TYPE_CH") == "非政区国土":
                flags.append("non_administrative_geography")
            periods = [key for key, year in PERIODS.items()
                       if begin is not None and end is not None and begin <= year <= end
                       and a.get("TYPE_CH") != "非政区国土"]
            years = [year for year in YEARS if begin is not None and end is not None and begin <= year <= end
                     and a.get("TYPE_CH") != "非政区国土"]
            history = [f"{begin}—{end}：{a.get('NAME_CH', '')}"]
            if a.get("BEG_CHG_TY"):
                history.append("此段记录起因：" + a["BEG_CHG_TY"])
            if a.get("END_CHG_TY"):
                history.append("此段记录终因：" + a["END_CHG_TY"])
            note = "历史行政区划时序资料。"
            note += "治所点不能用于判定县界。" if geom.geom_type == "Point" else "边界经过简化，附近归属仅供参考。"
            if "reference_transition_year" in flags:
                note += "此段记录在某个参考年内有变更，具体日期待核。"
            typename = a.get("TYPE_CH", "")
            system = "土司" if any(t in typename for t in ("宣抚", "宣慰", "安抚", "招讨", "长官", "土", "羁縻", "御夷")) else "军事" if any(t in typename for t in ("卫", "所", "都司")) else "民政"
            label_kind = typename + ("治所" if geom.geom_type == "Point" else "辖区") if typename else kind
            store(f"{src}:{i}", src, a.get("SYS_ID"), "cn", label_kind,
                  a.get("NAME_CH") or a.get("NAME_PY") or "未名", a, geom,
                  begin, end, flags, subtitle=note, history=history, rank=rank, system=system, periods=periods, years=years)

    names = PrefectureNames(con)
    for i, a, geom in read_shp(RAW / "china-prefectures-zheng-wu.zip", "ResearchArea"):
        year = int(a["YEAR"].removesuffix("AD"))
        name, evidence = names.resolve(a, geom) if year in {2,742,1102} else (None, "unselected_reference_year")
        attrs = dict(a, layer="ResearchArea", name_evidence=evidence)
        store(f"zheng-wu-prefecture:{year}:{a['PrefID']}", "zheng-wu-prefecture", str(a['PrefID']),
              "cn", "郡国辖区" if year == 2 else "州府辖区", name or a["PrefNAM"], attrs, geom,
              year, year, years=[year] if name else [], rank=1,
              flags=[] if name else [evidence],
              subtitle="据历史地图集数字化的郡州级参考辖界；不采用该研究的模拟县界。")

    for i, a, geom in read_shp(RAW / "ming-garrisons.zip"):
        begin, end = a.get("beg_yr"), a.get("end_yr")
        corrected = None
        flags = []
        note = "明代军事驻地点，未提供辖区边界；不能据此推断民政归属。原数据终年可能为明末截止标记。"
        if a.get("wei_id") == 22 and a.get("name_ch") == "铁岭卫":
            anchors = con.execute("SELECT id,geometry_json FROM feature WHERE source='chgis-county' "
                                  "AND name='铁岭县' AND begin_year=1664").fetchall()
            if len(anchors) != 1 or any(y < 1393 for y in YEARS if begin <= y <= end):
                raise ValueError("Tieling reference requires review for this timeline")
            anchor, geometry = anchors[0]
            corrected = shape(json.loads(geometry))
            a = dict(a, display_location_anchor=anchor,
                     location_evidence="https://zh.wikisource.org/wiki/讀史方輿紀要/卷三十七",
                     same_city_evidence="https://zh.wikisource.org/wiki/嘉慶重修一統志",
                     location_note="1393年迁银州故城，清改卫为铁岭县；借同城县治点作卫城参考，非衙署实测点")
            flags.append("source_location_corrected_to_historical_city")
            note += "原始坐标误在海州附近；据迁治记载及同城铁岭县治参考点校正，原坐标留存研究库。"
        store(f"ming-military:{i}", "ming-military", a.get("wei_id"), "cn",
              "卫所驻地", a.get("name_ch") or a.get("name_py"), a, geom, begin, end,
              periods=[key for key, year in PERIODS.items()
                       if begin is not None and end is not None and begin <= year <= end],
              years=[year for year in YEARS if begin is not None and end is not None and begin <= year <= end],
              subtitle=note, flags=flags, display_geometry=corrected,
              history=[f"{begin}—{end}：{a.get('name_ch', '')}"], rank=2, system="军事")

    # The adjoining Yongping/Liaodong pair comes from one atlas layer. Keep each
    # complete source geometry; do not buffer, bridge, or splice source boundaries.
    ming_admin = json.loads((RAW / "ming-admin-1582.geojson").read_text())["features"]
    for name in ("辽东都司", "永平府"):
        matches = [f for f in ming_admin if f["properties"].get("name") == name]
        if len(matches) != 1 or matches[0]["geometry"]["type"] not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"Missing or ambiguous Ming administrative polygon: {name}")
        source = matches[0]
        store("atlas-ming-liaodong:" + source["properties"]["id"], "atlas-ming-liaodong", source["properties"]["id"],
              "cn", "都司辖区参考" if name == "辽东都司" else "府级辖区参考", name,
              dict(source["properties"], source_year=1582, original_layer="ming-ad1582",
                   reviewed_scope="adjoining Yongping-Liaodong source pair"),
              shape(source["geometry"]), years=[DEFAULT_YEAR], periods=["ming"], rank=1,
              system="军事" if name == "辽东都司" else "民政", geometry_year=1582,
              flags=["third_party_atlas_reference", "individual_garrison_boundaries_unavailable"],
              subtitle="1582年永平府—辽东都司同源参考面，用于1585年明代背景；不是逐卫、逐县界。未强行贴合异年朝鲜边界。")

    # Daning moved to Baoding in 1403. Represent the documented host city only;
    # neither the old frontier area nor a precise office-site coordinate is implied.
    host = con.execute("SELECT id,source_id,geometry_json FROM feature WHERE source='chgis-pref-point' "
                       f"AND name='保定府' AND begin_year<={DEFAULT_YEAR} AND end_year>={DEFAULT_YEAR}").fetchall()
    if len(host) != 1:
        raise ValueError("Ambiguous Baoding host-city reference")
    anchor_id, anchor_source_id, host_geometry = host[0]
    store("ming-daning-seat:baoding", "ming-daning-seat", "daning-at-baoding", "cn", "都司驻城参考", "大宁都司",
          {"host_city":"保定府", "host_feature_id":anchor_id, "host_source_id":anchor_source_id,
           "move_year":1403, "position_basis":"CHGIS prefectural seat as a city reference, not the military office location"},
          shape(json.loads(host_geometry)), years=[DEFAULT_YEAR], periods=["ming"], rank=1, system="军事", parent="保定府",
          flags=["host_city_reference_not_office_site"],
          subtitle="1403年迁驻保定；以有来源的保定府治坐标表示驻城，非都司衙署实测位置。不将明初大宁旧辖区套用于晚明。")

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

    # These early references supply administrative names and centers only.
    for i, (year, kind, name, native, lon, lat, citation) in enumerate(KOREAN_CENTERS):
        period = "silla" if year == SILLA_YEAR else "goryeo"
        store(f"korea-{period}:{i}", f"korea-{period}", str(i), "kr", kind, name,
              {"citation": citation, "coordinate_basis": "approximate reference city"},
              Point(lon, lat), year, year, years=[year], rank=2 if "小京" in kind or "牧治" in kind else 1,
              native_name=native, names_by_year={str(year): name},
              native_names_by_year={str(year): native},
              subtitle="新罗九州五小京／高丽八牧行政中心参考；坐标为历史所在地的城市级参考点，非衙署实测点；未提供完整郡县或辖界。")

    # Retain original workbook rows; histories are evidence, not invented events.
    histories = defaultdict(list)
    korean_summary = defaultdict(list)
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
                if doc == "summary":
                    korean_summary[a.get("admid_group")].append(a)
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
            hanja = korean_name(korean_summary, group, 1864)
            if include and not hanja:
                issues.append({"id": f"hisgeo:{level}:{i}", "issues": ["no_valid_dated_hanja_name"]})
                include = False
            store(f"hisgeo:{level}:{i}", "hisgeo", a.get("admid_gis"), "kr",
                  "道级辖区" if level == "lv1" else "府郡县辖区", hanja or name, a, geom,
                  include=include, parent=korean_name(korean_summary, parent, 1864) or "", rank=1 if level == "lv1" else 2,
                  names_by_year={"1864": hanja} if hanja else {}, native_name=name,
                  native_names_by_year={"1864": a.get("nm_kr_1864")} if level == "lv2" else {},
                  label_id="hisgeo:" + GROUP_ALIASES.get(group, group),
                  subtitle="1864年地方辖区参考；汉字名按来源沿革表核对。",
                  history=histories.get(group, []),
                  flags=["source_name_conflict"] if level == "lv1" and a.get("nm_kr_1864", "").rstrip("도") not in ("", group) else [])

    # The publisher also provides dated seat points. Use its named baseline membership,
    # not an inferred county outline, to support pre-1864 Joseon reference years.
    for i, a, geom in read_shp(RAW / "korea-joseon-spatial.zip", "all_pt"):
        if a.get("adm_level") not in {"lv1", "lv2"}:
            continue
        group = a.get("admid_grp", "")
        baselines = set(a.get("base_year", "").split("/"))
        names = {str(y): korean_name(korean_summary, group, y) for y in YEARS if f"s{y}" in baselines}
        years = [int(y) for y, name in names.items() if name]
        names = {y: name for y, name in names.items() if name}
        parent = group.split("_")[0] if "_" in group else ""
        store(f"hisgeo:seat:{i}", "hisgeo", a.get("admid_gis"), "kr", "治所点位",
              next(iter(names.values()), group), a, geom, years=years,
              names_by_year=names, native_name=group.split("_")[-1],
              native_names_by_year={str(y): a.get(f"nm_kr_{y}") for y in years} if a.get("adm_level") == "lv2" else {},
              label_id="hisgeo:" + GROUP_ALIASES.get(group, group),
              parents_by_year={str(y): korean_name(korean_summary, parent, y) or "" for y in years},
              rank=1 if a.get("adm_level") == "lv1" else 2,
              subtitle="来源基准年的历史治所坐标，仅供点位参考，不表示辖界。")

    # These contemporary geographic masks drive the UI's regional menu ONLY. They never
    # become historical borders, clip historical geometry, or determine historical ownership.
    countries = json.loads((RAW / "natural-earth-countries-10m.geojson").read_text())["features"]
    region_shapes = defaultdict(list)
    for f in countries:
        code = f["properties"]["ADM0_A3"]
        if code in REGION_CODES:
            region_shapes[REGION_CODES[code]].append(make_valid(shape(f["geometry"])))
    regions = {key: unary_union(parts) for key, parts in region_shapes.items()}
    study_geometry = unary_union(list(regions.values()))
    study_area = prep(study_geometry)
    (APP / "regions.json").write_text(dump([
        {"id": key, "region": key, "layer": "ui_region", "geometry": mapping(g.simplify(0.03, preserve_topology=True))}
        for key, g in regions.items()]))

    # Research-only scope masks for the Chinese dynasty filter. These NEVER ship
    # as map features, labels, search results or location-query fallbacks.
    with zipfile.ZipFile(RAW / "cliopatria.geojson.zip") as archive:
        member = next(n for n in archive.namelist() if n.endswith(".geojson"))
        polities = json.load(archive.open(member))["features"]
    stats["cliopatria:archive_rows"] = len(polities)
    for i, f in enumerate(polities):
        a = f["properties"]
        begin, end = a["FromYear"], a["ToYear"]
        years = [year for year in YEARS if begin <= year <= end]
        if not years or a["Type"] != "POLITY" or a["Name"].startswith("(") or a.get("Components"):
            continue
        geom = shape(f["geometry"])
        if not study_area.intersects(geom):
            continue
        flags = ["approximate_polity_outline"]
        if a["Name"] == "Đại Việt" and a.get("Wikipedia") == "Đại Việt":
            flags.append("ambiguous_polity_identity")
        if a["Name"] in {"Ngô Dynasty", "Later Jin Dynasty", "Đại Việt", "French Indochina"}:
            flags.append("reviewed_display_name")
        region = territory_region(a["Name"])
        store(f"cliopatria:{i}", "cliopatria", str(i), region, "政权参考范围",
              a["Name"], a, geom, begin, end, flags=flags, years=years,
              time_region="vn" if a["Name"] in VIETNAM_CONTEXT else region,
              label_id="cliopatria:" + a["Name"],
              layer="territory", rank=0, system="政权", subtitle="粗尺度历史疆域参考，不作为府县界或精确归属依据。")

    # Import complete source boundaries; bundled maps retain trace/date provenance.
    # Neither polity outlines nor later borders fill any missing province.
    for year in (SILLA_YEAR, GORYEO_YEAR):
        areas = load_upper_areas(RAW, year, bundled=ROOT / "data/reference/korean-upper", require_complete=True)
        source_id = f"korea-upper-source:{year}"
        provenance = areas[0]["source"]
        con.execute("INSERT INTO source VALUES (?,?,?)",
                    (source_id, provenance["source_url"], provenance["rights"]))
        source_urls[source_id] = provenance["source_url"]
        for area in areas:
            fid = f"korea-upper:{year}:{area['key']}"
            attrs = dict(area["attributes"], provenance=area["source"])
            store(fid, source_id, area["key"], "kr", "州级辖区" if year == SILLA_YEAR else "道／边境区级辖区",
                  area["name"], attrs, area["geometry"], year, year, years=[year], rank=1,
                  native_name=area["native"], names_by_year={str(year): area["name"]},
                  native_names_by_year={str(year): area["native"]}, geometry_year=provenance.get("map_year"))
            features[-1].update(boundary_basis=provenance["boundary_basis"], boundary_source_id=source_id,
                                boundary_date_precision=provenance.get("date_precision", "reference_year"))
            seats = [f for f in features if f["region"] == "kr" and f["name"] == area["name"]
                     and f["geometry"]["type"] == "Point" and year in f["years"]
                     and area["geometry"].buffer(.05).covers(Point(f["center"]))]
            if len(seats) == 1:
                seat = seats[0]
                features[-1].update(label_id=seat["label_id"], label_center=seat["center"],
                                    label_anchor_id=seat["id"])
                if not area["geometry"].covers(Point(seat["center"])):
                    issues.append({"id": fid, "issues": ["source_map_seat_near_coastal_edge"],
                                   "seat_id": seat["id"], "distance_degrees": area["geometry"].distance(Point(seat["center"]))})

    # Keep the research union outside the APK. Each on-device snapshot has one global
    # year; loading a year never parses every other year's polygon caches into RAM.
    with (OUT / "published.jsonl").open("w") as stream:
        for feature in features:
            stream.write(dump(feature) + "\n")
    snapshot_dir = APP / "snapshots"
    snapshot_dir.mkdir(exist_ok=True)
    # Do not retain obsolete snapshots after removing unsupported menu choices.
    for old in snapshot_dir.glob("*.jsonl"):
        if old.stem not in {str(year) for year in YEARS}:
            old.unlink()
    counts_by_year = {}
    references = {}
    default_counts = Counter()
    source_shapes = {f["id"]: shape(f["geometry"]) for f in features}
    geometry_report = {}
    fixed_display = {}
    for region in ("kr", "jp"):
        region_years = sorted({y for f in features if f["region"]==region and f["layer"]=="administrative"
                              and f["geometry"]["type"]!="Point" for y in f["years"]})
        for local_year in region_years:
            local = [f for f in features if f["region"]==region and f["layer"]=="administrative"
                     and f["geometry"]["type"]!="Point" and local_year in f["years"]]
            simplified, report = simplify_areas(local)
            fixed_display.update({f["id"]:f for f in simplified})
            geometry_report[f"{region}-{local_year}"] = report
    for year in YEARS:
        local_years = reference_years(year)
        references[str(year)] = local_years
        cn_year = local_years["cn"]
        cn_period = period_at("cn", cn_year) if cn_year is not None else None
        allowed = CN_POLITIES.get(cn_period["id"], set()) if cn_period else set()
        chinese_polities = [f for f in features if f["layer"] == "territory" and f["source_name"] in allowed and cn_year in f["years"]]
        footprint = unary_union([source_shapes[f["id"]] for f in chinese_polities])
        # Small display-source discrepancies must not invent clipped administrative borders.
        # Gate by the source center / majority overlap; keep accepted source geometry whole.
        tolerance = footprint.buffer(0.03)
        preferred = [f for f in features if f["id"].startswith("zheng-wu-prefecture:") and cn_year in f["years"]]
        preferred_area = unary_union([source_shapes[f["id"]] for f in preferred])
        preferred_names = {alias for f in preferred for alias in search_names(f["name"])}
        rows = []
        excluded_cn = 0
        for feature in features:
            local_year = local_years.get(feature["time_region"])
            if feature["layer"] != "administrative" or not reference_layer_available(feature["region"], feature["rank"], year):
                continue
            if local_year is None or local_year not in feature["years"]:
                continue
            if feature["region"] == "cn":
                if cn_year == DEFAULT_YEAR and feature["id"].startswith("chgis-pref-polygon:") and feature["name"] in SUPERSEDED_PREFECTURES:
                    continue  # Retained in the research DB; the adjoining atlas pair is displayed.
                geom = source_shapes[feature["id"]]
                if feature["id"].startswith("zheng-wu-prefecture:"):
                    rows.append(feature)
                    continue
                if feature["id"].startswith("chgis-pref-polygon:") and preferred:
                    if preferred_names.intersection(search_names(feature["name"])) or (
                            geom.intersects(preferred_area) and geom.intersection(preferred_area).area > geom.area * .5):
                        continue
                accepted = tolerance.covers(geom) if geom.geom_type == "Point" else (
                    geom.intersects(tolerance) and geom.intersection(tolerance).area >= geom.area * 0.5)
                if not accepted:
                    excluded_cn += 1
                    continue
            rows.append(feature)
        # Keep a separate label anchor: area geometry and its interior center
        # continue to serve containment; names use dated seats when identified.
        seats = [f for f in features if f["geometry"]["type"] == "Point" and
                 local_years.get(f["time_region"]) in f["years"] and
                 f["id"].startswith(("chgis-pref-point:", "hisgeo:seat:"))]
        anchors = {}
        for area in rows:
            if area["geometry"]["type"] == "Point":
                continue
            local_year = local_years[area["time_region"]]
            area_names = set(search_names(area["name"]))
            area_buffer = []  # Built on the first seat that passes the cheap tests.

            def covers_seat(seat):
                if not area_buffer:
                    area_buffer.append(source_shapes[area["id"]].buffer(.03))
                return area_buffer[0].covers(source_shapes[seat["id"]])
            matches = [seat for seat in seats if seat["region"] == area["region"] and
                       seat["rank"] == area["rank"] and
                       (seat["label_id"] == area["label_id"] if area["region"] == "kr" else
                        not area_names.isdisjoint(search_names(seat["name"]))) and
                       covers_seat(seat)]
            # Ambiguous seats are kept as an area-center label, never guessed.
            positions = {tuple(seat["center"]) for seat in matches}
            if len(positions) == 1:
                seat = matches[0]
                anchors[area["id"]] = {"label_center": seat["center"], "label_anchor_id": seat["id"]}
        # The polygon's name is authoritative for this displayed reference. Do not
        # label the same area again via an overlapping prefecture-seat record,
        # including alternate names around a within-year administrative reform.
        mapped_prefectures = unary_union([source_shapes[f["id"]] for f in rows
            if f["region"] == "cn" and f["rank"] == 1 and f["geometry"]["type"] != "Point"])
        rows = [f for f in rows if not (f["id"].startswith("chgis-pref-point:") and
                                       mapped_prefectures.covers(source_shapes[f["id"]]))]
        # A mapped county polygon takes label priority over its duplicate seat point.
        polygon_entities = {f["label_id"] for f in rows if f["region"] == "kr" and f["geometry"]["type"] != "Point"}
        rows = [f for f in rows if not (f["id"].startswith("hisgeo:seat:") and f["label_id"] in polygon_entities)]
        chinese = [f for f in rows if f["region"] == "cn" and f["geometry"]["type"] != "Point"]
        simplified, report = simplify_areas(chinese)
        if chinese:
            geometry_report[f"cn-{year}"] = report
        display = {**fixed_display, **{f["id"]: f for f in simplified}}
        rows = [display.get(f["id"], f) for f in rows]
        if year == DEFAULT_YEAR:
            default_counts.update(f["id"].split(":")[0] for f in rows)
        with (snapshot_dir / f"{year}.jsonl").open("w") as stream:
            for feature in rows:
                local_year = local_years[feature["time_region"]]
                row = dict(feature, year=local_year, context_year=year, **anchors.get(feature["id"], {}))
                if row["region"] == "kr":
                    row["name"] = row["names_by_year"][str(local_year)]
                    row["native_name"] = (row["native_names_by_year"].get(str(local_year)) if row["id"].startswith("korea-") else
                        korean_native(row["name"], row["label_id"].removeprefix("hisgeo:"),
                                      row["native_names_by_year"].get(str(local_year))))
                    row["parent"] = row["parents_by_year"].get(str(local_year), row["parent"])
                if row["region"] == "kr" and local_year in (SILLA_YEAR, GORYEO_YEAR) and row["geometry"]["type"] != "Point":
                    if row.get("inferred") or row.get("boundary_basis") not in SOURCE_BASES:
                        raise ValueError(f"Undocumented early Korean boundary in export: {row['id']}")
                row.pop("names_by_year", None)
                row.pop("parents_by_year", None)
                row.pop("native_names_by_year", None)
                row["search_names"] = search_names(row["name"])
                stream.write(dump(row) + "\n")
                con.execute("INSERT INTO display_snapshot VALUES (?,?,?)", (feature["id"], year, local_year))
        counts_by_year[str(year)] = dict(Counter(f["layer"] for f in rows))
        counts_by_year[str(year)]["excluded_cn_outside_selected_dynasty"] = excluded_cn
    (APP / "map.jsonl").write_bytes((snapshot_dir / f"{DEFAULT_YEAR}.jsonl").read_bytes())
    (APP / "timeline.json").write_text(dump(CATALOG))
    (APP / "reference-years.json").write_text(dump(references))
    for key in list(stats):
        if key.endswith(":baseline"):
            del stats[key]
    for source, count in default_counts.items():
        stats[source + ":baseline"] = count
    con.commit()
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    temp_db.replace(OUT / "history.sqlite")
    if (APP / "map.json").exists():
        (APP / "map.json").unlink()
    land = json.loads((RAW / "natural-earth-land-10m.geojson").read_text())
    coast = []
    for f in land["features"]:
        g = shape(f["geometry"]).intersection(box(70, 0, 160, 65))
        if not g.is_empty and g.geom_type in ("Polygon", "MultiPolygon"):
            coast.append(g)
    light_coast = simplify_land(coast)
    geometry_report["land"] = dict(before=geometry_counts(coast), after=geometry_counts(light_coast))
    (APP / "land.json").write_text(dump([mapping(g) for g in light_coast]))
    write_json(OUT / "display-geometry.json", geometry_report)
    write_json(OUT / "quality.json", {
        "counts": stats, "issues": issues,
        "baseline": {"context_year": DEFAULT_YEAR, "regional_years": reference_years(DEFAULT_YEAR)},
        "snapshots": counts_by_year,
        "periods": {key: {"year": year, "features": sum(key in f["periods"] for f in features),
                          "points": sum(key in f["periods"] and f["geometry"]["type"] == "Point" for f in features)}
                    for key, year in PERIODS.items()},
        "limitations": ["China county boundaries missing", "No Taiwan Qing backprojection into earlier periods", "No complete polity/province hierarchy",
                        "Display-only water holes and tiny islands removed; shared-edge VW simplification 0.008 degrees, 0.001-degree grid; no survey accuracy", "Japan post-Meiji district changes not fully resolved"],
    })
    manifest = [{"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
                 "sha256": sha256_file(p)}
                for p in sorted(RAW.iterdir()) if p.is_file()]
    write_json(OUT / "input-manifest.json", manifest)
    compile_directory(APP)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Android features: {len(features)}; map: {(APP / 'map.jsonl').stat().st_size / 1024**2:.1f} MiB")


if __name__ == "__main__":
    main()
