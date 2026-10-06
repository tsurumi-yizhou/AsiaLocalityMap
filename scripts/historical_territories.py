"""Reviewed display aliases; never merge POLITY geometry through allegiance/RELATION rows."""
ALIASES = {
 'Qin Dynasty':'秦','Han Dynasty':'汉','Xin Dynasty':'新','Cao Cao':'曹操势力',
 'Cao Wei':'魏','Shu Han':'蜀汉','Eastern Wu':'吴','Western Jin':'晋',
 'Liu Song Dynasty':'刘宋','Southern Qi':'南齐','Liang Dynasty':'梁','Chen Dynasty':'陈',
 'Northern Wei':'北魏','Eastern Wei':'东魏','Western Wei':'西魏','Northern Qi':'北齐','Northern Zhou':'北周',
 'Former Yan':'前燕','Later Yan':'后燕','Former Qin':'前秦','Later Qin':'后秦',
 'Former Liang':'前凉','Later Liang':'后凉','Northern Liang':'北凉','Western Liang':'西凉',
 'Southern Liang':'南凉','Western Qin':'西秦','Tuyuhun':'吐谷浑','Li Zicheng':'李自成势力',
 'Sui Dynasty':'隋','Tang Dynasty':'唐','Northern Song':'北宋','Southern Song':'南宋',
 'Liao Dynasty':'辽','Western Liao':'西辽','Great Jin':'金','Yuan Dynasty':'元',
 'Ming Dynasty':'明','Southern Ming':'南明','Qing Dynasty':'清',
 'Western Xia':'西夏','Mongol Empire':'蒙古','Xiongnu':'匈奴','Xianbei':'鲜卑','Rouran Khaganate':'柔然',
 'Nanzhao':'南诏','Kingdom of Dali':'大理','Tibetan Empire':'吐蕃',
 'Southern Han':'南汉','Southern Tang':'南唐','Southern Chu':'楚',
 'Goguryeo':'高句丽','Baekje':'百济','Silla':'新罗','Unified Silla':'新罗',
 'Balhae':'渤海','Goryeo':'高丽','Joseon':'朝鲜','Korean Empire':'大韩帝国',
 'Mahan':'马韩','Jinhan':'辰韩','Byeonhan':'弁韩','Dongye':'东濊','Dong-okjeo':'沃沮',
 'Tamna':'耽罗','Hubaekje':'后百济','Taebong':'泰封',
 'Asuka Japan':'大和','Nara Japan':'奈良时代日本','Heian Japan':'平安时代日本',
 'Northern Fujiwara':'奥州藤原氏','Kamakura Shogunate':'镰仓幕府','Kenmu Restoration':'建武政权',
 'Ashikaga Shogunate':'室町幕府','Warring States Japan':'战国日本','Tokugawa Shogunate':'江户幕府',
 'Empire of Japan':'明治日本','Early Lý Dynasty':'万春','Lê Dynasty':'后黎',
 'Trịnh lords':'郑主','Nguyễn lords':'阮主','Tây Sơn dynasty':'西山',
 'Nguyễn dynasty':'阮朝','Chámpa':'占城','Funan':'扶南','Chenla':'真腊',
 'Land Chenla':'陆真腊','Water Chenla':'水真腊','Khmer Empire':'高棉',
 'Cambodia':'柬埔寨','Lan Xang':'澜沧','Lan Na Kingdom':'兰纳',
 'Russian Empire':'俄罗斯帝国',
 'Wusun':'乌孙','Yuezhi':'月氏','Minyue':'闽越','Âu Lạc':'瓯雒',
 'Protectorate of the Western Regions':'西域都护府','Qocho Kingdom':'高昌',
 'Kara-Khitans':'西辽','Shunten Dynasty':'舜天王统','French Indochina':'法属印度支那',
}
CHINESE = {'Qin Dynasty','Han Dynasty','Xin Dynasty','Cao Cao','Cao Wei','Shu Han','Eastern Wu','Western Jin',
           'Liu Song Dynasty','Southern Qi','Liang Dynasty','Chen Dynasty','Northern Wei','Eastern Wei',
           'Western Wei','Northern Qi','Northern Zhou','Former Yan','Later Yan','Former Qin','Later Qin',
           'Former Liang','Later Liang','Northern Liang','Western Liang','Southern Liang','Western Qin',
           'Sui Dynasty','Tang Dynasty','Northern Song','Southern Song','Liao Dynasty','Great Jin','Yuan Dynasty',
           'Ming Dynasty','Southern Ming','Qing Dynasty','Later Jin Dynasty','Southern Han','Southern Tang','Southern Chu',
           'Western Xia','Nanzhao','Kingdom of Dali','Li Zicheng','Minyue'}
KOREAN = {'Goguryeo','Baekje','Silla','Unified Silla','Balhae','Goryeo','Joseon','Korean Empire',
          'Mahan','Jinhan','Byeonhan','Dongye','Dong-okjeo','Tamna','Hubaekje','Taebong'}
JAPANESE = {'Asuka Japan','Nara Japan','Heian Japan','Northern Fujiwara','Kamakura Shogunate',
            'Kenmu Restoration','Ashikaga Shogunate','Warring States Japan','Tokugawa Shogunate','Empire of Japan'}
VIETNAMESE = {'Ngô Dynasty','Early Lý Dynasty','Lê Dynasty','Đại Việt','Trịnh lords','Nguyễn lords',
              'Tây Sơn dynasty','Nguyễn dynasty','Chámpa','French Indochina'}

def region(name):
    if name in KOREAN: return 'kr'
    if name in JAPANESE: return 'jp'
    if name in VIETNAMESE: return 'vn'
    return 'cn' if name in CHINESE else 'ea'

def label(attributes, year):
    name = attributes['Name']
    # Keep original names/identifiers in the research DB; correct only independently checked labels.
    if name == 'Later Jin Dynasty': return '清' if year >= 1636 else '后金'
    if name == 'Ngô Dynasty':
        if year >= 1400: return '大虞'
        if year >= 1054: return '大越'
        if year >= 968: return '大瞿越'
        return '吴朝'
    if name == 'Đại Việt' and attributes.get('Wikipedia') == 'Mạc dynasty': return '莫朝'
    if name == 'French Indochina': return '法属交趾支那' if year < 1887 else '法属印度支那'
    return ALIASES.get(name, name)

# Chinese overlays follow the selected dynasty/period, not every polity whose map
# intersects today's China. Other regions retain their own historical context.
CN_POLITIES = {
 'han': {'Han Dynasty'}, 'song': {'Northern Song'},
 'qin': {'Qin Dynasty'}, 'western_han': {'Han Dynasty'}, 'eastern_han': {'Han Dynasty'},
 'three_kingdoms': {'Cao Wei','Shu Han','Eastern Wu'},
 'western_jin': {'Western Jin'},
 'eastern_jin': {'Western Jin','Former Yan','Later Yan','Former Qin','Later Qin','Northern Liang','Southern Liang','Western Qin','Later Liang','Northern Wei'},
 'northern_southern': {'Northern Wei','Eastern Wei','Western Wei','Northern Qi','Northern Zhou','Liu Song Dynasty','Southern Qi','Liang Dynasty','Chen Dynasty'},
 'sui': {'Sui Dynasty'}, 'tang': {'Tang Dynasty'},
 'five_dynasties': {'Later Liang Dynasty','Later Tang','Later Jin','Later Han','Later Zhou','Former Shu','Later Shu','Southern Wu','Southern Tang','Southern Han','Northern Han','Wuyue','Min','Southern Chu','Qi Kingdom','Yan Kingdom'},
 'northern_song': {'Northern Song'}, 'southern_song': {'Southern Song'},
 'yuan': {'Yuan Dynasty','Mongol Empire'}, 'ming': {'Ming Dynasty'},
}
CHINESE.update(set().union(*CN_POLITIES.values()))
VIETNAM_CONTEXT = {'Funan','Chenla','Land Chenla','Water Chenla','Khmer Empire','Cambodia'}
ALIASES.update({'Goguryeo':'高句麗','Baekje':'百濟','Goryeo':'高麗','Joseon':'朝鮮',
                'Korean Empire':'大韓帝國','Mahan':'馬韓','Dongye':'東濊','Hubaekje':'後百濟',
                'Early Lý Dynasty':'萬春','Lê Dynasty':'後黎','Trịnh lords':'鄭主',
                'Tây Sơn dynasty':'西山','Later Liang Dynasty':'後梁','Later Tang':'後唐',
                'Later Jin':'晉','Later Han':'後漢','Later Zhou':'後周','Former Shu':'前蜀',
                'Later Shu':'後蜀','Northern Han':'北漢','Wuyue':'吳越','Min':'閩',
                'Southern Wu':'吳','Qi Kingdom':'岐','Yan Kingdom':'燕'})
