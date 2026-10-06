"""Shared offline timeline catalogue. Menus are regional; the selected year is global."""
import json

# id, region, reference year, display interval, Chinese/Japanese/Korean menu names.
ROWS = [
 ('han','cn',2,-202,220,'汉','漢','한'),
 ('tang','cn',742,618,906,'唐','唐','당'),
 ('song','cn',1102,960,1278,'宋','宋','송'),
 ('ming','cn',1585,1368,1644,'明','明','명'),
 ('silla','kr',757,668,935,'新羅','新羅','신라'),
 ('goryeo','kr',1370,936,1391,'高麗','高麗','고려'),
 ('joseon_late','kr',1864,1392,1897,'朝鮮','朝鮮','조선'),
 ('jp_early_modern','jp',1864,1333,1867,'近世','近世','근세'),

]
CATALOG = [dict(id=i, region=r, year=y, start=a, end=b, titles={'zh':zh,'ja':ja,'ko':ko})
           for i,r,y,a,b,zh,ja,ko in ROWS]
YEARS = sorted({p['year'] for p in CATALOG})
DEFAULT_YEAR = 1585
# Shared-reference display windows, not formation dates of individual boundaries.
# Align Japan's country-level reference to the Tang slot; later district boundaries
# remain limited to the previously accepted Muromachi-to-Edo reference window.
REFERENCE_LAYERS = {
    'kr': {1: (668,1897), 2: (668,1897)},
    'jp': {1: (618,1867), 2: (1336,1867)},
}

def reference_layer_available(region, rank, year):
    if region not in REFERENCE_LAYERS:
        return True
    span = REFERENCE_LAYERS[region].get(rank)
    return span is not None and span[0] <= year <= span[1]

def period_at(region, year):
    return next((p for p in CATALOG if p['region'] == region and p['start'] <= year <= p['end']), None)

def reference_years(year):
    # Every reference is an available LOCAL dataset, never a political-map fallback.
    result = {region: None for region in ('cn', 'kr', 'jp', 'vn')}
    for region in ('cn', 'kr'):
        period = period_at(region, year)
        if period:
            result[region] = period['year']
    if reference_layer_available('jp', 1, year):
        result['jp'] = 1864
    return result

REGION_CODES = {'CHN':'cn','TWN':'cn','HKG':'cn','MAC':'cn','JPN':'jp','KOR':'kr','PRK':'kr','VNM':'vn'}

if __name__ == '__main__':
    print(json.dumps(CATALOG, ensure_ascii=False))
