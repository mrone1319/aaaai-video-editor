"""合成层：把卡片／图片／带透明通道的片段和推近，编成 ffmpeg 滤镜图。

全部并入主滤镜链，成片仍然只编码一次——加卡片不增加一次转码。
"""
from __future__ import annotations

import hashlib
import os
from typing import Dict, List, Optional, Tuple

from . import cards, draw, fonts, fx, icons, matte, richtext, theme

DEF_DI, DEF_DO = cards.DI, cards.DO


def q(s: str) -> str:
    """滤镜参数里的路径／字串引用。"""
    return "'" + s.replace("\\", "\\\\").replace("'", r"'\''") + "'"


def col(hexc: str) -> str:
    return "0x" + hexc.lstrip("#")


def ease(t0: float, d: float) -> str:
    """0→1 的平滑渐变表达式（smoothstep）。"""
    p = "min(1\\,max(0\\,(t-%.3f)/%.3f))" % (t0, max(d, 0.01))
    return "(%s)*(%s)*(3-2*(%s))" % (p, p, p)


def alpha_expr(t0: float, t1: float, di: float, do: float) -> str:
    return ("min(1\\,max(0\\,(t-%.3f)/%.3f))*min(1\\,max(0\\,(%.3f-t)/%.3f))"
            % (t0, max(di, 0.01), t1, max(do, 0.01)))


def _textfile(work: str, text: str) -> str:
    d = os.path.join(work, "text")
    os.makedirs(d, exist_ok=True)
    name = "t_%s.txt" % hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    p = os.path.join(d, name)
    if not os.path.isfile(p):
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
    return "text/" + name  # 相对 work 目录，避开滤镜里的路径转义


def _drawtext(it: dict, work: str, fps: float) -> List[str]:
    txt = it.get("text") or ""
    if it.get("counter"):   # 跳数的文字在 counter 里：前后缀（例如「天」「万」）有中文也要算
        txt = "%s%s" % (it["counter"].get("prefix", ""), it["counter"].get("suffix", ""))
    # 等宽数字字体没有中文字形：文字里有中文就退回中文字体，否则会显示成方块
    font = theme.num_font() if it.get("mono") and not any(cards.is_cjk(c) for c in txt) \
        else theme.cjk_font()
    t0, t1, di, do = it["t0"], it["t1"], it["di"], it["do"]
    s = ease(t0, di)
    if it.get("cx") is not None:
        x = "(%d-text_w/2)" % it["cx"]
    else:
        x = "%d" % it["x"]
    if it.get("dx"):
        x = "%s+(%d)*(1-%s)" % (x, it["dx"], s)
    y = "%d" % it["y"]
    if it.get("dy"):
        y = "%s+(%d)*(1-%s)" % (y, it["dy"], s)
    common = ("fontfile=%s:fontsize=%d:fontcolor=%s:x=%s:y=%s:alpha='%s':expansion=none"
              % (q(font), it["size"], col(it["color"]), x, y, alpha_expr(t0, t1, di, do)))
    if it.get("stroke"):
        common += ":borderw=%d:bordercolor=black@0.7" % max(2, int(it["size"] * 0.055))
    out = []
    if it.get("counter"):
        for a, b, s_txt in cards.counter_steps(it["counter"], t0, t1, fps):
            # 左闭右开：相邻两个数值在交界那一帧不会同时画出来（否则数字会叠成乱码）
            out.append("drawtext=textfile=%s:%s:enable='gte(t\\,%.4f)*lt(t\\,%.4f)'"
                       % (q(_textfile(work, s_txt)), common, a, b))
    else:
        out.append("drawtext=textfile=%s:%s:enable='between(t\\,%.3f\\,%.3f)'"
                   % (q(_textfile(work, it["text"])), common, max(0, t0 - 0.05), t1 + 0.05))
    return out


def _rich(it: dict, th: dict, fps: float) -> List[str]:
    if it.get("counter"):
        steps = cards.counter_steps(it["counter"], it["t0"], it["t1"], fps)
        out: List[str] = []
        for k, (a, b, txt) in enumerate(steps):
            out += richtext.dialogues(it, th, text=txt, a0=a, a1=b, fade_out=(k == len(steps) - 1))
        return out
    return richtext.dialogues(it, th, runs=it.get("runs"))


def zoom_filter(zooms: List[dict], W: int, H: int, fps: float) -> str:
    """多段推近合成一条 zoompan。smooth 为缓入缓出，punch 为瞬切。"""
    zs, xs, ys, ws = [], [], [], []
    for z in zooms:
        a, b = float(z["t"][0]), float(z["t"][1])
        to = float(z.get("to", 1.12))
        ax, ay = (z.get("anchor") or [0.5, 0.42])[:2]
        if (z.get("style") or "smooth") == "punch":
            shape = "between(time\\,%.3f\\,%.3f)" % (a, b)
        else:
            d = min(float(z.get("ease", 0.45)), max(0.05, (b - a) / 2))
            pin = "min(1\\,max(0\\,(time-%.3f)/%.3f))" % (a, d)
            pout = "min(1\\,max(0\\,(%.3f-time)/%.3f))" % (b, d)
            shape = "(%s)*(%s)*(%s)*(3-2*(%s))" % (pin, pout, pin, pin)
        zs.append("(%.4f)*(%s)" % (to - 1.0, shape))
        ws.append("(%s)" % shape)
        xs.append("(%.4f)*(%s)" % (float(ax), shape))
        ys.append("(%.4f)*(%s)" % (float(ay), shape))
    zexpr = "1+" + "+".join(zs)
    wsum = "+".join(ws)
    axe = "(0.0000005+%s)/(0.000001+%s)" % ("+".join(xs), wsum)
    aye = "(0.0000005+%s)/(0.000001+%s)" % ("+".join(ys), wsum)
    return ("zoompan=z='%s':x='(iw-iw/zoom)*(%s)':y='(ih-ih/zoom)*(%s)':d=1:s=%dx%d:fps=%s"
            % (zexpr, axe, aye, W, H, fps))


def _merge(rs: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for a, b in sorted(rs):
        if out and a <= out[-1][1] + 0.04:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def build(sb: dict, work: str, W: int, H: int, fps: float, base_idx: int = 1,
          source: Optional[str] = None, base_graph: Optional[str] = None):
    """返回 (输入参数, 组装函数)。组装函数接 base 标签、字幕滤镜、推近滤镜，产出滤镜尾段。"""
    ovs = sb.get("overlays") or []
    mc = dict({"quality": "balanced", "scale": 0.5, "feather": 2.0}, **(sb.get("matte") or {}))
    inputs: List[List[str]] = []
    prepared: List[dict] = []
    subjects: List[dict] = []   # 需要人像遮罩的层
    idx = base_idx

    def need_matte(a: float, b: float, tag: str) -> Tuple[int, int, int]:
        nonlocal idx
        if not source or not base_graph:
            raise ValueError("人像去背需要 source 与 base_graph")
        f, mw, mh = matte.build(source, base_graph, (a, b), work, W, H, fps,
                                str(mc["quality"]), float(mc["scale"]), tag)
        cov = matte.coverage(f)
        if cov < 0.005:
            print("⚠️ %.1f–%.1fs 没认出人物（遮罩覆盖率 %.1f%%），这段的去背不会有效果" % (a, b, cov * 100))
        inputs.append(["-i", os.path.relpath(f, work)])
        i = idx
        idx += 1
        return i, mw, mh

    for ov in ovs:
        typ = ov.get("type")
        t0, t1 = float(ov["t"][0]), float(ov["t"][1])
        dur = max(0.1, t1 - t0)
        if typ == "broll":
            # B-roll：满版盖住口播画面（口播声音照常），卡片与字幕仍在它上面
            f = os.path.normpath(os.path.join(sb.get("_base", ""), ov["file"]))
            if not os.path.isfile(f):
                raise FileNotFoundError("B-roll 找不到文件：%s" % f)
            is_img = os.path.splitext(f)[1].lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
            if is_img:
                inputs.append(["-loop", "1", "-framerate", str(fps), "-t", "%.3f" % dur, "-i", f])
            else:   # 素材比时段短就循环；from＝从素材第几秒开始取
                inputs.append(["-stream_loop", "-1", "-ss", "%.3f" % float(ov.get("from", 0)), "-t", "%.3f" % dur,
                               "-i", f])
            mode = ov.get("mode", "fullscreen")
            prepared.append({"ov": ov, "t0": t0, "t1": t1, "under": False, "behind": False, "layers": [],
                             "items": [], "cutout": None,
                             "broll": {"idx": idx, "img": is_img, "mode": mode,
                                       "motion": ov.get("motion", "in" if is_img else "none"),
                                       "fade": float(ov.get("fade", 0.0))}})
            idx += 1
            continue
        if typ == "frame":
            # 卡片接管：整屏底 → 画面收进圆角框 → 标题 → 人物从框上缘冲出（需要人像遮罩）
            th = theme.theme(ov.get("style") or sb.get("style"), sb.get("_base"), sb.get("brand"))
            if th.get("display_font"):
                fonts.display(th)
            mx = round(W * cards.MARGIN_X)
            bx, by = mx & ~1, int(H * float(ov.get("top", 0.34))) & ~1
            bw, bh = (W - 2 * mx) & ~1, int(H * float(ov.get("height", 0.50))) & ~1
            zoom = float(ov.get("zoom", 1.12))
            vw = int(round(bw * zoom)) & ~1
            vh = int(round(vw * H / float(W))) & ~1
            cy = int((vh - bh) * float(ov.get("focus", 0.30))) & ~1
            cx = ((vw - bw) // 2) & ~1
            rec = {"ov": ov, "t0": t0, "t1": t1, "under": bool(ov.get("under_captions")), "behind": False,
                   "layers": [], "items": [], "cutout": None, "th": th,
                   "engine": th.get("text_engine", "drawtext")}
            if th.get("bleed_bg") == "starfield":
                inputs.append(["-stream_loop", "-1", "-t", "%.3f" % dur, "-i",
                               fx.starfield(W, H, fps, th.get("accent", "#E60012"), th.get("accent2", "#FF6A1A"))])
            else:
                png, _m = draw.make_plate({"w": W, "h": H, "radius": 0, "fill": th["plate"], "alpha": 1.0,
                                           "border": {"w": 0}, "shadow": {}}, os.path.join(work, "plates"))
                inputs.append(["-loop", "1", "-t", "%.3f" % dur, "-i", os.path.relpath(png, work)])
            rec["layers"].append({"idx": idx, "x": "-%d" % (0 if th.get("bleed_bg") == "starfield" else _m),
                                  "y": "-%d" % (0 if th.get("bleed_bg") == "starfield" else _m),
                                  "t0": t0, "t1": t1, "scale": None, "di": DEF_DI, "do": DEF_DO, "fade": True})
            idx += 1
            mask, mm = draw.make_plate({"w": bw, "h": bh, "radius": th["radius"], "fill": "#FFFFFF", "alpha": 1.0,
                                        "border": {"w": 0}, "shadow": {}}, os.path.join(work, "plates"))
            inputs.append(["-loop", "1", "-t", "%.3f" % (t1 + 0.5), "-i", os.path.relpath(mask, work)])
            fr = {"mask": idx, "mm": mm, "bx": bx, "by": by, "bw": bw, "bh": bh, "vw": vw, "vh": vh,
                  "cx": cx, "cy": cy, "popout": bool(ov.get("popout", True)), "subject": None}
            idx += 1
            if fr["popout"]:
                mi, _, _ = need_matte(t0, t1, "frame")
                subjects.append({"a": t0, "b": t1, "mode": "frame", "idx": mi, "ov": ov, "order": -1})
                fr["subject"] = len(subjects) - 1
            rec["frame"] = fr
            if ov.get("text") or ov.get("kicker"):
                tov = {"type": "title", "t": [t0, t1], "text": ov.get("text", ""), "kicker": ov.get("kicker"),
                       "sub": ov.get("sub"), "pos": "top", "anim": ov.get("anim", "rise")}
                rec["items"] = cards.layout(tov, th, W, H, fps)["items"]   # 只要文字，不要底板
            prepared.append(rec)
            continue
        if typ == "cutout":
            mi, _, _ = need_matte(t0, t1, "cutout")
            subjects.append({"a": t0, "b": t1, "mode": "cutout", "idx": mi, "ov": ov,
                             "order": len(prepared)})
            prepared.append({"ov": ov, "t0": t0, "t1": t1, "under": bool(ov.get("under_captions")),
                             "behind": False, "layers": [], "items": [], "cutout": len(subjects) - 1})
            continue
        rec = {"ov": ov, "t0": t0, "t1": t1, "under": bool(ov.get("under_captions")),
               "behind": bool(ov.get("behind_subject")), "layers": [], "items": [], "cutout": None}
        if typ in ("image", "clip"):
            f = os.path.normpath(os.path.join(sb.get("_base", ""), ov["file"]))
            if not os.path.isfile(f):
                raise FileNotFoundError("overlay 找不到文件：%s" % f)
            if typ == "image":
                if ov.get("disc"):   # 黑色／透明底 logo 放深色卡上会看不见：先垫一个白底圆片
                    wf_ = float(ov.get("width", 0.3))
                    ow_ = int(round(W * wf_))
                    dd = int(round(ow_ * 1.35))
                    ax_, ay_ = cards.ANCHORS.get(ov.get("pos") or "center", (0.5, 0.5))
                    mx_ = round(W * cards.MARGIN_X)
                    lx = mx_ + ax_ * (W - 2 * mx_ - ow_)
                    ly = H * cards.TOP_M + ay_ * (H * (1 - cards.TOP_M - cards.BOT_M) - ow_)
                    dp, dm = draw.make_plate({"w": dd, "h": dd, "radius": dd / 2, "fill": ov.get("disc_color", "#FFFFFF"),
                                              "alpha": 1.0, "border": {"w": 0},
                                              "shadow": {"soft": 16, "alpha": 0.35, "dy": 5, "color": "#000000"}},
                                             os.path.join(work, "plates"))
                    inputs.append(["-loop", "1", "-t", "%.3f" % dur, "-i", os.path.relpath(dp, work)])
                    rec["layers"].append({"idx": idx, "x": "%d" % int(lx + ow_ / 2 - dd / 2 - dm),
                                          "y": "%d" % int(ly + ow_ / 2 - dd / 2 - dm), "t0": t0, "t1": t1,
                                          "scale": None, "di": DEF_DI, "do": DEF_DO, "fade": True})
                    idx += 1
                inputs.append(["-loop", "1", "-t", "%.3f" % dur, "-i", f])
            else:
                inputs.append(["-i", f])
            wfrac = float(ov.get("width", 1.0 if typ == "clip" else 0.3))
            ax, ay = cards.ANCHORS.get(ov.get("pos") or "center", (0.5, 0.5))
            mx = round(W * cards.MARGIN_X)
            ow = int(round(W * wfrac))
            x = "%d" % int(round(mx + ax * (W - 2 * mx - ow)))
            y = "%d" % int(round(H * cards.TOP_M + ay * (H * (1 - cards.TOP_M - cards.BOT_M) - ow)))
            if wfrac >= 0.999 and typ == "clip":
                x, y = "0", "0"
            rec["layers"].append({"idx": idx, "x": x, "y": y, "t0": t0, "t1": t1,
                                  "scale": ow if wfrac < 0.999 else W, "di": DEF_DI, "do": DEF_DO,
                                  "fade": bool(ov.get("fade", typ == "image"))})
            idx += 1
        else:
            th = theme.theme(ov.get("style") or sb.get("style"), sb.get("_base"), sb.get("brand"))
            if th.get("display_font"):
                fonts.display(th)          # 先把展示字体固化好，libass 才找得到
            L = cards.layout(ov, th, W, H, fps)
            rec["th"], rec["engine"] = th, th.get("text_engine", "drawtext")
            loose = list(L.get("icons") or [])
            if L["plate"]:
                p = L["plate"]
                bleed = bool(ov.get("bleed"))
                if bleed and th.get("bleed_bg") == "starfield":
                    # 整屏断章换成星空跃迁背景（循环素材，按卡片时长截取）
                    clip = fx.starfield(W, H, fps, th.get("accent", "#E60012"), th.get("accent2", "#FF6A1A"))
                    inputs.append(["-stream_loop", "-1", "-t", "%.3f" % dur, "-i", clip])
                    rec["layers"].append({"idx": idx, "x": "0", "y": "0", "t0": t0, "t1": t1, "scale": None,
                                          "di": p["di"], "do": p["do"], "fade": True})
                    idx += 1
                else:
                    baked = [ic for ic in loose if abs(ic["t0"] - t0) < 1e-6]
                    loose = [ic for ic in loose if abs(ic["t0"] - t0) >= 1e-6]
                    spec = {k: p[k] for k in ("w", "h", "radius", "fill", "alpha", "border", "shadow")}
                    if p.get("scrim"):
                        spec["scrim"] = p["scrim"]
                    if baked:
                        spec["icons"] = [{"name": ic["name"], "x": round(ic["x"] - p["x"], 1),
                                          "y": round(ic["y"] - p["y"], 1), "size": ic["size"],
                                          "color": ic["color"], "badge": ic.get("badge")} for ic in baked]
                    if L.get("shapes"):
                        spec["shapes"] = [dict(sh, x=round(sh["x"] - p["x"], 1), y=round(sh["y"] - p["y"], 1))
                                          for sh in L["shapes"]]
                    pill = typ == "stamp"
                    glass_cfg = th.get("glass") if not p.get("scrim") else None
                    if glass_cfg and not bleed and not pill:
                        # 毛玻璃：把卡片底下的画面模糊后按卡片形状贴回，再盖半透明底板
                        mask, mm = draw.make_plate({"w": p["w"], "h": p["h"], "radius": p["radius"],
                                                    "fill": "#FFFFFF", "alpha": 1.0, "border": {"w": 0},
                                                    "shadow": {}}, os.path.join(work, "plates"))
                        # yuv420 裁切只能取偶数尺寸／偶数坐标：区域对齐到偶数，遮罩再缩放过去
                        gx, gy = (p["x"] - mm) & ~1, (p["y"] - mm) & ~1
                        gw, gh = (p["w"] + 2 * mm) & ~1, (p["h"] + 2 * mm) & ~1
                        if gx >= 0 and gy >= 0 and gx + gw <= W and gy + gh <= H:
                            inputs.append(["-loop", "1", "-t", "%.3f" % (t1 + 0.5), "-i",
                                           os.path.relpath(mask, work)])
                            rec["glass"] = {"idx": idx, "x": gx, "y": gy, "w": gw,
                                            "h": gh, "sigma": float(glass_cfg.get("sigma", 16)),
                                            "t0": t0, "t1": t1, "di": p["di"], "do": p["do"]}
                            idx += 1
                    png, margin = draw.make_plate(spec, os.path.join(work, "plates"))
                    inputs.append(["-loop", "1", "-t", "%.3f" % dur, "-i", os.path.relpath(png, work)])
                    s_ = ease(t0, p["di"])
                    x = "%d" % (p["x"] - margin)
                    y = "%d" % (p["y"] - margin)
                    if p["dx"]:
                        x = "%s+(%d)*(1-%s)" % (x, p["dx"], s_)
                    if p["dy"]:
                        y = "%s+(%d)*(1-%s)" % (y, p["dy"], s_)
                    rec["layers"].append({"idx": idx, "x": x, "y": y, "t0": t0, "t1": t1,
                                          "scale": None, "di": p["di"], "do": p["do"], "fade": True})
                    idx += 1
                    if th.get("laser") and ov.get("laser", typ in ("title", "stat")) and not pill:
                        # 激光扫光：卡片落定后一道光带扫过，只在主卡（标题／数据）上
                        pat, nfr = fx.sweep(p["w"], p["h"], float(p["radius"]), fps,
                                            th.get("laser_color", "#FFFFFF"))
                        st = t0 + p["di"]
                        inputs.append(["-framerate", str(fps), "-i", pat])
                        rec["layers"].append({"idx": idx, "x": "%d" % p["x"], "y": "%d" % p["y"], "t0": st,
                                              "t1": min(t1, st + nfr / float(fps)), "scale": None,
                                              "di": 0.0, "do": 0.0, "fade": False})
                        idx += 1
            for ic in loose:  # 错峰出现的图标：单独一层，跟着自己那一行的时间进场
                png = icons.make_png(ic["name"], ic["size"], ic["color"], os.path.join(work, "plates"),
                                     badge=ic.get("badge"))
                it0 = ic["t0"]
                inputs.append(["-loop", "1", "-t", "%.3f" % max(0.1, t1 - it0), "-i",
                               os.path.relpath(png, work)])
                s_ = ease(it0, ic["di"])
                x = "%d" % int(round(ic["x"]))
                y = "%d" % int(round(ic["y"]))
                if ic["dx"]:
                    x = "%s+(%d)*(1-%s)" % (x, ic["dx"], s_)
                if ic["dy"]:
                    y = "%s+(%d)*(1-%s)" % (y, ic["dy"], s_)
                rec["layers"].append({"idx": idx, "x": x, "y": y, "t0": it0, "t1": t1,
                                      "scale": None, "di": ic["di"], "do": ic["do"], "fade": True})
                idx += 1
            rec["items"] = L["items"]
        prepared.append(rec)

    # 被「穿插」的卡片窗口合并后，人物只需要重贴一次
    behind_wins = _merge([(r["t0"], r["t1"]) for r in prepared if r["behind"]])
    behind_subj: List[int] = []
    for a, b in behind_wins:
        mi, _, _ = need_matte(a, b, "behind")
        subjects.append({"a": a, "b": b, "mode": "behind", "idx": mi, "ov": None, "order": -1})
        behind_subj.append(len(subjects) - 1)

    def assemble(base: str, subs: Optional[str], zoom: Optional[str] = None) -> Tuple[str, str]:
        parts: List[str] = []
        n = [0]
        cur = base
        branch: List[str] = []
        frames = [r for r in prepared if r.get("frame")]
        nsplit = len(subjects) + 1 + len(frames)
        if nsplit > 1:
            branch = ["sp%d" % i for i in range(nsplit)]
            parts.append("[%s]split=%d%s" % (base, nsplit, "".join("[%s]" % l for l in branch)))
            cur = branch[0]
        for k, r in enumerate(frames):
            r["frame"]["branch"] = branch[len(subjects) + 1 + k]
        subj_lab: Dict[int, str] = {}
        for i, sj in enumerate(subjects):
            m = ("[%d:v]format=gray,tpad=start_duration=%.3f:start_mode=add:color=black,"
                 "scale=%d:%d" % (sj["idx"], sj["a"], W, H))
            if float(mc["feather"]) > 0:
                m += ",gblur=sigma=%.2f" % float(mc["feather"])
            if zoom:
                m += "," + zoom   # 遮罩跟着底片一起推近，才不会错位
            parts.append(m + "[mm%d]" % i)
            parts.append("[%s][mm%d]alphamerge[subj%d]" % (branch[i + 1], i, i))
            subj_lab[i] = "subj%d" % i

        def put(lab_in: str, x: str, y: str, a: float, b: float) -> None:
            nonlocal cur
            n[0] += 1
            out = "c%d" % n[0]
            parts.append("[%s][%s]overlay=x=%s:y=%s:enable='between(t\\,%.3f\\,%.3f)':"
                         "eof_action=pass:repeatlast=0[%s]" % (cur, lab_in, x, y, a, b, out))
            cur = out

        def fadeA(t0_, t1_, di_, do_):
            return ("fade=t=in:st=%.3f:d=%.3f:alpha=1,fade=t=out:st=%.3f:d=%.3f:alpha=1"
                    % (t0_, di_, max(t0_, t1_ - do_), do_))

        def emit_frame(rec):
            nonlocal cur
            f = rec["frame"]
            n[0] += 1
            k = n[0]
            parts.append("[%s]scale=%d:%d,crop=%d:%d:%d:%d,format=yuva444p[fv%d]"
                         % (f["branch"], f["vw"], f["vh"], f["bw"], f["bh"], f["cx"], f["cy"], k))
            parts.append("[%d:v]alphaextract,crop=%d:%d:%d:%d[fm%d]"
                         % (f["mask"], f["bw"], f["bh"], f["mm"], f["mm"], k))
            parts.append("[fv%d][fm%d]alphamerge,%s[ff%d]"
                         % (k, k, fadeA(rec["t0"], rec["t1"], DEF_DI, DEF_DO), k))
            put("ff%d" % k, "%d" % f["bx"], "%d" % f["by"], rec["t0"], rec["t1"])
            if f["subject"] is not None:   # 人物：同样缩放，只保留框底以上 → 头冲出框上缘
                parts.append("[%s]scale=%d:%d,crop=%d:%d:%d:0,%s[fp%d]"
                             % (subj_lab[f["subject"]], f["vw"], f["vh"], f["bw"], f["cy"] + f["bh"], f["cx"],
                                fadeA(rec["t0"], rec["t1"], DEF_DI, DEF_DO), k))
                put("fp%d" % k, "%d" % f["bx"], "%d" % (f["by"] - f["cy"]), rec["t0"], rec["t1"])

        def emit(rec):
            nonlocal cur
            if rec["cutout"] is not None:
                sj = subjects[rec["cutout"]]
                ov = rec["ov"]
                wfrac = float(ov.get("width", 1.0))
                lab = subj_lab[rec["cutout"]]
                if wfrac < 0.999:
                    n[0] += 1
                    ow = int(round(W * wfrac))
                    parts.append("[%s]scale=%d:-1[cut%d]" % (lab, ow, n[0]))
                    lab = "cut%d" % n[0]
                    ax, ay = cards.ANCHORS.get(ov.get("pos") or "center", (0.5, 0.5))
                    mx = round(W * cards.MARGIN_X)
                    x = "%d" % int(round(mx + ax * (W - 2 * mx - ow)))
                    y = "%d" % int(round(H * cards.TOP_M + ay *
                                         (H * (1 - cards.TOP_M - cards.BOT_M) - ow * H / W)))
                else:
                    x, y = "0", "0"
                put(lab, x, y, rec["t0"], rec["t1"])
                return
            g = rec.get("glass")
            if g:
                n[0] += 1
                k = n[0]
                parts.append("[%s]split=2[gA%d][gB%d]" % (cur, k, k))
                parts.append("[gB%d]crop=%d:%d:%d:%d,gblur=sigma=%.1f:enable='between(t\\,%.3f\\,%.3f)'[gC%d]"
                             % (k, g["w"], g["h"], g["x"], g["y"], g["sigma"], g["t0"], g["t1"], k))
                parts.append("[%d:v]alphaextract,scale=%d:%d[gM%d]" % (g["idx"], g["w"], g["h"], k))
                parts.append("[gC%d][gM%d]alphamerge,fade=t=in:st=%.3f:d=%.3f:alpha=1,"
                             "fade=t=out:st=%.3f:d=%.3f:alpha=1[gD%d]"
                             % (k, k, g["t0"], g["di"], max(g["t0"], g["t1"] - g["do"]), g["do"], k))
                out = "c%d" % k
                parts.append("[gA%d][gD%d]overlay=x=%d:y=%d:enable='between(t\\,%.3f\\,%.3f)'[%s]"
                             % (k, k, g["x"], g["y"], g["t0"], g["t1"], out))
                cur = out
            for lay in rec["layers"]:
                n[0] += 1
                lab = "ov%d" % n[0]
                pre = "[%d:v]format=rgba" % lay["idx"]
                if lay["scale"]:
                    pre += ",scale=%d:-1" % lay["scale"]
                if lay["fade"]:
                    d = max(0.1, lay["t1"] - lay["t0"])
                    pre += (",fade=t=in:st=0:d=%.3f:alpha=1,fade=t=out:st=%.3f:d=%.3f:alpha=1"
                            % (lay["di"], max(0.0, d - lay["do"]), lay["do"]))
                pre += ",setpts=PTS+%.3f/TB[%s]" % (lay["t0"], lab)
                parts.append(pre)
                put(lab, lay["x"], lay["y"], lay["t0"], lay["t1"])
            if rec.get("frame"):
                emit_frame(rec)
            txt = []
            for it in rec["items"]:
                if rec.get("engine") == "ass" or it.get("runs"):
                    rich.extend(_rich(it, rec["th"], fps))   # 富文本：整组合成一个 ASS，最后一次烧上
                else:
                    txt += _drawtext(it, work, fps)
            if txt:
                n[0] += 1
                out = "c%d" % n[0]
                parts.append("[%s]%s[%s]" % (cur, ",".join(txt), out))
                cur = out

        rich: List[str] = []

        def flush(tag: str) -> None:
            nonlocal cur
            if not rich:
                return
            name = richtext.file_for(work, W, H, rich, tag)
            n[0] += 1
            out = "c%d" % n[0]
            parts.append("[%s]subtitles=filename=%s:fontsdir=%s[%s]" % (cur, name, q(fonts.FONT_DIR), out))
            cur = out
            del rich[:]

        def emit_broll(rec):
            nonlocal cur
            b = rec["broll"]
            n[0] += 1
            k = n[0]
            dur_ = rec["t1"] - rec["t0"]
            src = "[%d:v]" % b["idx"]
            if b["mode"] == "letterbox":        # 横式素材：完整显示，上下黑边
                ch = "scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:black" % (W, H, W, H)
                parts.append("%s%s,setsar=1,fps=%s[br%d]" % (src, ch, fps, k))
            elif b["mode"] == "blur":           # 横式素材：完整显示，背后铺同一画面的模糊放大版
                parts.append("%ssplit=2[bb%d][bf%d]" % (src, k, k))
                parts.append("[bb%d]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,gblur=sigma=28,"
                             "eq=brightness=-0.08[bg%d]" % (k, W // 4 * 2, H // 4 * 2, W // 4 * 2, H // 4 * 2, k))
                parts.append("[bg%d]scale=%d:%d[bs%d]" % (k, W, H, k))
                parts.append("[bf%d]scale=%d:%d:force_original_aspect_ratio=decrease[bfs%d]" % (k, W, H, k))
                parts.append("[bs%d][bfs%d]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=%s[br%d]" % (k, k, fps, k))
            else:                               # fullscreen：裁切铺满
                ch = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (W, H, W, H)
                if b["img"] and b["motion"] in ("in", "out"):   # 图片：缓慢推拉，不是一张死图
                    nf = max(1, int(round(dur_ * float(fps))))
                    z = ("1+0.08*on/%d" % nf) if b["motion"] == "in" else ("1.08-0.08*on/%d" % nf)
                    ch += (",zoompan=z='%s':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=%dx%d:fps=%s"
                           % (z, W, H, fps))
                parts.append("%s%s,setsar=1,fps=%s[br%d]" % (src, ch, fps, k))
            post = "[br%d]format=yuva420p" % k
            if b["fade"] > 0:
                post += (",fade=t=in:st=0:d=%.3f:alpha=1,fade=t=out:st=%.3f:d=%.3f:alpha=1"
                         % (b["fade"], max(0.0, dur_ - b["fade"]), b["fade"]))
            parts.append(post + ",setpts=PTS-STARTPTS+%.3f/TB[bo%d]" % (rec["t0"], k))
            put("bo%d" % k, "0", "0", rec["t0"], rec["t1"])

        # 图层顺序：底片 → B-roll → 穿插卡片 → 人物重贴 → 字幕下卡片 → 字幕 → 其余卡片
        for rec in prepared:
            if rec.get("broll"):
                emit_broll(rec)
        for rec in prepared:
            if rec["behind"]:
                emit(rec)
        flush("behind")
        for i in behind_subj:
            sj = subjects[i]
            put(subj_lab[i], "0", "0", sj["a"], sj["b"])
        for rec in prepared:
            if rec["under"] and not rec["behind"] and not rec.get("broll"):
                emit(rec)
        flush("under")
        if subs:
            n[0] += 1
            out = "c%d" % n[0]
            parts.append("[%s]%s[%s]" % (cur, subs, out))
            cur = out
        for rec in prepared:
            if not rec["under"] and not rec["behind"] and not rec.get("broll"):
                emit(rec)
        flush("top")
        return ";".join(parts), cur

    return inputs, assemble
