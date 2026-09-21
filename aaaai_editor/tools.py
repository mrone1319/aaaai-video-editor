"""辅助工具：配乐清单、滑动窗口听写、剪点探测、配乐 A/B、手机预览、封面、推近对比。

listen／probe-cut 移植自 MR ONE 频道自己的 map-audio／probe-cut：
  · 不用整段 whisper 验收——同一段跑两次会随机漏掉整句（ep07）
  · 判定性听写一律**不带提示词**——提示词会在静音上幻听出词（ep10）
  · 「窗口里听到这个词」≠「词在窗口开头」，要逐步收窄窗口（probe-cut 就是做这个）
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

from . import captions, env, render, zh
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
    tl = Timeline([tuple(c) for c in sb["cuts"]], sb["output"]["fps"])
    b = min(tl.duration, at + dur)
    cuts = tl.source_ranges(at, b)
    outs = []
    for db in dbs:
        d = os.path.join(sb["_base"], "work", "ab", "db%+d" % int(db))
        os.makedirs(d, exist_ok=True)
        a_, _rep = loud.master(sb["source"], render._voice_graph(cuts), b - at, d, float(sb["loudness"]),
                               music=dict(sb["music"], db=db))
        mp3 = os.path.join(sb["_base"], "out", "ab_%+ddB.mp3" % int(db))
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
    tl = Timeline([tuple(c) for c in sb["cuts"]], o["fps"])
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


def cover(sb_path: str, at: float, text: str, sub: str = "", handle: Optional[str] = None,
          y: float = 0.55, color: str = "#F4C430") -> Tuple[List[str], str]:
    """封面：成片一帧 + 招牌金大字，关键文字落在四周各留 15% 的安全区（IG 主页 3:4／1:1／4:5 裁切都不掉字）。
    输出 1080×1920 与 1080×1350，并检查文字块有没有压到脸（用人像遮罩估脸的位置）。"""
    from . import richtext
    sb = render.load_storyboard(sb_path)
    src = sb["output"]["path"]
    if not os.path.isfile(src):
        raise env.ToolError("找不到成片 %s（先 render）" % src)
    ow, oh = int(sb["output"]["width"]), int(sb["output"]["height"])
    landscape = ow > oh
    W, H = (1920, 1080) if landscape else (1080, 1920)   # 横版片出 YouTube 缩图尺寸；竖版出 Reels／Shorts 尺寸
    d = os.path.join(sb["_base"], "out")
    work = os.path.join(sb["_base"], "work")
    os.makedirs(work, exist_ok=True)
    os.makedirs(d, exist_ok=True)
    frame = os.path.join(work, "cover_frame.png")
    env.run([env.ffmpeg(), "-y", "-v", "error", "-ss", "%.3f" % at, "-i", src, "-frames:v", "1",
             "-vf", "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (W, H, W, H), frame])
    safe_w = W * 0.70
    n = max(1, sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in text))
    size = min(W * 0.13, H * 0.16, safe_w / n)
    fam = "PingFang SC"
    win, asc, _cap = richtext.metrics(fam)
    top = H * y
    lines = [
        "Dialogue: 0,0:00:00.00,0:00:05.00,C,,0,0,0,,{\\an8\\pos(%d,%.1f)\\fn%s\\fs%.1f\\b1\\c%s\\bord%.1f\\3c&H101010&"
        "\\shad%.1f\\4c&H000000&\\4a&H60&}%s" % (W // 2, top - (asc - 0.85) * size, fam, size * win,
                                                 richtext._c(color), size * 0.035, size * 0.05, text)]
    yy = top + size * 1.30
    if sub:
        ss = size * 0.36
        lines.append("Dialogue: 0,0:00:00.00,0:00:05.00,C,,0,0,0,,{\\an8\\pos(%d,%.1f)\\fn%s\\fs%.1f\\b1\\c&HFFFFFF&"
                     "\\bord%.1f\\3c&H101010&}%s" % (W // 2, yy - (asc - 0.85) * ss, fam, ss * win, ss * 0.06, sub))
        yy += ss * 1.6
    from . import config
    handle = config.load().get("handle", "") if handle is None else handle   # 账号名：aaaai-editor config --set handle=@你的账号
    hs = min(W, H * 0.75) * 0.030 if handle else 0.0
    if handle:
        lines.append("Dialogue: 0,0:00:00.00,0:00:05.00,C,,0,0,0,,{\\an8\\pos(%d,%.1f)\\fnAvenir Next Bold\\fs%.1f"
                     "\\fsp%.1f\\c&HFFFFFF&\\bord2\\3c&H101010&}%s" % (W // 2, yy, hs * 1.2, hs * 0.06, handle))
    block = (top, yy + hs * 1.4)
    ass = os.path.join(work, "cover.ass")
    richtext.write(ass, W, H, lines)
    full = os.path.join(d, "cover_%dx%d.png" % (W, H))
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", frame, "-vf", "subtitles=filename=cover.ass",
             "-frames:v", "1", full], cwd=work)   # 相对文件名：路径里有引号／冒号也不会坏
    if landscape:
        check = os.path.join(work, "cover_check.png")
        env.run([env.ffmpeg(), "-y", "-v", "error", "-i", full, "-vf", "scale=960:540", check])
        return [full, check], ""
    crop = os.path.join(d, "cover_1080x1350.png")
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", full, "-vf", "crop=1080:1350:0:285", crop])
    check = os.path.join(work, "cover_check.png")   # Reels 全画面 vs 主页裁切：两版并排给人看
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", full, "-i", crop, "-filter_complex",
             "[0]scale=540:960[a];[1]scale=540:675,pad=540:960:0:142:black[b];[a][b]hstack", check])
    warn = ""
    try:   # 用人像遮罩估脸：人物遮罩最上面 35% 高度当作脸部区
        from . import matte
        raw = subprocess.run([env.ffmpeg(), "-v", "error", "-i", frame, "-vf", "scale=270:480", "-f", "rawvideo",
                              "-pix_fmt", "bgra", "-"], capture_output=True).stdout
        m = subprocess.run([matte.helper(), "270", "480", "accurate"], input=raw, capture_output=True).stdout
        rows = [y_ for y_ in range(480) if sum(1 for x in range(270) if m[y_ * 270 + x] > 128) > 12]
        if rows:
            f0, f1 = rows[0] * 4, (rows[0] + (rows[-1] - rows[0]) * 0.35) * 4
            if block[0] < f1 and block[1] > f0:
                warn = "文字块 y %.0f–%.0f 可能压到脸（脸约在 y %.0f–%.0f），试 --y %.2f" % (
                    block[0], block[1], f0, f1, min(0.78, (f1 + 40) / H))
    except Exception:
        pass
    return [full, crop, check], warn
