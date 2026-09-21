"""字幕：transcript 分段 → 按标点/宽度切句 → 映射到成片时间轴 → ASS。

支持双语（每句可带英文一行）与关键词高亮（每句 hl 列表、全局 highlight、或 **标记**）。
切好的句子可导出成 work/captions.json 手改（修错字、填英文、标高亮）；
存的是**原片时间**，之后改剪辑点也不会错位。
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

from .timeline import Timeline

TRACK = "work/captions.json"

BREAK = "。！？!?；;\n"
SOFT = "，、,：:"
STRIP = "。！？!?；;，、,：:… —–"   # 句尾悬空的标点／破折号一并清掉

# 三套字幕样式（颜色为 ASS 的 &HAABBGGRR）
STYLES: Dict[str, dict] = {
    "clean": dict(size=0.031, bold=1, primary="&H00FFFFFF", outline="&H00000000", outline_w=0.0028,
                  shadow=1, margin_v=0.30, back="&H80000000", max_w=17, hold=0.40),
    "punch": dict(size=0.036, bold=1, primary="&H0000E0FF", outline="&H00000000", outline_w=0.0040,
                  shadow=1, margin_v=0.30, back="&H80000000", max_w=16, hold=0.40),
    "box": dict(size=0.030, bold=1, primary="&H00FFFFFF", outline="&HB0000000", outline_w=0.010,
                shadow=0, margin_v=0.30, back="&HB0000000", border_style=3, max_w=17, hold=0.40),
    # 双语＋高亮风格（配合同名卡片风格；关键词颜色与卡片高亮一致）
    # 口播字幕：字小一点、放在画面约 65% 处（不压桌面／不被 Reels 底部按钮盖住），每段更长、停得更久
    "mrone": dict(size=0.029, bold=1, primary="&H00FFFFFF", outline="&H00000000", outline_w=0.0022,
                  shadow=2, margin_v=0.30, back="&H80000000", hl="#FFC933", en_ratio=0.74,
                  en_font="Avenir Next Bold", max_w=17, hold=0.40),
    "otg": dict(size=0.030, bold=1, primary="&H00FFFFFF", outline="&H00000000", outline_w=0.0030,
                shadow=0, margin_v=0.30, back="&H00000000", hl="#FF2A3A", en_ratio=0.74,
                en_font="Avenir Next Bold", max_w=17, hold=0.40),
}
# 英文行用具体字形名：libass 给「Avenir Next」加粗时会挑中 Bold Italic，写死字形名才稳定是正体
DEF_HL, DEF_EN_RATIO, DEF_EN_FONT = "#FFD23F", 0.62, "Avenir Next Bold"


def width(s: str) -> float:
    """显示宽度：CJK 全角=1，其余=0.55。"""
    return sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in s)


def is_latin(text: str) -> bool:
    """以拉丁字母为主（英文等）：按词断行，不在单词中间切。"""
    han = sum(1 for c in text if ord(c) > 0x2E80)
    alnum = sum(1 for c in text if c.isalnum())
    return alnum > 0 and han < 0.3 * alnum


def _split_latin(text: str, maxw: float) -> List[str]:
    out: List[str] = []
    for sent in re.split(r"(?<=[.!?;])\s+|\n", text):
        cur: List[str] = []
        for w in sent.split():
            if cur and width(" ".join(cur + [w]).rstrip(STRIP)) > maxw:
                out.append(" ".join(cur))
                cur = []
            cur.append(w)
        if cur:
            out.append(" ".join(cur))
    return [o.strip(STRIP) for o in out if o.strip(STRIP)]


def _cut_at(cur: str, maxw: float) -> int:
    """硬切位置：不超过 maxw；落在英文单词中间就退回到上一个空格。"""
    k, acc = 0, 0.0
    while k < len(cur) and acc + width(cur[k]) <= maxw:
        acc += width(cur[k])
        k += 1
    if 0 < k < len(cur) and cur[k - 1].isascii() and cur[k - 1].isalnum() and cur[k].isascii() and cur[k].isalnum():
        sp = cur.rfind(" ", 0, k)
        if sp > 0:
            k = sp + 1
    return max(k, 1)


def split_text(text: str, maxw: float) -> List[str]:
    """先按强标点切，再把过长的按弱标点/宽度切成不超过 maxw 的片段。"""
    if is_latin(text):
        return _split_latin(text, maxw)
    parts = [p for p in re.split("[%s]" % re.escape(BREAK), text) if p.strip()]
    out: List[str] = []
    for p in parts:
        chunks = [c for c in re.split("(?<=[%s])" % re.escape(SOFT), p) if c.strip()]
        cur = ""
        for c in chunks:
            if cur and width((cur + c).rstrip(STRIP)) > maxw:   # 句尾标点会被去掉，量宽时不算
                out.append(cur)
                cur = ""
            cur += c
            while width(cur) > maxw * 1.4:  # 单段仍过长：硬切
                k = _cut_at(cur, maxw)
                out.append(cur[:k])
                cur = cur[k:]
        if cur.strip():
            out.append(cur)
    return [o.strip(STRIP) for o in out if o.strip(STRIP)]


SIDE = 0.06   # 字幕左右边距（占画面宽）


def fit_units(style: str, w: int, h: int) -> float:
    """这个字幕样式下，一行放得下多少个中文字宽（中文每句必须单行）。"""
    st = STYLES.get(style) or STYLES["clean"]
    return w * (1 - 2 * SIDE) / (h * st["size"])


def resolve_style(sb: dict) -> str:
    """字幕样式没写就跟随卡片风格（mrone／otg 有配套的双语高亮字幕）；这两套字幕样式也受同名风格的授权限制。"""
    from . import theme
    cap = sb["captions"]
    if not cap.get("style"):
        cap["style"] = theme.theme(sb.get("style"), sb["_base"], sb.get("brand")).get("captions") or "clean"
    th = theme.all_themes(sb.get("_base"))
    if cap["style"] in th:
        theme.check_access(cap["style"], th[cap["style"]])
    return cap["style"]


def fit(sb: dict) -> float:
    resolve_style(sb)
    o = sb["output"]
    return max_width(sb["captions"], int(o["width"]), int(o["height"]))


def max_width(cap: dict, w: int, h: int) -> float:
    st = STYLES.get(cap.get("style") or "clean") or STYLES["clean"]
    return min(float(cap.get("max_width", st.get("max_w", 15))), fit_units(cap.get("style") or "clean", w, h))


def too_long(pcs: List[dict], cap: dict, w: int, h: int) -> List[str]:
    lim = fit_units(cap.get("style") or "clean", w, h)
    return [pc["text"] for pc in pcs if width(pc["text"].replace("**", "")) > lim + 0.3]


def pieces(segments: List[dict], maxw: float) -> List[dict]:
    """按句切好、按字数分配时长的字幕片段（原片时间）。"""
    out: List[dict] = []
    for sg in segments:
        ps = split_text(sg["text"], maxw)
        if not ps:
            continue
        weights = [max(width(p), 0.5) for p in ps]
        total = sum(weights)
        dur = sg["end"] - sg["start"]
        t = sg["start"]
        for p, w in zip(ps, weights):
            d = dur * w / total
            out.append({"s": [t, t + d], "text": p})
            t += d
    return out


def to_events(pcs: List[dict], tl: Timeline) -> list:
    """原片时间片段 → 成片时间事件 (起, 止, 文字, {en, hl})。"""
    ev = []
    for pc in pcs:
        extra = {"en": pc.get("en") or "", "hl": list(pc.get("hl") or [])}
        for a, b in tl.clip(float(pc["s"][0]), float(pc["s"][1])):
            if b - a >= 0.15:
                ev.append((a, b, pc["text"], extra))
    ev.sort(key=lambda e: (e[0], e[1], e[2]))
    return ev


def build_events(segments: List[dict], tl: Timeline, maxw: float) -> list:
    return to_events(pieces(segments, maxw), tl)


def track_path(sb: dict) -> str:
    return os.path.join(sb["_base"], sb["captions"].get("track") or TRACK)


def load_pieces(sb: dict, segments: List[dict], maxw: float) -> Tuple[List[dict], Optional[str]]:
    """有手改字幕轨就用它，否则按 transcript 自动切。返回 (片段, 字幕轨路径或 None)。"""
    p = track_path(sb)
    if os.path.isfile(p):
        return list(json.load(open(p, encoding="utf-8"))["pieces"]), p
    return pieces(segments, maxw), None


_FW = {",": "，", "?": "？", "!": "！", ":": "：", ";": "；"}


def zh_punct(t: str) -> str:
    """中文句里的半角标点转全角（whisper 常输出半角逗号）；英文之间的不动。"""
    out = list(t)
    for i, c in enumerate(out):
        if c in _FW:
            prev = out[i - 1] if i else ""
            nxt = out[i + 1] if i + 1 < len(out) else ""
            if (prev and ord(prev) > 0x2E80) or (nxt and ord(nxt) > 0x2E80):
                out[i] = _FW[c]
    return "".join(out)


def glossary(sb: dict) -> Dict[str, str]:
    """误听词表：程序通用 glossary.json → 当前频道档案 → 用户 ~/.aaaai-editor/glossary.json → 项目 captions.glossary。"""
    from . import config
    g: Dict[str, str] = {}
    files = [os.path.join(config.APP, "glossary.json")]
    files += [os.path.join(d, "glossary.json") for d in config.profile_dirs()]
    files.append(config.path("glossary.json"))
    for p in files:
        if os.path.isfile(p):
            g.update({k: v for k, v in json.load(open(p, encoding="utf-8")).items() if not k.startswith("_")})
    g.update(sb["captions"].get("glossary") or {})
    return g


def export_track(sb: dict, segments: List[dict], maxw: float, force: bool = False) -> Tuple[str, int, bool]:
    p = track_path(sb)
    if os.path.isfile(p) and not force:
        return p, len(json.load(open(p, encoding="utf-8"))["pieces"]), False
    gl = glossary(sb)
    fixed = []
    pcs = []
    for x in pieces(segments, maxw):
        t = zh_punct(x["text"])
        for wrong, right in gl.items():
            if wrong in t:
                t = t.replace(wrong, right)
                fixed.append("%s→%s" % (wrong, right))
        pcs.append({"s": [round(x["s"][0], 3), round(x["s"][1], 3)], "text": t, "en": "", "hl": []})
    if fixed:
        print("📖 词表自动修正 %d 处：%s" % (len(fixed), "、".join(sorted(set(fixed)))))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump({"version": 1,
               "note": "s 是原片时间（改剪辑点不会错位）。可改 text 修错字、填 en 出双语、"
                       "hl 列出要高亮的词，或在 text 里写 **关键词**。删掉本文件即回到自动字幕。",
               "pieces": pcs}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return p, len(pcs), True


def _ts(x: float) -> str:
    cs = int(round(x * 100))
    return "%d:%02d:%02d.%02d" % (cs // 360000, cs // 6000 % 60, cs // 100 % 60, cs % 100)


def _mask(text: str, words: Sequence[str]) -> Tuple[str, List[bool]]:
    from .cards import parse_marks
    plain, m = parse_marks(text)
    for w in words:
        if not w:
            continue
        i = plain.find(w)
        while i >= 0:
            for k in range(i, i + len(w)):
                m[k] = True
            i = plain.find(w, i + len(w))
    return plain, m


def _asscol(hexc: str) -> str:
    h = hexc.lstrip("#")
    return "&H%s%s%s&" % (h[4:6], h[2:4], h[0:2])


def _line(t: str, extra: Optional[dict], st: dict, h: int, words: Sequence[str], w: int = 0) -> str:
    extra = extra or {}
    lift = ("{\\an2\\pos(%d,%d)}" % (w // 2, int(h * 0.55))) if (extra.get("lift") and w) else ""
    hl = list(extra.get("hl") or []) + list(words or [])
    if not extra.get("en") and "**" not in t and not any(w_ and w_ in t for w_ in hl):
        return lift + t.replace("\n", "\\N")   # 没有双语／高亮（也没抬高）：与旧版输出逐字节相同
    plain, m = _mask(t, hl)
    out_prefix = lift
    esc = lambda x: x.replace("{", "｛").replace("}", "｝").replace("\n", "\\N")
    col = _asscol(st.get("hl") or DEF_HL)
    out, i = "", 0
    while i < len(plain):
        j = i
        while j < len(plain) and m[j] == m[i]:
            j += 1
        seg = esc(plain[i:j])
        out += ("{\\c%s}%s{\\c}" % (col, seg)) if m[i] else seg
        i = j
    if extra.get("en"):
        en_size = int(round(h * st["size"] * st.get("en_ratio", DEF_EN_RATIO)))
        usable = (w or h * 9 / 16.0) * (1 - 2 * SIDE)
        est = len(str(extra["en"])) * 0.56 * en_size
        if usable and est > usable:   # 英文太长：缩字号塞进一行，最小到中文字号的 0.42
            en_size = max(int(h * st["size"] * 0.42), int(en_size * usable / est))
        out += "\\N{\\fn%s\\fs%d\\b0\\i0}%s" % (st.get("en_font", DEF_EN_FONT), en_size,
                                                esc(str(extra["en"])))
    return out_prefix + out


def write_ass(events, path: str, w: int, h: int, font: str, style: str = "clean",
              highlight: Sequence[str] = (), margin_v: Optional[float] = None,
              size_scale: Optional[float] = None, hl_color: Optional[str] = None,
              faces: Optional[list] = None, t_off: float = 0.0) -> None:
    """margin_v：字幕底边离画面底部的比例（storyboard 的 captions.margin_v 可覆盖；0.30≈画面 70% 处）；
    size_scale：字号倍率（captions.size_scale）。"""
    st = dict(STYLES[style])
    if margin_v is not None:
        st["margin_v"] = float(margin_v)
    if size_scale:
        st["size"] = st["size"] * float(size_scale)
    if hl_color and not st.get("hl"):   # 通用字幕样式：关键词颜色跟着卡片风格的强调色
        st["hl"] = hl_color
    size = int(round(h * st["size"]))
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,"
        "Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,"
        "MarginR,MarginV,Encoding\n"
        "Style: Cap,%s,%d,%s,&H000000FF,%s,%s,%d,0,0,0,100,100,0,0,%d,%d,%d,2,%d,%d,%d,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    ) % (w, h, font, size, st["primary"], st["outline"], st["back"], st["bold"], st.get("border_style", 1),
         max(1, int(round(h * st["outline_w"]))), st["shadow"], int(w * 0.06), int(w * 0.06),
         int(h * st["margin_v"]))
    mvs = [None] * len(events)
    if faces:   # 字幕避脸：脸落在字幕位置的那几句，改放到下巴下面
        from . import faces as faces_mod
        mvs = faces_mod.margins([(e[0] + t_off, e[1] + t_off, e[2], e[3] if len(e) > 3 else None) for e in events],
                                faces, h, st, st["margin_v"])
    lines = ["Dialogue: 0,%s,%s,Cap,,0,0,%d,,%s" % (_ts(e[0]), _ts(e[1]), mv or 0,
                                                    _line(e[2], e[3] if len(e) > 3 else None, st, h, highlight, w))
             for e, mv in zip(events, mvs)]
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")
