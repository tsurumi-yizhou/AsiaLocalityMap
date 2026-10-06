"""Translate ResearchArea names using CHGIS identities and reviewed historical names.

Geometry is always the author's ResearchArea geometry. No simulated county layer
is used. Unresolved/aggregated units are quarantined rather than guessed.
"""
import re
from collections import defaultdict
from historical_names import to_simplified
from shapely.geometry import shape

HAN_TEXT = 'https://zh.wikisource.org/wiki/漢書/卷028'
TANG_TEXT = 'https://zh.wikisource.org/wiki/新唐書/卷043上'
TANG_GEOGRAPHY = 'https://zh.wikisource.org/wiki/新唐書/卷037'
SONG_TEXT = 'https://zh.wikisource.org/wiki/宋史/卷089'
# IDs refer to the authors' PrefID within YEAR, not CHGIS IDs. Coordinates and
# the English source name were checked together to disambiguate homophones.
REVIEWED = {
 2: {1:'日南郡',2:'九真郡',3:'交趾郡',24:'六安国',26:'九江郡',40:'右扶风',
     42:'沛郡',45:'左冯翊',50:'鲁国',51:'城阳国',55:'东郡',58:'高密国',61:'淄川国',
     69:'千乘郡',72:'信都国',86:'云中郡',88:'五原郡',89:'朔方郡',98:'玄菟郡',101:'乐浪郡',102:'辽东郡'},
 742: {1:'爱州',2:'长州',3:'武安州',4:'驩州',5:'交州',6:'罗伏州',7:'唐林州',10:'武峨州',
       24:'峰州',29:'汤州',46:'藤州',82:'溱州',83:'建州',86:'戎州',107:'忠州',125:'彭州',
       127:'婺州',128:'汉州',130:'峡州',145:'巂州',152:'安南中都护府',173:'龙州',174:'随州',
       183:'常州',184:'利州',190:'滁州',193:'扶州',200:'叠州',206:'亳州',208:'楚州',214:'邠州',
       231:'滑州',232:'卫州',234:'泽州',286:'蔚州',288:'蓟州',289:'檀州',295:'营州',296:'西州',
       297:'伊州',301:'福禄州',309:'庭州',310:'巫州',316:'安东都护府'},
 1102: {84:'富顺监',118:'陵井监',136:'汉州',177:'三泉县',227:'单州',240:'滑州',
        252:'积石军',258:'西安州',262:'怀德军',283:'潍州',325:'丰州'},
}
# These are statistical aggregates, tribal tracts, or unresolved identities, not
# individually established prefectural boundaries. Keep them only in research DB.
EXCLUDED = {742: {8,136,139,150,154,156,163,164,168,315},
            1102: {1,21,34,43,55,61,63,69,70,72,73,80,82,84,118,125,177}}


def key(name):
    return re.sub('[^a-z]', '', name.lower())


class PrefectureNames:
    def __init__(self, connection):
        self.lookup = defaultdict(list)
        self.simplify = to_simplified
        for fid, source, raw, geometry, begin, end in connection.execute(
                "SELECT id,source,attributes_json,geometry_json,begin_year,end_year FROM feature "
                "WHERE source IN ('chgis-pref-point','chgis-pref-polygon')"):
            import json
            attrs = json.loads(raw)
            self.lookup[key(attrs.get('NAME_PY',''))].append(
                (fid,source,self.simplify(attrs['NAME_CH']),shape(json.loads(geometry)),begin,end))

    def resolve(self, attrs, geometry):
        year = int(attrs['YEAR'].removesuffix('AD'))
        ident = attrs['PrefID']
        if ident in EXCLUDED.get(year,set()) or ',' in attrs['PrefNAM']:
            return None, 'aggregated_or_unresolved_local_unit'
        if ident in REVIEWED.get(year,{}):
            text = HAN_TEXT if year == 2 else SONG_TEXT if year == 1102 else TANG_TEXT if ident <= 46 or ident in {152,301} else TANG_GEOGRAPHY
            return REVIEWED[year][ident], text
        candidates = self.lookup[key(attrs['PrefNAM'])]
        suffix = next((cn for en,cn in [('zhou','州'),('guo','国'),('fu','府'),('jun','军' if year==1102 else '郡')]
                       if key(attrs['PrefNAM']).endswith(en)), '')
        buffered = geometry.buffer(.15)
        near = [r for r in candidates if (not suffix or r[2].endswith(suffix)) and buffered.intersects(r[3])]
        current = [r for r in near if r[4] <= year <= r[5]]
        chosen = current or near
        points = [r for r in chosen if r[1]=='chgis-pref-point']
        chosen = points or chosen
        names = {r[2] for r in chosen}
        if len(names) == 1:
            return next(iter(names)), 'CHGIS name identity: '+','.join(sorted(r[0] for r in chosen))
        return None, 'unresolved_chinese_name'
