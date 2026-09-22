"""组合卡片：证据截图卡（proof）、工作流步骤卡（flow）、行动号召卡（cta）、倒数（countdown），
以及「卡片接管」期间的自动排版。在读 storyboard 时展开成基本卡片（图片、文字、印章、步骤卡…），
渲染只看得到基本卡片——分段渲染、预览、抽帧都照常。

卡片接管（type=frame，配方 takeover）期间，画面收进下方的圆角框，上方 6%～32% 是「面板区」：
  - 落在接管期间的卡片自动改用底板版（不用渐变遮罩），默认放进面板区；
  - 接管背景是纸面（"bg": "paper"）时，卡片改白底深字。
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import List, Optional, Tuple

from . import env
from .timeline import Timeline

PANEL_TOP = 0.065       # 面板区上缘（相对画面高）
PANEL_BOTTOM = 0.325    # 面板区下缘：接管的框从 0.34 开始
PAPER = "#F4EFE7"       # 纸面底色
PILL = {"accent": "#F5C542", "on_accent": "#1E1B16"}          # 黄色日期胶囊
ON_PAPER = {"plate": "#FFFFFF", "text": "#1E1B16", "muted": "#5B554C"}  # 纸面上的白卡深字


def _image_size(path: str) -> Tuple[int, int]:
    out = subprocess.run([env.ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "json", path], capture_output=True, text=True).stdout
    s = (json.loads(out or "{}").get("streams") or [{}])[0]
    if not s.get("width"):
        raise env.ToolError("读不到图片尺寸：%s" % path)
    return int(s["width"]), int(s["height"])


def windows(sb: dict) -> List[dict]:
    return [o for o in sb.get("overlays") or [] if o.get("type") == "frame"]


def _in_window(ov: dict, wins: List[dict]) -> Optional[dict]:
    a, b = float(ov["t"][0]), float(ov["t"][1])
    for w in wins:
        wa, wb = float(w["t"][0]), float(w["t"][1])
        if min(b, wb) - max(a, wa) >= 0.5 * (b - a):
            return w
    return None


def _proof(ov: dict, sb: dict, W: int, H: int, win: Optional[dict]) -> List[dict]:
    """证据截图卡：白框截图＋（上方小标题）＋（底边黄色日期胶囊）＋（右上角金额印章，对准说出数字那一刻盖下）。"""
    f = os.path.normpath(os.path.join(sb.get("_base", ""), ov["file"]))
    if not os.path.isfile(f):
        raise env.ToolError("证据截图找不到：%s" % f)
    iw, ih = _image_size(f)
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    wf = float(ov.get("width", 0.84 if ov.get("x") is None else 0.41))
    cx = float(ov.get("x", 0.5))
    top = float(ov.get("top", PANEL_TOP + (0.03 if ov.get("kicker") else 0.0)))
    max_h = float(ov.get("max_h", PANEL_BOTTOM - top))
    border = max(6, int(W * 0.012))
    # 截图按宽度放，太高就按高度缩（白框也算进去）
    w = int(W * wf) - 2 * border
    h = int(w * ih / float(iw))
    if h + 2 * border > H * max_h:
        h = int(H * max_h) - 2 * border
        w = int(h * iw / float(ih))
    # 位置与尺寸存成比例：预览（半分辨率）和成片都按实际画面换算
    out = [{"type": "proof_img", "t": [t0, t1], "file": ov["file"], "wf": w / float(W), "hf": h / float(H),
            "bf": border / float(W), "xf": (W * cx - w / 2 - border) / float(W), "yf": top,
            "sfx": ov.get("sfx"), "sfx_at": ov.get("sfx_at")}]
    bottom = H * top + h + 2 * border
    if ov.get("kicker"):
        out.append({"type": "text", "t": [t0, t1], "text": ov["kicker"], "_xy": [cx, top - 0.028], "scale": 0.8,
                    "color": "@muted" if not win or win.get("bg") != "paper" else ON_PAPER["muted"], "anim": "fade"})
    if ov.get("pill"):
        out.append({"type": "stamp", "t": [t0 + 0.15, t1], "text": ov["pill"], "_xy": [cx, (bottom - H * 0.018) / H],
                    "colors": dict(PILL), "anim": "pop", "_raw": True})
    if ov.get("stamp"):
        at = float(ov.get("stamp_at", t0 + 0.6))
        sx = (W * cx + w / 2 + border - W * 0.02) / W
        out.append({"type": "stamp", "t": [at, t1], "text": ov["stamp"], "_xy": [min(0.86, sx), top + 0.012],
                    "anim": "pop", "scale": float(ov.get("stamp_scale", 1.5)), "_raw": True,
                    "sfx": ov.get("stamp_sfx"), "sfx_at": at})
    return out


def _flow(ov: dict, W: int, H: int, win: Optional[dict]) -> List[dict]:
    """工作流步骤卡：一排小卡，每步对准台词（at）出现；最后一张是强调色的「结果」卡。"""
    steps = ov.get("steps") or []
    if not steps:
        raise env.ToolError("flow 需要 steps")
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    n = len(steps)
    mx = 0.058
    gap = 0.022
    cw = (1 - 2 * mx - gap * (n - 1)) / n
    top = float(ov.get("top", PANEL_TOP + (0.04 if ov.get("kicker") else 0.0)))
    out = []
    if ov.get("kicker"):
        out.append({"type": "text", "t": [t0, t1], "text": ov["kicker"], "_xy": [0.5, top - 0.035], "scale": 0.9,
                    "color": "@muted" if not win or win.get("bg") != "paper" else ON_PAPER["muted"], "anim": "fade"})
    for i, s in enumerate(steps):
        at = float(s.get("at", t0 + 0.25 * i))
        last = i == n - 1 and ov.get("result", True)
        st = {"type": "step", "t": [at, t1], "icon": s.get("icon"), "top": s.get("top", ""), "big": s.get("big", ""),
              "_xy": [mx + cw / 2 + i * (cw + gap), top], "width": cw, "anim": "pop", "lite": False,
              "sfx": s.get("sfx", ov.get("sfx")), "sfx_at": at if (s.get("sfx") or ov.get("sfx")) else None}
        if last:
            st["_result"] = True
        out.append(st)
    return out


def _cta(ov: dict, W: int, H: int, win: Optional[dict]) -> List[dict]:
    """行动号召卡：小标题＋问题（可用 **关键词**）→ 关键词大药丸（对准说出关键词那一刻弹出）→ 一行小字。"""
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    qa = float(ov.get("question_at", t0))
    ca = float(ov.get("cta_at", qa + 1.0))
    top = float(ov.get("top", PANEL_TOP))
    out = [{"type": "title", "t": [qa, t1], "kicker": ov.get("kicker"), "text": ov.get("question", ""),
            "_xy": [0.5, top], "lite": False, "anim": "rise", "align": "center"}]
    if ov.get("keyword"):
        out.append({"type": "stamp", "t": [ca, t1], "text": ov["keyword"], "_xy": [0.5, top + 0.165],
                    "scale": float(ov.get("keyword_scale", 2.2)), "anim": "pop", "_raw": True,
                    "sfx": ov.get("sfx"), "sfx_at": ca if ov.get("sfx") else None})
    if ov.get("badge"):
        out.append({"type": "text", "t": [ca + 0.3, t1], "text": ov["badge"], "_xy": [0.5, top + 0.235],
                    "scale": 0.85, "anim": "fade",
                    "color": "@muted" if not win or win.get("bg") != "paper" else ON_PAPER["muted"]})
    return out


def _countdown(ov: dict, W: int, H: int) -> List[dict]:
    """倒数：圆环一秒一秒缩短＋中间大数字（可每秒一声 tick）。"""
    n = int(ov.get("from", 3))
    t0 = float(ov["t"][0])
    cx, cy = [float(v) for v in (ov.get("at_xy") or [0.5, 0.21])]   # 默认在头顶上方，不挡脸
    size = float(ov.get("size", 0.34))
    out = [{"type": "ring", "t": [t0, t0 + n], "cx": cx, "cy": cy, "size": size, "from": n}]
    for k in range(n):
        o = {"type": "text", "t": [t0 + k, t0 + k + 0.98], "text": str(n - k), "_xy": [cx, cy - size * W / H * 0.23],
             "scale": float(ov.get("scale", 3.2)), "anim": "pop", "color": ov.get("color", "#FFFFFF"), "_raw": True}
        if ov.get("sfx", "tick"):
            o.update(sfx=ov.get("sfx", "tick"), sfx_at=t0 + k)
        out.append(o)
    return out


def expand(sb: dict) -> dict:
    """展开组合卡片、处理卡片接管的 hold 与排版。读 storyboard 时调用一次。"""
    ovs = sb.get("overlays") or []
    if not ovs:
        return sb
    W, H = int(sb["output"]["width"]), int(sb["output"]["height"])
    total = Timeline([tuple(c) for c in sb["cuts"]], sb["output"]["fps"]).duration if sb.get("cuts") else None
    for o in ovs:   # hold：接管一直停到片尾（行动号召收尾）
        if o.get("type") == "frame" and o.get("hold") and total:
            o["t"] = [float(o["t"][0]), round(total, 3)]
    wins = windows({"overlays": ovs})
    out: List[dict] = []
    for o in ovs:
        typ = o.get("type")
        win = _in_window(o, wins) if typ not in ("frame", "broll") else None
        if typ == "proof":
            out += _proof(o, sb, W, H, win)
        elif typ == "flow":
            out += _flow(o, W, H, win)
        elif typ == "cta":
            if o.get("hold") and total:
                o = dict(o, t=[float(o["t"][0]), round(total, 3)])
            out += _cta(o, W, H, win)
        elif typ == "countdown":
            out += _countdown(o, W, H)
        else:
            out.append(o)
    # 落在接管期间的卡片：底板版、放进面板区；纸面背景改白卡深字
    for o in out:
        if o.get("type") in ("frame", "broll", "proof_img", "ring", "confetti", "glow", "image", "clip", "cutout"):
            continue
        win = _in_window(o, wins)
        if not win or o.get("_raw"):
            continue
        o.setdefault("lite", False)
        if o.get("pos") is None and o.get("_xy") is None and o.get("type") not in ("lower_third", "avatar"):
            o["_xy"] = [0.5, PANEL_TOP]
            o.setdefault("align", "center")
        if win.get("bg") == "paper" and not o.get("_result"):
            o["colors"] = dict(ON_PAPER, **(o.get("colors") or {}))
    for o in out:   # 纸面上的无底板文字：不用给画面用的深色描边（在浅底上发脏）
        w = _in_window(o, wins) if o.get("type") == "text" else None
        if w and w.get("bg") == "paper":
            o.setdefault("halo", False)
    sb["overlays"] = out
    return sb
