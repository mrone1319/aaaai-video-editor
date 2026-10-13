#!/usr/bin/env python3
"""Motion audit of a rendered film: is it alive where it should be, still only
where it means to be, and readable?

    $PY check_motion.py film.mp4 [--scene scene.html --root .] [--out tmp/motion.png]

Reports (Chinese, for the user) and draws an energy chart:

  energy      mean frame-to-frame change per second — the film's real energy
              shape. Compare it with the shape the mode promises (§1: A/C need a
              breakdown before the drop, B breathes, D peaks on the number/CTA).
  dead time   runs longer than --dead seconds where almost nothing moves.
              Intended stills (poster frame, end board) are declared in the scene
              with MG.hold(a, b) and are not flagged.
  jumps       single-frame changes far above their neighbourhood that are not a
              declared MG.cut(t) — usually an element that pops on without easing.
  black       frames darker than a "black" hold should be (mean luma < 4) and
              the longest black run (a held frame over silence reads as a fault).
  text        with --scene (mg-kit.js loaded): the smallest visible text as a share
              of frame height, sampled every 0.5 s, and text outside the safe area.

Exit code 0 = no problems, 1 = problems found (still prints everything).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def ff(name="ffmpeg"):
    for c in (os.environ.get("AAAAI_EDITOR_FFMPEG"), "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
              "/usr/local/opt/ffmpeg-full/bin/ffmpeg"):
        if c and os.path.isfile(c):
            p = os.path.join(os.path.dirname(c), name)
            if os.path.isfile(p):
                return p
    return shutil.which(name) or name


def probe(path):
    out = subprocess.run([ff("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "json", path],
                         capture_output=True, text=True).stdout
    s = json.loads(out)["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(n) / float(d)


def frames_gray(path, w=160, h=90):
    raw = subprocess.run([ff(), "-v", "error", "-i", path, "-vf", f"scale={w}:{h}:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)


def runs(mask):
    out, st = [], None
    for i, v in enumerate(mask):
        if v and st is None:
            st = i
        elif not v and st is not None:
            out.append((st, i))
            st = None
    if st is not None:
        out.append((st, len(mask)))
    return out


def scene_info(scene, root, W, H, fps, dur, step=0.5):
    """Declared holds/cuts + text audit, by loading the scene in the renderer's browser."""
    sys.path.insert(0, HERE)
    import render_frames as R
    from playwright.sync_api import sync_playwright
    root = os.path.abspath(root or os.path.dirname(os.path.abspath(scene)))
    base, srv = R.serve(root)
    url = R.scene_url(base, root, scene, W, H, int(round(fps)), dur, "")
    info = {"holds": [], "cuts": [], "text": []}
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=R.BASE_ARGS + R.gpu_args())
        p = b.new_page(viewport={"width": W, "height": H})
        p.goto(url, wait_until="load")
        p.wait_for_function("window.__ready === true", timeout=45000)
        info["holds"] = p.evaluate("window.__holds || []")
        info["cuts"] = p.evaluate("window.__cuts || []")
        has_audit = p.evaluate("typeof window.__audit === 'function'")
        if has_audit:
            t = 0.0
            while t < dur:
                p.evaluate("(f)=>window.__render(f)", t * fps)
                a = p.evaluate("window.__audit(0.05)")
                info["text"].append((round(t, 2), a))
                t += step
        b.close()
    srv.shutdown()
    return info


def chart(sec, dead, jumps, holds, out, fps, n):
    from PIL import Image, ImageDraw, ImageFont
    W, H, pad = 1400, 360, 50
    im = Image.new("RGB", (W, H), (18, 18, 22))
    d = ImageDraw.Draw(im)
    font = None
    for fp in ("/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
               os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttc"),
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if os.path.isfile(fp):
            font = ImageFont.truetype(fp, 16)
            break
    font = font or ImageFont.load_default()
    dur = n / fps
    X = lambda t: pad + (W - 2 * pad) * t / max(dur, 1e-6)
    top = max(1.0, max(sec) * 1.15)
    Y = lambda v: H - pad - (H - 2 * pad) * min(v, top) / top
    for a, b in holds:
        d.rectangle([X(a), pad, X(b), H - pad], fill=(30, 46, 38))
    for a, b in dead:
        d.rectangle([X(a), pad, X(b), H - pad], fill=(70, 30, 30))
    pts = [(X(i + 0.5), Y(v)) for i, v in enumerate(sec)]
    for i, v in enumerate(sec):
        d.rectangle([X(i) + 2, Y(v), X(i + 1) - 2, H - pad], fill=(245, 184, 61))
    if len(pts) > 1:
        d.line(pts, fill=(255, 230, 170), width=2)
    for t, _v in jumps:
        d.line([X(t), pad, X(t), H - pad], fill=(90, 150, 255), width=2)
    d.line([pad, H - pad, W - pad, H - pad], fill=(120, 120, 130))
    for s in range(0, int(dur) + 1, max(1, int(dur // 14) or 1)):
        d.text((X(s) - 6, H - pad + 8), "%ds" % s, fill=(170, 170, 180), font=font)
    d.text((pad, 14), "每秒运动量（黄）· 死时间（红底）· 宣告的停留（绿底）· 突然跳变（蓝线）", fill=(220, 220, 225), font=font)
    im.save(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--scene", help="scene HTML (reads MG.hold/MG.cut and audits text sizes)")
    ap.add_argument("--root", help="folder served to the scene (default: its folder)")
    ap.add_argument("--out", help="energy chart PNG (default: next to the video)")
    ap.add_argument("--dead", type=float, default=2.0, help="flag stills longer than this (s)")
    ap.add_argument("--still", type=float, default=0.15, help="per-frame change below this counts as still")
    ap.add_argument("--min-text", type=float, default=0.022,
                    help="smallest readable text as a share of frame height (0.022 ≈ 24px at 1080)")
    a = ap.parse_args()

    W, H, fps = probe(a.video)
    g = frames_gray(a.video)
    n = len(g)
    dur = n / fps
    diff = np.abs(np.diff(g, axis=0)).mean((1, 2))
    luma = g.mean((1, 2))
    per = int(round(fps))
    sec = [float(diff[i * per:(i + 1) * per].mean()) for i in range(int(np.ceil(len(diff) / per)))]

    info = {"holds": [], "cuts": [], "text": []}
    if a.scene:
        try:
            info = scene_info(a.scene, a.root, W, H, fps, dur)
        except Exception as e:   # the motion part still works without the scene
            print("（场景检查跳过：%s）" % str(e).splitlines()[0][:120])
    holds = [(float(x), float(y)) for x, y in info["holds"]]
    cuts = [float(c) for c in info["cuts"]]

    problems = 0
    print("== 能量曲线（每秒平均变化量，0–255）")
    top = max(sec) or 1
    for i, v in enumerate(sec):
        print("  %3ds %5.2f %s" % (i, v, "█" * int(round(v / top * 40))))

    in_hold = lambda t0, t1: any(h0 - 0.1 <= t0 and t1 <= h1 + 0.1 for h0, h1 in holds)
    dead = []
    for s0, s1 in runs(diff < a.still):
        t0, t1 = (s0 + 1) / fps, (s1 + 1) / fps
        if t1 - t0 >= a.dead and not in_hold(t0, t1):
            dead.append((t0, t1))
    still_share = float((diff < a.still).mean())
    print("\n== 死时间（超过 %.1f 秒几乎不动，且不是 MG.hold 宣告的停留）" % a.dead)
    print("  几乎静止的帧占 %.0f%%" % (still_share * 100))
    for t0, t1 in dead:
        print("  ⚠️ %.2f–%.2f 秒（%.1f 秒）" % (t0, t1, t1 - t0))
    problems += len(dead)
    if not dead:
        print("  ✅ 没有")

    jumps = []
    k = max(3, int(fps / 4))
    for i in range(k, len(diff) - k):
        m = float(np.median(np.r_[diff[i - k:i], diff[i + 1:i + 1 + k]])) + 0.05
        t = (i + 1) / fps
        if diff[i] > 6 * m and diff[i] > 3.0 and not any(abs(t - c) <= 1.5 / fps for c in cuts):
            jumps.append((round(t, 3), round(float(diff[i]), 1)))
    print("\n== 突然跳变（不是 MG.cut 宣告的硬切：多半是元素没有缓动就跳出来）")
    for t, v in jumps:
        print("  ⚠️ %.3f 秒（第 %d 帧，变化 %.1f）" % (t, int(round(t * fps)), v))
    problems += len(jumps)
    if not jumps:
        print("  ✅ 没有")

    print("\n== 黑场")
    dark = runs(luma < 4.0)
    longest = max([(b - s) / fps for s, b in dark] or [0])
    print("  全黑（亮度 < 4）帧 %d 个，最长连续 %.2f 秒" % (sum(b - s for s, b in dark), longest))
    if longest > 1.0:
        print("  ⚠️ 超过 1 秒的全黑：静音下读作事故；呼吸黑场应保持亮度 5–12（不是 0）")
        problems += 1

    if info["text"]:
        print("\n== 文字（每 0.5 秒取样）")
        small = [(t, x["minText"], x["minTextSample"]) for t, x in info["text"]
                 if x.get("minText") is not None and x["minText"] < a.min_text]
        outside = sorted({s for _t, x in info["text"] for s in x.get("outside") or []})
        mins = [x["minText"] for _t, x in info["text"] if x.get("minText") is not None]
        if mins:
            print("  最小字号：画面高度的 %.1f%%（约 %.0fpx）" % (min(mins) * 100, min(mins) * H))
        seen = set()
        for t, v, s in small:
            if s in seen:
                continue
            seen.add(s)
            print("  ⚠️ %.1f 秒「%s」只有画面高度的 %.1f%%（约 %.0fpx，建议 ≥ %.1f%%）" % (t, s, v * 100, v * H, a.min_text * 100))
        problems += len(seen)
        for s in outside:
            print("  ⚠️ 超出 5%% 安全边：「%s」" % s)
        problems += len(outside)
        if not small and not outside:
            print("  ✅ 字够大、都在安全区内")

    out = a.out or os.path.splitext(a.video)[0] + "_motion.png"
    chart(sec, dead, jumps, holds, out, fps, n)
    print("\n📈 能量图：%s" % out)
    print("结论：%s" % ("✅ 没有问题" if not problems else "⚠️ %d 处要看" % problems))
    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()
