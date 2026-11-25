"""Этап 5 — проверка качества final_video.mp4.

Длительность 8–10 мин, параметры потока (1920x1080, 30 fps, H.264, AAC), отсутствие чёрных/пустых
участков (blackdetect), громкость и пики (без клиппинга), полное декодирование без ошибок,
совпадение текста субтитров со сценарием, 6 контрольных скриншотов в build/qa/.
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VIDEO = ROOT / "final_video.mp4"
OUT = ROOT / "build" / "qa"


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report, ok = [], True
    pr = json.loads(sh(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(VIDEO)]).stdout)
    v = next(s for s in pr["streams"] if s["codec_type"] == "video")
    a = next(s for s in pr["streams"] if s["codec_type"] == "audio")
    dur = float(pr["format"]["duration"])
    fps = eval(v["r_frame_rate"])  # noqa: S307 - строка вида "30/1" из ffprobe
    checks = [
        ("длительность 8–10 мин", 480 <= dur <= 600, f"{dur:.1f} с ({int(dur // 60)}:{int(dur % 60):02d})"),
        ("1920x1080", (v["width"], v["height"]) == (1920, 1080), f"{v['width']}x{v['height']}"),
        ("30 fps", abs(fps - 30) < 0.01, f"{fps:g}"),
        ("H.264 yuv420p", v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p", f"{v['codec_name']} {v['pix_fmt']}"),
        ("AAC", a["codec_name"] == "aac", f"{a['codec_name']} {a.get('sample_rate')} Гц {a.get('channels')} кан."),
        ("звук не короче видео", abs(float(a.get("duration", dur)) - float(v.get("duration", dur))) < 0.5,
         f"видео {float(v.get('duration', 0)):.2f} / звук {float(a.get('duration', 0)):.2f}"),
    ]
    # чёрные кадры (кроме финального затемнения последней секунды)
    bd = sh(["ffmpeg", "-hide_banner", "-i", str(VIDEO), "-vf", "blackdetect=d=0.3:pix_th=0.06", "-an", "-f", "null", "-"]).stderr
    blacks = [(float(s), float(e)) for s, e in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", bd)]
    blacks = [b for b in blacks if b[0] < dur - 1.2]
    checks.append(("нет чёрных кадров", not blacks, str(blacks) if blacks else "нет"))
    # застывшие/пустые участки: freezedetect (кадр не меняется > 4 с)
    fz = sh(["ffmpeg", "-hide_banner", "-i", str(VIDEO), "-vf", "freezedetect=n=0.0005:d=4", "-an", "-f", "null", "-"]).stderr
    freezes = re.findall(r"freeze_start: ([\d.]+)", fz)
    freezes = [float(x) for x in freezes if float(x) < dur - 17]  # конечная заставка может стоять
    checks.append(("нет застывших участков > 4 с", not freezes, str(freezes) if freezes else "нет"))
    # громкость и пики
    eb = sh(["ffmpeg", "-hide_banner", "-i", str(VIDEO), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr
    i_lufs = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", eb)[-1])
    peak = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", eb)[-1])
    checks.append(("громкость около −16 LUFS", -17.5 <= i_lufs <= -13.5, f"{i_lufs} LUFS"))
    checks.append(("без клиппинга (true peak < −1 dBFS)", peak < -1.0, f"{peak} dBFS"))
    # полное декодирование
    dec = sh(["ffmpeg", "-v", "error", "-i", str(VIDEO), "-f", "null", "-"]).stderr.strip()
    checks.append(("декодируется без ошибок", not dec, dec[:200] or "ок"))
    # субтитры = сценарий
    srt = (ROOT / "subtitles.srt").read_text(encoding="utf-8")
    srt_words = " ".join(l for l in srt.splitlines() if l and not l.isdigit() and "-->" not in l).split()
    script_words = (ROOT / "script_voiceover.txt").read_text(encoding="utf-8").split()
    checks.append(("субтитры совпадают со сценарием", srt_words == script_words,
                   f"{len(srt_words)} / {len(script_words)} слов"))
    last_end = max(float(m[0]) * 3600 + float(m[1]) * 60 + float(m[2].replace(",", "."))
                   for m in re.findall(r"--> (\d+):(\d+):([\d,]+)", srt))
    checks.append(("субтитры не выходят за конец видео", last_end <= dur, f"последний {last_end:.1f} с"))
    for name, good, info in checks:
        ok &= bool(good)
        report.append(f"{'OK ' if good else 'FAIL'} {name}: {info}")
    # 6 скриншотов по всей длине
    for k, t in enumerate([12, dur * 0.18, dur * 0.36, dur * 0.55, dur * 0.74, dur - 10]):
        sh(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(VIDEO), "-frames:v", "1", "-q:v", "3",
            str(OUT / f"screen_{k + 1}_{int(t // 60)}m{int(t % 60):02d}s.jpg")])
    (OUT / "report.txt").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print("ИТОГ:", "всё в порядке" if ok else "есть проблемы")
    return ok


if __name__ == "__main__":
    main()
