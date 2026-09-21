"""图标：本项目自绘的线性图标，24 单位网格，用有符号距离场栅格化。

不用 SVG、不用字体图标、不用 Pillow。每个图标是几个几何图元（线段、折线、圆、圆角矩形、
多边形、胶囊）的并集／差集；距离场天然带抗锯齿，任意尺寸都锐利。
"""
from __future__ import annotations

import hashlib
import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

from .png import write_rgba

Pt = Tuple[float, float]
INF = float("inf")


# ---------------------------------------------------------------- 取点辅助
def arc(cx, cy, rx, ry, a0, a1, n=18) -> List[Pt]:
    """y 轴向下：180→360 是上半圆，0→180 是下半圆。"""
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def star(cx, cy, ro, ri, k=5) -> List[Pt]:
    pts = []
    for i in range(k * 2):
        r = ro if i % 2 == 0 else ri
        a = math.radians(-90 + i * 180 / k)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def lens(x0, x1, cy, h, n=14) -> List[Pt]:
    up = [(x0 + (x1 - x0) * i / n, cy - h * math.sin(math.pi * i / n)) for i in range(n + 1)]
    dn = [(x0 + (x1 - x0) * i / n, cy + h * math.sin(math.pi * i / n)) for i in range(n, -1, -1)]
    return up + dn[1:]


def hexagon(cx, cy, r) -> List[Pt]:
    return [(cx + r * math.cos(math.radians(-90 + 60 * i)), cy + r * math.sin(math.radians(-90 + 60 * i)))
            for i in range(6)]


# ---------------------------------------------------------------- 图标定义
# 图元：("l",x1,y1,x2,y2[,w]) 线段  ("pl",[点][,w]) 折线  ("pg",[点]) 多边形描边
#       ("pf",[点]) 多边形填充  ("c",cx,cy,r) 圆环  ("cf",cx,cy,r) 实心圆
#       ("r",x,y,w,h,圆角) 矩形描边  ("rf",…) 矩形填充  ("pill",x1,y1,x2,y2,r) 胶囊描边
#       ("cut", 图元) 从已画部分挖掉
ICONS: Dict[str, list] = {
    # —— Web3 ——
    "wallet": [("r", 3, 7, 18, 13, 3), ("pl", [(6, 7), (15, 3.5), (17, 7)]),
               ("r", 14, 11, 7, 5, 2), ("cf", 17, 13.5, 1.1)],
    "token": [("c", 12, 12, 9), ("pg", hexagon(12, 12, 4.8))],
    "candlestick": [("l", 5.5, 3, 5.5, 13, 1.4), ("rf", 3.8, 5.5, 3.4, 5.5, 0.8),
                    ("l", 12, 7, 12, 21, 1.4), ("rf", 10.3, 10, 3.4, 8, 0.8),
                    ("l", 18.5, 4, 18.5, 17, 1.4), ("rf", 16.8, 7, 3.4, 6.5, 0.8)],
    "chainlink": [("pill", 4.5, 16.5, 10.5, 10.5, 3.3), ("pill", 13.5, 13.5, 19.5, 7.5, 3.3),
                  ("l", 9.5, 14.5, 14.5, 9.5)],
    "contract": [("r", 5, 3, 14, 18, 2), ("l", 8.5, 8, 15.5, 8), ("l", 8.5, 12, 15.5, 12),
                 ("l", 8.5, 16, 12, 16)],
    "gas": [("r", 4, 4, 10, 17, 2), ("rf", 6.3, 6.5, 5.4, 4.2, 1), ("l", 2.5, 21, 15.5, 21),
            ("pl", [(14, 8), (17.2, 8), (19.5, 10.3), (19.5, 16.5), (18, 18)])],
    "nft": [("pg", hexagon(12, 12, 9.5)), ("pf", [(12, 7.5), (16, 12), (12, 16.5), (8, 12)])],
    "x": [("pf", [(4, 4), (9, 4), (20, 20), (15, 20)]), ("l", 19.3, 4.2, 4.7, 19.8, 1.9)],
    "telegram": [("pg", [(3, 11.5), (21, 4), (16.5, 20)]), ("l", 10.8, 14.2, 21, 4),
                 ("l", 10.8, 14.2, 11.6, 19.2)],
    "discord": [("rf", 3, 6.5, 18, 12.5, 5.2), ("rf", 4.5, 14, 4, 5.5, 2), ("rf", 15.5, 14, 4, 5.5, 2),
                ("cut", ("cf", 9, 12.2, 1.9)), ("cut", ("cf", 15, 12.2, 1.9))],
    "chart_up": [("pl", [(4, 4), (4, 20), (20, 20)]), ("pl", [(7, 16), (11, 12), (14, 14), (19, 8)]),
                 ("pl", [(15.3, 8), (19, 8), (19, 11.7)])],
    "chart_down": [("pl", [(4, 4), (4, 20), (20, 20)]), ("pl", [(7, 8), (11, 12), (14, 10), (19, 16)]),
                   ("pl", [(15.3, 16), (19, 16), (19, 12.3)])],
    "swap": [("l", 5, 8, 19, 8), ("pl", [(15, 4.5), (19, 8), (15, 11.5)]),
             ("l", 19, 16, 5, 16), ("pl", [(9, 12.5), (5, 16), (9, 19.5)])],
    "lock": [("r", 5, 11, 14, 10, 2.2), ("pl", [(8, 11)] + arc(12, 8, 4, 4, 180, 360) + [(16, 11)]),
             ("cf", 12, 15.3, 1.4), ("l", 12, 15.3, 12, 17.6)],
    "shield": [("pg", [(12, 2.8), (19.8, 5.8), (19, 13), (12, 21.2), (5, 13), (4.2, 5.8)]),
               ("pl", [(8.6, 12), (11, 14.4), (15.4, 9.6)])],
    "key": [("c", 8, 15, 4), ("l", 10.8, 12.2, 20, 3), ("l", 17, 6, 19.5, 8.5), ("l", 14.5, 8.5, 16.5, 10.5)],
    # —— 通用 ——
    "check": [("pl", [(5, 12.5), (10, 17.5), (19, 7)])],
    "cross": [("l", 6, 6, 18, 18), ("l", 18, 6, 6, 18)],
    "arrow_right": [("l", 4, 12, 20, 12), ("pl", [(14, 6), (20, 12), (14, 18)])],
    "arrow_up": [("l", 12, 20, 12, 4), ("pl", [(6, 10), (12, 4), (18, 10)])],
    "star": [("pf", star(12, 12.6, 9.6, 4.1))],
    "bolt": [("pf", [(13.5, 2), (4.5, 13.5), (11, 13.5), (10, 22), (19.5, 10), (13, 10)])],
    "rocket": [("pg", [(12, 2.5), (16, 8), (16, 16), (8, 16), (8, 8)]), ("c", 12, 9.6, 1.9),
               ("pf", [(8, 11.5), (4.5, 17), (8, 16)]), ("pf", [(16, 11.5), (19.5, 17), (16, 16)]),
               ("l", 12, 18.5, 12, 21.5)],
    "user": [("c", 12, 8, 4), ("pl", arc(12, 21, 7.5, 7.5, 180, 360))],
    "users": [("c", 9, 8.5, 3.5), ("pl", arc(9, 20.5, 6.2, 6.2, 180, 360)),
              ("pl", arc(16.2, 8.5, 3.2, 3.5, 270, 450)), ("pl", arc(16.5, 20.5, 5, 6.2, 270, 360))],
    "clock": [("c", 12, 12, 9), ("pl", [(12, 7), (12, 12), (15.5, 14)])],
    "calendar": [("r", 3.5, 5, 17, 15.5, 2.5), ("l", 3.5, 10, 20.5, 10), ("l", 8, 3, 8, 7), ("l", 16, 3, 16, 7),
                 ("cf", 8, 14.5, 1.1), ("cf", 12, 14.5, 1.1), ("cf", 16, 14.5, 1.1)],
    "globe": [("c", 12, 12, 9), ("l", 3, 12, 21, 12), ("pg", arc(12, 12, 4.2, 9, 0, 360, 28)[:-1])],
    "heart": [("cf", 8.4, 9.6, 4.6), ("cf", 15.6, 9.6, 4.6), ("pf", [(4.1, 11.3), (12, 20.5), (19.9, 11.3), (12, 8.5)])],
    "eye": [("pg", lens(2.5, 21.5, 12, 6.2)), ("c", 12, 12, 3)],
    "play": [("pf", [(8, 4.8), (19.5, 12), (8, 19.2)])],
    "mic": [("pill", 12, 6, 12, 11.5, 3.5), ("pl", arc(12, 11, 6.5, 6.5, 0, 180)), ("l", 12, 17.5, 12, 21),
            ("l", 8.5, 21, 15.5, 21)],
    "idea": [("pl", arc(12, 10, 6.2, 6.2, 125, 415, 26)), ("l", 9.4, 15.1, 9.4, 17.5), ("l", 14.6, 15.1, 14.6, 17.5),
             ("l", 9.4, 17.5, 14.6, 17.5), ("l", 10.3, 20.5, 13.7, 20.5)],
    "target": [("c", 12, 12, 9), ("c", 12, 12, 5), ("cf", 12, 12, 1.7)],
    "trophy": [("pl", [(7, 4), (7, 10), (9.5, 14), (14.5, 14), (17, 10), (17, 4)]), ("l", 7, 4, 17, 4),
               ("pl", [(7, 6), (4, 6), (4, 8.5), (7.3, 11)]), ("pl", [(17, 6), (20, 6), (20, 8.5), (16.7, 11)]),
               ("l", 12, 14, 12, 18), ("l", 8, 20, 16, 20)],
    "money": [("c", 12, 12, 9.5), ("l", 12, 4.8, 12, 19.2, 1.6),
              ("pl", [(15, 8.6), (13.6, 7.6), (10.5, 7.6), (9, 9), (9.5, 11), (14.5, 13), (15, 15),
                      (13.5, 16.4), (10.4, 16.4), (8.9, 15.4)], 1.7)],
    "chat": [("r", 3, 4, 18, 13, 4), ("pl", [(7.5, 17), (7, 21), (11.5, 17)])],
    "camera": [("r", 3, 7, 18, 13, 3), ("c", 12, 13.5, 3.8), ("pl", [(8, 7), (9.5, 4.5), (14.5, 4.5), (16, 7)])],
    "bell": [("pl", [(5, 17)] + arc(12, 10.5, 6, 6, 180, 360) + [(18, 17)]), ("l", 4, 17, 20, 17),
             ("l", 10, 20.5, 14, 20.5)],
    "fire": [("pg", [(12, 2.5), (15.5, 7.5), (17.5, 11.5), (17.8, 15), (16, 18.8), (12, 21), (8, 18.8),
                     (6.2, 15), (6.8, 11), (9, 8), (10.2, 11), (12, 2.5)][:-1])],
    "link": [("pill", 5, 12, 11, 12, 3.2), ("pill", 13, 12, 19, 12, 3.2)],
}
ALIASES = {"twitter": "x", "x-twitter": "x", "coin": "token", "chain": "chainlink", "candle": "candlestick",
           "doc": "contract", "fuel": "gas", "up": "arrow_up", "right": "arrow_right", "ok": "check",
           "no": "cross", "growth": "chart_up", "drop": "chart_down", "dollar": "money", "time": "clock",
           "bulb": "idea", "security": "shield", "people": "users", "launch": "rocket"}


def resolve(name: str) -> str:
    n = ALIASES.get(name, name)
    if n not in ICONS:
        raise KeyError("没有这个图标：%s（可用：%s）" % (name, " ".join(sorted(ICONS))))
    return n


def list_icons() -> List[str]:
    return sorted(ICONS)


# ---------------------------------------------------------------- 距离场
def _seg(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _poly(px, py, v) -> float:
    d = (px - v[0][0]) ** 2 + (py - v[0][1]) ** 2
    s = 1.0
    n = len(v)
    j = n - 1
    for i in range(n):
        ex, ey = v[j][0] - v[i][0], v[j][1] - v[i][1]
        wx, wy = px - v[i][0], py - v[i][1]
        ee = ex * ex + ey * ey
        t = 0.0 if ee == 0 else max(0.0, min(1.0, (wx * ex + wy * ey) / ee))
        bx, by = wx - ex * t, wy - ey * t
        d = min(d, bx * bx + by * by)
        c1, c2, c3 = py >= v[i][1], py < v[j][1], ex * wy > ey * wx
        if (c1 and c2 and c3) or (not c1 and not c2 and not c3):
            s = -s
        j = i
    return s * math.sqrt(d)


def _rrect(px, py, x, y, w, h, r) -> float:
    hw, hh = w / 2.0, h / 2.0
    r = max(0.0, min(r, hw, hh))
    qx, qy = abs(px - x - hw) - (hw - r), abs(py - y - hh) - (hh - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def _prim(op, px, py, sw) -> float:
    k = op[0]
    if k == "l":
        w = op[5] if len(op) > 5 else sw
        return _seg(px, py, op[1], op[2], op[3], op[4]) - w / 2
    if k == "pl":
        pts = op[1]
        w = op[2] if len(op) > 2 else sw
        return min(_seg(px, py, *pts[i], *pts[i + 1]) for i in range(len(pts) - 1)) - w / 2
    if k == "pg":
        return abs(_poly(px, py, op[1])) - sw / 2
    if k == "pf":
        return _poly(px, py, op[1])
    if k == "c":
        return abs(math.hypot(px - op[1], py - op[2]) - op[3]) - sw / 2
    if k == "cf":
        return math.hypot(px - op[1], py - op[2]) - op[3]
    if k == "r":
        return abs(_rrect(px, py, *op[1:6])) - sw / 2
    if k == "rf":
        return _rrect(px, py, *op[1:6])
    if k == "pill":
        return abs(_seg(px, py, op[1], op[2], op[3], op[4]) - op[5]) - sw / 2
    raise ValueError(k)


def _sdf(ops, px, py, sw) -> float:
    d = INF
    for op in ops:
        if op[0] == "cut":
            d = max(d, -_prim(op[1], px, py, sw))
        else:
            d = min(d, _prim(op, px, py, sw))
    return d


def _hex(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def paint(buf: bytearray, W: int, H: int, name: str, x: float, y: float, size: float,
          color: str, stroke: float = 2.0, badge: Optional[str] = None) -> None:
    """把图标按 source-over 画进 RGBA 画布。badge 给颜色时先画一个实心圆底。"""
    ops = ICONS[resolve(name)]
    cr, cg, cb = _hex(color)
    if badge:
        br, bg, bb = _hex(badge)
        R = size / 2.0
        cx, cy = x + R, y + R
        for py in range(max(0, int(y)), min(H, int(y + size) + 1)):
            for px in range(max(0, int(x)), min(W, int(x + size) + 1)):
                a = min(1.0, max(0.0, 0.5 - (math.hypot(px + 0.5 - cx, py + 0.5 - cy) - R)))
                if a > 0:
                    _blend(buf, (py * W + px) * 4, br, bg, bb, a)
        pad = size * 0.22
        x, y, size = x + pad, y + pad, size - 2 * pad
    k = 24.0 / size          # 像素 → 图标单位
    for py in range(max(0, int(y)), min(H, int(math.ceil(y + size)))):
        uy = (py + 0.5 - y) * k
        row = py * W
        for px in range(max(0, int(x)), min(W, int(math.ceil(x + size)))):
            d = _sdf(ops, (px + 0.5 - x) * k, uy, stroke) / k   # 回到像素距离
            a = 0.5 - d
            if a <= 0:
                continue
            _blend(buf, (row + px) * 4, cr, cg, cb, min(1.0, a))


def _blend(buf, i, r, g, b, a) -> None:
    if a >= 0.999:
        buf[i:i + 4] = bytes((r, g, b, 255))
        return
    da = buf[i + 3] / 255.0
    na = a + da * (1 - a)
    if na <= 0:
        return
    buf[i] = int(round((r * a + buf[i] * da * (1 - a)) / na))
    buf[i + 1] = int(round((g * a + buf[i + 1] * da * (1 - a)) / na))
    buf[i + 2] = int(round((b * a + buf[i + 2] * da * (1 - a)) / na))
    buf[i + 3] = int(round(na * 255))


def make_png(name: str, size: int, color: str, cache_dir: str, stroke: float = 2.0,
             badge: Optional[str] = None) -> str:
    """单独的图标 PNG（给需要错峰出现、不能烤进底板的图标用）。"""
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.sha1(repr((resolve(name), size, color, stroke, badge)).encode()).hexdigest()[:16]
    p = os.path.join(cache_dir, "icon_%s.png" % key)
    if not os.path.isfile(p):
        buf = bytearray(size * size * 4)
        paint(buf, size, size, name, 0, 0, size, color, stroke, badge)
        write_rgba(p, size, size, buf)
    return p


def sheet(path: str, size: int = 96, cols: int = 8, color: str = "#F6F3EC", bg: str = "#12161D") -> int:
    """所有图标的总表（检查用）。"""
    names = list_icons()
    rows = (len(names) + cols - 1) // cols
    cell = int(size * 1.5)
    W, H = cols * cell, rows * cell
    br, bgc, bb = _hex(bg)
    buf = bytearray(bytes((br, bgc, bb, 255)) * (W * H))
    for i, n in enumerate(names):
        cx, cy = (i % cols) * cell, (i // cols) * cell
        paint(buf, W, H, n, cx + (cell - size) / 2, cy + (cell - size) / 2, size, color)
    write_rgba(path, W, H, buf)
    return len(names)
