"""Reviewed early Korean administrative centers, not reconstructed boundaries.

Names and city correspondences: AKS Encyclopedia (Nine Provinces, Cities) and
National Institute of Korean History (Eight Mok). Coordinates identify the
reference city only, not a surveyed government office. Coverage is deliberately
limited to these documented centers; no Joseon boundary is backprojected.
Eight-Mok names are historical institutional references, not a complete list
of offices active in 1370.
"""
SILLA_SOURCE = 'https://encykorea.aks.ac.kr/Article/E0006042'
CAPITAL_SOURCE = 'https://encykorea.aks.ac.kr/Article/E0015742'
GORYEO_SOURCE = 'https://contents.history.go.kr/front/ta/webBook.do?levelId=ta_p51_0030_0020_0020_0010'
# reference year, kind, name, native name, longitude, latitude, citation
ROWS = [
 (757,'州治参考','尙州','상주',128.159,36.411,SILLA_SOURCE),
 (757,'州治参考','良州','양주',129.038,35.338,SILLA_SOURCE),
 (757,'州治参考','康州','강주',128.084,35.180,SILLA_SOURCE),
 (757,'州治参考','漢州','한주',127.206,37.539,SILLA_SOURCE),
 (757,'州治参考','朔州','삭주',127.730,37.882,SILLA_SOURCE),
 (757,'州治参考','溟州','명주',128.896,37.752,SILLA_SOURCE),
 (757,'州治参考','熊州','웅주',127.124,36.446,SILLA_SOURCE),
 (757,'州治参考','全州','전주',127.148,35.815,SILLA_SOURCE),
 (757,'州治参考','武州','무주',126.913,35.149,CAPITAL_SOURCE),
 (757,'小京参考','金官京','금관경',128.881,35.234,CAPITAL_SOURCE),
 (757,'小京参考','中原京','중원경',127.925,36.991,CAPITAL_SOURCE),
 (757,'小京参考','北原京','북원경',127.945,37.349,CAPITAL_SOURCE),
 (757,'小京参考','西原京','서원경',127.489,36.643,CAPITAL_SOURCE),
 (757,'小京参考','南原京','남원경',127.390,35.408,CAPITAL_SOURCE),
 (1370,'牧治参考','廣州牧','광주목',127.206,37.539,GORYEO_SOURCE),
 (1370,'牧治参考','忠州牧','충주목',127.925,36.991,GORYEO_SOURCE),
 (1370,'牧治参考','淸州牧','청주목',127.489,36.643,GORYEO_SOURCE),
 (1370,'牧治参考','晉州牧','진주목',128.084,35.180,GORYEO_SOURCE),
 (1370,'牧治参考','尙州牧','상주목',128.159,36.411,GORYEO_SOURCE),
 (1370,'牧治参考','全州牧','전주목',127.148,35.815,GORYEO_SOURCE),
 (1370,'牧治参考','羅州牧','나주목',126.717,35.032,GORYEO_SOURCE),
 (1370,'牧治参考','黃州牧','황주목',125.776,38.670,GORYEO_SOURCE),
]
