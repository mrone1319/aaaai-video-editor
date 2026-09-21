"""渲染：storyboard.json → 视频通道(裁切+字幕，一次编码) + 音频通道(拼接+配乐闪避+响度) → 封装。"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional

from . import captions, env, overlays, recipes, segment, theme
from .timeline import Timeline

DEFAULTS = {
    "output": {"width": 1080, "height": 1920, "fps": 30, "path": "out/final.mp4"},
    "captions": {"enabled": True},   # style 不写时跟随卡片风格，没有就 clean
    "music": None,
    "loudness": -14.0,
    "overlays": [],
    "zooms": [],
    "style": None,
    "segment": {"enabled": "auto", "target": 45.0, "min": 6.0},
}
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FADE = 0.008  # 段边界音频淡入淡出，消除拼接爆音


def load_storyboard(path: str) -> dict:
    sb = json.load(open(path, encoding="utf-8"))
    for k, v in DEFAULTS.items():
        if isinstance(v, dict):
            sb[k] = dict(v, **(sb.get(k) or {}))
        else:
            sb.setdefault(k, v)
    base = os.path.dirname(os.path.abspath(path))
    sb["_base"] = base
    sb["source"] = os.path.normpath(os.path.join(base, sb["source"]))
    sb["output"]["path"] = os.path.normpath(os.path.join(base, sb["output"]["path"]))
    if sb.get("music"):
        f = sb["music"]["file"]
        if f.startswith("bgm:"):   # 常备配乐库：写曲名就好（先找用户自己的 ~/.aaaai-editor/bgm/，再找套件自带的）
            from . import config
            name = f[4:]
            cands = [config.path("bgm", name + ext) for ext in (".m4a", ".mp3", ".wav")]
            cands.append(os.path.join(REPO, "assets", "bgm", name + ".m4a"))
            f = next((c for c in cands if os.path.isfile(c)), cands[-1])
            if not os.path.isfile(f):
                raise env.ToolError("常备配乐库没有这首：%s（aaaai-editor bgm 看清单）" % sb["music"]["file"])
        sb["music"]["file"] = os.path.normpath(os.path.join(base, f))
    try:
        return recipes.expand(sb)
    except ValueError as e:
        raise env.ToolError(str(e))


def _video_base(cuts, w, h, fps, deep: bool, nframes: Optional[int] = None,
                framing: Optional[dict] = None, hdr: bool = False) -> str:
    """裁切拼接 + 统一画幅，产出 [base]。deep=True 时走 yuv444，卡片边缘不被色度下采样。

    nframes：分段渲染时把这一段锁成确定帧数。各段单独做 fps 重采样会各自取整，
    不锁帧数就会每个接缝少一帧，段数一多就累积成音画不同步。
    """
    parts = []
    src = "[0:v]"
    if hdr:   # iPhone HLG／HDR10：先色调映射成 SDR bt709，否则成片发灰、颜色不对
        parts.append("[0:v]zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
                     "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,split=%d%s"
                     % (len(cuts), "".join("[h%d]" % i for i in range(len(cuts)))))
    for i, (a, b) in enumerate(cuts):
        if hdr:
            src = "[h%d]" % i
        # 每段先转到目标帧率再锁死帧数：不然每个剪辑点的取整误差会一路累积，
        # 长片到后面字幕就和画面对不上了
        n = max(1, int(round((b - a) * fps)))
        parts.append(src + "trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS,fps=%s,"
                     "tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=%d,"
                     "setpts=PTS-STARTPTS[v%d]" % (a, b, fps, n, i))
    n = len(cuts)
    parts.append("%sconcat=n=%d:v=1:a=0[cat]" % ("".join("[v%d]" % i for i in range(n)), n))
    z = float((framing or {}).get("zoom", 1.0))
    if z > 1.0001:   # 全局推近（机位坐得远）：并进第一次编码，不多压一代
        cx, cy = float(framing.get("cx", 0.5)), float(framing.get("cy", 0.4))
        tail = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d:(iw-%d)*%.4f:(ih-%d)*%.4f"
                % (int(w * z) & ~1, int(h * z) & ~1, w, h, w, cx, h, cy))
    else:
        tail = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d"
                % (w, h, w, h))
    if nframes:
        # 先用克隆帧补足（源区间偶尔会短一帧），再裁到确定帧数
        tail += (",tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=%d,setpts=PTS-STARTPTS"
                 % nframes)
    if deep:
        tail += ",format=yuv444p"
    parts.append("[cat]%s[base]" % tail)
    return ";".join(parts)


def _voice_graph(cuts, has_audio: bool = True) -> str:
    if not has_audio:   # 素材没有音轨（屏幕录制、动画片）：补一条等长静音，后面照常混配乐
        total = sum(b - a for a, b in cuts)
        return "anullsrc=r=48000:cl=stereo,atrim=duration=%.3f[voice]" % total
    parts = []
    for i, (a, b) in enumerate(cuts):
        d = b - a
        parts.append("[0:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS,afade=t=in:d=%s,afade=t=out:st=%.3f:d=%s[a%d]"
                     % (a, b, FADE, max(0.0, d - FADE), FADE, i))
    n = len(cuts)
    parts.append("%sconcat=n=%d:v=0:a=1[voice]" % ("".join("[a%d]" % i for i in range(n)), n))
    return ";".join(parts)


def _measure_loudness(wav: str, target: float) -> dict:
    p = env.run([env.ffmpeg(), "-v", "info", "-i", wav, "-af",
                 "loudnorm=I=%s:TP=-1.5:LRA=11:print_format=json" % target, "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    if not m:
        raise env.ToolError("响度测量失败")
    return json.loads(m.group(0))


def _render_pass(sb: dict, cuts, cap_events, t0: float, w: int, h: int, fps, work: str,
                 out: str, proxy: bool, tag: str, t1: Optional[float] = None,
                 nframes: Optional[int] = None, total: Optional[float] = None) -> None:
    """渲染一段（或整支）视频：卡片／推近／人像／字幕并进同一条链，只编码一次。"""
    ff = env.ffmpeg()
    ass_name = None
    if cap_events is not None:
        dur = (t1 - t0) if t1 is not None else None
        ev = []
        for a, b, txt, ex in cap_events:
            a2, b2 = a - t0, b - t0
            if dur is not None:
                if b2 <= 0.02 or a2 >= dur - 0.02:
                    continue
                a2, b2 = max(0.0, a2), min(dur, b2)
            ev.append((a2, b2, txt, ex))
        # B-roll 满版盖住画面的期间，字幕抬到画面中上；letterbox／blur 默认不抬（下方有黑边或模糊底，字幕放那里正好）
        lifts = [(float(o["t"][0]), float(o["t"][1])) for o in sb.get("overlays") or []
                 if o.get("type") == "broll" and o.get("lift", o.get("mode", "fullscreen") == "fullscreen")]
        if lifts:
            ev = [(a2, b2, txt, dict(ex or {}, lift=True)) if any(la <= (a2 + b2) / 2 <= lb for la, lb in lifts)
                  else (a2, b2, txt, ex) for a2, b2, txt, ex in ev]
        ass_name = "captions_%s.ass" % tag
        captions.write_ass(ev, os.path.join(work, ass_name), w, h,
                           sb["captions"].get("font") or env.find_font(), sb["captions"]["style"],
                           sb["captions"].get("highlight") or (), sb["captions"].get("margin_v"),
                           sb["captions"].get("size_scale"))
    zooms = sb.get("zooms") or []
    zoom_str = overlays.zoom_filter(zooms, w, h, fps) if zooms else None
    # 人像遮罩按「不带 format 的剪辑图」生成，成片改画质不会让遮罩缓存失效
    ov_inputs, assemble = overlays.build(sb, work, w, h, fps, source=sb["source"],
                                         base_graph=_video_base(cuts, w, h, fps, False, nframes,
                                                                sb.get("framing"), sb.get("_hdr", False)))
    parts = [_video_base(cuts, w, h, fps, bool(ov_inputs) and not proxy, nframes, sb.get("framing"),
                         sb.get("_hdr", False))]
    cur = "base"
    if zoom_str:
        parts.append("[base]%s[zb]" % zoom_str)
        cur = "zb"
    tail, cur = assemble(cur, ("subtitles=filename=%s" % ass_name) if ass_name else None, zoom_str)
    if tail:
        parts.append(tail)
    fade = float((sb.get("ending") or {}).get("fade", 0) or 0)
    if fade > 0 and total:
        st = total - fade - t0            # 片尾淡出换算成本段时间
        seg_len = (t1 - t0) if t1 is not None else total
        if st < seg_len:
            parts.append("[%s]fade=t=out:st=%.3f:d=%.3f[fo]" % (cur, max(0.0, st), fade))
            cur = "fo"
    parts.append("[%s]format=yuv420p[vout]" % cur)
    args = [ff, "-y", "-v", "error", "-i", sb["source"]]
    for g in ov_inputs:
        args += g
    if proxy:
        venc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "30"]
    elif sb["output"].get("encoder") == "hw":   # 长片赶时间：Apple 硬件编码，快数倍、文件稍大、画质略低
        venc = ["-c:v", "h264_videotoolbox", "-q:v", "70", "-pix_fmt", "yuv420p"]
    else:
        venc = ["-c:v", "libx264", "-preset", "slow", "-crf", "15"]
    env.run(args + ["-filter_complex", ";".join(parts), "-map", "[vout]", "-an"]
            + venc + ["-movflags", "+faststart", out], cwd=work)


def render(sb_path: str, only: Optional[str] = None, proxy: bool = False) -> str:
    sb = load_storyboard(sb_path)
    cuts: List = [tuple(c) for c in sb["cuts"]]
    if not cuts:
        raise env.ToolError("storyboard.cuts 是空的")
    out = sb["output"]
    w, h, fps = int(out["width"]), int(out["height"]), out["fps"]
    tl = Timeline(cuts, fps)
    if proxy:  # 预览：短边减半（保持偶数），只为看版面与节奏
        w, h = max(2, (w // 2) & ~1), max(2, (h // 2) & ~1)
        out = dict(out, path=os.path.splitext(out["path"])[0] + "_preview.mp4")
    work = os.path.join(sb["_base"], "work")
    os.makedirs(work, exist_ok=True)
    os.makedirs(os.path.dirname(out["path"]), exist_ok=True)
    ff = env.ffmpeg()
    info = env.probe(sb["source"])
    sb["_hdr"] = bool(info.get("hdr"))
    if sb["_hdr"]:
        print("🎨 素材是 HDR（iPhone 常见）：自动转成 SDR 色彩")

    # ---- 字幕事件（按整片时间轴算一次；分段时再平移）----
    cap_events = None
    cap = sb["captions"]
    if cap.get("enabled"):
        tr_path = os.path.join(sb["_base"], cap.get("transcript", "work/transcript.json"))
        if not os.path.isfile(tr_path):
            raise env.ToolError("缺少转录文件 %s（先跑 aaaai-editor transcribe）" % tr_path)
        segs = json.load(open(tr_path, encoding="utf-8"))["segments"]
        captions.resolve_style(sb)   # 没指定就跟随卡片风格；受限风格要先授权
        pcs, track = captions.load_pieces(sb, segs, captions.max_width(cap, w, h))
        if track:
            print("📝 使用手改字幕轨：%s" % os.path.relpath(track, sb["_base"]))
        cap_events = captions.to_events(pcs, tl)
        long_ = captions.too_long(pcs, cap, w, h)
        if long_:
            print("⚠️ %d 句字幕放不进一行（中文每句必须单行，请在标点处拆成两句）：%s"
                  % (len(long_), "；".join(x[:14] for x in long_[:5])))

    # ---- 视频通道 ----
    video = os.path.join(work, "video.mp4")
    if only in (None, "video"):
        scfg = sb.get("segment") or {}
        bounds = []
        if not proxy and segment.should(sb, tl.duration, len(cuts)):
            bounds = segment.plan(tl.duration, segment.forbidden(sb), fps,
                                  float(scfg.get("target", 45.0)), float(scfg.get("min", 6.0)),
                                  tl.boundaries())
        if not bounds:
            _render_pass(sb, cuts, cap_events, 0.0, w, h, fps, work, video, proxy, "full",
                         total=tl.duration)
        else:
            sd = os.path.join(work, "segs")
            os.makedirs(sd, exist_ok=True)
            edges = [0.0] + bounds + [tl.duration]
            print("🔪 分段渲染 %d 段，切点 %s（都落在卡片与推近之外）"
                  % (len(edges) - 1, " ".join("%.2fs" % b for b in bounds)))
            files = []
            total_frames = int(round(tl.duration * fps))
            for k in range(len(edges) - 1):
                s0, s1 = edges[k], edges[k + 1]
                last = k == len(edges) - 2
                # 每段都锁死帧数：各段之和恰好等于整片帧数，接缝不掉帧也不多帧
                f0 = int(round(s0 * fps))
                nf = (total_frames if last else int(round(s1 * fps))) - f0
                src_end = tl.duration if last else min(tl.duration, s1 + 3.0 / fps)
                p = os.path.join(sd, "seg_%02d.mp4" % k)
                _render_pass(segment.window(sb, s0, s1), tl.source_ranges(s0, src_end), cap_events,
                             s0, w, h, fps, work, p, proxy, "s%02d" % k, s1, nf, tl.duration)
                files.append(p)
            with open(os.path.join(sd, "list.txt"), "w", encoding="utf-8") as f:
                for p in files:
                    f.write("file '%s'\n" % os.path.basename(p))
            # 各段编码参数相同 → 直接无损拼接，不再压第二代
            env.run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "list.txt",
                     "-c", "copy", "-movflags", "+faststart", video], cwd=sd)
    if only == "video":
        return video

    # ---- 音频通道：响度锁定（频道实测做法，见 aaaai_editor/loud.py）----
    from . import loud
    target = float(sb["loudness"])
    mu = sb.get("music")
    fade = float((sb.get("ending") or {}).get("fade", 0) or 0)
    if not info.get("has_audio"):
        print("🔇 素材没有音轨：用静音垫底%s" % ("，照常混配乐" if mu else ""))
    audio, rep = loud.master(sb["source"], _voice_graph(cuts, info.get("has_audio", True)), tl.duration, work, target,
                             music=mu, fade=fade)
    print("🔊 响度 %.1f LUFS・真峰值 %.1f dBTP（人声 %+.1fdB%s，迭代 %d 次）"
          % (rep["I"], rep["TP"], rep["voice_gain"],
             ("、配乐 %+.1fdB" % rep["music_gain"]) if mu else "", rep["iters"]))
    if only == "audio":
        return audio

    # ---- 封装 ----
    env.run([ff, "-y", "-v", "error", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy",
             "-movflags", "+faststart", "-shortest", out["path"]])
    return out["path"]


def preview_subs(sb_path: str, t_from: Optional[float] = None, t_to: Optional[float] = None) -> str:
    """只烧字幕的低画质预览（480 宽、ultrafast、无卡片无推近、不做响度迭代）。
    频道教训（ep05）：为了确认字幕对时重渲完整成片 5 次＝75 分钟；这支约一分钟就能给用户看。"""
    sb = load_storyboard(sb_path)
    fps = sb["output"]["fps"]
    tl_full = Timeline([tuple(c) for c in sb["cuts"]], fps)
    a = max(0.0, t_from or 0.0)
    b = min(tl_full.duration, t_to if t_to is not None else tl_full.duration)
    cuts = tl_full.source_ranges(a, b)
    tl = Timeline(cuts, fps)
    w, h = 480, int(round(480 * int(sb["output"]["height"]) / float(sb["output"]["width"]))) & ~1
    work = os.path.join(sb["_base"], "work")
    os.makedirs(work, exist_ok=True)
    cap = sb["captions"]
    ass = None
    if cap.get("enabled"):
        tr = os.path.join(sb["_base"], cap.get("transcript", "work/transcript.json"))
        segs = json.load(open(tr, encoding="utf-8"))["segments"]
        pcs, _t = captions.load_pieces(sb, segs, captions.fit(sb))
        ass = "captions_subs.ass"
        captions.write_ass(captions.to_events(pcs, tl), os.path.join(work, ass), w, h,
                           cap.get("font") or env.find_font(), cap["style"], cap.get("highlight") or (),
                           cap.get("margin_v"), cap.get("size_scale"))
    info = env.probe(sb["source"])
    g = _video_base(cuts, w, h, fps, False, None, sb.get("framing"), bool(info.get("hdr")))
    g += ";[base]%sformat=yuv420p[v]" % (("subtitles=filename=%s," % ass) if ass else "")
    g += ";" + _voice_graph(cuts, info.get("has_audio", True)) + ";[voice]aformat=channel_layouts=stereo[a]"
    out = os.path.splitext(sb["output"]["path"])[0] + "_subs.mp4"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", sb["source"], "-filter_complex", g, "-map", "[v]",
             "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-c:a", "aac",
             "-b:a", "96k", "-movflags", "+faststart", out], cwd=work)
    return out
