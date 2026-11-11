"""贴纸弹跳（Sticker Pop）：黑粗描边＋右下硬投影的贴纸卡片、斜标签、打字框、重砸大字、彩纸小爆发。

来源是街头口播短视频的「贴纸」包装：卡片贴在胸口区域（画面 35–70%，不挡脸），一张约 1–1.5 秒；
弹出带回弹、伴一小簇彩纸；台词逐字打进白框；斜标签压在框角；关键词三种强调（粉字、黄色荧光笔底条、
粉色实底块）；重砸大字；先出空心描边再填满；斜向黄色色带扫过当转场；手形光标点按的行动号召。

全部画成 ASS 矢量图形交给 libass（与富文本卡片同一次 subtitles 滤镜，不增加编码）。
每个元素有自己的入场／出场曲线：动画期间逐帧采样成一行 Dialogue（事件边界落在两帧正中间，
厘秒取整也不会跳帧或重复帧），静止期间只写一行。图片类（拍立得、扇形、翻面）走 ffmpeg 图层（overlays）。

storyboard（t 是成片秒数；卡片里的其他时间都是「相对卡片开始」的秒数，分段渲染不用换算）：
  {"type": "sticker", "kind": "box", "t": [2.0, 3.4], "text": "我**不想**拍==短视频==", "tag": "只需"}
  kind：box 台词框｜tag 斜标签｜slam 重砸大字｜icon 卡通贴纸图标｜badge 圆环计数｜checklist 打勾清单｜
        cta 点击按钮＋手形光标｜wipe 斜色带转场（transitions 写 "type": "band" 会自动加）｜
        polaroid 拍立得照片｜fan 扇形卡片｜flip 翻面卡片（后三种是图片，见 overlays）
  通用：xy [中心 x, 中心 y]（0–1）、rot（度，正＝顺时针）、scale、fill（pink｜yellow｜cream｜navy｜ink｜white｜#hex）、
        anim（pop｜slam｜rise｜drop｜slide｜ghost｜fade｜none）、out（fade｜pop｜cut）、burst（彩纸小爆发）、sfx（"" 关掉）
  文字标记：**粉字**　==黄色荧光笔底条==　[[粉色实底块]]　换行写 \\n
"""
from __future__ import annotations

import math
import random
import subprocess
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import env, richtext

INK = "#0A0A0B"
PALETTE = {"pink": "#FF4F9A", "yellow": "#FEDA62", "cream": "#FFFCF5", "navy": "#1D1B49",
           "ink": INK, "white": "#FFFFFF"}
KINDS = ("box", "tag", "slam", "icon", "badge", "checklist", "cta", "drop", "comment", "wipe",
         "polaroid", "fan", "flip", "grid")
IMAGE_KINDS = ("polaroid", "fan", "flip", "grid")
FONT_FALLBACK = "PingFang SC"


# ---------------------------------------------------------------- 颜色与主题
def color(c: Optional[str], th: dict, default: str = "cream") -> str:
    c = c or default
    if c.startswith("#"):
        return c
    if th.get("sticker_palette"):   # 贴纸系风格：粉／黄／奶油／海军蓝取风格自己的色板（可用 brand 覆盖）
        named = {"pink": th.get("accent"), "yellow": th.get("accent2"), "navy": th.get("navy"),
                 "cream": th.get("paper"), "ink": th.get("ink")}
        if named.get(c):
            return named[c]
    return PALETTE.get(c) or PALETTE["cream"]


def _dark(c: str) -> bool:
    h = c.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b < 140


def on(c: str, th: dict) -> str:
    """底色上的字色：深底白字、浅底墨字。"""
    return "#FFFFFF" if _dark(c) else (th.get("ink") or INK)


def _ac(hexc: str) -> str:
    h = hexc.lstrip("#")
    return "&H%s%s%s&" % (h[4:6], h[2:4], h[0:2])


def _aa(transp: float) -> str:
    return "&H%02X&" % int(round(min(1.0, max(0.0, transp)) * 255))


# ---------------------------------------------------------------- 字体与真实字宽
@lru_cache(maxsize=16)
def family(name: str) -> str:
    """风格指定的字体本机没有（例如圆体是 macOS 的可下载字体）就退回苹方。"""
    if env.WIN:
        return env.font_family(name) or name
    try:
        got = subprocess.run(["fc-match", "-f", "%{family}", name], capture_output=True, text=True).stdout
    except OSError:
        return name
    return name if name.split()[0].lower() in got.lower() else FONT_FALLBACK


@lru_cache(maxsize=16)
def _face(fam: str, bold: bool) -> Tuple[str, int]:
    if env.WIN:
        return richtext.locate(fam)
    for q in ([fam + ":style=Bold", fam + ":bold"] if bold else []) + [fam]:
        out = subprocess.run(["fc-match", "-f", "%{file}|%{index}", q], capture_output=True, text=True).stdout
        f, _, i = out.partition("|")
        if f:
            return f, int(i or 0)
    return "", 0


@lru_cache(maxsize=16)
def _font(fam: str, bold: bool):
    """(\\fs 换算倍率, 量字宽的函数)。"""
    path, idx = _face(fam, bold)
    try:
        win = richtext.metrics_file(path, idx)[0]
        upem, adv, cmap = richtext.advance_table(path, idx)
    except (OSError, KeyError, ValueError, Exception):   # 读不了字体：退回估算
        return 1.0, None

    def width(s: str) -> float:
        tot = 0
        for ch in s:
            g = cmap.get(ord(ch))
            tot += adv[min(g, len(adv) - 1)] if g is not None else (upem if ord(ch) > 0x2E80 else upem * 0.55)
        return tot / float(upem)
    return win, width


def text_w(s: str, em: float, fam: str, bold: bool = True) -> float:
    _w, fn = _font(fam, bold)
    if fn is None:
        return sum(1.0 if ord(c) > 0x2E80 else 0.56 for c in s) * em
    return fn(s) * em


def fs_tag(em: float, fam: str, bold: bool = True) -> float:
    return em * _font(fam, bold)[0]


# ---------------------------------------------------------------- 文字标记
MARKS = (("**", "pink"), ("==", "marker"), ("[[", "block"), ("]]", "block"))


def parse(text: str) -> List[Tuple[str, str]]:
    """「我**不想**拍==短视频==」→ [(字, 种类)]，种类：plain｜pink｜marker｜block｜nl。"""
    out: List[Tuple[str, str]] = []
    cur, i, s = "plain", 0, str(text).replace("\\n", "\n")
    while i < len(s):
        if s.startswith("**", i) or s.startswith("==", i):
            k = "pink" if s[i] == "*" else "marker"
            cur = "plain" if cur == k else k
            i += 2
            continue
        if s.startswith("[[", i):
            cur, i = "block", i + 2
            continue
        if s.startswith("]]", i):
            cur, i = "plain", i + 2
            continue
        out.append((s[i], "nl" if s[i] == "\n" else cur))
        i += 1
    return out


def wrap(chars: List[Tuple[str, str]], em: float, fam: str, maxw: float) -> List[List[Tuple[str, str]]]:
    """按真实字宽换行；英文词不拆开。"""
    lines: List[List[Tuple[str, str]]] = [[]]
    word: List[Tuple[str, str]] = []

    def lw(ln):
        return text_w("".join(c for c, _ in ln), em, fam)

    def flush():
        nonlocal word
        if not word:
            return
        if lines[-1] and lw(lines[-1] + word) > maxw:
            while lines[-1] and lines[-1][-1][0] == " ":
                lines[-1].pop()
            lines.append([])
            while word and word[0][0] == " ":
                word = word[1:]
        lines[-1].extend(word)
        word = []

    for ch, k in chars:
        if k == "nl":
            flush()
            lines.append([])
            continue
        if ord(ch) > 0x2E80 or ch == " ":
            flush()
            word = [(ch, k)]
            flush()
        else:
            word.append((ch, k))
    flush()
    return [ln for ln in lines if ln] or [[(" ", "plain")]]


# ---------------------------------------------------------------- 矢量路径（ASS \p1）
Cmd = Tuple[str, Tuple[float, ...]]


def rrect(x: float, y: float, w: float, h: float, r: float, ccw: bool = False) -> List[Cmd]:
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    k = 0.5523 * r
    pts = [("m", (x + r, y)), ("l", (x + w - r, y)),
           ("b", (x + w - r + k, y, x + w, y + r - k, x + w, y + r)), ("l", (x + w, y + h - r)),
           ("b", (x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h)), ("l", (x + r, y + h)),
           ("b", (x + r - k, y + h, x, y + h - r + k, x, y + h - r)), ("l", (x, y + r)),
           ("b", (x, y + r - k, x + r - k, y, x + r, y))]
    return _reverse(pts) if ccw else pts


def ellipse(cx: float, cy: float, rx: float, ry: float, ccw: bool = False) -> List[Cmd]:
    kx, ky = 0.5523 * rx, 0.5523 * ry
    pts = [("m", (cx, cy - ry)), ("b", (cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy)),
           ("b", (cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry)),
           ("b", (cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy)),
           ("b", (cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry))]
    return _reverse(pts) if ccw else pts


def poly(pts: Sequence[Tuple[float, float]], ccw: bool = False) -> List[Cmd]:
    p = list(pts)[::-1] if ccw else list(pts)
    return [("m", p[0])] + [("l", q) for q in p[1:]]


def stroke(a: Tuple[float, float], b: Tuple[float, float], w: float) -> List[Cmd]:
    """一段圆头粗线（打勾、箭头、音波线）。"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(dx, dy) or 1e-6
    nx, ny = -dy / ln * w / 2.0, dx / ln * w / 2.0
    ang = math.atan2(dy, dx)
    pts = [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny)]
    for i in range(1, 8):                          # b 端半圆
        t = ang + math.pi / 2 - math.pi * i / 8.0
        pts.append((b[0] + math.cos(t) * w / 2.0, b[1] + math.sin(t) * w / 2.0))
    pts += [(b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]
    for i in range(1, 8):                          # a 端半圆
        t = ang - math.pi / 2 - math.pi * i / 8.0
        pts.append((a[0] + math.cos(t) * w / 2.0, a[1] + math.sin(t) * w / 2.0))
    return poly(pts)


def arc_band(cx: float, cy: float, r0: float, r1: float, a0: float, a1: float, n: int = 48) -> List[Cmd]:
    """圆环的一段（a0→a1，度，0＝正上方、顺时针）：外弧去、内弧回。"""
    if a1 - a0 >= 359.9:
        return ellipse(cx, cy, r1, r1) + ellipse(cx, cy, r0, r0, ccw=True)
    k = max(2, int(n * (a1 - a0) / 360.0) + 1)
    out_ = [(cx + r1 * math.sin(math.radians(a0 + (a1 - a0) * i / k)),
             cy - r1 * math.cos(math.radians(a0 + (a1 - a0) * i / k))) for i in range(k + 1)]
    in_ = [(cx + r0 * math.sin(math.radians(a1 - (a1 - a0) * i / k)),
            cy - r0 * math.cos(math.radians(a1 - (a1 - a0) * i / k))) for i in range(k + 1)]
    return poly(out_ + in_)


def _reverse(cmds: List[Cmd]) -> List[Cmd]:
    """反向走一遍（同一路径里反向的子路径＝挖洞）。"""
    pts: List[Tuple[float, ...]] = []
    cur = cmds[0][1]
    segs = []
    for op, c in cmds[1:]:
        segs.append((op, cur, c))
        cur = c[-2:]
    out: List[Cmd] = [("m", tuple(cur))]
    for op, start, c in reversed(segs):
        if op == "b":
            out.append(("b", (c[2], c[3], c[0], c[1], start[-2], start[-1])))
        else:
            out.append(("l", (start[-2], start[-1])))
    return out


def rotate(cmds: List[Cmd], cx: float, cy: float, deg: float) -> List[Cmd]:
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for op, c in cmds:
        q = []
        for i in range(0, len(c), 2):
            x, y = c[i] - cx, c[i + 1] - cy
            q += [cx + x * ca - y * sa, cy + x * sa + y * ca]
        out.append((op, tuple(q)))
    return out


def shape_of(cmds: List[Cmd], scale: float = 1.0) -> Tuple[str, float, float, float, float]:
    """路径 → (ASS 绘图字串, 宽, 高, 中心 x, 中心 y)。坐标平移到左上角＝(0,0)：
    libass 定位绘图时把原点也算进外框，不平移的话 \\an5 置中会偏。"""
    xs = [v for _op, c in cmds for v in c[0::2]]
    ys = [v for _op, c in cmds for v in c[1::2]]
    x0, y0 = min(xs), min(ys)
    parts = []
    for op, c in cmds:
        q = " ".join("%.1f" % ((v - (x0 if i % 2 == 0 else y0)) * scale) for i, v in enumerate(c))
        parts.append("%s %s" % (op, q))
    w, h = (max(xs) - x0) * scale, (max(ys) - y0) * scale
    return " ".join(parts), w, h, (x0 + max(xs)) / 2.0, (y0 + max(ys)) / 2.0


# ---------------------------------------------------------------- 卡通贴纸图标（100×100 设计格）
# 每个零件：(路径, 颜色键, 是否带投影)。只有最底下的外形带投影，里面的零件不再各自投影。
def _icon_parts(name: str) -> List[Tuple[List[Cmd], str, bool]]:
    P = []
    if name in ("phone_play", "phone"):
        P += [(rrect(26, 4, 48, 92, 11), "pink", True), (rrect(32, 14, 36, 64, 5), "cream", False),
              (poly([(44, 34), (60, 46), (44, 58)]), "pink", False), (ellipse(50, 87, 3.5, 3.5), "cream", False)]
    elif name == "camera_off":
        P += [(rrect(30, 20, 30, 18, 5), "yellow", True), (rrect(8, 30, 84, 56, 12), "yellow", True),
              (ellipse(50, 58, 18, 18), "cream", False), (ellipse(50, 58, 9, 9), "ink", False),
              (ellipse(50, 56, 44, 44) + ellipse(50, 56, 36, 36, ccw=True), "pink", False),
              (rotate(rrect(46, 10, 8, 92, 4), 50, 56, 45), "pink", False)]
    elif name == "moon":
        out_ = [(50 + 40 * math.cos(math.radians(a)), 52 + 40 * math.sin(math.radians(a))) for a in range(60, 301, 8)]
        in_ = [(66 + 30 * math.cos(math.radians(a)), 40 + 30 * math.sin(math.radians(a)))
               for a in range(250, 96, -8)]
        P += [(poly(out_ + in_), "yellow", True), (_star(80, 66, 8, 3.5, 4), "yellow", False),
              (_star(70, 86, 5, 2.2, 4), "cream", False)]
    elif name == "megaphone":
        P += [(poly([(14, 38), (60, 16), (60, 84), (14, 62)]), "yellow", True),
              (rrect(6, 36, 14, 28, 5), "pink", False), (ellipse(60, 50, 8, 34), "cream", False),
              (rotate(rrect(22, 62, 12, 26, 5), 28, 64, -12), "pink", True),
              (stroke((76, 34), (90, 24), 6), "ink", False), (stroke((78, 50), (94, 50), 6), "ink", False),
              (stroke((76, 66), (90, 76), 6), "ink", False)]
    elif name in ("bolt", "lightning"):
        P += [(poly([(58, 2), (18, 56), (46, 56), (36, 98), (82, 38), (54, 38), (66, 2)]), "yellow", True)]
    elif name == "link":
        a = rotate(rrect(8, 34, 52, 32, 16) + rrect(18, 43, 32, 14, 7, ccw=True), 50, 50, -40)
        b = rotate(rrect(40, 34, 52, 32, 16) + rrect(50, 43, 32, 14, 7, ccw=True), 50, 50, -40)
        P += [(a, "pink", True), (b, "yellow", True)]
    elif name in ("cursor", "hand"):
        P += [(rrect(38, 4, 18, 56, 9), "cream", True), (rrect(24, 40, 56, 50, 16), "cream", True),
              (rrect(56, 34, 14, 24, 7), "cream", False), (rrect(68, 38, 14, 22, 7), "cream", False),
              (rotate(rrect(10, 46, 26, 13, 6.5), 30, 52, 35), "cream", False),
              (rrect(38, 4, 18, 30, 9), "cream", False)]
    elif name == "pencil":
        body = rotate(rrect(20, 40, 62, 20, 3), 50, 50, -40)
        tip = rotate(poly([(82, 40), (98, 50), (82, 60)]), 50, 50, -40)
        lead = rotate(poly([(92, 46.5), (98, 50), (92, 53.5)]), 50, 50, -40)
        eraser = rotate(rrect(6, 40, 16, 20, 5), 50, 50, -40)
        P += [(body, "yellow", True), (tip, "cream", False), (lead, "ink", False), (eraser, "pink", True)]
    elif name == "scissors":
        P += [(rotate(ellipse(50, 30, 9, 30), 50, 56, -22), "cream", True),
              (rotate(ellipse(50, 30, 9, 30), 50, 56, 22), "cream", True),
              (ellipse(32, 78, 15, 15) + ellipse(32, 78, 8, 8, ccw=True), "pink", True),
              (ellipse(68, 78, 15, 15) + ellipse(68, 78, 8, 8, ccw=True), "pink", True),
              (ellipse(50, 56, 4, 4), "ink", False)]
    elif name == "checkbox":
        P += [(rrect(8, 8, 84, 84, 16), "cream", True), (stroke((26, 52), (44, 70), 12), "pink", False),
              (stroke((44, 70), (76, 30), 12), "pink", False)]
    elif name == "star":
        P += [(_star(50, 52, 48, 21, 5), "yellow", True)]
    elif name == "heart":
        P += [([("m", (50, 92)), ("b", (20, 70, 2, 52, 4, 32)), ("b", (6, 12, 34, 4, 50, 24)),
                ("b", (66, 4, 94, 12, 96, 32)), ("b", (98, 52, 80, 70, 50, 92))], "pink", True)]
    elif name == "sparkle":
        P += [(_star(50, 50, 48, 12, 4), "yellow", True)]
    elif name == "fire":
        P += [([("m", (50, 96)), ("b", (22, 96, 10, 72, 18, 50)), ("b", (24, 34, 38, 30, 40, 4)),
                ("b", (60, 20, 70, 34, 66, 50)), ("b", (74, 44, 78, 36, 78, 30)),
                ("b", (94, 52, 92, 96, 50, 96))], "pink", True),
              ([("m", (50, 92)), ("b", (36, 92, 30, 80, 36, 68)), ("b", (40, 60, 48, 56, 50, 44)),
                ("b", (60, 58, 68, 66, 64, 78)), ("b", (62, 88, 56, 92, 50, 92))], "yellow", False)]
    else:
        raise KeyError(name)
    return P


ICONS = ("phone_play", "camera_off", "moon", "megaphone", "bolt", "link", "cursor", "pencil", "scissors",
         "checkbox", "star", "heart", "sparkle", "fire")


def _star(cx, cy, ro, ri, k=5) -> List[Cmd]:
    return poly([(cx + (ro if i % 2 == 0 else ri) * math.sin(math.pi * i / k),
                  cy - (ro if i % 2 == 0 else ri) * math.cos(math.pi * i / k)) for i in range(2 * k)])


# ---------------------------------------------------------------- 动画曲线
def _cl(p: float) -> float:
    return min(1.0, max(0.0, p))


def back_out(p: float, k: float = 1.70158) -> float:
    p = _cl(p) - 1.0
    return 1.0 + (k + 1.0) * p * p * p + k * p * p


def ease_out(p: float) -> float:
    return 1.0 - (1.0 - _cl(p)) ** 3


def ease_io(p: float) -> float:
    p = _cl(p)
    return p * p * (3 - 2 * p)


ENTRY_DUR = {"pop": 0.32, "slam": 0.34, "rise": 0.34, "drop": 0.42, "slide": 0.42, "ghost": 0.46,
             "fade": 0.18, "fall": 0.55, "none": 0.0}


def bounce_out(p: float) -> float:
    """落地弹两下（标准 bounce 曲线）。"""
    p = _cl(p)
    n, d = 7.5625, 2.75
    if p < 1 / d:
        return n * p * p
    if p < 2 / d:
        p -= 1.5 / d
        return n * p * p + 0.75
    if p < 2.5 / d:
        p -= 2.25 / d
        return n * p * p + 0.9375
    p -= 2.625 / d
    return n * p * p + 0.984375
EXIT_DUR = {"fade": 0.16, "pop": 0.18, "cut": 0.0}


def entry(anim: str, u: float, W: int, H: int) -> dict:
    """入场第 u 秒的变换：s 缩放、dx/dy 位移、rot 额外旋转、a 不透明度、blur、ghost（0＝只有描边，1＝已填满）。"""
    d = ENTRY_DUR.get(anim, 0.3)
    st = {"s": 1.0, "dx": 0.0, "dy": 0.0, "rot": 0.0, "a": 1.0, "blur": 0.0, "ghost": 1.0}
    if anim == "none" or d <= 0 or u >= d:
        return st
    p = _cl(u / d)
    if anim == "pop":
        st.update(s=0.30 + 0.70 * back_out(p, 2.6), a=_cl(u / 0.06))
    elif anim == "slam":   # 从 1.9 倍加速砸下（带模糊），落地一下压扁回弹
        if u < 0.15:
            q = u / 0.15
            st.update(s=1.9 - 0.9 * q * q, blur=7.0 * (1 - q), a=_cl(u / 0.05))
        else:
            q = (u - 0.15) / (d - 0.15)
            st.update(s=1.0 - 0.07 * math.sin(math.pi * q) * (1 - q))
    elif anim == "rise":
        st.update(dy=H * 0.045 * (1 - back_out(p, 1.6)), a=_cl(u / 0.12))
    elif anim == "drop":
        st.update(dy=-H * 0.16 * (1 - back_out(p, 1.4)), rot=-10 * (1 - ease_out(p)), a=_cl(u / 0.08))
    elif anim == "fall":   # 掉落字：从画面上方掉下来、落地弹两下
        st.update(dy=-H * 0.22 * (1 - bounce_out(p)), a=_cl(u / 0.06))
    elif anim == "slide":
        st.update(dx=W * 0.75 * (1 - back_out(p, 1.2)), rot=14 * (1 - ease_out(p)), a=_cl(u / 0.08))
    elif anim == "ghost":   # 先出黄色空心描边，0.24 秒后一下子填满（带一点放大回弹）
        if u < 0.24:
            st.update(s=0.86 + 0.14 * ease_out(u / 0.24), a=_cl(u / 0.06), ghost=0.0)
        else:
            q = (u - 0.24) / (d - 0.24)
            st.update(s=1.0 + 0.08 * math.sin(math.pi * _cl(q * 1.4)) * (1 - q), ghost=_cl(q / 0.35))
    elif anim == "fade":
        st.update(a=p)
    return st


def leave(out: str, v: float) -> dict:
    """出场：v＝离结束还有几秒。"""
    d = EXIT_DUR.get(out, 0.16)
    if d <= 0 or v >= d:
        return {"s": 1.0, "a": 1.0}
    q = 1.0 - _cl(v / d)
    if out == "pop":
        return {"s": 1.0 + 0.10 * math.sin(math.pi * min(1.0, q * 1.6)) - 0.45 * q * q, "a": 1.0 - q * q}
    return {"s": 1.0, "a": 1.0 - q}


# ---------------------------------------------------------------- 元素与采样
class El:
    """一个元素（形状或文字）。ox/oy：中心相对组中心；ax/ay：入场缩放／旋转的支点（相对组中心）。"""

    def __init__(self, kind: str, ox: float, oy: float, **kw):
        self.kind, self.ox, self.oy = kind, ox, oy
        self.ax, self.ay = kw.pop("ax", 0.0), kw.pop("ay", 0.0)
        self.rot = kw.pop("rot", 0.0)
        self.delay = kw.pop("delay", 0.0)
        self.anim = kw.pop("anim", None)
        self.layer = kw.pop("layer", 0)
        self.windows: List[Tuple[float, float]] = kw.pop("windows", [])   # 相对组开始：这段时间逐帧采样
        self.points: List[float] = kw.pop("points", [])                    # 相对组开始：这些时刻状态会变
        self.dyn: Optional[Callable[[float], dict]] = kw.pop("dyn", None)  # 相对组开始的秒数 → 覆盖属性
        self.until: Optional[float] = kw.pop("until", None)               # 提早消失（相对组开始）
        self.p = kw   # path,w,h,fill,bord,bc,shad,shc / body,em,fam,color


class Group:
    def __init__(self, t0: float, t1: float, cx: float, cy: float, anim: str = "pop", out: str = "fade",
                 layer: int = 0, rot: float = 0.0):
        self.t0, self.t1, self.cx, self.cy, self.rot = t0, t1, cx, cy, rot
        self.anim, self.out, self.layer = anim, out, layer
        self.els: List[El] = []

    def add(self, el: El) -> El:
        self.els.append(el)
        return el


def _ts(x: float) -> str:
    return richtext._ts(x)


def render(g: Group, fps: float, W: int, H: int) -> List[str]:
    """一组元素 → ASS Dialogue 行。"""
    fps = float(fps)
    out: List[str] = []
    F = lambda t: int(round(t * fps))   # noqa: E731
    f_end = F(g.t1)
    for li, el in enumerate(g.els):
        anim = el.anim or g.anim
        ts = g.t0 + el.delay
        te = g.t1 if el.until is None else min(g.t1, g.t0 + el.until)
        f0, f1 = F(ts), min(f_end, F(te))
        if f1 <= f0:
            continue
        frames = {f0, f1}
        wins = [(ts, ts + ENTRY_DUR.get(anim, 0.3) + 1.0 / fps)]
        if te >= g.t1 - 1e-6:
            wins.append((g.t1 - EXIT_DUR.get(g.out, 0.16) - 1.0 / fps, g.t1))
        wins += [(g.t0 + a, g.t0 + b) for a, b in el.windows]
        for a, b in wins:
            for f in range(max(f0, F(a)), min(f1, F(b) + 1)):
                frames.add(f)
        for pt in el.points:   # 状态在这个时刻改变：取它之后的第一帧（四舍五入可能落在它前面，字就晚一拍出来）
            f = int(math.ceil((g.t0 + pt) * fps - 1e-6))
            if f0 <= f < f1:
                frames.add(f)
        fr = sorted(frames)
        prev = None
        seg_a = None
        for i, f in enumerate(fr[:-1]):
            t = f / fps
            tags = _state_tags(g, el, anim, t, ts, W, H, li)
            if tags == prev:
                continue
            if prev is not None:
                out.append(_dlg(g.layer + el.layer, seg_a, (f - 0.5) / fps, prev))
            prev, seg_a = tags, (f - 0.5) / fps
        if prev is not None:
            out.append(_dlg(g.layer + el.layer, seg_a, (fr[-1] - 0.5) / fps, prev))
    return out


def _dlg(layer: int, a: float, b: float, body: str) -> str:
    return "Dialogue: %d,%s,%s,C,,0,0,0,,%s" % (layer, _ts(max(0.0, a)), _ts(max(0.0, b)), body)


def _state_tags(g: Group, el: El, anim: str, t: float, ts: float, W: int, H: int, li: int) -> Optional[str]:
    e = entry(anim, t - ts, W, H)
    lv = leave(g.out, g.t1 - t) if (el.until is None or g.t0 + el.until >= g.t1 - 1e-6) else {"s": 1.0, "a": 1.0}
    p = dict(el.p)
    ox, oy, ax, ay, rot0 = el.ox, el.oy, el.ax, el.ay, el.rot
    extra_s, extra_dx, extra_dy, extra_rot, extra_a = 1.0, 0.0, 0.0, 0.0, 1.0
    if el.dyn:
        d = el.dyn(t - g.t0)
        if d is None:
            return None
        ox, oy = d.pop("ox", ox), d.pop("oy", oy)
        rot0 = d.pop("rot", rot0)
        extra_s = d.pop("s", 1.0)
        extra_dx, extra_dy = d.pop("dx", 0.0), d.pop("dy", 0.0)
        extra_a = d.pop("a", 1.0)
        if d.pop("free", False):   # 粒子：自己管全部运动，不跟入场曲线（只跟出场淡出）
            e = {"s": 1.0, "dx": 0.0, "dy": 0.0, "rot": 0.0, "a": 1.0, "blur": 0.0, "ghost": 1.0}
        p.update(d)
    s = e["s"] * lv["s"]
    a = e["a"] * lv["a"] * extra_a
    if a <= 0.004 or s <= 0.01:
        return None
    # 组的入场变换以支点为中心：位置 = 支点 + R·(元素中心 − 支点)·s
    r = math.radians(e["rot"])
    vx, vy = (ox - ax) * s, (oy - ay) * s
    px = ax + vx * math.cos(r) - vy * math.sin(r) + extra_dx
    py = ay + vx * math.sin(r) + vy * math.cos(r) + extra_dy
    if g.rot:   # 整组倾斜：元素位置绕组中心转过去，角度叠加
        gr = math.radians(g.rot)
        px, py = px * math.cos(gr) - py * math.sin(gr), px * math.sin(gr) + py * math.cos(gr)
    px, py = g.cx + px + e["dx"], g.cy + py + e["dy"]
    sc = s * extra_s
    ang = rot0 + e["rot"] + g.rot
    tags = ["\\an5\\pos(%.1f,%.1f)" % (px, py)]
    if abs(ang) > 0.01:
        tags.append("\\org(%.1f,%.1f)\\frz%.2f" % (px, py, -ang))
    if abs(sc - 1.0) > 0.001:
        tags.append("\\fscx%.1f\\fscy%.1f" % (sc * 100, sc * 100))
    if e["blur"] > 0.05:
        tags.append("\\blur%.1f" % e["blur"])
    tr = 1.0 - a
    if el.kind == "shape":
        ghost = e["ghost"] if p.get("ghostable", True) else 1.0
        fa = 1.0 - (1.0 - p.get("fa", 0.0)) * ghost
        bc = p.get("bc", INK) if ghost > 0.5 or not p.get("ghost_bc") else p["ghost_bc"]
        bw = float(p.get("bord", 0.0)) * sc
        sh = float(p.get("shad", 0.0)) * sc * (ghost if p.get("ghostable", True) else 1.0)
        tags.append("\\bord%.2f\\3c%s\\3a%s" % (bw, _ac(bc), _aa(1 - (1 - tr) * (1 - p.get("ba", 0.0)))))
        if sh > 0.2:
            tags.append("\\xshad%.2f\\yshad%.2f\\4c%s\\4a%s" % (sh, sh, _ac(p.get("shc", INK)), _aa(tr)))
        else:
            tags.append("\\shad0")
        tags.append("\\1c%s\\1a%s\\p1}%s" % (_ac(p["fill"]), _aa(1 - (1 - tr) * (1 - fa)), p["path"]))
        return "{" + "".join(tags)
    # 文字
    tags.append("\\fn%s\\fs%.1f\\b%d\\bord%.2f\\shad0\\c%s\\alpha%s"
                % (p["fam"], fs_tag(p["em"], p["fam"], p.get("bold", True)), 1 if p.get("bold", True) else 0,
                   float(p.get("bord", 0.0)) * sc, _ac(p["color"]), _aa(tr)))
    if p.get("bord"):
        tags.append("\\3c%s" % _ac(p.get("bc", INK)))
    if p.get("tshad"):   # 字的硬投影（掉落字这种直接压在画面上的大字）
        sh = float(p["tshad"]) * sc
        tags.append("\\xshad%.2f\\yshad%.2f\\4c%s\\4a%s" % (sh, sh, _ac(INK), _aa(tr)))
    if p.get("italic"):
        tags.append("\\i1")
    if p.get("fsp"):
        tags.append("\\fsp%.1f" % p["fsp"])
    return "{" + "".join(tags) + "}" + p["body"].replace("{A}", _aa(tr))


# ---------------------------------------------------------------- 尺寸
def _u(W: int, H: int) -> float:
    return float(min(W, H))   # 竖屏＝宽；横屏＝高：贴纸大小跟着短边走


def _lines(W: int) -> Tuple[float, float]:
    """(描边粗, 投影距离)：1080 宽约 5px／10px，720 宽约 3px／7px。"""
    return max(2.5, W * 0.0046), max(4.0, W * 0.0092)


# ---------------------------------------------------------------- 彩纸小爆发
def burst(g: Group, w: float, h: float, U: float, th: dict, seed: int, delay: float = 0.04, n: int = 12,
          life: float = 0.55) -> None:
    """卡片弹出那一刻，从卡片四周往外迸出一小簇彩纸（小方块、圆点、菱形、细条），减速、旋转、淡出。"""
    rnd = random.Random(seed)
    cols = [color("pink", th), color("yellow", th), th.get("ink") or INK, color("navy", th), color("cream", th)]
    bw, _sd = _lines(U)
    for k in range(n):
        ang = 2 * math.pi * (k + rnd.uniform(-0.35, 0.35)) / n
        ex, ey = math.cos(ang), math.sin(ang)
        # 起点：卡片外框上（椭圆近似）
        sx, sy = ex * w * 0.52, ey * h * 0.56
        dist = U * rnd.uniform(0.09, 0.19)
        sz = U * rnd.uniform(0.020, 0.034)
        kind = rnd.choice(("sq", "dot", "dia", "bar", "tri"))
        if kind == "sq":
            cm = rrect(0, 0, sz, sz, sz * 0.18)
        elif kind == "dot":
            cm = ellipse(sz / 2, sz / 2, sz / 2, sz / 2)
        elif kind == "dia":
            cm = poly([(sz / 2, 0), (sz, sz * 0.65), (sz / 2, sz * 1.3), (0, sz * 0.65)])
        elif kind == "bar":
            cm = rrect(0, 0, sz * 0.42, sz * 1.5, sz * 0.2)
        else:
            cm = poly([(sz / 2, 0), (sz, sz * 0.9), (0, sz * 0.9)])
        path, pw, ph, _cx, _cy = shape_of(cm)
        col = cols[k % len(cols)]
        spin = rnd.uniform(160, 520) * rnd.choice((-1, 1))
        lf = life * rnd.uniform(0.8, 1.15)
        d0 = delay + rnd.uniform(0.0, 0.05)
        light = not _dark(col)

        def dyn(u, sx=sx, sy=sy, ex=ex, ey=ey, dist=dist, spin=spin, lf=lf, d0=d0):
            q = (u - d0) / lf
            if q < 0 or q >= 1:
                return {"a": 0.0, "free": True}
            m = ease_out(q)
            return {"free": True, "ox": sx + ex * dist * m, "oy": sy + ey * dist * m + U * 0.03 * q * q,
                    "rot": spin * m, "s": 1.0 - 0.45 * q, "a": 1.0 if q < 0.6 else (1 - q) / 0.4}
        g.add(El("shape", sx, sy, layer=60 + k, windows=[(d0, d0 + lf)], dyn=dyn, until=d0 + lf + 0.05,
                 path=path, w=pw, h=ph, fill=col, bord=bw * 0.55 if light else 0.0, bc=INK, shad=0.0,
                 ghostable=False))


# ---------------------------------------------------------------- 富文字块（台词框的内容）
def text_block(g: Group, chars: List[Tuple[str, str]], em: float, fam: str, maxw: float, cx: float, cy: float,
               th: dict, txt_col: str, layer: int, type_from: Optional[float], step: float,
               align: str = "center", delay: float = 0.0, anim: Optional[str] = None) -> Tuple[float, float]:
    """排好一段带标记的字（可逐字打出）。回传 (宽, 高)。cx/cy 是这块字的中心（相对组中心）。"""
    lines = wrap(chars, em, fam, maxw)
    lh = em * 1.32
    widths = [text_w("".join(c for c, _ in ln), em, fam) for ln in lines]
    bw_ = max(widths) if widths else 0.0
    bh_ = lh * len(lines) - (lh - em) * 0.6
    pink, yellow = color("pink", th), color("yellow", th)
    # 每个字的全局序号（打字用）
    idx = 0
    order: List[List[int]] = []
    for ln in lines:
        order.append(list(range(idx, idx + len(ln))))
        idx += len(ln)
    total = idx

    def typed(u: float) -> int:
        if type_from is None:
            return total
        return max(0, min(total, int(math.floor((u - type_from) / step)) + 1)) if u >= type_from else 0

    pts = [type_from + k * step for k in range(total)] if type_from is not None else []
    for li, (ln, lw) in enumerate(zip(lines, widths)):
        ly = cy - bh_ / 2.0 + lh * li + em / 2.0
        lx0 = cx - (bw_ / 2.0 if align == "left" else lw / 2.0)
        # 荧光笔底条／实底块：按连续同种类的字分段，画在字后面
        x = lx0
        runs: List[Tuple[str, int, int, float, float]] = []   # 种类, 起序号, 止序号, 左, 宽
        j = 0
        while j < len(ln):
            k_ = ln[j][1]
            jj = j
            while jj < len(ln) and ln[jj][1] == k_:
                jj += 1
            seg = "".join(c for c, _ in ln[j:jj])
            sw = text_w(seg, em, fam)
            runs.append((k_, order[li][j], order[li][jj - 1], x, sw))
            x += sw
            j = jj
        for k_, a_, b_, rx, rw in runs:
            if k_ not in ("marker", "block"):
                continue
            hh = em * (0.56 if k_ == "marker" else 1.18)
            yy = ly + (em * 0.12 if k_ == "marker" else 0.0)
            col = yellow if k_ == "marker" else pink
            padx = em * (0.10 if k_ == "marker" else 0.18)

            def dyn(u, a_=a_, b_=b_, rx=rx, rw=rw, hh=hh, yy=yy, padx=padx, k_=k_):
                n_ = typed(u)
                if n_ <= a_:
                    return None
                frac = min(1.0, (n_ - a_) / float(b_ - a_ + 1))
                ww = max(hh * 0.6, (rw + 2 * padx) * frac)
                path, pw, ph, _c1, _c2 = shape_of(rrect(0, 0, ww, hh, hh * (0.28 if k_ == "marker" else 0.22)))
                return {"path": path, "ox": rx - padx + ww / 2.0, "oy": yy}
            g.add(El("shape", rx + rw / 2.0, yy, layer=layer, delay=delay, anim=anim, dyn=dyn,
                     points=[p_ for p_ in pts], path="", fill=col, bord=0.0, shad=0.0, ghostable=False))
        # 文字本身：未打出的字透明（{A} 在采样时换成整体透明度），版面不动
        base_col = _ac(txt_col)

        def body(u, ln=ln, li=li):
            n_ = typed(u)
            s_ = ""
            prev_k = None
            for (ch, k_), gi in zip(ln, order[li]):
                vis = gi < n_
                key = (k_, vis)
                if key != prev_k:
                    c_ = _ac(pink) if k_ == "pink" else (_ac("#FFFFFF") if k_ == "block" else base_col)
                    s_ += "{\\c%s\\alpha%s}" % (c_, "{A}" if vis else "&HFF&")
                    prev_k = key
                s_ += richtext._esc(ch)
            return s_

        def dyn_t(u, body=body):
            return {"body": body(u)}
        g.add(El("text", lx0 + lw / 2.0, ly, layer=layer + 1, delay=delay, anim=anim, dyn=dyn_t,
                 points=[p_ for p_ in pts], body="", em=em, fam=fam, color=txt_col))
    return bw_, bh_


# ---------------------------------------------------------------- 各种贴纸
def _base(ov: dict, W: int, H: int, dx: float = 0.5, dy: float = 0.42) -> Tuple[float, float]:
    xy = ov.get("xy") or [dx, dy]
    return float(xy[0]) * W, float(xy[1]) * H


def _pill(g: Group, text: str, em: float, fam: str, fill: str, th: dict, ox: float, oy: float, rot: float,
          layer: int, delay: float = 0.0, anim: Optional[str] = None, txt: Optional[str] = None,
          padx: float = 0.62, pady: float = 0.34, ax: Optional[float] = None, ay: Optional[float] = None,
          U: float = 1080.0) -> Tuple[float, float]:
    tw = text_w(text, em, fam)
    w, h = tw + 2 * em * padx, em * (1 + 2 * pady)
    bw, sd = _lines(U)
    path, pw, ph, _a, _b = shape_of(rrect(0, 0, w, h, h / 2.0))
    ax = ox if ax is None else ax
    ay = oy if ay is None else ay
    g.add(El("shape", ox, oy, ax=ax, ay=ay, rot=rot, layer=layer, delay=delay, anim=anim,
             path=path, w=pw, h=ph, fill=fill, bord=bw, shad=sd * 0.8, ghost_bc=color("yellow", th)))
    g.add(El("text", ox, oy, ax=ax, ay=ay, rot=rot, layer=layer + 1, delay=delay, anim=anim,
             body=richtext._esc(text), em=em, fam=fam, color=txt or on(fill, th)))
    return w, h


def build(ov: dict, th: dict, W: int, H: int, fps: float, order: int = 0) -> List[str]:
    """一个 sticker overlay → ASS 行（图片类回传空，交给 overlays 的图层）。"""
    kind = ov.get("kind", "box")
    if kind == "grid":   # 影片网格：画面是图层，外框与进度条是矢量
        return _grid_decor(ov, th, W, H, fps, order)
    if kind in IMAGE_KINDS:
        return []
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    U = _u(W, H)
    sc = float(ov.get("scale", 1.0))
    fam = family(th.get("sticker_font") or th.get("body_font") or FONT_FALLBACK)
    bw, sd = _lines(U)
    seed = int(t0 * 1000) + order * 7919
    layer = 100 + order * 100
    cx, cy = _base(ov, W, H)
    rot = float(ov.get("rot", 0.0))
    want_burst = ov.get("burst")
    if kind == "wipe":
        return _wipe(ov, th, W, H, fps, layer)
    if kind == "box":
        em = U * 0.072 * sc
        g = Group(t0, t1, cx, cy, ov.get("anim", "pop"), ov.get("out", "fade"), layer, rot)
        chars = parse(ov.get("text", ""))
        fill = color(ov.get("fill"), th, "cream")
        maxw = U * float(ov.get("max_width", 0.80)) - 2 * em * 0.62
        lines = wrap(chars, em, fam, maxw)
        n_chars = sum(len(ln) for ln in lines)
        step = float(ov.get("type_speed") or min(0.075, 0.5 * (t1 - t0) / max(1, n_chars)))
        tw = max(text_w("".join(c for c, _ in ln), em, fam) for ln in lines)
        lh = em * 1.32
        th_ = lh * len(lines) - (lh - em) * 0.6
        w, h = max(em * 2.6, tw + 2 * em * 0.62), th_ + 2 * em * 0.46
        path, pw, ph, _a, _b = shape_of(rrect(0, 0, w, h, min(h / 2.0, em * 0.62)))
        g.add(El("shape", 0, 0, layer=0, path=path, w=pw, h=ph, fill=fill, bord=bw, shad=sd,
                 ghost_bc=color("yellow", th)))
        typing = ov.get("typing", True)
        text_block(g, chars, em, fam, maxw, 0.0, 0.0, th, on(fill, th) if not ov.get("color") else color(ov["color"], th),
                   2, (ENTRY_DUR.get(g.anim, 0.3) * 0.55) if typing else None, step,
                   align=ov.get("align", "center"))
        tag = ov.get("tag")
        if tag:   # 斜标签压在框的左上角
            tcol = color(ov.get("tag_fill") or "pink", th)
            tem = em * 0.62
            tw_ = text_w(tag, tem, fam) + 2 * tem * 0.62
            th2 = tem * 1.68
            tx = -w / 2.0 + tw_ * 0.42
            ty = -h / 2.0 - th2 * 0.12
            _pill(g, tag, tem, fam, tcol, th, tx, ty, float(ov.get("tag_rot", -6.0)), 10, delay=0.10, anim="pop", U=U)
        icn = ov.get("icon")
        if icn:   # 卡通图标贴在右上角
            _icon(g, icn, U * 0.13 * sc, w / 2.0 - U * 0.02, -h / 2.0 - U * 0.035, float(ov.get("icon_rot", 10)),
                  th, 20, delay=0.14, anim="pop")
        if want_burst if want_burst is not None else th.get("sticker_burst", True):
            burst(g, w, h, U, th, seed)
        return render(g, fps, W, H)
    if kind == "tag":
        g = Group(t0, t1, cx, cy, ov.get("anim", "pop"), ov.get("out", "fade"), layer)
        em = U * 0.050 * sc
        fill = color(ov.get("fill") or "pink", th)
        w, h = _pill(g, ov.get("text", ""), em, fam, fill, th, 0, 0, float(ov.get("rot", -6.0)), 0, U=U)
        if want_burst:
            burst(g, w, h, U, th, seed, n=8)
        return render(g, fps, W, H)
    if kind == "slam":
        g = Group(t0, t1, cx, cy, ov.get("anim", "slam"), ov.get("out", "fade"), layer)
        em = U * 0.110 * sc
        fill = color(ov.get("fill") or "yellow", th)
        w, h = _pill(g, ov.get("text", ""), em, fam, fill, th, 0, 0, float(ov.get("rot", -4.0)), 0,
                     padx=0.5, pady=0.26, U=U)
        if want_burst if want_burst is not None else True:
            burst(g, w, h, U, th, seed, delay=0.14, n=14)
        return render(g, fps, W, H)
    if kind == "icon":
        g = Group(t0, t1, cx, cy, ov.get("anim", "pop"), ov.get("out", "fade"), layer, rot)
        size = U * 0.20 * sc
        _icon(g, ov.get("name") or ov.get("icon") or "star", size, 0, 0, 0.0, th, 0)
        if want_burst if want_burst is not None else True:
            burst(g, size, size, U, th, seed, n=10)
        return render(g, fps, W, H)
    if kind == "badge":
        return render(_badge(ov, th, W, H, U, fam, cx, cy, layer, seed, sc), fps, W, H)
    if kind == "checklist":
        return render(_checklist(ov, th, W, H, U, fam, cx, cy, layer, sc), fps, W, H)
    if kind == "cta":
        return render(_cta(ov, th, W, H, U, fam, cx, cy, layer, seed, sc), fps, W, H)
    if kind == "drop":
        return render(_drop(ov, th, W, H, U, fam, cx, cy, layer, sc), fps, W, H)
    if kind == "comment":
        return render(_comment(ov, th, W, H, U, fam, cx, cy, layer, sc), fps, W, H)
    raise env.ToolError("sticker 没有这种 kind：%s（可用：%s）" % (kind, "、".join(KINDS)))


def _icon(g: Group, name: str, size: float, ox: float, oy: float, rot: float, th: dict, layer: int,
          delay: float = 0.0, anim: Optional[str] = None) -> None:
    try:
        parts = _icon_parts(name)
    except KeyError:
        raise env.ToolError("贴纸图标没有：%s（可用：%s）" % (name, "、".join(ICONS)))
    k = size / 100.0
    bw, sd = _lines(size / 0.17)
    for i, (cm, ck, shadow) in enumerate(parts):
        path, pw, ph, pcx, pcy = shape_of(cm, k)
        # 零件中心（相对图标中心）再按图标的倾斜转过去
        vx, vy = (pcx - 50) * k, (pcy - 50) * k
        r = math.radians(rot)
        px, py = ox + vx * math.cos(r) - vy * math.sin(r), oy + vx * math.sin(r) + vy * math.cos(r)
        g.add(El("shape", px, py, ax=ox, ay=oy, rot=rot, layer=layer + i, delay=delay, anim=anim,
                 path=path, w=pw, h=ph, fill=color(ck, th), bord=bw * 0.85, shad=sd * 0.75 if shadow else 0.0,
                 ghostable=False))


def _badge(ov, th, W, H, U, fam, cx, cy, layer, seed, sc) -> Group:
    """圆环计数徽章：数字一步步跳（每跳一下弹一下），粉色圆环跟着数字走满。"""
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    g = Group(t0, t1, cx, cy, ov.get("anim", "pop"), ov.get("out", "fade"), layer)
    d = U * 0.34 * sc
    bw, sd = _lines(U)
    vals = [v for v in (ov.get("values") or [ov.get("value", 0)])]
    top = float(ov.get("max") or max(float(v) for v in vals) or 1.0)
    step = float(ov.get("step", 0.45))
    at = [0.0] + [0.30 + step * i for i in range(len(vals) - 1)]
    path, pw, ph, _a, _b = shape_of(ellipse(d / 2, d / 2, d / 2, d / 2))
    g.add(El("shape", 0, 0, layer=0, path=path, w=pw, h=ph, fill=color(ov.get("fill") or "cream", th),
             bord=bw, shad=sd))
    rw = d * 0.085
    r1, r0 = d / 2 - d * 0.07, d / 2 - d * 0.07 - rw
    pk = color(ov.get("ring") or "pink", th)
    tr_path, *_ = shape_of(arc_band(0, 0, r0, r1, 0, 359.95))
    g.add(El("shape", 0, 0, layer=1, path=tr_path, fill=color("pink", th), fa=0.80, bord=0.0, shad=0.0,
             ghostable=False))

    def frac_at(u):
        i = max(k for k, a in enumerate(at) if u >= a) if u >= 0 else 0
        prev = float(vals[i - 1]) if i > 0 else float(vals[0]) * 0.0
        q = ease_out((u - at[i]) / 0.30)
        return (prev + (float(vals[i]) - prev) * q) / top

    def ring(u):
        f = _cl(frac_at(u))
        if f <= 0.003:
            return None
        cm = arc_band(0, 0, r0, r1, 0, 360.0 * f)
        path, pw, ph, pcx, pcy = shape_of(cm)
        return {"path": path, "ox": pcx, "oy": pcy}
    g.add(El("shape", 0, 0, layer=2, path="", fill=pk, bord=0.0, shad=0.0, ghostable=False, dyn=ring,
             windows=[(a, a + 0.32) for a in at]))
    em = d * 0.34
    unit = ov.get("unit", "")
    uem = d * 0.12

    def num(u):
        i = max(k for k, a in enumerate(at) if u >= a) if u >= 0 else 0
        q = (u - at[i]) / 0.18
        s = 1.0 + (0.28 * (1 - ease_out(q)) if (i > 0 and q < 1) else 0.0)
        return {"body": richtext._esc(str(vals[i])), "s": s}
    g.add(El("text", 0, -d * 0.04 if unit else 0, layer=3, dyn=num, windows=[(a, a + 0.2) for a in at[1:]],
             points=at, body="", em=em, fam=fam, color=on(color(ov.get("fill") or "cream", th), th)))
    if unit:
        g.add(El("text", 0, d * 0.20, layer=3, body=richtext._esc(unit), em=uem, fam=fam,
                 color=color(ov.get("unit_color") or "pink", th)))
    if ov.get("label"):   # 徽章旁的斜标签（例如「最快」）
        _pill(g, ov["label"], U * 0.040 * sc, fam, color(ov.get("label_fill") or "yellow", th), th,
              -d * 0.42, -d * 0.46, -8.0, 10, delay=0.10, anim="pop", U=U)
    if ov.get("burst", True):
        burst(g, d, d, U, th, seed, n=10)
    return g


def _checklist(ov, th, W, H, U, fam, cx, cy, layer, sc) -> Group:
    """打勾清单：奶油白卡，每行一个方框；行一条条弹出，粉色勾一笔笔画上。"""
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    g = Group(t0, t1, cx, cy, ov.get("anim", "pop"), ov.get("out", "fade"), layer)
    items = [x if isinstance(x, dict) else {"text": str(x)} for x in ov.get("items") or []]
    em = U * 0.060 * sc
    bw, sd = _lines(U)
    box = em * 1.05
    rh = em * 1.62
    gap = float(ov.get("gap", 0.42))
    tws = [text_w(x["text"].replace("**", ""), em, fam) for x in items]
    w = box + em * 0.55 + (max(tws) if tws else em * 4) + 2 * em * 0.75
    h = rh * len(items) + em * 0.9
    fill = color(ov.get("fill") or "cream", th)
    path, pw, ph, _a, _b = shape_of(rrect(0, 0, w, h, em * 0.62))
    g.add(El("shape", 0, 0, layer=0, path=path, w=pw, h=ph, fill=fill, bord=bw, shad=sd))
    pink = color("pink", th)
    for i, it in enumerate(items):
        at = float(it.get("at", 0.18 + gap * i))
        y = -h / 2.0 + em * 0.45 + rh * (i + 0.5)
        x_box = -w / 2.0 + em * 0.75 + box / 2.0
        bp, bpw, bph, _a, _b = shape_of(rrect(0, 0, box, box, box * 0.22))
        g.add(El("shape", x_box, y, ax=x_box, ay=y, layer=2 + i * 6, delay=at, anim="pop", path=bp, w=bpw,
                 h=bph, fill="#FFFFFF", bord=bw * 0.8, shad=0.0, ghostable=False))
        tx = x_box + box / 2.0 + em * 0.55 + tws[i] / 2.0
        chars = parse(it["text"])
        body = ""
        for k_, grp in _runs(chars):
            body += ("{\\c%s}" % _ac(pink) if k_ == "pink" else "{\\c%s}" % _ac(on(fill, th))) + richtext._esc(grp)
        g.add(El("text", tx, y, ax=tx - tws[i] / 2.0, ay=y, layer=3 + i * 6, delay=at, anim="rise", body=body,
                 em=em, fam=fam, color=on(fill, th)))
        # 勾：两笔，接着画
        a1 = (x_box - box * 0.28, y + box * 0.02)
        a2 = (x_box - box * 0.06, y + box * 0.26)
        a3 = (x_box + box * 0.40, y - box * 0.34)
        sw = box * 0.20
        tk = at + 0.20

        def leg(u, p0, p1, u0, u1):
            q = (u - u0) / (u1 - u0)
            if q <= 0:
                return None
            q = ease_out(min(1.0, q))
            e_ = (p0[0] + (p1[0] - p0[0]) * q, p0[1] + (p1[1] - p0[1]) * q)
            path_, pw_, ph_, pcx, pcy = shape_of(stroke(p0, e_, sw))
            return {"path": path_, "ox": pcx, "oy": pcy}
        for j, (p0, p1, u0, u1) in enumerate(((a1, a2, tk, tk + 0.08), (a2, a3, tk + 0.08, tk + 0.20))):
            g.add(El("shape", x_box, y, layer=4 + i * 6 + j, path="", fill=pink, bord=0.0, shad=0.0,
                     ghostable=False, windows=[(u0, u1 + 0.04)], points=[u0],
                     dyn=lambda u, p0=p0, p1=p1, u0=u0, u1=u1: leg(u, p0, p1, u0, u1)))
    return g


def _runs(chars):
    out = []
    for ch, k in chars:
        if out and out[-1][0] == k:
            out[-1][1] += ch
        else:
            out.append([k, ch])
    return [(k, s) for k, s in out]


def _cta(ov, th, W, H, U, fam, cx, cy, layer, seed, sc) -> Group:
    """行动号召：粉色胶囊按钮（可先出空心描边再填满）＋手形光标一下下点按＋下面两个往下跳的箭头。"""
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    g = Group(t0, t1, cx, cy, ov.get("anim", "ghost"), ov.get("out", "fade"), layer)
    em = U * 0.072 * sc
    fill = color(ov.get("fill") or "pink", th)
    text = ov.get("text", "点击链接")
    tw = text_w(text, em, fam)
    w, h = tw + 2 * em * 0.75, em * 1.82
    bw, sd = _lines(U)
    period = float(ov.get("tap_every", 0.9))
    first = ENTRY_DUR.get(g.anim, 0.3) + 0.12

    def press(u):   # 0～1：按下去的程度
        if u < first:
            return 0.0
        q = ((u - first) % period) / period
        return math.sin(math.pi * q / 0.22) if q < 0.22 else 0.0

    path, pw, ph, _a, _b = shape_of(rrect(0, 0, w, h, h / 2.0))
    win = [(first, t1 - t0)]
    g.add(El("shape", 0, 0, layer=0, path=path, w=pw, h=ph, fill=fill, bord=bw, shad=sd,
             ghost_bc=color("yellow", th), windows=win,
             dyn=lambda u: {"s": 1.0 - 0.06 * press(u), "dy": sd * 0.5 * press(u)}))
    g.add(El("text", 0, 0, layer=1, body=richtext._esc(text), em=em, fam=fam, color=on(fill, th), windows=win,
             dyn=lambda u: {"s": 1.0 - 0.06 * press(u), "dy": sd * 0.5 * press(u),
                            "a": _cl((u - 0.22) / 0.08) if g.anim == "ghost" else 1.0}))
    # 点按的涟漪
    def ripple(u):
        if u < first:
            return None
        q = ((u - first) % period) / 0.34
        if q >= 1:
            return None
        rr = em * (0.3 + 0.9 * ease_out(q))
        p_, pw_, ph_, _c, _d = shape_of(ellipse(0, 0, rr, rr) + ellipse(0, 0, rr * 0.8, rr * 0.8, ccw=True))
        return {"path": p_, "a": 1.0 - q}
    tip = (w * 0.40, h * 0.20)   # 指尖落点：按钮右下角
    g.add(El("shape", tip[0], tip[1], layer=2, path="", fill="#FFFFFF", bord=0.0, shad=0.0, ghostable=False,
             windows=win, dyn=ripple))
    # 手形光标：从右下靠过来点一下再退开（图标里指尖在设计格 (47, 4)，光标转了 -18°）
    cs = em * 1.65
    vx, vy = (47 - 50) * cs / 100.0, (4 - 50) * cs / 100.0
    r_ = math.radians(-18.0)
    cx0 = tip[0] - (vx * math.cos(r_) - vy * math.sin(r_)) + cs * 0.06
    cy0 = tip[1] - (vx * math.sin(r_) + vy * math.cos(r_)) + cs * 0.08
    cur = Group(0, 0, 0, 0)
    _icon(cur, "cursor", cs, cx0, cy0, -18.0, th, 0)
    for el in cur.els:
        base_ox, base_oy = el.ox, el.oy

        def dyn(u, base_ox=base_ox, base_oy=base_oy):
            k = press(u)
            return {"ox": base_ox - cs * 0.10 * k, "oy": base_oy - cs * 0.12 * k, "s": 1.0 - 0.08 * k}
        el.dyn, el.windows, el.layer, el.delay, el.anim = dyn, win, 10 + el.layer, 0.16, "pop"
        el.ax, el.ay = cx0, cy0
        g.add(el)
    # 往下跳的箭头 ⌄⌄
    for j in range(2):
        yy = h / 2.0 + em * (0.75 + 0.42 * j)
        cw = em * 0.46

        def chev(u, j=j, yy=yy, cw=cw):
            ph_ = (u * 2.2 - j * 0.18) % 1.0
            p_, pw_, ph2, pcx, pcy = shape_of(stroke((-cw, -cw * 0.45), (0, cw * 0.45), cw * 0.32)
                                              + stroke((0, cw * 0.45), (cw, -cw * 0.45), cw * 0.32))
            return {"path": p_, "oy": yy + em * 0.16 * math.sin(2 * math.pi * ph_), "a": 0.55 + 0.45 * math.cos(2 * math.pi * ph_)}
        g.add(El("shape", 0, yy, layer=4 + j, path="", fill=color(ov.get("arrow") or "yellow", th),
                 bord=bw * 0.7, bc=INK, shad=0.0, ghostable=False, delay=0.25, anim="fade",
                 windows=[(0.25, t1 - t0)], dyn=chev))
    return g


def _wipe(ov: dict, th: dict, W: int, H: int, fps: float, layer: int) -> List[str]:
    """斜色带转场：一大片黄色斜带（前面一条粉色细带、黑色描边）横扫过画面，正中间那几帧整片盖住
    （剪辑点就藏在这里），扫走后一下淡淡的白闪。"""
    a, b = float(ov["t"][0]), float(ov["t"][1])
    g = Group(a, b, 0, 0, "none", "cut", layer)
    slant = W * 0.45 + H * 0.0
    band = W * 1.60
    bw, _sd = _lines(_u(W, H))
    yel, pink = color(ov.get("fill") or "yellow", th), color("pink", th)
    lead = W * 0.10
    dist = W + band + slant + lead * 2.5
    x_start = -(band + slant + lead * 1.6)
    d = b - a
    main = poly([(slant, 0), (slant + band, 0), (band, H), (0, H)])
    thin = poly([(slant, 0), (slant + lead, 0), (lead, H), (0, H)])

    def pos(u, off):
        q = ease_io(u / (d * 0.86))
        return x_start + dist * q + off

    for nm, cm, off, col, lay in (("main", main, 0.0, yel, 0), ("lead", thin, band + lead * 0.35, pink, 1),
                                  ("tail", thin, -lead * 1.25, pink, 1)):
        path, pw, ph, pcx, pcy = shape_of(cm)
        g.add(El("shape", 0, 0, layer=lay, path=path, w=pw, h=ph, fill=col, bord=bw, shad=0.0, ghostable=False,
                 windows=[(0, d)], until=d * 0.92,
                 dyn=lambda u, off=off, pcx=pcx: {"ox": pos(u, off) + pcx, "oy": H / 2.0}))
    fl, fw, fh, _c, _d = shape_of(rrect(0, 0, W, H, 0))
    g.add(El("shape", W / 2.0, H / 2.0, layer=5, path=fl, fill="#FFFFFF", bord=0.0, shad=0.0, ghostable=False,
             windows=[(d * 0.55, d)],
             dyn=lambda u: None if u < d * 0.55 else {"a": 0.55 * (1 - _cl((u - d * 0.55) / (d * 0.45)))}))
    return render(g, fps, W, H)


# ---------------------------------------------------------------- 打字框字幕（captions 的 sticker 样式）
def caption_lines(events, st: dict, w: int, h: int, words: Sequence[str], mvs: Sequence, fps: float,
                  th: Optional[dict] = None) -> List[str]:
    """每句字幕放进一个白色贴纸框，框先弹出、字一个个打进去；关键词粉字，==底条== 照样可用。"""
    from .captions import _mask
    th = th or {"accent": PALETTE["pink"], "accent2": PALETTE["yellow"], "plate": [PALETTE["cream"]],
                "navy": PALETTE["navy"], "ink": INK}
    U = float(min(w, h))
    em = h * st["size"] if w < h else U * 0.052
    fam = family(st.get("font") or "Yuanti SC")
    out: List[str] = []
    for i, (e, mv) in enumerate(zip(events, mvs)):
        a, b = float(e[0]), float(e[1])
        extra = e[3] if len(e) > 3 else None
        txt = e[2]
        hl = list((extra or {}).get("hl") or []) + list(words or [])
        if "==" in txt or "[[" in txt:
            chars = parse(txt)
        else:
            plain, m = _mask(txt, hl)
            chars = [(c, "pink" if k else "plain") for c, k in zip(plain, m)]
            chars = [(c, "nl" if c == "\n" else k) for c, k in chars]
        maxw = w * 0.84 - 2 * em * 0.62
        lines = wrap(chars, em, fam, maxw)
        tw = max(text_w("".join(c for c, _ in ln), em, fam) for ln in lines)
        lh = em * 1.32
        tbh = lh * len(lines) - (lh - em) * 0.6
        en = (extra or {}).get("en")
        enh = em * 0.62 * 1.3 if en else 0.0
        bw_ = max(em * 2.4, tw + 2 * em * 0.62, (text_w(str(en), em * 0.62, fam) + 2 * em * 0.62) if en else 0)
        bh_ = tbh + enh + 2 * em * 0.44
        bottom = h - (mv if mv else h * st["margin_v"])
        cy = bottom - bh_ / 2.0
        nxt = events[i + 1][0] if i + 1 < len(events) else None
        joined = nxt is not None and float(nxt) - b < 0.08
        g = Group(a, b, w / 2.0, cy, "pop" if not joined or i == 0 else "pop", "cut" if joined else "fade", 0)
        bwid, sd = _lines(U)
        path, pw, ph, _c, _d = shape_of(rrect(0, 0, bw_, bh_, min(bh_ / 2.0, em * 0.6)))
        g.add(El("shape", 0, 0, layer=0, path=path, w=pw, h=ph, fill=st.get("box", PALETTE["white"]),
                 bord=bwid, shad=sd))
        n_chars = sum(len(ln) for ln in lines)
        step = min(0.07, 0.55 * (b - a) / max(1, n_chars))
        text_block(g, chars, em, fam, maxw, 0.0, -enh / 2.0, th, INK, 2, 0.08, step)
        if en:
            g.add(El("text", 0, tbh / 2.0 - enh / 2.0 + em * 0.40, layer=5, body=richtext._esc(str(en)),
                     em=em * 0.62, fam=fam, color="#5A5560", delay=0.1, anim="fade"))
        out += [ln.replace(",C,,", ",Cap,,", 1) for ln in render(g, fps, w, h)]
    return out


# ---------------------------------------------------------------- 音效
def sfx_events(ov: dict) -> List[Tuple[float, str, float]]:
    """贴纸出现的音效（相对卡片开始的秒数, 音效名, dB）。写 "sfx": "" 关掉；写别的名字换音效。"""
    s = ov.get("sfx")
    if s == "" or s is False:
        return []
    kind = ov.get("kind", "box")
    if kind == "wipe":
        return []   # 转场的「咻」由 transitions 那边加
    name = s if isinstance(s, str) else ("whoosh" if kind == "polaroid" else "pop")
    out = [(0.0, name, float(ov.get("sfx_db", -2.0)))]
    if kind == "flip":
        t0, t1 = float(ov["t"][0]), float(ov["t"][1])
        out.append((float(ov.get("flip_at", (t1 - t0) * 0.45)), "whoosh", -4.0))
    if kind == "slam" and not isinstance(s, str):
        out = [(0.10, "pop", 1.0)]
    if kind == "checklist":
        gap = float(ov.get("gap", 0.42))
        items = ov.get("items") or []
        out = []
        for i, it in enumerate(items):
            at = float(it.get("at", 0.18 + gap * i)) if isinstance(it, dict) else 0.18 + gap * i
            out += [(at, "pop", -4.0), (at + 0.22, "click", -2.0)]
    if kind == "badge":
        step = float(ov.get("step", 0.45))
        out += [(0.30 + step * i, "tick", -4.0) for i in range(len(ov.get("values") or []) - 1)]
    if kind == "cta":
        out = [(0.0, "pop", -3.0)] + [(0.46 + 0.12 + float(ov.get("tap_every", 0.9)) * k, "click", -3.0)
                                      for k in range(3)]
    if kind == "drop" and not isinstance(s, str):
        n = len(str(ov.get("text", "")).replace(" ", ""))
        step = float(ov.get("step", 0.08))
        out = [(0.20 + step * i + 0.20, "thud", -3.0) for i in range(min(n, 8))]
    if kind == "comment" and not isinstance(s, str):
        out = [(0.0, "pop", -3.0), (_comment_post_at(ov), "ding", -4.0)]
    if kind == "grid" and not isinstance(s, str):
        out = [(float(ov.get("stagger", 0.12)) * i, "pop", -4.0) for i in range(min(6, len(ov.get("files") or [])))]
    return out


# ---------------------------------------------------------------- 图片贴纸（拍立得／扇形／翻面）：ffmpeg 图层
def _photo_card(src: str, pw: int, ph: int, side: int, bottom: int, radius: int, photo_r: int, U: float,
                fill: str, tape: Optional[str], work: str) -> Tuple[str, int, int]:
    """奶油白框（黑描边＋硬投影）里嵌一张照片，可加一条胶带。回传 (png, 宽, 高)，按内容缓存。"""
    import hashlib
    import os
    from . import draw
    st = os.stat(src)
    bw, sd = _lines(U)
    key = hashlib.sha1(repr((os.path.abspath(src), st.st_size, st.st_mtime_ns, pw, ph, side, bottom, radius,
                             photo_r, fill, tape, round(bw, 2), round(sd, 2), 2)).encode()).hexdigest()[:16]
    pdir = os.path.join(work, "plates")
    os.makedirs(pdir, exist_ok=True)
    out = os.path.join(pdir, "stkphoto_%s.png" % key)
    cw, ch = pw + 2 * side, ph + side + bottom
    plate, m = draw.make_plate({"w": cw, "h": ch, "radius": radius, "fill": fill, "alpha": 1.0,
                                "border": {"w": round(bw, 1), "color": INK},
                                "shadow": {"soft": 0, "alpha": 1.0, "dx": round(sd), "dy": round(sd), "color": INK}},
                               pdir)
    te = int(round(pw * 0.06)) if tape else 0
    W_, H_ = cw + 2 * m, ch + 2 * m + te
    if os.path.isfile(out):
        return out, W_, H_
    args = [env.ffmpeg(), "-y", "-v", "error", "-i", plate, "-i", src]
    r = max(0, photo_r)
    corner = ("if(gt(hypot(max(0\\,abs(X-W/2)-(W/2-%d))\\,max(0\\,abs(Y-H/2)-(H/2-%d)))\\,%d)\\,0\\,alpha(X\\,Y))"
              % (r, r, r))
    g = ("[0:v]format=rgba,pad=iw:ih+%d:0:%d:color=black@0[c];"
         "[1:v]scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,crop=%d:%d,format=rgba%s[p];"
         "[c][p]overlay=%d:%d:format=auto" % (te, te, pw, ph, pw, ph,
                                             (",geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='%s'" % corner) if r else "",
                                             m + side, m + side + te))
    if tape:
        tw, th_ = int(pw * 0.36), int(pw * 0.11)
        tp, tm = draw.make_plate({"w": tw, "h": th_, "radius": 3, "fill": tape, "alpha": 0.88, "border": {"w": 0},
                                  "shadow": {}}, pdir)
        args += ["-i", tp]
        g += ("[c2];[2:v]format=rgba,rotate=-0.07:ow=hypot(iw\\,ih):oh=ow:c=none[t];[c2][t]overlay=%d:%d:format=auto"
              % (m + cw // 2 - int(math.hypot(tw + 2 * tm, th_ + 2 * tm)) // 2,
                 te + m - int(math.hypot(tw + 2 * tm, th_ + 2 * tm)) // 2))
    env.run(args + ["-filter_complex", g, "-frames:v", "1", out])
    return out, W_, H_


def _bo_expr(p: str, k: float = 1.4) -> str:
    """back_out 的 ffmpeg 表达式（p 已夹在 0～1）。"""
    q = "(%s-1)" % p
    return "(1+%.3f*%s*%s*%s+%.3f*%s*%s)" % (k + 1, q, q, q, k, q, q)


def _clip_p(tvar: str, a: float, d: float) -> str:
    return "clip((%s-%.3f)/%.3f\\,0\\,1)" % (tvar, a, max(0.01, d))


def image_layers(ov: dict, th: dict, W: int, H: int, fps: float, base: str, work: str) -> List[dict]:
    """图片贴纸 → 图层清单：{png, t0, t1, pre, x, y, di, do}。pre 里的 t 从 0 起算（图层自己的时间），
    x／y 用成片时间。旋转输出是边长＝对角线的正方形，所以位置按固定尺寸算、不用 overlay_w。"""
    import os
    kind = ov["kind"]
    if kind == "grid":
        return _grid_layers(ov, W, H, base)
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    U = _u(W, H)
    sc = float(ov.get("scale", 1.0))
    cx, cy = _base(ov, W, H, 0.5, 0.45)
    files = ov.get("files") or ([ov["file"]] if ov.get("file") else [])
    files = [os.path.normpath(os.path.join(base, f)) for f in files]
    for f in files:
        if not os.path.isfile(f):
            raise env.ToolError("贴纸图片找不到：%s" % f)
    if not files:
        raise env.ToolError("%s 贴纸要给 file（或 files）" % kind)
    cream = color(ov.get("fill") or "cream", th)
    out: List[dict] = []

    def rot_layer(png, R, angle_expr_local, x_expr, y_expr, a, b, di=0.08, do=0.16):
        pre = "rotate=a='%s':ow=%d:oh=%d:c=none" % (angle_expr_local, R, R)
        out.append({"png": png, "t0": a, "t1": b, "pre": pre, "x": x_expr, "y": y_expr, "di": di, "do": do})

    if kind == "polaroid":
        pw = int(U * 0.46 * sc) & ~1
        ph = int(pw * float(ov.get("aspect", 1.0))) & ~1
        png, cw, ch = _photo_card(files[0], pw, ph, int(pw * 0.06), int(pw * 0.22), int(pw * 0.03), 0, U, cream,
                                  color(ov.get("tape") or "yellow", th), work)
        R = int(math.ceil(math.hypot(cw, ch))) | 1
        R += 1
        rot = float(ov.get("rot", 6.0))
        d = 0.46
        p_l = _clip_p("t", 0.0, d)
        p_g = _clip_p("t", t0, d)
        ang = "(%.3f+14*pow(1-%s\\,3))*PI/180" % (rot, p_l)
        frm = ov.get("from", "right")
        sgn = -1 if frm == "left" else 1
        x = "%d+(%d)*(1-%s)" % (int(cx - R / 2), int(sgn * W * 0.8), _bo_expr(p_g, 1.2))
        rot_layer(png, R, ang, x, "%d" % int(cy - R / 2), t0, t1)
        return out
    if kind == "fan":
        n = len(files)
        pw = int(U * float(ov.get("card_width", 0.27)) * sc) & ~1
        ph = int(pw * float(ov.get("aspect", 16 / 9.0))) & ~1
        spread = float(ov.get("spread", min(64.0, 16.0 * (n - 1))))
        L = ph * 1.05   # 支点在卡片下方够远：像手里摊开的一把牌，而不是叠成一团
        px, py = cx, cy + L
        for i, f in enumerate(files):
            png, cw, ch = _photo_card(f, pw, ph, int(pw * 0.045), int(pw * 0.045), int(pw * 0.10), int(pw * 0.06),
                                      U, cream, None, work)
            R = (int(math.ceil(math.hypot(cw, ch))) + 1) & ~1
            ai = (-spread / 2 + spread * i / max(1, n - 1)) if n > 1 else 0.0
            st = 0.06 * i
            a_l = "(%.3f*%s)*PI/180" % (ai, _bo_expr(_clip_p("t", st, 0.42), 1.6))
            a_g = "(%.3f*%s)*PI/180" % (ai, _bo_expr(_clip_p("t", t0 + st, 0.42), 1.6))
            x = "%d+%.1f*sin(%s)" % (int(px - R / 2), L, a_g)
            y = "%d-%.1f*cos(%s)+%d*(1-%s)" % (int(py - R / 2), L, a_g, int(H * 0.04),
                                               _bo_expr(_clip_p("t", t0 + st, 0.30), 1.4))
            rot_layer(png, R, a_l, x, y, t0, t1, di=0.10)
        return out
    if kind == "flip":
        if len(files) < 2:
            raise env.ToolError("flip 贴纸要两张图：files: [正面, 背面]")
        pw = int(U * float(ov.get("card_width", 0.36)) * sc) & ~1
        ph = int(pw * float(ov.get("aspect", 16 / 9.0))) & ~1
        fa = float(ov.get("flip_at", (t1 - t0) * 0.45))
        d = 0.34
        rot = float(ov.get("rot", 0.0))
        for side_i, f in enumerate(files[:2]):
            png, cw, ch = _photo_card(f, pw, ph, int(pw * 0.045), int(pw * 0.045), int(pw * 0.10), int(pw * 0.06),
                                      U, cream, None, work)
            cw2 = cw + 2   # 缩成细条时留一点宽度，避免 0 宽
            if side_i == 0:
                a, b = t0, t0 + fa + d / 2
                k = "abs(cos(PI*clip((t-%.3f)/%.3f\\,0\\,0.5)))" % (fa, d)
            else:
                a, b = t0 + fa + d / 2, t1
                k = "abs(cos(PI*clip((t+%.3f)/%.3f\\,0.5\\,1)))" % (d / 2, d)
            pre = ("scale=w='max(2\\,trunc(iw*%s/2)*2)':h=ih:eval=frame,pad=w=%d:h=%d:x='(ow-iw)/2':y=0:"
                   "color=black@0:eval=frame" % (k, cw2 & ~1, ch & ~1))
            if rot:
                R = (int(math.ceil(math.hypot(cw2, ch))) + 1) & ~1
                pre += ",rotate=a=%.4f:ow=%d:oh=%d:c=none" % (math.radians(rot), R, R)
                xw, yh = R, R
            else:
                xw, yh = cw2 & ~1, ch & ~1
            pop = "" if side_i else "+%d*(1-%s)" % (int(H * 0.05), _bo_expr(_clip_p("t", t0, 0.34), 1.6))
            out.append({"png": png, "t0": a, "t1": b, "pre": pre, "x": "%d" % int(cx - xw / 2),
                        "y": "%d%s" % (int(cy - yh / 2), pop), "di": 0.10 if not side_i else 0.02,
                        "do": 0.02 if not side_i else 0.16})   # 不能写 0：ffmpeg 的 fade 时长 0 会改用默认 25 帧
        return out
    raise env.ToolError("不是图片贴纸：%s" % kind)


# ---------------------------------------------------------------- 掉落字／留言列／影片网格
def _drop(ov, th, W, H, U, fam, cx, cy, layer, sc) -> Group:
    """掉落字：英文大字一个个从上方掉下来、落地弹两下；上方一行小斜体先淡入，下方一行中文小字。"""
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    g = Group(t0, t1, cx, cy, "fade", ov.get("out", "fade"), layer, float(ov.get("rot", 0.0)))
    big = str(ov.get("text", "DROP"))
    bfam = family(ov.get("font") or th.get("drop_font") or "Arial Black")
    em = U * float(ov.get("size", 0.20)) * sc
    maxw = W * 0.92
    tw = text_w(big, em, bfam)
    if tw > maxw:   # 太长就缩到放得下
        em *= maxw / tw
        tw = maxw
    bw, sd = _lines(U)
    col = color(ov.get("color") or "white", th)
    step = float(ov.get("step", 0.08))
    x = -tw / 2.0
    k = 0
    for ch in big:
        cw = text_w(ch, em, bfam)
        if ch != " ":
            g.add(El("text", x + cw / 2.0, 0.0, ax=x + cw / 2.0, ay=0.0, layer=10 + k, delay=0.20 + step * k,
                     anim="fall", body=richtext._esc(ch), em=em, fam=bfam, color=col, bord=bw * 1.2, bc=INK,
                     tshad=sd * 1.2))
            k += 1
        x += cw
    if ov.get("small"):
        sem = em * 0.28
        g.add(El("text", -tw / 2.0 + text_w(ov["small"], sem, "Georgia") / 2.0, -em * 0.72, layer=2, anim="fade",
                 body=richtext._esc(str(ov["small"])), em=sem, fam=family("Georgia"), color=col, italic=True,
                 bold=False, bord=bw * 0.6, bc=INK))
    if ov.get("sub"):
        sem = U * 0.042 * sc
        g.add(El("text", 0.0, em * 0.70, layer=3, delay=0.20 + step * k, anim="rise",
                 body=richtext._esc(str(ov["sub"])), em=sem, fam=fam, color=col, bord=bw * 0.7, bc=INK))
    return g


def _comment_post_at(ov: dict) -> float:
    """「发布」变蓝的时刻（相对卡片开始）：打字打完那一刻；没有打字就在 0.6 秒。"""
    if ov.get("post_at") is not None:
        return float(ov["post_at"])
    txt = str(ov.get("text") or "")
    if not txt:
        return 0.6
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    step = float(ov.get("type_speed") or min(0.08, 0.55 * (t1 - t0) / max(1, len(txt))))
    return 0.30 + step * len(txt) + 0.10


def _comment(ov, th, W, H, U, fam, cx, cy, layer, sc) -> Group:
    """留言列：白色圆角长条，左边头像圆点，中间「新增留言…」（或逐字打出 text），右边纸飞机发送键灰→蓝。"""
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    g = Group(t0, t1, cx, cy, ov.get("anim", "rise"), ov.get("out", "fade"), layer)
    em = U * 0.042 * sc
    w, h = U * 0.80 * sc, em * 2.2
    bw, sd = _lines(U)
    path, pw, ph, _a, _b = shape_of(rrect(0, 0, w, h, h / 2.0))
    g.add(El("shape", 0, 0, layer=0, path=path, w=pw, h=ph, fill="#FFFFFF", bord=bw * 0.8, shad=sd * 0.7))
    av = h * 0.66
    ap, *_ = shape_of(ellipse(av / 2, av / 2, av / 2, av / 2))
    g.add(El("shape", -w / 2 + h * 0.17 + av / 2, 0, layer=1, path=ap, fill=color(ov.get("avatar") or "pink", th),
             bord=bw * 0.5, shad=0.0, ghostable=False))
    pa = _comment_post_at(ov)
    # 发送键：纸飞机图标，打完之前灰色，打完那一刻变蓝、弹一下（写 "post": "发布" 改回文字按钮）
    post = ov.get("post")
    if post:
        pwid = text_w(str(post), em, fam)
        px = w / 2 - h * 0.35 - pwid / 2
        g.add(El("text", px, 0, layer=2, body=richtext._esc(str(post)), em=em, fam=fam, color="#9AA0A6", until=pa))
        g.add(El("text", px, 0, layer=3, body=richtext._esc(str(post)), em=em, fam=fam, color="#0095F6", delay=pa,
                 anim="pop"))
    else:
        pwid = h * 0.50
        px = w / 2 - h * 0.30 - pwid / 2
        k = pwid / 100.0
        # 纸飞机：上翼（亮）＋下翼（暗）沿折线拼起来，一眼看得出是折纸
        wings = ((poly([(0, 44), (100, 0), (40, 62)]), "#9AA0A6", "#0095F6"),
                 (poly([(40, 62), (100, 0), (56, 100)]), "#767C83", "#0068B8"))
        for wi, (cm, grey, blue) in enumerate(wings):
            pp_, ppw, pph, pcx, pcy = shape_of(cm, k)
            ox, oy = px + (pcx - 50) * k, (pcy - 50) * k
            for lay, col, kw in ((2, grey, {"until": pa}), (3, blue, {"delay": pa, "anim": "pop"})):
                g.add(El("shape", ox, oy, ax=px, ay=0, layer=lay * 2 + wi, path=pp_, w=ppw, h=pph, fill=col,
                         bord=0.0, shad=0.0, ghostable=False, **kw))
    tx0 = -w / 2 + h * 0.17 + av + em * 0.5
    txt = str(ov.get("text") or "")
    if txt:
        step = float(ov.get("type_speed") or min(0.08, 0.55 * (t1 - t0) / max(1, len(txt))))
        maxw = px - pwid / 2 - em * 0.4 - tx0
        while len(txt) > 1 and text_w(txt, em, fam) > maxw:   # 太长就截掉尾巴（留言列只有一行）
            txt = txt[:-1]
        tw = text_w(txt + "|", em, fam)

        def body(u, txt=txt, step=step):
            n_ = max(0, min(len(txt), int(math.floor((u - 0.30) / step)) + 1)) if u >= 0.30 else 0
            # 光标紧跟在已打出的字后面（光标字符一直在、只换透明度，整行宽度不变、字不会跳）
            on_ = n_ < len(txt) and int(u * 3) % 2 == 0
            return {"body": "{\\alpha{A}}%s{\\c&HA6A09A&\\alpha%s}|{\\c&H0B0A0A&\\alpha&HFF&}%s" % (
                richtext._esc(txt[:n_]), "{A}" if on_ else "&HFF&", richtext._esc(txt[n_:]))}
        g.add(El("text", tx0 + tw / 2.0, 0, layer=2, body="", em=em, fam=fam, color=INK, dyn=body,
                 points=[0.30 + step * k for k in range(len(txt) + 1)], windows=[(0.30, 0.30 + step * len(txt))]))
    else:
        ph_txt = str(ov.get("placeholder", "新增留言…"))
        tw = text_w(ph_txt, em, fam)
        g.add(El("text", tx0 + tw / 2.0, 0, layer=2, body=richtext._esc(ph_txt), em=em, fam=fam, color="#9AA0A6"))
    return g


def _grid_geom(ov: dict, W: int, H: int) -> List[Tuple[float, float, int, int, float]]:
    """影片网格每格的 (中心 x, 中心 y, 宽, 高, 出现时间)。"""
    U = _u(W, H)
    sc = float(ov.get("scale", 1.0))
    n = min(6, len(ov.get("files") or []))
    cols = int(ov.get("cols", 3 if n > 4 or n == 3 else (2 if n > 1 else 1)))
    rows = int(math.ceil(n / float(cols)))
    gap = U * 0.025 * sc
    cw = int(U * float(ov.get("cell", 0.28 if cols >= 3 else 0.40)) * sc) & ~1
    ch = int(cw * float(ov.get("aspect", 16 / 9.0))) & ~1
    cx, cy = _base(ov, W, H, 0.5, 0.52)
    stag = float(ov.get("stagger", 0.12))
    out = []
    for i in range(n):
        r, c = divmod(i, cols)
        in_row = min(cols, n - r * cols)
        x = cx + (c - (in_row - 1) / 2.0) * (cw + gap)
        y = cy + (r - (rows - 1) / 2.0) * (ch + gap)
        out.append((x, y, cw, ch, stag * i))
    return out


def _grid_decor(ov: dict, th: dict, W: int, H: int, fps: float, order: int) -> List[str]:
    """每格一圈米白框（盖住影片的方角）＋底下一条跟着播放前进的黄色进度条。"""
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    U = _u(W, H)
    bw, sd = _lines(U)
    out: List[str] = []
    for i, (x, y, cw, ch, st) in enumerate(_grid_geom(ov, W, H)):
        g = Group(t0, t1, x, y, "pop", ov.get("out", "fade"), 100 + order * 100 + i * 4)
        pad, rr = U * 0.0055, U * 0.026   # 细框：只盖住影片的方角
        cm = rrect(0, 0, cw + 2 * pad, ch + 2 * pad, rr + pad) + rrect(pad, pad, cw, ch, rr, ccw=True)
        p, pw, ph, _a, _b = shape_of(cm)
        g.add(El("shape", 0, 0, layer=0, delay=st, path=p, w=pw, h=ph, fill=color("cream", th), bord=bw * 0.5,
                 shad=sd * 0.6, ghostable=False))
        bwid, bh = cw * 0.84, U * 0.008
        track, *_ = shape_of(rrect(0, 0, bwid, bh, bh / 2))
        g.add(El("shape", 0, ch / 2 - U * 0.03, layer=1, delay=st + 0.25, anim="fade", path=track, fill="#FFFFFF",
                 fa=0.55, bord=0.0, shad=0.0, ghostable=False))
        dur = max(0.3, t1 - t0 - st - 0.25)

        def prog(u, st=st, dur=dur, bwid=bwid, bh=bh, ch=ch):
            q = (u - st - 0.25) / dur
            if q <= 0.01:
                return None
            ww = bwid * min(1.0, q)
            pp, *_ = shape_of(rrect(0, 0, ww, bh, bh / 2))
            return {"path": pp, "ox": -bwid / 2 + ww / 2, "oy": ch / 2 - U * 0.03}
        g.add(El("shape", 0, ch / 2 - U * 0.03, layer=2, delay=st + 0.25, anim="none", path="",
                 fill=color("yellow", th), bord=0.0, shad=0.0, ghostable=False, dyn=prog,
                 windows=[(st + 0.25, t1 - t0)]))
        out += render(g, fps, W, H)
    return out


VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def _grid_layers(ov: dict, W: int, H: int, base: str) -> List[dict]:
    """影片网格的画面：每格一路输入（影片从 start 起播；图片也行），按格子大小裁满，带一点放大弹出。"""
    import os
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    out = []
    files = ov.get("files") or []
    for (x, y, cw, ch, st), f in zip(_grid_geom(ov, W, H), files):
        spec = f if isinstance(f, dict) else {"path": f}
        fp = os.path.normpath(os.path.join(base, spec["path"]))
        if not os.path.isfile(fp):
            raise env.ToolError("影片网格找不到：%s" % fp)
        a = t0 + st
        d = max(0.1, t1 - a)
        if os.path.splitext(fp)[1].lower() in VIDEO_EXT:
            inp = ["-stream_loop", "-1", "-ss", "%.3f" % float(spec.get("start", 0.0)), "-t", "%.3f" % d, "-i", fp]
        else:
            inp = ["-loop", "1", "-t", "%.3f" % d, "-i", fp]
        ct, cb = float(spec.get("crop_top", 0.0)), float(spec.get("crop_bottom", 0.0))
        pw_, ph_ = int(cw * 1.14) & ~1, int(ch * 1.14) & ~1
        s = "(0.30+0.70*%s)" % _bo_expr(_clip_p("t", 0.0, 0.32), 2.6)
        pre = ("setpts=PTS-STARTPTS,crop=iw:ih*%.4f:0:ih*%.4f,scale=%d:%d:force_original_aspect_ratio=increase,"
               "crop=%d:%d,setsar=1,format=rgba,scale=w='max(2\\,trunc(%d*%s/2)*2)':h='max(2\\,trunc(%d*%s/2)*2)':eval=frame,"
               "pad=w=%d:h=%d:x='(ow-iw)/2':y='(oh-ih)/2':color=black@0:eval=frame"
               % (max(0.05, 1 - ct - cb), ct, cw, ch, cw, ch, cw, s, ch, s, pw_, ph_))
        out.append({"input": inp, "t0": a, "t1": t1, "pre": pre, "x": "%d" % int(x - pw_ / 2),
                    "y": "%d" % int(y - ph_ / 2), "di": 0.06, "do": 0.16})
    return out
