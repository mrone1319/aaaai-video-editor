"""转录：ffmpeg 抽 16k 单声道 → whisper.cpp → transcript.json（分段级时间戳）。"""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Optional, Tuple

from . import audio, env, zh

ZH_PROMPT = "以下是普通话的句子，请使用简体中文。"
# 语速：中文按字、其他语言按词（每分钟）。中文 203 字/分为口播实测值，英文约 150 词/分
RATE = {"zh": 203.0, "other": 150.0}


def detect_language(wav: str) -> str:
    """用 whisper 自带的语言识别（看前 30 秒）；识别不出就当中文。"""
    p = subprocess.run([env.whisper_cli(), "-m", env.whisper_model(), "-f", wav, "-l", "auto", "-dl"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    m = re.search(r"auto-detected language:\s*([a-z]{2,3})", p.stdout or "")
    return m.group(1) if m else "zh"


def is_cjk_text(text: str) -> bool:
    han = sum(1 for c in text if ord(c) > 0x2E80)
    alnum = sum(1 for c in text if c.isalnum())
    return alnum > 0 and han >= 0.3 * alnum


def speech_units(text: str) -> Tuple[int, str]:
    """(数量, 单位)：中文数字，其他语言数词。"""
    if is_cjk_text(text):
        return sum(1 for c in text if ord(c) > 0x2E80 or c.isalnum()), "字"
    return len(re.findall(r"[^\W_]+(?:['’][^\W_]+)?", text)), "词"


def transcribe(src: str, out_json: str, lang: str = "auto", prompt: Optional[str] = None) -> dict:
    work = os.path.dirname(os.path.abspath(out_json))
    os.makedirs(work, exist_ok=True)
    if not env.probe(src).get("has_audio"):
        raise env.ToolError("这个视频没有音轨，没法转录（不要字幕就在 storyboard 写 \"captions\": {\"enabled\": false}）")
    wav = os.path.join(work, "audio16k.wav")
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", wav])
    if lang == "auto":
        lang = detect_language(wav)
    base = os.path.join(work, "whisper")
    cmd = [env.whisper_cli(), "-m", env.whisper_model(lang), "-f", wav, "-l", lang, "-oj", "-of", base, "-np"]
    if lang == "zh" and prompt is None:
        prompt = ZH_PROMPT
    if prompt:
        cmd += ["--prompt", prompt]
    env.run(cmd)
    raw = json.load(open(base + ".json", encoding="utf-8"))
    segs = []
    for t in raw.get("transcription", []):
        text = re.sub(r"\s+", " ", t.get("text", "")).strip()
        if lang == "zh":
            text = zh.t2s(text)   # 不带提示词时常出繁体
        if not text:
            continue
        segs.append({"start": t["offsets"]["from"] / 1000.0, "end": t["offsets"]["to"] / 1000.0, "text": text})
    # 结尾／静音处的幻听：whisper 会在接近静音的地方编出一句话（ep04 实测 -67dB 静音里转出「请不吝点赞…」）
    stats = {}
    try:
        e = audio.envelope(src)
        cut = max(-45.0, e.floor + 4)
        kept, dropped = [], []
        for sg in segs:
            (kept if e.level(sg["start"], max(sg["end"], sg["start"] + 0.2)) > cut else dropped).append(sg)
        segs = kept
        n, unit = speech_units(" ".join(sg["text"] for sg in segs))
        stats = {"chars": n, "unit": unit,
                 "est_seconds": round(n / (RATE["zh"] if unit == "字" else RATE["other"]) * 60, 1),
                 "snr_db": round(e.loud - e.floor, 1), "floor_db": round(e.floor, 1),
                 "dropped": [{"start": d["start"], "text": d["text"]} for d in dropped]}
    except env.ToolError:
        pass
    doc = {"language": raw.get("result", {}).get("language", lang), "source": os.path.abspath(src),
           "segments": segs, "stats": stats}
    json.dump(doc, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return doc
