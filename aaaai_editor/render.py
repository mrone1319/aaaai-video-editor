"""渲染：storyboard.json → 视频通道(裁切+字幕，一次编码) + 音频通道(拼接+配乐闪避+响度) → 封装。"""
from __future__ import annotations

import hashlib
import json
import subprocess
import os
from typing import Tuple, List, Optional

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
    from . import icons as _icons
    _icons.set_project(base)   # 项目自己的图标（assets/icons/、assets/）优先于套件图标库
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
        sb = recipes.expand(sb)
    except ValueError as e:
        raise env.ToolError(str(e))
    from . import composites
    return composites.expand(sb)   # 证据截图／工作流／行动号召／倒数 → 基本卡片；卡片接管期间的排版


def _hl_color(sb: dict) -> Optional[str]:
    """字幕关键词颜色：storyboard 写了 captions.hl 就用它，否则用卡片风格的强调色。"""
    if sb["captions"].get("hl"):
        return sb["captions"]["hl"]
    try:
        th = theme.theme(sb.get("style"), sb["_base"], sb.get("brand"))
        return th.get("hl") if str(th.get("hl", "")).startswith("#") else th.get("accent")
    except (RuntimeError, KeyError):
        return None


def _abx(c) -> Tuple[float, float, float]:
    """剪辑段 → (起, 止, 倍速)。没有变速的段只有 (起, 止)，倍速是 1。"""
    return float(c[0]), float(c[1]), (float(c[2]) if len(c) > 2 else 1.0)


def _atempo(x: float) -> str:
    """变速的声音：atempo 每一级只接受 0.5～2，超出就串几级。倍速 1 回传空字串（和以前一样）。"""
    if abs(x - 1.0) < 1e-6:
        return ""
    out = []
    while x > 2.0:
        out.append("atempo=2.0")
        x /= 2.0
    while x < 0.5:
        out.append("atempo=0.5")
        x /= 0.5
    out.append("atempo=%.4f" % x)
    return "," + ",".join(out)


def _seek_inputs(cuts, source: str) -> List[str]:
    """每个剪辑段各开一次素材、从段头附近开始解码（-ss 放在 -i 前面＝精确跳转）。
    只解码用得到的部分：素材常有一半以上被剪掉，整支解码是渲染最花时间的一步。
    段数多（长片＋大量变速区间）时每个输入只给 2 个解码线程：上百个 4K 解码器各开满线程会撞到
    每进程线程上限，x264 开不起来（解码结果与线程数无关，画面逐位不变）。"""
    args: List[str] = []
    cap = ["-threads", "2"] if len(cuts) > 40 else []
    for c in cuts:
        a, b, _x = _abx(c)
        args += cap + ["-ss", "%.3f" % a, "-t", "%.3f" % (b - a + 1.0), "-i", source]
    return args


def hw_encoder() -> List[str]:
    """硬件编码：Mac 用 VideoToolbox；Windows 依次试 NVIDIA、Intel、AMD；都没有就用软件编码（快一点的预设）。"""
    if env.MAC:
        return ["-c:v", "h264_videotoolbox", "-q:v", "70", "-pix_fmt", "yuv420p"]
    for enc, extra in (("h264_nvenc", ["-cq", "21", "-preset", "p5"]), ("h264_qsv", ["-global_quality", "21"]),
                       ("h264_amf", ["-quality", "quality", "-qp_i", "20", "-qp_p", "22"])):
        p = subprocess.run([env.ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "color=s=64x64:d=0.1", "-c:v", enc,
                            "-f", "null", "-"], capture_output=True)
        if p.returncode == 0:
            return ["-c:v", enc] + extra + ["-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "17"]


def video_encoder(sb: dict, proxy: bool = False) -> List[str]:
    """成片的视频编码参数。封面帧（coverframe.py）用同一组参数编码，才能无损接在片头。"""
    if proxy:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "30"]
    if sb["output"].get("encoder") == "hw":   # 长片赶时间：Apple 硬件编码，快数倍、文件稍大、画质略低
        return hw_encoder()
    return ["-c:v", "libx264", "-preset", "slow", "-crf", "15"]


def frame_chain(w: int, h: int, framing: Optional[dict] = None, hdr: bool = False):
    """原片一帧 → 成片画幅的处理（HDR 转 SDR＋缩放裁切＋全局推近）。回传 (pre, fit)，渲染与封面共用。"""
    z = float((framing or {}).get("zoom", 1.0))
    if z > 1.0001:   # 全局推近（机位坐得远）：并进第一次编码，不多压一代
        cx, cy = float(framing.get("cx", 0.5)), float(framing.get("cy", 0.4))
        fit = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d:(iw-%d)*%.4f:(ih-%d)*%.4f"
               % (int(w * z) & ~1, int(h * z) & ~1, w, h, w, cx, h, cy))
    else:
        fit = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (w, h, w, h)
    # 先缩到成片尺寸再分给各段：素材常比成片大（手机 4K），在原尺寸上分 n 路裁切会慢好几倍
    pre = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
           "zscale=t=bt709:m=bt709:r=tv,format=yuv420p," if hdr else "")   # iPhone HLG／HDR10 → SDR bt709
    return pre, fit


def look_of(sb: dict) -> Optional[dict]:
    """画面调色设定：剪辑表的 "look"，没写就跟随卡片风格自带的 look（见 aaaai_editor/look.py）。"""
    from . import look
    th = None
    if sb.get("look") is None:
        try:
            th = theme.theme(sb.get("style"), sb.get("_base"), sb.get("brand"))
        except (RuntimeError, KeyError):
            th = None
    try:
        return look.resolve(sb, th)
    except ValueError as e:
        raise env.ToolError(str(e))


def _bokeh_matte(sb: dict, cuts, w: int, h: int, fps, work: str, length: float) -> Optional[str]:
    """背景虚化用的人像遮罩（整段）。没有人像分割、或这段几乎没有人，就回传 None（不虚化）。"""
    from . import matte
    try:
        f, _mw, _mh = matte.build(sb["source"], {"cuts": cuts, "framing": sb.get("framing"), "hdr": sb.get("_hdr", False)},
                                  (0.0, length), work, w, h, fps, "balanced", 0.35, "bokeh")
    except (env.ToolError, OSError) as e:
        print("（背景虚化跳过：%s）" % str(e).splitlines()[0][:80])
        return None
    if matte.coverage(f) < 0.02:
        print("（背景虚化跳过：这段几乎认不出人物，虚化会把整个画面糊掉）")
        return None
    try:
        return _dof_matte(f, _mw, _mh)
    except ImportError:
        print("（背景虚化跳过：需要 numpy——重跑安装器即可）")
        return None


def _dof_matte(f: str, mw: int, mh: int) -> str:
    """把人像遮罩改成「虚化遮罩」：认不出人的帧整张保持清楚（白），有人和没人之间用 0.3 秒渐变，不会忽糊忽清。
    实测：远景、人物太小或转身时，分割会有几帧整张全黑——直接拿来用，那几帧整个画面都会被当背景糊掉。"""
    import numpy as np
    out = os.path.join(os.path.dirname(f), "dof_" + os.path.basename(f).split("_", 1)[1])
    if os.path.isfile(out):
        return out
    fs = mw * mh

    def frames():
        p = subprocess.Popen([env.ffmpeg(), "-v", "error", "-i", f, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             stdout=subprocess.PIPE)
        while True:
            b = p.stdout.read(fs)
            if len(b) < fs:
                break
            yield np.frombuffer(b, np.uint8)
        p.stdout.close()
        p.wait()

    cov = np.array([fr.mean() / 255.0 for fr in frames()])
    if not len(cov):
        return f
    wgt = np.clip((cov - 0.015) / 0.03, 0.0, 1.0)
    k = 9   # 约 0.3 秒的移动平均
    wgt = np.convolve(np.pad(wgt, k // 2, mode="edge"), np.ones(k) / k, mode="valid")[:len(cov)]
    fps = subprocess.run([env.ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                          "-of", "csv=p=0", f], capture_output=True, text=True).stdout.strip() or "30"
    tmp = out + ".part.mkv"
    enc = subprocess.Popen([env.ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "%dx%d" % (mw, mh),
                            "-r", fps, "-i", "-", "-c:v", "ffv1", "-pix_fmt", "gray", tmp], stdin=subprocess.PIPE)
    for i, fr in enumerate(frames()):
        w_ = float(wgt[min(i, len(wgt) - 1)])
        enc.stdin.write((255.0 - w_ * (255.0 - fr.astype(np.float32))).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()
    os.replace(tmp, out)
    return out


def _video_base(cuts, w, h, fps, deep: bool, nframes: Optional[int] = None,
                framing: Optional[dict] = None, hdr: bool = False, seek_base: Optional[int] = None) -> str:
    """裁切拼接 + 统一画幅，产出 [base]。deep=True 时走 yuv444，卡片边缘不被色度下采样。

    nframes：分段渲染时把这一段锁成确定帧数。各段单独做 fps 重采样会各自取整，
    不锁帧数就会每个接缝少一帧，段数一多就累积成音画不同步。
    """
    n = len(cuts)
    pre, fit = frame_chain(w, h, framing, hdr)
    if seek_base is None:
        parts = ["[0:v]%s%s,split=%d%s" % (pre, fit, n, "".join("[s%d]" % i for i in range(n)))]
    else:   # 每段一个已跳转的输入（见 _seek_inputs）：时间从 0 起算
        parts = ["[%d:v]%s%s[s%d]" % (seek_base + i, pre, fit, i) for i in range(n)]
    for i, c in enumerate(cuts):
        # 每段先转到目标帧率再锁死帧数：不然每个剪辑点的取整误差会一路累积，
        # 长片到后面字幕就和画面对不上了
        a, b, x = _abx(c)
        k = max(1, int(round((b - a) / x * fps)))
        ta, tb = (a, b) if seek_base is None else (0.0, b - a)
        sp = "setpts=PTS-STARTPTS" if abs(x - 1.0) < 1e-6 else "setpts=(PTS-STARTPTS)/%.4f" % x   # 变速
        parts.append("[s%d]trim=start=%.3f:end=%.3f,%s,fps=%s,"
                     "tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=%d,"
                     "setpts=PTS-STARTPTS[v%d]" % (i, ta, tb, sp, fps, k, i))
    parts.append("%sconcat=n=%d:v=1:a=0[cat]" % ("".join("[v%d]" % i for i in range(n)), n))
    tail = "null"
    if nframes:
        # 先用克隆帧补足（源区间偶尔会短一帧），再裁到确定帧数
        tail = "tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=%d,setpts=PTS-STARTPTS" % nframes
    if deep:
        tail += ",format=yuv444p"
    parts.append("[cat]%s[base]" % tail)
    return ";".join(parts)


def denoise_filter(sb: dict) -> str:
    """降噪滤镜链。默认开标准档；storyboard 写 "denoise": false 关掉、"strong" 加强、数字＝降几 dB。
    先切掉 70Hz 以下的低频嗡声，再用 FFT 降噪：噪声底按这支素材实测的底噪设定，并持续追踪噪声变化。"""
    d = sb.get("denoise", True)
    if not d:
        return ""
    strong = d == "strong"
    nr = 20.0 if strong else (float(d) if isinstance(d, (int, float)) and not isinstance(d, bool) else 12.0)
    try:
        from . import audio
        floor = audio.envelope(sb["source"]).floor
    except env.ToolError:
        floor = -50.0
    # afftdn 的噪声门槛要比实测底噪（10ms RMS 的第 10 百分位）高 15～20dB 才抓得到噪声；
    # 实测：底噪 -47dB 的风扇声，门槛 -30、降 12dB → 底噪降到 -58dB，人声响度不变
    nf = max(-80.0, min(-20.0, floor + (20.0 if strong else 15.0)))
    return "highpass=f=70,afftdn=nr=%.1f:nf=%.1f" % (max(1.0, min(40.0, nr)), nf)


def _voice_graph(cuts, has_audio: bool = True, denoise: str = "", fps: float = 0.0) -> str:
    if not has_audio:   # 素材没有音轨（屏幕录制、动画片）：补一条等长静音，后面照常混配乐
        total = sum((_abx(c)[1] - _abx(c)[0]) / _abx(c)[2] for c in cuts)
        return "anullsrc=r=48000:cl=stereo,atrim=duration=%.3f[voice]" % total
    parts = []
    src = "[0:a]"
    if denoise:   # 整条音轨先降噪再切段：降噪器要连续的声音才估得准噪声
        parts.append("[0:a]%s,asplit=%d%s" % (denoise, len(cuts), "".join("[dn%d]" % i for i in range(len(cuts)))))
    for i, c in enumerate(cuts):
        a, b, x = _abx(c)
        d = (b - a) / x
        src = ("[dn%d]" % i) if denoise else "[0:a]"
        tempo = _atempo(x)
        if len(c) > 2:   # 有变速的片：每段声音补齐到和画面一样的整帧长度（atempo 尾巴会少几十毫秒），
            # 不然整片声音比画面短、封装时 -shortest 会把画面尾巴截掉几帧
            dq = max(1, round(d * fps)) / fps if fps else d
            tempo += ",apad=whole_dur=%.4f,atrim=end=%.4f" % (dq, dq)
            d = dq
        parts.append(src + "atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS%s,afade=t=in:d=%s,afade=t=out:st=%.3f:d=%s[a%d]"
                     % (a, b, tempo, FADE, max(0.0, d - FADE), FADE, i))
    n = len(cuts)
    parts.append("%sconcat=n=%d:v=0:a=1[voice]" % ("".join("[a%d]" % i for i in range(n)), n))
    return ";".join(parts)


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
                           sb["captions"].get("size_scale"), _hl_color(sb),
                           sb.get("_faces") if sb["captions"].get("avoid_face", True) else None, t0,
                           [(float(o["t"][0]), float(o["t"][1]), h * float(o.get("top", 0.34)),
                             h * (float(o.get("top", 0.34)) + float(o.get("height", 0.50))))
                            for o in sb.get("overlays") or []
                            if o.get("type") == "frame" and (o.get("bg") == "paper" or str(o.get("bg", "")).startswith("#"))],
                           sb["captions"].get("anim", "soft"), fps)
    zooms = sb.get("zooms") or []
    zoom_str = overlays.zoom_filter(zooms, w, h, fps) if zooms else None
    # 人像遮罩按「不带 format 的剪辑图」生成，成片改画质不会让遮罩缓存失效
    ov_inputs, assemble = overlays.build(sb, work, w, h, fps, source=sb["source"],
                                         base_graph={"cuts": cuts, "framing": sb.get("framing"),
                                                     "hdr": sb.get("_hdr", False)})
    seek_base = 1 + sum(g.count("-i") for g in ov_inputs)   # 各段跳转输入排在卡片素材之后
    parts = [_video_base(cuts, w, h, fps, bool(ov_inputs) and not proxy, nframes, sb.get("framing"),
                         sb.get("_hdr", False), seek_base)]
    cur = "base"
    if zoom_str:
        parts.append("[base]%s[zb]" % zoom_str)
        cur = "zb"
    trs = sb.get("_transitions") or []
    if trs:   # 甩镜转场：只动剪辑点前后那几帧
        from . import transitions
        tg = transitions.graph("[%s]" % cur, "[tr]", trs, w, h, fps, t0, (t1 - t0) if t1 is not None else None)
        if tg:
            parts.append(tg)
            cur = "tr"
    lk = look_of(sb)
    extra_inputs: List[str] = []
    if lk:   # 画面调色：在卡片与字幕之前（卡片、字幕不被调色；人像穿插抠出来的人也是调过色的）
        from . import look
        mlab = None
        length = (t1 - t0) if t1 is not None else (total or 0.0)
        if lk["bokeh"] > 0 and length > 0:
            mf = _bokeh_matte(sb, cuts, w, h, fps, work, length)
            if mf:
                mi = seek_base + len(cuts)
                extra_inputs = ["-i", os.path.relpath(mf, work)]
                m = "[%d:v]format=gray,fps=%s,scale=%d:%d,gblur=sigma=%.1f" % (mi, fps, w, h, max(1.5, min(w, h) / 360.0))
                if zoom_str:
                    m += "," + zoom_str   # 遮罩跟着底片一起推近
                parts.append(m + "[lkm]")
                mlab = "[lkm]"
        parts.append(look.graph(lk, "[%s]" % cur, "[lk]", w, h, matte=mlab))
        cur = "lk"
    pfx = sb.get("_postfx") or []
    if pfx:   # 整屏特效（手机框、前后对比、滑下一支、底片感）：调色之后、卡片之前
        from . import postfx
        pg, px_in = postfx.graph("[%s]" % cur, "[pfx]", pfx, w, h, fps, t0, (t1 - t0) if t1 is not None else None,
                                 sb["_base"], work, seek_base + len(cuts) + extra_inputs.count("-i"))
        if pg:
            parts.append(pg)
            extra_inputs += px_in
            cur = "pfx"
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
    args += _seek_inputs(cuts, sb["source"])
    args += extra_inputs
    venc = video_encoder(sb, proxy)
    prog = []
    if os.environ.get("AAAAI_PROGRESS_DIR"):   # Studio 显示真实进度用：每段写一个进度文件（不影响输出）
        prog = ["-progress", os.path.join(os.environ["AAAAI_PROGRESS_DIR"], "p_%09d.txt" % int(round(t0 * 1000)))]
    env.run(args + prog + ["-filter_complex", ";".join(parts), "-map", "[vout]", "-an"]
            + venc + ["-movflags", "+faststart", out], cwd=work)


def _prepare(sb_path: str, proxy: bool = False) -> dict:
    """渲染前的共同准备：读剪辑表、算尺寸、HDR、转场、避脸、字幕事件。整片渲染与「渲染一段」共用。"""
    sb = load_storyboard(sb_path)
    cuts: List = [tuple(c) for c in sb["cuts"]]
    if not cuts:
        raise env.ToolError("storyboard.cuts 是空的")
    out = sb["output"]
    w, h, fps = int(out["width"]), int(out["height"]), out["fps"]
    tl = Timeline(cuts, fps, sb.get("speed"))
    cuts = tl.segments()   # 有变速：段在变速边界切开、带倍速；没有就和以前完全一样
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

    from . import transitions as _tr
    sb["_transitions"] = _tr.resolve(sb, tl)   # 转场吸附到剪辑点（成片时间）
    from . import postfx, triggers
    triggers.expand(sb, tl)   # 关键词触发：讲到哪个词，卡片／特效就在那个时间出现
    sb["_postfx"] = postfx.items(sb)
    lk = look_of(sb)
    if lk:
        print("🎞 画面调色：%s（强度 %.0f%%%s）" % (lk["name"], lk["strength"] * 100, "，背景虚化" if lk["bokeh"] > 0 else ""))

    # ---- 字幕事件（按整片时间轴算一次；分段时再平移）----
    cap_events = None
    cap = sb["captions"]
    sb["_faces"] = None
    cards_face = bool(sb.get("overlays")) and sb.get("avoid_face", True) is not False
    if (cap.get("enabled") and cap.get("avoid_face", True)) or cards_face:   # 字幕／卡片避脸（需要人像分割；没有就跳过）
        try:
            from . import faces
            sb["_faces"] = faces.track(sb, tl, int(out["width"]), int(out["height"]))
            moved = sum(1 for _t, f in sb["_faces"] if f and f[1] > 0.62)
            if moved:
                print("🙂 字幕避脸：有 %d 个时间点脸的位置偏低，那几句字幕会移到下巴下面" % moved)
        except (env.ToolError, OSError) as e:
            print("（字幕避脸跳过：%s）" % str(e).splitlines()[0][:80])
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

    return {"sb": sb, "cuts": cuts, "out": out, "w": w, "h": h, "fps": fps, "tl": tl, "work": work,
            "ff": ff, "info": info, "cap_events": cap_events}


def render(sb_path: str, only: Optional[str] = None, proxy: bool = False) -> str:
    c = _prepare(sb_path, proxy)
    sb, cuts, out, w, h, fps = c["sb"], c["cuts"], c["out"], c["w"], c["h"], c["fps"]
    tl, work, ff, info, cap_events = c["tl"], c["work"], c["ff"], c["info"], c["cap_events"]

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
    dn = denoise_filter(sb) if info.get("has_audio", True) else ""
    if dn:
        print("🎙 降噪：%s" % dn.split(",")[-1])
    from . import sfx as sfx_mod
    fx_items = [x for x in sfx_mod.collect(sb) if x[0] < tl.duration]
    if fx_items:
        print("🔔 音效 %d 个" % len(fx_items))
    audio, rep = loud.master(sb["source"], _voice_graph(cuts, info.get("has_audio", True), dn, fps), tl.duration, work, target,
                             music=mu, fade=fade, sfx=fx_items,
                             sfx_gain=sfx_mod.gain_for((sb.get("sfx_level") or None)))
    print("🔊 响度 %.1f LUFS・真峰值 %.1f dBTP（人声 %+.1fdB%s，迭代 %d 次）"
          % (rep["I"], rep["TP"], rep["voice_gain"],
             ("、配乐 %+.1fdB" % rep["music_gain"]) if mu else "", rep["iters"]))
    if only == "audio":
        return audio

    # ---- 封装 ----
    env.run([ff, "-y", "-v", "error", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy",
             "-movflags", "+faststart", "-shortest", out["path"]])
    if not proxy:   # 正式成片：再放一份到「成品」文件夹，不用进项目里找
        from . import config
        stem = os.path.splitext(os.path.basename(out["path"]))[0]   # final.mp4 → 不加；final_1080x1350 → -1080x1350
        dst = config.export(out["path"], sb["_base"], "" if stem == "final" else "-" + stem.replace("final_", "", 1))
        if dst:
            print("📦 成品：%s" % dst)
        from . import coverframe
        coverframe.after_render(sb, out["path"])
    return out["path"]


def _studio_dir(work: str) -> str:
    d = os.path.join(work, "studio")
    os.makedirs(d, exist_ok=True)
    return d


def master_audio_cached(c: dict) -> str:
    """整片混音（人声降噪＋配乐闪避＋音效＋响度），按会影响声音的设定做缓存。
    「渲染一段」从它截取，所以单段听到的就是成片的声音。在 work/studio/audio 里做，不会和正式渲染互相覆盖。"""
    from . import loud, sfx as sfx_mod
    sb, cuts, tl, info, fps = c["sb"], c["cuts"], c["tl"], c["info"], c["fps"]
    mu = sb.get("music")
    fade = float((sb.get("ending") or {}).get("fade", 0) or 0)
    dn = denoise_filter(sb) if info.get("has_audio", True) else ""
    fx_items = [x for x in sfx_mod.collect(sb) if x[0] < tl.duration]
    st = os.stat(sb["source"])
    key = hashlib.sha1(json.dumps([cuts, mu, fade, dn, fx_items, sb["loudness"], sb.get("sfx_level"),
                                   st.st_size, st.st_mtime_ns], sort_keys=True, default=str).encode()).hexdigest()[:16]
    d = os.path.join(_studio_dir(c["work"]), "audio")
    os.makedirs(d, exist_ok=True)
    cached = os.path.join(d, "mix_%s.m4a" % key)
    if os.path.isfile(cached):
        return cached
    audio, _rep = loud.master(sb["source"], _voice_graph(cuts, info.get("has_audio", True), dn, fps), tl.duration, d,
                              float(sb["loudness"]), music=mu, fade=fade, sfx=fx_items,
                              sfx_gain=sfx_mod.gain_for((sb.get("sfx_level") or None)))
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", audio, "-c:a", "aac", "-b:a", "128k", cached])
    return cached


def render_range(sb_path: str, a: float, b: float, out_path: Optional[str] = None) -> str:
    """只渲染成片时间 [a, b] 这一段（预览画质：卡片、字幕、推近、人像都照正式规则；声音截自整片混音）。
    给 Studio「渲染这一段」用；不影响整片渲染。"""
    c = _prepare(sb_path, proxy=True)
    sb, w, h, fps, tl, work = c["sb"], c["w"], c["h"], c["fps"], c["tl"], c["work"]
    a = max(0.0, min(float(a), tl.duration - 1.0 / fps))
    b = max(a + 1.0 / fps, min(float(b), tl.duration))
    nf = max(1, int(round(b * fps)) - int(round(a * fps)))
    sd = _studio_dir(work)
    tag = "range_%d_%d" % (int(round(a * 1000)), int(round(b * 1000)))
    vid = os.path.join(sd, tag + "_v.mp4")
    src_end = min(tl.duration, b + 3.0 / fps)
    _render_pass(segment.window(sb, a, b), tl.source_ranges(a, src_end), c["cap_events"], a, w, h, fps,
                 work, vid, True, "rg", b, nf, tl.duration)
    audio = master_audio_cached(c)
    out_path = out_path or os.path.join(sd, tag + ".mp4")
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", vid, "-ss", "%.3f" % a, "-t", "%.3f" % (b - a), "-i", audio,
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", "-shortest", out_path])
    try:
        os.remove(vid)
    except OSError:
        pass
    return out_path


def proxy_path(sb_path: str, height: int = 960, sb: Optional[dict] = None, info: Optional[dict] = None) -> str:
    """代理影片的路径（不产生；用来判断是否已经有了）。"""
    sb = sb or load_storyboard(sb_path)
    out = sb["output"]
    W, H = int(out["width"]), int(out["height"])
    ph = max(2, int(height) & ~1)
    pw = max(2, int(round(W * ph / float(H))) & ~1)
    info = info if info is not None else env.probe(sb["source"])
    st = os.stat(sb["source"])
    key = hashlib.sha1(json.dumps([sb["source"], st.st_size, st.st_mtime_ns, pw, ph, sb.get("framing"),
                                   bool(info.get("hdr"))], sort_keys=True).encode()).hexdigest()[:16]
    return os.path.join(_studio_dir(os.path.join(sb["_base"], "work")), "proxy_%s.mp4" % key)


def proxy_source(sb_path: str, height: int = 960) -> str:
    """Studio 播放用的代理影片：整支原片转成低分辨率（构图与成片相同：同样的推近与裁切），
    界面按剪辑点跳着播，所以改剪辑点不必重新转。按原片与构图设定缓存。"""
    sb = load_storyboard(sb_path)
    out = sb["output"]
    W, H = int(out["width"]), int(out["height"])
    ph = max(2, int(height) & ~1)
    pw = max(2, int(round(W * ph / float(H))) & ~1)
    info = env.probe(sb["source"])
    p = proxy_path(sb_path, height, sb, info)
    if os.path.isfile(p):
        return p
    pre, fit = frame_chain(pw, ph, sb.get("framing"), bool(info.get("hdr")))
    args = [env.ffmpeg(), "-y", "-v", "error", "-i", sb["source"], "-vf", pre + fit + ",format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-g", "15"]
    args += (["-c:a", "aac", "-b:a", "96k"] if info.get("has_audio", True) else ["-an"])
    tmp = p + ".part.mp4"
    env.run(args + ["-movflags", "+faststart", tmp])
    os.replace(tmp, p)
    return p


def preview_subs(sb_path: str, t_from: Optional[float] = None, t_to: Optional[float] = None) -> str:
    """只烧字幕的低画质预览（480 宽、ultrafast、无卡片无推近、不做响度迭代）。
    频道教训（ep05）：为了确认字幕对时重渲完整成片 5 次＝75 分钟；这支约一分钟就能给用户看。"""
    sb = load_storyboard(sb_path)
    fps = sb["output"]["fps"]
    tl_full = Timeline([tuple(c) for c in sb["cuts"]], fps, sb.get("speed"))
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
                           cap.get("margin_v"), cap.get("size_scale"), _hl_color(sb),
                           anim=cap.get("anim", "soft"))
    info = env.probe(sb["source"])
    g = _video_base(cuts, w, h, fps, False, None, sb.get("framing"), bool(info.get("hdr")))
    lk = look_of(sb)
    from . import look as _look
    g += ";[base]%s%sformat=yuv420p[v]" % ((_look.simple(lk) + ",") if lk else "",
                                         ("subtitles=filename=%s," % ass) if ass else "")
    g += ";" + _voice_graph(cuts, info.get("has_audio", True), denoise_filter(sb) if info.get("has_audio", True) else "", fps) \
        + ";[voice]aformat=channel_layouts=stereo[a]"
    out = os.path.splitext(sb["output"]["path"])[0] + "_subs.mp4"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", sb["source"], "-filter_complex", g, "-map", "[v]",
             "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-c:a", "aac",
             "-b:a", "96k", "-movflags", "+faststart", out], cwd=work)
    return out
