#!/usr/bin/env python3
"""Real music → the film's grid. Use a licensed track (the user's file, the
HeyGen music library via hyperframes:media-use, or the suite's bgm library)
instead of synthesising one, and let its actual beats drive the anchors.

  analyze  song.mp3 --out beats.json
           tempo, every beat, bar downbeats, section changes, drops (energy
           jumps), and whether the song has a natural ending
  fit      song.mp3 --dur 24 [--drop-at 9.5] --out score.wav --grid grid.json
           picks where in the song to start (always a downbeat) so that the
           film ends on the song's natural end or a phrase boundary, and the
           film's big moment (--drop-at, film seconds) lands on a real drop;
           cuts that span, loudness-matches it (-14 LUFS, -1 dBTP), and writes
           grid.json + a `const MUSIC = {...}` line to paste at the top of the
           scene so T's anchors sit on the song's real bars.
           The film length may flex by up to --flex bars to finish with the
           song instead of fading — the new length is printed; use it as DUR.

Anchors (the 3–5 hard moments) go on MUSIC.bars / MUSIC.drops; everything else
stays content-timed (SKILL §5.2). Beat analysis ported from
afterevent-movie-editor/scripts/score.py (Ellis DP beat tracking + least-squares
grid fit), verified there on real songs.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from scipy import signal


def _ff(name):
    for c in (os.environ.get("AAAAI_EDITOR_FFMPEG"), "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
              "/usr/local/opt/ffmpeg-full/bin/ffmpeg"):
        if c and os.path.isfile(c):
            p = os.path.join(os.path.dirname(c), name)
            if os.path.isfile(p):
                return p
    return shutil.which(name) or name


FFMPEG = _ff("ffmpeg")


# ================================================================ analysis
def load_mono(path, sr=22050):
    r = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True)
    if not r.stdout:
        raise SystemExit("could not decode %s" % path)
    return np.frombuffer(r.stdout, dtype=np.float32).copy(), sr


def onset_env(x, sr, hop=256, n_fft=2048):
    f, _t, Z = signal.stft(x, sr, nperseg=n_fft, noverlap=n_fft - hop, boundary=None, padded=False)
    S = np.log1p(100 * np.abs(Z))
    flux = np.maximum(0, np.diff(S, axis=1)).sum(0)
    low = np.maximum(0, np.diff(S[f < 200], axis=1)).sum(0)          # kick energy: finds the downbeat
    flux = np.concatenate([[0], flux]); low = np.concatenate([[0], low])
    flux -= signal.medfilt(flux, 31) if len(flux) > 31 else 0
    flux = np.maximum(flux, 0)
    return flux / (flux.max() + 1e-9), low / (low.max() + 1e-9), sr / hop


def tempo(env, fr, lo=70, hi=180):
    """Autocorrelation tempo using the 1–4× beat-lag peaks, then a fine sweep."""
    # FFT autocorrelation: np.correlate is O(n²) — a 6-minute song took minutes
    n2 = 1 << int(np.ceil(np.log2(2 * len(env))))
    F = np.fft.rfft(env, n2)
    ac = np.fft.irfft(F * np.conj(F), n2)[:len(env)]
    ac = ac / (ac[0] + 1e-9)

    def val(lag):
        i = int(lag)
        if i + 1 >= len(ac):
            return 0.0
        f = lag - i
        return ac[i] * (1 - f) + ac[i + 1] * f

    def score(b):
        lag = 60 * fr / b
        v = sum(val(k * lag) / k ** 0.5 for k in (1, 2, 3, 4))
        return v * np.exp(-0.5 * (np.log2(b / 118.0) / 0.9) ** 2)    # prefer common tempi (no half/double)

    grid = np.arange(lo, hi, 0.5)
    b0 = grid[int(np.argmax([score(b) for b in grid]))]
    fine = np.arange(b0 - 1.0, b0 + 1.0, 0.02)
    return float(fine[int(np.argmax([score(b) for b in fine]))])


def track_beats(env, fr, bpm, tight=100.0):
    """Ellis dynamic-programming beat tracker."""
    period = 60 * fr / bpm
    n = len(env)
    score = env.copy()
    back = -np.ones(n, int)
    lo, hi = int(round(period * 0.5)), int(round(period * 2))
    for i in range(hi, n):
        prev = np.arange(i - hi, i - lo)
        cost = -tight * np.log((i - prev) / period) ** 2
        k = np.argmax(score[prev] + cost)
        score[i] = env[i] + score[prev][k] + cost[k]
        back[i] = prev[k]
    i = int(np.argmax(score[-int(period * 2):])) + n - int(period * 2)
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    return np.array(beats[::-1]) / fr


def analyze(path):
    x, sr = load_mono(path)
    env, low, fr = onset_env(x, sr)
    bpm = tempo(env, fr)
    beats = track_beats(env, fr, bpm) + 2048 / 2 / sr        # STFT frames are centred
    if len(beats) > 8:                                       # least-squares tempo + phase
        k = np.round((beats - beats[0]) / (60.0 / bpm))
        slope, icpt = np.polyfit(k, beats, 1)
        bpm = 60.0 / slope
        resid = beats - (icpt + slope * k)
        if np.abs(resid).max() < 0.06:                       # steady song: use the clean grid
            beats = icpt + slope * np.arange(int(k.max()) + 1)
            beats = beats[beats >= 0]
    idx = np.clip(((beats - 2048 / 2 / sr) * fr).astype(int), 0, len(low) - 1)
    phase = int(np.argmax([low[idx[p::4]].sum() for p in range(4)])) if len(idx) >= 8 else 0
    downs = beats[phase::4]
    bars_t = list(downs) + [len(x) / sr]
    bar_db = []
    for a_, b_ in zip(bars_t[:-1], bars_t[1:]):
        seg = x[int(a_ * sr):int(b_ * sr)]
        bar_db.append(float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-7)) if len(seg) else -90.0)
    bar_db = np.array(bar_db)
    sections = []
    for b in range(2, len(bar_db) - 2):
        before = bar_db[max(0, b - 4):b].mean()
        after = bar_db[b:b + 4].mean()
        if abs(after - before) >= 3.0:
            sections.append((b, float(after - before)))
    sec = []
    for b, d in sections:                                    # one marker per change
        if sec and b - sec[-1][0] <= 2:
            if abs(d) > abs(sec[-1][1]):
                sec[-1] = (b, d)
        else:
            sec.append((b, d))
    med = float(np.median(bar_db)) if len(bar_db) else -30.0
    loud = [i for i, v in enumerate(bar_db) if v > med - 10]
    song_end = float(bars_t[loud[-1] + 1]) if loud else len(x) / sr
    natural = (len(x) / sr - song_end) < 6.0 and len(bar_db) > 8 and bar_db[-1] < med - 3
    return {"src": os.path.abspath(path), "bpm": round(bpm, 3), "beats": [round(float(b), 4) for b in beats],
            "downbeats": [round(float(b), 4) for b in downs],
            "sections": [round(float(downs[b]), 4) for b, _d in sec],
            "drops": [round(float(downs[b]), 4) for b, d in sec if d >= 4.0],
            "song_end": round(song_end, 3), "natural_end": bool(natural),
            "bar_db": [round(float(v), 1) for v in bar_db], "duration": round(len(x) / sr, 3)}


def choose_window(a, film_len, drop_at=None, flex_bars=2):
    """Start on a downbeat so the film ends with the song (natural end or phrase
    boundary) and the film's big moment lands on a drop; flex the length a little."""
    downs = a["downbeats"]
    beat = 60.0 / a["bpm"]
    flex = flex_bars * 4 * beat
    best = None
    for d in downs:
        end = d + film_len
        if end > a["duration"] + 0.05 and not a.get("natural_end"):
            break
        sc, mode, length = 0.0, "fade", film_len
        if a.get("natural_end") and abs((a["song_end"] - d) - film_len) <= flex:
            sc += 6.0; mode = "natural"
            length = a["song_end"] - d
        elif end > a["duration"] + 0.05:
            continue
        else:
            # snap the end to the nearest section boundary within the flex range
            cands = [t - d for t in a.get("sections", []) if abs((t - d) - film_len) <= flex]
            if cands:
                length = min(cands, key=lambda L: abs(L - film_len))
                sc += 3.5; mode = "phrase"
        hit = None
        inside = [x for x in a.get("drops") or [] if 0 <= x - d <= length]   # only drops this window plays
        if drop_at is not None and inside:
            target = drop_at * length / film_len
            hit = min(inside, key=lambda t: abs((t - d) - target)) - d - target
            sc += max(0.0, 3.0 - abs(hit) / beat)
        sc += 0.02 * (d < 60)
        sc -= 0.3 * abs(length - film_len) / (4 * beat)
        if best is None or sc > best[0]:
            best = (sc, d, mode, hit, length)
    if best is None:
        return {"start": downs[0] if downs else 0.0, "end_mode": "fade", "drop_hit": None, "length": film_len}
    return {"start": round(best[1], 4), "end_mode": best[2],
            "drop_hit": None if best[3] is None else round(best[3], 3), "length": round(best[4], 4)}


# ================================================================ fit
def loudnorm(src, dst, start, length, fade_in, fade_out, target=-14.0):
    af = "afade=t=in:st=0:d=%.3f,afade=t=out:st=%.3f:d=%.3f" % (fade_in, max(0.0, length - fade_out), fade_out)
    base = [FFMPEG, "-v", "error", "-ss", "%.4f" % start, "-t", "%.4f" % length, "-i", src]
    p = subprocess.run(base + ["-af", af + ",loudnorm=I=%g:TP=-1:LRA=11:print_format=json" % target,
                               "-f", "null", "-"], capture_output=True, text=True)
    m = p.stderr[p.stderr.rfind("{"):p.stderr.rfind("}") + 1]
    st = json.loads(m) if m else {}
    ln = "loudnorm=I=%g:TP=-1:LRA=11" % target
    if st:
        ln += (":measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true"
               % (st["input_i"], st["input_tp"], st["input_lra"], st["input_thresh"], st["target_offset"]))
    subprocess.run(base + ["-af", af + "," + ln + ",aresample=48000", "-ac", "2", "-c:a", "pcm_s16le",
                           "-t", "%.4f" % length, dst], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analyze"); p.add_argument("music"); p.add_argument("--out", default="beats.json")
    p = sub.add_parser("fit"); p.add_argument("music")
    p.add_argument("--dur", type=float, required=True, help="intended film length (s)")
    p.add_argument("--drop-at", type=float, help="film second of the big moment (burst / number lock)")
    p.add_argument("--flex", type=float, default=2, help="bars the length may stretch to end with the song")
    p.add_argument("--start", type=float, help="force the song start (s) instead of choosing")
    p.add_argument("--out", default="score.wav"); p.add_argument("--grid", default="grid.json")
    p.add_argument("--lufs", type=float, default=-14.0)
    a = ap.parse_args()

    an = analyze(a.music)
    if a.cmd == "analyze":
        with open(a.out, "w") as fh:
            json.dump(an, fh)
        print(f"[✓] {a.out}: {an['bpm']} BPM · {len(an['beats'])} beats · first bar at {an['downbeats'][0] if an['downbeats'] else 0}s")
        print(f"    {len(an['sections'])} section changes · {len(an['drops'])} drops · "
              + (f"natural ending at {an['song_end']}s" if an['natural_end'] else "no natural ending (file is cut off)"))
        return

    w = choose_window(an, a.dur, a.drop_at, a.flex)
    if a.start is not None:
        s0 = min(an["downbeats"], key=lambda d: abs(d - a.start)) if an["downbeats"] else a.start
        w = {"start": s0, "end_mode": "fade", "drop_hit": None, "length": a.dur}
    start, length, mode = w["start"], w["length"], w["end_mode"]
    beat = 60.0 / an["bpm"]
    fade_out = 0.05 if mode in ("natural", "phrase") else min(2.5, 4 * beat)
    loudnorm(an["src"], a.out, start, length, 0.012, fade_out, a.lufs)

    rel = lambda ts: [round(t - start, 4) for t in ts if 0 <= t - start <= length + 1e-3]
    grid = {"src": an["src"], "song_start": start, "dur": round(length, 4), "bpm": an["bpm"],
            "beat": round(beat, 5), "bar": round(4 * beat, 5), "end_mode": mode,
            "beats": rel(an["beats"]), "bars": rel(an["downbeats"]), "sections": rel(an["sections"]),
            "drops": rel(an["drops"])}
    with open(a.grid, "w") as fh:
        json.dump(grid, fh)
    js = {k: grid[k] for k in ("dur", "bpm", "beat", "bar", "bars", "drops", "sections")}
    print(f"[✓] {a.out}: song {start:.2f}s → {start + length:.2f}s, {an['bpm']:.1f} BPM, {a.lufs:g} LUFS")
    print(f"    ending: {dict(natural='the song’s own ending', phrase='a phrase boundary', fade='a fade over the last bar')[mode]}")
    if abs(length - a.dur) > 0.01:
        print(f"    ⚠ film length flexes {a.dur:g}s → {length:.3f}s to finish with the music: use DUR = {length:.3f}")
    if a.drop_at is not None:
        print("    big moment: " + ("no drop in this window" if w["drop_hit"] is None else
                                     f"nearest drop is {w['drop_hit']:+.2f}s from --drop-at → put the anchor ON the drop"))
    print(f"    bars at: {', '.join('%.2f' % b for b in grid['bars'][:16])}{' …' if len(grid['bars']) > 16 else ''}")
    if grid["drops"]:
        print(f"    drops at: {', '.join('%.2f' % d for d in grid['drops'])}")
    print("\npaste at the top of the scene (anchors → MUSIC.bars[i] / MUSIC.drops[0]):")
    print("const MUSIC = " + json.dumps(js) + ";")


if __name__ == "__main__":
    main()
