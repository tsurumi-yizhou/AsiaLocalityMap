"""Refresh the existing website screenshots, preserving filenames and pixel sizes."""
import json
import re
import struct
import time
from smoke_emulator import ROOT, SCREEN, adb, find_node, launch_at, restore_device, save_device, ui

APP = 'asia.locality.map'
OUT = ROOT / 'docs' / 'assets' / 'screenshots'
LOCALES = {
    'zh-Hans': (112.5283, 32.9908, '南阳府', '查地名', '关闭', ['当前位置', '放大', '缩小']),
    'ja': (135.7681, 35.0116, '葛野郡', '地名検索', '閉じる', ['現在地', '拡大', '縮小']),
    'ko': (126.978, 37.5665, '漢城', '지명 검색', '닫기', ['현재 위치', '확대', '축소']),
}
captures = []
for path in sorted(OUT.glob('*.png')):
    match = re.fullmatch(r'(phone|tablet)-(zh-Hans|ja|ko)-(map|search)', path.stem)
    if not match:
        raise ValueError(f'Unknown screenshot scenario: {path.name}')
    width, height = struct.unpack('>II', path.read_bytes()[16:24])
    captures.append((path, *match.groups(), width, height))
assert captures, 'No existing website screenshots found'

saved = save_device(APP, font=True)
report = []
try:
    adb('shell', 'settings', 'put', 'system', 'font_scale', '1.0')
    for path, device, locale, state, width, height in captures:
        lon, lat, place, search, close, buttons = LOCALES[locale]
        adb('shell', 'wm', 'size', f'{width}x{height}')
        adb('shell', 'wm', 'density', '320' if device == 'phone' else '240')
        adb('shell', 'cmd', 'locale', 'set-app-locales', APP, '--locales', locale)
        texts, body = launch_at(APP, lon, lat, lambda texts: any(place in text for text in texts))
        assert all(button in texts for button in buttons), texts
        if state == 'search':
            node = find_node(body, search)
            x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.get('bounds')))
            adb('shell', 'input', 'tap', str((x1 + x2) // 2), str((y1 + y2) // 2))
            texts, body = ui()
            assert close in texts, texts
        time.sleep(0.4)
        png = adb('exec-out', 'screencap', '-p')
        assert struct.unpack('>II', png[16:24]) == (width, height)
        path.write_bytes(png)
        report.append({'file': path.name, 'size': [width, height], 'texts': texts})
        print(path.name, 'updated', flush=True)
finally:
    restore_device(saved)
    (SCREEN / 'site-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
