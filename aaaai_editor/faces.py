"""字幕避脸：每 0.5 秒取一帧，用人像分割（Apple Vision）估出「头顶～下巴」的高度范围。

字幕默认在画面约 70% 处；人坐得低、脸落在那附近时，那几句字幕改放到下巴下面，不压脸。
没有人像分割（没装 Xcode 工具）就跳过，字幕照常。
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import subprocess
from typing import List, Optional, Tuple

from . import env

STEP = 0.5


def _band(mask: bytes, w: int, h: int) -> Optional[Tuple[float, float]]:
    """一帧遮罩 → (头顶, 下巴) 占画面高的比例；画面里没有人就 None。"""
    widths = []
    for y in range(h):
        row = mask[y * w:(y + 1) * w]
        widths.append(sum(1 for v in row if v > 128))
    thr = max(2, int(w * 0.03))
    rows = [y for y, c in enumerate(widths) if c > thr]
    if len(rows) < h * 0.08:
        return None
    top = rows[0]
    head = [widths[y] for y in range(top, min(h, top + max(2, int(h * 0.06))))]
    hw = statistics.median(head) if head else 0
    chin = None
    for y in range(top + int(h * 0.04), min(h, top + int(h * 0.32))):
        if hw and widths[y] > hw * 1.7:   # 肩膀开始变宽：下巴大约在这里
            chin = y
            break
    if chin is None:
        chin = min(h - 1, top + int(h * 0.22))
    return top / float(h), chin / float(h)


def track(sb: dict, tl, W: int, H: int) -> List[Tuple[float, Optional[Tuple[float, float]]]]:
    """成片时间轴上每 0.5 秒一个 (时间, 脸的范围)。有缓存。"""
    from . import matte
    src = sb["source"]
    st = os.stat(src)
    fr = sb.get("framing") or {}
    sw = 144
    sh = int(round(sw * H / float(W))) & ~1
    key = hashlib.sha1(json.dumps([os.path.abspath(src), st.st_size, st.st_mtime_ns, tl.cuts, fr, W, H, STEP, 1])
                       .encode()).hexdigest()[:16]
    cache = os.path.join(sb["_base"], "work", "faces_%s.json" % key)
    if os.path.isfile(cache):
        return [(t, tuple(b) if b else None) for t, b in json.load(open(cache))]
    helper = matte.helper()
    z = float(fr.get("zoom", 1.0))
    if z > 1.0001:
        cx, cy = float(fr.get("cx", 0.5)), float(fr.get("cy", 0.4))
        vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d:(iw-%d)*%.4f:(ih-%d)*%.4f"
              % (int(sw * z) & ~1, int(sh * z) & ~1, sw, sh, sw, cx, sh, cy))
    else:
        vf = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (sw, sh, sw, sh)
    out: List[Tuple[float, Optional[Tuple[float, float]]]] = []
    for (ca, _cb), off, ln in zip(tl.cuts, tl.offsets, tl.lengths):
        n = max(1, int(ln / STEP))
        raw = subprocess.run([env.ffmpeg(), "-v", "error", "-ss", "%.3f" % (ca + STEP / 2), "-t", "%.3f" % ln, "-i", src,
                              "-vf", "fps=%.3f,%s" % (1.0 / STEP, vf), "-frames:v", str(n), "-f", "rawvideo",
                              "-pix_fmt", "bgra", "-"], capture_output=True).stdout
        k = len(raw) // (sw * sh * 4)
        if not k:
            continue
        masks = subprocess.run([helper, str(sw), str(sh), "balanced"], input=raw[:k * sw * sh * 4],
                               capture_output=True).stdout
        for i in range(min(k, len(masks) // (sw * sh))):
            out.append((round(off + STEP / 2 + i * STEP, 3), _band(masks[i * sw * sh:(i + 1) * sw * sh], sw, sh)))
    json.dump(out, open(cache, "w"))
    return out


def margins(events, faces, H: int, st: dict, bottom_frac: float) -> List[Optional[int]]:
    """每句字幕的 MarginV（像素）；不用改的给 None。bottom_frac：字幕底边离画面底部的比例。"""
    size = H * st["size"]
    res: List[Optional[int]] = []
    for a, b, _txt, ex in events:
        if ex and ex.get("lift"):
            res.append(None)
            continue
        hits = [f for t, f in faces if a - STEP / 2 <= t <= b + STEP / 2 and f]
        if not hits:
            res.append(None)
            continue
        top = min(f[0] for f in hits) * H
        chin = max(f[1] for f in hits) * H
        two = bool(ex and ex.get("en"))
        cap_h = size * (1.30 + (st.get("en_ratio", 0.62) * 1.30 if two else 0.0))
        cap_b = H * (1.0 - bottom_frac)
        cap_t = cap_b - cap_h
        if cap_b < top or cap_t > chin:     # 没压到脸
            res.append(None)
            continue
        new_b = min(H * 0.95, chin + cap_h + H * 0.05)   # 下巴估计偏高一点：多留一段脖子的距离
        if new_b - cap_h < chin - H * 0.01:  # 下巴下面放不下：保持原位
            res.append(None)
            continue
        res.append(int(round(H - new_b)))
    return res
