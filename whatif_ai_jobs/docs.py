"""Этап 6 — документы: sources.md, youtube.md (названия, описание с таймкодами, теги), thumbnail.png.

python docs.py            всё сразу
python docs.py --thumb    только превью
"""

import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
FONT_DIR = Path("/usr/share/fonts/opentype/inter")

TITLES = [
    "Что если ИИ заменит ВСЕХ людей на работе?",
    "Мир без работы: что будет, если ИИ заберёт все профессии",
    "ИИ уволил человечество: от первого дня до 20 лет спустя",
]

TAGS = ["что если", "искусственный интеллект", "ИИ", "нейросети", "будущее работы", "безработица",
        "базовый доход", "безусловный базовый доход", "профессии будущего", "автоматизация", "роботы",
        "экономика будущего", "навыки будущего", "ИИ заменит людей", "что будет если"]

HASHTAGS = "#ЧтоЕсли #ИИ #БудущееРаботы"

CHAPTER_NAMES = {
    "hook": "Твоя работа уже сделана",
    "day1": "День 1: кто исчезает первым",
    "month1": "Месяц 1: зарплаты, налоги и парадокс",
    "year1": "Год 1: базовый доход — Финляндия, Кения, США",
    "year5": "Через 5 лет: луддиты, Форд и банкоматы",
    "year20": "Через 20 лет: реальные прогнозы и поиск смысла",
    "newworld": "Новый мир: утопия или антиутопия",
    "now": "Что делать уже сейчас",
}

FACTS = [
    ("Goldman Sachs: генеративный ИИ затрагивает ~300 млн рабочих мест; базовый сценарий — 6–7% работников "
     "потеряют работу за ~10 лет внедрения",
     ["https://www.goldmansachs.com/insights/articles/how-will-ai-affect-the-us-labor-market",
      "https://www.forbes.com/sites/jackkelly/2023/03/31/goldman-sachs-predicts-300-million-jobs-will-be-lost-or-degraded-by-artificial-intelligence/"]),
    ("McKinsey Global Institute, «Agents, robots, and us» (ноябрь 2025): ~57% рабочих часов в США технически "
     "автоматизируемы; дольше держится непредсказуемый физический труд и уход за людьми",
     ["https://www.mckinsey.com/~/media/mckinsey/mckinsey%20global%20institute/our%20research/agents%20robots%20and%20us%20skill%20partnerships%20in%20the%20age%20of%20ai/agents-robots-and-us-skill-partnerships-in-the-age-of-ai.pdf"]),
    ("WEF Future of Jobs Report 2025: до 2030 года появится 170 млн рабочих мест, исчезнет 92 млн (итог +78 млн); "
     "39% ключевых навыков изменятся; быстрее всего растёт спрос на ИИ и большие данные, аналитическое мышление",
     ["https://www.weforum.org/press/2025/01/future-of-jobs-report-2025-78-million-new-job-opportunities-by-2030-but-urgent-upskilling-needed-to-prepare-workforces/",
      "https://www.weforum.org/publications/the-future-of-jobs-report-2025/"]),
    ("Microsoft Research (июль 2025): профессии, наиболее и наименее затронутые генеративным ИИ",
     ["https://fortune.com/2025/07/31/microsoft-research-generative-ai-occupational-impact-jobs-most-and-least-likely-to-impact-teaching-office-jobs-college-gen-z-grads/"]),
    ("Финляндия, 2017–2018: 2 000 безработных получали 560 € в месяц; эффект на занятость небольшой, "
     "самочувствие и уверенность лучше",
     ["https://stm.fi/en/-/perustulokokeilun-tulokset-tyollisyysvaikutukset-vahaisia-toimeentulo-ja-psyykkinen-terveys-koettiin-paremmaksi",
      "https://www.helsinki.fi/en/news/fair-society/basic-income-experiment-finland-yields-surprising-results"]),
    ("Кения, GiveDirectly: базовый доход ≈ $22,5 в месяц, в одной из групп — на 12 лет; рост бизнеса и сбережений",
     ["https://www.npr.org/sections/goatsandsoda/2023/12/07/1217478771/its-one-of-the-biggest-experiments-in-fighting-global-poverty-now-the-results-ar",
      "https://www.givedirectly.org/ubi/"]),
    ("Стоктон (SEED), США: 125 человек по $500 в месяц; полная занятость выросла с 28% до 40% (контроль: 32% → 37%)",
     ["https://www.cbsnews.com/news/basic-guaranteed-income-stockton-experiment",
      "https://sp2.upenn.edu/guaranteed-income-increases-employment-improves-financial-and-physical-health/"]),
    ("OpenResearch: 1 000 человек по $1 000 в месяц на протяжении 3 лет; работали в среднем на ~1,3 часа в неделю меньше",
     ["https://www.route-fifty.com/management/2024/07/results-biggest-study-guaranteed-income-programs-are-finally/398260/",
      "https://www.cbsnews.com/news/sam-altman-universal-basic-income-study-open-research"]),
    ("Доходы федерального бюджета США, 2024 ф. г.: подоходный налог ~49%, налоги на зарплаты ~35%",
     ["https://www.cbo.gov/system/files/2025-03/61185-Revenues.pdf",
      "https://www.crfb.org/papers/explaining-federal-spending-and-revenue"]),
    ("Луддиты: Арнольд, Ноттингемшир, 11 марта 1811 года; закон 1812 года сделал поломку станков преступлением, "
     "караемым смертью",
     ["https://en.wikipedia.org/wiki/Luddite", "https://www.worldhistory.org/Luddite/"]),
    ("Конвейер Форда (1913): сборка автомобиля сократилась с более чем 12 часов до ~1,5 часа; $5 в день (1914)",
     ["https://www.history.com/this-day-in-history/December-1/fords-assembly-line-starts-rolling"]),
    ("Доля занятых в сельском хозяйстве США: 41% (1900), 21,5% (1930), 4% (1970), 1,9% (2000) — USDA ERS",
     ["https://ers.usda.gov/sites/default/files/_laserfiche/publications/44197/13566_eib3_1_.pdf"]),
    ("Банкоматы и кассиры: число кассиров в США выросло примерно с 500 тыс. до 600 тыс. (Джеймс Бессен)",
     ["https://0-www-imf-org.library.svsu.edu/external/pubs/ft/fandd/2015/03/pdf/bessen.pdf",
      "https://www.ccianet.org/articles/what-bank-tellers-and-radiologists-can-tell-us-about-our-job-security-in-the-ai-era/"]),
    ("Джон Мейнард Кейнс, «Экономические возможности наших внуков» (1930): прогноз 15-часовой рабочей недели",
     ["https://en.wikipedia.org/wiki/Economic_Possibilities_for_our_Grandchildren"]),
]


def F(weight, size):
    return ImageFont.truetype(str(FONT_DIR / f"Inter-{weight}.otf"), size)


def ts(t):
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"


def chapters():
    data = json.loads((BUILD / "shots.json").read_text(encoding="utf-8"))
    timing = json.loads((BUILD / "timing.json").read_text(encoding="utf-8"))
    out = []
    for i, s in enumerate(data["shots"]):
        if i == 0 or s["section"] != data["shots"][i - 1]["section"]:
            t = 0 if i == 0 else timing["lines"][i]["shot_start"]
            out.append((t, CHAPTER_NAMES[s["section"]]))
    return out, timing["duration"]


def image_credits():
    meta = json.loads((BUILD / "images.json").read_text(encoding="utf-8")) if (BUILD / "images.json").exists() else {}
    used = json.loads((BUILD / "used_images.json").read_text(encoding="utf-8")) if (BUILD / "used_images.json").exists() else None
    rows = []
    for key, cands in meta.items():
        for i, c in enumerate(cands):
            if used is not None and f"{key}_{i}.jpg" not in used:
                continue
            rows.append((key, c))
    return rows


def sources_md():
    ch, dur = chapters()
    lines = ["# Источники — «Что если бы ИИ заменил всех людей на работе?»", "",
             f"Длительность видео: {ts(dur)}. Все факты в сценарии проверены по источникам ниже.", "",
             "## Факты и цифры", ""]
    for i, (fact, urls) in enumerate(FACTS, 1):
        lines.append(f"{i}. {fact}")
        for u in urls:
            lines.append(f"   - {u}")
    lines += ["", "Сценарные элементы (обвал биржевого индекса, «утопия/антиутопия», сроки «день/месяц/год») — "
              "мысленный эксперимент; на экране помечены как иллюстрация сценария.", "",
              "## Изображения", "",
              "Все фото — Wikimedia Commons, только лицензии, разрешающие коммерческое использование без "
              "«копилефта»: Public domain, CC0, CC BY. Фото обработаны (цветокоррекция, кадрирование, движение камеры). "
              "Инфографика, заставки, графики и превью нарисованы кодом (Python/Pillow) специально для ролика.", "",
              "| Ключ | Файл | Автор | Лицензия | Ссылка |", "|---|---|---|---|---|"]
    for key, c in image_credits():
        author = re.sub(r"\s+", " ", c["author"]).replace("|", "/")[:80]
        title = c["title"].replace("File:", "").replace("|", "/")
        lic = c["license"] + (f" ({c['license_url']})" if c.get("license_url") else "")
        lines.append(f"| {key} | {title} | {author} | {lic} | {c['page']} |")
    lines += ["", "## Музыка и звук", "",
              "Оригинальная процедурная электронная/эмбиент-музыка, сгенерированная кодом для этого ролика "
              "(модуль `ai_shorts_ru/shorts_ru/audio.py`): своя тема на каждую главу. Сторонних треков нет — "
              "авторских прав третьих лиц не затрагивает.", "",
              "## Голос", "",
              "Озвучка: офлайн-синтез Vosk TTS 0.9 (модель vosk-model-tts-ru-0.9-multi, голос male_1, лицензия "
              "Apache 2.0), обработка (эквалайзер, компрессия), нормализация до −16 LUFS. ElevenLabs не "
              "использовался: на бесплатном тарифе оставалось 244 символа из ~8 000 нужных.", "",
              "## Шрифт", "", "Inter (SIL Open Font License 1.1).", ""]
    (ROOT / "sources.md").write_text("\n".join(lines), encoding="utf-8")


def youtube_md():
    ch, dur = chapters()
    stamps = "\n".join(f"{ts(t)} {name}" for t, name in ch)
    desc = f"""Что будет, если завтра искусственный интеллект заменит всех людей на работе? Проживём этот сценарий шаг за шагом: первый день, первый месяц, год, пять и двадцать лет — и посмотрим, каким станет новый мир.

В ролике: какие профессии исчезнут первыми, а какие продержатся дольше всех; что станет с зарплатами, налогами и экономикой; что показали реальные эксперименты с базовым доходом в Финляндии, Кении и США; чему нас учат луддиты, конвейер Форда и банкоматы; что прогнозируют Goldman Sachs, McKinsey и Всемирный экономический форум — и где люди будут искать смысл, если работа исчезнет.

А в конце — пять навыков, которые стоит развивать уже сейчас, чтобы ИИ работал на тебя, а не вместо тебя. Пиши в комментариях, какой мир ждёт нас, по-твоему: утопия или антиутопия?

Таймкоды:
{stamps}

Источники:
Goldman Sachs (2023) · McKinsey Global Institute «Agents, robots, and us» (2025) · WEF Future of Jobs Report 2025 · Microsoft Research (2025) · Kela/STM (Финляндия) · GiveDirectly (Кения) · SEED (Стоктон) · OpenResearch · CBO · USDA ERS · J. Bessen. Полный список ссылок — в закреплённом комментарии.

Фото: Wikimedia Commons (Public domain / CC0 / CC BY, авторы указаны в закреплённом комментарии). Музыка: оригинальная. Голос: синтез речи.

{HASHTAGS}"""
    credits = ["Фото (Wikimedia Commons):"]
    for key, c in image_credits():
        author = re.sub(r"\s+", " ", c["author"])[:60]
        credits.append(f"• {author} — {c['license']} — {c['page']}")
    pinned = ("Источники цифр:\n" + "\n".join(f"• {u[0]}" for _, u in FACTS) + "\n\n" + "\n".join(credits))
    md = ["# YouTube — пакет публикации", "", "## Варианты названия (≤ 60 символов)", ""]
    for t in TITLES:
        md.append(f"- {t}  ({len(t)} симв.)")
    md += ["", "## Описание", "", "```", desc, "```", "", f"Длина описания: {len(desc)} символов (лимит 5000).", "",
           "## Теги (15)", "", ", ".join(TAGS), "", f"Длина тегов: {len(','.join(TAGS))} символов (лимит 500).", "",
           "## Закреплённый комментарий (источники и авторы фото)", "", "```", pinned, "```", "",
           f"Длина: {len(pinned)} символов (лимит комментария 10 000).", "",
           "## Конечная заставка", "", f"Последние ~16 с ({ts(dur - 16)}–{ts(dur)}): слева рамка «Смотри дальше», "
           "справа «Лучшее на канале», по центру кнопка подписки — поставьте туда элементы YouTube.", "",
           "## Файлы", "", "- final_video.mp4 — видео 1920×1080, 30 fps, H.264 + AAC",
           "- thumbnail.png — превью 1280×720", "- subtitles.srt — русские субтитры (загрузить как «Русский»)",
           "- script_voiceover.txt, storyboard.md — сценарий и раскадровка", "- sources.md — источники и лицензии", ""]
    assert all(len(t) <= 60 for t in TITLES) and len(TAGS) == 15 and len(desc) <= 5000
    (ROOT / "youtube.md").write_text("\n".join(md), encoding="utf-8")
    (ROOT / "youtube_description.txt").write_text(desc, encoding="utf-8")
    print("titles:", [len(t) for t in TITLES], "desc:", len(desc), "pinned:", len(pinned))


def thumbnail(robot_path=None):
    """1280x720: робот справа, огромное «ТЫ УВОЛЕН» слева, высокий контраст."""
    import numpy as np
    TW, TH = 1280, 720
    bg = Image.new("RGB", (TW, TH), (8, 6, 22))
    # фон: тёмный градиент + неоновые пятна
    y = np.linspace(0, 1, TH)[:, None, None]
    x = np.linspace(0, 1, TW)[None, :, None]
    arr = np.array((10, 8, 30)) * (1 - y) + np.array((28, 6, 40)) * y
    arr = arr + np.exp(-(((x - 0.85) * 1.8) ** 2 + ((y - 0.4) * 1.6) ** 2)) * np.array((40, 120, 255)) * 0.55
    arr = arr + np.exp(-(((x - 0.1) * 2.0) ** 2 + ((y - 0.9) * 1.8) ** 2)) * np.array((255, 40, 80)) * 0.35
    bg = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if robot_path and Path(robot_path).exists():
        rb = Image.open(robot_path).convert("RGB")
        rh = TH
        rw = int(rb.width * rh / rb.height)
        if rw < 760:
            rw = 760
            rh = int(rb.height * rw / rb.width)
        rb = rb.resize((rw, rh), Image.LANCZOS)
        crop_x = max(0, (rw - 760) // 2)
        rb = rb.crop((crop_x, max(0, (rh - TH) // 3), crop_x + 760, max(0, (rh - TH) // 3) + TH))
        a = np.asarray(rb, np.float32) / 255
        lum = a @ np.array([0.299, 0.587, 0.114])
        a = np.clip((a - 0.5) * 1.35 + 0.5, 0, 1)          # контраст
        a = a * 0.75 + lum[..., None] * 0.25
        a = a * np.array((0.85, 0.95, 1.15))                  # холодный тон
        rb = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
        mask = Image.new("L", (760, TH), 255)
        md = np.tile(np.clip(np.linspace(-0.3, 1.4, 760), 0, 1)[None, :], (TH, 1))
        mask = Image.fromarray((md * 255).astype(np.uint8))
        bg.paste(rb, (TW - 760, 0), mask)
    d = ImageDraw.Draw(bg, "RGBA")
    # верхняя плашка
    f_top = F("Black", 44)
    top = "ЧТО ЕСЛИ ИИ ЗАМЕНИТ ВСЕХ?"
    tw = d.textlength(top, font=f_top)
    d.rounded_rectangle((48, 44, 48 + tw + 44, 44 + 72), 12, fill=(255, 214, 40))
    d.text((48 + 22, 44 + 36), top, font=f_top, fill=(10, 8, 20), anchor="lm")
    # «ТЫ УВОЛЕН» со свечением
    glow = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    f1, f2 = F("Black", 184), F("Black", 172)
    g.text((44, 300), "ТЫ", font=f1, fill=(255, 255, 255, 255), anchor="lm")
    g.text((40, 500), "УВОЛЕН", font=f2, fill=(255, 40, 70, 255), anchor="lm")
    blur = glow.filter(ImageFilter.GaussianBlur(18))
    bg = Image.alpha_composite(bg.convert("RGBA"), blur)
    bg = Image.alpha_composite(bg, blur)
    d = ImageDraw.Draw(bg)
    d.text((44, 300), "ТЫ", font=f1, fill=(255, 255, 255), anchor="lm", stroke_width=8, stroke_fill=(5, 5, 15))
    d.text((40, 500), "УВОЛЕН", font=f2, fill=(255, 45, 75), anchor="lm", stroke_width=8, stroke_fill=(5, 5, 15))
    # нижняя подпись
    d.text((48, 652), "через 1 день · 1 год · 20 лет", font=F("Bold", 40), fill=(120, 225, 255), anchor="lm",
           stroke_width=4, stroke_fill=(5, 5, 15))
    bg.convert("RGB").save(ROOT / "thumbnail.png")
    print("thumbnail.png", bg.size)


if __name__ == "__main__":
    if "--thumb" in sys.argv:
        thumbnail(sys.argv[sys.argv.index("--thumb") + 1] if len(sys.argv) > sys.argv.index("--thumb") + 1 else None)
    else:
        sources_md()
        youtube_md()
