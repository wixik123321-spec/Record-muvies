"""Find tempo and beat times of a music track, so cuts can land on the beat (ads, montages, music videos).

Usage: python -I music_beats.py <music> [--start 0] [--dur 60] [--json out.json]
Prints BPM, the first beat, the beat interval and a cut grid (every beat, every 2 and every 4 beats = one bar in 4/4).
Method: onset strength (spectral flux, 23 ms hops) -> tempo by autocorrelation (70-180 BPM) -> beat phase that best
lines up with the onsets. Good on steady pop/electronic/acoustic beds; rubato or ambient tracks have no reliable grid
(the script says so when the peak is weak). Claude cannot hear: check one cut against the waveform or ask the user.
"""
import argparse, json, subprocess, sys
import numpy as np

SR, HOP, NFFT = 22050, 512, 2048


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("music"); ap.add_argument("--start", type=float, default=0); ap.add_argument("--dur", type=float, default=60)
    ap.add_argument("--json")
    a = ap.parse_args()
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(a.start), "-t", str(a.dur), "-i", a.music, "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    if len(x) < SR * 5: sys.exit("need at least 5 s of audio")
    n = 1 + (len(x) - NFFT) // HOP; win = np.hanning(NFFT)
    frames = np.lib.stride_tricks.as_strided(x, (n, NFFT), (x.strides[0] * HOP, x.strides[0])) * win
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(axis=1); flux = flux - np.convolve(flux, np.ones(16) / 16, "same"); flux = np.maximum(flux, 0)
    fps = SR / HOP
    ac = np.correlate(flux, flux, "full")[len(flux) - 1:]; lags = np.arange(len(ac)) / fps
    ok = (lags >= 60 / 180) & (lags <= 60 / 70)
    k = np.argmax(np.where(ok, ac, 0)); period = lags[k]
    # refine to a fractional lag by parabolic fit
    if 0 < k < len(ac) - 1:
        y0, y1, y2 = ac[k - 1], ac[k], ac[k + 1]; period = (k + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2 + 1e-9)) / fps
    strength = ac[k] / (np.median(ac[ok]) + 1e-9)
    step = period * fps; best, phase = -1, 0
    for ph in np.arange(0, step, 0.5):
        idx = (ph + np.arange(0, len(flux) - ph, step)).astype(int); sc = flux[idx].sum()
        if sc > best: best, phase = sc, ph
    first = a.start + phase / fps + HOP / SR
    beats = [round(first + i * period, 3) for i in range(int((a.dur - (first - a.start)) / period) + 1)]
    bpm = 60 / period
    print(f"{bpm:.1f} BPM, beat every {period:.3f} s, first beat {first:.3f} s, peak strength {strength:.1f}"
          + ("  (weak: no steady beat, do not cut to a grid)" if strength < 1.6 else ""))
    print("every beat :", " ".join(f"{b:.2f}" for b in beats[:16]), "...")
    print("every 2    :", " ".join(f"{b:.2f}" for b in beats[::2][:12]), "...")
    print("every bar  :", " ".join(f"{b:.2f}" for b in beats[::4][:12]), "...")
    if a.json: json.dump({"bpm": round(bpm, 2), "period": round(period, 4), "first": first, "strength": round(float(strength), 2), "beats": beats},
                         open(a.json, "w"), indent=1)
