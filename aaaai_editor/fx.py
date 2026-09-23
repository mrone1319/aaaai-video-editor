"""动态素材：星空跃迁背景、激光扫光。纯 Python 逐帧生成，按参数缓存，只算一次。"""
from __future__ import annotations

import hashlib
import math
import os
import random
import subprocess
from typing import Tuple

from . import env
from .draw import _halfspan, hex_rgb
from .png import write_rgba

FX = os.path.expanduser("~/.cache/aaaai-editor/fx")


def starfield(W: int, H: int, fps: float, glow: str = "#E60012", flame: str = "#FF6A1A",
              seconds: float = 4.0, seed: int = 7) -> str:
    """深空跃迁星空，底部一抹发射火光。周期 seconds 秒、首尾无缝，循环播放不跳。"""
    os.makedirs(FX, exist_ok=True)
    key = hashlib.sha1(repr((W, H, fps, glow, flame, seconds, seed, 2)).encode()).hexdigest()[:12]
    out = os.path.join(FX, "starfield_%s.mp4" % key)
    if os.path.isfile(out):
        return out
    n = int(round(seconds * fps))
    gr, gg, gb = hex_rgb(glow)
    fr, fg, fb = hex_rgb(flame)
    # 底图：近黑 + 底部椭圆火光（可分离高斯：逐行乘同一条横向曲线）
    gx = [math.exp(-((x - W / 2.0) / (0.62 * W)) ** 2) for x in range(W)]
    base = bytearray(W * H * 3)
    for y in range(H):
        gy = math.exp(-((y - H * 1.04) / (0.30 * H)) ** 2) * 0.62
        hot = math.exp(-((y - H * 1.02) / (0.12 * H)) ** 2) * 0.45
        row = bytearray(W * 3)
        if gy > 0.004:
            for x in range(W):
                g, h = gx[x] * gy, gx[x] * gx[x] * hot
                row[3 * x] = min(255, int(5 + gr * g + fr * h))
                row[3 * x + 1] = min(255, int(5 + gg * g + fg * h))
                row[3 * x + 2] = min(255, int(5 + gb * g + fb * h))
        else:
            row = bytearray(b"\x05\x05\x05" * W)
        base[y * W * 3:(y + 1) * W * 3] = row
    rnd = random.Random(seed)
    cx, cy = W / 2.0, H * 0.40
    rmax = math.hypot(W, H) * 0.62
    stars = [(rnd.uniform(0, 2 * math.pi), rnd.random(), rnd.choice((1, 1, 1, 2)),
              rnd.uniform(0.5, 1.0), rnd.random() < 0.12) for _ in range(int(W * H / 5200))]
    enc = subprocess.Popen([env.ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", "%dx%d" % (W, H), "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "18",
                            "-preset", "medium", "-pix_fmt", "yuv420p", "-g", str(n), out],
                           stdin=subprocess.PIPE)
    for f in range(n):
        buf = bytearray(base)
        for ang, ph, k, br, warm in stars:
            p = (f / n * k + ph) % 1.0                       # 整数圈数 k → 周期无缝
            r = 6 + rmax * p ** 2.4                          # 由中心加速外飞
            tail = max(1.0, 26 * p ** 2 * k)                 # 越快拖尾越长
            ca, sa = math.cos(ang), math.sin(ang)
            v = br * min(1.0, p * 2.2)
            col = (255, 214, 170) if warm else (225, 232, 255)
            steps = int(tail) + 1
            for i in range(steps):
                rr = r - i
                if rr < 0:
                    break
                px, py = int(cx + ca * rr), int(cy + sa * rr)
                if 0 <= px < W and 0 <= py < H:
                    a = v * (1 - i / steps)
                    j = (py * W + px) * 3
                    buf[j] = max(buf[j], int(col[0] * a))
                    buf[j + 1] = max(buf[j + 1], int(col[1] * a))
                    buf[j + 2] = max(buf[j + 2], int(col[2] * a))
        enc.stdin.write(bytes(buf))
    enc.stdin.close()
    if enc.wait() != 0:
        raise env.ToolError("生成星空失败")
    return out


def mesh(W: int, H: int, fps: float, colors, seconds: float = 6.0, seed: int = 13,
         base: str = "#0B0B0D") -> str:
    """网状渐层背景：几团慢慢飘的色晕叠在底色上，首尾无缝可循环。

    整屏卡片、片头片尾用它当底，比纯色有空气感。逐像素算太慢，所以先算一张 1/8 的小图，
    交给 ffmpeg 放大（本来就是很柔的东西，放大完全看不出来）。
    """
    os.makedirs(FX, exist_ok=True)
    cols = [hex_rgb(c) for c in (colors or ["#3A2E1A", "#1A2A3A"])][:4]
    key = hashlib.sha1(repr((W, H, fps, tuple(cols), seconds, seed, base, 1)).encode()).hexdigest()[:12]
    out = os.path.join(FX, "mesh_%s.mp4" % key)
    if os.path.isfile(out):
        return out
    sw, sh = max(24, W // 8), max(24, H // 8)
    n = int(round(seconds * fps))
    br, bg_, bb = hex_rgb(base)
    rnd = random.Random(seed)
    blobs = []
    for i, c in enumerate(cols):
        blobs.append({"c": c, "x": rnd.uniform(0.15, 0.85), "y": rnd.uniform(0.12, 0.88),
                      "ax": rnd.uniform(0.06, 0.16), "ay": rnd.uniform(0.06, 0.18),
                      "k": rnd.choice([1, 1, 2]), "ph": rnd.random(),
                      "r": rnd.uniform(0.38, 0.62), "a": rnd.uniform(0.55, 0.85)})
    enc = subprocess.Popen(
        [env.ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", "%dx%d" % (sw, sh), "-r", str(fps), "-i", "-",
         "-vf", "scale=%d:%d:flags=bicubic,gblur=sigma=%d" % (W, H, max(6, W // 90)),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", out],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for f in range(n):
        t = f / float(n)
        buf = bytearray(sw * sh * 3)
        cs = []
        for b in blobs:   # 每团色晕沿椭圆飘（整数圈数 → 循环无缝）
            ang = 2 * math.pi * (t * b["k"] + b["ph"])
            cs.append((b["x"] + b["ax"] * math.cos(ang), b["y"] + b["ay"] * math.sin(ang),
                       b["r"], b["a"], b["c"]))
        for y in range(sh):
            fy = (y + 0.5) / sh
            row = y * sw * 3
            for x in range(sw):
                fx_ = (x + 0.5) / sw
                r_, g_, b2_ = br, bg_, bb
                for cx_, cy_, rr, aa, col in cs:
                    d = ((fx_ - cx_) / rr) ** 2 + ((fy - cy_) / rr) ** 2
                    w_ = aa * math.exp(-d * 2.4)
                    if w_ < 0.004:
                        continue
                    r_ += (col[0] - r_) * w_
                    g_ += (col[1] - g_) * w_
                    b2_ += (col[2] - b2_) * w_
                j = row + x * 3
                buf[j] = min(255, int(r_)); buf[j + 1] = min(255, int(g_)); buf[j + 2] = min(255, int(b2_))
        enc.stdin.write(bytes(buf))
    enc.stdin.close()
    if enc.wait() != 0:
        raise env.ToolError("生成网状渐层失败")
    return out


def sweep(w: int, h: int, radius: float, fps: float, color: str = "#FFFFFF", peak: float = 0.30,
          dur: float = 0.60) -> Tuple[str, int]:
    """激光扫光：一道斜向光带从左扫到右，裁在卡片圆角内。返回 (帧序列模板, 帧数)。"""
    key = hashlib.sha1(repr((w, h, radius, fps, color, peak, dur, 1)).encode()).hexdigest()[:12]
    d = os.path.join(FX, "sweep_%s" % key)
    n = max(4, int(round(dur * fps)))
    pat = os.path.join(d, "s_%03d.png")
    if os.path.isfile(pat % (n - 1)):
        return pat, n
    os.makedirs(d, exist_ok=True)
    r, g, b = hex_rgb(color)
    bw = max(40, int(w * 0.16))
    slope = 0.38
    prof = bytearray()
    for i in range(bw):                                 # 光带横截面：两边柔、中间一条亮芯
        q = abs(i - bw / 2.0) / (bw / 2.0)
        a = peak * (1 - q) ** 1.6 + (0.25 if q < 0.06 else 0.0)
        prof += bytes((r, g, b, min(255, int(a * 255))))
    span = w + bw + h * slope
    for f in range(n):
        buf = bytearray(w * h * 4)
        c = -bw - h * slope + span * (f / (n - 1)) ** 0.85
        for y in range(h):
            hs = _halfspan(w / 2.0, h / 2.0, radius, abs(y + 0.5 - h / 2.0))
            if hs < 0:
                continue
            xl, xr = int(math.ceil(w / 2.0 - hs)), int(w / 2.0 + hs)
            x0 = int(c + (h - y) * slope)
            a, z = max(x0, xl), min(x0 + bw, xr)
            if z > a:
                buf[(y * w + a) * 4:(y * w + z) * 4] = prof[(a - x0) * 4:(z - x0) * 4]
        write_rgba(pat % f, w, h, buf)
    return pat, n


def sparkle(size: int, fps: float, color: str = "#FFFFFF", dur: float = 0.9) -> Tuple[str, int, int]:
    """闪光：一颗四角星，放大→转一点→缩小淡出。白色星芯、外缘带一点强调色。
    返回 (帧序列模板, 帧数, 画布边长)。"""
    c = max(24, int(size * 1.6)) & ~1
    key = hashlib.sha1(repr((c, fps, color, dur, 1)).encode()).hexdigest()[:12]
    d = os.path.join(FX, "sparkle_%s" % key)
    n = max(6, int(round(dur * fps)))
    pat = os.path.join(d, "k_%03d.png")
    if os.path.isfile(pat % (n - 1)):
        return pat, n, c
    os.makedirs(d, exist_ok=True)
    ar, ag, ab = hex_rgb(color)
    h = c / 2.0
    for f in range(n):
        p = f / float(n - 1)
        s = math.sin(math.pi * p) ** 0.8            # 大小：0 → 1 → 0
        al = math.sin(math.pi * p) ** 0.6           # 透明度
        rot = math.radians(10 + 35 * p)
        R = h * 0.92 * max(s, 0.001)
        cr, sr = math.cos(rot), math.sin(rot)
        buf = bytearray(c * c * 4)
        for y in range(c):
            dy_ = y + 0.5 - h
            for x in range(c):
                dx_ = x + 0.5 - h
                u, v = (dx_ * cr + dy_ * sr) / R, (-dx_ * sr + dy_ * cr) / R
                au, av = abs(u), abs(v)
                if au > 1.4 or av > 1.4:
                    continue
                star = max(0.0, 1.0 - (math.sqrt(au) + math.sqrt(av)) ** 2)   # 四角星（星形线）
                r2 = u * u + v * v
                glow = 0.45 * math.exp(-r2 / 0.06)
                a = min(1.0, star * 1.6 + glow) * al
                if a <= 0.004:
                    continue
                t = min(1.0, math.sqrt(r2) * 1.4)          # 中心白、外缘偏强调色
                j = (y * c + x) * 4
                buf[j] = int(255 + (ar - 255) * t)
                buf[j + 1] = int(255 + (ag - 255) * t)
                buf[j + 2] = int(255 + (ab - 255) * t)
                buf[j + 3] = int(a * 255)
        write_rgba(pat % f, c, c, buf)
    return pat, n, c


def confetti(W: int, H: int, fps: float, colors, dur: float = 2.6, ox: float = 0.5, oy: float = 0.62,
             n: int = 150, seed: int = 11) -> Tuple[str, int]:
    """拉炮彩带：从 (ox, oy) 往上喷出、受重力落下、边转边飘的小纸片，后段渐隐。
    画布 W×H（通常是成片的一半，叠加时放大），返回 (帧序列模板, 帧数)。"""
    key = hashlib.sha1(repr((W, H, fps, tuple(colors), dur, ox, oy, n, seed, 1)).encode()).hexdigest()[:12]
    d = os.path.join(FX, "confetti_%s" % key)
    nf = max(8, int(round(dur * fps)))
    pat = os.path.join(d, "c_%03d.png")
    if os.path.isfile(pat % (nf - 1)):
        return pat, nf
    os.makedirs(d, exist_ok=True)
    rnd = random.Random(seed)
    cols = [hex_rgb(c) for c in colors]
    U = min(W, H * 0.5625)
    parts = []
    for _ in range(n):
        ang = math.radians(rnd.uniform(-160, -20))           # 往上半圈喷
        sp = U * rnd.uniform(1.1, 2.4)                        # 像素／秒
        parts.append({"vx": math.cos(ang) * sp, "vy": math.sin(ang) * sp, "c": rnd.choice(cols),
                      "w": U * rnd.uniform(0.012, 0.022), "h": U * rnd.uniform(0.006, 0.011),
                      "rot": rnd.uniform(0, math.pi), "spin": rnd.uniform(-9, 9), "flip": rnd.uniform(4, 11),
                      "drag": rnd.uniform(1.4, 2.4), "delay": rnd.uniform(0, 0.12)})
    g = U * 2.2
    x0, y0 = W * ox, H * oy
    for f in range(nf):
        t = f / float(fps)
        buf = bytearray(W * H * 4)
        fade = 1.0 if t < dur * 0.6 else max(0.0, 1.0 - (t - dur * 0.6) / (dur * 0.4))
        for p in parts:
            tt = t - p["delay"]
            if tt <= 0:
                continue
            k = p["drag"]
            e = (1 - math.exp(-k * tt)) / k                    # 空气阻力：速度指数衰减
            x = x0 + p["vx"] * e
            y = y0 + p["vy"] * e + 0.5 * g * tt * tt * 0.55
            if not (-20 < x < W + 20 and -20 < y < H + 20):
                continue
            rot = p["rot"] + p["spin"] * tt
            hw = p["w"] / 2.0
            hh = p["h"] / 2.0 * abs(math.cos(p["flip"] * tt))  # 翻面：看起来在飘
            cr, sr = math.cos(rot), math.sin(rot)
            ext = int(max(hw, hh) + 2)
            a8 = int(255 * fade)
            for yy in range(int(y) - ext, int(y) + ext + 1):
                if not 0 <= yy < H:
                    continue
                dy_ = yy + 0.5 - y
                for xx in range(int(x) - ext, int(x) + ext + 1):
                    if not 0 <= xx < W:
                        continue
                    dx_ = xx + 0.5 - x
                    u, v = dx_ * cr + dy_ * sr, -dx_ * sr + dy_ * cr
                    if abs(u) <= hw and abs(v) <= hh + 0.5:
                        j = (yy * W + xx) * 4
                        buf[j], buf[j + 1], buf[j + 2], buf[j + 3] = p["c"][0], p["c"][1], p["c"][2], a8
        write_rgba(pat % f, W, H, buf)
    return pat, nf
