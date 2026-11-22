"""Загрузка config.yaml с подстановкой значений по умолчанию."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULTS: dict = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text(encoding="utf-8")) \
    if (Path(__file__).resolve().parent.parent / "config.yaml").exists() else {}


class Config(dict):
    """dict с доступом через точку: cfg.video.fps."""

    def __getattr__(self, key):
        try:
            v = self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc
        return Config(v) if isinstance(v, dict) and not isinstance(v, Config) else v

    def __setattr__(self, key, value):
        self[key] = value


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path | None = None) -> Config:
    data = copy.deepcopy(DEFAULTS)
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Файл конфигурации не найден: {p}")
        data = _merge(data, yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    cfg = Config(data)
    dur = float(cfg.video.duration)
    if not 30 <= dur <= 60:
        raise ValueError(f"video.duration должна быть 30–60 с, сейчас {dur}")
    return cfg
