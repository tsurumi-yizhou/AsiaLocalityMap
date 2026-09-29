"""Cache CODH's published country/district GeoJSON, with provenance and retries.

These are late Edo / early Meiji reference boundaries, NOT a 1644 reconstruction.
Run from repository root: .venv/bin/python scripts/fetch_japan.py
"""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/japan"
BASE = "https://geoshape.ex.nii.ac.jp/kg/"


def fetch(relative):
    path = RAW / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        request = urllib.request.Request(BASE + relative, headers={
            "User-Agent": "AsiaLocalityMap/0.1 (nonprofit historical geography research)"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read()
                if relative.endswith("geojson"):
                    value = json.loads(body)
                    assert value["type"] == "FeatureCollection" and value["features"]
                temporary = path.with_suffix(path.suffix + ".part")
                temporary.write_bytes(body)
                temporary.replace(path)
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        time.sleep(0.15)
    return path


def province(code):
    page = fetch(f"resource/{code}.html")
    soup = BeautifulSoup(page.read_text(), "html.parser")
    districts = sorted(set(re.findall(r'G\d{5}(?=\.html)', str(soup))))
    fetch(f"geojson/{code}.geojson")
    for district in districts:
        fetch(f"geojson/{district}.geojson")
    return code, len(districts)


def main():
    index = fetch("resource/index.html")
    codes = sorted(set(re.findall(r'K\d{2}(?=\.html)', index.read_text())))
    if len(codes) != 85:
        raise ValueError(f"Source catalogue changed: expected 85 countries; got {len(codes)}")
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(province, c): c for c in codes}
        for future in concurrent.futures.as_completed(futures):
            try:
                code, count = future.result()
                print(f"{code}: country + {count} districts cached", flush=True)
            except Exception as exc:
                failures.append({"code": futures[future], "error": str(exc)})
                print(f"FAILED {futures[future]}: {exc}", flush=True)
    files = [{"path": str(p.relative_to(ROOT)),
              "url": BASE + str(p.relative_to(RAW)),
              "bytes": p.stat().st_size,
              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(RAW.rglob("*")) if p.is_file() and p.suffix != ".part"]
    (RAW / "manifest.json").write_text(json.dumps({
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "source": BASE, "license": "CC-BY-NC-4.0", "files": files,
        "failures": failures}, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
