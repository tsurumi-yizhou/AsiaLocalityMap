"""Verify fixed Japanese/Korean boundary references on phone and tablet AVD layouts."""
import json
import sys
import time
from smoke_emulator import SCREEN, adb, find_node, restore_device, save_device, ui

APP='asia.locality.map'
OUT=SCREEN/'local-periods'
OUT.mkdir(exist_ok=True)
report=[]


def ready(caption,county):
    for _ in range(25):
        texts,body=ui()
        node=find_node(body,caption)
        if node is not None and '正在准备历史地图' not in texts and any(f'历史地图 · {county} ·' in t for t in texts):
            assert node.get('clickable')==('true' if caption.startswith('朝鮮') else 'false'),node.attrib
            assert texts.count(caption)==1,texts
            assert not any('附近治所' in t for t in texts),texts
            return texts,body
        time.sleep(.3)
    raise AssertionError((caption,county,texts))


saved=save_device(APP)
try:
    adb('shell','cmd','locale','set-app-locales',APP,'--locales','zh-Hans')
    places=[('kr-seoul',126.978,37.5665,'朝鮮','漢城'),
            ('kr-pyongyang',125.754,39.033,'朝鮮','平壤'),
            ('jp',135.7681,35.0116,'近世','葛野郡')]
    if '--japan-only' in sys.argv:places=places[-1:]
    for region,lon,lat,caption,county in places:
        adb('shell','am','force-stop',APP)
        adb('emu','geo','fix',str(lon),str(lat))
        adb('shell','am','start','-f','0x10008000','-n',APP+'/.MainActivity')
        ready(caption,county)
        for layout,size,density in [('phone','640x1136','320'),('tablet','1600x1200','240')]:
            adb('shell','wm','size',size)
            adb('shell','wm','density',density)
            texts,body=ready(caption,county)
            name=f'{region}-fixed-{layout}'
            (OUT/f'{name}.png').write_bytes(adb('exec-out','screencap','-p'))
            (OUT/f'{name}.xml').write_bytes(body)
            report.append({'profile':name,'texts':texts})
            print(name,texts,flush=True)
finally:
    restore_device(saved)
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
