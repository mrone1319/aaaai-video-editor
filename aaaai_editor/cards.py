"""卡片版面：把一条 overlay 规格算成「底板 + 文字块」的绝对坐标与时间。

版面统一走「竖向块堆叠」：每种卡片只负责给出内容块，
尺寸、换行、定位、动画由同一套逻辑算，所以加新卡片类型只要加一个 blocks_* 函数。
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .theme import resolve_colors

MARGIN_X = 0.058   # 左右安全边距（相对宽）
TOP_M = 0.085      # 上安全边距（相对高）
BOT_M = 0.190      # 下安全边距：给字幕留位，卡片不压字幕
PAD = 0.050        # 卡片内边距（相对宽）
LH = 1.34          # 行高倍数（基准）


def lh_for(size: float, U: float) -> float:
    """行高按字号收放：大标题收紧（松了显得散），小字放宽（挤了不好读）。"""
    r = size / max(1.0, float(U))
    if r >= 0.075:
        return 1.16
    if r >= 0.055:
        return 1.24
    if r <= 0.032:
        return 1.42
    return LH
DI, DO = 0.42, 0.30  # 入场／出场时长（秒）
# 每种卡片的入场时长：越大的东西给越多时间，越小的越干脆（动效有轻重，画面才有节奏）
DI_BY_TYPE = {"title": 0.46, "quote": 0.46, "bullets": 0.40, "rows": 0.40, "compare": 0.40,
              "icons": 0.38, "stat": 0.34, "step": 0.30, "lower_third": 0.38, "avatar": 0.38,
              "text": 0.34, "stamp": 0.22}


def is_cjk(ch: str) -> bool:
    return ord(ch) > 0x2E80


def est_w(text: str, size: float, mono: bool = False, wf: Optional[Tuple[float, float]] = None) -> float:
    """估算文字像素宽（用于给底板定尺寸；居中由 ffmpeg 的 text_w 精确处理）。

    wf＝(拉丁字宽, 字距)，富文本风格按角色给：展示字体、全大写、加字距都会变宽。
    """
    if wf:
        lat, trk = wf
    else:
        lat, trk = (0.62 if mono else 0.55), 0.0  # 等宽字重较厚，估窄了底板留白会不够
    return (sum(1.0 if is_cjk(c) else lat for c in text) + trk * len(text)) * size


def width_factor(th: dict, role: str, mono: bool) -> Optional[Tuple[float, float]]:
    """富文本风格的字宽估算。drawtext 风格返回 None，走原来的估算，版面逐位不变。"""
    if th.get("text_engine") != "ass":
        return None
    from .richtext import role_cfg
    cfg = role_cfg(th, role)
    if cfg["font"] == "display":
        lat = float((th.get("display_font") or {}).get("width", 0.84 if cfg["upper"] else 0.66))
    elif mono or cfg["font"] == "mono":
        lat = 0.62
    elif cfg["upper"]:
        lat = 0.68
    else:
        lat = 0.56
    if cfg["bold"] and lat < 0.8:
        lat += 0.03
    return lat, float(cfg["tracking"])


def wrap(text: str, size: float, maxw: float, mono: bool = False,
         wf: Optional[Tuple[float, float]] = None) -> List[str]:
    """按估算宽度换行。中文可任意断；英文按词断；原文里的空格保留（中英之间的空格不吃掉）。"""
    out: List[str] = []
    for para in str(text).split("\n"):
        toks, buf = [], ""
        for ch in para:
            if is_cjk(ch) or ch == " ":
                if buf:
                    toks.append(buf)
                    buf = ""
                toks.append(ch)
            else:
                buf += ch
        if buf:
            toks.append(buf)
        line = ""
        for t in toks:
            if t == " ":
                if line and not line.endswith(" "):
                    line += " "
                continue
            cand = line + t
            if line.strip() and est_w(cand.rstrip(), size, mono, wf) > maxw:
                out.append(line.rstrip())
                line = t
            else:
                line = cand
        if line.strip():
            out.append(line.rstrip())
    return out or [""]


def parse_marks(text: str) -> Tuple[str, List[bool]]:
    """**关键词** → (去掉标记的文字, 每个字是否高亮)。"""
    out, mask, on, i = [], [], False, 0
    s = str(text)
    while i < len(s):
        if s.startswith("**", i):
            on = not on
            i += 2
            continue
        out.append(s[i])
        mask.append(on)
        i += 1
    return "".join(out), mask


def line_runs(lines: List[str], plain: str, mask: List[bool]) -> List[Optional[List[Tuple[str, bool]]]]:
    """把换行后的每一行对回原文的高亮标记；整行没有高亮就给 None。"""
    res, p = [], 0
    for ln in lines:
        runs: List[List] = []
        for ch in ln:
            while p < len(plain) and plain[p] != ch:
                p += 1
            m = mask[p] if p < len(plain) else False
            p += 1
            if runs and runs[-1][1] == m:
                runs[-1][0] += ch
            else:
                runs.append([ch, m])
        res.append([(a, b) for a, b in runs] if any(b for _, b in runs) else None)
    return res


def fmt_num(v: float, style: str = "comma", digits: int = 0) -> str:
    s = ("{:,.%df}" % digits).format(v) if digits > 0 else "{:,.0f}".format(round(v))
    return s if style == "comma" else s.replace(",", "")


# ---------------------------------------------------------------- 内容块
def _blk(text, size, color, **kw) -> dict:
    d = {"kind": "text", "text": text, "size": size, "color": color, "gap": 0, "align": "center",
         "delay": 0.0, "mono": False, "lead": None, "lead_color": None, "lead_icon": None, "role": "text"}
    d.update(kw)
    return d


def _icon_blk(ov, th, W, scale=0.085) -> Optional[dict]:
    """卡片顶部的主图标（可选实心圆底 icon_badge）。"""
    if not ov.get("icon"):
        return None
    return {"kind": "icon", "name": ov["icon"], "size": round(W * scale * float(ov.get("icon_scale", 1.0))),
            "color": th["on_accent"] if ov.get("icon_badge") else th["accent"],
            "badge": th["accent"] if ov.get("icon_badge") else None,
            "gap": 0, "align": ov.get("align", "center"), "delay": 0.0}


LITE_TYPES = ("title", "quote", "lower_third", "stat", "bullets", "rows", "compare", "icons", "avatar")
LOWER_TYPES = ("lower_third", "avatar")   # 放在画面下沿的卡片


def _lighten(c: str, k: float = 0.5) -> str:
    """深色强调色放到深遮罩上：保持色相与饱和度，把明度提到 0.64（浅色风格的赭红、深粉等才看得清）。"""
    import colorsys
    c = c.lstrip("#")
    r, g, b_ = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, sat = colorsys.rgb_to_hls(r, g, b_)
    if l >= 0.55:
        return "#" + c.upper()
    r2, g2, b2 = colorsys.hls_to_rgb(h, 0.64, min(1.0, sat * 1.05))
    return "#%02X%02X%02X" % (round(r2 * 255), round(g2 * 255), round(b2 * 255))


def is_lite(ov, th) -> bool:
    """口播画面上的标题／金句／人名条：不用方块，用「画面边缘渐变遮罩＋左对齐粗体字＋强调色线条」。
    所有风格默认开启（风格里写 "lite": 0 关闭）；单张卡片可写 "lite": false 回到底板版。"""
    return (bool(th.get("lite", 1)) or ov.get("type") in (th.get("lite_types") or ())) \
        and ov.get("type") in LITE_TYPES and ov.get("lite", True) \
        and (not ov.get("bleed") or ov.get("chapter") is not None)   # 章节断章在 lite 里改成「压暗画面」，不整屏盖黑


def blocks_title(ov, th, W) -> Tuple[List[dict], str]:
    if is_lite(ov, th) and ov.get("chapter") is not None:
        b = []
        idx = ov.get("chapter")
        if idx is not True and str(idx) != "":
            b.append(_blk("%02d" % int(idx) if str(idx).isdigit() else str(idx), round(W * 0.24), th["accent"],
                          mono=True, align="left", role="number"))
        elif ov.get("kicker"):
            b.append(_blk(ov["kicker"], round(W * 0.033), th["accent"], mono=True, align="left", role="kicker"))
        b.append(_blk(ov.get("text", ""), round(W * float(ov.get("scale", 1.0)) * 0.098), th["text"], align="left",
                      gap=round(W * 0.004) if b else 0, role="title"))
        if ov.get("sub"):
            b.append(_blk(ov["sub"], round(W * 0.040), th["muted"], align="left", gap=round(W * 0.020), role="sub"))
        return b, "fit"
    if is_lite(ov, th):
        b = []
        if ov.get("kicker"):
            b.append(_blk(ov["kicker"], round(W * 0.033), th["accent"], mono=True, align="left", role="kicker"))
        b.append(_blk(ov.get("text", ""), round(W * float(ov.get("scale", 1.0)) * 0.092), th["text"], align="left",
                      gap=round(W * 0.018) if b else 0, role="title"))
        if ov.get("sub"):
            b.append(_blk(ov["sub"], round(W * 0.040), th["muted"], align="left", gap=round(W * 0.018), role="sub"))
        return b, "fit"
    b = []
    ib = _icon_blk(ov, th, W)
    if ib:
        b.append(ib)
    if ov.get("kicker"):
        b.append(_blk(ov["kicker"], round(W * 0.030), th["accent"], mono=True,
                      gap=round(W * 0.024) if b else 0, role="kicker"))
    b.append(_blk(ov.get("text", ""), round(W * float(ov.get("scale", 1.0)) * 0.068), th["text"],
                  gap=round(W * 0.022) if b else 0, role="title"))
    if ov.get("sub"):
        b.append(_blk(ov["sub"], round(W * 0.032), th["muted"], gap=round(W * 0.024), role="sub"))
    return b, "full"


def blocks_stat(ov, th, W) -> Tuple[List[dict], str]:
    lite = is_lite(ov, th)
    b = []
    ib = _icon_blk(ov, th, W, 0.075)
    if ib:
        b.append(ib)
    al = "left" if lite else "center"
    if ov.get("kicker"):
        b.append(_blk(ov["kicker"], round(W * (0.033 if lite else 0.028)), th["accent"] if lite else th["muted"],
                      mono=True, align=al, gap=round(W * 0.020) if b else 0, role="kicker"))
    c = {"to": float(ov.get("value", 0)), "from": float(ov.get("from", 0)),
         "prefix": ov.get("prefix", ""), "suffix": ov.get("suffix", ""),
         "digits": int(ov.get("digits", 0)), "style": ov.get("format", "comma"),
         "count": bool(ov.get("count", True)), "dur": float(ov.get("count_dur", 1.0))}
    # 用终值字串量尺寸，计数过程中的中间值不会比它宽
    widest = c["prefix"] + fmt_num(max(abs(c["to"]), abs(c["from"])), c["style"], c["digits"]) + c["suffix"]
    num = _blk(widest, round(W * float(ov.get("scale", 1.0)) * (0.170 if lite else 0.150)),
               th["accent"], mono=True,
               align=al, gap=round(W * 0.012) if b else 0, role="number")
    num["counter"] = c
    # 单位（后缀，或单写 unit）小一号、换强调色：数字是主角，单位是配角
    unit = ov.get("unit") or (ov.get("suffix") if ov.get("suffix") and not str(ov.get("suffix")).isdigit() else "")
    if unit:
        num["unit"] = unit
        num["unit_scale"] = float(ov.get("unit_scale", 0.54))
        num["unit_color"] = th["accent"]
        num["color"] = th["text"]          # 数字用正文色、单位用强调色：主次分明
        if not ov.get("suffix"):
            c["suffix"] = unit
            widest = c["prefix"] + fmt_num(max(abs(c["to"]), abs(c["from"])), c["style"], c["digits"]) + unit
            num["text"] = widest
    b.append(num)
    if ov.get("label"):
        b.append(_blk(ov["label"], round(W * (0.040 if lite else 0.034)), th["text"] if lite else th["muted"],
                      align=al, gap=round(W * 0.010), role="label"))
    ratio = ov.get("bar")
    if ratio is None and ov.get("of"):          # 写了总量就自动算占比
        try:
            ratio = float(ov["value"]) / float(ov["of"])
        except (TypeError, ZeroDivisionError, ValueError):
            ratio = None
    if ratio is not None:
        pl_ = th["plate"][-1] if isinstance(th["plate"], (list, tuple)) else th["plate"]
        dark = lite or sum(int(pl_.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) < 3 * 128
        b.append({"kind": "bar", "size": max(4, round(W * 0.011)), "gap": round(W * 0.026),
                  "ratio": float(ratio), "color": th["accent"], "dark": dark,
                  "align": al, "delay": 0.0, "text": "", "mono": False, "color_": None})
    return b, "fit"


def _stagger(items: List[str], mode) -> List[float]:
    """错峰出现的延迟。数字＝固定间隔；"auto"＝按上一条的字数决定（读得完再出下一条），
    这是「内容驱动」的节奏——不是随机抖动，也不是机械等距。"""
    if mode != "auto":
        return [i * float(mode) for i in range(len(items))]
    out, acc = [], 0.0
    for i, t in enumerate(items):
        out.append(acc)
        acc += min(0.55, 0.10 + 0.018 * len(t))
    return out


def _at(items, ov, delays: List[float]) -> List[float]:
    """每条可写 at（成片秒数）：对准口播说到这一条的时刻出现；没写的沿用错峰。"""
    t0 = float(ov["t"][0])
    return [max(0.0, float(it["at"]) - t0) if isinstance(it, dict) and it.get("at") is not None else d
            for it, d in zip(items, delays)]


def blocks_bullets(ov, th, W) -> Tuple[List[dict], str]:
    lite = is_lite(ov, th)
    b = []
    if ov.get("kicker"):
        b.append(_blk(ov["kicker"], round(W * (0.033 if lite else 0.028)), th["accent"], mono=True, align="left",
                      role="kicker"))
    if ov.get("title"):
        b.append(_blk(ov["title"], round(W * (0.062 if lite else 0.050)), th["text"], align="left",
                      gap=round(W * 0.012) if b else 0, role="heading"))
    raw = ov.get("items", [])
    texts = [it["text"] if isinstance(it, dict) else str(it) for it in raw]
    delays = _at(raw, ov, _stagger(texts, ov.get("stagger", 0.16)))
    head = len(b)
    for i, it in enumerate(raw):
        icon = it.get("icon") if isinstance(it, dict) else ov.get("marker_icon")
        blk = _blk(texts[i], round(W * (0.046 if lite else 0.042)), th["text"], align="left",
                   gap=(round(W * 0.030) if (i == 0 and head) else (round(W * 0.026) if i else 0)),
                   delay=delays[i], role="item")
        if icon:
            blk["lead_icon"] = icon
            blk["lead_color"] = (it.get("color") if isinstance(it, dict) else None) or th["accent"]
        else:
            blk["lead"] = "%02d" % (i + 1)
            blk["lead_color"] = th["accent"]
        b.append(blk)
    return b, "full"


def blocks_quote(ov, th, W) -> Tuple[List[dict], str]:
    if is_lite(ov, th):
        b = [_blk("「%s」" % ov.get("text", ""), round(W * 0.066), th["text"], align="left", role="quote")]
        if ov.get("by"):
            b.append(_blk("— " + ov["by"], round(W * 0.030), th["muted"], align="left",
                          gap=round(W * 0.020), role="by"))
        return b, "fit"
    b = []
    ib = _icon_blk(dict(ov, align="left"), th, W, 0.07)
    if ib:
        b.append(ib)
    b.append(_blk("「%s」" % ov.get("text", ""), round(W * 0.056), th["text"], align="left",
                  gap=round(W * 0.022) if b else 0, role="quote"))
    if ov.get("by"):
        b.append(_blk("— " + ov["by"], round(W * 0.030), th["muted"], align="left",
                      gap=round(W * 0.026), role="by"))
    return b, "full"


def blocks_avatar(ov, th, W) -> Tuple[List[dict], str]:
    """头像牌：左边圆形照片（外圈强调色），右边姓名＋身份。照片由 layout 留位置、overlays 贴上。"""
    lite = is_lite(ov, th)
    ind = round(W * float(ov.get("photo_size", 0.15))) + round(W * 0.030)
    b = [_blk(ov.get("name", ""), round(W * 0.050), th["text"], align="left", role="name", indent=ind)]
    if ov.get("role"):
        b.append(_blk(ov["role"], round(W * 0.032), th["accent"] if lite else th["muted"], align="left",
                      gap=round(W * 0.010), role="position", indent=ind))
    return b, "fit"


def blocks_lower_third(ov, th, W) -> Tuple[List[dict], str]:
    lite = is_lite(ov, th)
    b = [_blk(ov.get("name", ""), round(W * (0.048 if lite else 0.042)), th["text"], align="left", role="name")]
    if ov.get("role"):
        b.append(_blk(ov["role"], round(W * (0.031 if lite else 0.027)), th["accent"] if lite else th["muted"],
                      align="left", gap=round(W * (0.010 if lite else 0.008)),
                      role="position"))
    return b, "fit"


def blocks_stamp(ov, th, W) -> Tuple[List[dict], str]:
    blk = _blk(ov.get("text", ""), round(W * 0.029 * float(ov.get("scale", 1.0))), th["on_accent"], mono=True,
               role="stamp")
    if ov.get("icon"):  # 图标在字前：改左对齐，底板宽按「图标＋字」算
        blk.update(lead_icon=ov["icon"], lead_color=th["on_accent"], align="left")
    return [blk], "pill"


def blocks_icons(ov, th, W) -> Tuple[List[dict], str]:
    """图标宫格：每格一个图标＋一行标签，一行最多 cols 格。"""
    lite = is_lite(ov, th)
    al = "left" if lite else "center"
    b = []
    if ov.get("kicker"):
        b.append(_blk(ov["kicker"], round(W * (0.033 if lite else 0.028)), th["accent"], mono=True, align=al,
                      role="kicker"))
    if ov.get("title"):
        b.append(_blk(ov["title"], round(W * (0.062 if lite else 0.048)), th["text"], align=al,
                      gap=round(W * 0.012) if b else 0, role="heading"))
    items = [it if isinstance(it, dict) else {"icon": str(it)} for it in ov.get("items", [])]
    labels = [it.get("label", "") for it in items]
    b.append({"kind": "grid", "items": items, "delays": _stagger(labels, ov.get("stagger", 0.12)),
              "cols": int(ov.get("cols", min(4, max(1, len(items))))),
              "icon_color": th["accent"], "label_color": th["text"],
              "badge": th["accent"] if ov.get("icon_badge") else None,
              "badge_glyph": th["on_accent"],
              "gap": round(W * 0.034) if b else 0, "delay": 0.0})
    return b, "full"


def blocks_text(ov, th, W) -> Tuple[List[dict], str]:
    col = ov.get("color") or th["text"]
    if isinstance(col, str) and col.startswith("@"):   # "@muted" 这类：引用风格的语义色
        col = th.get(col[1:], th["text"])
    return [_blk(ov.get("text", ""), round(W * float(ov.get("scale", 1.0)) * 0.056), col,
                 role=ov.get("role") or "free")], "none"


def blocks_step(ov, th, W) -> Tuple[List[dict], str]:
    """工作流步骤卡（flow 展开出来的一张）：图标＋一行小字＋粗体大字，置中。"""
    b = []
    ib = _icon_blk(ov, th, W, 0.058)
    if ib:
        b.append(ib)
    if ov.get("top"):
        b.append(_blk(ov["top"], round(W * 0.026), th["muted"], gap=round(W * 0.012) if b else 0, role="label"))
    b.append(_blk(ov.get("big", ""), round(W * float(ov.get("scale", 1.0)) * 0.040), th["text"],
                  gap=round(W * 0.008) if b else 0, role="heading"))
    return b, "fit"


def blocks_rows(ov, th, W) -> Tuple[List[dict], str]:
    """编号行卡：每条一张小卡，左边强调色方块编号，右边标题／标签／说明。"""
    lite = is_lite(ov, th)
    b = []
    if ov.get("kicker"):
        b.append(_blk(ov["kicker"], round(W * (0.033 if lite else 0.028)), th["accent"], mono=True, align="left",
                      role="kicker"))
    if ov.get("title"):
        b.append(_blk(ov["title"], round(W * (0.066 if lite else 0.054)), th["text"], align="left",
                      gap=round(W * 0.012) if b else 0, role="heading"))
    if ov.get("sub"):
        b.append(_blk(ov["sub"], round(W * 0.030), th["muted"], align="left", gap=round(W * 0.014), role="sub"))
    items = [it if isinstance(it, dict) else {"title": str(it)} for it in ov.get("items", [])]
    b.append({"kind": "rows", "items": items,
              "delays": _at(items, ov, _stagger([it.get("title", "") for it in items], ov.get("stagger", 0.14))),
              "gap": round(W * 0.034) if b else 0, "delay": 0.0})
    return b, "full"


def blocks_compare(ov, th, W) -> Tuple[List[dict], str]:
    """对比：上下两组（竖屏比左右并排好读）。前一组淡色＋叉，后一组价值色＋勾。"""
    lite = is_lite(ov, th)
    b = []
    if ov.get("kicker"):
        b.append(_blk(ov["kicker"], round(W * (0.033 if lite else 0.028)), th["accent"], mono=True, align="left",
                      role="kicker"))
    groups = [(ov.get("left") or {}, "cross", th["muted"], th["muted"]),
              (ov.get("right") or {}, "check", th.get("value") or th["accent"], th["text"])]
    t0 = 0.0
    for gi, (g, icon, mark, col) in enumerate(groups):
        if g.get("title"):
            b.append(_blk(g["title"], round(W * 0.036), mark, align="left", delay=t0,
                          gap=round(W * (0.040 if gi else 0.018)) if b else 0, role="heading"))
        for k, x in enumerate(g.get("items") or []):
            blk = _blk(str(x), round(W * (0.060 if gi else 0.052)), col, align="left", delay=t0,
                       gap=round(W * 0.012), role="item")
            blk["lead_icon"], blk["lead_color"] = icon, mark
            b.append(blk)
        t0 = float(ov.get("reveal", 0.6))   # 第二组晚一点出现：先说「以为」再说「其实」
    return b, "full"


BUILDERS = {"compare": blocks_compare, "title": blocks_title, "stat": blocks_stat, "bullets": blocks_bullets,
            "quote": blocks_quote, "lower_third": blocks_lower_third, "avatar": blocks_avatar, "stamp": blocks_stamp,
            "text": blocks_text, "icons": blocks_icons, "rows": blocks_rows, "step": blocks_step,
            "callout": blocks_stamp}   # callout＝画面上的小标注，版式与印章相同

ANCHORS = {"center": (0.5, 0.5), "top": (0.5, 0.0), "bottom": (0.5, 1.0),
           "top_left": (0.0, 0.0), "top_right": (1.0, 0.0),
           "bottom_left": (0.0, 1.0), "bottom_right": (1.0, 1.0),
           "left": (0.0, 0.5), "right": (1.0, 0.5)}
# 口播画面：卡片默认放上方，避开脸（人通常在画面中间）
DEFAULT_POS = {"avatar": "bottom_left", "lower_third": "bottom_left", "stamp": "top_left", "title": "top", "quote": "top", "stat": "top", "bullets": "top",
               "rows": "top", "compare": "top", "icons": "top"}


def layout(ov: dict, th: dict, W: int, H: int, fps: float) -> dict:
    """算出底板、文字项、图标项的绝对坐标、时间、动画。"""
    if ov.get("_result"):  # 工作流最后一张「结果」卡：强调色底、字用强调色上的对比色
        th = dict(th, plate=th["accent"], plate_alpha=1.0, text=th["on_accent"], muted=th["on_accent"],
                  accent=th["on_accent"])
    if ov.get("colors"):  # 单张卡片改色，可写 "@value" 引用语义色
        th = resolve_colors(dict(th, **ov["colors"]))
    typ = ov["type"]
    lite = is_lite(ov, th)
    outro = (bool(ov.get("bleed")) and typ == "title" and bool(th.get("lite", 1)) and ov.get("lite", True)
             and ov.get("chapter") is None)
    if lite or outro:
        pl_ = th["plate"][-1] if isinstance(th["plate"], (list, tuple)) else th["plate"]
        dark = sum(int(pl_.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) < 3 * 128
        if dark:   # 深色遮罩上的灰字看不清：提亮
            th = dict(th, muted="#E4E4E7")
        else:      # 浅色风格：遮罩改用风格的深色（白色字幕也看得清），字换成底板的浅色
            th = dict(th, scrim_color=th["text"], text=pl_, muted="#E4E4E7", accent=_lighten(th["accent"]),
                      value=_lighten(th.get("value") or th["accent"]),
                      hl=_lighten(th["accent"]) if th.get("hl") in (None, "@accent", th["accent"]) else th["hl"])
    # 字号与内距的基准：竖屏＝画面宽；横屏／方形按高度折算，卡片不会比画面还高
    U = min(W, int(H * 0.75))
    blocks, mode = BUILDERS[typ](ov, th, U)
    if ov.get("bleed") and not (lite and ov.get("chapter") is not None):
        mode = "bleed"
    mx, pad = round(W * MARGIN_X), round(U * PAD)
    if mode == "pill":
        pad = round(U * 0.026)
    bar_h = 0
    bleed_lite = outro
    if bleed_lite:   # 尾板：居中标题上方一条强调色短线
        bar_h = max(4, round(U * 0.0085))
        blocks[0]["gap"] = blocks[0].get("gap", 0) + bar_h + round(U * 0.036)
    if lite:
        if typ in LOWER_TYPES:   # 人名条／头像牌：字在竖线或照片右侧
            pad = round(U * 0.030)
        else:                      # 标题／金句：字左贴安全边，上方一条强调色短横线
            pad = 0
            bar_h = max(4, round(U * 0.0085))
            blocks[0]["gap"] = blocks[0].get("gap", 0) + bar_h + round(U * 0.030)
    fixed_w = min(W - 2 * mx, W * float(ov["width"])) if ov.get("width") and mode != "bleed" else None
    maxw_full = (fixed_w or (W - 2 * mx)) - 2 * pad

    # ---- 量尺寸：文字块换行，图标块定方，宫格等底板宽定了再算 ----
    lines_of: List[List[str]] = []
    for b in blocks:
        b["_lead_w"] = 0.0
        if b["kind"] != "text":
            lines_of.append([])
            continue
        if b.get("indent"):
            b["_lead_w"] = float(b["indent"])
        elif b.get("lead_icon"):
            b["_lead_w"] = b["size"] * 1.40
        elif b["lead"]:
            b["_lead_w"] = est_w(b["lead"] + "  ", b["size"] * 0.62, True)
        plain, mask = parse_marks(b["text"])   # **关键词** 只影响颜色，不参与量宽
        b["_wf"] = width_factor(th, b.get("role", "text"), b["mono"])
        ls = wrap(plain, b["size"], maxw_full - b["_lead_w"], b["mono"], b["_wf"])
        b["_runs"] = line_runs(ls, plain, mask) if any(mask) else [None] * len(ls)
        lines_of.append(ls)

    content_w = 0.0
    for b, ls in zip(blocks, lines_of):
        if b["kind"] == "icon":
            content_w = max(content_w, b["size"])
        for ln in ls:
            content_w = max(content_w, est_w(ln, b["size"], b["mono"], b.get("_wf")) + b["_lead_w"])

    if mode == "bleed":
        plate_w, cbox_x, cbox_w = W, mx + pad, W - 2 * mx - 2 * pad
    else:
        if fixed_w:
            plate_w = fixed_w
        elif mode == "full":
            plate_w = min(W - 2 * mx, round(U * 1.6))   # 横屏不拉满整个宽度
        else:
            plate_w = min(W - 2 * mx, content_w + 2 * pad)
        cbox_w = plate_w - 2 * pad

    for b in blocks:  # 宫格：底板宽已知，按格宽排
        if b["kind"] != "grid":
            continue
        n = len(b["items"])
        cols = max(1, min(b["cols"], n))
        cw = cbox_w / cols
        isz = min(cw * 0.46, U * 0.105)
        lsz = round(U * 0.030)
        rows, row_h, cell_lines = [], [], []
        for r0 in range(0, n, cols):
            row = list(range(r0, min(n, r0 + cols)))
            ls_row = [wrap(b["items"][i].get("label", ""), lsz, cw * 0.92) if b["items"][i].get("label")
                      else [] for i in row]
            cell_lines += ls_row
            lh = max([len(x) for x in ls_row] + [0]) * lsz * LH
            rows.append(row)
            row_h.append(isz + (U * 0.018 + lh if lh else 0))
        b.update(_cols=cols, _cw=cw, _isz=isz, _lsz=lsz, _rows=rows, _row_h=row_h,
                 _lines=cell_lines, _rgap=U * 0.030)

    for b in blocks:  # 编号行卡：底板宽已知，逐行量高
        if b["kind"] != "rows":
            continue
        if lite:   # 遮罩上的行卡更紧凑：少挡一点画面
            rp, bs, gx = U * 0.018, U * 0.050, U * 0.024
            ts, tgs, ds = round(U * 0.042), round(U * 0.026), round(U * 0.029)
        else:
            rp, bs, gx = U * 0.030, U * 0.058, U * 0.026
            ts, tgs, ds = round(U * 0.040), round(U * 0.026), round(U * 0.029)
        tw = cbox_w - rp * 2 - bs - gx
        rows = []
        for it in b["items"]:
            parts = []
            for key, sz, gap in (("title", ts, 0), ("tag", tgs, U * 0.006), ("desc", ds, U * 0.010)):
                if it.get(key):
                    plain, mask = parse_marks(it[key])
                    ls = wrap(plain, sz, tw, False, width_factor(th, "row_" + key, False))
                    parts.append((key, sz, gap if parts else 0, ls,
                                  line_runs(ls, plain, mask) if any(mask) else [None] * len(ls)))
            th_ = sum(g + len(ls) * sz * lh_for(sz, U) for _k, sz, g, ls, _r in parts)
            rows.append((parts, rp * 2 + max(bs, th_)))
        b.update(_rp=rp, _bs=bs, _gx=gx, _rowsm=rows, _rgap=U * (0.012 if lite else 0.020))

    def blk_h(b, ls):
        if b["kind"] == "rows":
            return sum(h for _p, h in b["_rowsm"]) + b["_rgap"] * (len(b["_rowsm"]) - 1)
        if b["kind"] == "icon":
            return b["size"]
        if b["kind"] == "grid":
            return sum(b["_row_h"]) + b["_rgap"] * (len(b["_rows"]) - 1)
        if b["kind"] == "bar":
            return b["size"]
        return len(ls) * b["size"] * lh_for(b["size"], U)

    photo_sz = round(U * float(ov.get("photo_size", 0.15))) if typ == "avatar" else 0
    if photo_sz:   # 头像牌：文字在照片旁边垂直置中
        text_h = sum(b["gap"] + blk_h(b, ls) for b, ls in zip(blocks, lines_of))
        blocks[0]["gap"] = blocks[0].get("gap", 0) + max(0.0, (photo_sz - text_h) / 2.0)
    body_h = sum(b["gap"] + blk_h(b, ls) for b, ls in zip(blocks, lines_of))
    if photo_sz:
        body_h = max(body_h, photo_sz)
    last = blocks[-1]
    body_h += (last["size"] * 0.16 if last["kind"] == "text"
               else last.get("_lsz", 0) * 0.16 if last["kind"] == "grid" else 0)

    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    anim = ov.get("anim") or ("rise" if typ != "stamp" else "fade")
    dx0, dy0 = {"rise": (0, round(H * 0.026)), "fall": (0, -round(H * 0.026)),
                "left": (-round(W * 0.05), 0), "right": (round(W * 0.05), 0),
                "pop": (0, round(H * 0.014)), "fade": (0, 0)}.get(anim, (0, 0))
    # 入场时长按卡片分工：大标题慢一点（稳），数字与小徽章快一点（脆）；pop 走带超调的曲线
    di = float(ov.get("di") or DI_BY_TYPE.get(typ, DI))
    if anim == "pop":
        di = min(di, 0.28)
    cv = "back" if anim in ("pop", "rise") and typ not in ("lower_third", "avatar", "text") else "smooth"

    if mode == "bleed":
        px, py, plate_h = 0, 0, H
        cur = (H - body_h) / 2.0
    else:
        plate_h = body_h + 2 * pad
        dpos = ({t: "top_left" for t in LITE_TYPES if t not in LOWER_TYPES} if lite else DEFAULT_POS)
        if lite and ov.get("chapter") is not None:
            dpos = {"title": "left"}   # 章节：画面中段偏左，像一页书的章节页
        ax, ay = ANCHORS.get(ov.get("pos") or dpos.get(typ, DEFAULT_POS.get(typ, "center")), (0.5, 0.5))
        top_m, bot_m = round(H * float(ov.get("_top_m", TOP_M))), round(H * BOT_M)   # _top_m：避脸时往上挪
        px = mx + ax * (W - 2 * mx - plate_w)
        py = top_m + ay * (H - top_m - bot_m - plate_h)
        if ov.get("_xy"):   # 指定位置：[水平中心, 上缘]（相对画面宽／高）——组合卡片与卡片接管的面板区用
            px = min(max(0.0, float(ov["_xy"][0]) * W - plate_w / 2.0), W - plate_w)
            py = float(ov["_xy"][1]) * H - (pad if mode == "none" else 0)   # 无底板的字：上缘就是字的上缘
        cbox_x = px + pad
        cur = py + pad

    plate = None
    if mode == "bleed":  # 整屏断章：底板只淡入淡出不位移，内容照常动画
        # 片尾（lite 风格）：半透明压暗，画面还看得到；想要全黑写 "dim": 1.0
        a_ = float(ov.get("dim", 0.82)) if bleed_lite else float(ov.get("opacity", 0.97))
        plate = {"w": W, "h": H, "radius": 0, "fill": th.get("scrim_color") or th["plate"],
                 "alpha": a_, "border": {"w": 0}, "shadow": {},
                 "x": 0, "y": 0, "dx": 0, "dy": 0, "t0": t0, "t1": t1, "di": di, "do": DO}
    elif lite:   # 渐变遮罩（不是方块）：标题／金句在画面上沿，人名条在下沿；颜色取风格底板色，字直接排在上面
        pl = th["plate"]
        sc_col = th.get("scrim_color") or (pl[-1] if isinstance(pl, (list, tuple)) else pl)
        chap = ov.get("chapter") is not None
        mid = bool(ov.get("_mid"))   # 避脸：人坐得高，卡片改放在下巴下面，遮罩只包住字、上下渐淡，不压脸
        if chap:
            band = H
        elif mid:
            band = int(round(plate_h + H * 0.32))
        elif typ in LOWER_TYPES:
            band = int(round(H * 0.40))
        else:   # 遮罩深的部分盖住内容，再往下渐渐透明（清单长，遮罩就长）
            content_end = py + plate_h
            band = int(round(min(H * 0.80, max(H * 0.38, content_end + H * 0.17))))
        by0 = H - band if (typ in LOWER_TYPES and not chap) else 0
        if mid:
            by0 = int(round(py - H * 0.16))
        plate = {"w": W, "h": band, "radius": 0, "fill": None, "alpha": 1.0, "border": {"w": 0}, "shadow": {},
                 "scrim": {"color": sc_col, "power": 1.3,
                           # 长清单会盖到脸：干脆把遮罩压深，变成一个明确的「清单时刻」，不要半透明地糊在脸上
                           "alpha": 0.80 if chap else (float(th.get("scrim_alpha", 0.78))
                                                      if (typ in LOWER_TYPES or py + plate_h < H * 0.40) else 0.90),
                           "hold": 1.0 if chap else (min(0.7, plate_h / float(band)) if mid else
                                                     (0.72 if typ in LOWER_TYPES
                                                      else min(0.72, max(0.45, (py + plate_h) / band)))),
                           "dir": "mid" if mid else ("up" if typ in LOWER_TYPES else "down")},
                 "x": 0, "y": by0, "dx": 0, "dy": 0, "t0": t0, "t1": t1, "di": di, "do": DO}
    elif mode != "none":
        if mode == "pill":
            plate = {"w": int(round(plate_w)), "h": int(round(plate_h)),
                     "radius": int(round(plate_h / 2)), "fill": th["accent"], "alpha": 1.0,
                     "border": {"w": 0}, "shadow": {"soft": 14, "alpha": 0.30, "dy": 5,
                                                    "color": "#000000"}}
        else:
            plate = {"w": int(round(plate_w)), "h": int(round(plate_h)), "radius": th["radius"],
                     "fill": th["plate"], "alpha": th["plate_alpha"], "border": th["border"],
                     "shadow": th["shadow"], "sheen": float(th.get("sheen", 0.05))}
        plate.update({"x": int(round(px)), "y": int(round(py)), "dx": dx0, "dy": dy0,
                      "t0": t0, "t1": t1, "di": di, "do": DO, "curve": cv})

    items: List[dict] = []
    icons: List[dict] = []
    shapes: List[dict] = []
    if bleed_lite:
        bw = max(round(U * 0.10), 40)
        shapes.append({"x": W / 2.0 - bw / 2.0, "y": cur, "w": bw, "h": bar_h, "r": bar_h / 2.0, "fill": th["accent"]})
    if lite and typ == "lower_third":
        bw = max(4, round(U * 0.008))
        shapes.append({"x": px, "y": py + pad, "w": bw, "h": body_h, "r": bw / 2.0, "fill": th["accent"]})
    elif lite:
        bw = max(round(U * 0.10), 40)
        shapes.append({"x": cbox_x, "y": py, "w": bw, "h": bar_h, "r": bar_h / 2.0, "fill": th["accent"]})
    ccx = cbox_x + cbox_w / 2.0
    common = {"t1": t1, "di": di, "do": DO, "dx": dx0, "dy": dy0, "curve": cv}

    def add_icon(name, x, y, size, color, badge, delay):
        icons.append(dict(common, name=name, x=round(x, 1), y=round(y, 1), size=int(round(size)),
                          color=color, badge=badge, t0=t0 + delay))

    for b, ls in zip(blocks, lines_of):
        cur += b["gap"]
        if b["kind"] == "bar":   # 量感条：一条底轨＋一段强调色，占比一眼看得出来
            h = b["size"]
            shapes.append({"x": cbox_x, "y": cur, "w": cbox_w, "h": h, "r": h / 2.0,
                           "fill": "#FFFFFF" if b["dark"] else "#000000", "alpha": 0.14})
            fw = max(h, cbox_w * min(1.0, max(0.02, b["ratio"])))
            shapes.append({"x": cbox_x, "y": cur, "w": fw, "h": h, "r": h / 2.0, "fill": b["color"]})
            cur += h
            continue
        if b["kind"] == "icon":
            x = ccx - b["size"] / 2.0 if b["align"] == "center" else cbox_x
            add_icon(b["name"], x, cur, b["size"], b["color"], b.get("badge"), b["delay"])
            cur += b["size"]
            continue
        if b["kind"] == "rows":
            ry = cur
            rp, bs, gx = b["_rp"], b["_bs"], b["_gx"]
            row_fill = th.get("row") or (th["plate"][-1] if isinstance(th["plate"], list) else th["plate"])
            line = th.get("line") or (th.get("border") or {}).get("color") or row_fill
            for i, (parts, rh) in enumerate(b["_rowsm"]):
                d = b["delays"][i]
                if lite:   # 遮罩上只留一层很淡的白色行底，分出每一条
                    shapes.append({"x": cbox_x, "y": ry, "w": cbox_w, "h": rh, "r": 16.0,
                                   "fill": "#FFFFFF", "alpha": 0.09})
                else:
                    shapes.append({"x": cbox_x, "y": ry, "w": cbox_w, "h": rh,
                                   "r": min(float(th["radius"]) * 0.6, 18.0), "fill": row_fill, "line": line})
                bx, by = cbox_x + rp, ry + rp
                shapes.append({"x": bx, "y": by, "w": bs, "h": bs, "r": bs * 0.26, "fill": th["accent"]})
                nsz = int(round(bs * 0.52))
                items.append(dict(common, size=nsz, color=th["on_accent"], mono=True, t0=t0 + d,
                                  y=int(round(by + (bs - nsz * 0.72) / 2.0)), cx=int(round(bx + bs / 2.0)),
                                  text=str(i + 1), stroke=False, role="badge"))
                ty = ry + rp
                tx = int(round(bx + bs + gx))
                col = {"title": th["text"], "tag": th["accent"], "desc": th["muted"]}
                for key, sz, gap, ls, runs in parts:
                    ty += gap
                    for li, ln in enumerate(ls):
                        items.append(dict(common, size=sz, color=col[key], mono=False, t0=t0 + d,
                                          y=int(round(ty)), x=tx, text=ln, stroke=False,
                                          role="row_" + key, runs=runs[li]))
                        ty += sz * lh_for(sz, U)
                ry += rh + b["_rgap"]
            cur = ry - b["_rgap"]
            continue
        if b["kind"] == "grid":
            k = 0
            ry = cur
            for r, row in enumerate(b["_rows"]):
                off = (b["_cols"] - len(row)) * b["_cw"] / 2.0  # 末行不满时居中
                for c, i in enumerate(row):
                    cx0 = cbox_x + off + c * b["_cw"]
                    it = b["items"][i]
                    d = b["delays"][i]
                    col = it.get("color") or (b["badge_glyph"] if b["badge"] else b["icon_color"])
                    add_icon(it["icon"], cx0 + (b["_cw"] - b["_isz"]) / 2.0, ry, b["_isz"], col,
                             b["badge"], d)
                    ly = ry + b["_isz"] + U * 0.018
                    for ln in b["_lines"][k]:
                        items.append(dict(common, size=b["_lsz"], color=b["label_color"], mono=False,
                                          t0=t0 + d, y=int(round(ly)), stroke=False, text=ln,
                                          cx=int(round(cx0 + b["_cw"] / 2.0)), role="label"))
                        ly += b["_lsz"] * LH
                    k += 1
                ry += b["_row_h"][r] + b["_rgap"]
            cur = ry - b["_rgap"]
            continue
        for li, ln in enumerate(ls):
            y = cur
            it = {"size": b["size"], "color": b["color"], "mono": b["mono"], "curve": cv,
                  "t0": t0 + b["delay"], "t1": t1, "di": di, "do": DO,
                  "dx": dx0, "dy": dy0, "y": int(round(y)), "stroke": mode == "none" and not lite and ov.get("halo", True),
                  "soft": False, "hl": th.get("hl") if lite else None,
                  "role": b.get("role", "text"), "runs": b["_runs"][li]}
            for k_ in ("unit", "unit_scale", "unit_color"):
                if b.get(k_) is not None and li == len(ls) - 1:
                    it[k_] = b[k_]
            if b["align"] == "center":
                it["cx"] = int(round(ccx))
            else:
                it["x"] = int(round(cbox_x + b["_lead_w"]))
            if b.get("counter") and li == 0:
                it["counter"] = b["counter"]
                it["text"] = None
            else:
                it["text"] = ln
            items.append(it)
            if bleed_lite and b.get("role") == "sub":   # 尾板的副标题：强调色胶囊里放深色字，像一个按钮
                fw = est_w(ln, b["size"], b["mono"], b.get("_wf"))
                ph, pw_ = b["size"] * 1.75, fw + b["size"] * 1.6
                shapes.append({"x": ccx - pw_ / 2.0, "y": y - b["size"] * 0.36, "w": pw_, "h": ph, "r": ph / 2.0,
                               "fill": th["accent"]})
                it["color"] = th["on_accent"]
                it["stroke"] = False
            if li == 0 and b.get("lead_icon"):
                isz = b["size"] * 0.95
                add_icon(b["lead_icon"], cbox_x, y + b["size"] * 0.60 - isz / 2.0, isz,
                         b["lead_color"], None, b["delay"])
            elif li == 0 and b["lead"]:
                items.append({"size": int(round(b["size"] * 0.62)), "color": b["lead_color"],
                              "mono": True, "t0": t0 + b["delay"], "t1": t1, "di": di, "do": DO,
                              "dx": dx0, "dy": dy0, "x": int(round(cbox_x)),
                              "y": int(round(y + b["size"] * 0.30)), "text": b["lead"],
                              "stroke": False, "role": "lead"})
            cur += b["size"] * lh_for(b["size"], U)
    L = {"plate": plate, "items": items, "icons": icons, "shapes": shapes, "t": (t0, t1)}
    # 闪光：主卡（标题、数据、金句、片尾）进场时，主文字旁边闪出几颗四角星
    if (typ in ("title", "stat", "quote") or bleed_lite) and ov.get("chapter") is None \
            and ov.get("sparkle", th.get("sparkle", True)):
        main = max((it for it in items if it.get("text") or it.get("counter")), key=lambda it: it["size"], default=None)
        if main:
            sz = float(main["size"])
            if main.get("counter"):
                c_ = main["counter"]
                txt = c_["prefix"] + fmt_num(max(abs(c_["to"]), abs(c_["from"])), c_["style"], c_["digits"]) + c_["suffix"]
            else:
                txt = main["text"]
            w_ = est_w(txt.replace("**", ""), sz, main.get("mono", False))
            x0 = main["x"] if main.get("x") is not None else main["cx"] - w_ / 2.0
            x1, y_ = x0 + w_, float(main["y"])
            st_ = t0 + di * 0.7
            spots = [(x1 + 0.12 * sz, y_ - 0.25 * sz, 0.95 * sz, 0.0), (x0 + w_ * 0.60, y_ - 0.50 * sz, 0.55 * sz, 0.14),
                     (x1 + 0.50 * sz, y_ + 0.62 * sz, 0.45 * sz, 0.26)]
            sp = []
            for cx_, cy_, s_, d_ in spots:
                s_ = max(24.0, min(s_, U * 0.16))
                sp.append({"cx": min(W - s_ * 0.6, max(s_ * 0.6, cx_)), "cy": min(H - s_ * 0.6, max(s_ * 0.6, cy_)),
                           "size": int(s_), "t": round(st_ + d_, 3)})
            if t1 - t0 > 3.2:   # 停留比较久：过一会儿大的那颗再闪一次
                sp.append(dict(sp[0], t=round(st_ + 1.9, 3)))
            L["sparkle"] = {"spots": sp, "color": th["accent"]}
    # 悬浮呼吸：进场落定后整张卡轻轻上下浮动（整屏章节／片尾不浮）
    if ov.get("float", th.get("float", True)) and mode != "bleed" and ov.get("chapter") is None and t1 - t0 > 1.2:
        L["float"] = {"a": max(2.0, round(U * 0.0036, 1)), "p": 3.2, "s": round(t0 + di + 0.05, 3)}
    if photo_sz:
        L["photo"] = {"file": ov.get("file", ""), "x": round(cbox_x), "y": round(py + pad + (body_h - photo_sz) / 2.0),
                      "size": photo_sz, "ring": th["accent"], "focus": float(ov.get("focus", 0.35)),
                      "t0": t0, "t1": t1, "di": di, "do": DO, "dx": dx0, "dy": dy0, "curve": cv}
    return L


def counter_steps(c: dict, t0: float, t1: float, fps: float) -> List[Tuple[float, float, str]]:
    """把计数动画摊成若干「值 + 显示区间」，避开 ffmpeg 表达式无法做千分位的限制。"""
    txt = lambda v: c["prefix"] + fmt_num(v, c["style"], c["digits"]) + c["suffix"]
    if not c["count"] or c["to"] == c["from"]:
        return [(t0, t1, txt(c["to"]))]
    dur = min(max(0.2, c["dur"]), max(0.2, t1 - t0 - 0.1))
    n = max(2, min(20, int(dur * fps)))
    steps, prev = [], None
    for i in range(n):
        p = (i + 1) / n
        e = 1 - (1 - p) ** 3  # ease-out
        v = c["from"] + (c["to"] - c["from"]) * e
        s = txt(v)
        a, b = t0 + dur * i / n, t0 + dur * (i + 1) / n
        if prev is not None and s == prev[2]:
            prev = (prev[0], b, s)
            steps[-1] = prev
        else:
            prev = (a, b, s)
            steps.append(prev)
    steps[-1] = (steps[-1][0], t1, txt(c["to"]))
    return steps
