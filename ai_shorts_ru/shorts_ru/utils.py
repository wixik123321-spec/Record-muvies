"""Общие помощники: логирование, ошибки, шрифты, запуск ffmpeg."""

from __future__ import annotations

import logging
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

log = logging.getLogger("shorts_ru")


class ShortsError(RuntimeError):
    """Понятная пользователю ошибка (выводится без трассировки)."""


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")


def require(binary: str, hint: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise ShortsError(f"Не найдена программа «{binary}». {hint}")
    return path


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise ShortsError(f"Команда завершилась с ошибкой: {Path(cmd[0]).name}\n{r.stderr[-1500:]}")
    return r


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


@lru_cache(maxsize=None)
def font(spec: str, size: int) -> ImageFont.FreeTypeFont:
    """Шрифт по пути или имени fontconfig; с кириллицей."""
    p = Path(spec)
    if p.suffix.lower() in (".ttf", ".otf") and p.exists():
        return ImageFont.truetype(str(p), size)
    for pattern in (spec, "Inter:style=Black", "DejaVu Sans:style=Bold"):
        try:
            path = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True,
                                  text=True, timeout=5).stdout.strip()
            if path:
                return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001 - fc-match может отсутствовать (Windows)
            continue
    for cand in ("C:/Windows/Fonts/arialbd.ttf", "/Library/Fonts/Arial Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if Path(cand).exists():
            return ImageFont.truetype(cand, size)
    raise ShortsError("Не найден шрифт с кириллицей. Укажите путь к .ttf в captions.font в config.yaml")
