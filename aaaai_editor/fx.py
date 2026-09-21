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
