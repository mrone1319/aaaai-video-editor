"""时间线：把「保留的原片区间」映射到成片时间轴。"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

Range = Tuple[float, float]


def split_speed(cuts: Sequence, speed: Optional[list]) -> List[Tuple[float, float, float]]:
    """剪辑段按变速区间（原片时间）切开，回传 [(起, 止, 倍速)]。没有变速就全部 1.0。
    cuts 每段可以是 (起, 止) 或已经带倍速的 (起, 止, 倍速)。"""
    regs = []
    for r in speed or []:
        try:
            a, b, x = float(r["s"][0]), float(r["s"][1]), float(r.get("x", 1.0))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if b > a and x > 0 and abs(x - 1.0) > 1e-6:
            regs.append((a, b, max(0.25, min(4.0, x))))
    out: List[Tuple[float, float, float]] = []
    for c in cuts:
        a, b = float(c[0]), float(c[1])
        r0 = float(c[2]) if len(c) > 2 else 1.0
        if b <= a:
            continue
        if not regs or r0 != 1.0:
            out.append((a, b, r0))
            continue
        pts = sorted({a, b} | {x for ra, rb, _ in regs for x in (ra, rb) if a < x < b})
        for u, v in zip(pts, pts[1:]):
            if v - u < 1e-6:
                continue
            mid = (u + v) / 2.0
            x = next((rx for ra, rb, rx in regs if ra <= mid < rb), 1.0)
            out.append((round(u, 4), round(v, 4), x))
    return out


class Timeline:
    """保留区间 → 成片时间轴。

    给了 fps 就把每段长度量化到整帧：渲染时每段也锁成同样的帧数，
    这样卡片、字幕用的时间和画面逐帧对得上，长片不会越到后面越漂。
    """

    def __init__(self, cuts: Sequence, fps: float = 0.0, speed: Optional[list] = None):
        # 保留 storyboard 写的顺序（不排序）：可以把后面的一句挪到开头当 hook，或重复一次当预告
        # speed：变速区间（原片时间）[{"s": [起, 止], "x": 倍速}]；有的话剪辑段在区间边界切开，各段有自己的倍速
        segs = split_speed(cuts, speed)
        self.cuts = [(a, b) for a, b, _x in segs]
        self.rates = [x for _a, _b, x in segs]
        self.varied = any(abs(x - 1.0) > 1e-6 for x in self.rates)
        self.fps = float(fps or 0)
        self.offsets: List[float] = []
        self.lengths: List[float] = []
        acc = 0.0
        for (a, b), x in zip(self.cuts, self.rates):
            ln = (b - a) / x
            if self.fps:
                ln = max(1, round(ln * self.fps)) / self.fps
            self.offsets.append(acc)
            self.lengths.append(ln)
            acc += ln
        self.duration = acc

    def frames(self, i: int) -> int:
        return max(1, round(self.lengths[i] * self.fps)) if self.fps else 0

    def boundaries(self) -> List[float]:
        """各段在成片时间轴上的起点（分段渲染优先切在这些天然硬切点上）。"""
        return list(self.offsets[1:])

    def segments(self) -> List[Tuple]:
        """渲染用的剪辑段：没有变速就是 (起, 止)（和以前一样），有变速就是 (起, 止, 倍速)。"""
        if not self.varied:
            return list(self.cuts)
        return [(a, b, x) for (a, b), x in zip(self.cuts, self.rates)]

    def to_source(self, t: float) -> float:
        """成片时间 → 原片时间。"""
        for (ca, _cb), off, ln, x in zip(self.cuts, self.offsets, self.lengths, self.rates):
            if off <= t < off + ln + 1e-9:
                return ca + (t - off) * x
        return self.cuts[-1][0] + self.lengths[-1] * self.rates[-1] if self.cuts else t

    def source_ranges(self, a: float, b: float) -> List[Range]:
        """成片区间 [a,b] 反查成原片区间（分段渲染时用）。"""
        out: List = []
        for (ca, _cb), off, ln, x in zip(self.cuts, self.offsets, self.lengths, self.rates):
            lo, hi = max(a, off), min(b, off + ln)
            if hi > lo:
                out.append((ca + (lo - off) * x, ca + (hi - off) * x, x) if self.varied else
                           (ca + (lo - off), ca + (hi - off)))
        return out

    def clip(self, a: float, b: float) -> List[Range]:
        """原片区间 [a,b] 与各保留区间相交的部分，换算成成片时间。"""
        out: List[Range] = []
        for (ca, _cb), off, ln, x in zip(self.cuts, self.offsets, self.lengths, self.rates):
            lo, hi = max(a, ca), min(b, ca + ln * x)
            if hi > lo:
                out.append((off + (lo - ca) / x, off + (hi - ca) / x))
        return out
