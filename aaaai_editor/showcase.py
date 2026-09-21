"""风格总览：每套风格用真实管线渲染一帧（标题＋人名条＋标签），拼成一张对照表。"""
from __future__ import annotations

import json
import os
import shutil
from typing import List, Optional

from . import env, render, theme

CACHE = os.path.expanduser("~/.cache/aaaai-editor/showcase")


def _bg(path: str, w: int, h: int) -> None:
    if os.path.isfile(path):
        return
    # 中性渐变 + 几块色块：看得出底板透明度与投影
    env.run([env.ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i",
             "gradients=s=%dx%d:c0=0x2f3d4c:c1=0x9a7c62:x0=0:y0=0:x1=%d:y1=%d:d=3:r=30" % (w, h, w, h),
             "-vf", "drawbox=x=0:y=%d:w=%d:h=%d:color=0xd9c7a8@0.55:t=fill,"
                    "drawbox=x=%d:y=%d:w=%d:h=%d:color=0x1f6f78@0.55:t=fill"
                    % (h * 0.42, w * 0.45, h * 0.30, w * 0.55, h * 0.12, w * 0.40, h * 0.22),
             "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", path])


def run(out: Optional[str] = None, names: Optional[List[str]] = None, base_dir: Optional[str] = None) -> str:
    os.makedirs(CACHE, exist_ok=True)
    W, H = 1080, 1920
    bg = os.path.join(CACHE, "bg.mp4")
    _bg(bg, W, H)
    names = names or theme.list_themes(base_dir, usable_only=True)
    frames = []
    for n in names:
        d = os.path.join(CACHE, n)
        os.makedirs(d, exist_ok=True)
        if base_dir and os.path.isdir(os.path.join(base_dir, "themes")):  # 自定义风格也能进总览
            shutil.rmtree(os.path.join(d, "themes"), ignore_errors=True)
            shutil.copytree(os.path.join(base_dir, "themes"), os.path.join(d, "themes"))
        sb = {"version": 1, "source": bg, "cuts": [[0, 2.5]], "style": n,
              "output": {"width": W, "height": H, "fps": 30, "path": "out/%s.mp4" % n},
              "captions": {"enabled": False}, "segment": {"enabled": False},
              "overlays": [   # 按真实口播用法：上方标题、下方人名条、右上角标签
                  {"type": "title", "t": [0, 2.5], "kicker": n.upper(), "text": "%s **风格**" % n,
                   "sub": theme.theme(n, base_dir)["desc"], "anim": "fade"},
                  {"type": "lower_third", "t": [0, 2.5], "name": "你的名字", "role": "人名条 · 自我介绍",
                   "anim": "fade"},
                  {"type": "stamp", "t": [0, 2.5], "text": "LIVE", "icon": "fire", "pos": "top_right",
                   "anim": "fade"},
              ]}
        p = os.path.join(d, "storyboard.json")
        json.dump(sb, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        v = render.render(p, only="video", proxy=True)
        f = os.path.join(d, "frame.png")
        env.run([env.ffmpeg(), "-y", "-v", "error", "-ss", "1.6", "-i", v, "-frames:v", "1", f])
        frames.append(f)
    cols = 3
    while len(frames) % cols:
        frames.append(frames[-1])  # 补齐最后一行（重复最后一格）
    out = os.path.abspath(out or "showcase.png")
    rows = len(frames) // cols
    args = [env.ffmpeg(), "-y", "-v", "error"]
    for f in frames:
        args += ["-i", f]
    g = []
    for r in range(rows):
        g.append("%shstack=inputs=%d[r%d]" % ("".join("[%d:v]" % (r * cols + c) for c in range(cols)), cols, r))
    g.append(("%svstack=inputs=%d[o]" % ("".join("[r%d]" % r for r in range(rows)), rows)) if rows > 1
             else "[r0]null[o]")
    env.run(args + ["-filter_complex", ";".join(g), "-map", "[o]", "-frames:v", "1", out])
    return out
