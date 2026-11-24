"""Полный цикл: тема → сценарий → озвучка → субтитры → анимация → музыка → MP4 (+ пакет для публикации)."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import re
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from . import animator, audio, tts
from .captions import CaptionRenderer
from .config import Config, _merge
from .models import Script
from .utils import ShortsError, log, require, run
from .writer import script_from_text, write_with_claude

LIMITS = {"short": (30.0, 60.0), "long": (60.0, 1800.0)}


def slug(text: str) -> str:
    tr = str.maketrans("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                       "abvgdeejzijklmnoprstufhccss_y_eua")
    s = text.lower().translate(tr)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40] or "video"


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


def apply_format(script: Script, cfg: Config) -> Config:
    """Для длинных видео подставить настройки из секции long: в config.yaml."""
    if script.format == "long":
        cli_duration = cfg.video.duration if cfg.get("_duration_from_cli") else None
        cfg = Config(_merge(dict(cfg), dict(cfg.get("long") or {})))
        if cli_duration:
            cfg["video"]["duration"] = cli_duration
    animator.configure(int(cfg.video.width), int(cfg.video.height))
    return cfg


def fit_duration(script: Script, voice: np.ndarray, cfg, work: Path) -> np.ndarray:
    """Если озвучка далеко от целевой длительности — переозвучить с другой скоростью."""
    lo_lim, hi_lim = LIMITS[script.format]
    target = float(cfg.video.duration)
    tol = 8.0 if script.format == "short" else 25.0
    length = len(voice) / tts.SR
    lo, hi = max(lo_lim, target - tol), min(hi_lim, target + tol)
    if lo <= length <= hi or cfg.voice.provider not in ("piper", "vosk"):
        if not lo_lim <= length <= hi_lim:
            log.warning("Длительность %.1f с вне диапазона %.0f–%.0f с — поправьте длину сценария", length, lo_lim, hi_lim)
        return voice
    k = length / target
    new_speed = float(cfg.voice.speed) * min(1.2, max(0.85, k))
    log.info("Озвучка %.1f с, цель %.0f с — переозвучиваю со скоростью %.2f", length, target, new_speed)
    cfg["voice"]["speed"] = new_speed
    voice = tts.voice_script(script, cfg, work)
    length = len(voice) / tts.SR
    if not lo <= length <= hi:
        log.warning("Итоговая длительность %.1f с (цель %.0f с) — сценарий стоит %s",
                    length, target, "сократить" if length > target else "дополнить")
    return voice


# ---------------------------------------------------------------------------
# рендер кадров (параллельно, кусками)

def _encode_cmd(cfg, out: Path, threads: int) -> list[str]:
    W, H, fps = animator.W, animator.H, int(cfg.video.fps)
    return ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.video.crf), "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-g", str(fps * 2), "-threads", str(threads), str(out)]


def _load_images(work: Path, cfg, script) -> dict | None:
    if cfg.visuals.provider != "openai":
        return None
    from PIL import Image
    imgs = {}
    for i in range(len(script.scenes)):
        p = work / "images" / f"scene_{i:02d}.png"
        if p.exists():
            imgs[i] = Image.open(p).convert("RGB")
    return imgs


def _render_chunk(job: dict) -> str:
    """Выполняется в отдельном процессе: кадры [f0, f1) → кусок видео без звука."""
    import cv2
    cv2.setNumThreads(1)
    cfg = Config(job["cfg"])
    animator.configure(job["width"], job["height"])
    work = Path(job["work"])
    script = Script.load(work / "script.json")
    env = np.load(work / "env.npy")
    fps = int(cfg.video.fps)
    anim = animator.Animator(script, cfg, env, fps, _load_images(work, cfg, script))
    caps = CaptionRenderer(cfg, script.scenes, animator.W)
    out = Path(job["out"])
    proc = subprocess.Popen(_encode_cmd(cfg, out, job["threads"]), stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for i in range(job["f0"], job["f1"]):
        t = i / fps
        fr = caps.overlay(anim.frame(t), t)
        proc.stdin.write((np.clip(fr, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(proc.stderr.read().decode(errors="ignore")[-1500:])
    return str(out)


def render_video(script: Script, cfg, work: Path, mix_path: Path, final: Path, duration: float) -> None:
    fps = int(cfg.video.fps)
    total = int(duration * fps)
    workers = cfg.video.get("workers", "auto")
    workers = max(1, min(6, (os.cpu_count() or 2))) if workers == "auto" else max(1, int(workers))
    chunk = max(fps * 10, min(fps * 30, total // (workers * 3) + 1))
    jobs = []
    seg_dir = work / "segments"
    seg_dir.mkdir(exist_ok=True)
    for k, f0 in enumerate(range(0, total, chunk)):
        jobs.append({"cfg": json.loads(json.dumps(cfg)), "width": animator.W, "height": animator.H,
                     "work": str(work), "f0": f0, "f1": min(total, f0 + chunk),
                     "out": str(seg_dir / f"seg_{k:04d}.mp4"), "threads": 2})
    log.info("Рендер %d кадров (%.1f с, %dx%d) в %d процессах, %d кусков…",
             total, duration, animator.W, animator.H, workers, len(jobs))
    t0 = time.time()
    done = 0
    if workers == 1:
        for j in jobs:
            _render_chunk(j)
            done += 1
            log.info("  %d/%d кусков, ~%.0f с осталось", done, len(jobs), (time.time() - t0) / done * (len(jobs) - done))
    else:
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
            futs = [ex.submit(_render_chunk, j) for j in jobs]
            for f in as_completed(futs):
                try:
                    f.result()
                except Exception as exc:  # noqa: BLE001
                    raise ShortsError(f"Ошибка рендера куска: {exc}") from exc
                done += 1
                el = time.time() - t0
                log.info("  %d/%d кусков, ~%.0f с осталось", done, len(jobs), el / done * (len(jobs) - done))
    lst = seg_dir / "list.txt"
    lst.write_text("".join(f"file '{Path(j['out']).name}'\n" for j in jobs), encoding="utf-8")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(mix_path),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-shortest", "-movflags", "+faststart", str(final)])
    for j in jobs:
        Path(j["out"]).unlink(missing_ok=True)


# ---------------------------------------------------------------------------

def render(args, cfg) -> Path:
    require("ffmpeg", "Установите FFmpeg: https://ffmpeg.org/download.html")
    t_start = time.time()
    script = make_script(args, cfg)
    if getattr(args, "format", None):
        script.format = args.format
    if getattr(args, "channel", None):
        script.channel = args.channel
    cfg = apply_format(script, cfg)
    out_dir = Path(args.out)
    name = args.name or slug(script.title)
    work = out_dir / f"{name}_work"
    work.mkdir(parents=True, exist_ok=True)
    script.save(work / "script.json")
    log.info("Сценарий: «%s», %d сцен, формат %s (%dx%d)", script.title, len(script.scenes), script.format,
             animator.W, animator.H)

    log.info("Озвучка…")
    speed_file = work / "voice_speed.json"
    if speed_file.exists():  # скорость, подобранная в прошлый раз (озвучка возьмётся из кэша)
        saved = json.loads(speed_file.read_text())
        if saved.get("base") == float(cfg.voice.speed) and saved.get("duration") == float(cfg.video.duration):
            cfg["voice"]["speed"] = saved["speed"]
    base_speed = float(cfg.voice.speed) if not speed_file.exists() else json.loads(speed_file.read_text()).get("base", float(cfg.voice.speed))
    voice = tts.voice_script(script, cfg, work / "voice")
    voice = fit_duration(script, voice, cfg, work / "voice")
    speed_file.write_text(json.dumps({"base": base_speed, "duration": float(cfg.video.duration),
                                      "speed": float(cfg.voice.speed)}))
    duration = len(voice) / tts.SR + (0.0 if script.ending == "cut" else 0.3)
    script.save(work / "script.json")  # с таймингами

    if cfg.visuals.provider == "openai":
        from .imagegen import generate_images
        generate_images(script, cfg, work / "images")

    log.info("Музыка и звук…")
    mix_path = audio.mix(voice, script, cfg, work / "audio.wav", args.music)

    fps = int(cfg.video.fps)
    env = audio.envelope(voice, fps)
    np.save(work / "env.npy", env)
    caps = CaptionRenderer(cfg, script.scenes, animator.W)
    _write_srt(caps, work / f"{name}.srt")

    if args.preview_frames:
        from PIL import Image
        anim = animator.Animator(script, cfg, env, fps, _load_images(work, cfg, script))
        for t in args.preview_frames:
            fr = caps.overlay(anim.frame(t), t)
            Image.fromarray((np.clip(fr, 0, 1) * 255).astype(np.uint8)).save(work / f"frame_{t:06.1f}.png")
        log.info("Кадры сохранены в %s", work)
        return work

    final = out_dir / f"{name}.mp4"
    render_video(script, cfg, work, mix_path, final, duration)
    _verify(final, duration)
    meta = {"title": script.title, "description": script.description, "hashtags": script.hashtags,
            "duration": round(duration, 1), "file": final.name}
    (out_dir / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if script.format == "long" or getattr(args, "kit", False):
        from .publish import make_kit
        make_kit(script, cfg, final, work / f"{name}.srt", out_dir / f"{name}_publish", duration)
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
    if not v or (v[0]["width"], v[0]["height"]) != (animator.W, animator.H) or v[0]["codec_name"] != "h264":
        problems.append(f"видео не H.264 {animator.W}x{animator.H}")
    if not a or a[0]["codec_name"] != "aac":
        problems.append("нет AAC-звука")
    if abs(dur - expected) > 1.0:
        problems.append(f"длительность {dur:.1f} с вместо {expected:.1f} с")
    if problems:
        raise ShortsError("Проверка файла не прошла: " + "; ".join(problems))
