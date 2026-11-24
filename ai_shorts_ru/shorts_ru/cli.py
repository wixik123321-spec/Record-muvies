"""Командная строка: python -m shorts_ru "тема ролика"."""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .utils import ShortsError, log, setup_logging


def _load_dotenv() -> None:
    import os
    from pathlib import Path
    for path in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if v.strip() and not os.environ.get(k.strip()):
                        os.environ[k.strip()] = v.strip().strip('"')
            break


def main(argv=None) -> int:
    _load_dotenv()
    p = argparse.ArgumentParser(prog="shorts_ru", description="Анимационные YouTube Shorts с русской озвучкой по одной теме.")
    p.add_argument("topic", nargs="?", help="тема ролика, например «почему мы видим сны»")
    p.add_argument("-d", "--duration", type=float, help="длительность, с: 30–60 для Shorts, до 1800 для длинных видео")
    p.add_argument("--format", choices=["short", "long"], help="short = вертикальный Shorts, long = видео 16:9 с главами")
    p.add_argument("--channel", help="название канала для заставок, превью, шапки и описания")
    p.add_argument("--workers", help="число процессов рендера (auto по умолчанию)")
    p.add_argument("-c", "--config", help="свой config.yaml")
    p.add_argument("-o", "--out", default="output", help="папка для результата (output)")
    p.add_argument("--name", help="имя файла без расширения")
    p.add_argument("--text", help="свой текст сценария (строка или путь к .txt) — без Claude API")
    p.add_argument("--script", help="готовый script.json (например, отредактированный после прошлого запуска)")
    p.add_argument("--mood", choices=["mystery", "epic", "calm", "tense", "upbeat"], help="настроение для --text")
    p.add_argument("--voice", help="голос: male_1 | male_0 | female_0 | female_1 | female_2 (Vosk) "
                                   "или ru_RU-dmitri-medium и др. (Piper)")
    p.add_argument("--music", help="свой музыкальный файл вместо сгенерированной музыки")
    p.add_argument("--images", choices=["procedural", "openai"], help="источник картинок")
    p.add_argument("--preview-frames", type=float, nargs="+", metavar="T",
                   help="только сохранить кадры в эти секунды (быстрая проверка стиля)")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    setup_logging(a.verbose)
    try:
        cfg = load_config(a.config)
        if a.duration:
            if not 30 <= a.duration <= 1800:
                raise ShortsError("--duration должна быть от 30 до 1800 секунд")
            cfg["video"]["duration"] = a.duration
            cfg["_duration_from_cli"] = True
        if a.workers:
            cfg["video"]["workers"] = a.workers
        if a.voice:
            if a.voice.startswith("ru_RU-"):
                cfg["voice"]["provider"], cfg["voice"]["piper_voice"] = "piper", a.voice
            else:
                cfg["voice"]["provider"], cfg["voice"]["vosk_voice"] = "vosk", a.voice
        if a.images:
            cfg["visuals"]["provider"] = a.images
        from .pipeline import render
        render(a, cfg)
        return 0
    except ShortsError as exc:
        log.error("Ошибка: %s", exc)
        return 1
    except KeyboardInterrupt:
        log.error("Остановлено пользователем")
        return 130


if __name__ == "__main__":
    sys.exit(main())
