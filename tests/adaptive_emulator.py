"""Material 3 phone/tablet, locale and keyboard regression on emulator only."""
import json
import time
import xml.etree.ElementTree as ET
from smoke_emulator import SCREEN, adb, capture as capture_screen, launch_at, restore_device, save_device, tap, tap_text

OUT = SCREEN / 'adaptive'
OUT.mkdir(exist_ok=True)
APP = 'asia.locality.map'
report = []

def _no_source_text(texts):
    assert not any(t in texts for t in ['资料','沿革记录','查看资料来源']), texts

def capture(slug):
    return capture_screen(OUT,slug,report,_no_source_text)

def launch(lon,lat,name):
    launch_at(APP,lon,lat,lambda texts:any(name in t for t in texts))

saved=save_device(APP,font=True)
try:
    for size,density,label in [('640x1136','320','phone'),('2560x1600','240','tablet')]:
        adb('shell','wm','size',size)
        adb('shell','wm','density',density)
        for locale,search,close,buttons,position in [
            ('zh-Hans','查地名','关闭',['当前位置','放大','缩小'],(112.5283,32.9908,'南阳府')),
            ('ja','地名検索','閉じる',['現在地','拡大','縮小'],(135.7681,35.0116,'葛野郡')),
            ('ko','지명 검색','닫기',['현재 위치','확대','축소'],(126.978,37.5665,'漢城'))]:
            adb('shell','cmd','locale','set-app-locales',APP,'--locales',locale)
            launch(*position)
            texts,_=capture(f'{label}-{locale}-map')
            assert all(b in texts for b in buttons),texts
            tap_text(search)
            texts,body=capture(f'{label}-{locale}-search')
            assert close in texts,texts
            edit=next(n for n in ET.fromstring(body).iter('node') if n.get('class')=='android.widget.EditText')
            tap(edit)
            time.sleep(1)  # Wait for the IME connection before injecting key events.
            for char in 'abc':
                adb('shell','input','text',char)
                time.sleep(0.15)
            adb('shell','input','keyevent','66')  # Commit the Chinese IME pre-edit text.
            texts,body=capture(f'{label}-{locale}-keyboard')
            field = next(n for n in ET.fromstring(body).iter('node') if n.get('class') == 'android.widget.EditText')
            assert field.get('text'), texts
            assert {'zh-Hans':'暂未收录此地名。','ja':'該当する地名は未収録です','ko':'아직 수록되지 않은 지명입니다'}[locale] in texts, texts
            tap_text(close)
            texts,_=capture(f'{label}-{locale}-closed')
            assert close not in texts and all(b in texts for b in buttons),texts
    adb('shell','wm','size','640x1136')
    adb('shell','wm','density','320')
    adb('shell','settings','put','system','font_scale','1.3')
    launch(126.978,37.5665,'漢城')
    capture('phone-ko-large-font')
finally:
    restore_device(saved)
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
