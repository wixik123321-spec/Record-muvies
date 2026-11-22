"""Офлайн-тесты: python -m pytest tests (или python tests/test_pipeline.py).

Не нужны ключи API: используется готовый сценарий и голос Piper.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shorts_ru.captions import build_phrases  # noqa: E402
from shorts_ru.models import Script  # noqa: E402
from shorts_ru.writer import script_from_text, split_sentences  # noqa: E402

TEXT = ("Знаете, почему кошки мурлычут? Учёные долго спорили об этом. Есть гипотеза, что мурчание "
        "помогает им заживлять кости, а частота звука совпадает с частотой, на которой растёт "
        "костная ткань. Но самое удивительное впереди! Кошки мурлычут даже тогда, когда им страшно.")


def test_split_and_plan():
    sents = split_sentences(TEXT)
    assert len(sents) >= 5 and all(len(s.split()) <= 16 for s in sents)
    sc = script_from_text(TEXT)
    assert sc.scenes[0].props and sc.scenes[0].props[0] == "question"
    assert sc.scenes[-1].sfx == "boom"


def test_example_script_loads():
    sc = Script.load(ROOT / "examples" / "octopus.json")
    assert len(sc.scenes) == 12 and sc.mood == "mystery"


def test_phrases_keep_script_text():
    sc = script_from_text(TEXT)
    t = 0.0
    for s in sc.scenes:
        s.words = []
        for w in s.text.split():
            s.words.append({"w": w, "s": t, "e": t + 0.3})
            t += 0.35
    phrases = build_phrases(sc.scenes, 3, 18)
    joined = " ".join(w["w"] for p in phrases for w in p.words)
    assert joined == " ".join(s.text for s in sc.scenes)
    assert all(len(p.words) <= 3 for p in phrases)


def test_render_short_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run([sys.executable, "-m", "shorts_ru", "--text", TEXT + " " + TEXT, "-d", "30",
                            "-o", d, "--name", "test"], cwd=ROOT, capture_output=True, text=True, timeout=1800)
        assert r.returncode == 0, r.stderr[-2000:]
        out = Path(d) / "test.mp4"
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
                                          "-show_format", str(out)], capture_output=True, text=True).stdout)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        assert (v["width"], v["height"]) == (1080, 1920)
        assert 25 <= float(info["format"]["duration"]) <= 62
        assert (Path(d) / "test_work" / "test.srt").exists()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
