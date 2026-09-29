"""Save unedited tablet screenshots using mocked GPS on an Android emulator.

Never run against a physical device. Usage: python3 tests/smoke_emulator.py
"""
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ADB = os.environ.get("ASIA_ADB", "/home/yizhou/.local/share/android-sdk/platform-tools/adb")
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
        adb("shell", "rm", "-f", "/sdcard/asia-smoke.xml")
        adb("shell", "uiautomator", "dump", "/sdcard/asia-smoke.xml")
        try:
            body = adb("shell", "cat", "/sdcard/asia-smoke.xml")
            return [value for n in ET.fromstring(body).iter("node") for value in [n.get("text") or n.get("content-desc")] if value], body
        except subprocess.CalledProcessError:
            time.sleep(1)
    raise RuntimeError("Could not obtain a fresh UI snapshot")


def main():
    positions = [
        ("hong-kong", "香港", 114.1694, 22.3193, "新安县"),
        ("macau", "澳门", 113.5439, 22.1987, "香山县"),
        ("beijing", "北京", 116.3972, 39.9163, "县界待考"),
        ("nanyang", "河南南阳", 112.5283, 32.9908, "南阳县"),
        ("kyoto", "京都", 135.7681, 35.0116, "葛野郡"),
        ("seoul", "首尔", 126.978, 37.5665, "한성"),
        ("pyongyang", "平壤", 125.7538, 39.0319, "평양"),
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
    lines += ["", "县治点只供标注，不作为当前位置归属。南阳当前显示附近南阳县治所，县界待补。台北自然轮廓不代表明代行政界。", "", "地名只在地图内标注一次；表格包含地图的无障碍描述，便于核对。机器记录见 [locations.json](locations.json)。"]
    (SCREEN / "README.md").write_text("\n".join(lines) + "\n")
    if not all(r["passed"] for r in report):
        raise SystemExit("Some mocked locations need review; see build/screenshots/locations.json")


if __name__ == "__main__":
    main()
