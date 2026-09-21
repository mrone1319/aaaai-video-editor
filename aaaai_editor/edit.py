"""剪辑层的自动整理：开头 hook（把最强的一句挪到／复制到开头）、口头禅与 NG（讲错重讲）检测。

都只改 storyboard 的 cuts（原片时间区间），并把卡片／推近／配方的成片时间一起换算，不会错位。
检测结果先列给用户看，用户同意再套用（--apply）。
"""
from __future__ import annotations

import difflib
import json
import os
import re
from typing import Dict, List, Optional, Tuple

from . import audio, env, zh
from .timeline import Timeline

Range = Tuple[float, float]

FILLERS_ZH = ("嗯", "呃", "额", "唔", "欸", "诶", "啊", "哦", "喔", "呃呃", "嗯嗯")
FILLERS_EN = ("um", "uh", "erm", "uhm", "hmm", "mm", "ah", "er")
# 让 whisper 把口头禅也写出来（不带提示词时它会自动省略「嗯、呃」）
FILLER_PROMPT = "嗯，呃，这个……嗯，那个，呃，我们今天，嗯，来聊一聊。Um, uh, so, like, you know."


# ---------------------------------------------------------------- storyboard 读写
def _load(path: str) -> dict:
    return json.load(open(path, encoding="utf-8"))


def _save(path: str, sb: dict) -> None:
    json.dump(sb, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _source(sb: dict, path: str) -> str:
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(path)), sb["source"]))


def _remap(sb: dict, old: Timeline, new: Timeline, skip_first: float = 0.0) -> None:
    """卡片／推近／配方的成片时间：旧时间轴 → 原片时间 → 新时间轴（跳过开头 hook 那段的重复）。"""
    def m(t: float) -> float:
        src = old.to_source(t)
        hits = [a for a, _b in new.clip(src, src + 1e-3) if a >= skip_first - 1e-6]
        return round(hits[0], 3) if hits else round(t + skip_first, 3)

    for key in ("overlays", "zooms", "recipes"):
        for it in sb.get(key) or []:
            if isinstance(it.get("t"), list) and len(it["t"]) == 2:
                a, b = float(it["t"][0]), float(it["t"][1])
                na = m(a)
                it["t"] = [na, round(na + (b - a), 3)]
            for k in ("at",):
                if isinstance(it.get(k), (int, float)):
                    it[k] = m(float(it[k]))
            for sub in it.get("items") or []:
                if isinstance(sub, dict) and isinstance(sub.get("at"), (int, float)):
                    sub["at"] = m(float(sub["at"]))


def _subtract(cuts: List[Range], rm: List[Range], min_len: float = 0.12) -> List[Range]:
    out: List[Range] = []
    for a, b in cuts:
        segs = [(a, b)]
        for x, y in sorted(rm):
            nxt = []
            for p, q in segs:
                if y <= p or x >= q:
                    nxt.append((p, q))
                    continue
                if x > p:
                    nxt.append((p, x))
                if y < q:
                    nxt.append((y, q))
            segs = nxt
        out += [(round(p, 3), round(q, 3)) for p, q in segs if q - p >= min_len]
    return out


# ---------------------------------------------------------------- 找句子
def _pieces(sb_path: str) -> List[dict]:
    """字幕轨（手改过的优先）或转录的句子，原片时间。"""
    base = os.path.dirname(os.path.abspath(sb_path))
    cp = os.path.join(base, "work", "captions.json")
    if os.path.isfile(cp):
        return [{"s": list(p["s"]), "text": p["text"]} for p in json.load(open(cp, encoding="utf-8"))["pieces"]]
    tp = os.path.join(base, "work", "transcript.json")
    if not os.path.isfile(tp):
        raise env.ToolError("还没有转录（先跑 transcribe）")
    return [{"s": [s["start"], s["end"]], "text": s["text"]} for s in json.load(open(tp, encoding="utf-8"))["segments"]]


def _norm(t: str) -> str:
    return "".join(c for c in zh.t2s(t).replace("**", "").lower() if c.isalnum())


def find_text(sb_path: str, text: str) -> Range:
    """在字幕／转录里找一句话（可以只给一部分），返回原片时间区间。跨两三句也行。"""
    ps = _pieces(sb_path)
    want = _norm(text)
    best, score = None, 0.0
    for i in range(len(ps)):
        acc = ""
        for j in range(i, min(len(ps), i + 4)):
            acc += _norm(ps[j]["text"])
            r = difflib.SequenceMatcher(None, want, acc).ratio() if want not in acc else 1.0 + len(want) / (len(acc) + 1)
            if r > score:
                best, score = (ps[i]["s"][0], ps[j]["s"][1]), r
    if not best or score < 0.6:
        raise env.ToolError("字幕里找不到「%s」（换一段更完整的原话，或直接用 --from/--to 给原片秒数）" % text)
    return best


SNAP_MAX = 1.5   # 字幕时间和真实人声最多差这么多秒


def _snap(src: str, a: float, b: float) -> Range:
    """按真实人声修起止：字幕时间常差 0.5 秒以上，不能直接用。
    起点：a 落在人声中间就往前找到这段人声的开头；终点：b 之后人声还在继续就一路跟到停顿，再等尾音收完。"""
    e = audio.envelope(src)
    hop = audio.HOP
    v = e.voiced_mask(bridge=0.15)          # 字与字之间的小缝补起来；0.15 秒以上的停顿才算句子断开
    n = len(v)
    i = min(n - 1, max(0, e.idx(a)))
    if v[i]:
        lo = max(0, i - int(SNAP_MAX / hop))
        while i > lo and v[i - 1]:
            i -= 1
        a2 = e.t0 + i * hop - 0.09
    else:
        on = [o for o in e.onsets() if a - 0.35 <= o <= a + 0.40]
        a2 = (min(on, key=lambda o: abs(o - a)) - 0.09) if on else a - 0.05
    j = min(n - 1, max(0, e.idx(b)))
    look = min(n - 1, j + int(0.25 / hop))
    if not v[j] and any(v[j:look + 1]):     # 字幕说结束了，但 0.25 秒内又有人声：还是同一句的尾字
        j = next(k for k in range(j, look + 1) if v[k])
    if v[j]:
        hi = min(n - 1, j + int(SNAP_MAX / hop))
        while j < hi and v[j + 1]:
            j += 1
        b = e.t0 + (j + 1) * hop
    b2 = e.decay_end(b, limit=0.8) + 0.06
    return round(max(0.0, a2), 3), round(b2, 3)


# ---------------------------------------------------------------- hook
def hook(sb_path: str, text: Optional[str] = None, a: Optional[float] = None, b: Optional[float] = None,
         mode: str = "teaser") -> dict:
    """把一句话放到片头。teaser：开头先放这一句，原位置照样保留（预告式，最常用）；move：从原位置挪到开头。"""
    sb = _load(sb_path)
    src = _source(sb, sb_path)
    if text:
        a, b = find_text(sb_path, text)
    if a is None or b is None:
        raise env.ToolError("要给 --text「原话」或 --from/--to 原片秒数")
    a, b = _snap(src, float(a), float(b))
    fps = sb.get("output", {}).get("fps", 30)
    old_cuts = [tuple(c) for c in sb["cuts"]]
    old = Timeline(old_cuts, fps)
    body = old_cuts if mode == "teaser" else _subtract(old_cuts, [(a, b)])
    new_cuts = [(a, b)] + body
    new = Timeline(new_cuts, fps)
    lead = new.lengths[0]
    _remap(sb, old, new, skip_first=lead)
    sb["cuts"] = [[round(x, 3), round(y, 3)] for x, y in new_cuts]
    sb.setdefault("hook", {})
    sb["hook"] = {"source": [a, b], "mode": mode}
    _save(sb_path, sb)
    heard = _hear(sb_path, src, a, b)
    miss = bool(text and heard is not None and _tail_missing(text, heard))
    return {"range": (a, b), "len": round(lead, 2), "mode": mode, "duration": round(new.duration, 2),
            "heard": heard, "tail_missing": miss}


def _hear(sb_path: str, src: str, a: float, b: float) -> Optional[str]:
    """把剪出来的那一段单独听写一次（不带提示词），给用户核对句子完不完整。"""
    try:
        work = os.path.join(os.path.dirname(os.path.abspath(sb_path)), "work")
        os.makedirs(work, exist_ok=True)
        wav = os.path.join(work, "hook16k.wav")
        env.run([env.ffmpeg(), "-y", "-v", "error", "-ss", "%.3f" % a, "-t", "%.3f" % (b - a), "-i", src,
                 "-vn", "-ac", "1", "-ar", "16000", wav])
        lang = _lang_of(sb_path)
        base = os.path.join(work, "hook_heard")
        env.run([env.whisper_cli(), "-m", env.whisper_model(lang), "-f", wav, "-l", lang, "-otxt", "-of", base, "-np"])
        txt = " ".join(open(base + ".txt", encoding="utf-8").read().split())
        return zh.t2s(txt) if lang == "zh" else txt
    except (env.ToolError, OSError):
        return None


def _tail_missing(want: str, heard: str) -> bool:
    """原话最后两个字（英文最后一个词）没出现在剪出来的那段里：多半切掉了句尾。"""
    w, h = _norm(want), _norm(heard)
    if not w or not h:
        return False
    tail = w[-2:] if any("\u4e00" <= c <= "\u9fff" for c in w[-2:]) else re.findall(r"[a-z0-9]+", _norm_words(want))[-1:]
    if isinstance(tail, list):
        return bool(tail) and tail[0] not in h
    return tail not in h


def _norm_words(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", t.lower())


_HOOK_WORDS_ZH = ("最", "千万", "别", "不要", "其实", "为什么", "秘密", "真相", "错", "贵", "省", "免费", "没人", "所有人",
                  "一定", "竟然", "原来", "关键", "唯一", "第一", "后悔", "难")
_HOOK_WORDS_EN = ("most", "never", "don't", "stop", "actually", "why", "secret", "truth", "mistake", "wrong",
                  "free", "nobody", "everyone", "only", "first", "regret", "biggest", "worst", "best")
_CONTRAST = (("不是", "而是"), ("不是", "是"), ("以为", "其实"), ("not", "but"), ("think", "actually"))


def hook_score(text: str) -> float:
    """一句话当开头 hook 的分数：有数字、有反差、有强烈字眼、是问句、长度刚好。"""
    t = text.replace("**", "")
    low = t.lower()
    s = 0.0
    if re.search(r"[0-9]|[一二两三四五六七八九十百千万亿]+(个|倍|年|天|次|块|元|%|成)|%", t):
        s += 2.0
    if any(a in low and b in low[low.find(a) + len(a):] for a, b in _CONTRAST):
        s += 3.0
    s += 1.2 * sum(1 for w in _HOOK_WORDS_ZH if w in t) + 1.2 * sum(1 for w in _HOOK_WORDS_EN if re.search(r"\b%s\b" % re.escape(w), low))
    if "?" in t or "？" in t or t.rstrip().endswith(("吗", "呢")):
        s += 1.5
    n = len(_norm(t))
    s += 1.0 if 10 <= n <= 28 else (-1.5 if n < 6 or n > 40 else 0.0)
    return round(s, 2)


def suggest_hooks(sb_path: str, n: int = 3) -> List[dict]:
    """从成片里挑最适合放到开头当预告的几句（1～3 段相连的字幕，中间没有长停顿，2～8 秒）。"""
    sb = _load(sb_path)
    cuts = [tuple(c) for c in sb["cuts"]]
    ps = [p for p in _pieces(sb_path) if _kept(p["s"][0], p["s"][1], cuts) > 0.3]
    tl = Timeline(cuts, sb.get("output", {}).get("fps", 30))
    env_ = audio.envelope(_source(sb, sb_path))
    cands = []
    for i in range(len(ps)):
        txt = ""
        for j in range(i, min(len(ps), i + 3)):
            if j > i and ps[j]["s"][0] - ps[j - 1]["s"][1] > 0.6:
                break
            txt += ("，" if txt else "") + ps[j]["text"].replace("**", "")
            a, b = ps[i]["s"][0], ps[j]["s"][1]
            if not (2.0 <= b - a <= 8.0):
                continue
            # 成片里的位置（已经做过 hook 的话，第一段是预告，取后面正片那一次）
            hit = [off + (a - ca) for (ca, cb), off in zip(tl.cuts, tl.offsets) if ca - 0.3 <= a <= cb]
            at = hit[-1] if hit else None
            if at is not None and at < 3.0:    # 本来就在开头
                continue
            sc = hook_score(txt)
            # 半句话不适合当开头：结束后人声还紧接着（句子没讲完）、或开始前人声还在（从句子中间切入）
            if env_.voiced(b + 0.05, b + 0.30):
                sc -= 3.0
            if env_.voiced(a - 0.30, a - 0.05):
                sc -= 1.5
            cands.append({"text": txt, "s": [a, b], "at": at, "score": round(sc, 2)})
    cands.sort(key=lambda c: -c["score"])
    out: List[dict] = []
    for c in cands:
        if c["score"] <= 0 or any(not (c["s"][1] <= o["s"][0] or c["s"][0] >= o["s"][1]) for o in out):
            continue
        out.append(c)
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------- 口头禅与 NG
def _tokens(src: str, work: str, lang: str) -> List[Tuple[str, float, float]]:
    """带口头禅提示词的逐词时间（缓存）。"""
    from . import transcribe
    os.makedirs(work, exist_ok=True)
    st = os.stat(src)
    cache = os.path.join(work, "tidy_tokens.json")
    key = [os.path.abspath(src), st.st_size, st.st_mtime_ns, lang, 3]
    try:
        d = json.load(open(cache, encoding="utf-8"))
        if d.get("key") == key:
            return [tuple(t) for t in d["tokens"]]
    except (OSError, ValueError):
        pass
    wav = os.path.join(work, "tidy16k.wav")
    from .align import voiced_wav
    convert = voiced_wav(src, wav)         # 拿掉长停顿再听写，逐词时间才不会漂
    if lang == "auto":
        lang = transcribe.detect_language(wav)
    base = os.path.join(work, "tidy_tokens")
    env.run([env.whisper_cli(), "-m", env.whisper_model(lang), "-f", wav, "-l", lang, "-ojf", "-of", base, "-np",
             "--prompt", FILLER_PROMPT])
    data = json.load(open(base + ".json", encoding="utf-8"))
    toks = []
    for seg in data.get("transcription", []):
        for t in seg.get("tokens") or []:
            txt = (t.get("text") or "").strip()
            off = t.get("offsets") or {}
            if not txt or txt.startswith("[") or txt.startswith("<") or "from" not in off:
                continue
            toks.append((zh.t2s(txt), off["from"] / 1000.0, off.get("to", off["from"]) / 1000.0))
    toks = convert(toks)
    json.dump({"key": key, "tokens": toks}, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return toks


def _lang_of(sb_path: str) -> str:
    tp = os.path.join(os.path.dirname(os.path.abspath(sb_path)), "work", "transcript.json")
    try:
        return json.load(open(tp, encoding="utf-8")).get("language") or "zh"
    except (OSError, ValueError):
        return "zh"


def _inside(t: float, cuts: List[Range]) -> bool:
    return any(a <= t <= b for a, b in cuts)


def _kept(a: float, b: float, cuts: List[Range]) -> float:
    """[a,b] 有多少秒还留在目前的片子里。"""
    return sum(max(0.0, min(b, y) - max(a, x)) for x, y in cuts)


def detect(sb_path: str, lang: str = "auto") -> List[dict]:
    """找出口头禅（嗯、呃、um…）与 NG（同一句讲到一半重讲、整句重讲），只列在目前保留的片段里的。"""
    sb = _load(sb_path)
    src = _source(sb, sb_path)
    work = os.path.join(os.path.dirname(os.path.abspath(sb_path)), "work")
    cuts = [tuple(c) for c in sb["cuts"]]
    e = audio.envelope(src)
    toks = _tokens(src, work, lang)
    props: List[dict] = []

    # 1) 口头禅：带提示词的识别会写出「嗯、呃」，但也会把含糊的真话听成「呃」（实测会切掉「个弯」「事情做」）。
    #    所以再拿不带提示词的逐词识别核对：同一段时间那边听到的是真正的字，就不算口头禅。
    from . import align
    try:
        plain = align.token_stream(src, work, lang if lang != "auto" else _lang_of(sb_path))
    except env.ToolError:
        plain = []
    fill = set(FILLERS_ZH) | set(FILLERS_EN)

    def real_word_under(a: float, b: float) -> bool:
        for txt, x, y in plain:
            w_ = re.sub(r"[\W_]+", "", txt.lower())
            if not w_ or w_ in fill:
                continue
            ov = min(b, max(y, x + 0.05)) - max(a, x)
            if ov > 0.4 * (b - a):
                return True
        return False

    for i, (txt, a, b) in enumerate(toks):
        w = re.sub(r"[\W_]+", "", txt.lower())
        if w not in fill or _kept(a, b, cuts) < 0.08 or real_word_under(a, b):
            continue
        if not e.voiced(a - 0.05, b + 0.05):   # 那段根本是静音：提示词让 whisper 在静音上「听」出了呃
            continue
        # 「啊／哦」常是句尾语气词：前一个词紧贴着就不算
        if w in ("啊", "哦", "喔", "ah") and i and a - toks[i - 1][2] < 0.08:
            continue
        lo = min(range(max(0, e.idx(a - 0.15)), e.idx(a + 0.05) + 1), key=lambda k: e.db[k]) * audio.HOP
        hi = min(range(e.idx(b - 0.05), min(len(e.db) - 1, e.idx(b + 0.20)) + 1), key=lambda k: e.db[k]) * audio.HOP
        if hi - lo >= 0.12:
            props.append({"kind": "口头禅", "s": [round(lo, 3), round(hi, 3)], "text": txt})

    # 2) 讲到一半重讲：同一串字（≥3 个）在 12 个字以内又出现一次 → 删掉前一次到重讲开始之间
    chars: List[Tuple[str, float, float]] = []
    for txt, a, b in toks:
        cs = [c for c in txt.lower() if c.isalnum()]
        for k, c in enumerate(cs):
            chars.append((c, a + (b - a) * k / max(1, len(cs)), a + (b - a) * (k + 1) / max(1, len(cs))))
    s = "".join(c for c, _a, _b in chars)
    i, n = 0, len(s)
    while i < n - 6:
        found = None
        for k in (6, 5, 4, 3):
            if i + k > n:
                continue
            frag = s[i:i + k]
            j = s.find(frag, i + k, min(n, i + k + 12))
            if j > 0 and chars[j][1] - chars[i + k - 1][2] < 2.5:
                found = (k, j)
                break
        if found:
            k, j = found
            a, b = chars[i][1], chars[j][1]
            if _inside((a + b) / 2, cuts) and b - a >= 0.3 and not re.fullmatch(r"(.)\1+", s[i:i + k]):
                lo = min(range(max(0, e.idx(a - 0.12)), e.idx(a + 0.05) + 1), key=lambda q: e.db[q]) * audio.HOP
                hi = min(range(e.idx(b - 0.12), e.idx(b + 0.03) + 1), key=lambda q: e.db[q]) * audio.HOP
                props.append({"kind": "讲到一半重讲", "s": [round(lo, 3), round(hi, 3)],
                              "text": "「%s…」→ 重讲「%s」" % (s[i:j], s[j:j + k + 4])})
            i = j
        else:
            i += 1

    # 3) 整句重讲：相邻两句开头很像、前一句较短或被打断 → 保留后一句
    ps = _pieces(sb_path)
    for x, y in zip(ps, ps[1:]):
        nx, ny = _norm(x["text"]), _norm(y["text"])
        if len(nx) < 4 or not _inside((x["s"][0] + x["s"][1]) / 2, cuts):
            continue
        k = min(len(nx), len(ny), 8)
        head = difflib.SequenceMatcher(None, nx[:k], ny[:k]).ratio()
        if head >= 0.75 and len(nx) <= len(ny) + 2 and y["s"][0] - x["s"][1] < 3.0:
            props.append({"kind": "整句重讲", "s": [round(x["s"][0] - 0.05, 3), round(y["s"][0] - 0.05, 3)],
                          "text": "「%s」→ 重讲「%s」" % (x["text"], y["text"])})

    # 合并重叠、按时间排序、换成成片时间方便人看
    props.sort(key=lambda p: p["s"][0])
    merged: List[dict] = []
    for p in props:
        if merged and p["s"][0] <= merged[-1]["s"][1] - 0.05:
            if p["kind"] != "口头禅":
                merged[-1] = p if (p["s"][1] - p["s"][0]) > (merged[-1]["s"][1] - merged[-1]["s"][0]) else merged[-1]
            continue
        merged.append(p)
    tl = Timeline(cuts, sb.get("output", {}).get("fps", 30))
    for k, p in enumerate(merged, 1):
        p["id"] = k
        hit = tl.clip(p["s"][0], p["s"][1])
        p["t"] = round(hit[0][0], 2) if hit else None
        p["len"] = round(p["s"][1] - p["s"][0], 2)
    json.dump(merged, open(os.path.join(work, "tidy.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return merged


def apply(sb_path: str, ids: Optional[List[int]] = None) -> dict:
    """套用 detect 的结果（全部或指定编号）：从 cuts 扣掉那些区间，卡片时间跟着换算。"""
    work = os.path.join(os.path.dirname(os.path.abspath(sb_path)), "work")
    props = json.load(open(os.path.join(work, "tidy.json"), encoding="utf-8"))
    pick = [p for p in props if not ids or p["id"] in ids]
    sb = _load(sb_path)
    fps = sb.get("output", {}).get("fps", 30)
    old_cuts = [tuple(c) for c in sb["cuts"]]
    old = Timeline(old_cuts, fps)
    new_cuts = _subtract(old_cuts, [tuple(p["s"]) for p in pick])
    new = Timeline(new_cuts, fps)
    lead = 0.0
    if sb.get("hook") and sb["hook"].get("source") and new_cuts and \
            abs(new_cuts[0][0] - sb["hook"]["source"][0]) < 1e-3:
        lead = new.lengths[0]
    _remap(sb, old, new, skip_first=lead)
    sb["cuts"] = [[x, y] for x, y in new_cuts]
    _save(sb_path, sb)
    return {"removed": len(pick), "saved": round(old.duration - new.duration, 2), "duration": round(new.duration, 2)}
