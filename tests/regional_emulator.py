"""Actual emulator checks for region-specific menus and Han-character labels."""
import json
import re
import time
import xml.etree.ElementTree as ET
from smoke_emulator import SCREEN, adb, capture as capture_screen, find_node, restore_device, save_device, tap, ui

APP='asia.locality.map'
OUT=SCREEN/'regional'
OUT.mkdir(exist_ok=True)
report=[]


def capture(name):
    return capture_screen(OUT,name,report)


def launch(lon,lat,caption):
    adb('shell','am','force-stop',APP)
    adb('emu','geo','fix',str(lon),str(lat))
    adb('shell','am','start','-f','0x10008000','-n',APP+'/.MainActivity')
    for _ in range(20):
        adb('emu','geo','fix',str(lon),str(lat))
        texts,body=ui()
        if caption == '近世' and caption in texts:
            time.sleep(.5)
            return
        if caption == '':
            if not any('年' in t for t in texts) and any(n.get('content-desc','').startswith('当前位置') for n in ET.fromstring(body).iter('node')):
                time.sleep(.5)
                return
            time.sleep(.25)
            continue
        if caption is None or caption in texts:
            root=ET.fromstring(body)
            parents={c:p for p in root.iter() for c in p}
            node=next((n for n in root.iter('node') if re.fullmatch(r'汉|唐|宋|明|中国',n.get('text',''))),None) if caption is None else next((n for n in root.iter('node') if n.get('text')==caption),None)
            if node is None:
                time.sleep(.25)
                continue
            while node.get('clickable')!='true':node=parents[node]
            if node.get('enabled')=='true':
                time.sleep(.5)
                return
        time.sleep(.25)
    raise AssertionError(texts)

def select_default():
    launch(112.5283,32.9908,None)
    _,body=ui()
    node=next(n for n in ET.fromstring(body).iter('node') if re.fullmatch(r'汉|唐|宋|明|中国',n.get('text','')))
    tap(node)
    for _ in range(12):
        texts,body=ui()
        node=next((n for n in ET.fromstring(body).iter('node') if n.get('text')=='明'),None)
        if node is not None:
            tap(node)
            break
        scroll=next(n for n in ET.fromstring(body).iter('node') if n.get('scrollable')=='true')
        x1,y1,x2,y2=map(int,re.findall(r'\d+',scroll.get('bounds')))
        adb('shell','input','swipe',str((x1+x2)//2),str(y2-30),str((x1+x2)//2),str(y1+30),'300')
    else:raise AssertionError('Ming preset not reachable')
    for _ in range(20):
        texts,_=ui()
        if '明' in texts and '中国' not in texts:return
        time.sleep(.25)
    raise AssertionError(texts)


saved=save_device(APP)
try:
    adb('shell','cmd','locale','set-app-locales',APP,'--locales','zh-Hans')
    select_default()
    for layout,size,density in [('phone','640x1136','320'),('tablet','1600x1200','240')]:
        adb('shell','wm','size',size)
        adb('shell','wm','density',density)
        for region,lon,lat,caption,title,first in [
            ('cn',123.17,41.27,'明','中国','汉'),
            ('kr',126.978,37.5665,'朝鮮','朝鲜历史地区','新羅'),
            ('jp',135.7681,35.0116,'近世','日本',''),
            ('vn',105.8342,21.0278,'','越南','')]:
            launch(lon,lat,caption)
            texts,body=capture(f'{layout}-{region}-map')
            if region == 'vn':
                assert not any('郑阮' in t or '鄭主' in t or '阮主' in t or re.fullmatch(r'.+ · .*年.*',t) for t in texts),texts
                continue
            assert texts.count(caption)==1,texts
            if region == 'jp':
                node=find_node(body,caption)
                assert node.get('clickable')=='false',node.attrib
                continue
            node=find_node(body,caption)
            tap(node)
            for _ in range(6):
                texts,body=ui()
                if first in texts:break
                scroll=next((n for n in ET.fromstring(body).iter('node') if n.get('scrollable')=='true'),None)
                if scroll is None:break
                x1,y1,x2,y2=map(int,re.findall(r'\d+',scroll.get('bounds')))
                adb('shell','input','swipe',str((x1+x2)//2),str(y1+30),str((x1+x2)//2),str(y2-30),'300')
            texts,_=capture(f'{layout}-{region}-menu')
            assert title in texts and first in texts,texts
            assert not any(t == '清' for t in texts),texts
            if region!='cn':assert not any(t == '汉' for t in texts),texts
            adb('shell','input','keyevent','4')
finally:
    restore_device(saved)
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
