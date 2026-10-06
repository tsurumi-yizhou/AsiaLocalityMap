"""Resolve Korean Hanja from the publisher's dated summary, not phonetic transliteration."""
import re
import unicodedata
from functools import lru_cache
from opencc import OpenCC

_simplified = OpenCC('t2s')
to_simplified = _simplified.convert
_traditional = OpenCC('s2t')

@lru_cache(maxsize=32768)
def search_names(name):
    """Search aliases only: display names stay exactly as reviewed from their source."""
    return list(dict.fromkeys([name, _simplified.convert(name), _traditional.convert(name)]))

GROUP_ALIASES = {'경도': '한성', '경도_한성': '한성'}

def korean_native(name, group, dated_native=None):
    # Explicit province renamings in the publisher's history workbook, not guessed readings.
    renamed = {'公忠':'공충', '公淸':'공청', '忠公':'충공', '淸洪':'청홍',
               '忠洪':'충홍', '公洪':'공홍', '洪淸':'홍청', '洪忠':'홍충'}
    if group in GROUP_ALIASES or group == '한성':
        return '한성'
    if dated_native and re.fullmatch(r'[가-힣]+', dated_native):
        return dated_native
    return renamed.get(name.replace('清', '淸'), group.split('_')[-1])


def korean_name(summary, group, year):
    key = GROUP_ALIASES.get(group, group)
    rows = summary.get(key, [])
    names = set()
    for row in rows:
        for name, interval in re.findall(r'([\u3400-\u9fff\uf900-\ufaff]+)\(([^)]*)\)', str(row.get('hist_name', ''))):
            years = re.findall(r'\d{4}', interval)
            if len(years) == 2 and int(years[0]) <= year <= int(years[1]):
                names.add(unicodedata.normalize('NFKC', name))
    return next(iter(names)) if len(names) == 1 else None


NATIVE_POLITIES = {
 'Goguryeo':'고구려', 'Baekje':'백제', 'Silla':'신라', 'Unified Silla':'신라',
 'Balhae':'발해', 'Goryeo':'고려', 'Joseon':'조선', 'Korean Empire':'대한제국',
 'Mahan':'마한', 'Jinhan':'진한', 'Byeonhan':'변한', 'Dongye':'동예',
 'Dong-okjeo':'옥저', 'Tamna':'탐라', 'Hubaekje':'후백제', 'Taebong':'태봉',
 'Early Lý Dynasty':'Vạn Xuân', 'Lê Dynasty':'Lê', 'Trịnh lords':'Trịnh',
 'Nguyễn lords':'Nguyễn', 'Tây Sơn dynasty':'Tây Sơn', 'Nguyễn dynasty':'Nguyễn',
 'Chámpa':'Chăm Pa', 'Funan':'Phù Nam', 'Chenla':'Chân Lạp', 'Khmer Empire':'Chân Lạp',
}


def native_polity(attributes, year):
    name = attributes['Name']
    if name == 'Ngô Dynasty':
        return 'Đại Ngu' if year >= 1400 else 'Đại Việt' if year >= 1054 else 'Đại Cồ Việt' if year >= 968 else 'Ngô'
    if name == 'Đại Việt' and attributes.get('Wikipedia') == 'Mạc dynasty':
        return 'Mạc'
    return NATIVE_POLITIES.get(name, '')
