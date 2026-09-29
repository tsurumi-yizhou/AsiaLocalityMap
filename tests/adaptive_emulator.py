"""Material 3 phone/tablet, locale and keyboard regression on emulator only."""
import json
import re
import time
import xml.etree.ElementTree as ET
from smoke_emulator import adb, ui, SCREEN

OUT = SCREEN / 'adaptive'
OUT.mkdir(exist_ok=True)
APP = 'asia.locality.map'
report = []

def tap_node(node):
    x1,y1,x2,y2 = map(int,re.findall(r'\d+',node.get('bounds')))
    adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2))

def tap_text(text):
    _, body = ui()
    tap_node(next(n for n in ET.fromstring(body).iter('node') if n.get('text') == text))

def capture(slug):
    texts,body=ui()
    (OUT/f'{slug}.xml').write_bytes(body)
    (OUT/f'{slug}.png').write_bytes(adb('exec-out','screencap','-p'))
    assert not any(t in texts for t in ['资料','沿革记录','查看资料来源']), texts
    report.append({'screen':slug,'texts':texts})
    print(slug, texts, flush=True)
    return texts,body

def launch(lon,lat,name):
    adb('shell','am','force-stop',APP)
    adb('emu','geo','fix',str(lon),str(lat))
    adb('shell','am','start','-n',f'{APP}/.MainActivity')
    time.sleep(2)
    for _ in range(8):
        adb('emu','geo','fix',str(lon),str(lat))
        texts,_=ui()
        if any(name in t for t in texts): return
    raise AssertionError(texts)

old_size=adb('shell','wm','size').decode()
old_density=adb('shell','wm','density').decode()
old_locale=adb('shell','cmd','locale','get-app-locales',APP).decode()
old_font=adb('shell','settings','get','system','font_scale').decode().strip()
try:
    for size,density,label in [('640x1136','320','phone'),('2560x1600','240','tablet')]:
        adb('shell','wm','size',size)
        adb('shell','wm','density',density)
        for locale,search,close,buttons,position in [
            ('zh-Hans','查地名','关闭',['当前位置','放大','缩小'],(112.5283,32.9908,'南阳县')),
            ('ja','地名検索','閉じる',['現在地','拡大','縮小'],(135.7681,35.0116,'葛野郡')),
            ('ko','지명 검색','닫기',['현재 위치','확대','축소'],(126.978,37.5665,'한성'))]:
            adb('shell','cmd','locale','set-app-locales',APP,'--locales',locale)
            launch(*position)
            texts,_=capture(f'{label}-{locale}-map')
            assert all(b in texts for b in buttons),texts
            tap_text(search)
            texts,body=capture(f'{label}-{locale}-search')
            assert close in texts,texts
            edit=next(n for n in ET.fromstring(body).iter('node') if n.get('class')=='android.widget.EditText')
            tap_node(edit)
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
    launch(126.978,37.5665,'한성')
    capture('phone-ko-large-font')
finally:
    for kind,old in [('size',old_size),('density',old_density)]:
        match=re.search(r'Override \w+: (\S+)',old)
        adb('shell','wm',kind,match.group(1) if match else 'reset')
    match=re.search(r'\[([^]]*)\]',old_locale)
    restore=match.group(1) if match else ''
    args=['shell','cmd','locale','set-app-locales',APP]
    if restore: args+=['--locales',restore]
    adb(*args)
    if old_font=='null': adb('shell','settings','delete','system','font_scale')
    else: adb('shell','settings','put','system','font_scale',old_font)
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
