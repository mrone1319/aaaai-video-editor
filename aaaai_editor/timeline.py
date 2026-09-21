"""时间线：把「保留的原片区间」映射到成片时间轴。"""
from __future__ import annotations

from typing import List, Tuple

Range = Tuple[float, float]


class Timeline:
    """保留区间 → 成片时间轴。

    给了 fps 就把每段长度量化到整帧：渲染时每段也锁成同样的帧数，
    这样卡片、字幕用的时间和画面逐帧对得上，长片不会越到后面越漂。
    """

    def __init__(self, cuts: List[Range], fps: float = 0.0):
        # 保留 storyboard 写的顺序（不排序）：可以把后面的一句挪到开头当 hook，或重复一次当预告
        self.cuts = [(float(a), float(b)) for a, b in cuts if b > a]
        self.fps = float(fps or 0)
        self.offsets: List[float] = []
        self.lengths: List[float] = []
        acc = 0.0
        for a, b in self.cuts:
            ln = b - a
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

    def to_source(self, t: float) -> float:
        """成片时间 → 原片时间。"""
        for (ca, _cb), off, ln in zip(self.cuts, self.offsets, self.lengths):
            if off <= t < off + ln + 1e-9:
                return ca + (t - off)
        return self.cuts[-1][0] + self.lengths[-1] if self.cuts else t

    def source_ranges(self, a: float, b: float) -> List[Range]:
        """成片区间 [a,b] 反查成原片区间（分段渲染时用）。"""
        out: List[Range] = []
        for (ca, _cb), off, ln in zip(self.cuts, self.offsets, self.lengths):
            lo, hi = max(a, off), min(b, off + ln)
            if hi > lo:
                out.append((ca + (lo - off), ca + (hi - off)))
        return out

    def clip(self, a: float, b: float) -> List[Range]:
        """原片区间 [a,b] 与各保留区间相交的部分，换算成成片时间。"""
        out: List[Range] = []
        for (ca, _cb), off, ln in zip(self.cuts, self.offsets, self.lengths):
            lo, hi = max(a, ca), min(b, ca + ln)
            if hi > lo:
                out.append((off + lo - ca, off + hi - ca))
        return out
