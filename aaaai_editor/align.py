"""字幕逐句对齐：把字幕轨每句的起止时间贴到真实人声上。

方法移植自 MR ONE 频道 ep03–ep06 验证过的做法（旧项目 align-subs）：
  1. whisper 逐词（token）时间戳 → 「字 → 时间」流（不带提示词：提示词会在静音上幻听）
  2. 整篇字幕与字流做**全局序列对齐**（字幕改过错字、改过写法也对得上；逐句找会大量失败）
  3. 每句起点吸附到 ±0.35s 内最近的真实起音，再提前 0.05s
  4. 对不上的句子用前后插值；句尾不拖进长停顿（贴尾音收完处 +0.2s）
试过不行、别走回头路：直接用段落时间（段内插值飘 1–2s）、逐字等宽重分配（语速不均，差 ±2.6s）。
"""
from __future__ import annotations

import difflib
import json
import os
import subprocess
from typing import List, Optional, Tuple

from . import audio, env, zh


def _clean(s: str) -> str:
    return "".join(c for c in s.replace("**", "").lower() if c.isalnum())   # 英文大小写不影响对齐


def token_stream(src: str, work: str, lang: str) -> List[Tuple[str, float, float]]:
    wav = os.path.join(work, "align16k.wav")
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", wav])
    base = os.path.join(work, "align_tokens")
    env.run([env.whisper_cli(), "-m", env.whisper_model(lang), "-f", wav, "-l", lang, "-ojf", "-of", base, "-np"])
    data = json.load(open(base + ".json", encoding="utf-8"))
    toks = []
    for seg in data.get("transcription", []):
        for t in seg.get("tokens") or []:
            txt = zh.t2s((t.get("text") or "").strip())
            if not txt or txt.startswith("[") or txt.startswith("<"):
                continue
            off = t.get("offsets") or {}
            if "from" not in off:
                continue
            toks.append((txt, off["from"] / 1000.0, off.get("to", off["from"]) / 1000.0))
    return toks


def align(sb: dict, pieces: List[dict], lang: str = "zh") -> Tuple[List[dict], dict]:
    work = os.path.join(sb["_base"], "work")
    env_ = audio.envelope(sb["source"])
    onsets = env_.onsets()
    first_v, last_v = env_.first_last_voice()
    from . import captions as captions_mod
    hold = float(captions_mod.STYLES.get(captions_mod.resolve_style(sb), {}).get("hold", 0.2))
    toks = token_stream(sb["source"], work, lang)
    if len(toks) < 5:
        raise env.ToolError("whisper 只给出 %d 个词的时间戳，无法对齐" % len(toks))

    ref, rtime, rend = "", [], []
    for txt, a, b in toks:
        cs = _clean(txt)
        for k, ch in enumerate(cs):
            ref += ch
            rtime.append(a + (b - a) * k / max(1, len(cs)))
            rend.append(a + (b - a) * (k + 1) / max(1, len(cs)))
    mine, starts, ends = "", [], []
    for pc in pieces:
        starts.append(len(mine))
        mine += _clean(pc["text"])
        ends.append(len(mine))
    sm = difflib.SequenceMatcher(None, mine, ref, autojunk=False)
    pair = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            pair[blk.a + k] = blk.b + k

    def snap(t: float, tol: float = 0.35) -> float:
        c = [o for o in onsets if abs(o - t) <= tol]
        return round((min(c, key=lambda o: abs(o - t)) if c else t) - 0.05, 3)

    new_s: List[Optional[float]] = []
    last_char: List[Optional[float]] = []
    prev, missed = -1.0, 0
    for i in range(len(pieces)):
        si, ei = starts[i], ends[i]
        k = next((x for x in range(si, min(si + 12, ei)) if x in pair), None)
        kl = next((x for x in range(ei - 1, max(si - 1, ei - 12), -1) if x in pair), None)
        if k is None:
            new_s.append(None)
            last_char.append(None)
            missed += 1
            continue
        t = snap(rtime[pair[k]])
        if t <= prev + 0.25:
            t = round(prev + 0.35, 3)
        new_s.append(t)
        last_char.append(rend[pair[kl]] if kl is not None else None)
        prev = t
    known = [(i, t) for i, t in enumerate(new_s) if t is not None]
    if not known:
        raise env.ToolError("完全对不上——字幕文字跟语音差太多，检查字幕轨是否属于这支素材")
    for i, t in enumerate(new_s):   # 对不上的：前后插值
        if t is not None:
            continue
        pv = max((x for x in known if x[0] < i), key=lambda x: x[0], default=None)
        nx = min((x for x in known if x[0] > i), key=lambda x: x[0], default=None)
        if pv and nx:
            new_s[i] = round(pv[1] + (i - pv[0]) / (nx[0] - pv[0]) * (nx[1] - pv[1]), 3)
        elif pv:
            new_s[i] = round(pv[1] + 0.9, 3)
        else:
            new_s[i] = round(max(first_v, nx[1] - 0.9), 3)
    for i in range(1, len(new_s)):
        if new_s[i] <= new_s[i - 1] + 0.25:
            new_s[i] = round(new_s[i - 1] + 0.35, 3)
    new_s = [max(0.0, t) for t in new_s]

    out, moved = [], []
    for i, pc in enumerate(pieces):
        s = new_s[i]
        nxt = new_s[i + 1] if i + 1 < len(new_s) else last_v + 0.3
        e = nxt - 0.03
        lc = last_char[i]
        if lc is not None:  # 句尾：贴尾音收完再多留一会儿（风格的 hold，默认 0.2s），不拖进长停顿
            e = min(e, env_.decay_end(lc, limit=1.0) + hold)
        e = max(e, s + 0.45)
        if hold > 0.2:      # 口播风格：至少留够读完的时间（按字数），但不越过下一句的开头
            e = max(e, min(nxt - 0.03, s + 0.35 + 0.09 * captions_mod.width(pc["text"].replace("**", ""))))
        old = float(pc["s"][0])
        moved.append(s - old)
        q = dict(pc)
        q["s"] = [round(s, 3), round(e, 3)]
        out.append(q)
    stats = {"pieces": len(pieces), "missed": missed,
             "matched_chars": len(pair), "chars": len(mine),
             "max_move": max((abs(m) for m in moved), default=0.0),
             "moved_over_0.3": sum(1 for m in moved if abs(m) > 0.3),
             "first_voice": first_v, "last_voice": last_v, "thr": env_.voice_thr}
    return out, stats
