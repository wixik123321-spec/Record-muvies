"""Сценарий и раскадровка «Что если исчезнут все пчёлы?» — единый источник.

python shots.py  →  build/shots.json, script_voiceover.txt, storyboard.md
Визуал: "img:<ключ>" — реальное фото (PD12M: Public Domain / CC0), "card" — заставка раздела,
или словарь инфографики {"kind": ...}. Каждый ключ фото используется один раз — фото не повторяются.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TITLE = "Что если исчезнут все пчёлы?"

# поиск фото в PD12M по подписям: все группы должны совпасть (регулярные выражения, нижний регистр)
PD_QUERIES = {
    "bee_flower": [r"\bbees?\b|honeybee|honey bee|bumblebee", r"flower|blossom|petals"],
    "einstein": [r"einstein"],
    "beekeeper": [r"beekeeper|apiarist", r"hive|bees|frame|smoker|honeycomb"],
    "hives": [r"beehives|bee hives|apiary|row of hives"],
    "honey_jars": [r"\bhoney\b", r"jars?\b"],
    "supermarket": [r"supermarket|grocery store", r"shelves|aisle|products"],
    "wheat_field": [r"wheat", r"field|crop|ears"],
    "blossom_orchard": [r"orchard", r"blossom|blooming|in bloom|flowering"],
    "apple_blossom": [r"apple", r"blossom"],
    "almond_orchard": [r"almond", r"orchard|trees"],
    "almond_blossom": [r"almond", r"blossom|flowers"],
    "berries": [r"blueberr(y|ies)|cherries|raspberries|strawberries"],
    "coffee": [r"coffee (beans|cherries|plant|plantation|berries)"],
    "cocoa": {"all": [r"chocolate"], "not": r"cake|cookie|ice cream|drink|cup|milk|brownie"},
    "market_fruit": [r"market|stall|vendor", r"fruits?|apples|oranges|berries"],
    "vegetables": [r"vegetables|tomatoes|cucumbers|peppers", r"table|basket|market|fresh|pile"],
    "cows": [r"\bcows?\b|cattle", r"pasture|field|grazing|meadow"],
    "bread_rice": {"all": [r"loaf of bread|loaves of bread|sliced bread|baguettes?|bread rolls|rye bread|bread loaf|freshly baked bread"], "not": r"fly|sandwich"},
    "apple_single": [r"\bred apple|an apple|single apple|apple on"],
    "meadow": [r"meadow|wildflowers", r"flowers|field|grass"],
    "hand_brush": {"all": [r"hands?", r"holding|touching|picking", r"flowers?|blossoms?"], "not": r"bouquet|wedding|bride"},
    "pear_blossom": [r"pear (tree|trees|blossoms?|flowers|orchard)|blossoming pear|flowering pear"],
    "orchard_worker": [r"orchard|fruit trees", r"workers?|farmers?|ladder|picking"],
    "pesticide": [r"spraying|sprayer|pesticides?|crop duster", r"field|crops|tractor|orchard|plants"],
    "lavender": [r"lavender"],
    "garden": [r"garden", r"flowers|gardening|flower bed|blooming"],
    "tall_grass": [r"tall grass|wild grass|unmown|long grass|grassland"],
    "bee_hotel": [r"insect hotel|bee hotel|bug hotel|bee house|insect house"],
    "sunflower": [r"sunflowers?"],
    "butterfly": [r"butterfly", r"flower"],
    "truck_hives": [r"beehives|bee hives|hives", r"truck|trailer|loaded|transport|stacked"],
    "bee_frame": [r"frame|comb|honeycomb", r"bees|bee\b"],
    "drone": {"all": [r"quadcopter|unmanned aerial|\bdrone\b", r"flying|sky|field|air"], "not": r"bee|wasp|insect"},
    "stumps": [r"tree stumps|stumps|felled trees|cut down trees|logging"],
    "honey_comb_close": [r"honeycomb|honey comb", r"honey|dripping|close"],
    "sunflower_bee": [r"sunflower|flower", r"\bbees?\b|bumblebee", r"pollen|close-up|nectar"],
    "farm_field": [r"farmland|agricultural field|fields of|crop field|harvest", r"combine|tractor|grain|wheat|corn"],
    "quiet_field": [r"field|landscape|meadow", r"fog|mist|grey sky|overcast|empty"],
    "balcony_flowers": [r"flower boxes?|window boxes?|potted (plants|flowers)|flower pots?|planters?", r"balcony|window|windowsill|terrace"],
    "local_honey": {"all": [r"\bhoney\b", r"market|stall|for sale|stand|vendor|fair"], "not": r"shop|mall|store|bear"},
    "village_market": [r"market", r"village|rural|street market|open-air"],
    "restaurant": [r"restaurant|cafe|café", r"menu|table|dinner|plates"],
    "empty_hive": [r"honeycomb|comb|hive frames?|bee frames?", r"empty|frame|wax|close"],
}
PD_BAD = (r"painting|drawing|illustration|engraving|lithograph|sketch|diagram|poster|postcard|stamp|cartoon|"
          r"watercolor|etching|woodcut|print of|map of|specimen|herbarium|pinned|museum|logo|coin")
ASSETS = {k: k for k in PD_QUERIES}

KEYWORDS = ["пчёл", "пчел", "пчелин", "опыл", "пыльц", "мёд", "мед", "улей", "улья", "ульи", "урожа", "миндал",
            "витамин", "пестицид", "эйнштейн", "фрукт", "овощ", "цветк", "цвет", "калифорн", "ханьюан", "ланцет"]

SECTIONS = [
    ("hook", "", "mystery"),
    ("day1", "ДЕНЬ 1", "mystery"),
    ("spring", "ПЕРВАЯ ВЕСНА", "tense"),
    ("year1", "ГОД 1", "epic"),
    ("year5", "ЧЕРЕЗ 5 ЛЕТ", "mystery"),
    ("real", "ЭТО УЖЕ ПРОИСХОДИТ", "tense"),
    ("now", "КАК ПОМОЧЬ ПЧЁЛАМ", "upbeat"),
]
S = {k: [] for k, _, _ in SECTIONS}


def add(sec, text, visual, onscreen="", **kw):
    S[sec].append({"text": text, "visual": visual, "onscreen": onscreen, **kw})


# ---------------------------------------------------------------- ХУК
add("hook", "Представь: однажды утром на Земле не осталось ни одной пчелы. Ни в ульях, ни на цветах, ни в лесу.",
    "img:bee_flower", "НИ ОДНОЙ ПЧЕЛЫ")
add("hook", "Говорят, Эйнштейн предупреждал: без пчёл человечеству останется всего четыре года.", "img:einstein",
    "«ОСТАНЕТСЯ 4 ГОДА»?")
add("hook", "Но вот сюрприз: Эйнштейн этого никогда не говорил. Эта цитата впервые появилась через десять лет после его смерти.",
    {"kind": "bigtext", "text": "ЭЙНШТЕЙН ЭТОГО НЕ ГОВОРИЛ", "sub": "цитата появилась в 1965 году, через 10 лет после его смерти"})
add("hook", "Пчёлы — это не только мёд. Это невидимые работники, без которых не было бы многих привычных продуктов.",
    "img:sunflower_bee", "НЕВИДИМЫЕ РАБОТНИКИ")
add("hook", "А реальность устроена сложнее и интереснее. В мире больше двадцати тысяч видов пчёл.",
    {"kind": "counter", "label": "ВИДОВ ПЧЁЛ В МИРЕ", "from": 0, "to": 20000, "prefix": ">", "note": "FAO"})
add("hook", "Давай проживём этот сценарий шаг за шагом: первый день, первая весна, год и пять лет без пчёл.",
    {"kind": "timeline", "title": "СЦЕНАРИЙ", "items": ["ДЕНЬ 1", "ВЕСНА", "ГОД 1", "5 ЛЕТ"]})
add("hook", "А в конце узнаем, что из этого уже происходит прямо сейчас.", "img:beekeeper", "ЭТО УЖЕ ПРОИСХОДИТ")

# ---------------------------------------------------------------- ДЕНЬ 1
add("day1", "День первый.", "card")
add("day1", "Сначала почти ничего не меняется. Магазины полны, хлеб и рис на месте.", "img:supermarket")
add("day1", "Пшеница, рис и кукуруза опыляются ветром — пчёлы им не нужны.", "img:wheat_field", "ИХ ОПЫЛЯЕТ ВЕТЕР")
add("day1", "Но пасечники по всему миру открывают ульи и видят, что они пусты.", "img:hives", "ПУСТЫЕ УЛЬИ")
add("day1", "Первыми тревогу поднимают фермеры. Опыление — это огромный бизнес: ульи возят на грузовиках от фермы к ферме и сдают в аренду.",
    "img:truck_hives", "ПЧЁЛЫ В АРЕНДУ")
add("day1", "Похожая загадка уже случалась. Зимой две тысячи шестого года пасечники в США начали находить ульи, из которых исчезли почти все рабочие пчёлы.",
    "img:bee_frame", "2006: УЛЬИ ОПУСТЕЛИ")
add("day1", "Это назвали синдромом разрушения пчелиных семей. Но тогда пчёлы исчезли не везде. А в нашем сценарии — везде и сразу.",
    {"kind": "bigtext", "text": "СИНДРОМ РАЗРУШЕНИЯ ПЧЕЛИНЫХ СЕМЕЙ", "sub": "США, 2006–2007"})
add("day1", "Мёд, который уже стоит на полках, становится последним мёдом в истории.", "img:honey_jars",
    "ПОСЛЕДНИЙ МЁД")
add("day1", "Учёные бьют тревогу. Но настоящий удар придёт не сразу, а весной, когда зацветут сады.",
    "img:blossom_orchard")

# ---------------------------------------------------------------- ПЕРВАЯ ВЕСНА
add("spring", "Первая весна.", "card")
add("spring", "Яблони и вишни покрываются цветами. Но цветы облетают, а плодов почти нет.", "img:apple_blossom",
    "ЦВЕТЫ БЕЗ ПЛОДОВ")
add("spring", "Из ста пятнадцати главных продовольственных культур мира восемьдесят семь в той или иной степени зависят от опылителей.",
    {"kind": "counter", "label": "ГЛАВНЫХ КУЛЬТУР ЗАВИСЯТ ОТ ОПЫЛИТЕЛЕЙ", "from": 0, "to": 87, "suffix": " ИЗ 115",
     "note": "Klein et al., 2007"})
add("spring", "За последние пятьдесят лет объём урожая, который зависит от опылителей, вырос в три раза. Мы зависим от пчёл всё сильнее.",
    {"kind": "counter", "label": "РОСТ УРОЖАЯ, ЗАВИСЯЩЕГО ОТ ОПЫЛИТЕЛЕЙ", "from": 0, "to": 300, "prefix": "+", "suffix": "%",
     "note": "IPBES, 2016 · за 50 лет"})
add("spring", "Особенно тяжело миндалю. Каждую весну в Калифорнию на грузовиках свозят около двух миллионов пчелиных семей — примерно две трети всех коммерческих ульев США.",
    {"kind": "factcard", "title": "МИНДАЛЬ, КАЛИФОРНИЯ", "rows": [["Пчелиных семей", "≈ 2 млн"],
                                                                 ["Доля ульев США", "≈ две трети"],
                                                                 ["Без пчёл", "урожая почти нет"]],
     "photo": "almond_orchard"})
add("spring", "Без них миндальные сады стоят в цвету, но без урожая.", "img:almond_blossom")
add("spring", "Фермеры пытаются спасти урожай: нанимают людей, чтобы опылять цветы вручную, пробуют дроны и вентиляторы. Но всё это дорого и медленно.",
    "img:drone", "СПАСАЮТ УРОЖАЙ")
add("spring", "Под ударом и многие другие продукты.",
    {"kind": "list", "title": "ПОД УДАРОМ", "color": "red",
     "items": ["Яблоки и вишня", "Миндаль", "Черника", "Огурцы и тыквы", "Дыни и арбузы"],
     "note": "сильная зависимость от опылителей"})
add("spring", "Ягоды становятся редкостью, а их цена растёт с каждой неделей.", "img:berries", "ЯГОДЫ — РЕДКОСТЬ")
add("spring", "Даже кофе станет дороже: пчёлы помогают ему давать больший урожай.", "img:coffee", "КОФЕ ДОРОЖАЕТ")
add("spring", "А вот шоколад неожиданно выживет: какао опыляют не пчёлы, а крошечные мошки.", "img:cocoa",
    "ШОКОЛАД ВЫЖИВЕТ")

# ---------------------------------------------------------------- ГОД 1
add("year1", "Год первый.", "card")
add("year1", "Через год прилавки выглядят иначе: фруктов и овощей стало меньше, а цены на них взлетели.",
    "img:market_fruit", "ЦЕНЫ ВЗЛЕТЕЛИ")
add("year1", "Учёные уже посчитали этот сценарий. По расчётам, опубликованным в журнале Ланцет, при полном исчезновении опылителей фруктов в мире станет меньше почти на двадцать три процента, орехов и семян — на двадцать два, а овощей — на шестнадцать.",
    {"kind": "bars", "title": "НА СКОЛЬКО МЕНЬШЕ ЕДЫ", "unit": "%",
     "bars": [["Фрукты", 22.9], ["Орехи и семена", 22.1], ["Овощи", 16.3]], "note": "The Lancet, Smith et al., 2015"})
add("year1", "Мёд тоже исчезнет, но это самая маленькая потеря. Пчёлы дают нам гораздо больше, чем мёд.",
    "img:honey_comb_close", "БОЛЬШЕ, ЧЕМ МЁД")
add("year1", "И дело не только в салатах. Фрукты и овощи — главный источник витаминов.", "img:vegetables", "ВИТАМИНЫ")
add("year1", "Те же учёные подсчитали: из-за такого питания каждый год могли бы умирать почти на полтора миллиона человек больше — от болезней сердца, инсультов и нехватки витаминов.",
    {"kind": "counter", "label": "ЛИШНИХ СМЕРТЕЙ В ГОД", "from": 0, "to": 1420000,
     "note": "The Lancet, 2015 · модельный расчёт"})
add("year1", "А ещё семьдесят один миллион человек в бедных странах рискуют столкнуться с нехваткой витамина А.",
    {"kind": "counter", "label": "РИСК НЕХВАТКИ ВИТАМИНА А", "from": 0, "to": 71000000, "note": "The Lancet, 2015"})
add("year1", "Пострадают даже мясо и молоко: люцерну, которой кормят коров, тоже опыляют пчёлы.", "img:cows",
    "КОРМ ДЛЯ КОРОВ")
add("year1", "Хуже всего придётся бедным странам: свежие фрукты и овощи там станут почти никому не по карману.",
    "img:village_market", "НЕ ПО КАРМАНУ")
add("year1", "Рестораны меняют меню, а блюда с ягодами и орехами становятся деликатесом.", "img:restaurant",
    "ДЕЛИКАТЕСЫ")
add("year1", "Сельское хозяйство придётся перестраивать по всему миру: меньше садов и огородов, больше полей с зерном.",
    "img:farm_field", "МЕНЬШЕ САДОВ")
add("year1", "Есть и цена в деньгах. Урожай, который напрямую зависит от опылителей, стоит от двухсот тридцати пяти до пятисот семидесяти семи миллиардов долларов в год.",
    {"kind": "counter", "label": "УРОЖАЙ ОТ ОПЫЛИТЕЛЕЙ В ГОД", "from": 0, "to": 577, "prefix": "$", "suffix": " МЛРД",
     "note": "IPBES, 2016: $235–577 млрд"})

# ---------------------------------------------------------------- ЧЕРЕЗ 5 ЛЕТ
add("year5", "Через пять лет.", "card")
add("year5", "Люди не вымрут за четыре года, как обещала фальшивая цитата. У нас останутся хлеб, рис и кукуруза.",
    "img:bread_rice", "ГОЛОДА НЕ БУДЕТ")
add("year5", "Но питание станет беднее и однообразнее, а свежие фрукты превратятся в роскошь.", "img:apple_single",
    "ФРУКТЫ — РОСКОШЬ")
add("year5", "Многие сады вырубят: держать деревья без урожая бессмысленно. На их месте посадят то, что опыляет ветер.",
    "img:stumps", "САДЫ ВЫРУБАЮТ")
add("year5", "Учёные попробуют заменить пчёл роботами. Крошечные дроны-опылители уже существуют, но заменить миллиарды пчёл им пока не под силу.",
    {"kind": "bigtext", "text": "РОБОТЫ ВМЕСТО ПЧЁЛ?", "sub": "прототипы есть, но до миллиардов пчёл им далеко"})
add("year5", "Сильнее всего пострадает природа: почти девяносто процентов цветковых растений зависят от опылителей, а пчёлы — главные из них.",
    {"kind": "counter", "label": "ЦВЕТКОВЫХ РАСТЕНИЙ ЗАВИСЯТ ОТ ОПЫЛИТЕЛЕЙ", "from": 0, "to": 90, "prefix": "≈",
     "suffix": "%", "note": "FAO"})
add("year5", "Часть диких растений перестанет давать семена, а вслед за ними исчезнут птицы и звери, которые ими питаются.",
    "img:meadow", "ЦЕПНАЯ РЕАКЦИЯ")
add("year5", "Остальные опылители — бабочки, мухи, птицы и летучие мыши — справятся лишь с частью этой работы.",
    "img:butterfly")
add("year5", "Мир станет тише и беднее красками: меньше цветов на лугах, меньше бабочек и птиц.", "img:quiet_field",
    "МИР СТАНЕТ ТИШЕ")
add("year5", "И тогда людям придётся делать работу пчёл своими руками.", "img:hand_brush", "ЛЮДИ ВМЕСТО ПЧЁЛ")

# ---------------------------------------------------------------- ЭТО УЖЕ ПРОИСХОДИТ
add("real", "Это уже происходит.", "card")
add("real", "В китайском уезде Ханьюань, в провинции Сычуань, грушевые сады опыляют вручную.",
    {"kind": "factcard", "title": "ХАНЬЮАНЬ, КИТАЙ", "rows": [["Что", "грушевые сады"], ["Как", "опыление вручную"],
                                                             ["Почему", "пестициды убили пчёл"]],
     "photo": "pear_blossom"})
add("real", "Пчёл там почти не осталось из-за пестицидов, и люди переносят пыльцу пучками перьев на длинных бамбуковых шестах.",
    "img:orchard_worker", "ПЕРЬЯ ВМЕСТО ПЧЁЛ")
add("real", "Человек за день успевает опылить около тридцати деревьев, а одна пчелиная семья — миллионы цветков.",
    {"kind": "split", "left": "30 ДЕРЕВЬЕВ", "right": "МИЛЛИОНЫ", "left_sub": "человек за день",
     "right_sub": "цветков у пчёл за день", "left_photo": "pesticide", "right_photo": "sunflower"})
add("real", "А в США с июня две тысячи двадцать четвёртого по февраль двадцать пятого коммерческие пасечники потеряли в среднем шестьдесят два процента пчелиных семей. Это рекорд за всю историю наблюдений.",
    {"kind": "counter", "label": "СЕМЕЙ ПОТЕРЯЛИ ПАСЕЧНИКИ США", "from": 0, "to": 62, "suffix": "%",
     "note": "Project Apis m., 2024–2025"})
add("real", "Пчёл убивают сразу несколько причин.",
    {"kind": "list", "title": "ЧТО УБИВАЕТ ПЧЁЛ", "color": "red",
     "items": ["Клещи и вирусы", "Пестициды", "Исчезновение цветущих лугов", "Жара и засухи"], "note": "IPBES, 2016"})
add("real", "По оценке учёных, под угрозой исчезновения больше сорока процентов видов беспозвоночных опылителей — прежде всего пчёл и бабочек.",
    "img:empty_hive", "БОЛЕЕ 40% ВИДОВ ПОД УГРОЗОЙ")

# ---------------------------------------------------------------- КАК ПОМОЧЬ
add("now", "Как помочь пчёлам.", "card")
add("now", "Хорошая новость: пчёл можно спасти, и помочь может каждый.",
    {"kind": "bigtext", "text": "ПЧЁЛ МОЖНО СПАСТИ", "sub": "и помочь может каждый"})
add("now", "Вот пять простых шагов.",
    {"kind": "list", "title": "КАК ПОМОЧЬ ПЧЁЛАМ", "color": "green",
     "items": ["Сажай цветы для опылителей", "Не трави сад лишней химией", "Оставь уголок дикой травы",
               "Покупай мёд у местных пасечников", "Поставь домик для диких пчёл"]})
add("now", "Первое: посади на балконе или во дворе цветы — лаванду, мяту или подсолнухи.", "img:lavender",
    "1 · ЦВЕТЫ ДЛЯ ПЧЁЛ")
add("now", "Второе: не трави сад лишними пестицидами.", "img:garden", "2 · БЕЗ ЛИШНЕЙ ХИМИИ")
add("now", "Третье: оставь уголок некошеной травы — это столовая для диких пчёл.", "img:tall_grass",
    "3 · ДИКИЙ УГОЛОК")
add("now", "Четвёртое: покупай мёд у местных пасечников, так ты поддерживаешь пчёл рядом с домом.", "img:local_honey",
    "4 · МЕСТНЫЙ МЁД")
add("now", "И пятое: поставь домик для диких пчёл — им нужны укрытия.", "img:bee_hotel", "5 · ДОМИК ДЛЯ ПЧЁЛ")
add("now", "Даже один горшок с цветами на балконе — это остановка для пчелы посреди города.", "img:balcony_flowers",
    "ОСТАНОВКА ДЛЯ ПЧЕЛЫ")
add("now", "Мир без пчёл не погибнет за четыре года. Но станет беднее, скучнее и голоднее. И это зависит от нас.",
    {"kind": "bigtext", "text": "МИР БЕЗ ПЧЁЛ — БЕДНЕЕ", "sub": "и это зависит от нас"})
add("now", "Если было интересно, подпишись на канал и напиши в комментариях: какой фрукт тебе было бы жальче всего потерять?",
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
             "split": "Экран делится на две половины", "endcard": "Конечная заставка с кнопкой подписки"}
    rows = [f"# Раскадровка: «{TITLE}»", "", "| № | Строка озвучки | Что на экране | Надпись на экране |", "|---|---|---|---|"]
    for s in shots:
        v = s["visual"]
        if v == "card":
            what, label = f"Заставка раздела «{s['section_title']}» (неон, глитч)", s["section_title"]
        elif isinstance(v, str):
            what, label = f"Фото: {v[4:]} (Ken Burns)", s["onscreen"]
        else:
            what = kinds.get(v["kind"], v["kind"])
            label = v.get("title") or v.get("text") or v.get("label") or s["onscreen"]
        rows.append(f"| {s['id']} | {s['text']} | {what} | {label} |")
    (ROOT / "storyboard.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    words = sum(len(s["text"].split()) for s in shots)
    print(f"{len(shots)} кадров, {words} слов, {sum(len(s['text']) for s in shots)} символов")
    used = [s["visual"][4:] for s in shots if isinstance(s["visual"], str) and s["visual"].startswith("img:")]
    for s in shots:
        v = s["visual"]
        if isinstance(v, dict):
            used += [v[k] for k in ("photo", "left_photo", "right_photo") if v.get(k)]
    dup = {k for k in used if used.count(k) > 1}
    print("фото-кадров:", len(used), "| повторы ключей:", dup or "нет")


if __name__ == "__main__":
    build()
