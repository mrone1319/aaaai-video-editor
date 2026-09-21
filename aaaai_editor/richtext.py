"""富文本通路：把卡片文字写成 ASS，交给 libass 渲染。

drawtext 一个滤镜只能画一种颜色、一种字体；libass 能在同一行里混色（关键词高亮）、
调字距（小标加宽）、合成斜体、按家族名找字体、自动回退中文字形。
新风格（text_engine: "ass"）的卡片文字全部走这里；旧风格只有带 **高亮** 的行走这里，
其余仍走 drawtext，所以旧成片逐位不变。

字号换算：libass 按 (usWinAscent+usWinDescent)/unitsPerEm 缩放，drawtext 按 em。
这里读字体文件把两者对齐，所以同一个字号在两条通路里一样大、版面算出来的底板不会错。
"""
from __future__ import annotations

import hashlib
import os
import struct
import subprocess
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from . import fonts


# ---------------------------------------------------------------- 字体度量（纯标准库解析 sfnt）
def _tables(f, base: int) -> Dict[bytes, Tuple[int, int]]:
    f.seek(base + 4)
    n = struct.unpack(">H", f.read(2))[0]
    f.seek(base + 12)
    out = {}
    for _ in range(n):
        tag, _cs, off, ln = struct.unpack(">4sIII", f.read(16))
        out[tag] = (off, ln)
    return out


@lru_cache(maxsize=64)
def metrics_file(path: str, index: int = 0) -> Tuple[float, float, float]:
    """(行高倍率 win, 上沿倍率 winAscent, 大写高倍率 capHeight)，都以 em 为单位。"""
    with open(path, "rb") as f:
        head = f.read(12)
        base = 0
        if head[:4] == b"ttcf":
            f.seek(12 + 4 * index)
            base = struct.unpack(">I", f.read(4))[0]
        t = _tables(f, base)
        f.seek(t[b"head"][0] + 18)
        upem = struct.unpack(">H", f.read(2))[0]
        o = t[b"OS/2"][0]
        f.seek(o)
        ver = struct.unpack(">H", f.read(2))[0]
        f.seek(o + 74)
        wa, wd = struct.unpack(">HH", f.read(4))
        cap = 0.70
        if ver >= 2:
            f.seek(o + 88)
            cap = struct.unpack(">h", f.read(2))[0] / upem or 0.70
    return (wa + wd) / upem, wa / upem, cap


@lru_cache(maxsize=64)
def locate(family: str) -> Tuple[str, int]:
    fd = fonts.FONT_DIR
    key = family.replace(" ", "")
    for f in sorted(os.listdir(fd)) if os.path.isdir(fd) else []:
        if f.replace(" ", "").lower().startswith(key.lower()) and f.lower().endswith((".ttf", ".otf")):
            return os.path.join(fd, f), 0   # 安装器下载的开源字体、固化的展示字体都在这里
    out = subprocess.run(["fc-match", "-f", "%{file}|%{index}", family], capture_output=True, text=True).stdout
    f, _, idx = out.partition("|")
    return f, int(idx or 0)


def metrics(family: str) -> Tuple[float, float, float]:
    try:
        return metrics_file(*locate(family))
    except (OSError, KeyError, struct.error, ValueError):
        return 1.0, 0.88, 0.70


def has_cjk(s: str) -> bool:
    return any(ord(c) > 0x2E80 for c in s)


# ---------------------------------------------------------------- ASS 组装
def _c(hexc: str) -> str:
    h = hexc.lstrip("#")
    return "&H%s%s%s&" % (h[4:6], h[2:4], h[0:2])


def _esc(s: str) -> str:
    return s.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


def _ts(x: float) -> str:
    cs = max(0, int(round(x * 100)))
    return "%d:%02d:%02d.%02d" % (cs // 360000, cs // 6000 % 60, cs // 100 % 60, cs % 100)


ROLE_DEFAULT = {"font": "body", "bold": 0, "italic": 0, "upper": 0, "tracking": 0.0}


def role_cfg(th: dict, role: str) -> dict:
    d = dict(ROLE_DEFAULT)
    d.update((th.get("type") or {}).get(role or "", {}))
    return d


def family_for(th: dict, key: str, text: str) -> str:
    if key == "display":
        _p, name = fonts.display(th)
        if name:
            return name
    if key == "mono" and not has_cjk(text):
        return th.get("mono_font", "IBM Plex Mono")
    if key == "serif":
        return th.get("serif_font", "Songti SC")
    return th.get("body_font", "Hiragino Sans GB")


def _smooth(p: float) -> float:
    p = min(1.0, max(0.0, p))
    return p * p * (3 - 2 * p)


def dialogues(it: dict, th: dict, runs: Optional[List[Tuple[str, bool]]] = None,
              text: Optional[str] = None, a0: Optional[float] = None, a1: Optional[float] = None,
              fade_out: bool = True) -> List[str]:
    """一个文字项 → 若干行 ASS Dialogue。

    入场（位移 smoothstep、透明度线性）拆成 4 段折线逼近，与 drawtext 通路的曲线一致；
    计数动画的每一步用 a0/a1 截取时间段，入场进行到一半的步骤会从当时的位置和透明度接着走。
    """
    cfg = role_cfg(th, it.get("role"))
    key = cfg["font"] if not (it.get("mono") and cfg["font"] == "body") else "mono"
    raw = text if text is not None else ("".join(r[0] for r in runs) if runs else (it.get("text") or ""))
    if cfg["upper"]:
        raw = raw.upper()
        runs = [(r[0].upper(), r[1]) for r in runs] if runs else None
    fam = family_for(th, key, raw)
    win, asc, cap = metrics(fam)
    em = float(it["size"])
    top = 0.85 if has_cjk(raw) else cap   # 墨迹顶端落在 y（与 drawtext 一致）
    y = it["y"] - (asc - top) * em
    an, x = (8, float(it["cx"])) if it.get("cx") is not None else (7, float(it["x"]))
    t_in, t_end = float(it["t0"]), float(it["t1"])
    a0 = t_in if a0 is None else a0
    a1 = t_end if a1 is None else a1
    di, do = max(0.01, float(it["di"])), float(it["do"])
    dx, dy = float(it.get("dx") or 0), float(it.get("dy") or 0)

    base = ["\\an%d" % an, "\\fn%s" % fam, "\\fs%.1f" % (em * win), "\\c%s" % _c(it["color"]),
            "\\b%d" % (1 if cfg["bold"] else 0), "\\i%d" % (1 if cfg["italic"] else 0)]
    if cfg["tracking"]:
        base.append("\\fsp%.1f" % (cfg["tracking"] * em))
    if it.get("soft"):   # 无底板的排版卡片：柔和投影代替描边，字放在任何画面上都清楚
        # 细描边（同字色）把字加粗一点 + 向下偏移的半透明投影托住字：任何画面上都清楚，字边不发虚
        base += ["\\bord%.1f" % max(0.8, em * 0.014), "\\3c%s" % _c(it["color"]), "\\3a&H00&",
                 "\\shad%.1f" % max(2.0, em * 0.05), "\\4c&H000000&", "\\4a&H40&"]
    elif it.get("stroke"):
        base += ["\\bord%.1f" % max(2.0, em * 0.055), "\\3c&H000000&", "\\3a&H4C&", "\\shad0"]
    else:
        base += ["\\bord0", "\\shad0"]
    if runs and any(h for _, h in runs):
        hl, bc = _c(th.get("hl") or th["accent"]), _c(it["color"])
        body = "".join(("{\\c%s}%s{\\c%s}" % (hl, _esc(t), bc)) if h else _esc(t) for t, h in runs)
    else:
        body = _esc(raw)

    def pos_at(t):
        k = 1.0 - _smooth((t - t_in) / di)
        return x + dx * k, y + dy * k

    def alpha_at(t):
        return 1.0 - min(1.0, max(0.0, (t - t_in) / di))   # 0＝不透明

    # 时间断点：入场 4 段 + 静止段
    cuts = [t_in + di * j / 4.0 for j in range(5)]
    pts = sorted({a0, a1} | {c for c in cuts if a0 < c < a1})
    out = []
    for u, v in zip(pts, pts[1:]):
        if v - u < 0.005:
            continue
        tags = list(base)
        moving = u < t_in + di - 1e-6 and (dx or dy)
        x0, y0 = pos_at(u)
        if moving:
            x1, y1 = pos_at(v)
            tags.append("\\move(%.1f,%.1f,%.1f,%.1f)" % (x0, y0, x1, y1))
        else:
            tags.append("\\pos(%.1f,%.1f)" % (x0, y0))
        au, av = alpha_at(u), alpha_at(v)
        if au > 0.001 or av > 0.001:
            tags.append("\\alpha&H%02X&\\t(\\alpha&H%02X&)" % (int(round(au * 255)), int(round(av * 255))))
        if fade_out and abs(v - t_end) < 1e-6 and do > 0:
            tags.append("\\fad(0,%d)" % int(round(min(do, v - u) * 1000)))
        out.append("Dialogue: 0,%s,%s,C,,0,0,0,,{%s}%s" % (_ts(u), _ts(v), "".join(tags), body))
    return out


def write(path: str, W: int, H: int, lines: List[str]) -> None:
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n"
            "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,"
            "Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,"
            "MarginL,MarginR,MarginV,Encoding\n"
            "Style: C,Hiragino Sans GB,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,"
            "1,0,0,7,0,0,0,1\n\n[Events]\n"
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n") % (W, H)
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")


def file_for(work: str, W: int, H: int, lines: List[str], tag: str) -> str:
    """写出（按内容哈希命名，分段渲染各段互不覆盖），返回相对 work 的文件名。"""
    key = hashlib.sha1(("%dx%d" % (W, H) + "\n".join(lines)).encode("utf-8")).hexdigest()[:12]
    name = "rich_%s_%s.ass" % (tag, key)
    p = os.path.join(work, name)
    if not os.path.isfile(p):
        write(p, W, H, lines)
    return name
