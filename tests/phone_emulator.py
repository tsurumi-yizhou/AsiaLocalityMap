"""Small-screen UI regression; emulator only. Restores tablet size in finally."""
import json
import sys
import re
import time
import xml.etree.ElementTree as ET
from smoke_emulator import adb, ui, SCREEN

OUT = SCREEN / 'phone'
OUT.mkdir(exist_ok=True)
search_only = "--search-only" in sys.argv
quick = "--quick" in sys.argv or search_only
report = json.loads((OUT / "results.json").read_text()) if quick and (OUT / "results.json").exists() else []


def bounds(node):
    return tuple(map(int, re.findall(r'\d+', node.get('bounds'))))


def tap_text(value):
    _, body = ui()
    node = next(n for n in ET.fromstring(body).iter('node') if n.get('text') == value)
    x1, y1, x2, y2 = bounds(node)
    adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))


def capture(slug):
    texts, body = ui()
    (OUT / f'{slug}.xml').write_bytes(body)
    (OUT / f'{slug}.png').write_bytes(adb('exec-out', 'screencap', '-p'))
    report[:] = [r for r in report if r['screen'] != slug]
    report.append({'screen': slug, 'texts': texts, 'screenshot': f'{slug}.png'})
    print(slug, texts, flush=True)
    return texts, body


def launch(lon, lat, expected):
    adb('shell', 'am', 'force-stop', 'asia.locality.map')
    adb('emu', 'geo', 'fix', str(lon), str(lat))
    adb('shell', 'am', 'start', '-n', 'asia.locality.map/.MainActivity')
    time.sleep(2)
    for _ in range(8):
        adb('emu', 'geo', 'fix', str(lon), str(lat))
        texts, body = ui()
        if any('当前位置历史地图' in t and expected in t for t in texts):
            return body
    raise AssertionError(texts)


font_scale = adb('shell', 'settings', 'get', 'system', 'font_scale').decode().strip()
try:
    for width, height in ([(640, 1136)] if quick else [(640, 1136), (720, 1280)]):
        dp = width // 2
        adb('shell', 'wm', 'size', f'{width}x{height}')
        adb('shell', 'wm', 'density', '320')
        adb('shell', 'settings', 'put', 'system', 'font_scale', '1.0')
        for slug, lon, lat, name in [('nanyang',112.5283,32.9908,'南阳县'), ('kyoto',135.7681,35.0116,'葛野郡'), ('seoul',126.978,37.5665,'한성')]:
            if (quick and slug == 'seoul') or (search_only and slug != 'nanyang'):
                continue
            launch(lon, lat, name)
            texts, body = capture(f'{dp}-{slug}')
            assert all(t in texts for t in ['当前位置','放大','缩小']), texts
            if slug == 'nanyang' and dp == 320:
                tap_text('查地名')
                _, body = ui()
                edit = next(n for n in ET.fromstring(body).iter('node') if n.get('class')=='android.widget.EditText')
                x1,y1,x2,y2 = bounds(edit)
                adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2))
                time.sleep(1)
                for char in 'abc':
                    adb('shell','input','text',char)
                    time.sleep(0.15)
                adb('shell','input','keyevent','66')  # Commit the Chinese IME pre-edit text.
                texts,_ = capture('320-search-keyboard')
                assert 'abc' in texts and '暂未收录此地名。' in texts
                tap_text('关闭')
                texts, _ = ui()
                assert any('当前位置历史地图' in t for t in texts), texts
            if slug == 'kyoto' and dp == 320:
                tap_text('放大')
                capture('320-zoom')
                adb('shell','input','swipe','300','500','450','650','450')
                capture('320-pan')
    if not search_only:
        adb('shell','wm','size','640x1136')
        adb('shell','settings','put','system','font_scale','1.3')
        launch(112.5283,32.9908,'南阳县')
        capture('320-large-text')
finally:
    if font_scale == 'null':
        adb('shell','settings','delete','system','font_scale')
    else:
        adb('shell','settings','put','system','font_scale',font_scale)
    adb('shell','wm','size','2560x1600')
    adb('shell','wm','density','240')
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
