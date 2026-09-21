"""分段渲染的切点规划。

长片一次编码会让滤镜图非常大（每个剪辑点两条滤镜，每张卡片一路输入），
分段能把内存和图规模压下来。但切点落在卡片或推近中间，动画会在接缝处重来一次，
所以切点只允许落在「所有卡片／推近窗口之外」的空隙。

音轨不分段——响度要按整支片子算，分段会让各段响度不一致。
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

Span = Tuple[float, float]


def merge(spans: Sequence[Span], pad: float = 0.0) -> List[Span]:
    out: List[Span] = []
    for a, b in sorted((x[0] - pad, x[1] + pad) for x in spans):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def forbidden(sb: dict) -> List[Span]:
    """不能在中间切开的时间段：卡片窗口（含淡出）与推近窗口。"""
    sp: List[Span] = []
    for ov in sb.get("overlays") or []:
        sp.append((float(ov["t"][0]), float(ov["t"][1])))
    for z in sb.get("zooms") or []:
        sp.append((float(z["t"][0]), float(z["t"][1])))
    return merge(sp, pad=0.35)


def _push_out(t: float, spans: Sequence[Span], fps: float) -> float:
    """把切点推到它所在窗口的末尾之后，直到落进空隙。"""
    step = 1.0 / max(fps, 1)
    moved = True
    while moved:
        moved = False
        for a, b in spans:
            if a < t < b:
                t = b + step
                moved = True
    return t


def _inside(t: float, spans: Sequence[Span]) -> bool:
    return any(a < t < b for a, b in spans)


def plan(total: float, spans: Sequence[Span], fps: float, target: float = 45.0,
         min_seg: float = 6.0, snap: Sequence[float] = ()) -> List[float]:
    """返回切点列表（成片时间，已对齐到整帧）。返回空表示不分段。"""
    bounds: List[float] = []
    cur = 0.0
    while total - cur > target * 1.5:
        t = _push_out(cur + target, spans, fps)
        # 能切在原有硬切点上就切在那里：不用从中间劈开一段素材，帧数天然是整数
        nat = [x for x in snap if t <= x <= total - min_seg and not _inside(x, spans)]
        if nat:
            t = nat[0]
        if total - t < min_seg or t - cur < min_seg:
            break
        t = round(t * fps) / fps
        if t <= cur:
            break
        bounds.append(t)
        cur = t
    return bounds


def should(sb: dict, duration: float, n_cuts: int) -> bool:
    """auto 模式的判断：够长、剪辑点够多或卡片够多，才值得分段。"""
    cfg = sb.get("segment") or {}
    mode = cfg.get("enabled", "auto")
    if mode is True:
        return True
    if mode is False:
        return False
    return duration > 90.0 or n_cuts > 120 or len(sb.get("overlays") or []) > 25


def window(sb: dict, s: float, e: float) -> dict:
    """把卡片／推近平移到以 s 为零点的段内时间，并丢掉不相交的。"""
    def shift(items):
        out = []
        for it in items or []:
            a, b = float(it["t"][0]), float(it["t"][1])
            if b <= s or a >= e:
                continue
            n = dict(it)
            n["t"] = [round(max(a, s) - s, 3), round(min(b, e) - s, 3)]
            out.append(n)
        return out
    seg = dict(sb)
    seg["overlays"] = shift(sb.get("overlays"))
    seg["zooms"] = shift(sb.get("zooms"))
    seg["_faces_off"] = s     # 脸的位置是整片时间：卡片避脸时要换回段内时间
    return seg
