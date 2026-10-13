#!/usr/bin/env python3
"""Deconstruct a reference video into its editing structure.

Produces five things:
  meta.txt        resolution, fps, duration, codecs
  sheet.jpg       contact sheet of the whole film — read this first
  frames/*.jpg    high-res stills at even intervals for close reading
  loudness.txt    per-interval RMS in dB, plus detected transients
  cuts.txt        every frame's scene score + mean luma, and the classified cuts:
                  HARD CUT  = big scene change AND a luma jump (a real edit)
                  CONTENT   = big scene change, luma steady (decode/scramble, a
                              fast animation — not an edit decision)

Two lessons this script encodes (each cost a wrong conclusion once):
  1. A detector that returns 0 must prove it read data. ffmpeg's metadata=print
     with -v error silently prints nothing; "no cuts" was really "no data". The
     script checks that it received a score for ~every frame and stops if not.
  2. Only hard cuts are editing decisions. Peaks of the frame-difference curve
     are by-products of animation; do beat-alignment statistics on hard cuts only,
     with a tolerance far below half the grid spacing (±0.03 s), and compare
     against the random expectation before believing a "match".

Copying more hard cuts than the reference has is the most common way a homage
ends up feeling busy.

Usage:
    ~/.aaaai-editor/bin/aaaai-editor-python analyze_reference.py ref.mp4 --out /tmp/ref
    ~/.aaaai-editor/bin/aaaai-editor-python analyze_reference.py ref.mp4 --out /tmp/ref --fps 6 --cols 6
"""
import argparse
import glob
import math
import os
import shlex
import subprocess


def _resolve_ffmpeg():
    """$AAAAI_EDITOR_FFMPEG -> ffmpeg-full (Apple Silicon) -> ffmpeg-full (Intel) -> PATH."""
    import os, shutil
    for c in (os.environ.get("AAAAI_EDITOR_FFMPEG"),
              "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
              "/usr/local/opt/ffmpeg-full/bin/ffmpeg"):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return shutil.which("ffmpeg") or "ffmpeg"


def _sibling_ffprobe(ff):
    import os, shutil
    p = os.path.join(os.path.dirname(ff), "ffprobe")
    if os.path.dirname(ff) and os.access(p, os.X_OK):
        return p
    return shutil.which("ffprobe") or "ffprobe"


FFMPEG = _resolve_ffmpeg()
FFPROBE = _sibling_ffprobe(FFMPEG)


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def probe(video, out):
    q = (f"{shlex.quote(FFPROBE)} -v error -show_entries "
         "format=duration,size,bit_rate:stream=index,codec_type,codec_name,"
         "width,height,r_frame_rate,channels,sample_rate "
         f"-of default=noprint_wrappers=0 '{video}'")
    r = sh(q)
    with open(os.path.join(out, "meta.txt"), "w") as f:
        f.write(r.stdout)
    print(r.stdout.strip())
    dur = 0.0
    for line in r.stdout.splitlines():
        if line.startswith("duration=") and line.split("=")[1] not in ("N/A", ""):
            dur = max(dur, float(line.split("=")[1]))
    return dur


def contact_sheet(video, out, fps, cols):
    fdir = os.path.join(out, "grid")
    os.makedirs(fdir, exist_ok=True)
    for p in glob.glob(f"{fdir}/*.jpg"):
        os.remove(p)
    sh(f"{shlex.quote(FFMPEG)} -v error -i '{video}' -vf fps={fps} -q:v 4 '{fdir}/g_%04d.jpg' -y")
    n = len(glob.glob(f"{fdir}/*.jpg"))
    if not n:
        print("no frames extracted")
        return
    rows = math.ceil(n / cols)
    sheet = os.path.join(out, "sheet.jpg")
    sh(f"{shlex.quote(FFMPEG)} -v error -pattern_type glob -i '{fdir}/*.jpg' "
       f"-vf 'scale=420:-1,tile={cols}x{rows}' -q:v 3 '{sheet}' -y")
    print(f"contact sheet: {sheet}  ({n} frames, {cols}x{rows})")


def stills(video, out, dur, count):
    sdir = os.path.join(out, "frames")
    os.makedirs(sdir, exist_ok=True)
    for i in range(count):
        t = dur * (i + 0.5) / count
        sh(f"{shlex.quote(FFMPEG)} -v error -ss {t:.3f} -i '{video}' -frames:v 1 -q:v 2 "
           f"'{sdir}/t_{t:06.2f}.jpg' -y")
    print(f"{count} high-res stills: {sdir}")


def loudness(video, out, step):
    """Per-interval RMS, with a simple transient flag."""
    wav = os.path.join(out, "_audio.wav")
    r = sh(f"{shlex.quote(FFMPEG)} -v error -i '{video}' -vn -ac 1 -ar 48000 -f wav '{wav}' -y")
    if not os.path.exists(wav):
        print("no audio track")
        return
    try:
        import numpy as np
        import wave
        with wave.open(wav) as w:
            sr = w.getframerate()
            a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2") / 32768.0
    except Exception as e:                                   # pragma: no cover
        print("could not read audio:", e)
        return

    hop = int(sr * step)
    rows, prev = [], None
    for i in range(0, len(a) - 1, hop):
        seg = a[i:i + hop]
        rms = float((seg ** 2).mean() ** 0.5) if len(seg) else 0.0
        db = 20 * math.log10(rms) if rms > 1e-6 else -120.0
        jump = (db - prev) if prev is not None else 0.0
        rows.append((i / sr, db, jump))
        prev = db

    peak = max((j for _, _, j in rows), default=0.0)
    lines = ["    t      dB     delta"]
    for t, db, j in rows:
        mark = "   <-- TRANSIENT" if j > max(8.0, peak * 0.55) else ""
        lines.append(f"{t:6.2f}  {db:7.2f}  {j:+6.2f}{mark}")
    txt = "\n".join(lines)
    with open(os.path.join(out, "loudness.txt"), "w") as f:
        f.write(txt + "\n")
    os.remove(wav)
    print("\n".join(lines[:1] + [l for l in lines if "TRANSIENT" in l]))
    print(f"full table: {os.path.join(out, 'loudness.txt')}")


def cuts(video, out, fps):
    """Per-frame scene score (validated) + luma; classify hard cuts vs content changes."""
    import re
    import numpy as np
    p = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-i", video, "-filter_complex",
                        "select='gte(scene,0)',metadata=print:file=-", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    scores, t = [], None
    for line in p.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
        m = re.search(r"scene_score=([\d.]+)", line)
        if m and t is not None:
            scores.append((t, float(m.group(1))))
    raw = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-i", video, "-vf", "scale=64:36:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    luma = np.frombuffer(raw, np.uint8).reshape(-1, 36 * 64).mean(1) if raw else np.zeros(0)
    n = len(luma)
    print(f"[check] {len(scores)} scene scores received for {n} frames")
    if not scores or (n and len(scores) < 0.9 * n):
        print("[!] the scene-score pipe returned too little data — this is a silent failure, not 'no cuts'")
        return
    rows, hard, content = [], [], []
    for i, (tt, sc) in enumerate(scores):
        dl = abs(float(luma[i]) - float(luma[i - 1])) if 0 < i < n else 0.0
        kind = ""
        if sc >= 0.1:
            kind = "HARD CUT" if dl > 12 or sc > 0.5 else "CONTENT"
            (hard if kind == "HARD CUT" else content).append(tt)
        rows.append(f"{tt:8.3f}  score {sc:.4f}  luma {float(luma[i]) if i < n else 0:6.1f}  dL {dl:6.1f}  {kind}")
    with open(os.path.join(out, "cuts.txt"), "w") as f:
        f.write("\n".join(rows) + "\n")
    if n:
        print(f"mean luma {luma.mean():.1f}/255, range {luma.min():.1f}–{luma.max():.1f}")
    print(f"hard cuts: {len(hard)}  " + " ".join(f"{x:.3f}" for x in hard[:40]))
    if content:
        print(f"content changes (not edits): {len(content)}  " + " ".join(f"{x:.3f}" for x in content[:20]))
    print(f"full table: {os.path.join(out, 'cuts.txt')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="/tmp/ref")
    ap.add_argument("--fps", type=float, default=4.0,
                    help="sampling rate for the contact sheet")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--stills", type=int, default=12)
    ap.add_argument("--step", type=float, default=0.5,
                    help="loudness interval in seconds")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    dur = probe(a.video, a.out)
    contact_sheet(a.video, a.out, a.fps, a.cols)
    if dur:
        stills(a.video, a.out, dur, a.stills)
    loudness(a.video, a.out, a.step)
    cuts(a.video, a.out, a.fps)

    print("\nNext: open sheet.jpg, write the segment boundaries in seconds, and")
    print("name each segment. Compare the hard cuts with the transients: whether a film")
    print("locks its cuts to the beat is a per-film choice — measure it, don't assume it.")
