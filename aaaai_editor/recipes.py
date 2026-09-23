"""配方：写一个意图，展开成一组卡片与推近。

规则来自 motion-graphic-video-editor 的剪辑公式库（四支参考片交叉验证，4/4 成立）：
  1. 绿＝能量／价值色，青＝静息／陈述色 —— stat_hit 用 value 色，chapter 用 state 色
  2. 黑场／低亮段一定放内容，不放空黑   —— chapter 是整屏暗底 + 内容，不是空黑
  3. 尾板＝品牌标独立 + 保持 + 音画同步淡出 —— outro 整屏品牌 + 片尾音画一起淡出
节奏：只有关键落点（数字落定、标题落地）会吸附到 storyboard 的 beats；
其余（列表逐条出现）按内容长度驱动，不随机抖动，也不机械等距。
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

REG: Dict[str, dict] = {}


def recipe(name: str, desc: str, required: Tuple[str, ...], optional: Tuple[str, ...] = ()):
    def deco(fn: Callable):
        REG[name] = {"fn": fn, "desc": desc, "required": ("t",) + required, "optional": optional}
        return fn
    return deco


def snap(t: float, beats: Optional[List[float]], tol: float = 0.12) -> float:
    """关键落点吸附到最近的拍点（容差内才吸），其余不动。"""
    if not beats:
        return t
    b = min(beats, key=lambda x: abs(x - t))
    return b if abs(b - t) <= tol else t


def _t(r) -> Tuple[float, float]:
    return float(r["t"][0]), float(r["t"][1])


def _clip_zoom(a: float, b: float, lo: float, hi: float) -> Optional[dict]:
    a, b = max(a, lo), min(b, hi - 0.05)
    return {"t": [round(a, 3), round(b, 3)]} if b - a >= 0.15 else None


@recipe("hook", "开场钩子：印章 + 大标题弹出，标题落地瞬间瞬切推近（冲击型）",
        ("text",), ("kicker", "sub", "stamp", "icon", "zoom"))
def _hook(r, beats):
    a, b = _t(r)
    ov = []
    if r.get("stamp"):
        ov.append({"type": "stamp", "t": [a, b], "text": r["stamp"], "pos": "top_left"})
    ov.append({"type": "title", "t": [a, b], "text": r["text"], "kicker": r.get("kicker"),
               "sub": r.get("sub"), "icon": r.get("icon"), "icon_badge": bool(r.get("icon")),
               "anim": "pop"})
    hit = snap(a + 0.26, beats)
    z = _clip_zoom(hit, hit + 0.55, a, b)
    zooms = [dict(z, to=float(r.get("zoom", 1.14)), style="punch")] if z else []
    return ov, zooms, None


@recipe("stat_hit", "数据冲击：数字从起始值跳到终值，落定瞬间瞬切推近；数字用价值绿",
        ("value",), ("label", "kicker", "prefix", "suffix", "from", "digits", "icon", "count_dur", "zoom"))
def _stat_hit(r, beats):
    a, b = _t(r)
    cd = float(r.get("count_dur", 1.0))
    ov = [{"type": "stat", "t": [a, b], "value": r["value"], "from": r.get("from", 0),
           "label": r.get("label"), "kicker": r.get("kicker"), "prefix": r.get("prefix", ""),
           "suffix": r.get("suffix", ""), "digits": r.get("digits", 0), "icon": r.get("icon"),
           "count_dur": cd, "anim": "pop", "colors": {"accent": "@value"}}]
    land = snap(a + 0.15 + cd, beats)
    z = _clip_zoom(land, land + 0.5, a, b)
    zooms = [dict(z, to=float(r.get("zoom", 1.10)), style="punch")] if z else []
    return ov, zooms, None


@recipe("chapter", "章节断章：画面整体压暗 + 大号章节数字（风格强调色）+ 标题（人仍看得见）",
        ("title",), ("index", "kicker", "sub", "opacity"))
def _chapter(r, beats):
    a, b = _t(r)
    kick = r.get("kicker") or ("CHAPTER %02d" % int(r["index"]) if r.get("index") is not None else None)
    return [{"type": "title", "t": [a, b], "bleed": True, "kicker": kick, "text": r["title"],
             "sub": r.get("sub"), "anim": "rise", "opacity": r.get("opacity", 1.0),
             "chapter": r.get("index", True),
             "under_captions": True}], [], None   # 章节页压暗整个画面，字幕要留在它上面


@recipe("steps", "步骤清单：可带标题与图标；每条可写 at 对准说到它的那一秒，否则按字数错峰；layout: rows 出编号行卡",
        ("items",), ("title", "kicker", "stagger", "pos", "layout"))
def _steps(r, beats):
    a, b = _t(r)
    if r.get("layout") == "rows":
        items = []
        for it in r["items"]:
            d = dict(it) if isinstance(it, dict) else {"text": str(it)}
            d.setdefault("title", d.pop("text", ""))
            items.append(d)
        return [{"type": "rows", "t": [a, b], "items": items, "title": r.get("title"),
                 "kicker": r.get("kicker"), "stagger": r.get("stagger", "auto"), "pos": r.get("pos")}], [], None
    return [{"type": "bullets", "t": [a, b], "items": r["items"], "title": r.get("title"),
             "kicker": r.get("kicker"), "stagger": r.get("stagger", "auto"), "pos": r.get("pos")}], [], None


@recipe("quote_pull", "金句：引言淡入 + 全程缓慢推近（柔和型）",
        ("text",), ("by", "icon", "zoom"))
def _quote(r, beats):
    a, b = _t(r)
    ov = [{"type": "quote", "t": [a, b], "text": r["text"], "by": r.get("by"), "icon": r.get("icon"),
           "anim": "fade"}]
    return ov, [{"t": [a, b], "to": float(r.get("zoom", 1.06)), "style": "smooth",
                 "ease": min(0.9, (b - a) / 2)}], None


@recipe("speaker", "人物介绍：姓名 + 头衔，从左滑入", ("name",), ("role",))
def _speaker(r, beats):
    a, b = _t(r)
    return [{"type": "lower_third", "t": [a, b], "name": r["name"], "role": r.get("role"),
             "anim": "left"}], [], None


@recipe("avatar", "头像牌：圆形照片（外圈强调色）＋姓名＋身份，讲到某个人时用；照片放 assets/",
        ("file", "name"), ("role", "pos", "focus", "photo_size"))
def _avatar(r, beats):
    a, b = _t(r)
    o = {"type": "avatar", "t": [a, b], "file": r["file"], "name": r["name"], "role": r.get("role"), "anim": "left"}
    for k in ("pos", "focus", "photo_size"):
        if r.get(k) is not None:
            o[k] = r[k]
    return [o], [], None


@recipe("outro", "尾板：画面半透明压暗 + 居中标题与按钮式标签，保持到片尾，音画同步淡出（dim 调深浅，1＝全黑）",
        ("text",), ("sub", "logo", "fade", "dim"))
def _outro(r, beats):
    a, b = _t(r)
    # t 往后多延 1 秒：尾板一直保持到片尾，不会在全局淡出之前自己先淡掉。
    # 排在字幕下层：最后一句话（常是「下期见」）的字幕仍然看得到。
    ov = [{"type": "title", "t": [a, b + 1.0], "bleed": True, "opacity": 1.0, "text": r["text"],
           "sub": r.get("sub"), "anim": "fade", "scale": 1.3, "under_captions": True, "dim": r.get("dim")}]
    if r.get("logo"):
        ov.append({"type": "image", "t": [a, b + 1.0], "file": r["logo"], "width": 0.30, "pos": "top"})
    fade = float(r.get("fade", min(1.2, max(0.3, (b - a) * 0.4))))
    return ov, [], {"fade": fade}


@recipe("brand_open", "品牌片头：整屏网状渐层底＋大字品牌名／主题＋一行副标，2–3 秒，画面照常播（不动时间轴）",
        ("text",), ("sub", "kicker", "logo", "dim", "bg"))
def _brand_open(r, beats):
    a, b = _t(r)
    ov = [{"type": "title", "t": [a, b], "bleed": True, "text": r["text"], "sub": r.get("sub"),
           "kicker": r.get("kicker"), "anim": "fade", "scale": 1.6, "align": "center", "lite": False,
           "colors": {"muted": "@accent"}, "dim": r.get("dim", 0.92), "_bleed_bg": r.get("bg", "mesh")}]
    if r.get("logo"):
        ov.append({"type": "image", "t": [a, b], "file": r["logo"], "width": 0.26, "pos": "top"})
    return ov, [], {}


@recipe("brand_close", "品牌片尾：整屏网状渐层底＋一句收尾＋账号名，保持到片尾并淡出",
        ("text",), ("sub", "logo", "fade", "dim", "bg"))
def _brand_close(r, beats):
    a, b = _t(r)
    ov = [{"type": "title", "t": [a, b + 1.0], "bleed": True, "text": r["text"], "sub": r.get("sub"),
           "anim": "fade", "scale": 1.6, "align": "center", "under_captions": True, "lite": False,
           "colors": {"muted": "@accent"}, "dim": r.get("dim", 0.92), "_bleed_bg": r.get("bg", "mesh")}]
    if r.get("logo"):
        ov.append({"type": "image", "t": [a, b + 1.0], "file": r["logo"], "width": 0.26, "pos": "top"})
    fade = float(r.get("fade", min(1.2, max(0.3, (b - a) * 0.4))))
    return ov, [], {"fade": fade}


@recipe("compare", "对比：上下两组，前一组淡色＋叉（以为／以前），后一组价值色＋勾（其实／现在），第二组晚一拍出现",
        ("left", "right"), ("kicker", "reveal", "pos"))
def _compare(r, beats):
    a, b = _t(r)
    return [{"type": "compare", "t": [a, b], "left": r["left"], "right": r["right"], "kicker": r.get("kicker"),
             "reveal": float(r.get("reveal", 0.6)), "pos": r.get("pos")}], [], None


@recipe("callout", "标注：带图标的小药丸，可排在人物后面",
        ("text",), ("icon", "pos", "behind"))
def _callout(r, beats):
    a, b = _t(r)
    return [{"type": "stamp", "t": [a, b], "text": r["text"], "icon": r.get("icon"),
             "pos": r.get("pos", "top_right"), "anim": "pop", "scale": float(r.get("scale", 1.35)),
             "behind_subject": bool(r.get("behind"))}], [], None


@recipe("takeover", "卡片接管：画面收进圆角框 + 人物头冲出框上缘；上方是标题或面板区（证据截图／工作流／行动号召）"
        "；bg=paper 纸面底；hold=true 停到片尾",
        (), ("text", "kicker", "sub", "focus", "zoom", "top", "height", "popout", "bg", "hold", "sfx"))
def _takeover(r, beats):
    a, b = _t(r)
    o = {"type": "frame", "t": [a, b]}
    for k in ("text", "kicker", "sub", "focus", "zoom", "top", "height", "popout", "bg", "hold", "sfx"):
        if r.get(k) is not None:
            o[k] = r[k]
    return [o], [], None


def expand(sb: dict) -> dict:
    """把 sb["recipes"] 展开进 overlays／zooms（接在手写的后面），并合并片尾淡出。"""
    rs = sb.get("recipes") or []
    if not rs:
        return sb
    beats = sb.get("beats")
    ovs, zms = list(sb.get("overlays") or []), list(sb.get("zooms") or [])
    ending = dict(sb.get("ending") or {})
    for i, r in enumerate(rs):
        name = r.get("use")
        if name not in REG:
            raise ValueError("第 %d 个配方 use=%r 不存在（可用：%s）" % (i + 1, name, " ".join(REG)))
        miss = [k for k in REG[name]["required"] if r.get(k) in (None, "", [])]
        if miss:
            raise ValueError("配方 %s 缺少参数：%s" % (name, ", ".join(miss)))
        o, z, e = REG[name]["fn"](r, beats)
        for x in o:
            for k, v in r.items():  # 通用字段透传：style／under_captions／behind_subject
                if k in ("style", "under_captions") and k not in x:
                    x[k] = v
        ovs += [{k: v for k, v in x.items() if v is not None} for x in o]
        zms += z
        if e and e.get("fade"):
            ending["fade"] = max(float(ending.get("fade", 0)), e["fade"])
    out = dict(sb)
    out["overlays"], out["zooms"] = ovs, zms
    if ending:
        out["ending"] = ending
    return out


def listing() -> str:
    rows = []
    for n, d in REG.items():
        req = ", ".join(d["required"])
        opt = ", ".join(d["optional"])
        rows.append("%-11s %s\n            必填：%s%s" % (n, d["desc"], req, ("   可选：" + opt) if opt else ""))
    return "\n".join(rows)
