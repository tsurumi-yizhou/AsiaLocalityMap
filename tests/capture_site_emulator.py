"""Refresh the existing website screenshots, preserving filenames and pixel sizes."""
import json
import re
import struct
import time
import xml.etree.ElementTree as ET
from smoke_emulator import ROOT, SCREEN, adb, ui

APP = 'asia.locality.map'
OUT = ROOT / 'docs' / 'assets' / 'screenshots'
LOCALES = {
    'zh-Hans': (112.5283, 32.9908, '南阳县', '查地名', '关闭', ['当前位置', '放大', '缩小']),
    'ja': (135.7681, 35.0116, '葛野郡', '地名検索', '閉じる', ['現在地', '拡大', '縮小']),
    'ko': (126.978, 37.5665, '한성', '지명 검색', '닫기', ['현재 위치', '확대', '축소']),
}
captures = []
for path in sorted(OUT.glob('*.png')):
    match = re.fullmatch(r'(phone|tablet)-(zh-Hans|ja|ko)-(map|search)', path.stem)
    if not match:
        raise ValueError(f'Unknown screenshot scenario: {path.name}')
    width, height = struct.unpack('>II', path.read_bytes()[16:24])
    captures.append((path, *match.groups(), width, height))
assert captures, 'No existing website screenshots found'

old_size = adb('shell', 'wm', 'size').decode()
old_density = adb('shell', 'wm', 'density').decode()
old_locale = adb('shell', 'cmd', 'locale', 'get-app-locales', APP).decode()
old_font = adb('shell', 'settings', 'get', 'system', 'font_scale').decode().strip()
report = []
try:
    adb('shell', 'settings', 'put', 'system', 'font_scale', '1.0')
    for path, device, locale, state, width, height in captures:
        lon, lat, place, search, close, buttons = LOCALES[locale]
        adb('shell', 'wm', 'size', f'{width}x{height}')
        adb('shell', 'wm', 'density', '320' if device == 'phone' else '240')
        adb('shell', 'cmd', 'locale', 'set-app-locales', APP, '--locales', locale)
        adb('shell', 'am', 'force-stop', APP)
        adb('emu', 'geo', 'fix', str(lon), str(lat))
        adb('shell', 'am', 'start', '-n', f'{APP}/.MainActivity')
        time.sleep(2)
        for _ in range(8):
            adb('emu', 'geo', 'fix', str(lon), str(lat))
            texts, body = ui()
            if any(place in text for text in texts): break
        assert any(place in text for text in texts), texts
        assert all(button in texts for button in buttons), texts
        if state == 'search':
            node = next(n for n in ET.fromstring(body).iter('node') if n.get('text') == search)
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
    for kind, old in [('size', old_size), ('density', old_density)]:
        match = re.search(r'Override \w+: (\S+)', old)
        adb('shell', 'wm', kind, match.group(1) if match else 'reset')
    match = re.search(r'\[([^]]*)\]', old_locale)
    locale = match.group(1) if match else ''
    adb('shell', 'cmd', 'locale', 'set-app-locales', APP, *(['--locales', locale] if locale else []))
    if old_font == 'null': adb('shell', 'settings', 'delete', 'system', 'font_scale')
    else: adb('shell', 'settings', 'put', 'system', 'font_scale', old_font)
    (SCREEN / 'site-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
