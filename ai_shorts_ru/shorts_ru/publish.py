"""Пакет для публикации на YouTube: всё, что нужно рядом с видео.

Создаёт папку <имя>_publish/ с файлами:
  video.mp4, thumbnail_1..N.jpg, subtitles_ru.srt,
  description.txt (с таймкодами глав), titles.txt, tags.txt, pinned_comment.txt,
  chapters.txt, end_screen.md, UPLOAD_CHECKLIST.md, metadata.json,
  channel/banner.jpg (+ разметка безопасной зоны), channel/avatar.png
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import branding
from .utils import log


def ts(t: float) -> str:
    t = int(round(t))
    h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def chapters(script) -> list[tuple[float, str]]:
    """Таймкоды для описания: 00:00 вступление, начало каждой главы, финал."""
    out = [(0.0, "Вступление")]
    for sc in script.scenes:
        if sc.card == "chapter" and 0 <= sc.chapter < len(script.chapters):
            out.append((sc.start, script.chapters[sc.chapter]["title"]))
    finals = [sc for sc in script.scenes if sc.chapter == -1 and sc.start > (out[-1][0] + 10) and not sc.card]
    if finals:
        out.append((finals[0].start, "Итоги"))
    # YouTube: главы не короче 10 секунд
    clean = [out[0]]
    for t, title in out[1:]:
        if t - clean[-1][0] >= 10:
            clean.append((t, title))
    return clean


def make_kit(script, cfg, video: Path, srt: Path, kit: Path, duration: float) -> Path:
    kit.mkdir(parents=True, exist_ok=True)
    shutil.copy2(video, kit / "video.mp4")
    shutil.copy2(srt, kit / "subtitles_ru.srt")
    chs = chapters(script)
    chapter_lines = "\n".join(f"{ts(t)} {title}" for t, title in chs)
    (kit / "chapters.txt").write_text(chapter_lines + "\n", encoding="utf-8")

    channel = script.channel or "наш канал"
    hashtags = " ".join(script.hashtags[:3])
    sources = "\n".join(f"• {s}" for s in script.sources) or "—"
    description = (
        f"{script.description}\n\n"
        f"⏱ Таймкоды:\n{chapter_lines}\n\n"
        f"📚 Источники:\n{sources}\n\n"
        f"Подписывайся на «{channel}», чтобы не пропустить новые видео. "
        f"Напиши в комментариях, какую тему разобрать следующей!\n\n"
        f"{hashtags}\n"
    )
    (kit / "description.txt").write_text(description, encoding="utf-8")

    titles = script.title_options or [script.title]
    (kit / "titles.txt").write_text(
        "Варианты названия (рекомендуемое — первое; держите до 70 символов, чтобы не обрезалось):\n\n"
        + "\n".join(f"{i}. {t}  [{len(t)} симв.]" for i, t in enumerate(titles, 1)) + "\n", encoding="utf-8")

    tags, total = [], 0
    for t in script.tags:
        if total + len(t) + 1 > 480:   # лимит YouTube — 500 символов на все теги
            break
        tags.append(t)
        total += len(t) + 1
    (kit / "tags.txt").write_text(", ".join(tags) + "\n", encoding="utf-8")
    (kit / "pinned_comment.txt").write_text((script.pinned_comment or "") + "\n", encoding="utf-8")

    end = next((sc for sc in script.scenes if sc.card == "end"), None)
    end_start = end.start if end else max(0.0, duration - 20)
    end_len = min(20.0, duration - end_start)
    (kit / "end_screen.md").write_text(
        "# Конечная заставка (YouTube Studio → Редактор → Конечная заставка)\n\n"
        f"- Начало: **{ts(end_start)}**, длительность **{end_len:.0f} с** (YouTube разрешает 5–20 с).\n"
        "- В видео уже нарисованы места под элементы:\n"
        "  - слева — рамка «СМОТРИ ДАЛЬШЕ» → элемент **Видео: последнее загруженное**;\n"
        "  - справа — вторая рамка → **Видео: подобранное для зрителя**;\n"
        "  - внизу по центру круг с кнопкой «ПОДПИСАТЬСЯ» → элемент **Подписка**.\n"
        "- Подгоните элементы точно по рамкам: так заставка выглядит «родной».\n", encoding="utf-8")

    thumbs = script.thumbnail or [{"top": script.title[:20], "bottom": "", "emotion": "surprised"}]
    for i, spec in enumerate(thumbs, 1):
        branding.thumbnail(spec, cfg, kit / f"thumbnail_{i}.jpg")
    if script.channel:
        branding.banner(script.channel, cfg.get("channel_tagline", "Наука простым языком · новые видео каждую неделю"),
                        cfg, kit / "channel" / "banner.jpg")
        branding.avatar(cfg, kit / "channel" / "avatar.png")

    checklist = f"""# Чек-лист загрузки на YouTube

## Файлы
- [ ] `video.mp4` — {cfg.video.width}x{cfg.video.height}, {cfg.video.fps} fps, H.264 + AAC, {ts(duration)}
- [ ] Превью: `thumbnail_1.jpg` (основное). Остальные загрузите в **Тест и сравнение** (A/B-тест обложек в YouTube Studio)
- [ ] Субтитры: `subtitles_ru.srt` → Субтитры → Добавить → Загрузить файл → «С тайм-кодами», язык русский
  (в видео субтитры уже вшиты, но файл улучшает поиск и даёт автоперевод на другие языки)

## Сведения
- [ ] Название: первое из `titles.txt`
- [ ] Описание: `description.txt` целиком (таймкоды создадут главы на шкале прогресса)
- [ ] Теги: `tags.txt`
- [ ] Категория: **Образование**; язык видео и субтитров: **русский**
- [ ] Аудитория: **Нет, это видео не для детей**
- [ ] Изменённый или синтетический контент: видео — явная 2D-анимация с синтезированной озвучкой и не
  выдаёт себя за реальную съёмку, поэтому раскрытие обычно не требуется; при сомнениях отметьте «Да»
- [ ] Лицензия: стандартная лицензия YouTube; вся музыка и звуки сгенерированы программой (без чужих прав)

## Элементы
- [ ] Конечная заставка — по `end_screen.md`
- [ ] Подсказки (карточки): на начале глав предложите связанное видео или плейлист
- [ ] Плейлист: добавьте в плейлист по теме канала

## После публикации
- [ ] Закрепите комментарий из `pinned_comment.txt`
- [ ] Через 24–48 часов проверьте CTR превью и удержание; если CTR ниже ~4%, запустите A/B-тест обложек
"""
    if script.channel:
        checklist += """
## Оформление канала (один раз)
- [ ] Шапка: `channel/banner.jpg` (2560x1440; всё важное в безопасной зоне — см. `banner_safe_area.png`)
- [ ] Фото профиля: `channel/avatar.png` (800x800, YouTube обрежет по кругу)
"""
    (kit / "UPLOAD_CHECKLIST.md").write_text(checklist, encoding="utf-8")

    # сценарий по главам с таймкодами (для правок, перевода, будущих монтажей)
    lines = [f"# {script.title}", "", f"Длительность: {ts(duration)} · сцен: {len(script.scenes)}", ""]
    cur = None
    for sc in script.scenes:
        head = ("Вступление" if sc.chapter == -1 and sc.start < 60 else "Финал") if sc.chapter < 0 else \
            f"Глава {sc.chapter + 1}. {script.chapters[sc.chapter]['title']}"
        if sc.card == "end":
            head = "Конечная заставка"
        if head != cur:
            lines += ["", f"## {head}", ""]
            cur = head
        mark = {"title": " *(титульная карточка)*", "chapter": " *(карточка главы)*",
                "end": " *(конечная заставка)*"}.get(sc.card, "")
        lines.append(f"- `{ts(sc.start)}` {sc.text}{mark}")
    if script.sources:
        lines += ["", "## Источники", ""] + [f"- {x}" for x in script.sources]
    (kit / "script.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    files = sorted(p.relative_to(kit).as_posix() for p in kit.rglob("*") if p.is_file())
    readme = [f"# Пакет для публикации: «{titles[0]}»", "",
              f"Видео {cfg.video.width}x{cfg.video.height}, {ts(duration)}, {len(chs)} глав(ы) в описании.", "",
              "Начните с `UPLOAD_CHECKLIST.md` — там пошагово, что и куда загружать.", "", "## Файлы", ""]
    about = {"video.mp4": "готовое видео", "subtitles_ru.srt": "субтитры для загрузки в YouTube",
             "description.txt": "описание с таймкодами и источниками", "titles.txt": "варианты названия",
             "tags.txt": "теги", "pinned_comment.txt": "комментарий для закрепления",
             "chapters.txt": "только таймкоды глав", "end_screen.md": "настройка конечной заставки",
             "UPLOAD_CHECKLIST.md": "пошаговый чек-лист загрузки", "metadata.json": "все метаданные в JSON",
             "script.md": "сценарий с таймкодами", "channel/banner.jpg": "шапка канала 2560x1440",
             "channel/banner_safe_area.png": "шапка с разметкой безопасной зоны (не загружать)",
             "channel/avatar.png": "фото профиля 800x800"}
    for f in files + ["README.md"]:
        desc = about.get(f, "превью 1280x720" if f.startswith("thumbnail_") else "")
        readme.append(f"- `{f}`" + (f" — {desc}" if desc else ""))
    (kit / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    meta = {"title": titles[0], "title_options": titles, "description": description, "tags": tags,
            "hashtags": script.hashtags, "chapters": [{"time": ts(t), "title": n} for t, n in chs],
            "duration_sec": round(duration, 1), "channel": script.channel, "category": "Education",
            "language": "ru", "made_for_kids": False}
    (kit / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Пакет для публикации: %s", kit)
    return kit
