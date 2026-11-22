"""Полный цикл: тема → сценарий → озвучка → субтитры → анимация → музыка → MP4."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

import numpy as np

from . import audio, tts
from .animator import H, W, Animator
from .captions import CaptionRenderer
from .models import Script
from .utils import ShortsError, log, require, run
from .writer import script_from_text, write_with_claude


def slug(text: str) -> str:
    tr = str.maketrans("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                       "abvgdeejzijklmnoprstufhccss_y_eua")
    s = text.lower().translate(tr)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40] or "short"


def make_script(args, cfg) -> Script:
    if args.script:
        return Script.load(Path(args.script))
    if args.text:
        text = args.text
        if len(text) < 260 and "\n" not in text:  # похоже на путь к файлу
            try:
                p = Path(text)
                if p.is_file():
                    text = p.read_text(encoding="utf-8")
            except OSError:
                pass
        return script_from_text(text, topic=args.topic or "", mood=args.mood or "mystery")
    if not args.topic:
        raise ShortsError("Укажите тему: python -m shorts_ru \"тема ролика\" (или --text / --script)")
    return write_with_claude(args.topic, float(cfg.video.duration), cfg)


def fit_duration(script: Script, voice: np.ndarray, cfg, work: Path) -> np.ndarray:
    """Если озвучка вышла за 30–60 с (или далеко от цели), переозвучить с другой скоростью."""
    target = float(cfg.video.duration)
    length = len(voice) / tts.SR
    lo, hi = max(30.0, target - 8), min(60.0, target + 8)
    if lo <= length <= hi or cfg.voice.provider != "piper":
        if not 30 <= length <= 60:
            log.warning("Длительность %.1f с вне диапазона 30–60 с — поправьте длину сценария", length)
        return voice
    k = length / target
    new_speed = float(cfg.voice.speed) * min(1.25, max(0.85, k))
    log.info("Озвучка %.1f с, цель %.0f с — переозвучиваю со скоростью %.2f", length, target, new_speed)
    cfg["voice"]["speed"] = new_speed
    voice = tts.voice_script(script, cfg, work)
    length = len(voice) / tts.SR
    if not 30 <= length <= 60:
        log.warning("Итоговая длительность %.1f с — сценарий слишком %s для 30–60 с",
                    length, "длинный" if length > 60 else "короткий")
    return voice


def render(args, cfg) -> Path:
    require("ffmpeg", "Установите FFmpeg: https://ffmpeg.org/download.html")
    t_start = time.time()
    script = make_script(args, cfg)
    out_dir = Path(args.out)
    name = args.name or slug(script.title)
    work = out_dir / f"{name}_work"
    work.mkdir(parents=True, exist_ok=True)
    script.save(work / "script.json")
    log.info("Сценарий: «%s», %d сцен, настроение %s", script.title, len(script.scenes), script.mood)

    log.info("Озвучка…")
    voice = tts.voice_script(script, cfg, work / "voice")
    voice = fit_duration(script, voice, cfg, work / "voice")
    duration = len(voice) / tts.SR + 0.3
    script.save(work / "script.json")  # с таймингами

    images = None
    if cfg.visuals.provider == "openai":
        from .imagegen import generate_images
        images = generate_images(script, cfg, work / "images")

    log.info("Музыка и звук…")
    mix_path = audio.mix(voice, script, cfg, work / "audio.wav", args.music)

    fps = int(cfg.video.fps)
    env = audio.envelope(voice, fps)
    anim = Animator(script, cfg, env, fps, images)
    caps = CaptionRenderer(cfg, script.scenes, W)
    _write_srt(caps, work / f"{name}.srt")

    if args.preview_frames:
        from PIL import Image
        for t in args.preview_frames:
            fr = caps.overlay(anim.frame(t), t)
            Image.fromarray((np.clip(fr, 0, 1) * 255).astype(np.uint8)).save(work / f"frame_{t:05.1f}.png")
        log.info("Кадры сохранены в %s", work)
        return work

    final = out_dir / f"{name}.mp4"
    total = int(duration * fps)
    log.info("Рендер %d кадров (%.1f с)…", total, duration)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-", "-i", str(mix_path), "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.video.crf), "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
           "-movflags", "+faststart", str(final)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    t0 = time.time()
    try:
        for i in range(total):
            t = i / fps
            fr = caps.overlay(anim.frame(t), t)
            proc.stdin.write((np.clip(fr, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
            if i % (fps * 5) == 0 and i:
                el = time.time() - t0
                log.info("  %4.1f / %.1f с  (осталось ~%.0f с)", t, duration, el / i * (total - i))
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait() != 0:
        raise ShortsError("FFmpeg не смог собрать видео:\n" + proc.stderr.read().decode(errors="ignore")[-1500:])
    _verify(final, duration)
    meta = {"title": script.title, "description": script.description, "hashtags": script.hashtags,
            "duration": round(duration, 1), "file": final.name}
    (out_dir / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Готово за %.0f с: %s", time.time() - t_start, final)
    return final


def _write_srt(caps: CaptionRenderer, path: Path) -> None:
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    lines = []
    for i, ph in enumerate(caps.phrases, 1):
        lines += [str(i), f"{ts(ph.start)} --> {ts(ph.end)}", " ".join(w["w"] for w in ph.words), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def _verify(path: Path, expected: float) -> None:
    info = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
                           str(path)]).stdout)
    v = [s for s in info["streams"] if s["codec_type"] == "video"]
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    dur = float(info["format"]["duration"])
    problems = []
    if not v or (v[0]["width"], v[0]["height"]) != (W, H) or v[0]["codec_name"] != "h264":
        problems.append("видео не H.264 1080x1920")
    if not a or a[0]["codec_name"] != "aac":
        problems.append("нет AAC-звука")
    if abs(dur - expected) > 1.0:
        problems.append(f"длительность {dur:.1f} с вместо {expected:.1f} с")
    if problems:
        raise ShortsError("Проверка файла не прошла: " + "; ".join(problems))
