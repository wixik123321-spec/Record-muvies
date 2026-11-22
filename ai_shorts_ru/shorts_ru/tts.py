"""Русская озвучка и тайминги слов.

* piper (по умолчанию): нейросетевые голоса Piper, работают офлайн и бесплатно.
  Голос (~63 МБ) один раз скачивается с Hugging Face в ~/.cache/shorts_ru/voices.
* elevenlabs: облачные голоса ElevenLabs (ключ ELEVENLABS_API_KEY, elevenlabs.io → Profile → API Keys).

Каждая сцена озвучивается отдельно, поэтому границы сцен точные. Время каждого
слова внутри сцены считается по числу фонем (Piper/espeak) с поправкой на
паузы у знаков препинания, а при наличии faster-whisper уточняется
распознаванием (слова сопоставляются с текстом сценария, поэтому в субтитрах
всегда исходный текст без ошибок распознавания).
"""

from __future__ import annotations

import difflib
import os
import re
import urllib.request
import wave
from pathlib import Path

import numpy as np

from .utils import ShortsError, log, run

SR = 44100
VOICE_DIR = Path(os.environ.get("SHORTS_RU_VOICES", Path.home() / ".cache" / "shorts_ru" / "voices"))
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/{name}/{quality}/ru_RU-{name}-{quality}.{ext}"


# ---------------------------------------------------------------------------

def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if w.getnchannels() == 2:
            x = x.reshape(-1, 2).mean(axis=1)
    return x, sr


def _write_wav(path: Path, x: np.ndarray, sr: int = SR) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def _resample(x: np.ndarray, sr: int, to: int = SR) -> np.ndarray:
    if sr == to:
        return x
    n = int(len(x) * to / sr)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def _speech_span(x: np.ndarray, sr: int) -> tuple[float, float]:
    hop = int(sr * 0.01)
    env = np.array([np.abs(x[i:i + hop]).mean() for i in range(0, max(1, len(x) - hop), hop)])
    thr = max(1e-4, env.max() * 0.06)
    idx = np.where(env > thr)[0]
    if not len(idx):
        return 0.0, len(x) / sr
    return idx[0] * 0.01, (idx[-1] + 1) * 0.01


# ---------------------------------------------------------------------------

class PiperTTS:
    def __init__(self, voice: str, speed: float = 1.0):
        try:
            from piper import PiperVoice, SynthesisConfig
        except ImportError as exc:
            raise ShortsError("Не установлен piper-tts: pip install -r requirements.txt") from exc
        self.SynthesisConfig = SynthesisConfig
        model = self._ensure(voice)
        log.info("Голос Piper: %s", voice)
        self.voice = PiperVoice.load(str(model))
        self.speed = speed

    @staticmethod
    def _ensure(voice: str) -> Path:
        m = re.fullmatch(r"ru_RU-(\w+)-(\w+)", voice)
        if not m:
            raise ShortsError(f"Неизвестный голос Piper: {voice}. Пример: ru_RU-dmitri-medium")
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        model = VOICE_DIR / f"{voice}.onnx"
        for ext in ("onnx", "onnx.json"):
            dest = VOICE_DIR / f"{voice}.{ext}"
            if dest.exists() and dest.stat().st_size > 1000:
                continue
            url = HF.format(name=m.group(1), quality=m.group(2), ext=ext)
            log.info("Скачиваю голос %s (%s)…", voice, ext)
            try:
                tmp = dest.with_suffix(dest.suffix + ".part")
                urllib.request.urlretrieve(url, tmp)
                tmp.rename(dest)
            except Exception as exc:  # noqa: BLE001
                raise ShortsError(f"Не удалось скачать голос с Hugging Face: {exc}\n"
                                  f"Скачайте вручную {url} в {VOICE_DIR}") from exc
        return model

    def synth(self, text: str, out: Path) -> tuple[np.ndarray, list[float]]:
        cfg = self.SynthesisConfig(length_scale=1.0 / max(0.5, self.speed), noise_scale=0.6, noise_w_scale=0.75)
        chunks = list(self.voice.synthesize(text, syn_config=cfg))
        if not chunks:
            raise ShortsError(f"Piper не озвучил текст: {text!r}")
        sr = chunks[0].sample_rate
        x = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)
        x = _resample(x, sr)
        weights = [self._weight(w) for w in text.split()]
        _write_wav(out, x)
        return x, weights

    def _weight(self, word: str) -> float:
        core = re.sub(r"[^\wёЁ-]", "", word)
        try:
            ph = sum(len(s) for s in self.voice.phonemize(core)) if core else 0
        except Exception:  # noqa: BLE001
            ph = len(core)
        pause = 3.0 if re.search(r"[,;:—]$", word) else (5.0 if re.search(r"[.!?…]$", word) else 0.0)
        return max(1.0, ph) + pause


class ElevenLabsTTS:
    """Облачный TTS ElevenLabs (модель eleven_multilingual_v2 говорит по-русски)."""

    def __init__(self, voice_id: str, model: str):
        import requests
        self.requests = requests
        self.key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not self.key:
            raise ShortsError("Для ElevenLabs нужен ключ: export ELEVENLABS_API_KEY=… (elevenlabs.io → API Keys)")
        if not voice_id:
            raise ShortsError("Укажите voice.elevenlabs_voice_id в config.yaml (ID голоса из библиотеки ElevenLabs)")
        self.voice_id, self.model = voice_id, model

    def synth(self, text: str, out: Path) -> tuple[np.ndarray, list[float]]:
        r = self.requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}?output_format=mp3_44100_128",
            headers={"xi-api-key": self.key, "Content-Type": "application/json"},
            json={"text": text, "model_id": self.model,
                  "voice_settings": {"stability": 0.4, "similarity_boost": 0.8, "style": 0.35}},
            timeout=120)
        if r.status_code != 200:
            raise ShortsError(f"ElevenLabs вернул {r.status_code}: {r.text[:300]}")
        mp3 = out.with_suffix(".mp3")
        mp3.write_bytes(r.content)
        run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", str(SR), str(out)])
        x, _ = _read_wav(out)
        weights = [max(1.0, len(re.sub(r"[^\wёЁ]", "", w))) + (3 if re.search(r"[,.!?…:;—]$", w) else 0)
                   for w in text.split()]
        return x, weights


# ---------------------------------------------------------------------------
# тайминги слов

def proportional_words(text: str, weights: list[float], x: np.ndarray, sr: int, offset: float) -> list[dict]:
    a, b = _speech_span(x, sr)
    words = text.split()
    total = sum(weights) or 1.0
    t, out = a, []
    for w, wt in zip(words, weights):
        d = (b - a) * wt / total
        out.append({"w": w, "s": round(offset + t, 3), "e": round(offset + t + d * 0.92, 3)})
        t += d
    return out


class WhisperAligner:
    """Уточняет время слов распознаванием faster-whisper (модель small, ~480 МБ)."""

    def __init__(self, mode: str):
        self.model = None
        if mode == "no":
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            if mode == "yes":
                raise ShortsError("Для align_with_whisper: yes установите faster-whisper")
            return
        try:
            # auto: только если модель уже скачана; yes: скачать при необходимости
            self.model = WhisperModel("small", device="cpu", compute_type="int8",
                                      local_files_only=(mode == "auto"))
            log.info("Тайминги субтитров уточняются через faster-whisper")
        except Exception as exc:  # noqa: BLE001
            if mode == "yes":
                raise ShortsError(f"Не удалось загрузить модель Whisper: {exc}") from exc
            log.info("Whisper-модель не найдена — тайминги по фонемам (align_with_whisper: yes, чтобы скачать)")

    @staticmethod
    def _norm(w: str) -> str:
        return re.sub(r"[^\wё]", "", w.lower().replace("ё", "е"))

    def refine(self, words: list[dict], x: np.ndarray, sr: int, offset: float) -> list[dict]:
        if self.model is None or not words:
            return words
        audio16 = _resample(x, sr, 16000)
        segs, _ = self.model.transcribe(audio16, language="ru", word_timestamps=True, beam_size=5)
        rec = [(self._norm(w.word), w.start + offset, w.end + offset) for s in segs for w in (s.words or [])]
        if not rec:
            return words
        a = [self._norm(w["w"]) for w in words]
        b = [r[0] for r in rec]
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        fixed = [dict(w) for w in words]
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                fixed[blk.a + k]["s"] = round(rec[blk.b + k][1], 3)
                fixed[blk.a + k]["e"] = round(rec[blk.b + k][2], 3)
        # монотонность и разумная длина
        for i in range(1, len(fixed)):
            if fixed[i]["s"] < fixed[i - 1]["e"] - 0.05:
                fixed[i]["s"] = fixed[i - 1]["e"]
            fixed[i]["e"] = max(fixed[i]["e"], fixed[i]["s"] + 0.08)
        return fixed


def make_engine(cfg):
    v = cfg.voice
    if v.provider == "piper":
        return PiperTTS(v.piper_voice, float(v.speed))
    if v.provider == "elevenlabs":
        return ElevenLabsTTS(v.elevenlabs_voice_id, v.elevenlabs_model)
    raise ShortsError(f"Неизвестный voice.provider: {v.provider} (piper | elevenlabs)")


def voice_script(script, cfg, work: Path) -> np.ndarray:
    """Озвучивает все сцены, заполняет scene.start/end/words. Возвращает общую дорожку голоса."""
    work.mkdir(parents=True, exist_ok=True)
    engine = make_engine(cfg)
    aligner = WhisperAligner(str(cfg.voice.align_with_whisper))
    pause = float(cfg.voice.sentence_pause)
    lead = 0.15
    parts, t = [np.zeros(int(lead * SR), np.float32)], lead
    for i, sc in enumerate(script.scenes):
        path = work / f"voice_{i:02d}.wav"
        x, weights = engine.synth(sc.text, path)
        words = proportional_words(sc.text, weights, x, SR, t)
        words = aligner.refine(words, x, SR, t)
        sc.start, sc.end, sc.audio, sc.words = t, t + len(x) / SR, str(path), words
        gap = pause if i < len(script.scenes) - 1 else 0.6
        parts += [x, np.zeros(int(gap * SR), np.float32)]
        t = sc.end + gap
        log.info("  сцена %d: %.1f с — %s", i + 1, sc.end - sc.start, sc.text[:60])
    # сцена длится до начала следующей
    for a, b in zip(script.scenes, script.scenes[1:]):
        a.end = b.start
    script.scenes[0].start = 0.0
    script.scenes[-1].end = t
    return np.concatenate(parts)
