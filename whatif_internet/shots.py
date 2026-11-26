"""Сценарий и раскадровка «Что если интернет отключится по всему миру?» — единый источник.

python shots.py  →  build/shots.json, script_voiceover.txt, storyboard.md

Каждая строка: (текст озвучки, визуал, надпись на экране).
Визуал: "img:<ключ>" — реальное фото из ASSETS (Wikimedia Commons), "card" — заставка раздела,
или словарь инфографики {"kind": ...}. Каждый ключ фото используется один раз — фото не повторяются.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TITLE = "Что если интернет отключится по всему миру?"

# ключ → поисковые запросы в Wikimedia Commons (через «|» — запасные варианты)
ASSETS = {
    "phone_dark": "smartphone in hand dark|smartphone screen night|mobile phone night",
    "people_phones": "people using smartphones|commuters smartphones|smartphone users",
    "city_lights": "city at night aerial|night city lights|city skyline night",
    "router": "wireless router|wifi router|network router",
    "smartphone_apps": "smartphone apps|smartphone home screen|mobile apps",
    "server_room": "server room|server racks|data center",
    "office_entrance": "security turnstile|office turnstiles|office lobby",
    "earth_night": "earth at night from space|night lights from space|city lights from space",
    "card_terminal": "card payment terminal|contactless payment|payment terminal",
    "supermarket_queue": "supermarket checkout|checkout queue|supermarket cashier",
    "atm_line": "automated teller machine|ATM machine|cash machine",
    "stock_exchange": "trading floor|stock exchange trading floor|New York Stock Exchange floor",
    "airport_board": "airport departures board|departure board airport|flight information display",
    "airport_crowd": "airport check-in queue|airport terminal crowd|airport terminal",
    "gps_navigation": "car navigation system|GPS navigation device|satellite navigation car",
    "office_dark": "office at night|dark office|empty office night",
    "warehouse": "distribution center|logistics warehouse|warehouse shelves",
    "container_port": "container terminal|container port|shipping containers port",
    "container_ship": "Maersk container ship|container ship|cargo ship",
    "paperwork": "stack of papers|paperwork|documents desk",
    "hospital": "hospital corridor|hospital ward|nurses station",
    "home_office": "home office|working from home|laptop at home",
    "radio_vintage": "vintage radio|old radio receiver|transistor radio",
    "neighbors": "people talking street|neighbours talking|conversation street",
    "empty_shelves": "empty supermarket shelves|empty shelves|bare shelves",
    "post_office": "post office counter|post office|mail sorting",
    "ocean": "ocean waves|open ocean|deep sea",
    "submarine_cable": "submarine communications cable|submarine cable|undersea cable",
    "cable_ship": "cable ship|cable laying ship|cable layer ship",
    "shovel_dig": "digging with shovel|shovel digging|trench digging",
    "yerevan": "Yerevan|Yerevan panorama|Yerevan city",
    "sun_flare": "solar flare|coronal mass ejection|Solar Dynamics Observatory",
    "aurora": "aurora borealis|northern lights|aurora",
    "telegraph": "telegraph key|telegraph instrument|morse telegraph",
    "power_lines": "high voltage power lines|transmission towers|power lines winter",
    "cell_tower": "cell tower|mobile phone mast|telecommunication tower",
    "city_morning": "quiet street morning|city morning street|empty street morning",
    "cash_wallet": "wallet cash|cash money|banknotes",
    "switchboard": "telephone switchboard operators|switchboard operator|telephone exchange operators",
    "newspaper": "reading newspaper|man reading newspaper|newspaper reader",
    "friends_talking": "friends talking|people conversation cafe|friends laughing",
    "laboratory": "laboratory scientist|science laboratory|laboratory research",
    "technicians": "fiber optic splicing|network technician|cable technician",
    "map_phone": "smartphone map|map on smartphone|navigation app smartphone",
    "notebook": "handwritten notes|notebook pen|address book",
    "flashlight": "flashlight|torch light|power bank",
    "family_walk": "family walking park|family outdoors|family walking",
    "fiber_cables": "fiber optic cables|optical fiber|network cables",
    "phone_call": "making phone call street|person phone call|talking on mobile phone",
    "taxi": "taxi cab street|yellow taxi|taxi night",
    "factory_line": "car factory assembly line|assembly line factory|production line",
    "market": "farmers market stall|grocery market|market stall",
    "craftsman": "carpenter workshop|craftsman workshop|repair workshop",
    "kids_playing": "children playing outdoors|kids playing street|children playground",
    "cash_home": "piggy bank|money jar|coins savings",
    "park_people": "people relaxing in park|picnic in park|people in park",
    "closed_shop": "closed shop|shuttered shop|closed store",
}

# поиск в PD12M по подписям: все группы должны совпасть (регулярные выражения, нижний регистр)
PD_QUERIES = {
    "phone_dark": [r"smartphone|mobile phone|cell phone|cellphone|iphone", r"hand|holding|dark|black background|night"],
    "people_phones": {"all": [r"people|commuters|passengers|crowd|pedestrians|young", r"smartphones|their phones|mobile phones|cell phones|looking at (their|a) phone"], "not": r"saxophone|headphone|microphone|telephone"},
    "city_lights": [r"\bcity\b|skyline|cityscape", r"at night|night sky|night time|nighttime"],
    "router": [r"\brouter\b|wi-?fi router|modem"],
    "smartphone_apps": [r"smartphone|iphone|android", r"screen|apps|icons|display", r"\bapps?\b|icons|home screen"],
    "server_room": [r"servers?\b|data cent(er|re)|server rack"],
    "office_entrance": [r"turnstiles?|security gates?|access control|ticket barriers?"],
    "earth_night": [r"\bearth\b", r"night", r"space|orbit|space station|from above"],
    "card_terminal": [r"payment terminal|card reader|card terminal|pos terminal|contactless|card payment"],
    "supermarket_queue": [r"supermarket|grocery store", r"checkout|cashier|queue|cash register"],
    "atm_line": [r"\batm\b|automated teller|cash machine|cash dispenser"],
    "stock_exchange": [r"stock exchange|trading floor|traders"],
    "airport_board": [r"departure board|departures board|flight information|arrivals board|departure screen|flight board"],
    "airport_crowd": {"all": [r"airport", r"terminal|check-in|hall", r"passengers|travell?ers|people|crowd"], "not": r"aircraft|airplane|jet|plane|runway|military|soldier"},
    "gps_navigation": [r"\bgps\b|navigation system|navigation device|sat ?nav"],
    "office_dark": [r"\boffice\b", r"\bat night\b|\bdark\b|\bempty\b"],
    "warehouse": [r"warehouse|distribution cent(er|re)|logistics cent(er|re)", r"shelves|racks|boxes|pallets"],
    "container_port": [r"containers?", r"port|harbou?r|terminal", r"cranes?"],
    "container_ship": [r"container ship|cargo ship|maersk"],
    "paperwork": [r"papers|documents|paperwork|files|folders", r"desk|stack|pile|table"],
    "hospital": {"all": [r"hospital", r"corridor|hallway|nurses?|doctors?"], "not": r"military|soldiers?|army|navy|marines?|museum"},
    "home_office": [r"laptop", r"home|living room|kitchen|sofa|couch"],
    "radio_vintage": [r"\bradio\b", r"old|vintage|antique|wooden|retro"],
    "neighbors": [r"people|men|women|neighbou?rs", r"talking|conversation|chatting", r"street|outside|outdoors|yard|courtyard"],
    "empty_shelves": [r"empty shelves|empty shelf|shelves (are|were) empty|bare shelves|empty supermarket"],
    "post_office": [r"post office|postal workers?|mail sorting|sorting (the )?mail|postal service"],
    "ocean": [r"ocean|\bsea\b", r"waves|horizon", r"sky"],
    "submarine_cable": [r"submarine cable|undersea cable|subsea cable|submarine communications cable|fib(er|re) optic cable"],
    "cable_ship": {"all": [r"fishing (boat|trawler|vessel|ship)|trawler", r"\bsea\b|ocean|nets?\b|waves"], "not": r"painting|model|toy|harbou?r|docked|moored"},
    "shovel_dig": [r"shovel|spade", r"digging|\bdig\b|soil|dirt|trench"],
    "yerevan": [r"yerevan"],
    "sun_flare": [r"\bsun\b|solar", r"flare|eruption|corona|prominence|plasma|filament"],
    "aurora": [r"aurora|northern lights"],
    "telegraph": [r"telegraph"],
    "power_lines": [r"power lines|transmission towers?|electricity pylons?|\bpylons?\b|transmission lines|high[- ]voltage"],
    "cell_tower": [r"cell tower|mobile phone mast|telecommunications? tower|cellular tower|antennas? tower|communications tower|radio mast"],
    "city_morning": {"all": [r"city|town|skyline", r"sunrise|dawn|morning light|early morning"], "not": r"painting|drawing|snow|sign"},
    "cash_wallet": [r"wallet|banknotes|cash|money|bills", r"wallet|hand|table|notes"],
    "switchboard": {"all": [r"rotary (dial )?(tele)?phone|vintage telephone|old telephone|antique telephone|old-fashioned telephone"], "not": r"booth|museum display case"},
    "newspaper": [r"newspaper", r"reading|reads"],
    "friends_talking": {"all": [r"friends|two women|two men|young people|group of people", r"laughing|talking|chatting|conversation", r"table|cafe|café|sitting|bench"], "not": r"sign|banner|uniform|military|navy|conference|meeting"},
    "laboratory": [r"laboratory|\blab\b", r"scientists?|researchers?|microscope|test tubes|pipette"],
    "technicians": [r"technicians?|engineers?|workers?", r"fib(er|re)|cables?|network|wires|wiring"],
    "map_phone": [r"\bmap\b", r"smartphone|phone|mobile"],
    "notebook": [r"notebook|address book|notepad|diary|handwritten", r"pen|writing|handwriting|notes"],
    "flashlight": {"all": [r"flashlight|power bank|powerbank|portable charger|torch\b"], "not": r"olympic|candle|lantern|parade"},
    "family_walk": [r"family|parents|mother|father", r"children|kids|child|son|daughter", r"walking|walk|park|path"],
    "fiber_cables": [r"fib(er|re) optic|optical fib(er|re)|network cables|ethernet cables|patch cables|patch panel"],
    "phone_call": [r"phone|mobile|cell", r"talking on|on the phone|calling|phone call", r"man|woman|person"],
    "taxi": [r"\btaxi|\bcabs?\b"],
    "factory_line": [r"assembly line|production line", r"car|cars|automobile|workers|robots"],
    "market": [r"market", r"stalls?|vendors?|fruits?|vegetables|produce"],
    "craftsman": [r"carpenter|craftsman|woodworker|repairman|blacksmith|workshop", r"working|tools|wood|workbench"],
    "kids_playing": [r"children|kids|boys|girls", r"playing", r"outside|outdoors|yard|street|park|playground"],
    "cash_home": [r"piggy bank|jar of coins|jar (full |filled )?(of|with) coins|money jar|coins"],
    "park_people": {"all": [r"people", r"\bpark\b", r"sitting on the grass|picnic|relaxing|lying on the grass|on the lawn"], "not": r"sepia|black and white|old photograph"},
    "closed_shop": [r"closed|shuttered|abandoned|boarded", r"shop|store|storefront|mall"],
}

# ключевые основы для подсветки в субтитрах (в дополнение к общим)
KEYWORDS = ["интернет", "сет", "кабел", "солнц", "бур", "банкомат", "карт", "рейс", "компьютер", "кабел",
            "наличн", "радио", "телеграф", "лопат", "армени", "маерск", "фейсбук", "краудстрайк", "триллион",
            "отключ", "офлайн", "пауэрбанк", "квебек", "кэррингтон"]

SECTIONS = [  # (ключ, заголовок заставки, настроение музыки)
    ("hook", "", "mystery"),
    ("minutes", "ПЕРВЫЕ МИНУТЫ", "tense"),
    ("day1", "ДЕНЬ 1", "tense"),
    ("week1", "НЕДЕЛЯ 1", "mystery"),
    ("month1", "МЕСЯЦ 1", "epic"),
    ("real", "ЭТО РЕАЛЬНО?", "mystery"),
    ("year1", "ГОД СПУСТЯ", "epic"),
    ("now", "ЧТО ДЕЛАТЬ СЕЙЧАС", "upbeat"),
]
S = {k: [] for k, _, _ in SECTIONS}


def add(sec, text, visual, onscreen="", **kw):
    S[sec].append({"text": text, "visual": visual, "onscreen": onscreen, **kw})


# ---------------------------------------------------------------- ХУК
add("hook", "Представь: ты берёшь телефон, а там пусто. Ни сообщений, ни карт, ни видео. Интернет исчез. Везде и сразу.",
    "img:phone_dark", "НЕТ СЕТИ")
add("hook", "Сегодня в интернете около шести миллиардов человек — это три четверти населения Земли.",
    {"kind": "counter", "label": "ЛЮДЕЙ В ИНТЕРНЕТЕ", "from": 0, "to": 6000000000, "note": "ITU, Facts and Figures 2025"})
add("hook", "И в среднем каждый из нас проводит онлайн шесть с половиной часов в день.", "img:people_phones",
    "6 Ч 38 МИН В ДЕНЬ")
add("hook", "Мы привыкли, что интернет есть всегда, как воздух. Но держится он на удивительно хрупких вещах.",
    "img:fiber_cables", "ХРУПКАЯ СЕТЬ")
add("hook", "Что станет с деньгами, едой, самолётами и с нами самими, если всё это выключится?", "img:city_lights")
add("hook", "Давай проживём этот сценарий шаг за шагом: первые минуты, первый день, неделя, месяц и год без интернета.",
    {"kind": "timeline", "title": "СЦЕНАРИЙ", "items": ["МИНУТЫ", "ДЕНЬ 1", "НЕДЕЛЯ", "МЕСЯЦ", "ГОД"]})
add("hook", "А ещё разберёмся, может ли такое случиться на самом деле. Спойлер: кое-что подобное уже происходило.",
    "img:server_room", "ЭТО УЖЕ БЫЛО")

# ---------------------------------------------------------------- ПЕРВЫЕ МИНУТЫ
add("minutes", "Первые минуты.", "card")
add("minutes", "Сначала никто ничего не понимает. Люди перезагружают роутеры и ругаются на провайдера.", "img:router")
add("minutes", "Но дело не в твоей квартире. Отключилось всё сразу: мессенджеры, соцсети, почта, облака и сайты.",
    "img:smartphone_apps", "ОТКЛЮЧИЛОСЬ ВСЁ")
add("minutes", "Маленькую репетицию мир уже видел. Четвёртого октября две тысячи двадцать первого года Фейсбук, Инстаграм и Ватсап пропали почти на шесть часов.",
    {"kind": "factcard", "title": "4 ОКТЯБРЯ 2021", "rows": [["Что пропало", "Facebook · Instagram · WhatsApp"],
                                                            ["Сколько", "≈ 6 часов"], ["Причина", "ошибка настройки сети"]],
     "photo": "office_dark"})
add("minutes", "Ошибка в настройке сети отрезала компанию от интернета, и даже электронные пропуска сотрудников перестали работать.",
    "img:office_entrance", "ПРОПУСКА НЕ РАБОТАЮТ")
add("minutes", "А теперь представь такой сбой не у одной компании, а у всей планеты.", "img:earth_night", "У ВСЕЙ ПЛАНЕТЫ")
add("minutes", "Сотни миллионов людей одновременно пытаются дозвониться родным, и мобильные сети захлёбываются от нагрузки.",
    "img:phone_call", "СЕТИ ПЕРЕГРУЖЕНЫ")
add("minutes", "И первое, что ты заметишь, — картой больше нельзя заплатить.", "img:card_terminal", "ОПЛАТА НЕ ПРОХОДИТ")

# ---------------------------------------------------------------- ДЕНЬ 1
add("day1", "День первый.", "card")
add("day1", "Терминалы в магазинах не могут связаться с банком. Очереди растут, а наличных у большинства с собой почти нет.",
    "img:supermarket_queue")
add("day1", "Люди бегут к банкоматам, но многие из них тоже работают через сеть.", "img:atm_line", "БАНКОМАТЫ ЗАВИСЛИ")
add("day1", "Биржи останавливают торги: без связи невозможно ни купить, ни продать.", "img:stock_exchange",
    "ТОРГИ ОСТАНОВЛЕНЫ")
add("day1", "В аэропортах начинается хаос. Регистрация, багаж, расписание — всё завязано на компьютерные системы.",
    "img:airport_board")
add("day1", "Девятнадцатого июля две тысячи двадцать четвёртого года одно неудачное обновление программы КраудСтрайк вывело из строя восемь с половиной миллионов компьютеров на Виндоус.",
    {"kind": "counter", "label": "КОМПЬЮТЕРОВ ВЫШЛО ИЗ СТРОЯ", "from": 0, "to": 8500000, "note": "CrowdStrike, 19 июля 2024"})
add("day1", "За один день в мире отменили больше пяти тысяч рейсов.",
    {"kind": "counter", "label": "РЕЙСОВ ОТМЕНЕНО ЗА ОДИН ДЕНЬ", "from": 0, "to": 5078, "note": "≈ 4,6% всех рейсов в мире"})
add("day1", "И это был не конец интернета, а ошибка в одном-единственном файле.", "img:airport_crowd",
    "ВСЕГО ОДИН ФАЙЛ")
add("day1", "Такси по приложению не вызвать, а доставка еды просто исчезает из твоей жизни.", "img:taxi", "ТАКСИ НЕ ВЫЗВАТЬ")
add("day1", "Навигатор ещё покажет точку на карте: спутники работают и без интернета. Но если карты не скачаны заранее, вокруг будет пустой серый экран.",
    "img:gps_navigation", "КАРТЫ НЕ ГРУЗЯТСЯ")
add("day1", "А настоящие проблемы начнутся через несколько дней, когда в магазинах закончатся запасы.", "img:empty_shelves")

# ---------------------------------------------------------------- НЕДЕЛЯ 1
add("week1", "Неделя первая.", "card")
add("week1", "Магазины почти не держат больших складов. Товар едет ровно тогда, когда нужен, а заказы передаются через сеть.",
    "img:warehouse")
add("week1", "Без интернета фуры стоят, контейнеры в портах невозможно отследить, и полки начинают пустеть.",
    "img:container_port", "ПОРТЫ ВСТАЛИ")
add("week1", "Это не фантазия. В две тысячи семнадцатом году вирус НотПетя уничтожил компьютерную сеть Маерск — одной из крупнейших судоходных компаний мира.",
    {"kind": "factcard", "title": "MAERSK, 2017", "rows": [["Атака", "вирус NotPetya"],
                                                          ["Переустановили", "45 000 ПК · 4 000 серверов"],
                                                          ["Ущерб", "$250–300 млн"]], "photo": "container_ship"})
add("week1", "Около десяти дней огромная компания работала почти вручную: на бумаге, по телефону и в обычных таблицах.",
    "img:paperwork", "10 ДНЕЙ ВРУЧНУЮ")
add("week1", "Заводы останавливают конвейеры: детали больше не приходят вовремя, потому что заказы некому передать.",
    "img:factory_line", "ЗАВОДЫ ВСТАЮТ")
add("week1", "Больницы переходят на бумажные карты, а врачи договариваются по телефону.", "img:hospital",
    "БУМАЖНЫЕ КАРТЫ")
add("week1", "Удалённая работа заканчивается в один день. Миллионы людей просто не могут ничего сделать.", "img:home_office")
add("week1", "Зато оживает то, о чём мы почти забыли.",
    {"kind": "list", "title": "ЧТО РАБОТАЕТ БЕЗ ИНТЕРНЕТА", "color": "green",
     "items": ["Радио и телевидение", "Наличные деньги", "Бумажные карты", "Спутники навигации", "Звонки — если работают вышки"]})
add("week1", "Радио снова становится главным источником новостей.", "img:radio_vintage", "СНОВА РАДИО")
add("week1", "А люди выходят во двор, чтобы узнать новости у соседей.", "img:neighbors")

# ---------------------------------------------------------------- МЕСЯЦ 1
add("month1", "Месяц первый.", "card")
add("month1", "Через месяц экономика выглядит так, будто по ней прошёл ураган.",
    {"kind": "chart_down", "title": "МИРОВАЯ ТОРГОВЛЯ", "note": "иллюстрация сценария", "label": "ОБВАЛ"})
add("month1", "Целые отрасли просто исчезли.",
    {"kind": "list", "title": "ИСЧЕЗЛИ ЗА МЕСЯЦ", "color": "red",
     "items": ["Онлайн-магазины", "Такси и доставка по приложению", "Соцсети и стриминг", "Мобильные банки", "Удалённая работа"]})
add("month1", "Миллионы людей остались без работы, и государства срочно возвращают старые способы: почту, курьеров и бумажные документы.",
    "img:post_office", "ВОЗВРАЩЕНИЕ ПОЧТЫ")
add("month1", "Цены на самое необходимое растут: доставить товар стало в разы сложнее.", "img:market", "ЦЕНЫ РАСТУТ")
add("month1", "Зато в цене снова те, кто умеет работать руками и договариваться без смартфона.", "img:craftsman",
    "РУКИ СНОВА В ЦЕНЕ")
add("month1", "И тут появляется главный вопрос: а можно ли вообще выключить интернет всей планеты?",
    {"kind": "bigtext", "text": "МОЖНО ЛИ ВЫКЛЮЧИТЬ ИНТЕРНЕТ?", "sub": "разбираемся на реальных случаях"})

# ---------------------------------------------------------------- ЭТО РЕАЛЬНО?
add("real", "Это реально?", "card")
add("real", "Интернет кажется облаком, но на самом деле он лежит на дне океана.", "img:ocean", "ИНТЕРНЕТ НА ДНЕ ОКЕАНА")
add("real", "Больше девяноста девяти процентов данных между континентами идёт по подводным кабелям. Их общая длина — почти полтора миллиона километров.",
    {"kind": "counter", "label": "ДАННЫХ МЕЖДУ КОНТИНЕНТАМИ — ПО КАБЕЛЯМ", "from": 0, "to": 99, "suffix": "%",
     "note": "TeleGeography · ≈ 1,4 млн км кабелей"})
add("real", "При этом многие такие кабели толщиной примерно с садовый шланг.", "img:submarine_cable",
    "ТОЛЩИНОЙ С САДОВЫЙ ШЛАНГ")
add("real", "Их рвут якоря и рыболовные сети, поэтому специальные корабли постоянно чинят их прямо в море.", "img:cable_ship")
add("real", "А в две тысячи одиннадцатом году семидесятипятилетняя жительница Грузии искала металлолом и перерубила лопатой оптический кабель.",
    "img:shovel_dig", "ЛОПАТА ПРОТИВ ИНТЕРНЕТА")
add("real", "Почти вся Армения на несколько часов осталась без интернета, а журналисты прозвали её хакером с лопатой.",
    {"kind": "factcard", "title": "АРМЕНИЯ, 2011", "rows": [["Причина", "лопата и кабель"], ["Без сети", "до 12 часов"],
                                                           ["Через Грузию шло", "≈ 90% интернета"]], "photo": "yerevan"})
add("real", "Но есть угроза пострашнее лопаты — Солнце.", "img:sun_flare", "УГРОЗА — СОЛНЦЕ")
add("real", "В тысяча восемьсот пятьдесят девятом году по Земле ударила мощнейшая солнечная буря — событие Кэррингтона. Северное сияние видели даже в тропиках.",
    "img:aurora", "1859 · СОБЫТИЕ КЭРРИНГТОНА")
add("real", "Телеграфы по всему миру сходили с ума: провода искрили, операторов било током, а некоторые линии работали даже с отключёнными батареями.",
    "img:telegraph", "ТЕЛЕГРАФЫ ИСКРИЛИ")
add("real", "В марте тысяча девятьсот восемьдесят девятого года буря послабее всего за полторы минуты обрушила энергосистему Квебека, и миллионы людей больше девяти часов сидели без света.",
    "img:power_lines", "КВЕБЕК, 1989")
add("real", "А в июле две тысячи двенадцатого года выброс такой же силы, как в тысяча восемьсот пятьдесят девятом, прошёл мимо Земли. Случись он на неделю раньше — удар пришёлся бы по нам.",
    {"kind": "bigtext", "text": "2012: ПРОНЕСЛО", "sub": "выброс силы Кэррингтона разминулся с Землёй"})
add("real", "Страховой рынок Ллойдс оценивал ущерб от такой бури только для США в сумму до двух триллионов шестисот миллиардов долларов.",
    {"kind": "counter", "label": "ВОЗМОЖНЫЙ УЩЕРБ ДЛЯ США", "from": 0, "to": 2600, "prefix": "$", "suffix": " МЛРД",
     "note": "Lloyd's, 2013: от $600 до $2600 млрд"})
add("real", "И есть ещё одна сторона: интернет выключают специально. В две тысячи двадцать четвёртом году его отключали двести девяносто шесть раз в пятидесяти четырёх странах.",
    {"kind": "counter", "label": "ОТКЛЮЧЕНИЙ ИНТЕРНЕТА ЗА 2024 ГОД", "from": 0, "to": 296, "note": "Access Now · 54 страны"})
add("real", "Так что для миллионов людей день без интернета — уже не фантастика.", "img:cell_tower", "УЖЕ НЕ ФАНТАСТИКА")

# ---------------------------------------------------------------- ГОД СПУСТЯ
add("year1", "Год спустя.", "card")
add("year1", "Допустим, сеть так и не вернулась. Что дальше?", "img:city_morning")
add("year1", "Мир медленно перестраивается. Возвращаются наличные, бумажные квитанции и почтовые переводы.", "img:cash_wallet")
add("year1", "Компании снова нанимают курьеров, архивистов и телефонистов — профессии, которые казались вымершими.",
    "img:switchboard", "ТЕЛЕФОНИСТЫ ВОЗВРАЩАЮТСЯ")
add("year1", "Новости приходят раз в день, а не каждую секунду.", "img:newspaper")
add("year1", "Дети, которые родились с планшетом в руках, учатся по бумажным учебникам и целыми днями играют во дворе.",
    "img:kids_playing")
add("year1", "И многие замечают неожиданное: им стало спокойнее. Меньше тревоги, больше живого общения.",
    "img:friends_talking", "МЕНЬШЕ ТРЕВОГИ")
add("year1", "Но цена огромна. Учёные теряют быстрый обмен данными, и новые лекарства и технологии появляются гораздо медленнее.",
    "img:laboratory", "ПРОГРЕСС ЗАМЕДЛИЛСЯ")
add("year1", "В итоге мир без интернета получается спокойнее, но беднее и медленнее.",
    {"kind": "split", "left": "СПОКОЙНЕЕ", "right": "БЕДНЕЕ", "left_sub": "живое общение", "right_sub": "медленный прогресс",
     "left_photo": "park_people", "right_photo": "closed_shop"})
add("year1", "И люди почти сразу начнут строить новую сеть — только на этот раз с запасным планом на случай катастрофы.",
    "img:technicians", "НОВАЯ СЕТЬ")

# ---------------------------------------------------------------- ЧТО ДЕЛАТЬ СЕЙЧАС
add("now", "Что делать уже сейчас.", "card")
add("now", "Полностью интернет вряд ли исчезнет: у сети тысячи запасных маршрутов. Но местные отключения случаются постоянно.",
    {"kind": "bigtext", "text": "ГЛОБАЛЬНО — ВРЯД ЛИ. ЛОКАЛЬНО — ПОСТОЯННО", "sub": ""})
add("now", "Поэтому вот пять простых шагов на случай дня без сети.",
    {"kind": "list", "title": "ПЛАН НА ДЕНЬ БЕЗ СЕТИ", "color": "blue",
     "items": ["Наличные на несколько дней", "Офлайн-карты в телефоне", "Важные номера на бумаге",
               "Пауэрбанк и фонарик", "Место встречи с семьёй"]})
add("now", "Первое: держи дома немного наличных — хотя бы на несколько дней.", "img:cash_home", "1 · НАЛИЧНЫЕ")
add("now", "Второе: скачай офлайн-карты своего города.", "img:map_phone", "2 · ОФЛАЙН-КАРТЫ")
add("now", "Третье: запиши на бумаге телефоны близких. Многие сегодня не помнят наизусть ни одного номера.",
    "img:notebook", "3 · НОМЕРА НА БУМАГЕ")
add("now", "Четвёртое: заряженный пауэрбанк и фонарик.", "img:flashlight", "4 · ПАУЭРБАНК")
add("now", "И пятое: договорись с семьёй, где вы встречаетесь, если связи нет.", "img:family_walk", "5 · МЕСТО ВСТРЕЧИ")
add("now", "Интернет — это не облако, а кабели, серверы и люди. И чем сильнее мы от него зависим, тем важнее иметь запасной план.",
    {"kind": "bigtext", "text": "ИМЕЙ ЗАПАСНОЙ ПЛАН", "sub": "интернет — это кабели, серверы и люди"})
add("now", "Если было интересно, подпишись на канал и напиши в комментариях: что ты сделаешь первым делом, если интернет исчезнет?",
    {"kind": "endcard"}, "ПОДПИШИСЬ")


def build():
    shots, n = [], 0
    for sec, card, mood in SECTIONS:
        for line in S[sec]:
            n += 1
            shots.append({"id": n, "section": sec, "section_title": card, "mood": mood, **line})
    out = ROOT / "build"
    out.mkdir(exist_ok=True)
    (out / "shots.json").write_text(json.dumps({"title": TITLE, "assets": ASSETS, "sections": SECTIONS,
                                                "keywords": KEYWORDS, "shots": shots},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    paras = [" ".join(l["text"] for l in S[sec]) for sec, _, _ in SECTIONS]
    (ROOT / "script_voiceover.txt").write_text("\n\n".join(paras) + "\n", encoding="utf-8")
    kinds = {"list": "Инфографика-список", "counter": "Анимированный счётчик", "bars": "Анимированная диаграмма",
             "timeline": "Таймлайн", "bigtext": "Крупный текст", "factcard": "Карточка фактов с фото",
             "chart_down": "Падающий график", "split": "Экран делится на две половины",
             "endcard": "Конечная заставка с кнопкой подписки"}
    rows = [f"# Раскадровка: «{TITLE}»", "", "| № | Строка озвучки | Что на экране | Надпись на экране |", "|---|---|---|---|"]
    for s in shots:
        v = s["visual"]
        if v == "card":
            what, label = f"Заставка раздела «{s['section_title']}» (неон, глитч)", s["section_title"]
        elif isinstance(v, str):
            what, label = f"Фото: {ASSETS[v[4:]].split('|')[0]} (Ken Burns)", s["onscreen"]
        else:
            what = kinds.get(v["kind"], v["kind"])
            label = v.get("title") or v.get("text") or v.get("label") or s["onscreen"]
        rows.append(f"| {s['id']} | {s['text']} | {what} | {label} |")
    (ROOT / "storyboard.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    words = sum(len(s["text"].split()) for s in shots)
    print(f"{len(shots)} кадров, {words} слов, {sum(len(s['text']) for s in shots)} символов")
    used = [s["visual"][4:] for s in shots if isinstance(s["visual"], str) and s["visual"].startswith("img:")]
    used += [s["visual"]["photo"] for s in shots if isinstance(s["visual"], dict) and s["visual"].get("photo")]
    dup = {k for k in used if used.count(k) > 1}
    print("фото-кадров:", len(used), "| повторы ключей:", dup or "нет")


if __name__ == "__main__":
    build()
