"""转场：甩镜（whip）。只动剪辑点前后那 0.3 秒左右的帧，片长不变、其他帧原样通过。

storyboard：
  "transitions": [{"t": 12.3, "type": "whip"}]      // t 写成片秒数，会吸附到最近的剪辑点（±0.6 秒内）
  可选：dur（秒，默认 0.32）、dir（"left"／"right"，画面往哪边甩出去）、sfx（默认 "whoosh"，写 "" 关掉）

做法：按帧号把时间轴切成「前／转场／后」三段再接回去（接缝逐帧对齐）；转场那段里，
画面先放大、往一边加速甩出去，过了剪辑点再从另一边减速甩回来，同时加方向性动态模糊。
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

DEF_DUR = 0.32


def resolve(sb: dict, tl) -> List[dict]:
    """把 transitions 的时间吸附到剪辑点，回传整理好的清单（成片时间）。"""
    out = []
    bounds = list(tl.offsets[1:])
    for tr in sb.get("transitions") or []:
        t = float(tr.get("t", tr.get("at", 0)))
        if bounds:
            near = min(bounds, key=lambda b: abs(b - t))
            if abs(near - t) <= 0.6:
                t = near
        d = max(0.12, min(0.8, float(tr.get("dur", DEF_DUR))))
        out.append(dict(tr, t=round(t, 4), dur=d, type=tr.get("type", "whip")))
    return sorted(out, key=lambda x: x["t"])


def spans(trs: List[dict]) -> List[Tuple[float, float]]:
    return [(x["t"] - x["dur"] / 2.0, x["t"] + x["dur"] / 2.0) for x in trs]


def _whip_chain(W: int, H: int, d: float, direction: str) -> str:
    """一段（从 0 秒起算、长 d 秒）的甩镜效果：放大＋横向甩动＋动态模糊。"""
    h = d / 2.0
    p = "((t-%.4f)/%.4f)" % (h, h)                      # -1 → 0（剪辑点）→ 1
    g = "(1-abs(%s))" % p                              # 两头 0、中间 1：放大程度
    # q：剪辑点前 0→1 加速甩出，剪辑点后 -1→0 减速甩回（同一个方向连续移动）
    q = "if(lt(%s\\,0)\\,pow(1+%s\\,2)\\,-pow(1-%s\\,2))" % (p, p, p)
    sgn = "1" if direction != "right" else "-1"
    zoom = "(1+0.42*%s)" % g
    blur = max(2, int(W * 0.035))
    return ("scale=w='trunc(%d*%s/2)*2':h='trunc(%d*%s/2)*2':eval=frame,"
            "crop=%d:%d:x='(iw-%d)/2*(1+%s*%s)':y='(ih-%d)/2',"
            "dblur=angle=%d:radius=%d:enable='lt(abs(%s)\\,0.55)',tmix=frames=3"
            % (W, zoom, H, zoom, W, H, W, sgn, q, H, 0 if direction != "right" else 180, blur, p))


def graph(src: str, dst: str, trs: List[dict], W: int, H: int, fps: float, t_off: float = 0.0,
          seg_len: Optional[float] = None) -> Optional[str]:
    """回传滤镜图片段（src → dst）；这一段里没有转场就回传 None。t_off：分段渲染时这一段的起点。"""
    f = float(fps)
    wins = []
    for tr in trs:
        a, b = tr["t"] - tr["dur"] / 2.0 - t_off, tr["t"] + tr["dur"] / 2.0 - t_off
        if b <= 0 or (seg_len is not None and a >= seg_len):
            continue
        fa, fb = max(0, int(math.floor(a * f + 0.5))), int(math.floor(b * f + 0.5))
        if seg_len is not None:
            fb = min(fb, int(round(seg_len * f)))
        if fb - fa >= 2:
            wins.append((fa, fb, tr))
    if not wins:
        return None
    segs, cur = [], 0
    for fa, fb, tr in wins:
        if fa < cur:
            fa = cur
        if fa > cur:
            segs.append((cur, fa, None))
        segs.append((fa, fb, tr))
        cur = fb
    segs.append((cur, None, None))
    n = len(segs)
    parts = ["%ssplit=%d%s" % (src, n, "".join("[tw%d]" % i for i in range(n)))]
    for i, (a, b, tr) in enumerate(segs):
        ch = "trim=start_frame=%d%s,setpts=PTS-STARTPTS" % (a, (":end_frame=%d" % b) if b is not None else "")
        if tr is not None:
            ch += "," + _whip_chain(W, H, (b - a) / f, tr.get("dir", "left")) + ",setpts=PTS-STARTPTS"
        parts.append("[tw%d]%s[to%d]" % (i, ch, i))
    parts.append("%sconcat=n=%d:v=1:a=0%s" % ("".join("[to%d]" % i for i in range(n)), n, dst))
    return ";".join(parts)
