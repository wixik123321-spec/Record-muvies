"""Command-line entry point: ``python -m shorts_maker`` (see README)."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import DEFAULT_CHANNEL_URL, Config
from .pipeline import run_pipeline
from .utils import setup_logging


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="shorts_maker",
        description="Turn Twitch GTA 6 VODs into 10-12 captioned vertical YouTube Shorts.")
    src = p.add_argument_group("sources")
    src.add_argument("--channel", default=DEFAULT_CHANNEL_URL, help="Twitch videos page URL")
    src.add_argument("--vod", action="append", default=[], metavar="URL",
                     help="specific VOD URL (repeatable); skips channel listing")
    src.add_argument("--input", action="append", default=[], type=Path, metavar="FILE",
                     help="local video file you own (repeatable); no download")
    src.add_argument("--title-keyword", action="append", metavar="WORD",
                     help="VOD title filter (repeatable). Default: GTA 6 variants. '' = any")
    src.add_argument("--max-vods", type=int, default=3)
    src.add_argument("--streamer", default="Kai Cenat")
    src.add_argument("--game", default="GTA 6")
    src.add_argument("--cookies-from-browser", metavar="BROWSER",
                     help="use your browser login for VODs your account may watch")

    out = p.add_argument_group("output")
    out.add_argument("--output", type=Path, default=Path("output/shorts"))
    out.add_argument("--temp", type=Path, default=Path("output/_tmp"))
    out.add_argument("--keep-temp", action="store_true")
    out.add_argument("--clips", type=int, default=12, help="how many Shorts to make")
    out.add_argument("--min-clips", type=int, default=10)
    ow = out.add_mutually_exclusive_group()
    ow.add_argument("--overwrite", dest="overwrite", action="store_const", const=True)
    ow.add_argument("--no-overwrite", dest="overwrite", action="store_const", const=False)
    out.add_argument("--dry-run", action="store_true", help="rank only, do not render")

    ai = p.add_argument_group("analysis")
    ai.add_argument("--whisper-model", default="small.en",
                    help="tiny.en | base.en | small.en | medium.en | large-v3")
    ai.add_argument("--device", default="auto", help="auto | cpu | cuda")
    ai.add_argument("--no-llm", action="store_true", help="heuristic ranking only")
    ai.add_argument("--llm-model", default="claude-opus-5-5")

    ed = p.add_argument_group("editing")
    ed.add_argument("--no-teaser", action="store_true", help="no cold-open hook")
    ed.add_argument("--no-zoom", action="store_true")
    ed.add_argument("--keep-pauses", action="store_true")
    ed.add_argument("--sfx", type=Path, help="short sound (wav/mp3) played on zoom-ins")
    ed.add_argument("--font", default="Arial Black")
    ed.add_argument("--censor", action="append", default=[], metavar="WORD",
                    help="mask a word in captions (repeatable)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def config_from_args(a: argparse.Namespace) -> Config:
    cfg = Config(
        channel_url=a.channel, vod_urls=a.vod, input_files=a.input, max_vods=a.max_vods,
        streamer_name=a.streamer, game_name=a.game, cookies_from_browser=a.cookies_from_browser,
        output_dir=a.output, temp_dir=a.temp, keep_temp=a.keep_temp,
        target_clips=a.clips, min_clips=min(a.min_clips, a.clips), overwrite=a.overwrite,
        dry_run=a.dry_run, whisper_model=a.whisper_model, whisper_device=a.device,
        use_llm=not a.no_llm, llm_model=a.llm_model, hook_teaser=not a.no_teaser,
        punch_zoom=1.0 if a.no_zoom else 1.12, remove_pauses=not a.keep_pauses,
        sfx_file=a.sfx, font_name=a.font, censor_words=tuple(a.censor),
    )
    if a.title_keyword is not None:
        cfg.title_keywords = tuple(k for k in a.title_keyword if k)
    return cfg


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    return run_pipeline(config_from_args(args))
