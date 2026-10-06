"""Exercise map gestures after installing the app and Kotlin Android test APKs."""
import json
import time
from smoke_emulator import SCREEN, adb, tap_text, ui


def capture(name):
    time.sleep(0.5)
    (SCREEN / f"tablet-{name}.png").write_bytes(adb("exec-out", "screencap", "-p"))


adb("shell", "am", "force-stop", "asia.locality.map")
adb("emu", "geo", "fix", "112.5283", "32.9908")
adb("shell", "am", "start", "-n", "asia.locality.map/.MainActivity")
time.sleep(3)
adb("emu", "geo", "fix", "112.5283", "32.9908")
for attempt in range(8):
    texts, _ = ui()
    if any("南阳府" in t for t in texts):
        break
    time.sleep(1)
    adb("emu", "geo", "fix", "112.5283", "32.9908")
assert any("南阳府" in t for t in texts), texts
capture("gesture-start")
app_path = adb("shell", "pm", "path", "asia.locality.map").decode().strip().removeprefix("package:")
test_path = adb("shell", "pm", "path", "asia.locality.map.test").decode().strip().removeprefix("package:")
assert app_path.startswith("/data/app/") and test_path.startswith("/data/app/")
adb("shell", "env", f"CLASSPATH={app_path}:{test_path}", "app_process", "/", "asia.locality.map.MapGestureProbe", "1280", "780", "180", "450")
capture("pinch-enlarged")
adb("shell", "input", "swipe", "1200", "750", "1700", "950", "500")
capture("panned")
tap_text("放大")
capture("button-enlarged")
tap_text("缩小")
capture("button-reduced")
adb("shell", "env", f"CLASSPATH={app_path}:{test_path}", "app_process", "/", "asia.locality.map.MapGestureProbe", "1200", "750")
capture("double-tap")
texts, _ = ui()
assert "沿革记录" not in texts, "Double tap unexpectedly opened details"
tap_text("当前位置")
adb("emu", "geo", "fix", "112.5283", "32.9908")
for attempt in range(8):
    texts, _ = ui()
    if "正在确定当前位置" not in texts:
        break
    adb("emu", "geo", "fix", "112.5283", "32.9908")
assert "附近县治 · 县界待考" not in texts, texts
capture("returned")
texts, _ = ui()
assert any("南阳府" in t for t in texts), texts
adb("shell", "input", "tap", "1295", "779")
time.sleep(1)
texts, _ = ui()
assert any("南阳府" in t for t in texts) and "沿革记录" not in texts, texts
capture("nanyang-selection")
print(json.dumps({"place": "河南南阳", "actions_completed": ["pinch", "pan", "zoom buttons", "double tap", "return to location", "tap place without details"], "visual_review_required": True}, ensure_ascii=False))
