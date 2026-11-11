"""章节目录：画面一侧固定一块目录，列出整支片的段落，讲到哪一段那一行就亮起来（「03/10」）。

清单型、教学型口播（「5 个工具」「18 种特效」）用：观众一眼知道讲到第几个、后面还有什么。

storyboard：
  "toc": {"title": "18 种特效", "items": [{"t": 3.2, "text": "掉落字"}, {"t": 6.0, "text": "巨大字幕"}],
          "footer": "收藏起来慢慢学", "side": "right", "end": 60}
  t 是成片秒数（该段开始）；关键词触发写 "toc": "名称" 会自动加进来。end 不写＝最后一项之后一直到片尾。
  可选：panel（底色，默认黑）、panel_alpha（不透明度，默认 0.55）、hl（亮起那一行的底色，默认米白）、scale（大小）。
"""
from __future__ import annotations

from typing import List

PANEL, CREAM, MUTED = "#000000", "#F6F2EA", "#D8D4C4"


def lines(sb: dict, W: int, H: int, fps: float, t_off: float = 0.0) -> List[str]:
    toc = sb.get("toc")
    if not isinstance(toc, dict) or not toc.get("items"):
        return []
    from . import richtext, sticker
    from .timeline import Timeline
    items = sorted(toc["items"], key=lambda x: float(x["t"]))
    total = None
    try:
        total = Timeline([tuple(c) for c in sb["cuts"]], sb["output"]["fps"], sb.get("speed")).duration
    except (KeyError, TypeError, ValueError):
        pass
    end = float(toc.get("end") or total or (float(items[-1]["t"]) + 4.0))
    starts = [float(x["t"]) - t_off for x in items]
    t_end = end - t_off
    if t_end <= 0:
        return []
    U = float(min(W, H)) * float(toc.get("scale", 1.2))   # 手机上看：比参考片的目录大一点才读得清
    fam = sticker.family("Yuanti SC")
    mono = sticker.family("Menlo")
    n = len(items)
    pw, rh = U * 0.215, U * 0.034
    x1 = W + U * 0.03 if toc.get("side", "right") == "right" else -U * 0.03
    px = x1 - pw if toc.get("side", "right") == "right" else x1
    py = H * 0.073
    ph = U * 0.068 + n * rh + U * 0.062
    out: List[str] = []

    def ev(a, b, layer, tags, body):
        if b - a > 0.004:
            out.append("Dialogue: %d,%s,%s,C,,0,0,0,,{%s}%s" % (layer, richtext._ts(max(0.0, a)), richtext._ts(b), tags, body))
    a0 = starts[0]
    pp, *_ = sticker.shape_of(sticker.rrect(0, 0, pw + U * 0.03, ph, U * 0.018))
    # 半透明黑底、边缘虚化（\\blur 羽化外框），叠在任何画面上都不抢眼
    pa = min(1.0, max(0.0, float(toc.get("panel_alpha", 0.55))))
    ev(a0, t_end, 900, "\\an7\\pos(%.1f,%.1f)\\bord0\\shad0\\blur%.1f\\1c%s\\1a&H%02X&\\fad(150,200)\\p1" % (
        px, py, U * 0.014, sticker._ac(toc.get("panel") or PANEL), int(round(255 * (1 - pa)))), pp)
    if toc.get("title"):
        ev(a0, t_end, 902, "\\an7\\pos(%.1f,%.1f)\\fn%s\\fs%.1f\\b1\\bord0\\shad0\\c%s\\fad(150,200)" % (
            px + U * 0.017, py + U * 0.017, fam, sticker.fs_tag(U * 0.020, fam), sticker._ac(MUTED)),
           richtext._esc(str(toc["title"])))
    for i, it in enumerate(items):   # 计数「03/18」：每段一行
        a = starts[i]
        b = starts[i + 1] if i + 1 < n else t_end
        ev(a, b, 902, "\\an9\\pos(%.1f,%.1f)\\fn%s\\fs%.1f\\b1\\bord0\\shad0\\c%s" % (
            x1 - U * 0.043 if toc.get("side", "right") == "right" else px + pw - U * 0.013, py + U * 0.020, mono,
            U * 0.017, sticker._ac(MUTED)), "%02d/%d" % (i + 1, n))

    def row_y(k):
        return py + U * 0.060 + k * rh

    # 亮起的那一行：0.12 秒滑过去（逐帧），其余时间静止
    hp, *_ = sticker.shape_of(sticker.rrect(0, 0, pw - U * 0.012, rh - U * 0.006, U * 0.006))
    hl = sticker._ac(toc.get("hl") or CREAM)
    for i in range(n):
        a = starts[i]
        b = starts[i + 1] if i + 1 < n else t_end
        slide = 0.12
        if i > 0:
            fa, fb = int(round(a * fps)), int(round(min(b, a + slide) * fps))
            for fr in range(fa, fb):
                p = 1 - (1 - min(1.0, (fr / fps - a) / slide)) ** 3
                y = row_y(i - 1 + p)
                ev((fr - 0.5) / fps, (fr + 0.5) / fps, 901, "\\an7\\pos(%.1f,%.1f)\\bord0\\shad0\\1c%s\\p1" % (
                    px + U * 0.008, y + U * 0.003, hl), hp)
            a = (fb - 0.5) / fps
        ev(a, b, 901, "\\an7\\pos(%.1f,%.1f)\\bord0\\shad0\\1c%s\\p1" % (px + U * 0.008, row_y(i) + U * 0.003, hl), hp)
    # 每一行字：亮起时墨黑，平时浅色
    for k, it in enumerate(items):
        txt = str(it.get("text", ""))
        size = U * (0.022 if len(txt) <= 6 else max(0.013, 0.150 / max(1, len(txt))))
        y = row_y(k) + rh / 2.0
        for i in range(n):
            a = starts[i]
            b = starts[i + 1] if i + 1 < n else t_end
            act = i == k
            col = "&H0B0A0A&" if act else sticker._ac("#E2E4D6")
            ncol = sticker._ac("#78746A") if act else sticker._ac("#788270")
            ev(a, b, 903, "\\an4\\pos(%.1f,%.1f)\\fn%s\\fs%.1f\\b1\\bord0\\shad0\\c%s" % (
                px + U * 0.017, y, mono, U * 0.015, ncol), "%02d" % (k + 1))
            ev(a, b, 903, "\\an4\\pos(%.1f,%.1f)\\fn%s\\fs%.1f\\b1\\bord0\\shad0\\c%s" % (
                px + U * 0.047, y, fam, sticker.fs_tag(size, fam), col), richtext._esc(txt))
    if toc.get("footer"):
        ev(a0, t_end, 902, "\\an7\\pos(%.1f,%.1f)\\fn%s\\fs%.1f\\b1\\bord0\\shad0\\c&HFFFFFF&\\fad(150,200)" % (
            px + U * 0.017, py + ph - U * 0.045, fam, sticker.fs_tag(U * 0.024, fam)),
           richtext._esc(str(toc["footer"]).replace("{n}", str(n))))
    return out
