"""Save unedited tablet screenshots using mocked GPS on an Android emulator.

Never run against a physical device. Usage: python3 tests/smoke_emulator.py
"""
import json
import os
import re
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ADB = os.environ.get("ASIA_ADB", "adb")
SERIAL = os.environ.get("ASIA_EMULATOR", "emulator-5554")
if not SERIAL.startswith("emulator-"):
    raise SystemExit("Mock GPS test must use an emulator")
SCREEN = ROOT / "build" / "screenshots"
SCREEN.mkdir(parents=True, exist_ok=True)


def adb(*args):
    return subprocess.run([ADB, "-s", SERIAL, *args], check=True, stdout=subprocess.PIPE, timeout=35).stdout


def ui():
    for attempt in range(3):
        # A failed UI dump must never reuse the preceding location's XML.
        try:
            adb("shell", "rm", "-f", "/sdcard/asia-smoke.xml")
            adb("shell", "uiautomator", "dump", "/sdcard/asia-smoke.xml")
            body = adb("shell", "cat", "/sdcard/asia-smoke.xml")
            return [value for n in ET.fromstring(body).iter("node") for value in [n.get("text") or n.get("content-desc")] if value], body
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            time.sleep(1)
    raise RuntimeError("Could not obtain a fresh UI snapshot")


def bounds(node):
    return tuple(map(int, re.findall(r"\d+", node.get("bounds"))))


def tap(node):
    x1, y1, x2, y2 = bounds(node)
    adb("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))


def tap_text(value):
    _, body = ui()
    tap(next(n for n in ET.fromstring(body).iter("node") if value in (n.get("text"), n.get("content-desc"))))


def find_node(body, text):
    return next((n for n in ET.fromstring(body).iter("node") if n.get("text") == text), None)


def capture(out, slug, report, check=None, **extra):
    """Save the current UI dump and screenshot, run an optional assertion and log the screen."""
    texts, body = ui()
    (out / f"{slug}.xml").write_bytes(body)
    (out / f"{slug}.png").write_bytes(adb("exec-out", "screencap", "-p"))
    if check:
        check(texts)
    report.append({"screen": slug, "texts": texts, **extra})
    print(slug, texts, flush=True)
    return texts, body


def launch_at(app, lon, lat, matches, flags=(), settle=2, attempts=8):
    """Restart the app at a mocked location until matches(texts) holds; returns (texts, body)."""
    adb("shell", "am", "force-stop", app)
    adb("emu", "geo", "fix", str(lon), str(lat))
    adb("shell", "am", "start", *flags, "-n", f"{app}/.MainActivity")
    time.sleep(settle)
    for _ in range(attempts):
        adb("emu", "geo", "fix", str(lon), str(lat))
        texts, body = ui()
        if matches(texts):
            return texts, body
    raise AssertionError(texts)


def save_device(app, font=False):
    saved = {"app": app,
             "size": adb("shell", "wm", "size").decode(),
             "density": adb("shell", "wm", "density").decode(),
             "locale": adb("shell", "cmd", "locale", "get-app-locales", app).decode()}
    if font:
        saved["font"] = adb("shell", "settings", "get", "system", "font_scale").decode().strip()
    return saved


def restore_device(saved, layout=True):
    """Undo display, locale and (when saved) font-scale overrides made by an emulator run."""
    if layout:
        for kind in ("size", "density"):
            match = re.search(r"Override \w+: (\S+)", saved[kind])
            adb("shell", "wm", kind, match.group(1) if match else "reset")
    match = re.search(r"\[([^]]*)\]", saved["locale"])
    locale = match.group(1) if match else ""
    adb("shell", "cmd", "locale", "set-app-locales", saved["app"], *(["--locales", locale] if locale else []))
    if "font" in saved:
        if saved["font"] == "null":
            adb("shell", "settings", "delete", "system", "font_scale")
        else:
            adb("shell", "settings", "put", "system", "font_scale", saved["font"])


def main():
    positions = [
        ("hong-kong", "香港", 114.1694, 22.3193, "广州府"),
        ("macau", "澳门", 113.5439, 22.1987, "香山县"),
        ("beijing", "北京", 116.3972, 39.9163, "县界待考"),
        ("nanyang", "河南南阳", 112.5283, 32.9908, "南阳府"),
        ("kyoto", "京都", 135.7681, 35.0116, "葛野郡"),
        ("seoul", "首尔", 126.978, 37.5665, "漢城"),
        ("pyongyang", "平壤", 125.7538, 39.0319, "平壤"),
        ("taipei", "台北", 121.5654, 25.033, "县界待考"),
        ("lianghe", "滇西梁河", 98.2967, 24.806, "县界待考"),
    ]
    report = []
    for slug, name, lon, lat, expected in positions:
        adb("shell", "am", "force-stop", "asia.locality.map")
        adb("emu", "geo", "fix", str(lon), str(lat))
        adb("shell", "am", "start", "-n", "asia.locality.map/.MainActivity")
        time.sleep(2)
        adb("emu", "geo", "fix", str(lon), str(lat))
        for attempt in range(8):
            texts, body = ui()
            combined = "\n".join(texts)
            if "当前位置历史地图" in combined and "取得定位后" not in combined and "地图资料未能载入" not in combined:
                break
            time.sleep(1)
        image = SCREEN / f"tablet-{slug}.png"
        image.write_bytes(adb("exec-out", "screencap", "-p"))
        (SCREEN / f"tablet-{slug}.xml").write_bytes(body)
        passed = "当前位置历史地图" in combined and "地图资料未能载入" not in combined and (expected is None or expected in combined)
        result = {"place": name, "mock_gps": [lon, lat], "expected_text": expected,
                  "passed": passed, "texts": texts, "screenshot": image.name}
        report.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    (SCREEN / "locations.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    lines = ["# 大屏模拟定位截图", "", "2026-09-29；Android API 35 模拟器；2560 × 1600，密度 240。均由 adb 原样截取；坐标为模拟 GPS。", "", "| 地点 | 经度、纬度 | 页面信息 | 截图 |", "| --- | --- | --- | --- |"]
    for r in report:
        description = next((t for t in r["texts"] if t.startswith("当前位置历史地图")), "未完成定位")
        lines.append(f"| {r['place']} | {r['mock_gps'][0]}, {r['mock_gps'][1]} | {description} | [打开]({r['screenshot']}) |")
    lines += ["", "县治点只供标注，不作为当前位置归属。南阳显示府级辖界，未推断县界。台北自然轮廓不代表明代行政界。", "", "地名只在地图内标注一次；表格包含地图的无障碍描述，便于核对。机器记录见 [locations.json](locations.json)。"]
    (SCREEN / "README.md").write_text("\n".join(lines) + "\n")
    if not all(r["passed"] for r in report):
        raise SystemExit("Some mocked locations need review; see build/screenshots/locations.json")


if __name__ == "__main__":
    main()
