"""图卡：把片子里已经排好的卡片，单独出成静态图（发小红书／IG 图文用）。

和封面不一样：封面是整支片的门面（只有一张，固定两种尺寸）；图卡是把片中的数据卡、清单卡、
金句卡、流程卡复用成图文轮播，一支片可以出好几张，版式和成片完全一致。

背景可选：原片干净帧（默认，压暗一点托住文字）、模糊帧、纯色底。
尺寸：1080×1350（默认，小红书／IG）、1080×1080（方版）、1080×1920（直版）。
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple

from . import cards, config, cover, draw, env, fonts, icons as icons_mod, richtext, theme

SIZES = {"1350": (1080, 1350), "1080": (1080, 1080), "1920": (1080, 1920)}
# 能出图卡的卡片：有内容、值得单独看的那几种（接管框、B-roll、装饰类不出）
CARD_TYPES = ("title", "stat", "bullets", "quote", "rows", "compare", "icons", "step", "text",
              "gauge", "rank", "timeline", "rating")


def listing(sb: dict) -> List[dict]:
    """可以出图卡的卡片（按时间排序），给 CLI 列清单和挑选用。"""
    out = []
    for i, ov in enumerate(sb.get("overlays") or []):
        if ov.get("_aux") or ov.get("_raw"):
            continue
        if ov.get("type") in CARD_TYPES and (ov.get("text") or ov.get("items") or ov.get("value") is not None
                                             or ov.get("title") or ov.get("rows") or ov.get("groups")):
            out.append(dict(ov, _i=i))
    out.sort(key=lambda o: float(o["t"][0]))
    return out


def _label(ov: dict) -> str:
    t = ov.get("text") or ov.get("title") or ov.get("label") or ""
    if ov.get("type") == "stat" and ov.get("value") is not None:
        t = "%s%s %s" % (ov["value"], ov.get("unit") or ov.get("suffix") or "", ov.get("label") or "")
    if ov.get("items"):
        t = t or "、".join(str(x if not isinstance(x, dict) else x.get("text", "")) for x in ov["items"][:2])
    return (t or ov.get("type", ""))[:22]


def _bg(sb: dict, ov: dict, W: int, H: int, work: str, mode: str, th: dict) -> str:
    """图卡背景：原片干净帧／模糊帧／纯色底。"""
    ff = env.ffmpeg()
    out = os.path.join(work, "cardpic_bg.png")
    if mode in ("black", "white"):   # 纯黑／纯白底：两张对比算出透明度（见 card_png）
        env.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=%s:s=%dx%d" % (mode, W, H),
                 "-frames:v", "1", "-update", "1", out])
        return out
    if mode == "solid":
        pl = th["plate"][-1] if isinstance(th["plate"], (list, tuple)) else th["plate"]
        env.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=%s:s=%dx%d" % (pl, W, H),
                 "-frames:v", "1", "-update", "1", out])
        return out
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    frame = cover.clean_frame(sb, min(t1 - 0.05, t0 + 0.6), W, H, os.path.join(work, "cardpic_frame.png"))
    vf = "eq=brightness=-0.16:saturation=0.92"
    if mode == "blur":
        vf = "gblur=sigma=%d," % max(8, int(W * 0.022)) + vf
    env.run([ff, "-v", "error", "-y", "-i", frame, "-vf", vf, "-frames:v", "1", "-update", "1", out])
    return out


def one(sb: dict, ov: dict, W: int, H: int, work: str, bg_mode: str, out_path: str) -> str:
    """排一张图卡：底板＋文字＋图标，落定状态（不带动画），直接出 PNG。"""
    th = theme.theme(ov.get("style") or sb.get("style"), sb.get("_base"), sb.get("brand"))
    fps = float(sb["output"]["fps"])
    still = dict(ov, anim="fade", t=[0.0, 9.0], sparkle=False, float=False)
    L = cards.layout(still, th, W, H, fps)
    bg = _bg(sb, ov, W, H, work, bg_mode, th)

    inputs: List[List[str]] = [["-loop", "1", "-t", "1", "-framerate", "10", "-i", os.path.relpath(bg, work)]]
    chain: List[Tuple[str, int, int]] = []     # (输入序号占位, x, y)
    loose = list(L.get("icons") or [])
    p = L.get("plate")
    if p:
        spec = {k: p[k] for k in ("w", "h", "radius", "fill", "alpha", "border", "shadow")}
        for k in ("scrim", "sheen", "pattern", "topbar", "corners"):
            if p.get(k):
                spec[k] = p[k]
        if L.get("shapes"):
            spec["shapes"] = [dict(sh, x=round(sh["x"] - p["x"], 1), y=round(sh["y"] - p["y"], 1))
                              for sh in L["shapes"]]
        if L.get("shapes") is not None and L.get("arcs"):
            spec["arcs"] = [dict(ac, cx=round(ac["cx"] - p["x"], 1), cy=round(ac["cy"] - p["y"], 1))
                            for ac in L["arcs"]]
        if L.get("stars"):
            spec["stars"] = [dict(st_, cx=round(st_["cx"] - p["x"], 1), cy=round(st_["cy"] - p["y"], 1))
                             for st_ in L["stars"]]
        gg_ = L.get("gauge")
        if gg_:    # 图卡是静态的：进度圈按最终值烤进底板（影片里它是会动的一层）
            spec.setdefault("arcs", []).extend([
                {"cx": round(gg_["cx"] - p["x"], 1), "cy": round(gg_["cy"] - p["y"], 1), "r": gg_["r"],
                 "w": gg_["w"], "color": gg_["track"], "alpha": 0.24, "a0": -90.0, "a1": 270.0},
                {"cx": round(gg_["cx"] - p["x"], 1), "cy": round(gg_["cy"] - p["y"], 1), "r": gg_["r"],
                 "w": gg_["w"], "color": gg_["color"], "alpha": 1.0,
                 "a0": -90.0, "a1": -90.0 + 360.0 * float(gg_["ratio"])}])
        baked = [ic for ic in loose if abs(ic["t0"] - 0.0) < 1e-6]
        loose = [ic for ic in loose if abs(ic["t0"] - 0.0) >= 1e-6]
        if baked:
            spec["icons"] = [{"name": ic["name"], "x": round(ic["x"] - p["x"], 1),
                              "y": round(ic["y"] - p["y"], 1), "size": ic["size"], "color": ic["color"],
                              "badge": ic.get("badge"), "style": ic.get("style", "line")} for ic in baked]
        png, m = draw.make_plate(spec, os.path.join(work, "plates"))
        inputs.append(["-loop", "1", "-t", "1", "-framerate", "10", "-i", os.path.relpath(png, work)])
        chain.append(("", p["x"] - m, p["y"] - m))
    for ic in loose:
        png = icons_mod.make_png(ic["name"], ic["size"], ic["color"], os.path.join(work, "plates"),
                                 badge=ic.get("badge"), style=ic.get("style", "line"))
        inputs.append(["-loop", "1", "-t", "1", "-framerate", "10", "-i", os.path.relpath(png, work)])
        chain.append(("", int(round(ic["x"])), int(round(ic["y"]))))

    lines: List[str] = []
    for it in L.get("items") or []:
        s_it = dict(it, dx=0, dy=0, di=0.01, do=0.0, t0=0.0, t1=9.0, float=None, curve="smooth")
        if s_it.get("counter"):                      # 跳数卡：图卡只要终值
            c = dict(s_it.pop("counter"))
            s_it["text"] = c["prefix"] + cards.fmt_num(c["to"], c["style"], c["digits"]) + c["suffix"]
            s_it.pop("unit", None)
            s_it["runs"] = None
        lines += richtext.dialogues(s_it, th, runs=s_it.get("runs"), fade_out=False)
    ass = os.path.join(work, "cardpic.ass")
    richtext.write(ass, W, H, lines)

    fc = ["[0:v]scale=%d:%d,format=rgba[b0]" % (W, H)]
    cur = "b0"
    for i, (_t, x, y) in enumerate(chain, start=1):
        fc.append("[%s][%d:v]overlay=%d:%d[b%d]" % (cur, i, x, y, i))
        cur = "b%d" % i
    from .overlays import q
    fc.append("[%s]subtitles=filename=cardpic.ass:fontsdir=%s,select='gte(t\\,0.5)',format=%s[v]"
              % (cur, q(fonts.FONT_DIR), "rgb24"))
    args = [env.ffmpeg(), "-v", "error", "-y"]
    for g in inputs:
        args += g
    args += ["-filter_complex", ";".join(fc), "-map", "[v]", "-frames:v", "1", "-update", "1", out_path]
    env.run(args, cwd=work)
    return out_path


def make(sb_path: str, sizes: Tuple[str, ...] = ("1350",), pick: Optional[List[int]] = None,
         bg_mode: str = "frame") -> Tuple[List[str], List[str]]:
    """出图卡。pick＝要哪几张（从 1 开始，对应 listing 的顺序）；不给就全部。"""
    from . import render as R
    sb = R.load_storyboard(sb_path)
    W0, H0 = int(sb["output"]["width"]), int(sb["output"]["height"])
    base = sb["_base"]
    work = os.path.join(base, "work")
    out_dir = os.path.join(base, "out")
    os.makedirs(work, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    items = listing(sb)
    if not items:
        return [], ["这支片里没有可以出图卡的卡片（数据卡、清单卡、金句卡…）"]
    chosen = [items[i - 1] for i in pick if 1 <= i <= len(items)] if pick else items
    files, warns = [], []
    for n, ov in enumerate(chosen, start=1):
        for key in sizes:
            if key not in SIZES:
                warns.append("没有这个尺寸：%s（可用 %s）" % (key, "／".join(SIZES)))
                continue
            W, H = SIZES[key]
            if W0 > H0:                       # 横版片：图卡按原比例出，不硬裁
                W, H = W0, H0
            name = "图卡%02d_%dx%d.png" % (n, W, H)
            out = os.path.join(out_dir, name)
            one(sb, ov, W, H, work, bg_mode, out)
            files.append(out)
            ex = config.export(out, base, "")
            if ex:
                files.append(ex)
    return files, warns


def card_png(sb_path: str, ov: dict, height: int = 960, out_path: Optional[str] = None) -> str:
    """一张字卡的「真样子」：引擎排版、透明背景的 PNG（Studio 停下来时用它换掉近似框）。
    ov＝剪辑表里的一张基本字卡（标题、数据卡、清单、金句、进度圈、评分星、排行榜、时间轴…）。"""
    import hashlib
    import json as _json
    from . import render as R
    sb = R.load_storyboard(sb_path)
    W0, H0 = int(sb["output"]["width"]), int(sb["output"]["height"])
    H = max(2, int(height) & ~1)
    W = max(2, int(round(W0 * H / float(H0))) & ~1)
    work = os.path.join(sb["_base"], "work")
    d = os.path.join(work, "studio", "cards")
    os.makedirs(d, exist_ok=True)
    key = hashlib.sha1(_json.dumps([ov, sb.get("style"), sb.get("brand"), W, H], sort_keys=True,
                                   ensure_ascii=False).encode()).hexdigest()[:16]
    out_path = out_path or os.path.join(d, "card_%s.png" % key)
    if os.path.isfile(out_path):
        return out_path
    # 字幕滤镜在透明画布上画字时不写透明度（字会跟着底一起变淡），所以改成：同一张卡在纯黑、纯白底上
    # 各排一次，两者的差就是透明度（差越小越不透明），黑底那张除以透明度就是原本的颜色。结果和叠在影片上一样准。
    kb, wb = out_path + ".k.png", out_path + ".w.png"
    one(sb, dict(ov), W, H, work, "black", kb)
    one(sb, dict(ov), W, H, work, "white", wb)
    env.run([env.ffmpeg(), "-v", "error", "-y", "-i", kb, "-i", wb, "-filter_complex",
             "[0:v]format=gbrp,split=2[k1][k2];[1:v]format=gbrp[w];"
             "[w][k1]blend=all_expr='255-(A-B)'[al];[al]extractplanes=g[a];"
             "[k2][a]alphamerge,format=rgba,unpremultiply=inplace=1[v]",
             "-map", "[v]", "-frames:v", "1", "-update", "1", out_path])
    for f in (kb, wb):
        try:
            os.remove(f)
        except OSError:
            pass
    return out_path
