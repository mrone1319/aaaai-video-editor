"""辅助工具：配乐清单、滑动窗口听写、剪点探测、配乐 A/B、手机预览、封面、推近对比。

listen／probe-cut 移植自 MR ONE 频道自己的 map-audio／probe-cut：
  · 不用整段 whisper 验收——同一段跑两次会随机漏掉整句（ep07）
  · 判定性听写一律**不带提示词**——提示词会在静音上幻听出词（ep10）
  · 「窗口里听到这个词」≠「词在窗口开头」，要逐步收窄窗口（probe-cut 就是做这个）
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Tuple

from . import env, render, zh
from .timeline import Timeline

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BGM = os.path.join(REPO, "assets", "bgm")
_clean = lambda s: re.sub(r"[^一-鿿a-z0-9]", "", re.sub(r"\[[^\]]*\]", "", s.lower()))


def bgm_list() -> List[Tuple[str, str]]:
    rows, readme = [], os.path.join(BGM, "README.md")
    desc = {}
    if os.path.isfile(readme):
        for ln in open(readme, encoding="utf-8"):
            m = re.match(r"\|\s*`([\w-]+)`\s*\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|", ln)
            if m:
                desc[m.group(1)] = "%s BPM｜%s｜%s" % (m.group(2), m.group(3).strip(), m.group(4).strip())
    for f in sorted(os.listdir(BGM)) if os.path.isdir(BGM) else []:
        if f.endswith(".m4a"):
            n = f[:-4]
            rows.append((n, desc.get(n, "")))
    from . import config
    mine = config.path("bgm")   # 用户自己加的配乐：放这里，更新程序不会删
    for f in sorted(os.listdir(mine)) if os.path.isdir(mine) else []:
        if f.endswith((".m4a", ".mp3", ".wav")) and f.rsplit(".", 1)[0] not in dict(rows):
            rows.append((f.rsplit(".", 1)[0], "（你自己加的）"))
    return rows


def _hear(wav: str, a: float, b: float, tmpd: str, lang: str = "zh") -> str:
    f = os.path.join(tmpd, "w.wav")
    env.run([env.ffmpeg(), "-y", "-v", "error", "-ss", "%.3f" % a, "-to", "%.3f" % b, "-i", wav, f])
    p = subprocess.run([env.whisper_cli(), "-m", env.whisper_model(lang), "-l", lang, "-f", f, "-nt", "-np"],
                       capture_output=True, text=True)
    return _clean(zh.t2s(p.stdout.replace("\n", "")))


def _wav(src: str, tmpd: str) -> str:
    w = os.path.join(tmpd, "src16k.wav")
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", w])
    return w


def _lang(wav: str) -> str:
    """短窗口里 whisper 自己判语言不稳：先对整段判一次，之后每个窗口都用它。"""
    from .transcribe import detect_language
    return detect_language(wav)


def listen(src: str, a: float, b: float, win: float = 2.5, hop: float = 0.5) -> List[Tuple[float, str]]:
    """滑动窗口听写：「第几秒在讲什么」对照表（单进程，whisper medium 每进程约 1.4GB）。"""
    tmpd = tempfile.mkdtemp()
    try:
        wav, rows, t = _wav(src, tmpd), [], a
        lang = _lang(wav)
        while t < b:
            rows.append((round(t, 2), _hear(wav, t, min(b, t + win), tmpd, lang)))
            t += hop
        return rows
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def probe_cut(src: str, mode: str, anchor: float, lo: float, hi: float, step: float, expect: str):
    """end：从 anchor 听到 t，找「已经讲完 expect」的最早 t；start：找「从 t 开始、开头是 expect」的最晚 t。"""
    if lo > hi or step <= 0:
        raise env.ToolError("范围不对：lo 要小于等于 hi，step 要大于 0")
    if mode == "end" and lo <= anchor:
        raise env.ToolError("end 模式是「从 anchor 听到 t」：lo 要大于 anchor（现在 anchor=%.2f、lo=%.2f）" % (anchor, lo))
    tmpd = tempfile.mkdtemp()
    try:
        wav, exp, out, t = _wav(src, tmpd), _clean(zh.t2s(expect)), [], lo
        lang = _lang(wav)
        while t <= hi + 1e-6:
            if mode == "end":
                txt = _hear(wav, anchor, t, tmpd, lang)
                ok = txt.endswith(exp[-min(3, len(exp)):]) if exp else False
            else:
                txt = _hear(wav, t, t + anchor, tmpd, lang)
                ok = txt.startswith(exp[:min(3, len(exp))]) if exp else False
            out.append((round(t, 3), ok, txt))
            t += step
        return out
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def music_ab(sb_path: str, at: float, dur: float, dbs: List[float]) -> List[str]:
    """同一段、几种配乐音量各出一支 MP3，让用户 A/B 听完再定（频道规则：不要没听过就定案）。"""
    from . import loud
    sb = render.load_storyboard(sb_path)
    if not sb.get("music"):
        raise env.ToolError("storyboard 没有 music，先选一首（aaaai-editor bgm 看常备配乐）")
    tl = Timeline([tuple(c) for c in sb["cuts"]], sb["output"]["fps"], sb.get("speed"))
    b = min(tl.duration, at + dur)
    cuts = tl.source_ranges(at, b)
    outs = []
    for db in dbs:
        d = os.path.join(sb["_base"], "work", "ab", "db%+d" % int(db))
        os.makedirs(d, exist_ok=True)
        a_, _rep = loud.master(sb["source"], render._voice_graph(cuts, True, render.denoise_filter(sb)), b - at, d,
                               float(sb["loudness"]),
                               music=dict(sb["music"], db=db))
        mp3 = os.path.join(sb["_base"], "out", "ab_%+ddB.mp3" % int(db))
        os.makedirs(os.path.dirname(mp3), exist_ok=True)
        env.run([env.ffmpeg(), "-y", "-v", "error", "-i", a_, "-c:a", "libmp3lame", "-b:a", "192k", mp3])
        outs.append(mp3)
    return outs


def denoise_ab(sb_path: str, at: float, dur: float, levels: List[str]) -> List[str]:
    """同一段、不降噪／几种降噪强度各出一支 MP3，让用户听完再定（降噪太重声音会发闷）。"""
    from . import loud
    sb = render.load_storyboard(sb_path)
    tl = Timeline([tuple(c) for c in sb["cuts"]], sb["output"]["fps"], sb.get("speed"))
    b = min(tl.duration, at + dur)
    cuts = tl.source_ranges(at, b)
    outs = []
    for lv in levels:
        cfg = dict(sb, denoise=(False if lv in ("0", "off") else ("strong" if lv == "strong" else
                                                                (float(lv) if lv.replace(".", "", 1).isdigit() else True))))
        d = os.path.join(sb["_base"], "work", "ab", "dn_%s" % lv)
        os.makedirs(d, exist_ok=True)
        a_, _rep = loud.master(sb["source"], render._voice_graph(cuts, True, render.denoise_filter(cfg)), b - at, d,
                               float(sb["loudness"]), music=None)
        mp3 = os.path.join(sb["_base"], "out", "降噪AB_%s.mp3" % {"0": "原声", "off": "原声", "on": "标准",
                                                                  "strong": "加强"}.get(lv, lv + "dB"))
        os.makedirs(os.path.dirname(mp3), exist_ok=True)
        env.run([env.ffmpeg(), "-y", "-v", "error", "-i", a_, "-c:a", "libmp3lame", "-b:a", "192k", mp3])
        outs.append(mp3)
    return outs


def phone(sb_path: str, limit_mb: float = 28.0) -> str:
    """手机预览版：720 宽、≤ 30MB（母带常 100MB 上下，传不到手机）。只供预览，不是交付物。"""
    sb = render.load_storyboard(sb_path)
    src = sb["output"]["path"]
    if not os.path.isfile(src):
        raise env.ToolError("找不到成片 %s（先 render）" % src)
    dur = env.probe(src)["duration"]
    vk = int(max(600, min(4000, limit_mb * 8 * 1024 / max(1.0, dur) * 0.92 - 128)))
    out = os.path.splitext(src)[0] + "_phone.mp4"
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", src, "-vf", "scale=720:-2", "-c:v", "libx264",
             "-preset", "medium", "-b:v", "%dk" % vk, "-maxrate", "%dk" % int(vk * 1.3), "-bufsize", "%dk" % (vk * 2),
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out])
    return out


def framing_sheet(sb_path: str, at: float, levels: List[float], cy: float = 0.4) -> str:
    """同一帧用几种推近倍率裁切，拼成对比图给用户选（频道规则：用截图，不用文字描述）。"""
    sb = render.load_storyboard(sb_path)
    o = sb["output"]
    W, H = int(o["width"]), int(o["height"])
    tl = Timeline([tuple(c) for c in sb["cuts"]], o["fps"], sb.get("speed"))
    ts = tl.to_source(min(at, tl.duration - 0.05))
    d = os.path.join(sb["_base"], "work")
    ins, parts = [], []
    for k, z in enumerate(levels):
        crop = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d:(iw-%d)*0.5:(ih-%d)*%.3f"
                % (int(W * z) & ~1, int(H * z) & ~1, W, H, W, H, cy))
        parts.append("[0:v]%s,scale=360:640,drawtext=fontfile='%s':text='%.2fx':fontsize=34:fontcolor=white:"
                     "borderw=3:bordercolor=black:x=18:y=18[v%d]" % (crop, _font(), z, k))
    g = ";".join(parts) + ";" + "".join("[v%d]" % k for k in range(len(levels))) + \
        "hstack=inputs=%d[o]" % len(levels) if len(levels) > 1 else ";".join(parts).replace("[v0]", "[o]")
    out = os.path.join(d, "framing.png")
    env.run([env.ffmpeg(), "-y", "-v", "error", "-ss", "%.3f" % ts, "-i", sb["source"], "-filter_complex", g,
             "-map", "[o]", "-frames:v", "1", out])
    return out


def _font() -> str:
    from . import theme
    return theme.cjk_font()
