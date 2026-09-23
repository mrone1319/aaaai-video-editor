"""合成层：把卡片／图片／带透明通道的片段和推近，编成 ffmpeg 滤镜图。

全部并入主滤镜链，成片仍然只编码一次——加卡片不增加一次转码。
"""
from __future__ import annotations

import hashlib
import math
import os
from typing import Dict, List, Optional, Tuple

from . import cards, composites, draw, env, fonts, fx, icons, matte, richtext, theme

DEF_DI, DEF_DO = cards.DI, cards.DO


def q(s: str) -> str:
    """滤镜参数里的路径／字串引用。"""
    if env.WIN and len(s) > 2 and s[1] == ":" and s[2] in "\\/":   # Windows 路径：C:\a\b → C\:/a/b（冒号不能当参数分隔）
        return "'" + s.replace("\\", "/").replace(":", "\\:").replace("'", r"'\''") + "'"
    return "'" + s.replace("\\", "\\\\").replace("'", r"'\''") + "'"


def col(hexc: str) -> str:
    return "0x" + hexc.lstrip("#")


def ease(t0: float, d: float, curve: str = "smooth") -> str:
    """0→1 的渐变表达式。smooth＝smoothstep；back＝收尾走过头一点再回来（弹出感）。"""
    p = "min(1\\,max(0\\,(t-%.3f)/%.3f))" % (t0, max(d, 0.01))
    if curve == "back":
        k = 0.9
        q = "((%s)-1)" % p
        return "(1+%.2f*%s*%s*%s+%.2f*%s*%s)" % (k + 1.0, q, q, q, k, q, q)
    return "(%s)*(%s)*(3-2*(%s))" % (p, p, p)


def float_expr(fl: Optional[dict]) -> str:
    """悬浮呼吸的 y 偏移表达式（与 richtext.float_y 同一条曲线，文字和底板一起动）。"""
    if not fl:
        return ""
    return ("+(%.2f)*sin(2*PI*(t-%.3f)/%.3f)*min(1\\,max(0\\,(t-%.3f)/0.6))"
            % (fl["a"], fl["s"], fl["p"], fl["s"]))


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
    s = ease(t0, di, it.get("curve") or "smooth")
    if it.get("cx") is not None:
        x = "(%d-text_w/2)" % it["cx"]
    else:
        x = "%d" % it["x"]
    if it.get("dx"):
        x = "%s+(%d)*(1-%s)" % (x, it["dx"], s)
    y = "%d" % it["y"]
    y_fl = float_expr(it.get("float"))
    if it.get("dy"):
        y = "%s+(%d)*(1-%s)" % (y, it["dy"], s)
    y += y_fl
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


def circle_photo(src: str, size: int, focus: float, cache_dir: str) -> str:
    """照片裁成正方形（按 focus 决定上下取哪一段，人脸通常在上方）→ 圆形透明边缘（抗锯齿）。"""
    st = os.stat(src)
    key = hashlib.sha1(repr((os.path.abspath(src), st.st_size, st.st_mtime_ns, size, round(focus, 3), 1)).encode()).hexdigest()[:16]
    os.makedirs(cache_dir, exist_ok=True)
    out = os.path.join(cache_dir, "avatar_%s.png" % key)
    if os.path.isfile(out):
        return out
    from . import env
    r = size / 2.0
    if env.MAC and src.lower().endswith((".heic", ".heif")):   # iPhone 照片：少数 HEIC 版本 ffmpeg 解不了，先用系统 sips 转 JPEG
        jpg = os.path.join(cache_dir, "avatar_%s_src.jpg" % key)
        try:
            env.run(["sips", "-s", "format", "jpeg", src, "--out", jpg])
            src = jpg
        except env.ToolError:
            pass
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", src, "-vf",
             "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d:(iw-%d)/2:(ih-%d)*%.3f,format=rgba,"
             "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='255*clip((%.2f-hypot(X-%.2f,Y-%.2f))/1.5,0,1)'"
             % (size, size, size, size, size, size, focus, r - 0.5, r - 0.5, r - 0.5),
             "-frames:v", "1", out])
    return out


def mesh_colors(th: dict) -> List[str]:
    """网状渐层的几团颜色：强调色／次强调色／价值色各压暗一点，配上风格底色才不会太跳。"""
    def dim(c: str, k: float) -> str:
        r, g, b = draw.hex_rgb(c)
        return "#%02X%02X%02X" % (int(r * k), int(g * k), int(b * k))
    acc = th.get("accent", "#FFC933")
    # 只用强调色（深浅两团）＋风格底色：不混进价值色，免得整块背景变成另一种颜色
    out = [dim(acc, 0.40), dim(th.get("accent2") or acc, 0.20)]
    pl = th["plate"][0] if isinstance(th["plate"], (list, tuple)) else th["plate"]
    out.append(dim(pl, 1.6 if _is_dark(pl) else 0.9))
    return out


def _is_dark(c: str) -> bool:
    r, g, b = draw.hex_rgb(c)
    return (r + g + b) < 3 * 128


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


def framed_image(src: str, w: int, h: int, border: int, radius: int, work: str) -> Tuple[str, int]:
    """证据截图：白色圆角框＋阴影，截图四角跟着圆。回传 (png, 四周留给阴影的边距)。按内容缓存。"""
    st = os.stat(src)
    key = hashlib.sha1(repr((os.path.abspath(src), st.st_size, st.st_mtime_ns, w, h, border, radius, 1)).encode()
                       ).hexdigest()[:16]
    out = os.path.join(work, "plates", "proof_%s.png" % key)
    plate, m = draw.make_plate({"w": w + 2 * border, "h": h + 2 * border, "radius": radius, "fill": "#FFFFFF",
                                "alpha": 1.0, "border": {"w": 0},
                                "shadow": {"soft": 22, "alpha": 0.38, "dy": 8, "color": "#000000"}},
                               os.path.join(work, "plates"))
    if os.path.isfile(out):
        return out, m
    r = max(2, radius - border)
    corner = "if(gt(hypot(max(0,abs(X-W/2)-(W/2-%d)),max(0,abs(Y-H/2)-(H/2-%d))),%d),0,alpha(X,Y))" % (r, r, r)
    g = ("[1:v]scale=%d:%d:flags=lanczos,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='%s'[s];"
         "[0:v][s]overlay=%d:%d:format=auto" % (w, h, corner, m + border, m + border))
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", plate, "-i", src, "-filter_complex", g, "-frames:v", "1", out])
    return out, m


def glow_png(w: int, h: int, bw: int, color: str, soft: int, work: str) -> Tuple[str, int]:
    """关注框：强调色圆角外框＋向外的光晕（实心圆角块加光晕，再把中间挖空）。"""
    r = min(h // 2, max(12, int(h * 0.28)))
    plate, m = draw.make_plate({"w": w, "h": h, "radius": r, "fill": color, "alpha": 1.0, "border": {"w": 0},
                                "shadow": {"soft": soft, "alpha": 0.9, "dy": 0, "color": color}},
                               os.path.join(work, "plates"))
    out = plate.replace(".png", "_ring%d.png" % bw)
    if not os.path.isfile(out):
        ri = max(2, r - bw)
        cx, cy = m + w / 2.0, m + h / 2.0
        hole = ("lte(hypot(max(0,abs(X-%.1f)-%.1f),max(0,abs(Y-%.1f)-%.1f)),%d)"
                % (cx, w / 2.0 - bw - ri, cy, h / 2.0 - bw - ri, ri))
        env.run([env.ffmpeg(), "-y", "-v", "error", "-i", plate, "-vf",
                 "format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(%s,0,alpha(X,Y))'" % hole,
                 "-frames:v", "1", out])
    return out, m


def ring_src(S: int, fps: float, color: str) -> str:
    """倒数圆环（lavfi 来源）：淡色底圈＋强调色弧，每秒从满圈顺时针缩到空。"""
    r, g, b = draw.hex_rgb(color)
    c = S / 2.0
    ro, ri = c * 0.96, c * 0.80
    rad = "hypot(X-%.1f,Y-%.1f)" % (c, c)
    ang = "mod(atan2(X-%.1f,%.1f-Y)+2*PI,2*PI)/(2*PI)" % (c, c)
    a = "255*between(%s,%.1f,%.1f)*if(lte(%s,1-mod(T,1)),1,0.22)" % (rad, ri, ro, ang)
    return "color=c=black@0:s=%dx%d:r=%s,format=rgba,geq=r=%d:g=%d:b=%d:a='%s'" % (S, S, fps, r, g, b, a)


def gauge_src(S: int, fps: float, color: str, track: str, ring_w: float, ratio: float,
              t0: float, dur: float) -> str:
    """进度圈（lavfi 来源）：淡色底圈＋强调色弧，从 12 点开始一圈圈填到目标值（缓出）。"""
    r, g, b = draw.hex_rgb(color)
    tr, tg, tb = draw.hex_rgb(track)
    c = S / 2.0
    ro, ri = c - 1.0, c - 1.0 - ring_w
    rad = "hypot(X-%.1f,Y-%.1f)" % (c, c)
    ang = "mod(atan2(X-%.1f,%.1f-Y)+2*PI,2*PI)/(2*PI)" % (c, c)
    if dur > 0.01:   # 缓出：一开始快、接近目标慢下来
        p = "min(1,max(0,(T-%.3f)/%.3f))" % (0.0, dur)
        grow = "%.4f*(1-pow(1-%s,3))" % (ratio, p)
    else:
        grow = "%.4f" % ratio
    on = "lte(%s,%s)" % (ang, grow)
    band = "between(%s,%.1f,%.1f)" % (rad, ri, ro)
    a = "255*%s*if(%s,1,0.22)" % (band, on)
    rr = "if(%s,%d,%d)" % (on, r, tr)
    gg = "if(%s,%d,%d)" % (on, g, tg)
    bb = "if(%s,%d,%d)" % (on, b, tb)
    return ("color=c=black@0:s=%dx%d:r=%s,format=rgba,geq=r='%s':g='%s':b='%s':a='%s'"
            % (S, S, fps, rr, gg, bb, a))


def _merge(rs: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for a, b in sorted(rs):
        if out and a <= out[-1][1] + 0.04:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


TOP_MIN = 0.05   # 避脸往上挪，最多挪到离顶 5%（再上去会被平台的状态栏／标题挡住）
CAP_TOP = 0.62   # 卡片改放下巴下面时，字不能低于这里（字幕约在 64%～70%）


def face_lift(ov: dict, th: dict, W: int, H: int, fps: float, faces) -> dict:
    """上方的卡片（标题、数据、清单、金句…）若在它出现期间压到眼睛，整张往上挪；挪到顶还压到就提醒。
    头顶、帽子被遮罩盖到一点没关系，眼睛不行：护住「头顶～下巴」的 30% 以下。"""
    if not faces or ov.get("behind_subject") or ov.get("bleed") or ov.get("chapter") is not None \
            or ov.get("avoid_face") is False or ov.get("type") in cards.LOWER_TYPES or not cards.is_lite(ov, th):
        return ov
    pos = ov.get("pos")
    if pos and cards.ANCHORS.get(pos, (0.5, 0.5))[1] > 0.0:
        return ov
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    hits = [f for t, f in faces if t0 - 0.25 <= t <= t1 + 0.25 and f]
    if not hits:
        return ov
    eye = min(f[0] + 0.30 * (f[1] - f[0]) for f in hits) * H
    L = cards.layout(ov, th, W, H, fps)
    its = L.get("items") or []
    if not its:
        return ov
    bottom = max(i["y"] + i["size"] * 1.25 for i in its)
    need = bottom - (eye - H * 0.01)
    if need <= 0:
        return ov
    top = cards.TOP_M - need / float(H)
    if top >= TOP_MIN:
        return dict(ov, _top_m=round(top, 4))
    # 挪到顶还压到眼睛：人坐得很高，改放到下巴下面（胸口那一段），字幕上方
    chin = max(f[1] for f in hits)
    low = chin + 0.04
    if bottom + (low - cards.TOP_M) * H <= H * CAP_TOP:
        print("🙂 %.1f–%.1fs 的%s卡片：人坐得高，上方放不下，改放在下巴下面" % (t0, t1, ov.get("type")))
        return dict(ov, _top_m=round(low, 4), _mid=True)
    print("⚠️ %.1f–%.1fs 的%s卡片会压到脸（人坐得高、卡片又太长）：已挪到最上面——文字写短一点，或拆成两张"
          % (t0, t1, ov.get("type")))
    return dict(ov, _top_m=TOP_MIN)


def build(sb: dict, work: str, W: int, H: int, fps: float, base_idx: int = 1,
          source: Optional[str] = None, base_graph=None):
    """返回 (输入参数, 组装函数)。组装函数接 base 标签、字幕滤镜、推近滤镜，产出滤镜尾段。"""
    # 印章、标注是小徽章：画在其他卡片上面，不被标题的遮罩盖住（其余保持原顺序）
    # 卡片接管（整屏底）最先画；印章、标注、关注框、倒数圈、彩带最后画；其余照原顺序
    ovs = sorted(sb.get("overlays") or [],
                 key=lambda o: 0 if o.get("type") == "frame" else
                 (2 if o.get("type") in ("stamp", "callout", "glow", "ring", "confetti") else 1))
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
            # 接管的画面在字幕下层：字幕照常显示在框里（面板区的卡片仍在字幕之上）
            rec = {"ov": ov, "t0": t0, "t1": t1, "under": bool(ov.get("under_captions", True)), "behind": False,
                   "layers": [], "items": [], "cutout": None, "th": th,
                   "engine": th.get("text_engine", "drawtext")}
            paper = ov.get("bg") == "paper" or str(ov.get("bg", "")).startswith("#")
            star = th.get("bleed_bg") == "starfield" and not paper
            if star:
                inputs.append(["-stream_loop", "-1", "-t", "%.3f" % dur, "-i",
                               fx.starfield(W, H, fps, th.get("accent", "#E60012"), th.get("accent2", "#FF6A1A"))])
            else:
                fill = (ov["bg"] if str(ov.get("bg", "")).startswith("#") else composites.PAPER) if paper else th["plate"]
                png, _m = draw.make_plate({"w": W, "h": H, "radius": 0, "fill": fill, "alpha": 1.0,
                                           "border": {"w": 0}, "shadow": {}}, os.path.join(work, "plates"))
                inputs.append(["-loop", "1", "-t", "%.3f" % dur, "-i", os.path.relpath(png, work)])
            bg_layer = {"idx": idx, "x": "-%d" % (0 if star else _m), "y": "-%d" % (0 if star else _m),
                        "t0": t0, "t1": t1, "scale": None, "di": DEF_DI, "do": DEF_DO, "fade": True,
                        "opacity": float(th.get("takeover_star_alpha", 0.55)) if star else 1.0}
            if not star:
                rec["layers"].append(bg_layer)
            idx += 1
            mask, mm = draw.make_plate({"w": bw, "h": bh, "radius": th["radius"], "fill": "#FFFFFF", "alpha": 1.0,
                                        "border": {"w": 0}, "shadow": {}}, os.path.join(work, "plates"))
            inputs.append(["-loop", "1", "-t", "%.3f" % (t1 + 0.5), "-i", os.path.relpath(mask, work)])
            fr = {"mask": idx, "mm": mm, "bx": bx, "by": by, "bw": bw, "bh": bh, "vw": vw, "vh": vh,
                  "cx": cx, "cy": cy, "popout": bool(ov.get("popout", True)), "subject": None}
            idx += 1
            if fr["popout"]:
                # 冲出框的人物要跟着框的圆角收边：上半段整块保留，框内用同一个圆角
                rr = int(th["radius"])
                clip, cmg = draw.make_plate(
                    {"w": bw, "h": cy + bh, "radius": 0, "fill": None, "alpha": 0.0,
                     "border": {"w": 0}, "shadow": {},
                     "shapes": [{"x": 0, "y": 0, "w": bw, "h": cy + rr, "r": 0, "fill": "#FFFFFF"},
                                {"x": 0, "y": cy, "w": bw, "h": bh, "r": rr, "fill": "#FFFFFF"}]},
                    os.path.join(work, "plates"))
                inputs.append(["-loop", "1", "-t", "%.3f" % (t1 + 0.5), "-i", os.path.relpath(clip, work)])
                fr["clip"], fr["cmg"] = idx, cmg
                idx += 1
            if fr["popout"]:
                mi, _, _ = need_matte(t0, t1, "frame")
                subjects.append({"a": t0, "b": t1, "mode": "frame", "idx": mi, "ov": ov, "order": -1})
                fr["subject"] = len(subjects) - 1
            rec["frame"] = fr
            if ov.get("text") or ov.get("kicker"):
                tov = {"type": "title", "t": [t0, t1], "text": ov.get("text", ""), "kicker": ov.get("kicker"),
                       "sub": ov.get("sub"), "pos": "top", "anim": ov.get("anim", "rise")}
                if paper:   # 纸面：标题改深字
                    tov["colors"] = dict(composites.ON_PAPER)
                TL = cards.layout(tov, th, W, H, fps)
                rec["items"] = TL["items"]   # 只要文字，不要底板
                if TL.get("shapes"):         # 标题上方的强调色短线：透明图层，画在框之上
                    sp, sm = draw.make_plate({"w": W, "h": H, "radius": 0, "fill": None, "alpha": 0.0,
                                              "border": {"w": 0}, "shadow": {}, "shapes": TL["shapes"]},
                                             os.path.join(work, "plates"))
                    inputs.append(["-loop", "1", "-t", "%.3f" % dur, "-i", os.path.relpath(sp, work)])
                    rec["post_layers"] = [{"idx": idx, "x": "-%d" % sm, "y": "-%d" % sm, "t0": t0, "t1": t1,
                                           "scale": None, "di": DEF_DI, "do": DEF_DO, "fade": True}]
                    idx += 1
            fr["blur_bg"] = not paper
            fr["bg_layers"] = [bg_layer] if star else []   # 星空盖在模糊画面之上（半透明）
            prepared.append(rec)
            continue
        if typ == "cta_box":   # 评论框：白底长条＋头像圆点＋发送键（打完字那一刻亮起来）＋闪动游标
            th = theme.theme(ov.get("style") or sb.get("style"), sb.get("_base"), sb.get("brand"))
            bx, by = int(W * float(ov["x"])), int(H * float(ov["y"]))
            bw, bh = int(W * float(ov["w"])) & ~1, int(H * float(ov["h"])) & ~1
            av = int(bh * 0.62)
            sd = int(bh * 0.70)
            send_at = float(ov["send_at"])
            rec = {"ov": ov, "t0": t0, "t1": t1, "under": False, "behind": False, "layers": [],
                   "items": [], "cutout": None}
            for lit, la, lb in ((False, t0, send_at), (True, send_at, t1)):
                if lb - la <= 0.01:
                    continue
                shapes = [{"x": int(bh * 0.19), "y": (bh - av) // 2, "w": av, "h": av, "r": av // 2,
                           "fill": "#E7E7EC"},
                          {"x": bw - sd - int(bh * 0.19), "y": (bh - sd) // 2, "w": sd, "h": sd, "r": sd // 2,
                           "fill": th["accent"] if lit else "#DCDCE2"}]
                png, m = draw.make_plate({"w": bw, "h": bh, "radius": bh // 2, "fill": "#FFFFFF", "alpha": 1.0,
                                          "border": {"w": 0},
                                          "shadow": {"soft": int(bh * 0.30), "alpha": 0.34, "dy": int(bh * 0.10)},
                                          "shapes": shapes,
                                          "icons": [{"name": "arrow_right",
                                                     "x": bw - sd - int(bh * 0.19) + sd // 2 - int(sd * 0.27),
                                                     "y": (bh - sd) // 2 + sd // 2 - int(sd * 0.27),
                                                     "size": int(sd * 0.54),
                                                     "color": "#1E1B16" if lit else "#9A9AA4", "stroke": 3.0}]},
                                         os.path.join(work, "plates"))
                inputs.append(["-loop", "1", "-t", "%.3f" % max(0.1, lb - la), "-i", os.path.relpath(png, work)])
                rise = int(round(H * 0.012))
                rec["layers"].append({"idx": idx, "x": "%d" % (bx - m),
                                      "y": "%d+(%d)*(1-%s)" % (by - m, rise, ease(t0, DEF_DI)) if not lit
                                           else "%d" % (by - m),
                                      "t0": la, "t1": lb, "scale": None,
                                      "di": 0.0 if lit else DEF_DI, "do": DEF_DO if lit else 0.0,
                                      "fade": not lit})
                idx += 1
            # 游标：打完字之后在字尾闪动（打字途中不画，省一层也不抢眼）
            cw = max(3, int(W * 0.005))
            ch = max(8, int(H * float(ov.get("caret_h", 0.03))))
            kx = int(W * float(ov["caret_x"]))
            png, m = draw.make_plate({"w": cw, "h": ch, "radius": cw // 2, "fill": th["accent"], "alpha": 1.0,
                                      "border": {"w": 0}, "shadow": {}}, os.path.join(work, "plates"))
            inputs.append(["-loop", "1", "-t", "%.3f" % max(0.1, t1 - send_at), "-i", os.path.relpath(png, work)])
            rec["layers"].append({"idx": idx, "x": "%d" % (kx - m), "y": "%d" % (by + (bh - ch) // 2 - m),
                                  "t0": send_at, "t1": t1, "scale": None, "di": 0.0, "do": 0.0, "fade": False,
                                  "pre": "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
                                         "a='alpha(X,Y)*(0.5+0.5*sin(2*PI*T/0.9))'"})
            idx += 1
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
        if typ in ("proof_img", "ring", "confetti", "glow"):
            rec = {"ov": ov, "t0": t0, "t1": t1, "under": bool(ov.get("under_captions")), "behind": False,
                   "layers": [], "items": [], "cutout": None}
            th = theme.theme(ov.get("style") or sb.get("style"), sb.get("_base"), sb.get("brand"))
            if typ == "proof_img":   # 白框截图（合成一次、缓存）：淡入＋轻轻上浮
                bd = max(3, int(round(W * float(ov["bf"]))))
                png, m = framed_image(os.path.normpath(os.path.join(sb.get("_base", ""), ov["file"])),
                                      int(W * float(ov["wf"])) & ~1, int(H * float(ov["hf"])) & ~1, bd,
                                      th["radius"], work)
                inputs.append(["-loop", "1", "-t", "%.3f" % dur, "-i", os.path.relpath(png, work)])
                y0 = int(H * float(ov["yf"])) - m
                rise = int(round(H * 0.018))
                rec["layers"].append({"idx": idx, "x": "%d" % (int(W * float(ov["xf"])) - m),
                                      "y": "%d+(%d)*(1-%s)" % (y0, rise, ease(t0, DEF_DI)), "t0": t0, "t1": t1,
                                      "scale": None, "di": DEF_DI, "do": DEF_DO, "fade": True})
            elif typ == "ring":      # 倒数圆环：每秒从满圈缩到空
                S = int(round(W * float(ov.get("size", 0.34)))) & ~1
                inputs.append(["-f", "lavfi", "-t", "%.3f" % dur, "-i", ring_src(S, fps, th["accent"])])
                rec["layers"].append({"idx": idx, "x": "%d" % int(W * float(ov["cx"]) - S / 2),
                                      "y": "%d" % int(H * float(ov["cy"]) - S / 2), "t0": t0, "t1": t1,
                                      "scale": None, "di": 0.2, "do": 0.2, "fade": True})
            elif typ == "confetti":  # 拉炮彩带：逐帧生成的粒子
                cols = ov.get("colors_list") or [th["accent"], th.get("value") or "#35C46A", "#FFFFFF", "#F5C542",
                                                 "#FF5C7A", "#4CC3FF"]
                pat, nfr = fx.confetti(W // 2, H // 2, fps, cols, float(ov.get("dur", min(2.6, dur))),
                                       float(ov.get("x", 0.5)), float(ov.get("y", 0.62)))
                inputs.append(["-framerate", str(fps), "-i", pat])
                rec["layers"].append({"idx": idx, "x": "0", "y": "0", "t0": t0, "t1": min(t1, t0 + nfr / float(fps)),
                                      "scale": W, "di": 0.0, "do": 0.0, "fade": False})
            else:                    # 关注框：强调色发光外框，一呼一吸
                bx, by, bw, bh = [float(v) for v in ov.get("box", [0.1, 0.55, 0.8, 0.11])]
                col = ov.get("color") or th["accent"]
                png, m = glow_png(int(W * bw), int(H * bh), max(4, int(W * 0.007)), col, int(W * 0.024), work)
                inputs.append(["-loop", "1", "-t", "%.3f" % dur, "-i", os.path.relpath(png, work)])
                rec["layers"].append({"idx": idx, "x": "%d" % (int(W * bx) - m), "y": "%d" % (int(H * by) - m),
                                      "t0": t0, "t1": t1, "scale": None, "di": 0.25, "do": 0.25, "fade": True,
                                      "pre": "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
                                             "a='alpha(X,Y)*(0.62+0.38*sin(2*PI*T/%.2f))'" % float(ov.get("pulse", 1.1))})
            idx += 1
            prepared.append(rec)
            continue
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
            if sb.get("avoid_face", True):
                off = float(sb.get("_faces_off", 0.0))
                fc = [(t - off, f) for t, f in sb.get("_faces") or []]
                ov = face_lift(ov, th, W, H, fps, fc)
            L = cards.layout(ov, th, W, H, fps)
            fl = L.get("float") if sb.get("float", True) else None
            fe = float_expr(fl)
            for it_ in L["items"]:
                it_["float"] = fl
            rec["th"], rec["engine"] = th, th.get("text_engine", "drawtext")
            loose = list(L.get("icons") or [])
            if L["plate"]:
                p = L["plate"]
                bleed = bool(ov.get("bleed"))
                bleed_bg = ov.get("_bleed_bg") or th.get("bleed_bg")
                if bleed and bleed_bg in ("starfield", "mesh"):
                    # 整屏断章换成动态背景（循环素材，按卡片时长截取）：星空跃迁或网状渐层
                    if bleed_bg == "mesh":
                        clip = fx.mesh(W, H, fps, mesh_colors(th), float(th.get("mesh_seconds", 6.0)),
                                       base=th["plate"][-1] if isinstance(th["plate"], (list, tuple)) else th["plate"])
                    else:
                        clip = fx.starfield(W, H, fps, th.get("accent", "#E60012"), th.get("accent2", "#FF6A1A"))
                    inputs.append(["-stream_loop", "-1", "-t", "%.3f" % dur, "-i", clip])
                    rec["layers"].append({"idx": idx, "x": "0", "y": "0", "t0": t0, "t1": t1, "scale": None,
                                          "di": p["di"], "do": p["do"], "fade": True,
                                          "opacity": float(ov.get("_bleed_alpha",
                                                                   th.get("starfield_alpha", 1.0)))})
                    idx += 1
                else:
                    baked = [ic for ic in loose if abs(ic["t0"] - t0) < 1e-6]
                    loose = [ic for ic in loose if abs(ic["t0"] - t0) >= 1e-6]
                    spec = {k: p[k] for k in ("w", "h", "radius", "fill", "alpha", "border", "shadow")}
                    for k in ("sheen", "pattern", "topbar", "corners"):   # 顶部高光与风格签名底纹
                        if p.get(k):
                            spec[k] = p[k]
                    if p.get("scrim"):
                        spec["scrim"] = p["scrim"]
                    if baked:
                        spec["icons"] = [{"name": ic["name"], "x": round(ic["x"] - p["x"], 1),
                                          "y": round(ic["y"] - p["y"], 1), "size": ic["size"],
                                          "color": ic["color"], "badge": ic.get("badge"),
                                          "style": ic.get("style", "line")} for ic in baked]
                    if L.get("stars"):
                        spec["stars"] = [dict(st_, cx=round(st_["cx"] - p["x"], 1), cy=round(st_["cy"] - p["y"], 1))
                                         for st_ in L["stars"]]
                    if L.get("arcs"):
                        spec["arcs"] = [dict(ac, cx=round(ac["cx"] - p["x"], 1), cy=round(ac["cy"] - p["y"], 1))
                                        for ac in L["arcs"]]
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
                    s_ = ease(t0, p["di"], p.get("curve") or "smooth")
                    x = "%d" % (p["x"] - margin)
                    y = "%d" % (p["y"] - margin)
                    if p["dx"]:
                        x = "%s+(%d)*(1-%s)" % (x, p["dx"], s_)
                    if p["dy"]:
                        y = "%s+(%d)*(1-%s)" % (y, p["dy"], s_)
                    y += fe
                    rec["layers"].append({"idx": idx, "x": x, "y": y, "t0": t0, "t1": t1,
                                          "scale": None, "di": p["di"], "do": p["do"], "fade": True})
                    idx += 1
                    sweep_cfg = (th.get("signature") or {}).get("sweep")
                    if th.get("laser"):   # 旧写法：laser／laser_color 等同签名扫光
                        sweep_cfg = {"color": th.get("laser_color", "#FFFFFF"), "peak": 0.30}
                    if sweep_cfg and ov.get("laser", typ in ("title", "stat")) and not pill:
                        # 签名扫光：卡片落定后一道光带扫过，只在主卡（标题／数据）上
                        pat, nfr = fx.sweep(p["w"], p["h"], float(p["radius"]), fps,
                                            sweep_cfg.get("color", "#FFFFFF"),
                                            float(sweep_cfg.get("peak", 0.22)))
                        st = t0 + p["di"]
                        inputs.append(["-framerate", str(fps), "-i", pat])
                        rec["layers"].append({"idx": idx, "x": "%d" % p["x"], "y": "%d" % p["y"], "t0": st,
                                              "t1": min(t1, st + nfr / float(fps)), "scale": None,
                                              "di": 0.0, "do": 0.0, "fade": False})
                        idx += 1
            gg_ = L.get("gauge")
            if gg_:   # 进度圈：一层会动的圆环，跟着卡片一起进场
                src = gauge_src(int(gg_["size"]), fps, gg_["color"], gg_["track"], gg_["w"],
                                float(gg_["ratio"]), gg_["t0"], float(gg_["dur"]))
                inputs.append(["-f", "lavfi", "-t", "%.3f" % max(0.2, gg_["t1"] - gg_["t0"]), "-i", src])
                rec["layers"].append({"idx": idx, "x": "%d" % gg_["x"], "y": "%d" % gg_["y"],
                                      "t0": gg_["t0"], "t1": gg_["t1"], "scale": None,
                                      "di": gg_["di"], "do": gg_["do"], "fade": True})
                idx += 1

            ph = L.get("photo")
            if ph:   # 头像牌：强调色圆（外圈）＋圆形照片，跟卡片同时进场
                f = os.path.normpath(os.path.join(sb.get("_base", ""), ph["file"]))
                if not os.path.isfile(f):
                    raise FileNotFoundError("头像牌找不到照片：%s" % f)
                ring = max(3, round(ph["size"] * 0.035))
                rp, rm = draw.make_plate({"w": ph["size"] + 2 * ring, "h": ph["size"] + 2 * ring,
                                          "radius": ph["size"] / 2.0 + ring, "fill": ph["ring"], "alpha": 1.0,
                                          "border": {"w": 0},
                                          "shadow": {"soft": 16, "alpha": 0.40, "dy": 5, "color": "#000000"}},
                                         os.path.join(work, "plates"))
                cp = circle_photo(f, ph["size"], ph["focus"], os.path.join(work, "plates"))
                for png, off in ((rp, ring + rm), (cp, 0)):
                    inputs.append(["-loop", "1", "-t", "%.3f" % dur, "-i", os.path.relpath(png, work)])
                    s_ = ease(t0, ph["di"])
                    x = "%d" % (ph["x"] - off)
                    y = "%d" % (ph["y"] - off)
                    if ph["dx"]:
                        x = "%s+(%d)*(1-%s)" % (x, ph["dx"], s_)
                    if ph["dy"]:
                        y = "%s+(%d)*(1-%s)" % (y, ph["dy"], s_)
                    y += fe
                    rec["layers"].append({"idx": idx, "x": x, "y": y, "t0": t0, "t1": t1, "scale": None,
                                          "di": ph["di"], "do": ph["do"], "fade": True})
                    idx += 1
            spk = L.get("sparkle") if sb.get("sparkle", True) else None
            for sp in (spk or {}).get("spots", []):   # 闪光：四角星序列帧，一次性
                pat, nfr, cv = fx.sparkle(sp["size"], fps, spk["color"])
                if sp["t"] + nfr / float(fps) > t1:
                    continue
                inputs.append(["-framerate", str(fps), "-i", pat])
                rec["layers"].append({"idx": idx, "x": "%d" % int(sp["cx"] - cv / 2), "y": "%d" % int(sp["cy"] - cv / 2),
                                      "t0": sp["t"], "t1": sp["t"] + nfr / float(fps), "scale": None,
                                      "di": 0.0, "do": 0.0, "fade": False})
                idx += 1
            for ic in loose:  # 错峰出现的图标：单独一层，跟着自己那一行的时间进场
                png = icons.make_png(ic["name"], ic["size"], ic["color"], os.path.join(work, "plates"),
                                     badge=ic.get("badge"), style=ic.get("style", "line"))
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
                y += fe
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
            # 遮罩档是 mkv（时基 1/1000）：直接 tpad 补秒数会把每帧当 33ms 算，越后面的段落遮罩越超前
            # （45 秒处约早 14 帧，头冲出框的部分就和画面错开）。先 fps 换成整帧时基，再按帧数补到起点
            m = ("[%d:v]format=gray,fps=%s,tpad=start=%d:start_mode=add:color=black,"
                 "scale=%d:%d" % (sj["idx"], fps, int(math.ceil(sj["a"] * fps - 1e-6)), W, H))
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
            src = f["branch"]
            if f.get("blur_bg"):   # 背景：同一段画面放大、模糊、压暗，比纯色底有层次，也和画面连在一起
                parts.append("[%s]split=2[fsA%d][fsB%d]" % (src, k, k))
                dk = 0.62 if f.get("bg_layers") else 0.34   # 上面还要盖一层半透明星空：画面少压一点
                parts.append("[fsB%d]scale=%d:%d,gblur=sigma=28,lutrgb=r=val*%.2f:g=val*%.2f:b=val*%.2f,"
                             "format=yuva444p,%s[fbg%d]"
                             % (k, W // 4 * 2, H // 4 * 2, dk, dk, dk + 0.02,
                                fadeA(rec["t0"], rec["t1"], DEF_DI, DEF_DO), k))
                parts.append("[fbg%d]scale=%d:%d[fbs%d]" % (k, W, H, k))
                put("fbs%d" % k, "0", "0", rec["t0"], rec["t1"])
                src = "fsA%d" % k
            for lay in f.get("bg_layers") or []:
                n[0] += 1
                d = max(0.1, lay["t1"] - lay["t0"])
                pre = "[%d:v]format=rgba" % lay["idx"]
                if lay.get("opacity", 1.0) < 0.999:
                    pre += ",colorchannelmixer=aa=%.3f" % lay["opacity"]
                pre += (",fade=t=in:st=0:d=%.3f:alpha=1,fade=t=out:st=%.3f:d=%.3f:alpha=1,setpts=PTS+%.3f/TB[bgl%d]"
                        % (lay["di"], max(0.0, d - lay["do"]), lay["do"], lay["t0"], n[0]))
                parts.append(pre)
                put("bgl%d" % n[0], lay["x"], lay["y"], lay["t0"], lay["t1"])
            parts.append("[%s]scale=%d:%d,crop=%d:%d:%d:%d,format=yuva444p[fv%d]"
                         % (src, f["vw"], f["vh"], f["bw"], f["bh"], f["cx"], f["cy"], k))
            parts.append("[%d:v]alphaextract,crop=%d:%d:%d:%d[fm%d]"
                         % (f["mask"], f["bw"], f["bh"], f["mm"], f["mm"], k))
            parts.append("[fv%d][fm%d]alphamerge,%s[ff%d]"
                         % (k, k, fadeA(rec["t0"], rec["t1"], DEF_DI, DEF_DO), k))
            put("ff%d" % k, "%d" % f["bx"], "%d" % f["by"], rec["t0"], rec["t1"])
            if f["subject"] is not None:   # 人物：同样缩放，只保留框底以上 → 头冲出框上缘
                parts.append("[%s]scale=%d:%d,crop=%d:%d:%d:0[fpv%d]"
                             % (subj_lab[f["subject"]], f["vw"], f["vh"], f["bw"], f["cy"] + f["bh"],
                                f["cx"], k))
                # 人物的去背遮罩再乘上框的圆角剪裁：框里的边缘才不会是方角
                parts.append("[fpv%d]split=2[fpa%d][fpb%d]" % (k, k, k))
                parts.append("[fpa%d]alphaextract[fpm%d]" % (k, k))
                parts.append("[%d:v]alphaextract,crop=%d:%d:%d:%d[fcm%d]"
                             % (f["clip"], f["bw"], f["cy"] + f["bh"], f["cmg"], f["cmg"], k))
                parts.append("[fpm%d][fcm%d]blend=all_mode=multiply[fpmm%d]" % (k, k, k))
                parts.append("[fpb%d][fpmm%d]alphamerge,%s[fp%d]"
                             % (k, k, fadeA(rec["t0"], rec["t1"], DEF_DI, DEF_DO), k))
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
                if lay.get("pre"):
                    pre += "," + lay["pre"]
                if lay.get("opacity", 1.0) < 0.999:   # 半透明（otg 星空：看得到底下的画面）
                    pre += ",colorchannelmixer=aa=%.3f" % lay["opacity"]
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
            for lay in rec.get("post_layers") or []:
                n[0] += 1
                lab = "pl%d" % n[0]
                d = max(0.1, lay["t1"] - lay["t0"])
                parts.append("[%d:v]format=rgba,fade=t=in:st=0:d=%.3f:alpha=1,fade=t=out:st=%.3f:d=%.3f:alpha=1,"
                             "setpts=PTS+%.3f/TB[%s]" % (lay["idx"], lay["di"], max(0.0, d - lay["do"]), lay["do"],
                                                         lay["t0"], lab))
                put(lab, lay["x"], lay["y"], lay["t0"], lay["t1"])
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
