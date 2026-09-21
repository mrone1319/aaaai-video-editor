"""自动剪静音：silencedetect → 保留区间（带留白，合并过短间隔，丢弃过短片段）。"""
from __future__ import annotations

import re
from typing import List, Tuple

from . import env


def detect_silences(src: str, noise_db: float = -35, min_dur: float = 0.5) -> List[Tuple[float, float]]:
    p = env.run([env.ffmpeg(), "-v", "info", "-i", src, "-vn", "-af",
                 "silencedetect=noise=%ddB:d=%s" % (noise_db, min_dur), "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    out = []
    for i, s in enumerate(starts):
        out.append((s, ends[i] if i < len(ends) else float("inf")))
    return out


def keep_ranges(duration: float, silences, pad: float = 0.12, min_keep: float = 0.4,
                merge_gap: float = 0.25) -> List[Tuple[float, float]]:
    keeps, cur = [], 0.0
    for s, e in silences:
        if s - cur > 0:
            keeps.append((cur, s))
        cur = min(e, duration)
    if cur < duration:
        keeps.append((cur, duration))
    keeps = [(max(0.0, a - pad), min(duration, b + pad)) for a, b in keeps]
    merged: List[Tuple[float, float]] = []
    for a, b in keeps:
        if merged and a - merged[-1][1] <= merge_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return [(round(a, 3), round(b, 3)) for a, b in merged if b - a >= min_keep]


def refine(cuts, e) -> List[Tuple[float, float]]:
    """按能量包络修剪点（旧项目记忆 cut-on-decay-not-vad，ep07／ep08 实测）：
    · 段尾：延到尾音真正衰减回底噪 + 0.06s（照静音检测切会咬掉每段最后一个字）
    · 段头：起音前 0.09s，且那一刻要是安静的（贴太近会咬掉字头）
    """
    out: List[Tuple[float, float]] = []
    for a, b in cuts:
        e_end = min(e.dur, e.decay_end(max(a, b - 0.05), limit=0.8) + 0.06)
        o = e.onset_after(max(0.0, a - 0.25), limit=0.6)
        s = a if o is None else max(0.0, o - 0.09)
        k = 0
        while k < 20 and s > 0 and e.at(s) > e.decay_thr:      # 起点落在声音里：往前找静音
            s -= 0.01
            k += 1
        if out and s < out[-1][1]:
            s = out[-1][1]
        if e_end - s >= 0.2:
            out.append((round(s, 3), round(max(e_end, s + 0.2), 3)))
    merged: List[Tuple[float, float]] = []
    for a, b in out:
        if merged and a - merged[-1][1] <= 0.05:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged
