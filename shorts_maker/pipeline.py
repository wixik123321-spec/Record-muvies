"""End-to-end orchestration: sources -> analysis -> ranking -> editing -> export."""

from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

from tqdm import tqdm

from . import llm
from .audio_analysis import AudioProfile, analyse_audio, pick_peaks
from .config import Config
from .editor import render
from .export import (clip_filename, verify_captions, verify_mp4, vod_link, write_clip_text,
                     write_manifest)
from .highlights import Candidate, choose_boundaries, dedupe, heuristic_metadata, heuristic_score
from .layout import plan_layout
from .sources import Source, download_audio, fetch_clip, list_vods, local_source
from .subtitles import build_ass
from .timeline import build_timeline, total_duration
from .transcribe import Transcriber
from .utils import fmt_ts, log, require_binaries, video_size

WINDOW_BEFORE, WINDOW_AFTER = 50.0, 25.0
# A streamer's facecam stays in the same place for the whole VOD: once it is
# found in one clip, reuse it for clips where the face was not detected
# (looking away, dark scene, cutscene).
_FACECAM_BY_SOURCE: dict = {}


def _confirm_overwrite(path: Path, cfg: Config) -> bool:
    if cfg.overwrite is not None:
        return cfg.overwrite
    if sys.stdin.isatty():
        ans = input(f"{path.name} already exists. Overwrite? [y/N] ").strip().lower()
        return ans in ("y", "yes")
    log.info("Keeping existing %s (use --overwrite to replace)", path.name)
    return False


def gather_sources(cfg: Config) -> list[Source]:
    if cfg.input_files:
        return [local_source(Path(p), i) for i, p in enumerate(cfg.input_files, 1)]
    sources = []
    for src in list_vods(cfg):
        if download_audio(src, cfg):
            sources.append(src)
    return sources


def find_candidates(sources: list[Source], cfg: Config,
                    transcriber: Transcriber) -> tuple[list[Candidate], dict[str, AudioProfile]]:
    profiles: dict[str, AudioProfile] = {}
    cands: list[Candidate] = []
    per_source = math.ceil(cfg.target_clips * cfg.candidates_per_clip / max(1, len(sources)))
    for src in sources:
        log.info("Analysing audio of '%s'…", src.title)
        bar = tqdm(desc="  audio", unit="min", leave=False)
        last = [0]

        def tick(sec, bar=bar, last=last):
            m = sec // 60
            if m > last[0]:
                bar.update(m - last[0])
                last[0] = m
        try:
            profile = analyse_audio(src.audio_path, progress=tick)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping '%s': audio analysis failed (%s)", src.title, exc)
            continue
        finally:
            bar.close()
        profiles[src.id] = profile
        for peak in pick_peaks(profile, per_source, cfg.min_gap_between_candidates):
            ws = max(0.0, peak - WINDOW_BEFORE)
            we = min(profile.duration, peak + WINDOW_AFTER)
            cands.append(Candidate(source=src, peak=peak, window_start=ws, window_end=we,
                                   audio_score=float(profile.excitement[int(peak)])))
    log.info("Transcribing %d candidate moments with Whisper…", len(cands))
    for c in tqdm(cands, desc="transcribe", unit="clip"):
        try:
            c.words = transcriber.transcribe(c.source.audio_path, c.window_start,
                                             c.window_end - c.window_start)
        except Exception as exc:  # noqa: BLE001
            log.warning("Transcription failed at %s: %s", fmt_ts(c.peak), exc)
        c.start, c.end = choose_boundaries(c, cfg)
        c.score = heuristic_score(c)
    return cands, profiles


def _dump_candidates(cands: list[Candidate], cfg: Config) -> None:
    """Save every candidate with its transcript for review (output/_tmp/candidates.json)."""
    import json
    data = [{"source": c.source.id, "peak": round(c.peak, 1), "start": round(c.start, 1),
             "end": round(c.end, 1), "score": c.score, "title": c.title,
             "text": c.text(c.window_start, c.window_end)} for c in cands]
    (cfg.temp_dir / "candidates.json").write_text(json.dumps(data, indent=1), encoding="utf-8")


def rank(cands: list[Candidate], profiles: dict[str, AudioProfile], cfg: Config) -> list[Candidate]:
    used_llm = False
    if cands and llm.llm_available(cfg):
        used_llm = llm.rank_with_llm(cands, profiles, cfg)
        if not used_llm:
            log.warning("AI ranking failed - falling back to heuristic scores")
            for c in cands:
                c.start, c.end = choose_boundaries(c, cfg)
                c.score = heuristic_score(c)
    for c in cands:
        if not c.title:
            heuristic_metadata(c, cfg)
    _dump_candidates(cands, cfg)
    ranked = dedupe(cands)
    ranked = [c for c in ranked if c.score > 0]
    ranked.sort(key=lambda c: c.score, reverse=True)
    picked = ranked[: cfg.target_clips]
    log.info("Selected %d clips (%s ranking):", len(picked), "AI" if used_llm else "heuristic")
    for i, c in enumerate(picked, 1):
        log.info("  %2d. %.1f  %s  [%s @ %s, %.0fs]", i, c.score, c.title, c.source.id,
                 fmt_ts(c.start), c.duration)
    return picked


def produce(c: Candidate, rank_no: int, profile: AudioProfile, cfg: Config,
            use_llm: bool) -> dict:
    name = clip_filename(rank_no, c, cfg)
    final = cfg.output_dir / name
    row = {"rank": rank_no, "file": name, "title": c.title, "score": round(c.score, 2),
           "category": c.category, "source_title": c.source.title, "source_url": c.source.url,
           "vod_link": vod_link(c), "start": fmt_ts(c.start), "end": fmt_ts(c.end),
           "description": c.description, "hashtags": " ".join(c.hashtags), "reason": c.reason,
           "status": "", "issues": "", "layout": "", "duration_s": ""}
    if final.exists() and not _confirm_overwrite(final, cfg):
        row["status"] = "kept-existing"
        return row

    work = cfg.temp_dir / f"clip{rank_no:02d}"
    work.mkdir(parents=True, exist_ok=True)
    clip = fetch_clip(c.source, c.start, c.end, cfg)
    w, h = video_size(clip.path)
    layout = plan_layout(str(clip.path), c.start - clip.offset, c.end - clip.offset, w, h,
                         cfg.width, cfg.height)
    known = _FACECAM_BY_SOURCE.get(c.source.id)
    if layout.kind == "split" and layout.exact:
        _FACECAM_BY_SOURCE[c.source.id] = layout
    elif known and (known.src_w, known.src_h) == (w, h) and (
            layout.kind == "blur" or not layout.exact):
        log.info("Layout: reusing facecam position found earlier in this VOD")
        layout = known
    if use_llm:
        llm.fix_captions(c, cfg)
    pieces = build_timeline(c, profile, cfg)
    duration = total_duration(pieces)
    ass = work / "captions.ass"
    n_events = build_ass(c.words_in(), pieces, cfg, layout.caption_y, c.emphasis, ass, duration)
    tmp_out = work / "render.mp4"
    render(clip.path, clip.offset, pieces, layout, ass, tmp_out, cfg)

    issues = verify_mp4(tmp_out, cfg, duration)
    if not issues and n_events:
        issues += verify_captions(tmp_out, ass, layout.caption_y, cfg, duration)
    fatal = [i for i in issues if not i.startswith(("captions not", "no caption"))]
    if fatal:
        raise RuntimeError("; ".join(fatal))
    shutil.move(str(tmp_out), final)
    write_clip_text(final.with_suffix(".txt"), c)
    row.update(status="ok", issues="; ".join(issues), layout=layout.kind,
               duration_s=round(duration, 1))
    log.info("✔ %s (%.1fs, %s layout%s)", name, duration, layout.kind,
             f", warnings: {'; '.join(issues)}" if issues else "")
    return row


def prime_facecam(picked: list[Candidate], cfg: Config) -> None:
    """Find each VOD's facecam once up front so every clip uses the same layout."""
    for c in picked:
        if c.source.id in _FACECAM_BY_SOURCE:
            continue
        try:
            clip = fetch_clip(c.source, c.start, c.end, cfg)
            w, h = video_size(clip.path)
            layout = plan_layout(str(clip.path), c.start - clip.offset, c.end - clip.offset,
                                 w, h, cfg.width, cfg.height)
        except Exception as exc:  # noqa: BLE001 - handled again per clip
            log.debug("facecam priming failed: %s", exc)
            continue
        if layout.kind == "split" and layout.exact:
            _FACECAM_BY_SOURCE[c.source.id] = layout


def run_pipeline(cfg: Config) -> int:
    require_binaries("ffmpeg", "ffprobe")
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.temp_dir.mkdir(parents=True, exist_ok=True)

    sources = gather_sources(cfg)
    if not sources:
        log.error("No usable sources. Nothing to do.")
        return 2
    transcriber = Transcriber(cfg)
    cands, profiles = find_candidates(sources, cfg, transcriber)
    picked = rank(cands, profiles, cfg)
    if len(picked) < cfg.min_clips:
        log.warning("Only %d suitable clips found (wanted %d-%d). Add more VODs with --max-vods "
                    "or --vod.", len(picked), cfg.min_clips, cfg.target_clips)
    if cfg.dry_run:
        log.info("Dry run: not rendering.")
        return 0

    prime_facecam(picked, cfg)
    use_llm = llm.llm_available(cfg)
    rows = []
    for i, c in enumerate(tqdm(picked, desc="render", unit="clip"), 1):
        try:
            rows.append(produce(c, i, profiles[c.source.id], cfg, use_llm))
        except Exception as exc:  # noqa: BLE001 - one bad clip must not stop the batch
            log.error("✘ clip %d (%s) failed: %s", i, c.title, exc)
            rows.append({"rank": i, "file": "", "status": "failed", "title": c.title,
                         "issues": str(exc)[:500], "vod_link": vod_link(c),
                         "source_url": c.source.url, "start": fmt_ts(c.start), "end": fmt_ts(c.end),
                         "description": c.description, "hashtags": " ".join(c.hashtags)})
    write_manifest(rows, cfg.output_dir)

    ok = sum(1 for r in rows if r["status"] in ("ok", "kept-existing"))
    log.info("Done: %d/%d Shorts in %s", ok, len(picked), cfg.output_dir.resolve())
    if not cfg.keep_temp and ok == len(picked):
        shutil.rmtree(cfg.temp_dir, ignore_errors=True)
        log.info("Temporary files removed")
    elif not cfg.keep_temp:
        log.info("Kept temporary files in %s because some clips failed", cfg.temp_dir)
    return 0 if ok >= min(cfg.min_clips, len(picked)) else 1
