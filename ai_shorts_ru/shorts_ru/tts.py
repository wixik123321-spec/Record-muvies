"""Русская озвучка и тайминги слов.

* vosk (по умолчанию): Vosk TTS 0.9 от alphacep — выразительные русские голоса со словарём
  ударений, офлайн и бесплатно (Apache 2.0, можно для монетизируемых роликов).
  Модель (~750 МБ) один раз скачивается с alphacephei.com в ~/.cache/shorts_ru/vosk.
* piper: нейросетевые голоса Piper — легче (63 МБ), но интонация беднее и бывают ошибки ударений.
  Голос один раз скачивается с Hugging Face в ~/.cache/shorts_ru/voices.
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

    def synth(self, text: str, out: Path, rate: float = 1.0) -> tuple[np.ndarray, list[float]]:
        cfg = self.SynthesisConfig(length_scale=1.0 / max(0.5, self.speed * rate), noise_scale=0.6, noise_w_scale=0.75)
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



VOSK_DIR = Path(os.environ.get("SHORTS_RU_VOSK", Path.home() / ".cache" / "shorts_ru" / "vosk"))
VOSK_MODEL = "vosk-model-tts-ru-0.9-multi"
VOSK_SPEAKERS = {"female_0": 0, "female_1": 1, "female_2": 2, "male_0": 3, "male_1": 4}


class VoskTTS:
    """Vosk TTS: многоголосая русская модель с ударениями из словаря (alphacep, Apache 2.0)."""

    def __init__(self, voice: str, speed: float = 1.0):
        try:
            from vosk_tts import Model, Synth
        except ImportError as exc:
            raise ShortsError("Не установлен vosk-tts: pip install -r requirements.txt") from exc
        if voice not in VOSK_SPEAKERS:
            raise ShortsError(f"Неизвестный голос Vosk: {voice}. Доступны: {', '.join(VOSK_SPEAKERS)}")
        path = self._ensure()
        log.info("Голос Vosk: %s", voice)
        self.synth_ = Synth(Model(model_path=str(path)))
        self.sid, self.speed = VOSK_SPEAKERS[voice], speed

    @staticmethod
    def _ensure() -> Path:
        path = VOSK_DIR / VOSK_MODEL
        if (path / "model.onnx").exists():
            return path
        import zipfile
        VOSK_DIR.mkdir(parents=True, exist_ok=True)
        url = f"https://alphacephei.com/vosk/models/{VOSK_MODEL}.zip"
        tmp = VOSK_DIR / f"{VOSK_MODEL}.zip.part"
        log.info("Скачиваю модель озвучки Vosk (~750 МБ, один раз)…")
        try:
            urllib.request.urlretrieve(url, tmp)
            with zipfile.ZipFile(tmp) as z:
                z.extractall(VOSK_DIR)
        except Exception as exc:  # noqa: BLE001
            raise ShortsError(f"Не удалось скачать модель Vosk: {exc}\nСкачайте вручную {url} "
                              f"и распакуйте в {VOSK_DIR}") from exc
        finally:
            tmp.unlink(missing_ok=True)
        return path

    def synth(self, text: str, out: Path, rate: float = 1.0) -> tuple[np.ndarray, list[float]]:
        audio = self.synth_.synth_audio(text, speaker_id=self.sid, speech_rate=self.speed * rate)
        x = np.asarray(audio)
        x = x.astype(np.float32) / 32768 if x.dtype == np.int16 else x.astype(np.float32)
        x = _resample(x, 22050)
        _write_wav(out, x)
        return x, [_syllable_weight(w) for w in text.split()]


def _syllable_weight(word: str) -> float:
    """Длительность слова ~ число слогов (гласных) + паузы у знаков препинания."""
    vowels = len(re.findall(r"[аеёиоуыэюяaeiouy]", word.lower()))
    letters = len(re.sub(r"[^\wёЁ]", "", word))
    pause = 2.0 if re.search(r"[,;:—]$", word) else (3.0 if re.search(r"[.!?…]$", word) else 0.0)
    return max(0.6, vowels + letters * 0.12) + pause


def _movavg(x: np.ndarray, n: int) -> np.ndarray:
    c = np.cumsum(np.concatenate([[0.0], x]))
    out = (c[n:] - c[:-n]) / n
    return np.pad(out, (n // 2, len(x) - len(out) - n // 2), mode="edge")


def polish(x: np.ndarray, sr: int = SR) -> np.ndarray:
    """Обработка голоса как в студии: срез гула, теплота, «присутствие», компрессия, лёгкая комната."""
    from scipy.signal import butter, sosfilt
    if len(x) < sr // 10:
        return x
    y = sosfilt(butter(2, 80, "high", fs=sr, output="sos"), x)
    # мягкий низ (теплота) и подъём разборчивости 2–5 кГц
    low = sosfilt(butter(2, [120, 300], "band", fs=sr, output="sos"), y)
    pres = sosfilt(butter(2, [2200, 5000], "band", fs=sr, output="sos"), y)
    y = y + low * 0.25 + pres * 0.35
    # лёгкий де-эссер: приглушаем резкие «с/ш» выше 6 кГц, когда их много
    hi = sosfilt(butter(2, 6000, "high", fs=sr, output="sos"), y)
    hop = int(sr * 0.01)
    env_hi = np.sqrt(_movavg(hi ** 2, hop)) + 1e-6
    env_all = np.sqrt(_movavg(y ** 2, hop)) + 1e-6
    y = y - hi * np.clip((env_hi / env_all - 0.35) * 1.5, 0, 0.6)
    # компрессор (RMS, 3:1 выше -20 dBFS), чтобы голос звучал ровно и «в лицо»
    rms = np.sqrt(_movavg(y ** 2, hop * 3)) + 1e-9
    db = 20 * np.log10(rms)
    gain_db = np.where(db > -20, (-20 - db) * (1 - 1 / 3), 0.0)
    gain = 10 ** (_movavg(gain_db, hop * 2) / 20)
    y = y * gain
    # очень лёгкая «комната» (ранние отражения), чтобы голос не был сухим
    for d_ms, g in ((11, 0.10), (23, 0.07), (37, 0.05)):
        d = int(sr * d_ms / 1000)
        y[d:] += y[:-d] * g
    return (y / (np.max(np.abs(y)) + 1e-9) * 0.9).astype(np.float32)


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

    def synth(self, text: str, out: Path, rate: float = 1.0) -> tuple[np.ndarray, list[float]]:
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
    if v.provider == "vosk":
        try:
            return VoskTTS(str(v.vosk_voice), float(v.speed))
        except ShortsError as exc:
            log.warning("%s — переключаюсь на Piper", exc)
            return PiperTTS(v.piper_voice, float(v.speed))
    if v.provider == "piper":
        return PiperTTS(v.piper_voice, float(v.speed))
    if v.provider == "elevenlabs":
        return ElevenLabsTTS(v.elevenlabs_voice_id, v.elevenlabs_model)
    raise ShortsError(f"Неизвестный voice.provider: {v.provider} (vosk | piper | elevenlabs)")


def voice_script(script, cfg, work: Path) -> np.ndarray:
    """Озвучивает все сцены, заполняет scene.start/end/words. Возвращает общую дорожку голоса."""
    work.mkdir(parents=True, exist_ok=True)
    engine = make_engine(cfg)
    aligner = WhisperAligner(str(cfg.voice.align_with_whisper))
    pause = float(cfg.voice.sentence_pause)
    dramatic = bool(cfg.voice.get("dramatic_pacing", True))
    do_polish = bool(cfg.voice.get("polish", True))
    lead = 0.15
    parts, t = [np.zeros(int(lead * SR), np.float32)], lead
    n = len(script.scenes)
    for i, sc in enumerate(script.scenes):
        path = work / f"voice_{i:02d}.wav"
        rate = 1.0
        if dramatic:
            # темп по эмоции: волнение быстрее, раздумье и грусть медленнее, финал — весомее
            rate = {"excited": 1.06, "scared": 1.05, "surprised": 1.03, "sad": 0.94,
                    "thinking": 0.96}.get(sc.character_emotion or "", 1.0)
            if i == n - 1:
                rate *= 0.94
        x, weights = engine.synth(sc.text, path, rate)
        if do_polish:
            x = polish(x)
            _write_wav(path, x)
        words = proportional_words(sc.text, weights, x, SR, t)
        words = aligner.refine(words, x, SR, t)
        sc.start, sc.end, sc.audio, sc.words = t, t + len(x) / SR, str(path), words
        gap = pause if i < n - 1 else 0.6
        if dramatic and i < n - 1:
            if i == 0:
                gap += 0.2             # пауза после хука
            if i == n - 2:
                gap += 0.35            # пауза перед развязкой
            if sc.text.rstrip().endswith("?"):
                gap += 0.15            # дать вопросу «повиснуть»
        parts += [x, np.zeros(int(gap * SR), np.float32)]
        t = sc.end + gap
        log.info("  сцена %d: %.1f с — %s", i + 1, sc.end - sc.start, sc.text[:60])
    # сцена длится до начала следующей
    for a, b in zip(script.scenes, script.scenes[1:]):
        a.end = b.start
    script.scenes[0].start = 0.0
    script.scenes[-1].end = t
    return np.concatenate(parts)
