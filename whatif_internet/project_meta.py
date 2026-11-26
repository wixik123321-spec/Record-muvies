# Тексты публикации для «Что если интернет отключится по всему миру?» (читается docs.py)

VIDEO_TITLE = "Что если интернет отключится по всему миру?"

TITLES = [
    "Что если интернет отключится по всему миру?",
    "Мир без интернета: что будет через час, день и год",
    "Интернет исчез навсегда. Что будет с нами?",
]

TAGS = ["что если", "интернет", "без интернета", "отключение интернета", "мир без интернета", "подводные кабели",
        "солнечная буря", "событие Кэррингтона", "CrowdStrike", "сбой интернета", "кибератака", "технологии",
        "что будет если", "научпоп", "интересные факты"]

HASHTAGS = "#ЧтоЕсли #Интернет #БезИнтернета"

CHAPTER_NAMES = {
    "hook": "Интернет исчез",
    "minutes": "Первые минуты: сбой как у Facebook",
    "day1": "День 1: карты, банкоматы, самолёты",
    "week1": "Неделя 1: пустые полки и бумага",
    "month1": "Месяц 1: обвал экономики",
    "real": "Это реально? Кабели, лопата и Солнце",
    "year1": "Год спустя: каким станет мир",
    "now": "Что делать уже сейчас",
}

DESC_INTRO = (
    "Что будет, если завтра интернет исчезнет — везде и сразу? Проживём этот сценарий шаг за шагом: первые минуты, "
    "первый день, неделя, месяц и год без сети.\n\n"
    "В ролике: почему первыми перестанут работать карты и банкоматы; что произошло, когда Facebook пропал на шесть "
    "часов, а одно обновление CrowdStrike отменило тысячи рейсов; как вирус NotPetya заставил гиганта Maersk работать "
    "на бумаге; почему интернет на самом деле лежит на дне океана, как пенсионерка с лопатой оставила без сети почти "
    "целую страну и чем опасны солнечные бури вроде события Кэррингтона.\n\n"
    "А в конце — пять простых шагов, которые стоит сделать уже сегодня, чтобы день без интернета не застал тебя "
    "врасплох. Пиши в комментариях: что ты сделаешь первым делом, если интернет исчезнет?")

SOURCES_LINE = ("ITU Facts and Figures 2025 · DataReportal Digital 2025 · TeleGeography · Access Now #KeepItOn 2024 · "
                "Hydro-Québec · NASA · Lloyd's · разборы сбоев Facebook (2021), CrowdStrike (2024) и NotPetya/Maersk "
                "(2017). Полный список ссылок — в закреплённом комментарии.")

PHOTO_LINE = "Фото: открытый набор PD12M (Public Domain / CC0). Музыка: оригинальная. Голос: синтез речи."

PHOTO_SECTION = ("Все фото — реальные снимки из открытого набора PD12M (Spawning / Source.Plus, лицензия набора "
                 "CDLA-Permissive-2.0): только Public Domain и CC0, в основном из Wikimedia Commons. Коммерческое "
                 "использование разрешено, указание авторства не требуется — источники всё равно перечислены. "
                 "Каждое фото используется в ролике один раз.")

SCENARIO_NOTE = ("Сценарные элементы (обвал мировой торговли, остановка бирж, ход событий «минуты / день / неделя / "
                 "месяц / год») — мысленный эксперимент; на экране помечены как иллюстрация сценария.")

VOICE_NOTE = ("Озвучка: офлайн-синтез Vosk TTS 0.9 (модель vosk-model-tts-ru-0.9-multi, голос male_1, лицензия "
              "Apache 2.0), обработка (эквалайзер, компрессия), нормализация до −16 LUFS.")

THUMB = {"top": "ЧТО ЕСЛИ ИНТЕРНЕТ ИСЧЕЗНЕТ?", "line1": ("НЕТ", 200, (255, 255, 255)),
         "line2": ("СЕТИ", 210, (255, 45, 75)), "bottom": "1 минута · 1 день · 1 год без интернета", "icon": "nowifi"}

FACTS = [
    ("ITU Facts and Figures 2025: в интернете около 6 млрд человек (≈ три четверти населения Земли), 2,2 млрд — офлайн",
     ["https://www.itu.int/en/mediacentre/Pages/PR-2025-11-17-facts-and-figures.aspx", "https://www.itu.int/ff2025"]),
    ("DataReportal Digital 2025: пользователь интернета проводит онлайн в среднем 6 ч 38 мин в день",
     ["https://datareportal.com/reports/digital-2025-sub-section-ever-more-connected"]),
    ("Сбой Facebook, Instagram и WhatsApp 4 октября 2021 года: около 6 часов, ошибка конфигурации сети (BGP); "
     "у сотрудников перестали работать электронные пропуска",
     ["https://www.thousandeyes.com/blog/facebook-outage-analysis",
      "https://www.snopes.com/news/2021/10/05/cause-facebook-outage-2021/",
      "https://computerweekly.com/news/252507717/Facebook-unplugged-for-six-hours-due-to-configuration-error"]),
    ("CrowdStrike, 19 июля 2024 года: ошибочное обновление вывело из строя ≈ 8,5 млн устройств на Windows; "
     "за день отменено 5 078 рейсов (≈ 4,6% от запланированных)",
     ["https://fortune.com/2024/07/20/crowdstrike-global-outage-less-than-1-percent-all-microsoft-windows-devices",
      "https://www.wikiwand.com/en/articles/CrowdStrike_incident",
      "https://techtarget.com/whatis/feature/Explaining-the-largest-IT-outage-in-history-and-whats-next"]),
    ("NotPetya и Maersk, 2017: переустановлены 45 000 ПК и 4 000 серверов примерно за 10 дней, компания работала "
     "в основном вручную; ущерб $250–300 млн",
     ["https://securityaffairs.com/68227/security/maersk-notpetya-attack.html",
      "https://www.supplychaindive.com/news/maersk-reconstructed-entire-it-infrastructure-in-10-days-following-nyetya/515776/",
      "https://www.theregister.com/2018/01/25/after_notpetya_maersk_replaced_everything"]),
    ("Подводные кабели передают более 99% межконтинентальных данных; их длина — почти 1,4 млн км; глубоководные "
     "кабели толщиной примерно с садовый шланг, повреждаются в основном якорями и рыболовными снастями",
     ["https://blog.telegeography.com/2023-mythbusting-part-3",
      "https://www2.telegeography.com/submarine-cable-faqs-frequently-asked-questions"]),
    ("Грузия/Армения, 28 марта 2011 года: 75-летняя жительница Грузии, искавшая металлолом, повредила оптический "
     "кабель; Армения, получавшая через Грузию ≈ 90% интернета, осталась без сети до 12 часов («хакер с лопатой»)",
     ["https://www.npr.org/2011/04/07/135201463/little-old-lady-with-shovel-disrupts-internet-in-2-nations",
      "https://spectrum.ieee.org/georgian-woman-accidentally-brings-down-armenias-internet",
      "https://www.themoscowtimes.com/2011/04/10/75-year-old-shut-off-internet-a6202"]),
    ("Событие Кэррингтона, 1859: отказы телеграфа по всему миру, искры и удары током у операторов, работа линий "
     "с отключёнными батареями; полярные сияния далеко к югу",
     ["https://en.wikipedia.org/wiki/Carrington_Event"]),
    ("Квебек, 13 марта 1989 года: геомагнитная буря обрушила энергосистему меньше чем за 90 секунд, провинция "
     "осталась без света больше чем на 9 часов",
     ["https://hydroquebec.com/learning/notions-de-base/tempete-mars-1989.html",
      "https://en.wikipedia.org/wiki/March_1989_geomagnetic_storm"]),
    ("Июль 2012 года: выброс солнечной плазмы силы Кэррингтона прошёл мимо Земли; по оценке NASA, извергнись он "
     "на неделю раньше — удар пришёлся бы по Земле",
     ["https://science.nasa.gov/science-news/science-at-nasa/2014/23jul_superstorm/",
      "https://en.wikipedia.org/wiki/Carrington_Event"]),
    ("Lloyd's и AER (2013): ущерб от бури уровня Кэррингтона только для США — $0,6–2,6 трлн",
     ["https://en.wikipedia.org/wiki/Carrington_Event"]),
    ("Access Now #KeepItOn: в 2024 году зафиксировано 296 отключений интернета в 54 странах",
     ["https://www.accessnow.org/internet-shutdowns-2024/",
      "https://www.accessnow.org/press-release/keepiton-internet-shutdowns-2024-en/"]),
]
