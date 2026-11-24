"""Сценарий: Claude пишет историю по теме, либо свой текст разбивается на сцены.

Режим Claude требует ключ ANTHROPIC_API_KEY (console.anthropic.com → API Keys)
или вход через `ant auth login`. Режим «свой текст» работает без ключей:
визуальные решения подбираются по словам каждого предложения.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .models import CAMERAS, EMOTIONS, MOODS, POSES, PROPS, SETTINGS, SFX, TRANSITIONS, Scene, Script
from .utils import log, ShortsError

SYSTEM = """Ты — сценарист вирусных YouTube Shorts на русском языке. Пишешь короткие истории:
интересные факты, психология, загадки, истории, мотивация, необычные события.

Правила текста:
- Только русский язык, разговорный, живой, без канцелярита. Без эмодзи и хэштегов в тексте.
- Первая фраза — сильный хук: вопрос, шокирующий факт или интрига, которая не даёт пролистать.
- Каждое предложение — отдельная сцена, 5–14 слов, чтобы картинка менялась каждые 2–4 секунды.
- История развивается, напряжение растёт, финал — неожиданный поворот или ответ на хук.
- Числа пиши словами, как их произносят («три сердца», «в тысяча девятьсот двенадцатом году»),
  чтобы озвучка читала их правильно. Не используй сокращения и латиницу.
- Только проверенные факты. Если тема — вымышленная история, не выдавай её за правду.

Для каждой сцены выбери визуал из списков: место (setting), эмоцию и позу персонажа
(или null, если персонаж не нужен — например, крупный план объекта), до трёх предметов (props),
крупную надпись big_text (число или 1–2 слова, необязательно), движение камеры, переход и звук.
keywords — 1–2 слова из текста сцены (точно как в тексте), которые стоит подсветить в субтитрах.
image_prompt — короткое описание кадра на английском (для генератора картинок).
ending: "cut", если последняя фраза специально обрывается на полуслове, чтобы ролик
зациклился (приём для удержания), иначе "normal".
"""


def _lit(values):
    return Literal[tuple(values)]  # type: ignore[valid-type]


class SceneOut(BaseModel):
    text: str
    setting: _lit(SETTINGS)
    character_emotion: Optional[_lit(EMOTIONS)] = None
    character_pose: _lit(POSES)
    character_side: Literal["left", "right", "center"]
    props: list[_lit(PROPS)] = Field(default_factory=list)
    big_text: str = ""
    keywords: list[str] = Field(default_factory=list)
    camera: _lit(CAMERAS)
    transition: _lit(TRANSITIONS)
    sfx: _lit(SFX)
    image_prompt: str = ""


class ScriptOut(BaseModel):
    title: str
    mood: _lit(MOODS)
    description: str
    hashtags: list[str]
    ending: Literal["normal", "cut"] = "normal"
    scenes: list[SceneOut]


def write_with_claude(topic: str, duration: float, cfg) -> Script:
    try:
        import anthropic
    except ImportError as exc:
        raise ShortsError("Пакет anthropic не установлен: pip install -r requirements.txt") from exc
    words = int(duration * float(cfg.script.words_per_second))
    n_scenes = max(8, round(duration / 3.2))
    prompt = (f"Тема ролика: {topic}\n\nДлительность озвучки около {int(duration)} секунд: "
              f"всего примерно {words} слов, {n_scenes}–{n_scenes + 3} сцен. "
              "Придумай цепляющее название (до 60 символов), описание для YouTube (1–2 предложения) "
              "и 3–5 хэштегов.")
    client = anthropic.Anthropic(max_retries=3)
    log.info("Claude (%s) пишет сценарий…", cfg.script.model)
    try:
        with client.beta.messages.stream(
            model=cfg.script.model, max_tokens=32000, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"}, output_config={"effort": cfg.script.effort},
            output_format=ScriptOut,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError as exc:
        raise ShortsError("Неверный ключ Anthropic. Проверьте ANTHROPIC_API_KEY.") from exc
    except anthropic.RateLimitError as exc:
        raise ShortsError("Превышен лимит запросов Anthropic, попробуйте позже.") from exc
    except anthropic.APIStatusError as exc:
        raise ShortsError(f"Ошибка Anthropic API {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise ShortsError("Нет соединения с Anthropic API.") from exc
    if msg.stop_reason == "refusal":
        raise ShortsError("Модель отказалась писать сценарий на эту тему. Попробуйте другую тему.")
    if msg.stop_reason == "max_tokens" or msg.parsed_output is None:
        raise ShortsError("Сценарий не получен полностью, попробуйте ещё раз.")
    out: ScriptOut = msg.parsed_output
    script = Script(topic=topic, title=out.title, mood=out.mood, description=out.description,
                    hashtags=out.hashtags, ending=out.ending,
                    scenes=[Scene(**s.model_dump()) for s in out.scenes])
    script.validate()
    return script


# ---------------------------------------------------------------------------
# свой текст → сцены (без ключей)

_RULES = [  # (регулярное выражение по основе слова, setting, props)
    (r"океан|мор[еяю]|рыб|осьминог|кит|акул|волн", "underwater", ["fish"]),
    (r"космос|звезд|планет|галакт|марс|луна|вселенн|астронавт", "space", ["star", "rocket"]),
    (r"мозг|психолог|памят|мысл|сознан|подсознан|эмоци", "brain", ["brain", "lightbulb"]),
    (r"сон|сны|снит|ноч", "night_city", ["moon"]),
    (r"город|улиц|метро|дом[ауе]? |квартир", "night_city", []),
    (r"лес|дерев|животн|волк|медвед", "forest", []),
    (r"гор[аы]|верш|скал", "mountains", []),
    (r"пустын|песок|египет|пирамид", "desert", []),
    (r"учён|лаборатор|эксперимент|исследов|наук", "lab", ["magnifier"]),
    (r"комнат|кроват|дома\b|телефон|смартфон", "room", ["phone"]),
    (r"небо|закат|солнц|облак", "sky_sunset", []),
]
_PROP_RULES = [
    (r"сердц|любов", "heart"), (r"врем|час|минут|секунд|год", "clock"), (r"деньг|богат|миллион|доллар|рубл", "coin"),
    (r"телефон|смартфон", "phone"), (r"мир[аеу]?\b|страна|планет", "globe"), (r"глаз|видит|смотр", "eye"),
    (r"ключ|тайн|секрет", "key"), (r"книг|читал|учёб", "book"), (r"молни|энерги|электр", "lightning"),
    (r"смерт|погиб|опасн", "skull"), (r"идея|понял|догадал", "lightbulb"), (r"подар", "gift"),
]


def plan_scene(text: str, i: int, n: int) -> Scene:
    low = text.lower()
    setting, props = "abstract", []
    for pat, st, pr in _RULES:
        if re.search(pat, low):
            setting, props = st, list(pr)
            break
    for pat, pr in _PROP_RULES:
        if re.search(pat, low) and pr not in props:
            props.append(pr)
    if "?" in text:
        props.insert(0, "question")
        emotion, pose = "thinking", "think"
    elif "!" in text:
        emotion, pose = "surprised", "hands_up"
    elif re.search(r"страш|ужас|опасн|погиб|смерт|исчез", low):
        emotion, pose = "scared", "hands_up"
    elif re.search(r"груст|печал|одинок|потерял", low):
        emotion, pose = "sad", "idle"
    elif re.search(r"счаст|рад|улыб|отличн|лучш", low):
        emotion, pose = "happy", "wave"
    else:
        emotion, pose = "neutral", ["idle", "point", "shrug"][i % 3]
    nums = re.findall(r"\d+[\d\s,.]*%?", text)
    big = nums[0].strip() if nums else ""
    words = [w.strip(".,!?«»—-…:;") for w in text.split()]
    long_words = sorted([w for w in words if len(w) >= 7], key=len, reverse=True)
    keywords = ([big] if big else []) + long_words[:1]
    camera = ["zoom_in", "pan_right", "zoom_out", "pan_left", "push_up"][i % 5]
    if i == n - 1:
        camera, sfx, transition = "zoom_in", "boom", "flash"
    elif i == n - 2:
        sfx, transition = "riser", "zoom"
    else:
        sfx = "whoosh" if i % 2 == 0 else ("pop" if props else "none")
        transition = ["fade", "slide", "whip", "zoom"][i % 4]
    character = None if (props and i % 4 == 3) else emotion
    return Scene(text=text, setting=setting, character_emotion=character, character_pose=pose,
                 character_side=["left", "right"][i % 2], props=props[:3], big_text=big,
                 keywords=keywords, camera=camera, transition=transition, sfx=sfx)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[.!?…])\s+(?=[А-ЯЁA-Z«\"0-9—-])", text)
    out = []
    for p in parts:
        # длинные предложения делим по запятым/тире, чтобы картинка менялась каждые 2–4 с
        if len(p.split()) > 16:
            chunks = re.split(r"(?<=[,;:—])\s+", p)
            buf = ""
            for ch in chunks:
                if buf and len((buf + " " + ch).split()) > 12:
                    out.append(buf)
                    buf = ch
                else:
                    buf = f"{buf} {ch}".strip()
            if buf:
                out.append(buf)
        else:
            out.append(p)
    return [o.strip() for o in out if o.strip()]


def script_from_text(text: str, topic: str = "", mood: str = "mystery") -> Script:
    if re.search(r"[A-Za-z]{3,}", text):
        log.warning("В тексте есть латиница — Piper прочитает её плохо. Лучше писать по-русски.")
    sents = split_sentences(text)
    if not sents:
        raise ShortsError("Пустой текст сценария")
    scenes = [plan_scene(s, i, len(sents)) for i, s in enumerate(sents)]
    title = topic or sents[0][:60]
    script = Script(topic=topic or title, title=title, mood=mood, scenes=scenes,
                    description=sents[0], hashtags=["#shorts", "#факты", "#интересно"])
    script.validate()
    return script
