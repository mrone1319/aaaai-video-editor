"""画面调色（look）：给口播画面本身套一层统一的电影感，卡片与字幕不受影响。

目前一套：cozy —— Warm & Cozy Cinematic Vlog（暖调居家电影感博主风）
  - 低对比曲线、暗部微抬成暖褐（不出现死黑）、高光柔和压下来
  - 肤色红润通透微偏暖（红＞绿＞蓝 分通道抬起）
  - 1/4 黑柔：只取高光做大半径柔光再叠回去，灯与窗光会晕开，脸不糊
  - 微弱 35mm 胶片颗粒（随时间变化）、极轻暗角（放在抬黑之前，四角不会压成死黑）
  - 选做 bokeh：用人像遮罩把背景虚化（模拟 50mm f/1.4 浅景深），背景再偏暖一点（像 3000K 落地灯）

storyboard 写法：
  "look": "cozy"                                   ← 用默认强度
  "look": {"name": "cozy", "strength": 0.6, "grain": 0.5, "bloom": 0.8, "bokeh": true}
  "look": false                                    ← 关掉（风格自带 look 时也关）
风格（theme）可以带 "look": "cozy"，选了那套风格就自动套用。

实测踩过的坑：eq（对比／饱和）是 YUV 滤镜，放在 RGB（gbrp）里会把绿色通道当亮度，整片偏品红；
所以饱和度在 YUV 里先调，对比度交给曲线。暗角若放在抬黑之后，会把四周又压回死黑。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# 每个通道的曲线控制点 (输入, 输出)，strength=1 时的完整效果；strength 在原样与它之间线性插值
LOOKS: Dict[str, dict] = {
    "cozy": {
        "desc": "暖调居家电影感：低对比、暗部暖褐不死黑、肤色红润微暖、黑柔柔光、细颗粒",
        "curves": {
            "r": [(0, 0.070), (0.25, 0.290), (0.5, 0.530), (0.8, 0.800), (1, 0.965)],
            "g": [(0, 0.055), (0.25, 0.270), (0.5, 0.505), (0.8, 0.785), (1, 0.950)],
            "b": [(0, 0.040), (0.25, 0.240), (0.5, 0.470), (0.8, 0.750), (1, 0.920)],
        },
        "saturation": 1.04,
        "bloom": {"threshold": 0.60, "sigma": 0.028, "opacity": 0.25},   # sigma 按画面短边的比例
        "grain": 7.0,
        "vignette": 0.45,           # 0～1，对应 vignette 角度 0～PI/4
        "bokeh": {"sigma": 0.012, "warm": 3200, "warm_mix": 0.30, "lift": 0.04},
    },
}
DEFAULT = "cozy"


def resolve(sb: dict, th: Optional[dict] = None) -> Optional[dict]:
    """剪辑表的 look 设定（或风格自带的 look）→ 完整参数；没有就 None。"""
    raw = sb.get("look", None)
    if raw is False:
        return None
    if raw is None or raw is True:
        raw = (th or {}).get("look") if raw is None else DEFAULT
        if not raw:
            return None
    spec = {"name": raw} if isinstance(raw, str) else dict(raw)
    name = spec.get("name") or DEFAULT
    if name not in LOOKS:
        raise ValueError("没有这个画面调色：%s（可用：%s）" % (name, " ".join(LOOKS)))
    base = LOOKS[name]

    def f(k, d=1.0):
        v = spec.get(k, d)
        return max(0.0, min(2.0, float(v)))

    bk = spec.get("bokeh", False)
    return {"name": name, "base": base, "strength": f("strength"), "grain": f("grain"), "bloom": f("bloom"),
            "vignette": f("vignette"),
            "bokeh": (0.0 if not bk else (1.0 if bk is True else max(0.0, min(3.0, float(bk)))))}


def _curve(points: List[Tuple[float, float]], s: float) -> str:
    return " ".join("%.4g/%.4f" % (x, max(0.0, min(1.0, x + (y - x) * s))) for x, y in points)


def grade(lk: dict) -> str:
    """单进单出的调色（不含柔光与颗粒）：YUV 里调饱和度 → RGB 曲线。暗角在最前面。
    暗角与饱和度直接在进来的格式上做（实测在 yuv444p 上做暗角慢一倍）。"""
    b, s = lk["base"], lk["strength"]
    out = []
    if lk["vignette"] > 0 and b.get("vignette"):
        out.append("vignette=angle=%.4f" % (0.7853981 * b["vignette"] * min(1.0, lk["vignette"] * s)))
    sat = 1.0 + (b.get("saturation", 1.0) - 1.0) * s
    if abs(sat - 1.0) > 1e-3:
        out.append("eq=saturation=%.3f" % sat)
    c = b["curves"]
    out.append("format=gbrp,curves=r='%s':g='%s':b='%s'" % (_curve(c["r"], s), _curve(c["g"], s), _curve(c["b"], s)))
    return ",".join(out)


def _blur(sigma: float, w: int, h: int) -> str:
    """大半径模糊：先缩小四倍再模糊、再放大回来。看起来和全尺寸模糊一样，快好几倍。"""
    k = 4 if sigma >= 8 else 1
    if k == 1:
        return "gblur=sigma=%.1f" % sigma
    return "scale=%d:%d,gblur=sigma=%.1f,scale=%d:%d:flags=bicubic" % (
        max(2, (w // k) & ~1), max(2, (h // k) & ~1), sigma / k, w, h)


def graph(lk: dict, src: str, dst: str, w: int, h: int, tag: str = "lk",
          matte: Optional[str] = None) -> str:
    """完整的调色滤镜图：[src] → [dst]。matte：人像遮罩标签（灰度、已对齐成片）——有就做背景虚化。"""
    b = lk["base"]
    short = min(w, h)
    parts = []
    cur = src
    if matte and lk["bokeh"] > 0 and b.get("bokeh"):
        bk = b["bokeh"]
        sig = max(1.0, short * bk["sigma"] * lk["bokeh"])
        # 背景：大半径模糊（浅景深）＋偏暖、亮部略抬（像画面外有一盏暖色落地灯）
        parts.append("%ssplit[%s_fg][%s_bg]" % (cur, tag, tag))
        parts.append("[%s_bg]%s,colortemperature=temperature=%d:mix=%.2f,"
                     "curves=all='0/0 0.5/%.3f 1/1'[%s_bgb]"
                     % (tag, _blur(sig, w, h), bk["warm"], bk["warm_mix"], 0.5 + bk["lift"], tag))
        parts.append("[%s_fg]%salphamerge[%s_subj]" % (tag, matte, tag))
        parts.append("[%s_bgb][%s_subj]overlay=format=auto[%s_dof]" % (tag, tag, tag))
        cur = "[%s_dof]" % tag
    parts.append("%s%s[%s_g]" % (cur, grade(lk), tag))
    cur = "[%s_g]" % tag
    bl = b.get("bloom")
    if bl and lk["bloom"] > 0:
        # 黑柔：只取高光（阈值以上）→ 大半径模糊 → 用 screen 叠回去
        parts.append("%ssplit[%s_a][%s_b]" % (cur, tag, tag))
        parts.append("[%s_b]curves=all='0/0 %.3f/0 1/1',%s[%s_h]"
                     % (tag, bl["threshold"], _blur(max(2.0, short * bl["sigma"]), w, h), tag))
        parts.append("[%s_a][%s_h]blend=all_mode=screen:all_opacity=%.3f[%s_bl]"
                     % (tag, tag, min(1.0, bl["opacity"] * lk["bloom"] * lk["strength"]), tag))
        cur = "[%s_bl]" % tag
    g = b.get("grain", 0) * lk["grain"]
    if g > 0.2:
        # 颗粒的尺寸要跟着画面走：预览（半分辨率）颗粒也减半，看起来和成片一样
        n = max(1, int(round(g * short / 1080.0)))
        parts.append("%snoise=c0s=%d:c1s=%d:c2s=%d:allf=t[%s_n]" % (cur, n, n, n, tag))
        cur = "[%s_n]" % tag
    parts.append("%sformat=yuv444p%s" % (cur, dst))
    return ";".join(parts)


def simple(lk: dict) -> str:
    """单链版（不含柔光、颗粒、背景虚化）：只烧字幕的快速预览用。"""
    return grade(lk) + ",format=yuv420p"
