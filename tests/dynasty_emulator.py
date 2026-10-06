"""Exercise every dynasty option on an emulator; save screenshots and restore settings."""
import json
import re
import time
import sys
import xml.etree.ElementTree as ET
from smoke_emulator import SCREEN, adb, bounds, capture as capture_screen, find_node, restore_device, save_device, tap, ui

APP = 'asia.locality.map'
KEEP_LAYOUT = '--keep-layout' in sys.argv
OUT = SCREEN / 'dynasties'
OUT.mkdir(exist_ok=True)
from pathlib import Path
catalogue = json.loads((Path(__file__).resolve().parents[1] / 'data/processed/android/timeline.json').read_text())
PERIODS = [(p['titles']['zh'], p['year']) for p in catalogue if p['region'] == 'cn']

def caption(name, year):
    return name

report = []


def capture(slug):
    if KEEP_LAYOUT: slug = slug.replace('phone-', 'current-').replace('tablet-', 'current-')
    return capture_screen(OUT, slug, report, _no_stale_text)


def _no_stale_text(texts):
    assert not any('已收录' in t or '中国按参考年' in t or '现有资料支持' in t for t in texts), texts


def open_picker():
    for _ in range(20):
        _, body = ui()
        root = ET.fromstring(body)
        parents = {child: parent for parent in root.iter() for child in parent}
        selector = next((n for n in root.iter('node') if re.fullmatch(r'汉|唐|宋|明|中国', n.get('text', '')) is not None),None)
        if selector is None:
            time.sleep(.5)
            continue
        while selector.get('clickable') != 'true':
            selector = parents[selector]
        if selector.get('enabled') == 'true':
            tap(selector)
            return
        time.sleep(0.5)
    raise AssertionError('Dynasty selector did not become ready')


def scroll_to(text):
    for _ in range(12):
        _, body = ui()
        node = find_node(body, text)
        if node is not None:
            x1, y1, x2, y2 = bounds(node)
            if x2 > x1 and y2 > y1:
                return node
        scroll = next(n for n in ET.fromstring(body).iter('node') if n.get('scrollable') == 'true')
        x1, y1, x2, y2 = bounds(scroll)
        adb('shell', 'input', 'swipe', str((x1+x2)//2), str(y2-30),
            str((x1+x2)//2), str(y1+30), '300')
    raise AssertionError(f'Option not reachable: {text}')


def choose(name, year):
    open_picker()
    tap(scroll_to(caption(name, year)))
    for _ in range(20):
        texts, _ = ui()
        if caption(name, year) in texts and '中国' not in texts: break
        time.sleep(.25)
    else: raise AssertionError(texts)
    assert texts.count(caption(name, year)) == 1, texts
    expected = {'汉':'南阳郡','唐':'邓州','宋':'邓州','明':'南阳府'}[name]
    # A real enclosing administrative area, not a nearby county seat.
    assert any(f'历史地图 · {expected} ·' in t for t in texts),texts
    assert not any('附近治所' in t for t in texts),texts
    print('selected', name, year, flush=True)


saved = save_device(APP)
try:
    adb('shell', 'cmd', 'locale', 'set-app-locales', APP, '--locales', 'zh-Hans')
    if not KEEP_LAYOUT:
        adb('shell', 'wm', 'size', '640x1136')
        adb('shell', 'wm', 'density', '320')
    adb('shell', 'am', 'force-stop', APP)
    adb('emu', 'geo', 'fix', '112.5283', '32.9908')
    adb('shell', 'am', 'start', '-f', '0x10008000', '-n', f'{APP}/.MainActivity')
    time.sleep(3)
    adb('emu', 'geo', 'fix', '112.5283', '32.9908')
    for name, year in PERIODS:
        choose(name, year)
        if name in ('汉', '唐', '宋', '明'):
            capture(f'phone-{year}')
    open_picker()
    capture('phone-picker-top')
    scroll_to('明')
    texts, _ = capture('phone-picker-bottom')
    assert '明' in texts and not any(t == '清' for t in texts)
    assert '日本' not in texts and '越南' not in texts
    adb('shell', 'input', 'keyevent', '4')
    adb('shell', 'am', 'force-stop', APP)
    adb('shell', 'am', 'start', '-f', '0x10008000', '-n', f'{APP}/.MainActivity')
    time.sleep(3)
    texts, _ = capture('phone-restarted-ming')
    assert texts.count('明') == 1, texts
    if not KEEP_LAYOUT:
        adb('shell', 'wm', 'size', '2560x1600')
        adb('shell', 'wm', 'density', '240')
    time.sleep(2)
    texts, _ = capture('tablet-restored-ming')
    assert texts.count('明') == 1, texts
    open_picker()
    capture('tablet-picker')
    adb('shell', 'input', 'keyevent', '4')
    choose('明', 1585)
    report.append({'all_options_clickable': True, 'restart_preserves_choice': True, 'resize_checked': not KEEP_LAYOUT})
finally:
    restore_device(saved, layout=not KEEP_LAYOUT)
    (OUT / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
