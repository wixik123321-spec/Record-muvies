"""Speech recognition with faster-whisper (word-level timestamps)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .utils import log, read_audio


@dataclass
class Word:
    start: float  # absolute source time, seconds
    end: float
    text: str

    @property
    def clean(self) -> str:
        return self.text.strip()


class Transcriber:
    """Lazy wrapper so the (large) model is only loaded when needed."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # heavy import

            device = self.cfg.whisper_device
            compute = self.cfg.whisper_compute_type
            if device == "auto":
                try:
                    import ctranslate2
                    device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
                except Exception:  # noqa: BLE001
                    device = "cpu"
            if compute == "auto":
                compute = "float16" if device == "cuda" else "int8"
            log.info("Loading Whisper model '%s' on %s (%s)…", self.cfg.whisper_model, device, compute)
            self._model = WhisperModel(self.cfg.whisper_model, device=device, compute_type=compute)
        return self._model

    def transcribe(self, media: Path, start: float, duration: float) -> list[Word]:
        audio = read_audio(media, start, duration, sr=16000)
        if audio.size == 0:
            return []
        model = self._load()
        lang = None if self.cfg.whisper_model.endswith(".en") else self.cfg.language
        segments, _ = model.transcribe(
            audio, language=lang, word_timestamps=True, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400}, beam_size=5,
            condition_on_previous_text=False,
        )
        words: list[Word] = []
        for seg in segments:
            for w in seg.words or []:
                if w.word.strip():
                    words.append(Word(start + w.start, start + w.end, w.word.strip()))
        return words
