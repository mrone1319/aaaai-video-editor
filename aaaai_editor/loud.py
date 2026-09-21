"""响度锁定：成品 -14 LUFS（±0.1）、真峰值 ≤ -1 dBTP。

做法来自 MR ONE 频道实测（旧项目记忆 loudness-lock，ep04–ep09 各集曾飘 1.5dB）：
  1. 人声静态增益到 -16 LUFS（人声／配乐比例的基准）
  2. 配乐**也先正规化到 -16 LUFS** 再压 musicDb——否则 musicDb 只是相对曲子本身，曲子原始响度差 4dB 以上
  3. 混出无损中间档（24-bit）
  4. 增益 → 192k 过采样 → 限幅（-1.5dBFS）→ 回 48k，量整体响度，**割线法**修正增益，2–4 次收敛到 ±0.1
  5. AAC 编码后再量真峰值；> -1 dBTP 就把限幅收到 -2.5 整个重做
试过不行（别走回头路）：只用 loudnorm 两段式（有真峰值上限时拉不到目标）、简单 gain+=误差（步子不够）、
限幅前加压缩器（增益失控）。
"""
from __future__ import annotations

import math
import os
import re
from typing import Optional, Tuple

from . import env

VOICE_REF = -16.0


def measure(path: str, start: Optional[float] = None, dur: Optional[float] = None) -> Tuple[float, float]:
    """(整体响度 LUFS, 真峰值 dBTP)。"""
    cmd = [env.ffmpeg(), "-nostats", "-v", "info"]
    if start is not None:
        cmd += ["-ss", "%.3f" % start]
    if dur is not None:
        cmd += ["-t", "%.3f" % dur]
    p = env.run(cmd + ["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    tail = p.stderr[p.stderr.rfind("Summary"):]
    mi = re.search(r"I:\s*(-?[\d.]+|-inf)\s*LUFS", tail)
    mp = re.search(r"True peak:\s*\n\s*Peak:\s*(-?[\d.]+|-inf)", tail)
    if not mi:
        raise env.ToolError("响度测量失败")
    f = lambda m: -70.0 if (m is None or "inf" in m.group(1)) else float(m.group(1))
    return f(mi), f(mp)


def _limit(mix: str, out: str, gain: float, limit_db: float, fade: float, total: float) -> None:
    af = ("volume=%.3fdB,aresample=192000,alimiter=limit=%.4f:attack=2:release=40:level=0,aresample=48000"
          % (gain, 10 ** (limit_db / 20.0)))
    if fade > 0:
        af += ",afade=t=out:st=%.3f:d=%.3f" % (max(0.0, total - fade), fade)
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", mix, "-af", af, "-c:a", "pcm_s24le", out])


def master(source: str, voice_graph: str, total: float, work: str, target: float = -14.0,
           music: Optional[dict] = None, fade: float = 0.0):
    ff = env.ffmpeg()
    voice = os.path.join(work, "voice.wav")
    env.run([ff, "-y", "-v", "error", "-i", source, "-filter_complex",
             voice_graph + ";[voice]aformat=sample_rates=48000:channel_layouts=stereo[v]",
             "-map", "[v]", "-t", "%.3f" % total, "-c:a", "pcm_s24le", voice])
    iv, _ = measure(voice)
    gv = max(-20.0, min(30.0, VOICE_REF - iv)) if iv > -69 else 0.0
    rep = {"voice_gain": gv, "music_gain": 0.0}
    mix = os.path.join(work, "mix.wav")
    if music:
        im, _ = measure(music["file"], 0, 120)
        gm = (VOICE_REF - im if im > -69 else 0.0) + float(music.get("db", -18))
        rep["music_gain"] = gm
        g = ("[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=%.3fdB[vo];"
             "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=%.3fdB[bgm]" % (gv, gm))
        if music.get("duck", True):   # 人声出现时压低配乐
            g += (";[vo]asplit=2[vs][vk];[bgm][vk]sidechaincompress=threshold=0.04:ratio=8:attack=20:"
                  "release=500[bd];[vs][bd]amix=inputs=2:duration=first:normalize=0[m]")
        else:
            g += ";[vo][bgm]amix=inputs=2:duration=first:normalize=0[m]"
        env.run([ff, "-y", "-v", "error", "-i", voice, "-stream_loop", "-1", "-i", music["file"],
                 "-filter_complex", g, "-map", "[m]", "-t", "%.3f" % total, "-c:a", "pcm_s24le", mix])
    else:
        env.run([ff, "-y", "-v", "error", "-i", voice, "-af", "volume=%.3fdB" % gv, "-c:a", "pcm_s24le", mix])

    out_wav = os.path.join(work, "master.wav")
    audio = os.path.join(work, "audio.m4a")
    if not music and iv <= -69:   # 没有人声也没有配乐：静音轨，不做响度迭代
        env.run([ff, "-y", "-v", "error", "-i", mix, "-c:a", "aac", "-b:a", "192k", audio])
        rep.update(I=-70.0, TP=-70.0, iters=0, limit=0.0)
        return audio, rep
    for limit_db in (-1.5, -2.5):
        i0, _ = measure(mix)
        g0 = target - i0
        _limit(mix, out_wav, g0, limit_db, fade, total)
        f0, _ = measure(out_wav)
        g1 = g0 + (target - f0)
        iters = 1
        for _ in range(6):                       # 割线法：限幅越深每 dB 效果越小，普通「加误差」步子不够
            _limit(mix, out_wav, g1, limit_db, fade, total)
            f1, _ = measure(out_wav)
            iters += 1
            if abs(f1 - target) <= 0.1:
                break
            slope = (f1 - f0) / (g1 - g0) if abs(g1 - g0) > 1e-3 else 1.0
            slope = min(1.2, max(0.15, slope))
            g0, f0, g1 = g1, f1, g1 + (target - f1) / slope
        env.run([ff, "-y", "-v", "error", "-i", out_wav, "-c:a", "aac", "-b:a", "192k", audio])
        I, TP = measure(audio)
        rep.update(I=I, TP=TP, iters=iters, limit=limit_db)
        if TP <= -1.0:
            break
    return audio, rep
