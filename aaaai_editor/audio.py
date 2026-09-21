"""音频分析：10ms 能量包络、自适应门槛、发声区间、起音点、尾音衰减终点。

包络交给 ffmpeg 的 astats 在 C 层算（纯 Python 逐样本太慢）。
门槛规则来自 MR ONE 频道的实测（旧项目记忆 cut-on-decay-not-vad / check-sync-threshold-bug）：
  · 底噪取 P10、人声取 P95，但**先排除数字静音**（< -90dB 的编码器零值）——
    长录音、多 take 之间的真静音会把 P10 拉到 -180dB，门槛整个失真（ep10）。
  · 判「有没有人声」用 max(底噪+8, 底噪与人声的中点)；贴着底噪的门槛会把呼吸当说话（ep05）。
  · 判「尾音收完」用 底噪+6，并要求连续 120ms 低于门槛（ep07：照 VAD 切会咬掉每段最后一个字）。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from typing import List, Optional, Tuple

from . import env

HOP = 0.01


class Envelope:
    def __init__(self, db: List[float], t0: float = 0.0):
        self.db, self.t0 = db, t0
        real = sorted(v for v in db if v > -90.0) or [-90.0]
        self.floor = real[int(len(real) * 0.10)]
        self.loud = real[min(len(real) - 1, int(len(real) * 0.95))]
        self.voice_thr = max(self.floor + 8, (self.floor + self.loud) / 2)
        self.decay_thr = self.floor + 6

    @property
    def dur(self) -> float:
        return len(self.db) * HOP

    def idx(self, t: float) -> int:
        return max(0, min(len(self.db) - 1, int(round((t - self.t0) / HOP))))

    def at(self, t: float) -> float:
        return self.db[self.idx(t)]

    def level(self, a: float, b: float) -> float:
        """区间平均能量（功率平均）。"""
        i0, i1 = self.idx(a), self.idx(b)
        if i1 <= i0:
            return -120.0
        s = sum(10 ** (v / 10) for v in self.db[i0:i1])
        return 10 * math.log10(s / (i1 - i0) + 1e-30)

    def voiced(self, a: float, b: float) -> bool:
        """窗口内任一 100ms 超过人声门槛就算有人声（平均值会被词头前的静音拉低，造成假警报）。"""
        t = a
        while t < b - 0.05:
            if self.level(t, t + 0.1) > self.voice_thr:
                return True
            t += 0.05
        return False

    def voiced_mask(self, bridge: float = 0.20) -> List[bool]:
        v = [x > self.voice_thr for x in self.db]
        n, gap, i = len(v), int(bridge / HOP), 0
        while i < n:          # 把短于 bridge 的静音缝补起来（字与字之间的小停顿）
            if not v[i]:
                j = i
                while j < n and not v[j]:
                    j += 1
                if 0 < i and j < n and (j - i) < gap:
                    for k in range(i, j):
                        v[k] = True
                i = j
            else:
                i += 1
        return v

    def onsets(self) -> List[float]:
        v = self.voiced_mask()
        out = [self.t0] if v and v[0] else []
        out += [self.t0 + i * HOP for i in range(1, len(v)) if v[i] and not v[i - 1]]
        return out

    def first_last_voice(self) -> Tuple[float, float]:
        v = self.voiced_mask()
        f = next((i for i in range(len(v)) if v[i]), 0)
        l = next((i for i in range(len(v) - 1, -1, -1) if v[i]), len(v) - 1)
        return self.t0 + f * HOP, self.t0 + l * HOP

    def decay_end(self, t: float, limit: float = 0.8, hold: float = 0.12) -> float:
        """从 t 往后找尾音真正收完的位置：连续 hold 秒低于衰减门槛的起点。"""
        i, end, need = self.idx(t), self.idx(t + limit), int(hold / HOP)
        run = 0
        while i <= end:
            run = run + 1 if self.db[i] < self.decay_thr else 0
            if run >= need:
                return self.t0 + (i - need + 1) * HOP
            i += 1
        return t

    def onset_after(self, t: float, limit: float = 0.8) -> Optional[float]:
        """t 之后第一个起音（超过衰减门槛）的时刻。"""
        i, end = self.idx(t), self.idx(t + limit)
        while i <= end:
            if self.db[i] >= self.decay_thr:
                return self.t0 + i * HOP
            i += 1
        return None


_MEM: dict = {}


def _cache_file(path: str) -> Optional[str]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    sig = hashlib.sha1(json.dumps([os.path.abspath(path), st.st_size, int(st.st_mtime), HOP]).encode()).hexdigest()[:16]
    return os.path.join(os.path.expanduser("~/.cache/aaaai-editor/envelope"), sig + ".json")


def envelope(path: str, start: Optional[float] = None, end: Optional[float] = None) -> Envelope:
    """10ms RMS 包络（dB）。整条音轨的结果按（路径、大小、修改时间）缓存：autocut／转录／对齐／体检不再各解一次。"""
    whole = start is None and end is None
    cf = _cache_file(path) if whole else None
    if cf:
        if cf in _MEM:
            return Envelope(_MEM[cf])
        try:
            db = json.load(open(cf))
            _MEM[cf] = db
            return Envelope(db)
        except (OSError, ValueError):
            pass
    cmd = [env.ffmpeg(), "-v", "info", "-nostats"]
    if start is not None:
        cmd += ["-ss", "%.3f" % start]
    if end is not None:
        cmd += ["-to", "%.3f" % end]
    cmd += ["-i", path, "-vn", "-af",
            "aresample=16000,aformat=channel_layouts=mono,asetnsamples=n=160:p=0,"
            "astats=metadata=1:reset=1,ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-",
            "-f", "null", "-"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    vals = re.findall(r"RMS_level=(-?inf|[-\d.]+)", p.stdout)
    if not vals:   # 管道没产出数据就直说，别把「空」当成「全是静音」
        raise env.ToolError("能量包络没有产出数据：%s" % (p.stderr or "")[-300:])
    db = [-120.0 if "inf" in v else max(-120.0, float(v)) for v in vals]
    if cf:
        try:
            os.makedirs(os.path.dirname(cf), exist_ok=True)
            json.dump(db, open(cf, "w"))
            _MEM[cf] = db
        except OSError:
            pass
    return Envelope(db, start or 0.0)


def junctions(e: Envelope, cuts) -> List[dict]:
    """剪点审计：每段尾的最后 50ms、段头的前 30ms 应该回到底噪附近。
    段尾还响＝切在尾音上（下一段接上时最后一个字被截）；段头已响＝咬掉字头。"""
    out = []
    peak = lambda a_, b_: max(e.db[e.idx(a_):e.idx(b_) + 1] or [-120.0])
    for i, (a, b) in enumerate(cuts):
        # 用峰值不用平均：尾音正在衰减时平均值被拉低会漏判（实测切掉半个字时平均 -39.8、峰值 -23.2）
        tail = peak(b - 0.05, b - 0.01)
        head = peak(a, a + 0.03)
        # 切点之后原片紧接着还有人声：可能把字切在两个音节之间的小低谷（前面安静、字其实没讲完），
        # 也可能是故意砍掉后面的话——所以只作提示，由人判断
        after = peak(b, b + 0.08) if b < e.dur - 0.05 else -120.0
        out.append({"i": i, "a": a, "b": b, "head": head, "tail": tail, "after": after,
                    "tail_bad": tail > e.decay_thr + 6, "head_bad": i > 0 and head > e.decay_thr + 6,
                    "cont": after > e.voice_thr})
    return out
