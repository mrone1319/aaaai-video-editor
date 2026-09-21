"""外部工具的定位与体检：ffmpeg / ffprobe / whisper-cli / 模型 / 字体。"""
from __future__ import annotations

import glob
import json
import re
import os
import shutil
import subprocess
from functools import lru_cache
from typing import List, Optional, Sequence


class ToolError(RuntimeError):
    pass


def run(cmd: Sequence[str], cwd: Optional[str] = None, capture: bool = True) -> subprocess.CompletedProcess:
    """执行外部命令；失败时带上 stderr 尾部抛出，方便定位。"""
    p = subprocess.run(list(cmd), cwd=cwd, stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None, text=True)
    if p.returncode != 0:
        tail = (p.stderr or "")[-1500:]
        raise ToolError("命令失败（%d）：%s\n%s" % (p.returncode, " ".join(cmd[:4]) + " …", tail))
    return p


def _has_filter(ffmpeg: str, name: str) -> bool:
    out = subprocess.run([ffmpeg, "-hide_banner", "-filters"], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True).stdout
    return (" %s " % name) in out


@lru_cache(maxsize=1)
def ffmpeg() -> str:
    """优先 AAAAI_EDITOR_FFMPEG；否则选第一个带 libass(subtitles 滤镜) 的 ffmpeg。"""
    cands: List[str] = []
    if os.environ.get("AAAAI_EDITOR_FFMPEG"):
        cands.append(os.environ["AAAAI_EDITOR_FFMPEG"])
    cands += ["/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg", "/usr/local/opt/ffmpeg-full/bin/ffmpeg"]
    w = which("ffmpeg")
    if w:
        cands.append(w)
    for c in cands:
        if os.path.isfile(c) and _has_filter(c, "subtitles"):
            return c
    raise ToolError("找不到带 libass 的 ffmpeg（需要 subtitles 滤镜）。安装：brew install ffmpeg-full，"
                    "或设 AAAAI_EDITOR_FFMPEG=/path/to/ffmpeg")


def ffprobe() -> str:
    f = ffmpeg()
    sibling = os.path.join(os.path.dirname(f), "ffprobe")
    if os.path.isfile(sibling):
        return sibling
    w = which("ffprobe")
    if not w:
        raise ToolError("找不到 ffprobe")
    return w


BREW_BINS = ["/opt/homebrew/bin", "/usr/local/bin"]   # 从 GUI／MCP 启动时 PATH 很短，Homebrew 目录要自己找


def which(name: str) -> Optional[str]:
    w = shutil.which(name)
    if w:
        return w
    for d in BREW_BINS:
        c = os.path.join(d, name)
        if os.access(c, os.X_OK):
            return c
    return None


def whisper_cli() -> str:
    w = os.environ.get("AAAAI_EDITOR_WHISPER") or which("whisper-cli")
    if not w:
        raise ToolError("找不到 whisper-cli。安装：brew install whisper-cpp（或重跑安装器）")
    return w


MIN_MODEL_BYTES = 50 * 1024 * 1024   # 小于这个多半是下载中断的半截文件


def whisper_model(lang: str = "auto") -> str:
    """挑模型：大的优先；只认完整文件；非英文不选 *.en（英文专用模型）。"""
    from . import config
    m = os.environ.get("AAAAI_EDITOR_WHISPER_MODEL")
    if m and os.path.isfile(m):
        return m
    pats = [os.path.join(config.HOME, "models", "ggml-*.bin"),
            os.path.expanduser("~/.aaaai-editor/models/ggml-*.bin"),
            os.path.expanduser("~/.cache/*/models/ggml-*.bin"),
            os.path.expanduser("~/.cache/whisper*/ggml-*.bin"),
            "/opt/homebrew/share/whisper*/ggml-*.bin"]
    found: List[str] = []
    for p in pats:
        found += [f for f in glob.glob(p) if f not in found and os.path.getsize(f) >= MIN_MODEL_BYTES]
    if lang != "en":
        found = [f for f in found if not re.search(r"\.en(\.|-|$)", os.path.basename(f)[:-4])]
    if not found:
        raise ToolError("找不到 whisper 模型（ggml-*.bin）。设 AAAAI_EDITOR_WHISPER_MODEL=/path/to/ggml-medium.bin")
    for pref in ("large", "medium", "small", "base"):
        for f in found:
            if pref in os.path.basename(f):
                return f
    return found[0]


def probe(path: str) -> dict:
    p = run([ffprobe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    j = json.loads(p.stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    info = {"duration": float(j["format"].get("duration", 0)), "has_audio": a is not None,
            "has_video": v is not None}
    if v:
        num, den = (v.get("r_frame_rate") or "30/1").split("/")
        w, h = int(v["width"]), int(v["height"])
        rot = 0
        for sd in v.get("side_data_list") or []:
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
        rot = rot or int(float((v.get("tags") or {}).get("rotate", 0) or 0))
        if abs(rot) % 180 == 90:   # 手机竖拍：像素是横的、靠旋转标记显示成竖的（ffmpeg 解码时会自动转正）
            w, h = h, w
        info.update(width=w, height=h, fps=float(num) / float(den or 1) if float(num) else 30.0, rotation=rot,
                    hdr=v.get("color_transfer") in ("arib-std-b67", "smpte2084"),
                    ten_bit="10" in (v.get("pix_fmt") or ""))
    return info


CJK_FONTS = ["PingFang SC", "Heiti SC", "STHeiti", "Noto Sans CJK SC", "Noto Sans SC", "Arial Unicode MS"]


def find_font() -> str:
    """用 fc-list 找第一个可用的中文字体名（找不到就交给 libass 自己回退）。"""
    fc = shutil.which("fc-list")
    if fc:
        out = subprocess.run([fc, ":", "family"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True).stdout
        for f in CJK_FONTS:
            if f in out:
                return f
    return CJK_FONTS[0]


def doctor() -> int:
    ok = True

    def line(good: bool, name: str, detail: str):
        nonlocal ok
        ok = ok and good
        print("%s %-14s %s" % ("✅" if good else "❌", name, detail))

    for name, fn in (("ffmpeg(libass)", ffmpeg), ("ffprobe", ffprobe), ("whisper-cli", whisper_cli),
                     ("whisper 模型", whisper_model)):
        try:
            line(True, name, fn())
        except ToolError as e:
            line(False, name, str(e))
    line(True, "字幕字体", find_font())
    from . import zh as _zh
    line(_zh.available(), "繁→简(OpenCC)", "可选；没有会降低对齐／体检的命中率" if not _zh.available() else "")
    try:
        from . import theme as _th
        line(True, "卡片中文字体", _th.cjk_font())
        line(True, "卡片数字字体", _th.num_font())
    except Exception as e:  # 字体缺失不影响转录／剪辑，只影响卡片
        line(False, "卡片字体", str(e))
    try:
        from . import matte as _mt
        line(True, "人像去背", _mt.helper())
    except Exception as e:  # 只影响 behind_subject／cutout
        line(False, "人像去背", str(e))
    try:
        f = ffmpeg()
        for flt in ("loudnorm", "sidechaincompress", "subtitles", "drawtext", "zoompan", "overlay"):
            line(_has_filter(f, flt), "滤镜 " + flt, "")
    except ToolError:
        pass
    return 0 if ok else 1
