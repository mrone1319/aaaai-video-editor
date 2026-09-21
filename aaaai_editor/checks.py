"""字幕对时体检：把成片音轨重新转录一次，和烧上去的字幕逐句比时间。

渲染前跑这一步，能在出片之前抓到剪辑点映射错、时间轴漂移这类问题——
这些问题光看 storyboard 是看不出来的。
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import statistics
from typing import List, Optional, Tuple

from . import audio, captions, env, render, transcribe
from .timeline import Timeline


def _norm(s: str) -> str:
    return re.sub(r"[^\w一-鿿]+", "", s or "")


def sync(sb_path: str, tolerance: float = 0.4, keep: bool = True) -> int:
    sb = render.load_storyboard(sb_path)
    cap = sb["captions"]
    if not cap.get("enabled"):
        print("这个 storyboard 关掉了字幕，没什么好对的。")
        return 0
    work = os.path.join(sb["_base"], "work")
    tr_path = os.path.join(sb["_base"], cap.get("transcript", "work/transcript.json"))
    if not os.path.isfile(tr_path):
        raise env.ToolError("缺少转录文件 %s（先跑 aaaai-editor transcribe）" % tr_path)
    doc = json.load(open(tr_path, encoding="utf-8"))
    tl = Timeline([tuple(c) for c in sb["cuts"]], sb["output"]["fps"])
    pcs, _track = captions.load_pieces(sb, doc["segments"], captions.fit(sb))
    events = captions.to_events(pcs, tl)
    if not events:
        print("没有字幕事件。")
        return 0

    # ── 第一关：逐句能量检查（旧项目 check-sync v2 的三项检查＋剪点审计，每句都查得到）──
    print("① 逐句能量检查（原片人声，不受配乐影响）…")
    e = audio.envelope(sb["source"])
    probs, notes = [], []
    for a_, b_, txt, _ex in events:
        ts = tl.to_source(a_)
        if not e.voiced(ts, ts + 0.6):
            probs.append("  %6.2fs 出字时没有人声（%.1fdB）「%s」" % (a_, e.level(ts, ts + 0.6), txt[:18]))
            continue
        o = e.onset_after(ts, limit=1.2)
        if o is not None and o - ts > 0.35 and not e.voiced(ts, ts + 0.1):
            probs.append("  %6.2fs 字幕比开口早 %.2fs「%s」" % (a_, o - ts, txt[:18]))
    for j in audio.junctions(e, tl.cuts):
        if j["tail_bad"]:
            probs.append("  剪点 %.2fs 切在尾音上（最后 50ms 还有 %.1fdB）——这段最后一个字会被截" % (j["b"], j["tail"]))
        if j["head_bad"]:
            probs.append("  剪点 %.2fs 咬到字头（前 30ms 已有 %.1fdB）" % (j["a"], j["head"]))
        if j["cont"] and not j["tail_bad"]:
            notes.append("  剪点 %.2fs 之后原片紧接着还有人声（%.1fdB）——字可能没讲完；若是故意砍掉后面的话可忽略"
                         % (j["b"], j["after"]))
    print("   底噪 %.1fdB・人声 %.1fdB・门槛 %.1fdB｜字幕 %d 句｜剪点 %d 个"
          % (e.floor, e.loud, e.voice_thr, len(events), len(tl.cuts)))
    if probs:
        print("⚠️ 能量检查 %d 个问题：" % len(probs))
        for x in probs[:20]:
            print(x)
    else:
        print("   ✅ 每句出字时都有人声、没有早出，剪点都切在静音里")
    if notes:
        print("ℹ️ 提示 %d 个（不算失败，请听一下）：" % len(notes))
        for x in notes[:10]:
            print(x)

    print("② 生成成片音轨…")
    audio_f = render.render(sb_path, only="audio")
    print("③ 把成片音轨重新转录（这一步最慢）…")
    sd = os.path.join(work, "sync")
    os.makedirs(sd, exist_ok=True)
    ft = os.path.join(sd, "final_transcript.json")
    sha = hashlib.sha1(open(audio_f, "rb").read()).hexdigest()
    re_doc = None
    if os.path.isfile(ft):  # 成片音轨没变就不重转录：改完 transcript 再体检只要几秒
        cached = json.load(open(ft, encoding="utf-8"))
        if cached.get("audio_sha") == sha:
            re_doc = cached
            print("   （成片音轨没变，沿用上次的转录）")
    if re_doc is None:
        # 不带提示词：提示词会让 whisper 在静音上幻听出词，判定性检查一律不带（ep10 教训）
        re_doc = transcribe.transcribe(audio_f, ft, doc.get("language") or "auto", prompt="")
        re_doc["audio_sha"] = sha
        json.dump(re_doc, open(ft, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("④ 逐句比对…")
    # 按时间顺序单调对齐：同一句话在片中出现多次时，不会全配到第一次出现的位置
    rows: List[Tuple[float, float, float, str]] = []
    unmatched = 0
    win = max(3.0, tolerance * 6)
    j = 0
    # 只用 whisper 的段首时间做参照：那是模型给的真实时间。
    # （按字数比例把段再切小会引入几秒误差、造成误报；whisper.cpp 对中文也切不出更细的可靠时间点）
    for s in sorted(re_doc["segments"], key=lambda x: x["start"]):
        key = _norm(s["text"])[:8]
        if len(key) < 3:
            continue
        while j < len(events) and events[j][0] < s["start"] - win:
            j += 1
        best: Optional[Tuple[float, int]] = None
        k = j
        while k < len(events) and events[k][0] <= s["start"] + win:
            r = difflib.SequenceMatcher(None, key, _norm(events[k][2])[:len(key) + 4]).ratio()
            if best is None or r > best[0] + 1e-9:
                best = (r, k)
            k += 1
        if best is None or best[0] < 0.55:
            unmatched += 1
            continue
        a, _b, txt = events[best[1]][:3]
        rows.append((s["start"], a, a - s["start"], txt))
        j = best[1] + 1

    if not rows:
        print("❌ 一句都对不上——字幕内容和成片音轨可能根本不是一回事。")
        return 1
    deltas = [abs(r[2]) for r in rows]
    med = statistics.median(deltas)
    worst = sorted(rows, key=lambda r: -abs(r[2]))[:5]
    bad = [r for r in rows if abs(r[2]) > tolerance]

    print("\n" + "=" * 58)
    print("匹配 %d 句（%d 句没对上），字幕事件共 %d 条" % (len(rows), unmatched, len(events)))
    print("偏移中位数 %.2fs，最大 %.2fs，超过 %.1fs 的有 %d 句"
          % (med, max(deltas), tolerance, len(bad)))
    print("\n偏移最大的几句：")
    for st, ev, d, txt in worst:
        print("  成片 %6.2fs  字幕 %6.2fs  差 %+.2fs  %s" % (st, ev, d, txt[:18]))
    # 漂移体检：偏移是否随时间越来越大
    if len(rows) >= 6:
        half = len(rows) // 2
        a = statistics.median([r[2] for r in rows[:half]])
        b = statistics.median([r[2] for r in rows[half:]])
        print("\n前半段中位偏移 %+.2fs，后半段 %+.2fs → %s"
              % (a, b, "有累积漂移，检查剪辑点映射" if abs(b - a) > 0.25 else "没有累积漂移"))
    print("=" * 58)
    total = len(rows) + unmatched
    cover = len(rows) / float(max(1, total))
    print("对上 %d/%d 个参照点（%.0f%%）" % (len(rows), total, cover * 100))
    if len(rows) < 3 or cover < 0.6:
        print("=" * 58)
        if probs:
            print("⚠️ 能量检查有 %d 个问题（见上）；重转录只对上 %d 个参照点，无法补充判断。" % (len(probs), len(rows)))
            return 1
        # 能量检查逐句都过了；重转录样本太少不下结论，但不影响前者
        print("✅ 逐句能量检查通过。重转录只对上 %d 个参照点（whisper 把话并成了很少几段），这一关不作判断。"
              % len(rows))
        return 0
    ok = med <= tolerance and len(bad) <= max(1, len(rows) // 20) and not probs
    print("✅ 字幕对时没问题（能量检查＋重转录都通过）。" if ok else
          ("⚠️ 能量检查有问题，见上。" if probs else "⚠️ 字幕对时偏差偏大，建议检查字幕轨或剪辑点。"))
    if not keep:
        for f in ("final_transcript.json", "audio16k.wav", "whisper.json"):
            try:
                os.remove(os.path.join(sd, f))
            except OSError:
                pass
    return 0 if ok else 1
