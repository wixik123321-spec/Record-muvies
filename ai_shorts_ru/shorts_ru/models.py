"""Сценарий и сцены. Списки допустимых значений общие для ИИ-сценариста и 2D-движка."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

SETTINGS = ["night_city", "city_day", "room", "space", "ocean", "underwater", "forest", "mountains",
            "desert", "lab", "brain", "sky_sunset", "abstract"]
EMOTIONS = ["neutral", "happy", "surprised", "scared", "thinking", "sad", "angry", "excited"]
POSES = ["idle", "point", "hands_up", "think", "shrug", "wave"]
PROPS = ["question", "exclamation", "lightbulb", "brain", "heart", "clock", "coin", "phone", "globe",
         "eye", "key", "star", "book", "magnifier", "lightning", "rocket", "fish", "skull", "moon", "gift"]
CAMERAS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "push_up", "shake"]
TRANSITIONS = ["fade", "slide", "zoom", "flash", "whip"]
SFX = ["none", "whoosh", "pop", "boom", "riser", "ding", "click"]
MOODS = ["mystery", "epic", "calm", "tense", "upbeat"]


@dataclass
class Scene:
    text: str                                  # одно предложение озвучки (только русский)
    setting: str = "abstract"
    character_emotion: str | None = "neutral"  # None = без персонажа
    character_pose: str = "idle"
    character_side: str = "left"               # left | right | center
    props: list[str] = field(default_factory=list)
    big_text: str = ""                          # крупная надпись/число в кадре (2–3 слова максимум)
    keywords: list[str] = field(default_factory=list)  # слова для подсветки в субтитрах
    camera: str = "zoom_in"
    transition: str = "fade"
    sfx: str = "none"
    image_prompt: str = ""                      # для внешней генерации картинок (на английском)
    card: str = ""                              # "" | title | chapter | end — титульные карточки длинных видео
    chapter: int = -1                           # номер главы (индекс в Script.chapters), -1 = вне глав
    hold: float = 0.0                           # дополнительная пауза после сцены, с (например, под конечную заставку)
    # заполняется при рендере
    start: float = 0.0
    end: float = 0.0
    audio: str = ""
    words: list = field(default_factory=list)   # [{"w","s","e"}] абсолютное время

    def validate(self) -> None:
        if self.setting not in SETTINGS:
            self.setting = "abstract"
        if self.character_emotion is not None and self.character_emotion not in EMOTIONS:
            self.character_emotion = "neutral"
        if self.character_pose not in POSES:
            self.character_pose = "idle"
        if self.character_side not in ("left", "right", "center"):
            self.character_side = "left"
        self.props = [p for p in self.props if p in PROPS][:3]
        if self.camera not in CAMERAS:
            self.camera = "zoom_in"
        if self.transition not in TRANSITIONS:
            self.transition = "fade"
        if self.sfx not in SFX:
            self.sfx = "none"
        self.big_text = (self.big_text or "").strip()[:24]
        if self.card not in ("", "title", "chapter", "end"):
            self.card = ""
        self.hold = max(0.0, float(self.hold or 0))


@dataclass
class Script:
    topic: str
    title: str
    mood: str
    scenes: list[Scene]
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    ending: str = "normal"   # normal | cut (обрыв на полуслове — ролик зацикливается в Shorts)
    format: str = "short"    # short (9:16, 30–60 с) | long (16:9, несколько минут, с главами)
    chapters: list[dict] = field(default_factory=list)   # [{"title": "...", "mood": "calm"}]
    channel: str = ""        # название канала (для заставок, превью и описания)
    tags: list[str] = field(default_factory=list)
    title_options: list[str] = field(default_factory=list)
    thumbnail: list[dict] = field(default_factory=list)  # варианты превью [{"top","bottom","emotion","props","setting"}]
    sources: list[str] = field(default_factory=list)     # источники фактов для описания
    pinned_comment: str = ""

    def validate(self) -> None:
        if not self.scenes:
            raise ValueError("В сценарии нет сцен")
        if self.ending not in ("normal", "cut"):
            self.ending = "normal"
        if self.format not in ("short", "long"):
            self.format = "short"
        for ch in self.chapters:
            if ch.get("mood") not in MOODS:
                ch["mood"] = self.mood if self.mood in MOODS else "mystery"
        if self.mood not in MOODS:
            self.mood = "mystery"
        for s in self.scenes:
            s.validate()
            if not s.text.strip():
                raise ValueError("Пустой текст сцены")

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.scenes)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Script":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        scenes = [Scene(**{k: v for k, v in s.items() if k in Scene.__dataclass_fields__}) for s in d["scenes"]]
        extra = {k: d[k] for k in ("description", "hashtags", "ending", "format", "chapters", "channel", "tags",
                                   "title_options", "thumbnail", "sources", "pinned_comment") if k in d}
        sc = cls(topic=d.get("topic", ""), title=d.get("title", ""), mood=d.get("mood", "mystery"),
                 scenes=scenes, **extra)
        sc.validate()
        return sc
