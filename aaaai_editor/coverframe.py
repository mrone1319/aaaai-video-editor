"""封面帧版成片：把封面插在片头 2 帧（30fps 约 0.067 秒），另存一份 final_coverframe.mp4。

为什么：微信／朋友圈转发、WhatsApp、Telegram、LinkedIn、X 的预览图，和信息流自动播放前那一闪，
很多是直接截第一帧；能自己上传封面的平台（YouTube、B 站、小红书、抖音）用原版 final.mp4 就好。

做法：插入不是盖住——画面多 2 帧封面、声音前面补同样长的静音，字幕卡片整体往后挪，对时完全不变。
封面那 2 帧用和成片相同的编码参数单独编码，再无损接到片头（不必整支重压）；接完逐帧验证，
万一接不起来（例如硬件编码的参数对不上）就改成整支重新编码，慢但一定对。

剪辑表写法："cover_frame": "both"（原版＋封面帧版都出）／"off"（只出原版）。没写＝只出原版。
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Optional, Tuple

from . import env

FRAMES = 2


def enabled(sb: dict) -> bool:
    v = sb.get("cover_frame")
    return v is True or v == "both"


def out_path(final: str) -> str:
    stem, ext = os.path.splitext(final)
    return stem + "_coverframe" + ext


def _probe(path: str) -> dict:
    out = subprocess.run([env.ffprobe(), "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate,time_base,nb_frames,color_space,color_transfer,"
                          "color_primaries,color_range,bit_rate", "-of", "json", path],
                         capture_output=True, text=True).stdout
    st = json.loads(out or "{}").get("streams") or []
    v = next((s for s in st if s.get("codec_type") == "video"), None)
    a = next((s for s in st if s.get("codec_type") == "audio"), None)
    if not v:
        raise env.ToolError("读不到成片的画面：%s" % path)
    return {"v": v, "a": a}


def _fps(v: dict) -> float:
    n, d = (v.get("r_frame_rate") or "30/1").split("/")
    return float(n) / float(d or 1)


def cover_for(final: str, w: int, h: int) -> str:
    return os.path.join(os.path.dirname(final), "cover_%dx%d.png" % (w, h))


def _frames(path: str) -> int:
    out = subprocess.run([env.ffprobe(), "-v", "error", "-count_packets", "-select_streams", "v:0",
                          "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return int(out or 0)


def _first_frame_diff(path: str, cover: str, w: int, h: int) -> float:
    """片头第一帧和封面的平均差（0–255）。缩成 64×114 比，编码误差约 1–3。"""
    sw, sh = 64, max(2, int(round(64 * h / float(w))))
    def gray(args):
        return subprocess.run([env.ffmpeg(), "-v", "error"] + args + ["-frames:v", "1", "-vf", "scale=%d:%d" % (sw, sh),
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    a, b = gray(["-i", path]), gray(["-i", cover])
    if not a or len(a) != len(b):
        return 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / float(len(a))


def _verify(out: str, cover: str, n_body: int, w: int, h: int) -> Tuple[bool, str]:
    p = subprocess.run([env.ffmpeg(), "-v", "error", "-i", out, "-f", "null", "-"], capture_output=True, text=True)
    if p.returncode != 0 or p.stderr.strip():
        return False, "解码有错误：%s" % p.stderr.strip()[:200]
    n = _frames(out)
    if n != n_body + FRAMES:
        return False, "帧数不对（%d，应为 %d）" % (n, n_body + FRAMES)
    d = _first_frame_diff(out, cover, w, h)
    if d > 8.0:
        return False, "第一帧不是封面（差 %.1f）" % d
    return True, ""


def build(sb: dict, final: str) -> str:
    """final.mp4 ＋ 同画幅封面 → final_coverframe.mp4。回传输出路径。"""
    from . import render
    info = _probe(final)
    v, a = info["v"], info["a"]
    w, h = int(v["width"]), int(v["height"])
    cover = cover_for(final, w, h)
    if not os.path.isfile(cover):
        raise env.ToolError("还没有 %d×%d 的封面（先跑 aaaai-editor cover）" % (w, h))
    fps = _fps(v)
    work = os.path.join(sb["_base"], "work", "coverframe")
    os.makedirs(work, exist_ok=True)
    ff = env.ffmpeg()
    tags = ["-colorspace", v.get("color_space") or "bt709", "-color_primaries", v.get("color_primaries") or "bt709",
            "-color_trc", v.get("color_transfer") or "bt709", "-color_range", v.get("color_range") or "tv"]
    tb = (v.get("time_base") or "1/15360").split("/")[-1]
    venc = render.video_encoder(sb)
    sc = "scale=%d:%d:out_color_matrix=bt709:out_range=tv,format=yuv420p" % (w, h)
    head = os.path.join(work, "head.mp4")
    env.run([ff, "-y", "-v", "error", "-loop", "1", "-framerate", "%g" % fps, "-i", cover, "-frames:v", str(FRAMES),
             "-vf", sc, "-an"] + venc + tags + ["-video_track_timescale", tb, head])
    body = os.path.join(work, "body.mp4")
    env.run([ff, "-y", "-v", "error", "-i", final, "-map", "0:v", "-c", "copy", body])
    with open(os.path.join(work, "list.txt"), "w", encoding="utf-8") as f:
        f.write("file 'head.mp4'\nfile 'body.mp4'\n")
    vid = os.path.join(work, "v.mp4")
    env.run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", vid], cwd=work)
    aud = None
    if a:   # 声音前面补同样长的静音：字幕、卡片、口型全部照原样往后挪
        aud = os.path.join(work, "a.m4a")
        ms = FRAMES / fps * 1000.0
        env.run([ff, "-y", "-v", "error", "-i", final, "-vn", "-af", "adelay=delays=%.3f:all=1" % ms,
                 "-c:a", "aac", "-b:a", "192k", aud])
    out = out_path(final)
    tmp = out + ".part.mp4"

    def mux(video: str) -> None:
        args = [ff, "-y", "-v", "error", "-i", video] + (["-i", aud] if aud else [])
        args += ["-map", "0:v"] + (["-map", "1:a"] if aud else []) + ["-c", "copy", "-movflags", "+faststart", tmp]
        env.run(args)

    mux(vid)
    n_body = _frames(final)
    ok, why = _verify(tmp, cover, n_body, w, h)
    if not ok:   # 无损接不起来：整支重新编码（慢，但一定对）
        print("（封面帧无损拼接没过验证：%s；改成整支重新编码）" % why)
        env.run([ff, "-y", "-v", "error", "-loop", "1", "-framerate", "%g" % fps, "-t", "%.4f" % (FRAMES / fps), "-i", cover,
                 "-i", final, "-filter_complex",
                 "[0:v]%s,fps=%g,trim=end_frame=%d,setpts=PTS-STARTPTS[c];[1:v]format=yuv420p,setpts=PTS-STARTPTS[b];"
                 "[c][b]concat=n=2:v=1:a=0[o]" % (sc, fps, FRAMES), "-map", "[o]", "-an"] + venc + tags + [vid])
        mux(vid)
        ok, why = _verify(tmp, cover, n_body, w, h)
        if not ok:
            raise env.ToolError("封面帧版做不出来：%s" % why)
    os.replace(tmp, out)
    return out


def export_suffix(final: str) -> str:
    stem = os.path.splitext(os.path.basename(final))[0]
    return ("" if stem == "final" else "-" + stem.replace("final_", "", 1)) + "-封面帧"


def make(sb: dict, final: str) -> Optional[str]:
    """出封面帧版并复制到「成品」文件夹；回传输出路径。"""
    from . import config
    out = build(sb, final)
    print("🖼 封面帧版：%s（片头 %d 帧封面；发微信／朋友圈等会截第一帧当预览的地方用）" % (out, FRAMES))
    dst = config.export(out, sb["_base"], export_suffix(final))
    if dst:
        print("📦 成品：%s" % dst)
    return out


def after_render(sb: dict, final: str) -> None:
    """整片渲染完：选了出封面帧版、封面也已经有了，就跟着重做（封面没做就提示，做完封面会自动补）。"""
    if not enabled(sb):
        return
    try:
        info = _probe(final)
        w, h = int(info["v"]["width"]), int(info["v"]["height"])
        if not os.path.isfile(cover_for(final, w, h)):
            print("🖼 封面帧版：封面还没做，做完封面（aaaai-editor cover）会自动出")
            return
        make(sb, final)
    except env.ToolError as e:
        print("⚠️ 封面帧版没做成：%s" % str(e).splitlines()[0])
