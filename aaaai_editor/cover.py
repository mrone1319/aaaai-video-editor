"""封面：从原片取干净的一帧（没有字幕、卡片），先给用户挑候选，再排版。

两步：
  1. candidates()：自动挑 6～8 张适合当封面的画面（清楚、脸大小适中、没在大动作），拼成编号总表给用户挑；
  2. make()：用挑中的那一帧排版，出 9:16 与 4:5（横版片出 16:9），检查有没有压脸、会不会被主页裁掉。

版式：
  signature（默认，所有风格通用）：左对齐一整块——小标签（强调色、字距拉宽）→ 大标题（特粗、强调色，
    一行放得下就一行，放不下才在最自然的地方断成两行）→ 第三行说明（白色粗体）→ 账号名（强调色）；
    画面下半部压一层暗黑渐层托住文字，文字块放在下巴以下。
  center：居中的大标题＋一行说明＋账号名（简洁版）。
账号名读用户自己的设定（config 的 handle）；没设定就不印。
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from typing import List, Optional, Tuple

from . import config, draw, env, fonts, render, theme
from .timeline import Timeline

SAFE = 0.15                                    # Instagram 主页 4:5／1:1 裁切：四周各留 15%
PUNCT = "，,、：:；;！!？?。．. 　 ｜|—-"
BAD_END = "被把将在和与跟对从向给让是也都就还及或而为于第每"    # 这些字留在行尾读起来断得很怪（介词、连词、前缀）
BAD_START = "了的着过吗呢吧啊呀们地得么"                           # 这些字不能开新的一行
CANDIDATES = "work/cover_candidates.json"


# ---------------------------------------------------------------- 取帧
def _hdr(sb: dict) -> bool:
    try:
        return bool(env.probe(sb["source"]).get("hdr"))
    except env.ToolError:
        return False


def clean_frame(sb: dict, t: float, W: int, H: int, out: str) -> str:
    """成片时间 t 的画面，但从原片取：套用同样的剪辑、推近与 HDR 调色，没有字幕、卡片。"""
    tl = Timeline([tuple(c) for c in sb["cuts"]], sb["output"]["fps"])
    st = tl.to_source(max(0.0, min(t, tl.duration - 0.05)))
    pre, fit = render.frame_chain(W, H, sb.get("framing"), _hdr(sb))
    env.run([env.ffmpeg(), "-y", "-v", "error", "-ss", "%.3f" % st, "-i", sb["source"], "-frames:v", "1",
             "-vf", pre + fit, out])
    return out


def _sharpness(g: bytes, w: int, h: int) -> float:
    """拉普拉斯变异数：越大越清楚（手晃、动作大的帧会糊）。"""
    tot = tot2 = 0.0
    n = 0
    for y in range(1, h - 1, 2):
        r = y * w
        for x in range(1, w - 1, 2):
            v = 4 * g[r + x] - g[r + x - 1] - g[r + x + 1] - g[r - w + x] - g[r + w + x]
            tot += v
            tot2 += v * v
            n += 1
    m = tot / max(1, n)
    return tot2 / max(1, n) - m * m


def candidates(sb_path: str, n: int = 8) -> Tuple[str, List[dict]]:
    """挑 n 张候选封面帧，拼成编号总表。回传 (总表图, 候选清单)。"""
    from . import faces as faces_mod
    sb = render.load_storyboard(sb_path)
    fps = sb["output"]["fps"]
    tl = Timeline([tuple(c) for c in sb["cuts"]], fps)
    ow, oh = int(sb["output"]["width"]), int(sb["output"]["height"])
    try:
        fc = {round(t, 2): f for t, f in faces_mod.track(sb, tl, ow, oh)}
    except (env.ToolError, OSError):
        fc = {}
    # 每 0.5 秒一张小灰阶图：算清晰度、和前一张的差异（大动作）
    sw, sh = 96, int(96 * oh / float(ow)) & ~1
    pre, fit = render.frame_chain(sw, sh, sb.get("framing"), _hdr(sb))
    rows = []
    for (ca, _cb), off, ln in zip(tl.cuts, tl.offsets, tl.lengths):
        k = max(1, int(ln / 0.5))
        raw = subprocess.run([env.ffmpeg(), "-v", "error", "-ss", "%.3f" % (ca + 0.25), "-t", "%.3f" % ln, "-i",
                              sb["source"], "-vf", "fps=2,%s%s" % (pre, fit), "-frames:v", str(k), "-f", "rawvideo",
                              "-pix_fmt", "gray", "-"], capture_output=True).stdout
        prev = None
        for i in range(len(raw) // (sw * sh)):
            g = raw[i * sw * sh:(i + 1) * sw * sh]
            t = round(off + 0.25 + i * 0.5, 2)
            motion = (sum(abs(a - b) for a, b in zip(g[::7], prev[::7])) / (len(g) / 7.0)) if prev else 0.0
            rows.append({"t": t, "sharp": _sharpness(g, sw, sh), "motion": motion, "face": fc.get(t)})
            prev = g
    if not rows:
        raise env.ToolError("取不到画面")
    top_sharp = sorted(r["sharp"] for r in rows)[int(len(rows) * 0.9)] or 1.0
    dur = tl.duration
    for r in rows:
        s = min(1.0, r["sharp"] / top_sharp) - min(0.5, r["motion"] / 40.0)
        f = r["face"]
        if f:   # 脸在上半部、大小适中（太小＝人太远，太大＝贴脸）最适合放字
            top, chin = f
            s += 0.6 - 1.5 * abs(top - 0.22) - 1.2 * max(0.0, abs((chin - top) - 0.2) - 0.06)
        elif fc:
            s -= 0.8   # 有人像资料但这帧没认出人：多半是转头、离开画面
        if r["t"] < 0.4 or r["t"] > dur - 0.8:
            s -= 1.0
        r["score"] = s
    picked: List[dict] = []
    for r in sorted(rows, key=lambda x: -x["score"]):
        if all(abs(r["t"] - p["t"]) >= max(1.5, dur / (n * 2.5)) for p in picked):
            picked.append(r)
        if len(picked) >= n:
            break
    picked.sort(key=lambda r: r["t"])
    work = os.path.join(sb["_base"], "work")
    os.makedirs(work, exist_ok=True)
    tw, th = (480, 270) if ow > oh else (270, 480)
    tiles = []
    font = theme.num_font()
    for i, r in enumerate(picked, 1):
        f = os.path.join(work, "cover_cand_%d.png" % i)
        clean_frame(sb, r["t"], tw, th, f)
        lab = os.path.join(work, "cover_cand_%d_l.png" % i)
        env.run([env.ffmpeg(), "-y", "-v", "error", "-i", f, "-vf",
                 "drawbox=x=0:y=0:w=%d:h=%d:color=black@0.55:t=fill,drawtext=fontfile=%s:text='%d':x=14:y=8:"
                 "fontsize=%d:fontcolor=white,drawtext=fontfile=%s:text='%.1fs':x=w-tw-12:y=16:fontsize=%d:"
                 "fontcolor=white@0.85" % (tw, int(th * 0.11), _q(font), i, int(th * 0.085), _q(font), r["t"],
                                           int(th * 0.045)), lab])
        tiles.append(lab)
        r["n"] = i
        os.remove(f)
    cols = 4 if len(tiles) > 4 else len(tiles)
    sheet = os.path.join(work, "cover_candidates.png")
    ins = sum((["-i", t] for t in tiles), [])
    layout = "|".join("%d_%d" % ((i % cols) * tw, (i // cols) * th) for i in range(len(tiles)))
    env.run([env.ffmpeg(), "-y", "-v", "error"] + ins + ["-filter_complex",
            "%sxstack=inputs=%d:layout=%s:fill=black" % ("".join("[%d:v]" % i for i in range(len(tiles))),
                                                         len(tiles), layout), sheet] if len(tiles) > 1
            else [env.ffmpeg(), "-y", "-v", "error", "-i", tiles[0], sheet])
    for t in tiles:
        os.remove(t)
    items = [{"n": r["n"], "t": r["t"]} for r in picked]
    json.dump({"items": items}, open(os.path.join(sb["_base"], CANDIDATES), "w", encoding="utf-8"), indent=1)
    return sheet, items


def _q(s: str) -> str:
    from .overlays import q
    return q(s)


# ---------------------------------------------------------------- 文字量测与断行
def _em(ch: str) -> float:
    o = ord(ch)
    if o > 0x2E80 or ch in "，。！？：；、「」（）":
        return 1.0
    if ch == " ":
        return 0.28
    if ch.isdigit():
        return 0.60
    if ch.isupper():
        return 0.70
    if ch.isalpha():
        return 0.58
    return 0.45


def _w(s: str) -> float:
    return sum(_em(c) for c in s)


def _ascii_word(c: str) -> bool:
    return c.isascii() and (c.isalnum() or c in "$%.,+-_@#")


def split_title(text: str, max_em_one: float) -> List[str]:
    """大标题断行：手动写了 | 或换行就照写的断；一行放得下（按字宽）就一行；
    放不下才找最自然的断点——标点／空格后面优先，不切开英文单词和数字，两行长度尽量均衡。"""
    for sep in ("|", "｜", "\n"):
        if sep in text:
            return [p.strip() for p in text.split(sep) if p.strip()][:3]
    t = text.strip()
    if _w(t) <= max_em_one:
        return [t]
    best, cost = None, 1e9
    for i in range(1, len(t)):
        a, b = t[:i], t[i:]
        if _ascii_word(t[i - 1]) and _ascii_word(t[i]):
            continue                                  # 不切开英文单词／数字
        after_punct = t[i - 1] in PUNCT
        a2, b2 = a.rstrip(PUNCT.replace("！", "").replace("？", "").replace("!", "").replace("?", "")), b.lstrip(" 　")
        if not a2 or not b2:
            continue
        c = max(_w(a2), _w(b2)) + (0.0 if after_punct else 0.9) + 0.15 * abs(_w(a2) - _w(b2))
        c += 1.6 * (a2[-1] in BAD_END) + 1.6 * (b2[0] in BAD_START) + 0.8 * (a2[-1] == "的")
        c += 2.0 * (a2.rstrip()[-1:].isdigit() and ord(b2[0]) > 0x2E80)   # 数字和后面的单位不分开（3｜小时）
        if c < cost:
            best, cost = [a2, b2], c
    return best or [t]


def _wrap(text: str, max_em: float, max_lines: int = 2) -> List[str]:
    out, cur = [], ""
    for ch in text:
        if _w(cur + ch) > max_em and cur:
            out.append(cur.rstrip())
            cur = ch.lstrip() if len(out) < max_lines else cur + ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out[:max_lines]


# ---------------------------------------------------------------- 排版
def _families() -> Tuple[str, str, bool]:
    """(大标题字体, 内文粗体, 是否用了 Noto 特粗)。Noto Sans SC 可变字体在就固化成 900／700，否则退回系统粗体。"""
    src = os.path.join(fonts.FONT_DIR, "NotoSansSC[wght].ttf")
    try:
        if os.path.isfile(src):
            fonts.instance(src, 900, "NotoSansSCBlack")
            fonts.instance(src, 700, "NotoSansSCBold")
            return "NotoSansSCBlack", "NotoSansSCBold", True
    except RuntimeError:
        pass
    f = env.font_family("PingFang SC")
    return f, f, False


def _line(x: float, y: float, an: int, fam: str, size: float, color: str, text: str, bold: bool,
          tracking: float = 0.0, shadow: float = 0.0) -> str:
    from . import richtext
    win, asc, _cap = richtext.metrics(fam)
    tags = "\\an%d\\pos(%.1f,%.1f)\\fn%s\\fs%.1f\\b%d\\c%s\\bord0" % (
        an, x, y - (asc - 0.88) * size, fam, size * win, 1 if bold else 0, richtext._c(color))
    if tracking:
        tags += "\\fsp%.1f" % tracking
    tags += "\\shad%.1f\\4c&H000000&\\4a&H70&" % shadow if shadow else "\\shad0"
    return "Dialogue: 0,0:00:00.00,0:00:05.00,C,,0,0,0,,{%s}%s" % (tags, richtext._esc(text))


def _accent(th: dict, color: Optional[str]) -> str:
    if color:
        return color
    from .cards import _lighten
    pl = th["plate"][-1] if isinstance(th["plate"], (list, tuple)) else th["plate"]
    light = sum(int(pl.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) >= 3 * 128
    return _lighten(th["accent"]) if light else th["accent"]   # 浅色风格的强调色偏深，放在暗影上要提亮


def _face(frame: str, W: int, H: int) -> Optional[Tuple[float, float]]:
    """这一帧的（头顶, 下巴）占画面高的比例；没有人像分割就 None。"""
    try:
        from . import faces, matte
        sw, sh = 144, int(144 * H / float(W)) & ~1
        raw = subprocess.run([env.ffmpeg(), "-v", "error", "-i", frame, "-vf", "scale=%d:%d" % (sw, sh), "-f",
                              "rawvideo", "-pix_fmt", "bgra", "-"], capture_output=True).stdout
        m = subprocess.run(matte.helper_cmd() + [str(sw), str(sh), "accurate"], input=raw, capture_output=True).stdout
        return faces._band(m, sw, sh) if len(m) >= sw * sh else None
    except Exception:
        return None


def _saved(sb_path: str) -> dict:
    try:
        return dict(json.load(open(sb_path, encoding="utf-8")).get("cover") or {})
    except (OSError, ValueError):
        return {}


def _save(sb_path: str, cov: dict) -> None:
    s = json.load(open(sb_path, encoding="utf-8"))
    s["cover"] = cov
    json.dump(s, open(sb_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def make(sb_path: str, at: Optional[float] = None, pick: Optional[int] = None, title: Optional[str] = None,
         kicker: Optional[str] = None, sub: Optional[str] = None, handle: Optional[str] = None,
         layout: Optional[str] = None, color: Optional[str] = None) -> Tuple[List[str], List[str]]:
    """排封面。没给的参数沿用上一次（存在 storyboard 的 cover 里），换字重做不用重挑画面。
    回传 (输出文件, 提醒)。"""
    sb = render.load_storyboard(sb_path)
    cov = _saved(sb_path)
    if pick is not None:
        cp = os.path.join(sb["_base"], CANDIDATES)
        if not os.path.isfile(cp):
            raise env.ToolError("还没有候选封面：先跑 cover-frames")
        hit = [x for x in json.load(open(cp, encoding="utf-8"))["items"] if x["n"] == pick]
        if not hit:
            raise env.ToolError("候选里没有第 %d 张" % pick)
        at = hit[0]["t"]
    for k, v in (("at", at), ("title", title), ("kicker", kicker), ("sub", sub), ("layout", layout), ("color", color)):
        if v is not None:
            cov[k] = v
    if cov.get("at") is None:
        raise env.ToolError("还没选封面画面：先跑 cover-frames 挑一张（--pick 编号），或写 --at 秒数")
    if not cov.get("title"):
        raise env.ToolError("缺大标题：--text「……」")
    lay = cov.get("layout") or "signature"
    ow, oh = int(sb["output"]["width"]), int(sb["output"]["height"])
    landscape = ow > oh
    W, H = (1920, 1080) if landscape else (1080, 1920)
    d = os.path.join(sb["_base"], "out")
    work = os.path.join(sb["_base"], "work")
    os.makedirs(d, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    frame = clean_frame(sb, float(cov["at"]), W, H, os.path.join(work, "cover_frame.png"))
    th = theme.theme(sb.get("style"), sb.get("_base"), sb.get("brand"))
    acc = _accent(th, cov.get("color"))
    fam_t, fam_b, noto = _families()
    handle = config.load().get("handle", "") if handle is None else handle   # 各用户自己的账号名；没设就不印
    warns: List[str] = []
    U = min(W, H * 0.5625)                     # 竖版＝画面宽；横版按高折算
    face = _face(frame, W, H)
    chin = face[1] if face else 0.40

    if lay == "center":
        x, an, text_w = W / 2.0, 8, W * (1 - 2 * SAFE)
    else:
        x, an = (W * SAFE + 0.005 * W) if not landscape else W * 0.07, 7
        text_w = W * (1 - 2 * SAFE) if not landscape else W * 0.50
    ts_max, ts_min = U * 0.125, U * 0.112   # 一行时字至少这么大才不断；再小就断成两行、字放大
    one_line_em = text_w / ts_min
    lines = split_title(cov["title"], one_line_em)
    ts = min(ts_max, text_w / max(_w(l) for l in lines))
    if ts < U * 0.07:
        warns.append("大标题太长（字会很小）：建议缩短到 12 个字以内，或用 | 自己指定断行")
    ks, ss, hs = U * 0.036, U * 0.047, U * 0.036
    sub_lines = _wrap(cov.get("sub") or "", text_w / ss) if cov.get("sub") else []
    kick = cov.get("kicker") or ""
    g1, g2, g3 = U * 0.028, U * 0.030, U * 0.038
    hb = ((ks + g1) if kick else 0) + ts * 1.10 * len(lines) + ((g2 + ss * 1.35 * len(sub_lines)) if sub_lines else 0) \
        + ((g3 + hs) if handle else 0)
    bottom = H * (1 - SAFE) - U * 0.01
    top = max(H * (0.46 if not landscape else 0.40), chin * H + H * 0.03)
    if top + hb > bottom:
        top = bottom - hb
        if face and top < chin * H:
            warns.append("文字块会压到下巴：挑一张人坐得高一点的画面，或把标题缩短")

    # 暗黑渐层：文字块上方一点开始，往下越来越深
    g_top = max(0, int(max(top - H * 0.14, (chin + 0.01) * H if face else 0)))   # 从下巴以下才开始压暗，脸保持明亮
    gh = H - g_top
    hold = max(0.0, min(0.75, (H - top + H * 0.02) / float(gh)))   # 文字区整段都压暗，上面再渐渐透明
    png, m = draw.make_plate({"w": W, "h": gh, "radius": 0, "fill": None, "alpha": 1.0, "border": {"w": 0},
                              "shadow": {}, "scrim": {"color": "#000000", "power": 1.1, "alpha": 0.80,
                                                      "hold": hold, "dir": "up"}}, os.path.join(work, "plates"))
    shaded = os.path.join(work, "cover_shaded.png")
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", frame, "-i", png, "-filter_complex",
             "[0:v][1:v]overlay=%d:%d:format=auto" % (-m, g_top - m), "-frames:v", "1", shaded])

    ass: List[str] = []
    y = top
    if kick:
        ass.append(_line(x, y, an, fam_b, ks, acc, kick, not noto, tracking=ks * 0.28, shadow=ks * 0.06))
        y += ks + g1
    for l in lines:
        ass.append(_line(x, y, an, fam_t, ts, acc, l, not noto, shadow=ts * 0.035))
        y += ts * 1.10
    if sub_lines:
        y += g2
        for l in sub_lines:
            ass.append(_line(x, y, an, fam_b, ss, "#FFFFFF", l, not noto, shadow=ss * 0.06))
            y += ss * 1.35
    if handle:
        y += g3
        ass.append(_line(x, y, an, fam_b, hs, acc, handle, not noto, shadow=hs * 0.06))
    from . import richtext
    af = os.path.join(work, "cover.ass")
    richtext.write(af, W, H, ass)
    full = os.path.join(d, "cover_%dx%d.png" % (W, H))
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", "cover_shaded.png", "-vf",
             "subtitles=filename=cover.ass:fontsdir=%s" % _q(fonts.FONT_DIR), "-frames:v", "1", full], cwd=work)
    _save(sb_path, cov)
    outs = [full]
    check = os.path.join(work, "cover_check.png")
    if landscape:
        env.run([env.ffmpeg(), "-y", "-v", "error", "-i", full, "-vf", "scale=960:540", check])
        outs.append(check)
        ex = [config.export(full, sb["_base"], "-封面")]
    else:
        crop = os.path.join(d, "cover_1080x1350.png")
        env.run([env.ffmpeg(), "-y", "-v", "error", "-i", full, "-vf", "crop=1080:1350:0:285", crop])
        env.run([env.ffmpeg(), "-y", "-v", "error", "-i", full, "-i", crop, "-filter_complex",
                 "[0]scale=540:960[a];[1]scale=540:675,pad=540:960:0:142:black[b];[a][b]hstack", check])
        outs += [crop, check]
        ex = [config.export(full, sb["_base"], "-封面"), config.export(crop, sb["_base"], "-封面-4x5")]
    if not handle:
        warns.append("没有印账号名（设定里没有 handle）：要印就执行 aaaai-editor config --set handle=@你的账号")
    return outs + [e for e in ex if e], warns
