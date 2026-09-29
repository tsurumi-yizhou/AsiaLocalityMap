"""Reproduce the non-Japan raw downloads for local nonprofit research.

Source terms are recorded in docs/data-rights.html. This is not a redistribution
tool. Downloads use .part files and check archive integrity before replacement.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
from datetime import datetime, timezone
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
DV = "https://dataverse.harvard.edu/api/"
JOBS = {
    "chgis-county-points.zip": DV + "access/datafile/3048165",
    "chgis-pref-points.zip": DV + "access/datafile/2970286",
    "chgis-pref-polygons.zip": DV + "access/datafile/2966510",
    "chgis-dictionary.zip": DV + "access/datafile/2966673",
    "CHGIS_V6_README.txt": DV + "access/datafile/3048161",
    "ming-garrisons.zip": DV + "access/datafile/3007341",
    "README_MingGarrisons.txt": DV + "access/datafile/3007340",
    "natural-earth-land.geojson": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson",
    "natural-earth-land-10m.geojson": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson",
}
for stem, doi in [("chgis-county-points", "Q9VOF5"), ("chgis-pref-points", "WW1PD6"),
                  ("chgis-pref-polygons", "I0Q7SM"), ("chgis-dictionary", "SNCEAU"),
                  ("chgis-eula", "FDLFJ3"), ("ming-military", "5RUXK8")]:
    JOBS[stem + "-metadata.json"] = DV + "datasets/:persistentId/?persistentId=doi:10.7910/DVN/" + doi
for name, remote in [
    ("spatial.zip", "3/35/Kr_admin_조선_역지사지.zip"),
    ("history.xlsx", "2/22/조선시대_행정구역_이력.xlsx"),
    ("summary.xlsx", "0/08/조선시대_행정구역_이력_요약.xlsx"),
    ("seats.xlsx", "3/31/조선시대_읍치_이력.xlsx"),
]:
    JOBS["korea-joseon-" + name] = "https://www.hisgeo.info/wiki/images/" + quote(remote)
JOBS["korea-hisgeo-source.html"] = "https://www.hisgeo.info/wiki/" + quote("조선_행정구역_DB")
JOBS["japan-kg-index.html"] = "https://geoshape.ex.nii.ac.jp/kg/"


def verify(path):
    if path.name.endswith((".zip", ".xlsx", ".zip.part", ".xlsx.part")):
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"Corrupt archive: {path}")
    elif ".json" in path.name or ".geojson" in path.name:
        json.loads(path.read_text())


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = []
    for filename, url in JOBS.items():
        path = RAW / filename
        if not path.exists():
            partial = path.with_name(path.name + ".part")
            subprocess.run(["curl", "-L", "--fail", "--show-error", "--retry", "3", "--max-time", "1800", url, "-o", str(partial)], check=True)
            verify(partial)
            partial.replace(path)
        verify(path)
        manifest.append({"path": str(path.relative_to(ROOT)), "url": url,
                         "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print(filename, "verified", flush=True)
    (RAW / "source-manifest.json").write_text(json.dumps({"verified_at": datetime.now(timezone.utc).isoformat(), "files": manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
