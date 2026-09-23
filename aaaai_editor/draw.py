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
import random
from typing import Callable, Optional, Tuple

from .png import write_rgba

RGB = Tuple[int, int, int]
PLATE_VER = "7"


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
          r: float, color: Callable[[int], RGB], amax: float = 1.0, soft: float = 0.5,
          color_xy: Optional[Callable[[int, int], RGB]] = None) -> None:
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
        if color_xy is not None:       # 斜向渐层：整段也要逐像素取色
            for x in range(xa, xb + 1):
                d = _sdf(x + 0.5 - cx, y + 0.5 - cy, hw, hh, r)
                a = amax * min(1.0, max(0.0, (soft - d) / (2 * soft)))
                if a <= 0.002:
                    continue
                pr, pg, pb = color_xy(x, y)
                i = row + x * 4
                if a >= 0.998:
                    buf[i:i + 4] = bytes((pr, pg, pb, 255))
                    continue
                da = buf[i + 3] / 255.0
                na = a + da * (1 - a)
                for k, sc in enumerate((pr, pg, pb)):
                    buf[i + k] = int(round((sc * a + buf[i + k] * da * (1 - a)) / na)) if na else 0
                buf[i + 3] = int(round(na * 255))
            continue
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


def _mask(W: int, H: int, cx: float, cy: float, hw: float, hh: float, r: float, step: int) -> list:
    """圆角矩形的覆盖率图（每 step 像素取一格）：投影先在这张小图上糊，再放大回来。"""
    mw, mh = max(1, W // step), max(1, H // step)
    m = [0.0] * (mw * mh)
    for j in range(mh):
        y = (j + 0.5) * step
        dy = abs(y - cy)
        if _halfspan(hw + 1, hh + 1, r + 1, dy) < 0:
            continue
        row = j * mw
        for i in range(mw):
            x = (i + 0.5) * step
            d = _sdf(x - cx, y - cy, hw, hh, r)
            if d <= -step:
                m[row + i] = 1.0
            elif d < step:
                m[row + i] = min(1.0, max(0.0, (step - d) / (2.0 * step)))
    return m


def _blur(m: list, w: int, h: int, rad: int, passes: int = 3) -> list:
    """三次方框模糊 ≈ 高斯（用滑动窗口，纯 Python 也够快）。"""
    if rad < 1:
        return m
    for _ in range(passes):
        out = [0.0] * (w * h)
        n = 2 * rad + 1
        for j in range(h):                      # 横向
            row = j * w
            acc = m[row] * (rad + 1)
            for i in range(min(rad, w - 1)):
                acc += m[row + i + 1] if i + 1 < w else m[row + w - 1]
            for i in range(w):
                out[row + i] = acc / n
                acc += m[row + min(w - 1, i + rad + 1)] - m[row + max(0, i - rad)]
        m = out
        out = [0.0] * (w * h)
        for i in range(w):                      # 纵向
            acc = m[i] * (rad + 1)
            for j in range(min(rad, h - 1)):
                acc += m[(j + 1) * w + i] if j + 1 < h else m[(h - 1) * w + i]
            for j in range(h):
                out[j * w + i] = acc / n
                acc += m[min(h - 1, j + rad + 1) * w + i] - m[max(0, j - rad) * w + i]
        m = out
    return m


def _put_shadow(buf: bytearray, W: int, H: int, m: list, mw: int, mh: int, step: int,
                col: RGB, amax: float, over: bool = False, skip: tuple = ()) -> None:
    """把糊好的小图按双线性放大，铺成投影。over=False 时 buf 还是空的，直接写字节。"""
    cr, cg, cb = col
    for y in range(H):
        fy = (y + 0.5) / step - 0.5
        j0 = min(mh - 1, max(0, int(fy)))
        j1 = min(mh - 1, j0 + 1)
        wy = min(1.0, max(0.0, fy - j0))
        r0, r1 = j0 * mw, j1 * mw
        if max(m[r0:r0 + mw]) <= 0.004 and max(m[r1:r1 + mw]) <= 0.004:
            continue
        row = y * W * 4
        sx0, sx1 = (skip[0], skip[2]) if (skip and skip[1] <= y <= skip[3]) else (1, 0)
        for x in range(W):
            if sx0 <= x <= sx1:     # 底板自己会盖住的部分不用画投影（省掉大半的像素）
                continue
            fx = (x + 0.5) / step - 0.5
            i0 = min(mw - 1, max(0, int(fx)))
            i1 = min(mw - 1, i0 + 1)
            wx = min(1.0, max(0.0, fx - i0))
            v = ((m[r0 + i0] * (1 - wx) + m[r0 + i1] * wx) * (1 - wy)
                 + (m[r1 + i0] * (1 - wx) + m[r1 + i1] * wx) * wy)
            a = amax * v
            if a <= 0.004:
                continue
            i = row + x * 4
            da = buf[i + 3] / 255.0 if over else 0.0
            if da <= 0.004:
                buf[i:i + 4] = bytes((cr, cg, cb, min(255, int(a * 255 + 0.5))))
                continue
            na = a + da * (1 - a)
            buf[i + 3] = min(255, int(na * 255 + 0.5))


BAYER = (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)   # 4×4 有序抖动：大面积渐层不起色带


def make_plate(spec: dict, cache_dir: str) -> Tuple[str, int]:
    """按 spec 生成底板 PNG（带缓存）。返回 (路径, 外扩边距)。

    spec: w,h,radius,fill(单色或[上,下]),alpha,border{w,color},shadow{soft,alpha,dy}
    """
    # 画法改了就把 PLATE_VER 加一：旧缓存自动失效
    key = hashlib.sha1((PLATE_VER + json.dumps(spec, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:16]
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "plate_%s.png" % key)
    sh = spec.get("shadow") or {}
    # 环境光影比主投影铺得更开（soft×1.7）：边距要留够，否则投影会被画布切掉、出现一条硬边
    margin = int(math.ceil(sh.get("soft", 0) * 1.9 + abs(sh.get("dy", 0)) + float(sh.get("spread", 0)) + 2)) \
        if sh and sh.get("alpha", 0) > 0 else 2
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
        opaque = bool(spec.get("fill")) and float(spec.get("alpha", 1.0)) >= 0.9 and not spec.get("scrim")
        # 只跳过「一定被底板盖住」的中间那块：四角是圆的，跳过整个外框会让角上少一块投影
        skip = ((int(cx - hw + 2), int(cy - hh + r + 2), int(cx + hw - 2), int(cy + hh - r - 2))
                if opaque else ())
        soft = max(1.0, float(sh.get("soft", 18)))
        spread = float(sh.get("spread", 0.0))
        step = max(1, int(soft / 5) or 1)        # 投影是低频的：先缩小再糊，快很多、也更柔
        if sh.get("ambient", True):              # 更大更淡的环境光影：先铺在底下，层次更像真的
            st2 = max(1, int(soft / 2.5) or 1)
            mw2, mh2 = max(1, W // st2), max(1, H // st2)
            m2 = _blur(_mask(W, H, cx, cy + soft * 0.25, hw, hh, r, st2), mw2, mh2,
                       max(1, int(round(soft * 1.7 / st2 / 1.6))))
            _put_shadow(buf, W, H, m2, mw2, mh2, st2, sc, float(sh["alpha"]) * 0.36, skip=skip)
        mw, mh = max(1, W // step), max(1, H // step)
        m = _mask(W, H, cx + sh.get("dx", 0), cy + sh.get("dy", 0),
                  hw + float(sh.get("spread", 0.0)), hh + float(sh.get("spread", 0.0)),
                  r + float(sh.get("spread", 0.0)), step)
        m = _blur(m, mw, mh, max(1, int(round(soft / step / 1.6))))
        _put_shadow(buf, W, H, m, mw, mh, step, sc, float(sh["alpha"]), over=True, skip=skip)

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
        mid = sc.get("dir") == "mid"
        for y in range(H):
            t = min(1.0, max(0.0, (y - margin) / float(max(1, h - 1))))
            if mid:                                      # mid：中间最深，往上下两头渐渐透明
                t = abs(t - 0.5) * 2.0
            elif up:                                     # up：最深在下沿
                t = 1.0 - t
            hold = float(sc.get("hold", 0.0))             # 最深的一头先保持这么大比例，再渐渐透明
            t = 0.0 if t <= hold else (t - hold) / max(1e-6, 1.0 - hold)
            a8 = int(round(255 * a0 * (1.0 - t) ** pw))
            row = y * W * 4
            buf[row:row + W * 4] = bytes((col[0], col[1], col[2], a8)) * W

    fill = spec.get("fill") if not sc else None
    alpha = float(spec.get("alpha", 1.0))
    if fill:
        stops = [hex_rgb(fill)] if isinstance(fill, str) else [hex_rgb(c) for c in fill]
        if len(stops) == 1:
            stops = stops * 2
        top_y, span = cy - hh, max(1.0, 2 * hh)

        def grad(y: int, _st=stops, _y0=top_y, _s=span, _row=[0]) -> RGB:
            p = min(1.0, max(0.0, (y + 0.5 - _y0) / _s)) * (len(_st) - 1)
            k = min(len(_st) - 2, int(p))
            f = p - k
            a_, b_ = _st[k], _st[k + 1]
            # 有序抖动：整行同一个偏移，8 位深的大面积渐层就不会出现一圈圈色带
            d = (BAYER[(y & 3) * 4 + (y >> 2 & 3)] / 16.0 - 0.5)
            return tuple(min(255, max(0, int(a_[i] + (b_[i] - a_[i]) * f + d))) for i in range(3))

        ang = spec.get("angle")
        gxy = None
        if ang is not None:            # 斜向渐层：沿指定角度投影取色（90°＝原本的上下渐层）
            th_ = math.radians(float(ang))
            ux, uy = math.cos(th_), math.sin(th_)
            xs = (cx - hw, cx + hw)
            ys = (cy - hh, cy + hh)
            ps = [x * ux + y * uy for x in xs for y in ys]
            lo, span2 = min(ps), max(1e-6, max(ps) - min(ps))

            def gxy(x, y, _st=stops, _u=(ux, uy), _lo=lo, _s=span2):
                p = min(1.0, max(0.0, ((x + 0.5) * _u[0] + (y + 0.5) * _u[1] - _lo) / _s)) * (len(_st) - 1)
                k = min(len(_st) - 2, int(p))
                fk = p - k
                a_, b_ = _st[k], _st[k + 1]
                d = (BAYER[(y & 3) * 4 + (x & 3)] / 16.0 - 0.5)
                return tuple(min(255, max(0, int(a_[i] + (b_[i] - a_[i]) * fk + d))) for i in range(3))

        bd = spec.get("border") or {}
        bw = float(bd.get("w", 0))
        if bw > 0:
            bc = hex_rgb(bd.get("color", "#ffffff"))
            paint(buf, W, H, cx, cy, hw, hh, r, lambda _y: bc, min(1.0, alpha + 0.08))
            paint(buf, W, H, cx, cy, hw - bw, hh - bw, max(0.0, r - bw), grad, alpha, color_xy=gxy)
        else:
            paint(buf, W, H, cx, cy, hw, hh, r, grad, alpha, color_xy=gxy)

    gn = float(spec.get("grain", 0.0))
    if fill and gn > 0 and not sc:
        # 细噪点：底板上一层极淡颗粒，近看有质感、远看察觉不到（也进一步压掉大色块的塑料感）
        amp = max(1, int(round(gn * 255)))
        rnd = random.Random(hash((w, h, int(gn * 1000))) & 0xFFFF)
        for y in range(max(0, int(cy - hh)), min(H, int(cy + hh) + 1)):
            hs = _halfspan(hw - 0.5, hh - 0.5, r, abs(y + 0.5 - cy))
            if hs <= 0:
                continue
            row = y * W * 4
            for x in range(max(0, int(cx - hs + 1)), min(W, int(cx + hs - 1))):
                i = row + x * 4
                if not buf[i + 3]:
                    continue
                n_ = rnd.randint(-amp, amp)
                for k2 in range(3):
                    buf[i + k2] = min(255, max(0, buf[i + k2] + n_))

    sheen = float(spec.get("sheen", 0.0))
    if fill and sheen > 0 and not sc:
        # 顶部一层极淡的高光：像光从上面打下来，底板不再是一块死板的色
        band = max(8.0, hh * 0.9)
        for y in range(max(0, int(cy - hh)), min(H, int(cy - hh + band))):
            k = 1.0 - (y - (cy - hh)) / band
            a = sheen * k * k
            if a <= 0.002:
                continue
            hs = _halfspan(hw - 0.5, hh - 0.5, r, abs(y + 0.5 - cy))
            if hs <= 0:
                continue
            row = y * W * 4
            for x in range(max(0, int(cx - hs + 1)), min(W, int(cx + hs - 1))):
                i = row + x * 4
                if not buf[i + 3]:
                    continue
                for k2 in range(3):
                    buf[i + k2] = min(255, int(buf[i + k2] + (255 - buf[i + k2]) * a))

    pat = spec.get("pattern")
    if pat and fill and not sc:
        # 风格的签名底纹：网格／点阵／斜线，淡淡一层烤进底板（渲染时不额外花时间）
        kind = pat.get("kind", "grid")
        pc = hex_rgb(pat.get("color", "#FFFFFF"))
        pa = float(pat.get("alpha", 0.05))
        gs = max(6, int(pat.get("size", 28)))
        th_ = max(1, int(pat.get("w", 1)))
        x0, y0 = int(cx - hw), int(cy - hh)
        for y in range(max(0, y0), min(H, int(cy + hh))):
            hs = _halfspan(hw - 1.0, hh - 1.0, r, abs(y + 0.5 - cy))
            if hs <= 0:
                continue
            xa, xb = max(0, int(cx - hs + 1)), min(W, int(cx + hs - 1))
            row = y * W * 4
            dy_ = (y - y0) % gs
            for x in range(xa, xb):
                dx_ = (x - x0) % gs
                if kind == "grid":
                    on = dy_ < th_ or dx_ < th_
                elif kind == "dots":
                    on = dy_ < th_ + 1 and dx_ < th_ + 1
                else:                                  # diag：斜线
                    on = ((x - x0) + (y - y0)) % gs < th_
                if not on:
                    continue
                i = row + x * 4
                if not buf[i + 3]:
                    continue
                for k2 in range(3):
                    buf[i + k2] = min(255, max(0, int(buf[i + k2] + (pc[k2] - buf[i + k2]) * pa)))

    tb = spec.get("topbar")
    if tb and fill and not sc:   # 杂志风的顶部色条
        bh_ = max(2, int(tb.get("h", 8)))
        bc = hex_rgb(tb.get("color", "#000000"))
        for y in range(max(0, int(cy - hh)), min(H, int(cy - hh) + bh_)):
            hs = _halfspan(hw - 0.5, hh - 0.5, r, abs(y + 0.5 - cy))
            if hs <= 0:
                continue
            row = y * W * 4
            for x in range(max(0, int(cx - hs + 1)), min(W, int(cx + hs - 1))):
                i = row + x * 4
                if buf[i + 3]:
                    buf[i:i + 3] = bytes(bc)

    cn = spec.get("corners")
    if cn and fill and not sc:   # 衬线风的四角标记
        ln = max(8, int(cn.get("len", 26)))
        cw_ = max(1, int(cn.get("w", 2)))
        cc = hex_rgb(cn.get("color", "#000000"))
        ca = float(cn.get("alpha", 0.45))
        inset = int(cn.get("inset", 14))
        for sx in (0, 1):
            for sy in (0, 1):
                bx = int(cx - hw + inset) if sx == 0 else int(cx + hw - inset - ln)
                by = int(cy - hh + inset) if sy == 0 else int(cy + hh - inset - cw_)
                for yy in range(by, min(H, by + cw_)):          # 横画
                    for xx in range(max(0, bx), min(W, bx + ln)):
                        i = (yy * W + xx) * 4
                        if buf[i + 3]:
                            for k2 in range(3):
                                buf[i + k2] = int(buf[i + k2] + (cc[k2] - buf[i + k2]) * ca)
                vy = int(cy - hh + inset) if sy == 0 else int(cy + hh - inset - ln)
                vx = int(cx - hw + inset) if sx == 0 else int(cx + hw - inset - cw_)
                for yy in range(max(0, vy), min(H, vy + ln)):   # 竖画
                    for xx in range(max(0, vx), min(W, vx + cw_)):
                        i = (yy * W + xx) * 4
                        if buf[i + 3]:
                            for k2 in range(3):
                                buf[i + k2] = int(buf[i + k2] + (cc[k2] - buf[i + k2]) * ca)

    # 圆弧（进度圈）：按角度切一段圆环
    for ac in spec.get("arcs") or []:
        acx, acy = margin + ac["cx"], margin + ac["cy"]
        rr, tw = float(ac["r"]), float(ac["w"])
        col = hex_rgb(ac.get("color", "#FFFFFF"))
        a0 = math.radians(float(ac.get("a0", -90.0)))
        a1 = math.radians(float(ac.get("a1", 270.0)))
        al = float(ac.get("alpha", 1.0))
        y0 = max(0, int(acy - rr - tw)); y1 = min(H - 1, int(acy + rr + tw) + 1)
        for y in range(y0, y1 + 1):
            dy = y + 0.5 - acy
            for x in range(max(0, int(acx - rr - tw)), min(W - 1, int(acx + rr + tw)) + 1):
                dx = x + 0.5 - acx
                d = abs(math.hypot(dx, dy) - rr) - tw / 2.0
                if d > 0.7:
                    continue
                ang = math.atan2(dy, dx)
                while ang < a0:
                    ang += 2 * math.pi
                if ang > a1:                       # 端点做个圆头，收尾不会切得死板
                    e = min(abs(ang - a1), abs(ang - a0 - 2 * math.pi)) * rr
                    if e > tw / 2.0:
                        continue
                    d = max(d, math.hypot(e - tw / 2.0, 0))
                a = al * min(1.0, max(0.0, 0.5 - d))
                if a <= 0.004:
                    continue
                i = (y * W + x) * 4
                da = buf[i + 3] / 255.0
                na = a + da * (1 - a)
                for k2 in range(3):
                    buf[i + k2] = int(round((col[k2] * a + buf[i + k2] * da * (1 - a)) / na)) if na else 0
                buf[i + 3] = int(round(na * 255))

    for st_ in spec.get("stars") or []:
        # 评分星：满星实心、空星描边，半星按比例横向裁（4.6 分就是四颗满星＋一颗 60% 的星）
        scx, scy = margin + st_["cx"], margin + st_["cy"]
        rr = float(st_["r"])
        frac = min(1.0, max(0.0, float(st_.get("frac", 1.0))))
        fc = hex_rgb(st_.get("color", "#FFC933"))
        tc = hex_rgb(st_.get("track", "#888890"))
        pts = []
        for i in range(10):
            a_ = -math.pi / 2 + i * math.pi / 5
            k = rr if i % 2 == 0 else rr * 0.45
            pts.append((scx + k * math.cos(a_), scy + k * math.sin(a_)))
        cut = scx - rr + 2 * rr * frac
        y0 = max(0, int(scy - rr - 2)); y1 = min(H - 1, int(scy + rr + 2))
        for y in range(y0, y1 + 1):
            row = y * W * 4
            for x in range(max(0, int(scx - rr - 2)), min(W - 1, int(scx + rr + 2)) + 1):
                cov = 0.0
                for oy in (0.25, 0.75):          # 2×2 超采样：星角不锯齿
                    for ox in (0.25, 0.75):
                        px_, py_ = x + ox, y + oy
                        inside = False
                        j = len(pts) - 1
                        for i2 in range(len(pts)):
                            xi, yi = pts[i2]
                            xj, yj = pts[j]
                            if (yi > py_) != (yj > py_) and px_ < (xj - xi) * (py_ - yi) / (yj - yi + 1e-9) + xi:
                                inside = not inside
                            j = i2
                        if inside:
                            cov += 0.25
                if cov <= 0.004:
                    continue
                col = fc if x + 0.5 <= cut else tc
                a = cov * (1.0 if x + 0.5 <= cut else float(st_.get("track_alpha", 0.30)))
                i3 = row + x * 4
                da = buf[i3 + 3] / 255.0
                na = a + da * (1 - a)
                for k2 in range(3):
                    buf[i3 + k2] = int(round((col[k2] * a + buf[i3 + k2] * da * (1 - a)) / na)) if na else 0
                buf[i3 + 3] = int(round(na * 255))

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
                     ic["color"], float(ic.get("stroke", 2.0)), ic.get("badge"),
                     ic.get("style", "line"), ic.get("tint"))

    write_rgba(path, W, H, buf)
    return path, margin
