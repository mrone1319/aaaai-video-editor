#!/usr/bin/env python3
"""Side-by-side comparison sheet: the reference clip and our render at matching
moments, one row per timestamp — for the "compare against the reference and
adjust" pass (§3, §11).

  $PY compare_ref.py ref.mp4 ours.mp4 --every 2 --out tmp/compare.jpg
  $PY compare_ref.py ref.mp4 ours.mp4 --at 1.5,4,9.2 --map 1.1   # ours runs 10% longer
  $PY compare_ref.py ref.mp4 ours.mp4 --pairs 3.2:2.9,8:7.4       # explicit ref:ours pairs

--map scales reference time to ours (ours = ref × map + --offset), for films that
keep the structure but not the exact length. Rows are labelled with both times.
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont


def ff(name="ffmpeg"):
    for c in (os.environ.get("AAAAI_EDITOR_FFMPEG"), "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
              "/usr/local/opt/ffmpeg-full/bin/ffmpeg"):
        if c and os.path.isfile(c):
            p = os.path.join(os.path.dirname(c), name)
            if os.path.isfile(p):
                return p
    return shutil.which(name) or name


def duration(p):
    out = subprocess.run([ff("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", p],
                         capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


def grab(p, t, w, out):
    subprocess.run([ff(), "-v", "error", "-y", "-ss", "%.3f" % max(0.0, t), "-i", p, "-frames:v", "1",
                    "-vf", "scale=%d:-2" % w, out], check=True)
    return Image.open(out).convert("RGB")


def font(size):
    for fp in ("/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
               os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttc")):
        if os.path.isfile(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref"); ap.add_argument("ours")
    ap.add_argument("--every", type=float, default=0, help="a row every N seconds of the reference")
    ap.add_argument("--at", default="", help="reference seconds, comma-separated")
    ap.add_argument("--pairs", default="", help="explicit ref:ours pairs, e.g. 3.2:2.9,8:7.4")
    ap.add_argument("--map", type=float, default=1.0, help="ours time = ref time × map + offset")
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--width", type=int, default=640, help="width of each frame in the sheet")
    ap.add_argument("--out", default="compare.jpg")
    a = ap.parse_args()

    dr, do = duration(a.ref), duration(a.ours)
    if a.pairs:
        pairs = [tuple(float(x) for x in p.split(":")) for p in a.pairs.split(",") if p]
    else:
        ts = [float(x) for x in a.at.split(",") if x] if a.at else \
             [round(i * (a.every or 2.0), 3) for i in range(int(dr / (a.every or 2.0)) + 1)]
        pairs = [(t, t * a.map + a.offset) for t in ts if t < dr]
    pairs = [(r, min(o, do - 0.05)) for r, o in pairs]

    tmp = tempfile.mkdtemp()
    rows = []
    for i, (r, o) in enumerate(pairs):
        rows.append((r, o, grab(a.ref, r, a.width, os.path.join(tmp, "r%d.png" % i)),
                     grab(a.ours, o, a.width, os.path.join(tmp, "o%d.png" % i))))
    lab, pad = 34, 10
    rh = max(max(x[2].height, x[3].height) for x in rows)
    W, H = a.width * 2 + pad * 3, lab + len(rows) * (rh + pad + 26) + pad
    sheet = Image.new("RGB", (W, H), (20, 20, 22))
    d = ImageDraw.Draw(sheet)
    f, fs = font(20), font(16)
    d.text((pad, 6), "参考片", fill=(230, 230, 230), font=f)
    d.text((pad * 2 + a.width, 6), "我们的片", fill=(212, 255, 58), font=f)
    y = lab
    for r, o, ri, oi in rows:
        d.text((pad, y), "参考 %.2fs" % r, fill=(170, 170, 175), font=fs)
        d.text((pad * 2 + a.width, y), "我们 %.2fs" % o, fill=(170, 170, 175), font=fs)
        sheet.paste(ri, (pad, y + 22)); sheet.paste(oi, (pad * 2 + a.width, y + 22))
        y += rh + pad + 26
    sheet.save(a.out, quality=90)
    shutil.rmtree(tmp, ignore_errors=True)
    print("对照表：%s（%d 行；参考 %.1fs、我们 %.1fs）" % (a.out, len(rows), dr, do))


if __name__ == "__main__":
    main()
