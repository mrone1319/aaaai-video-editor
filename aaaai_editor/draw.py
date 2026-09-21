"""程序化绘制卡片底板：圆角矩形 + 渐变 + 描边 + 柔和投影。

不用浏览器、不用 Pillow。按「每行解析求跨度」绘制：
行内部整段直接写字节（C 速度），只有边缘带按像素混合，
所以 1080×600 的底板也在 0.1 秒内完成。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Callable, Optional, Sequence, Tuple

from .png import write_rgba

RGB = Tuple[int, int, int]
PLATE_VER = "2"


def hex_rgb(s: str) -> RGB:
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _halfspan(hw: float, hh: float, r: float, dy: float) -> float:
    """圆角矩形在某一行的半宽；返回 -1 表示该行不在形状内。"""
    if hw <= 0 or hh <= 0:
        return -1.0
    r = max(0.0, min(r, hw, hh))
    if dy <= hh - r:
        return hw
    k = dy - (hh - r)
    if k >= r:
        return -1.0
    return hw - r + math.sqrt(max(0.0, r * r - k * k))


def _sdf(dx: float, dy: float, hw: float, hh: float, r: float) -> float:
    """到圆角矩形边界的有符号距离，内部为负。"""
    r = max(0.0, min(r, hw, hh))
    qx, qy = abs(dx) - (hw - r), abs(dy) - (hh - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def paint(buf: bytearray, W: int, H: int, cx: float, cy: float, hw: float, hh: float,
          r: float, color: Callable[[int], RGB], amax: float = 1.0, soft: float = 0.5) -> None:
    """把一个圆角矩形按 source-over 混合进 buf。soft 为边缘羽化宽度（像素）。"""
    if amax <= 0:
        return
    soft = max(soft, 0.01)
    y0 = max(0, int(cy - hh - soft - 1))
    y1 = min(H - 1, int(cy + hh + soft + 1))
    for y in range(y0, y1 + 1):
        dy = abs(y + 0.5 - cy)
        hs_out = _halfspan(hw + soft, hh + soft, r + soft, dy)
        if hs_out < 0:
            continue
        hs_in = _halfspan(hw - soft, hh - soft, r - soft, dy)
        cr, cg, cb = color(y)
        row = y * W * 4
        xa = max(0, int(cx - hs_out - 1))
        xb = min(W - 1, int(cx + hs_out + 1))
        # 整段常量 alpha：目标为空时直接写字节，省掉逐像素混合（投影最吃这一步）
        if hs_in > 0 and amax < 1.0:
            sa = max(xa, int(math.ceil(cx - hs_in)))
            sb = min(xb, int(math.floor(cx + hs_in)) - 1)
            if sb >= sa and buf[row + sa * 4:row + (sb + 1) * 4] == bytes(4 * (sb - sa + 1)):
                buf[row + sa * 4:row + (sb + 1) * 4] = bytes(
                    (cr, cg, cb, int(round(amax * 255)))) * (sb - sa + 1)
                spans = ((xa, sa - 1), (sb + 1, xb))
            else:
                spans = ((xa, xb),)
        elif hs_in > 0 and amax >= 1.0:
            sa = max(xa, int(math.ceil(cx - hs_in)))
            sb = min(xb, int(math.floor(cx + hs_in)) - 1)
            if sb >= sa:
                buf[row + sa * 4:row + (sb + 1) * 4] = bytes((cr, cg, cb, 255)) * (sb - sa + 1)
                spans = ((xa, sa - 1), (sb + 1, xb))
            else:
                spans = ((xa, xb),)
        else:
            spans = ((xa, xb),)
        for px0, px1 in spans:
            for x in range(px0, px1 + 1):
                d = _sdf(x + 0.5 - cx, y + 0.5 - cy, hw, hh, r)
                a = amax * min(1.0, max(0.0, (soft - d) / (2 * soft)))
                if a <= 0.002:
                    continue
                i = row + x * 4
                if a >= 0.998:
                    buf[i:i + 4] = bytes((cr, cg, cb, 255))
                    continue
                da = buf[i + 3] / 255.0
                na = a + da * (1 - a)
                for k, sc in enumerate((cr, cg, cb)):
                    buf[i + k] = int(round((sc * a + buf[i + k] * da * (1 - a)) / na)) if na else 0
                buf[i + 3] = int(round(na * 255))


def make_plate(spec: dict, cache_dir: str) -> Tuple[str, int]:
    """按 spec 生成底板 PNG（带缓存）。返回 (路径, 外扩边距)。

    spec: w,h,radius,fill(单色或[上,下]),alpha,border{w,color},shadow{soft,alpha,dy}
    """
    # 画法改了就把 PLATE_VER 加一：旧缓存自动失效
    key = hashlib.sha1((PLATE_VER + json.dumps(spec, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:16]
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "plate_%s.png" % key)
    sh = spec.get("shadow") or {}
    margin = int(math.ceil(sh.get("soft", 0) + abs(sh.get("dy", 0)) + 2)) if sh else 2
    if os.path.isfile(path):
        return path, margin

    w, h = int(spec["w"]), int(spec["h"])
    W, H = w + margin * 2, h + margin * 2
    buf = bytearray(W * H * 4)
    cx, cy = W / 2.0, H / 2.0
    hw, hh = w / 2.0, h / 2.0
    r = float(spec.get("radius", 0))

    if sh and sh.get("alpha", 0) > 0:
        sc = hex_rgb(sh.get("color", "#000000"))
        paint(buf, W, H, cx + sh.get("dx", 0), cy + sh.get("dy", 0), hw, hh, r,
              lambda _y: sc, float(sh["alpha"]), max(1.0, float(sh.get("soft", 18))))

    # 半透明底板（毛玻璃）：投影只留在边外，底板里面挖空——否则红色光晕会透上来，整块变成红色
    if sh and sh.get("alpha", 0) > 0 and float(spec.get("alpha", 1.0)) < 0.9 and spec.get("fill"):
        for y in range(H):
            hs = _halfspan(hw, hh, r, abs(y + 0.5 - cy))
            if hs <= 0:
                continue
            x0, x1 = max(0, int(cx - hs + 1)), min(W, int(cx + hs - 1))
            if x1 > x0:
                buf[(y * W + x0) * 4:(y * W + x1) * 4] = bytes((x1 - x0) * 4)

    sc = spec.get("scrim")
    if sc:   # 画面边缘渐变遮罩：一头最深、渐渐透明，无边框无圆角（字直接排在上面，不用方块）
        col = hex_rgb(sc.get("color", "#000000"))
        a0 = float(sc.get("alpha", 0.8))
        pw = float(sc.get("power", 1.5))
        up = sc.get("dir", "down") == "up"
        for y in range(H):
            t = min(1.0, max(0.0, (y - margin) / float(max(1, h - 1))))
            t = 1.0 - t if up else t                     # up：最深在下沿
            hold = float(sc.get("hold", 0.0))             # 最深的一头先保持这么大比例，再渐渐透明
            t = 0.0 if t <= hold else (t - hold) / max(1e-6, 1.0 - hold)
            a8 = int(round(255 * a0 * (1.0 - t) ** pw))
            row = y * W * 4
            buf[row:row + W * 4] = bytes((col[0], col[1], col[2], a8)) * W

    fill = spec.get("fill") if not sc else None
    alpha = float(spec.get("alpha", 1.0))
    if fill:
        if isinstance(fill, str):
            top = bot = hex_rgb(fill)
        else:
            top, bot = hex_rgb(fill[0]), hex_rgb(fill[-1])
        top_y, span = cy - hh, max(1.0, 2 * hh)

        def grad(y: int, _t=top, _b=bot, _y0=top_y, _s=span) -> RGB:
            p = min(1.0, max(0.0, (y + 0.5 - _y0) / _s))
            return (int(_t[0] + (_b[0] - _t[0]) * p), int(_t[1] + (_b[1] - _t[1]) * p),
                    int(_t[2] + (_b[2] - _t[2]) * p))

        bd = spec.get("border") or {}
        bw = float(bd.get("w", 0))
        if bw > 0:
            bc = hex_rgb(bd.get("color", "#ffffff"))
            paint(buf, W, H, cx, cy, hw, hh, r, lambda _y: bc, min(1.0, alpha + 0.08))
            paint(buf, W, H, cx, cy, hw - bw, hh - bw, max(0.0, r - bw), grad, alpha)
        else:
            paint(buf, W, H, cx, cy, hw, hh, r, grad, alpha)

    # 卡片里的子形状（编号行卡的行底、编号方块）：同样烤进底板
    for sh in spec.get("shapes") or []:
        scx, scy = margin + sh["x"] + sh["w"] / 2.0, margin + sh["y"] + sh["h"] / 2.0
        shw, shh, sr = sh["w"] / 2.0, sh["h"] / 2.0, float(sh.get("r", 0))
        fc = hex_rgb(sh["fill"])
        if sh.get("line"):
            lc = hex_rgb(sh["line"])
            paint(buf, W, H, scx, scy, shw, shh, sr, lambda _y, _c=lc: _c, 1.0)
            paint(buf, W, H, scx, scy, shw - 1.5, shh - 1.5, max(0.0, sr - 1.5), lambda _y, _c=fc: _c,
                  float(sh.get("alpha", 1.0)))
        else:
            paint(buf, W, H, scx, scy, shw, shh, sr, lambda _y, _c=fc: _c, float(sh.get("alpha", 1.0)))

    # 与卡片同时出现的图标直接烤进底板：不增加 ffmpeg 输入，也不增加一次叠加
    for ic in spec.get("icons") or []:
        from . import icons as _icons
        _icons.paint(buf, W, H, ic["name"], margin + ic["x"], margin + ic["y"], ic["size"],
                     ic["color"], float(ic.get("stroke", 2.0)), ic.get("badge"))

    write_rgba(path, W, H, buf)
    return path, margin
