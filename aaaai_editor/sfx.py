"""音效：程序自己合成（正弦波＋噪声＋包络），没有版权问题。按名称缓存成 wav，只合成一次。

用法（storyboard）：
  "sfx": [{"t": 5.2, "sound": "coin"}, {"t": 9.0, "sound": "pop", "db": -4}]   // t 是成片秒数
  卡片上写 "sfx": "pop" ＝ 卡片出现时响；"sfx_at": 秒数 可改时间（例如印章盖下那一刻）。
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from . import env

CACHE = os.path.expanduser("~/.cache/aaaai-editor/sfx")
VER = 4

# 名称 → (时长秒, 说明, 表达式)。t＝秒，N＝噪声样本（-1～1，含 N 的音效用噪声源）；幅度压在 0.5 以内，混音时再按 db 调整
SOUNDS: Dict[str, Tuple[float, str, str]] = {
    "coin": (0.55, "金币「叮叮」：数字揭晓、金额出现",
             "0.42*(lt(t,0.085)*sin(2*PI*1318*t)*exp(-t*18)"
             "+gte(t,0.075)*(sin(2*PI*1976*t)+0.35*sin(2*PI*3952*t))*exp(-(t-0.075)*7))"),
    "pop": (0.16, "啵：卡片弹出、印章、清单一条条出现",
            "0.5*sin(2*PI*(900-3800*t)*t)*exp(-t*38)"),
    "ding": (1.3, "叮：重点、结论、提示",
             "0.34*(sin(2*PI*1568*t)+0.5*sin(2*PI*2352*t)+0.25*sin(2*PI*3136*t))*exp(-t*3.2)"),
    "whoosh": (0.55, "咻：转场、卡片接管进场",
               "3.2*N*sin(PI*t/0.55)^2"),
    "click": (0.06, "喀：按钮、勾选",
              "0.45*N*exp(-t*140)+0.3*sin(2*PI*2400*t)*exp(-t*90)"),
    "thud": (0.28, "咚：掉落字落地、重物落下",
             "0.62*sin(2*PI*(120-180*t)*t)*exp(-t*16)+0.12*sin(2*PI*240*t)*exp(-t*40)"),
    "tick": (0.05, "滴答：倒数每一秒",
             "0.40*sin(2*PI*2000*t)*exp(-t*120)"),
    "confetti": (0.9, "拉炮：庆祝、达成里程碑",
                 "0.6*N*exp(-t*28)+0.35*N*gt(sin(2*PI*37*t)*sin(2*PI*53*t),0.82)*exp(-t*3.5)"),
}


def path(name: str) -> str:
    if name not in SOUNDS:
        raise env.ToolError("没有这个音效：%s（可用：%s）" % (name, " ".join(SOUNDS)))
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, "%s_v%d.wav" % (name, VER))
    if not os.path.isfile(out):
        dur, _desc, expr = SOUNDS[name]
        if "N" in expr:   # 噪声类：噪声源逐样本乘包络
            src = "anoisesrc=c=%s:r=48000:a=0.5:d=%.3f:s=11,aeval='%s'" % (
                "pink" if name == "whoosh" else "white", dur, expr.replace("N", "val(0)"))
        else:
            src = "aevalsrc='%s':s=48000:d=%.3f" % (expr, dur)
        af = "bandpass=f=1100:width_type=h:w=1600,highpass=f=250" if name == "whoosh" else "anull"
        env.run([env.ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", src,
                 "-af", af + ",aformat=channel_layouts=stereo", "-c:a", "pcm_s16le", out])
    return out


def collect(sb: dict) -> List[Tuple[float, str, float]]:
    """storyboard 的 sfx 清单＋卡片上的 sfx → [(成片秒数, wav 路径, dB)]，按时间排序。"""
    out: List[Tuple[float, str, float]] = []
    for x in sb.get("sfx") or []:
        out.append((float(x["t"]), path(x.get("sound", "pop")), float(x.get("db", 0.0))))
    for tr in sb.get("_transitions") or sb.get("transitions") or []:   # 甩镜转场默认配「咻」（用吸附后的时间）
        s = tr.get("sfx", "whoosh")
        if s:
            out.append((max(0.0, float(tr.get("t", 0)) - float(tr.get("dur", 0.32)) / 2.0 - 0.05), path(s),
                        float(tr.get("sfx_db", 0.0))))
    for x in sb.get("_postfx") or []:   # 整屏特效：进出各一声「咻」（底片感不加）
        if x.get("type") == "film" or x.get("sfx") == "":
            continue
        a_, b_ = float(x["t"][0]), float(x["t"][1])
        out.append((max(0.0, a_ - 0.03), path(x.get("sfx") or "whoosh"), -4.0))
        if x.get("type") in ("phone", "swipe"):
            out.append((max(0.0, b_ - 0.40), path(x.get("sfx") or "whoosh"), -6.0))
    for ov in sb.get("overlays") or []:
        if ov.get("type") == "sticker":   # 贴纸：弹出「啵」、打勾「喀」、计数「滴答」……时间相对卡片开始
            from . import sticker
            for dt, name, db in sticker.sfx_events(ov):
                out.append((float(ov["t"][0]) + dt, path(name), db))
            continue
        s = ov.get("sfx")
        if not s:
            continue
        at = ov.get("sfx_at")
        at = float(at) if at is not None else float(ov["t"][0])
        out.append((at, path(s), float(ov.get("sfx_db", 0.0))))
    return sorted(out)


def describe() -> str:
    return "\n".join("%-9s %s" % (k, v[1]) for k, v in SOUNDS.items())


def mix_graph(n_inputs_before: int, items: List[Tuple[float, str, float]], base_gain_db: float,
              src: str = "[m0]", dst: str = "[m]") -> Tuple[List[str], str]:
    """回传 (ffmpeg 输入参数, 滤镜段)：把每个音效延迟到它的时间点，和 src 混在一起。
    base_gain_db：音效相对人声的整体音量（人声已拉到参考响度）。"""
    args: List[str] = []
    parts: List[str] = []
    labs: List[str] = []
    for k, (t, f, db) in enumerate(items):
        args += ["-i", f]
        ms = max(0, int(round(t * 1000)))
        parts.append("[%d:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=%.2fdB,adelay=%d|%d[sx%d]"
                     % (n_inputs_before + k, base_gain_db + db, ms, ms, k))
        labs.append("[sx%d]" % k)
    parts.append("%s%samix=inputs=%d:duration=first:normalize=0%s" % (src, "".join(labs), len(labs) + 1, dst))
    return args, ";".join(parts)


def gain_for(level: Optional[str]) -> float:
    """整体音效音量：quiet／normal／loud。"""
    return {"quiet": -10.0, "loud": 0.0}.get(level or "normal", -3.0)
