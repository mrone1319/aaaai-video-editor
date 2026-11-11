"""整屏特效：缩成手机框（phone）、调色前后对比（split）、滑下一支（swipe）、底片感（film）。

和转场一样只动那一段时间的帧（按帧号切成前／特效／后三段再接回去），片长不变；
放在画面调色之后、卡片与字幕之前——卡片、字幕不跟着缩、不被调色。装饰（手机外框、时间码、
进度条、分割线把手、前后标签）画成 ASS 矢量，和卡片同一次烧上（见 decor_lines）。

storyboard：
  "postfx": [{"t": [12.0, 15.0], "type": "phone"},
             {"t": [20.0, 23.0], "type": "split", "labels": ["调色前", "调色后"]},
             {"t": [30.0, 33.0], "type": "swipe", "file": "assets/滑reels录屏.mp4", "start": 2.0, "speed": 1.6},
             {"t": [40.0, 43.0], "type": "film"}]
  phone：scale（缩到多大，默认 0.66）、bg（背景色，默认深绿）、timecode（默认开）
  split：labels、before（"flat" 灰平｜"bw" 黑白）
  swipe：file（手机滑 Reels 的屏幕录像）、start（从第几秒开始）、speed（倍速，默认 1.5）、crop_top／crop_bottom（0–1）
  film：leak（漏光，默认开）、bars（上下黑边，默认开）、shake（轻微抖动，默认开）、grain（颗粒强度，默认 1）
"""
from __future__ import annotations

import math
import os
from typing import List, Optional, Tuple

TYPES = ("phone", "split", "swipe", "film")
EASE = 0.38    # 进出动画时长（秒）
GREEN = "#10261C"
CREAM = "#F6F0E2"
YELLOW = "#FEDA62"


def items(sb: dict) -> List[dict]:
    out = []
    for x in sb.get("postfx") or []:
        if x.get("type") not in TYPES:
            from . import env
            raise env.ToolError("postfx 没有这种特效：%s（可用：%s）" % (x.get("type"), "、".join(TYPES)))
        out.append(x)
    return sorted(out, key=lambda x: float(x["t"][0]))


# ---------------------------------------------------------------- 时间曲线（Python 与 ffmpeg 表达式同一条）
def phone_scale(u: float, d: float, s0: float) -> float:
    """手机框：前 EASE 秒缩进去、最后 EASE 秒放回来（三次缓动）。"""
    e = min(EASE, d / 3.0)
    if u < e:
        p = u / e
        k = 1 - (1 - p) ** 3
    elif u > d - e:
        p = (d - u) / e
        k = 1 - (1 - max(0.0, p)) ** 3
    else:
        k = 1.0
    return 1.0 - (1.0 - s0) * k


def _phone_expr(d: float, s0: float) -> str:
    e = min(EASE, d / 3.0)
    k = ("if(lt(t\\,%.4f)\\,1-pow(1-t/%.4f\\,3)\\,if(gt(t\\,%.4f)\\,1-pow(1-max(0\\,(%.4f-t)/%.4f)\\,3)\\,1))"
         % (e, e, d - e, d, e))
    return "(1-%.4f*%s)" % (1.0 - s0, k)


def split_pos(u: float, d: float) -> float:
    """前后对比的分割线位置（0–1，左边是「前」）：0.45 秒滑到中间，之后慢慢左右摆，最后 0.3 秒滑到右边收掉。"""
    e = min(0.45, d / 3.0)
    if u < e:
        p = u / e
        return 0.5 * (1 - (1 - p) ** 3)
    x = 0.5 + 0.20 * math.sin(2 * math.pi * (u - e) / max(1.6, (d - e) * 0.9))
    return x


def _split_expr(d: float) -> str:
    e = min(0.45, d / 3.0)
    return ("if(lt(T\\,%.4f)\\,0.5*(1-pow(1-T/%.4f\\,3))\\,0.5+0.20*sin(2*PI*(T-%.4f)/%.4f))"
            % (e, e, e, max(1.6, (d - e) * 0.9)))


def swipe_off(u: float, d: float) -> float:
    """滑下一支：主画面往上滑走的比例（0＝在原位，1＝整个滑出去）。前 EASE 秒滑走、最后 EASE 秒带一点回弹滑回来。"""
    e = min(EASE, d / 3.0)
    if u < e:
        p = u / e
        return 1 - (1 - p) ** 3
    if u > d - e:
        p = (d - u) / e   # 1 → 0
        q = 1 - p
        return 1 - (1 + 2.2 * (q - 1) ** 3 + 1.2 * (q - 1) ** 2)
    return 1.0


def _swipe_expr(d: float) -> str:
    e = min(EASE, d / 3.0)
    q = "(1-(%.4f-t)/%.4f)" % (d, e)
    back = "(1-(1+2.2*pow(%s-1\\,3)+1.2*pow(%s-1\\,2)))" % (q, q)
    return "if(lt(t\\,%.4f)\\,1-pow(1-t/%.4f\\,3)\\,if(gt(t\\,%.4f)\\,%s\\,1))" % (e, e, d - e, back)


# ---------------------------------------------------------------- 滤镜图
def _hex(c: str) -> str:
    return "0x" + c.lstrip("#")


def _leak_png(W: int, H: int, work: str) -> str:
    """漏光：一团暖橘色的径向光，四分之一解析度画好再放大（纯 Python、按尺寸缓存）。"""
    from .png import write_rgba
    w, h = max(8, W // 4), max(8, H // 4)
    p = os.path.join(work, "plates", "leak_%dx%d.png" % (w, h))
    if os.path.isfile(p):
        return p
    os.makedirs(os.path.dirname(p), exist_ok=True)
    buf = bytearray(w * h * 4)
    cx, cy, r = w * 0.5, h * 0.42, max(w, h) * 0.55
    for y in range(h):
        for x in range(w):
            dd = math.hypot((x - cx) / r, (y - cy) / (r * 1.25))
            a = max(0.0, 1.0 - dd) ** 1.8
            if a <= 0.004:
                continue
            i = (y * w + x) * 4
            buf[i:i + 4] = bytes((255, int(140 + 60 * a), int(60 + 40 * a), int(a * 170)))
    write_rgba(p, w, h, buf)
    return p


def graph(src: str, dst: str, fxs: List[dict], W: int, H: int, fps: float, t_off: float, seg_len: Optional[float],
          base: str, work: str, next_input: int) -> Tuple[Optional[str], List[str]]:
    """回传 (滤镜图片段 src → dst, 额外输入参数)；这一段里没有整屏特效就回传 (None, [])。"""
    f = float(fps)
    wins = []
    for x in fxs:
        a, b = float(x["t"][0]) - t_off, float(x["t"][1]) - t_off
        if b <= 0 or (seg_len is not None and a >= seg_len):
            continue
        fa, fb = max(0, int(round(a * f))), int(round(b * f))
        if seg_len is not None:
            fb = min(fb, int(round(seg_len * f)))
        if fb - fa >= 3:
            wins.append((fa, fb, x))
    if not wins:
        return None, []
    segs, cur = [], 0
    for fa, fb, x in wins:
        fa = max(fa, cur)
        if fb <= fa:
            continue
        if fa > cur:
            segs.append((cur, fa, None))
        segs.append((fa, fb, x))
        cur = fb
    segs.append((cur, None, None))
    n = len(segs)
    extra: List[str] = []
    parts = ["%ssplit=%d%s" % (src, n, "".join("[pq%d]" % i for i in range(n)))]
    for i, (a, b, x) in enumerate(segs):
        lab = "pq%d" % i
        parts.append("[%s]trim=start_frame=%d%s,setpts=PTS-STARTPTS[pr%d]"
                     % (lab, a, (":end_frame=%d" % b) if b is not None else "", i))
        if x is None:
            parts.append("[pr%d]format=yuv420p,setsar=1[po%d]" % (i, i))
            continue
        d = (b - a) / f
        typ = x["type"]
        k = "%d" % i
        if typ == "phone":
            s0 = float(x.get("scale", 0.66))
            se = _phone_expr(d, s0)
            parts.append("[pr%s]split=2[pa%s][pb%s]" % (k, k, k))
            parts.append("[pa%s]drawbox=x=0:y=0:w=iw:h=ih:color=%s:t=fill[pg%s]" % (k, _hex(x.get("bg") or GREEN), k))
            parts.append("[pb%s]scale=w='trunc(%d*%s/2)*2':h='trunc(%d*%s/2)*2':eval=frame[ps%s]" % (k, W, se, H, se, k))
            parts.append("[pg%s][ps%s]overlay=x='(W-w)/2':y='(H-h)/2':eval=frame:shortest=1[po%s]" % (k, k, i))
        elif typ == "split":
            before = x.get("before", "flat")
            bf = ("hue=s=0" if before == "bw" else "eq=contrast=0.80:saturation=0.45:brightness=0.03:gamma=1.06")
            parts.append("[pr%s]split=2[pa%s][pb%s]" % (k, k, k))
            parts.append("[pa%s]%s,format=yuv420p[pf%s]" % (k, bf, k))
            parts.append("[pb%s]eq=contrast=1.10:saturation=1.22,colorbalance=rs=0.05:gs=0.01:bs=-0.06:rm=0.04:bm=-0.04,"
                         "format=yuv420p[pt%s]" % (k, k))
            parts.append("[pf%s][pt%s]blend=all_expr='if(lt(X\\,W*(%s))\\,A\\,B)'[po%s]" % (k, k, _split_expr(d), i))
        elif typ == "swipe":
            fp = os.path.normpath(os.path.join(base, x["file"]))
            if not os.path.isfile(fp):
                from . import env
                raise env.ToolError("滑下一支找不到屏幕录像：%s" % fp)
            sp = max(0.25, float(x.get("speed", 1.5)))
            extra += ["-stream_loop", "-1", "-ss", "%.3f" % float(x.get("start", 0.0)), "-t", "%.3f" % (d * sp + 0.5),
                      "-i", fp]
            ct, cb = float(x.get("crop_top", 0.0)), float(x.get("crop_bottom", 0.0))
            parts.append("[%d:v]crop=iw:ih*%.4f:0:ih*%.4f,setpts=(PTS-STARTPTS)/%.4f,fps=%s,"
                         "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,format=yuv420p,"
                         "trim=duration=%.4f[pc%s]"
                         % (next_input, max(0.05, 1 - ct - cb), ct, sp, fps, W, H, W, H, d, k))
            next_input += 1
            parts.append("[pc%s][pr%s]overlay=x=0:y='-%d*(%s)':eval=frame:shortest=1[po%s]" % (k, k, H, _swipe_expr(d), i))
        elif typ == "film":
            g = float(x.get("grain", 1.0))
            ch = ("colorbalance=rs=0.07:gs=0.02:bs=-0.07:rh=0.05:bh=-0.05,eq=contrast=1.08:saturation=0.86:gamma=0.97,"
                  "vignette=angle=PI/4.2,noise=alls=%d:allf=t" % int(round(12 * g)))
            if x.get("shake", True):   # 轻微抖动：放大一点再按两个不相关的正弦慢慢晃
                m = max(4, int(W * 0.006))
                ch += (",scale=%d:%d,crop=%d:%d:x='%d+%d*sin(t*7.3)*sin(t*2.1)':y='%d+%d*sin(t*5.9+1)*sin(t*1.7)'"
                       % (W + 2 * m, H + 2 * m, W, H, m, m - 1, m, m - 1))
            parts.append("[pr%s]%s[pm%s]" % (k, ch, k))
            cur_l = "pm" + k
            if x.get("leak", True):
                lp = _leak_png(W, H, work)
                extra += ["-loop", "1", "-t", "%.3f" % (d + 0.2), "-i", os.path.relpath(lp, work)]
                parts.append("[%d:v]scale=%d:%d,format=rgba[pl%s]" % (next_input, int(W * 1.2), int(H * 1.0), k))
                next_input += 1
                parts.append("[%s][pl%s]overlay=x='-%d+%d*sin(t*0.9)':y=0:eval=frame:shortest=1[pn%s]"
                             % (cur_l, k, int(W * 0.55), int(W * 0.45), k))
                cur_l = "pn" + k
            if x.get("bars", True):
                bh = int(H * 0.075) & ~1
                parts.append("[%s]drawbox=x=0:y=0:w=iw:h=%d:color=black:t=fill,drawbox=x=0:y=ih-%d:w=iw:h=%d:color=black:t=fill[po%s]"
                             % (cur_l, bh, bh, bh, i))
            else:
                parts.append("[%s]null[po%s]" % (cur_l, i))
        else:
            parts.append("[pr%s]null[po%s]" % (k, i))
        last = parts[-1]   # 各段接回去之前格式要一致
        parts[-1] = last[:last.rfind("[")] + ",format=yuv420p,setsar=1[po%d]" % i
    parts.append("%sconcat=n=%d:v=1:a=0%s" % ("".join("[po%d]" % i for i in range(n)), n, dst))
    return ";".join(parts), extra


# ---------------------------------------------------------------- 装饰（ASS）
def decor_lines(fxs: List[dict], W: int, H: int, fps: float, t_off: float = 0.0) -> List[str]:
    """手机外框＋时间码＋进度条、分割线＋把手＋前后标签：跟着同一条曲线逐帧画。"""
    from . import richtext, sticker
    out: List[str] = []
    fam = sticker.family("Yuanti SC")
    mono = sticker.family("Menlo")
    U = float(min(W, H))
    bw, _sd = sticker._lines(U)
    ink = "&H0B0A0A&"

    def ev(a, b, layer, tags, body):
        out.append("Dialogue: %d,%s,%s,C,,0,0,0,,{%s}%s" % (layer, richtext._ts(max(0.0, a)), richtext._ts(max(0.0, b)),
                                                          tags, body))
    for x in fxs:
        a, b = float(x["t"][0]) - t_off, float(x["t"][1]) - t_off
        if b <= 0:
            continue
        d = b - a
        f0, f1 = int(round(a * fps)), int(round(b * fps))
        if x["type"] == "phone":
            s0 = float(x.get("scale", 0.66))
            for fr in range(f0, f1):
                u = fr / fps - a
                s = phone_scale(u, d, s0)
                vw, vh = W * s, H * s
                pad = U * 0.022 * (1 - s) / (1 - s0 + 1e-6)
                rr = U * 0.07 * (1 - s) / (1 - s0 + 1e-6)
                ta, tb = (fr - 0.5) / fps, (fr + 0.5) / fps
                if pad > 0.5:   # 米白手机外框（中间挖空，盖住画面的方角）
                    cm = sticker.rrect(0, 0, vw + 2 * pad, vh + 2 * pad, rr + pad) + \
                        sticker.rrect(pad, pad, vw, vh, rr, ccw=True)
                    p, _w, _h, _c, _d = sticker.shape_of(cm)
                    ev(ta, tb, 40, "\\an5\\pos(%.1f,%.1f)\\bord%.1f\\3c%s\\shad0\\1c%s\\p1" % (
                        W / 2, H / 2, bw * 0.8, ink, sticker._ac(CREAM)), p)
                k = (1 - s) / (1 - s0 + 1e-6)
                if x.get("timecode", True) and k > 0.05:
                    tt = fr / fps + t_off - float(x["t"][0])
                    tc = "00:%02d:%02d:%02d" % (int(tt) // 60, int(tt) % 60, int(round((tt % 1) * fps)) % int(fps))
                    alpha = "&H%02X&" % int(255 * (1 - min(1.0, k)))
                    ev(ta, tb, 41, "\\an2\\pos(%.1f,%.1f)\\fn%s\\fs%.1f\\b1\\bord0\\shad0\\c%s\\alpha%s" % (
                        W / 2, H / 2 - vh / 2 - pad - U * 0.025, mono, U * 0.042, sticker._ac(YELLOW), alpha), tc)
                    # 进度条：底轨＋走过的部分
                    by = H / 2 + vh / 2 + pad + U * 0.045
                    bwid = vw * 0.86
                    prog = min(1.0, max(0.0, (fr / fps - a) / d))
                    tp, *_ = sticker.shape_of(sticker.rrect(0, 0, bwid, U * 0.010, U * 0.005))
                    ev(ta, tb, 41, "\\an5\\pos(%.1f,%.1f)\\bord0\\shad0\\1c&HFFFFFF&\\1a&HB0&\\alpha%s\\p1" % (
                        W / 2, by, alpha), tp)
                    if prog > 0.01:
                        pp, *_ = sticker.shape_of(sticker.rrect(0, 0, bwid * prog, U * 0.010, U * 0.005))
                        ev(ta, tb, 42, "\\an4\\pos(%.1f,%.1f)\\bord0\\shad0\\1c%s\\alpha%s\\p1" % (
                            W / 2 - bwid / 2, by, sticker._ac(YELLOW), alpha), pp)
        elif x["type"] == "split":
            lab = x.get("labels") or ["调色前", "调色后"]
            hw = U * 0.006
            for fr in range(f0, f1):
                u = fr / fps - a
                px = W * split_pos(u, d)
                ta, tb = (fr - 0.5) / fps, (fr + 0.5) / fps
                lp, *_ = sticker.shape_of(sticker.rrect(0, 0, hw, H, 0))
                ev(ta, tb, 40, "\\an5\\pos(%.1f,%.1f)\\bord0\\shad0\\1c&HFFFFFF&\\p1" % (px, H / 2), lp)
                kr = U * 0.045   # 把手：白圆＋左右箭头
                kp, *_ = sticker.shape_of(sticker.ellipse(kr, kr, kr, kr))
                ev(ta, tb, 41, "\\an5\\pos(%.1f,%.1f)\\bord%.1f\\3c%s\\shad0\\1c&HFFFFFF&\\p1" % (px, H * 0.5, bw * 0.7, ink), kp)
                ap, *_ = sticker.shape_of(sticker.poly([(0, kr * 0.35), (kr * 0.35, 0), (kr * 0.35, kr * 0.7)])
                                          + sticker.poly([(kr * 1.0, 0), (kr * 1.35, kr * 0.35), (kr * 1.0, kr * 0.7)]))
                ev(ta, tb, 42, "\\an5\\pos(%.1f,%.1f)\\bord0\\shad0\\1c%s\\p1" % (px, H * 0.5, ink), ap)
                for side, txt in ((0, lab[0]), (1, lab[1] if len(lab) > 1 else "")):
                    if not txt:
                        continue
                    em = U * 0.040
                    tw = sticker.text_w(txt, em, fam) + em * 1.0
                    cx = px - U * 0.03 - tw / 2 if side == 0 else px + U * 0.03 + tw / 2
                    bp, *_ = sticker.shape_of(sticker.rrect(0, 0, tw, em * 1.6, em * 0.8))
                    col = "&H000000&" if side == 0 else sticker._ac(YELLOW)
                    tcol = "&HFFFFFF&" if side == 0 else ink
                    ev(ta, tb, 43, "\\an5\\pos(%.1f,%.1f)\\bord0\\shad0\\1c%s\\1a&H30&\\p1" % (cx, H * 0.40, col), bp)
                    ev(ta, tb, 44, "\\an5\\pos(%.1f,%.1f)\\fn%s\\fs%.1f\\b1\\bord0\\shad0\\c%s" % (
                        cx, H * 0.40, fam, sticker.fs_tag(em, fam), tcol), richtext._esc(txt))
    return out
