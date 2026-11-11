"""关键词触发：讲到哪个词，卡片／整屏特效就在那个时间出现，不用手动对时间。

storyboard：
  "triggers": [
    {"say": "AI网红", "card": {"type": "sticker", "kind": "slam", "text": "AI网红"}, "dur": 1.4},
    {"say": ["手机框", "手机"], "fx": {"type": "phone"}, "dur": 3.0},
    {"say": "调色", "card": {"type": "sticker", "kind": "tag", "text": "调色"}, "toc": "调色前后对比"}
  ]
  say：要听的词（可给几个写法；不分大小写、忽略空格标点）。
  card：出现的卡片（任何 overlay，不用写 t）；fx：整屏特效（postfx，不用写 t）；两个都写也可以。
  dur（默认 1.5 秒）、lead（提前几秒出现，默认 0.1）、every（true＝每次讲到都触发；默认只触发第一次）、
  after（成片秒数：只找这个时间之后讲到的，用来区分同一个词讲了好几次）、toc（同时在章节目录加一项）。

找词的时间：优先用对齐时的逐字时间（work/align_tokens_cache.json，跑过 align 就有），
没有就用字幕轨每句的起止按字数插值（误差约一两个字）。原片时间再换成成片时间（剪掉的段落讲到的词不触发）。
"""
from __future__ import annotations

import json
import os
from typing import List, Optional, Tuple

DEF_DUR, DEF_LEAD = 1.5, 0.1


def _clean(s: str) -> str:
    return "".join(c for c in str(s).replace("**", "").replace("==", "").lower() if c.isalnum())


def char_stream(sb: dict) -> List[Tuple[str, float]]:
    """[(字, 原片秒数)]：逐字时间优先，退回字幕轨插值。"""
    work = os.path.join(sb["_base"], "work")
    cache = os.path.join(work, "align_tokens_cache.json")
    try:
        d = json.load(open(cache, encoding="utf-8"))
        st = os.stat(sb["source"])
        k = d.get("key") or []
        if k[:3] == [os.path.abspath(sb["source"]), st.st_size, st.st_mtime_ns]:
            out = []
            for txt, a, b in d["tokens"]:
                cs = _clean(txt)
                for i, c in enumerate(cs):
                    out.append((c, a + (b - a) * i / max(1, len(cs))))
            if out:
                return out
    except (OSError, ValueError, KeyError, TypeError):
        pass
    from . import captions
    tr = os.path.join(sb["_base"], (sb.get("captions") or {}).get("transcript", "work/transcript.json"))
    segs = json.load(open(tr, encoding="utf-8"))["segments"] if os.path.isfile(tr) else []
    try:
        pcs, _p = captions.load_pieces(sb, segs, 40)
        spans = [(p["text"], float(p["s"][0]), float(p["s"][1])) for p in pcs]
    except Exception:   # noqa: BLE001
        spans = [(s["text"], float(s["start"]), float(s["end"])) for s in segs]
    out = []
    for text, a, b in spans:
        cs = _clean(text)
        for i, c in enumerate(cs):
            out.append((c, a + (b - a) * i / max(1, len(cs))))
    return out


def find(stream: List[Tuple[str, float]], words) -> List[float]:
    """所有讲到的位置（原片秒数，取第一个字的时间）。"""
    s = "".join(c for c, _ in stream)
    hits = []
    for w in ([words] if isinstance(words, str) else list(words)):
        key = _clean(w)
        if not key:
            continue
        i = s.find(key)
        while i >= 0:
            hits.append(stream[i][1])
            i = s.find(key, i + len(key))
    return sorted(set(round(h, 3) for h in hits))


def expand(sb: dict, tl) -> List[dict]:
    """把 triggers 展开成 overlays／postfx（成片时间），印出对照表。回传展开结果（给 CLI 列表用）。"""
    trs = sb.get("triggers") or []
    if not trs:
        return []
    stream = char_stream(sb)
    if not stream:
        print("⚠️ 关键词触发：没有转录或字幕轨，找不到讲话时间（先跑 transcribe）")
        return []
    new_ov, new_fx, res = [], [], []
    for tg in trs:
        words = tg.get("say") or tg.get("word")
        hits = []
        for src_t in find(stream, words):
            rs = tl.clip(src_t, src_t + 0.02)
            if rs:
                hits.append(rs[0][0])
        after = float(tg.get("after", -1e9))
        hits = [h for h in hits if h >= after]
        if not hits:
            print("⚠️ 关键词触发：没听到「%s」（换个写法，或检查字幕轨的字）" % (words if isinstance(words, str) else "／".join(words)))
            continue
        if not tg.get("every"):
            hits = hits[:1]
        dur, lead = float(tg.get("dur", DEF_DUR)), float(tg.get("lead", DEF_LEAD))
        for h in hits:
            a = round(max(0.0, h - lead), 3)
            b = round(a + dur, 3)
            if tg.get("card"):
                new_ov.append(dict(tg["card"], t=[a, b], _trigger=True))
            if tg.get("fx"):
                new_fx.append(dict(tg["fx"], t=[a, b], _trigger=True))
            if tg.get("toc"):
                toc = sb.setdefault("toc", {})
                if isinstance(toc, dict):
                    toc.setdefault("items", []).append({"t": a, "text": tg["toc"]})
            res.append({"say": words, "t": a})
    if new_ov:
        from . import composites
        tmp = dict(sb, overlays=new_ov)
        sb["overlays"] = list(sb.get("overlays") or []) + list(composites.expand(tmp).get("overlays") or [])
    if new_fx:
        sb["postfx"] = list(sb.get("postfx") or []) + new_fx
    if isinstance(sb.get("toc"), dict) and sb["toc"].get("items"):
        sb["toc"]["items"] = sorted(sb["toc"]["items"], key=lambda x: float(x["t"]))
    print("🎯 关键词触发：%s" % "、".join("%s@%.1fs" % (r["say"] if isinstance(r["say"], str) else r["say"][0], r["t"])
                                     for r in res))
    return res
