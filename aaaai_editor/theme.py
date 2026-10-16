"""设计令牌：颜色、字体、圆角、投影。

内置六套风格；也可以在仓库或项目目录的 themes/*.json 里加自己的风格（用 "extends" 继承），
或在 storyboard 里用 "brand" 临时覆盖品牌色。

语义色 value／state 来自剪辑公式库的实测结论（4/4 成立）：
绿＝能量／价值色（数据、增长、成就），青＝静息／陈述色（章节、说明、事实）。
"""
from __future__ import annotations

import glob
import json
import os
from functools import lru_cache
from typing import Dict, List, Optional

CJK_FONTS = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyhbd.ttc"),   # Windows：微软雅黑粗体
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttc"),
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simhei.ttf"),
]
NUM_FONTS = [
    os.path.expanduser("~/Library/Fonts/IBMPlexMono-Bold.ttf"),
    os.path.join(os.path.expanduser(os.environ.get("AAAAI_EDITOR_HOME") or "~/.aaaai-editor"), "fonts", "IBMPlexMono-Bold.ttf"),
    os.path.expanduser("~/Library/Fonts/Aptos.ttf"),
    "/System/Library/Fonts/Supplemental/Futura.ttc",
]
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=4)
def _first(paths: tuple) -> Optional[str]:
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


def cjk_font() -> str:
    f = os.environ.get("AAAAI_EDITOR_FONT") or _first(tuple(CJK_FONTS))
    if not f:
        raise RuntimeError("找不到中文字体，设 AAAAI_EDITOR_FONT=/path/to/font.ttc")
    return f


def num_font() -> str:
    return _first(tuple(NUM_FONTS)) or cjk_font()


_DARK_SEM = {"value": "#3DDC84", "state": "#38BDF8"}
_LIGHT_SEM = {"value": "#15803D", "state": "#0E7490"}

BUILTIN: Dict[str, dict] = {
    "ink": dict(_DARK_SEM, **{  # 商业／知识：墨底、米白字、琥珀强调
        "desc": "商业／知识：墨底、米白字、琥珀强调",
        "plate": ["#12161D", "#1B2430"], "plate_alpha": 0.92, "radius": 30,
        "text": "#F6F3EC", "muted": "#9BA6B4", "accent": "#F0B23C", "on_accent": "#14181F",
        "border": {"w": 0, "color": "#2A3442"},
        "shadow": {"soft": 26, "alpha": 0.42, "dy": 10, "color": "#000000"},
        "signature": {"pattern": {"kind": "diag", "color": "#FFFFFF", "alpha": 0.030, "size": 34}},
        "text_engine": "ass", "body_font": "PingFang SC", "mono_font": "IBM Plex Mono",
        "type": {"title": {"bold": 1}, "heading": {"bold": 1}, "quote": {"bold": 1}, "row_title": {"bold": 1},
                 "kicker": {"bold": 1, "upper": 1, "tracking": 0.20}, "stamp": {"bold": 1},
                 "number": {"font": "mono", "bold": 1}, "badge": {"font": "mono", "bold": 1},
                 "name": {"bold": 1}, "item": {"bold": 1}, "row_tag": {"font": "mono", "bold": 1}}}),
    "neon": dict(_DARK_SEM, **{  # Web3：近黑底、青绿强调
        "desc": "Web3：近黑底、青绿强调、细描边",
        "plate": ["#0A0C18", "#141033"], "plate_alpha": 0.90, "radius": 22,
        "text": "#EAF2FF", "muted": "#8C96B8", "accent": "#32E3C2", "on_accent": "#06120F",
        "border": {"w": 2, "color": "#2B3570"},
        "shadow": {"soft": 30, "alpha": 0.50, "dy": 8, "color": "#03030A"},
        "signature": {"pattern": {"kind": "grid", "color": "#7CF5DC", "alpha": 0.055, "size": 26}},
        "text_engine": "ass", "body_font": "PingFang SC", "mono_font": "IBM Plex Mono",
        "type": {"title": {"bold": 1}, "heading": {"bold": 1}, "quote": {"bold": 1}, "row_title": {"bold": 1},
                 "kicker": {"font": "mono", "bold": 1, "upper": 1, "tracking": 0.26}, "stamp": {"bold": 1, "tracking": 0.10},
                 "number": {"font": "mono", "bold": 1}, "badge": {"font": "mono", "bold": 1, "upper": 1},
                 "name": {"bold": 1}, "item": {"bold": 1}, "row_tag": {"font": "mono", "bold": 1}}}),
    "paper": dict(_LIGHT_SEM, **{  # 编辑／印刷：米白底、深墨字、朱红强调
        "desc": "编辑／印刷：米白底、深墨字、朱红强调",
        "plate": ["#F8F4EA", "#EFE7D6"], "plate_alpha": 0.96, "radius": 10,
        "text": "#191512", "muted": "#6B6257", "accent": "#C2452D", "on_accent": "#FFFFFF",
        "border": {"w": 0, "color": "#D8CDB6"},
        "shadow": {"soft": 22, "alpha": 0.30, "dy": 8, "color": "#2A2015"},
        "signature": {"pattern": {"kind": "dots", "color": "#7A6A52", "alpha": 0.075, "size": 11}},
        "text_engine": "ass", "body_font": "PingFang SC", "mono_font": "IBM Plex Mono", "serif_font": "Songti SC",
        "type": {"title": {"font": "serif", "bold": 1}, "heading": {"font": "serif", "bold": 1}, "quote": {"font": "serif", "bold": 1},
                 "kicker": {"bold": 1, "upper": 1, "tracking": 0.18}, "stamp": {"bold": 1},
                 "number": {"font": "mono", "bold": 1}, "badge": {"font": "mono", "bold": 1},
                 "row_title": {"bold": 1}, "name": {"bold": 1}, "item": {"bold": 1}}}),
    # —— 以下三套取自 uupm-design 的产品色板数据 ——
    "gold": dict(_DARK_SEM, **{  # Fintech/Crypto：金色信任 + 紫色科技
        "desc": "金融加密：石板底、金色信任、紫色科技",
        "plate": ["#1A2030", "#222735"], "plate_alpha": 0.93, "radius": 18,
        "text": "#F8FAFC", "muted": "#94A3B8", "accent": "#F59E0B", "on_accent": "#0F172A",
        "accent2": "#8B5CF6", "border": {"w": 2, "color": "#334155"},
        "shadow": {"soft": 28, "alpha": 0.45, "dy": 10, "color": "#020617"},
        "signature": {"sweep": {"color": "#FFE2A8", "peak": 0.16}},
        "text_engine": "ass", "body_font": "PingFang SC", "mono_font": "IBM Plex Mono",
        "type": {"title": {"bold": 1}, "heading": {"bold": 1}, "quote": {"bold": 1}, "row_title": {"bold": 1},
                 "kicker": {"font": "mono", "bold": 1, "upper": 1, "tracking": 0.24}, "stamp": {"bold": 1},
                 "number": {"font": "mono", "bold": 1}, "badge": {"font": "mono", "bold": 1, "upper": 1},
                 "name": {"bold": 1}, "item": {"bold": 1}, "row_tag": {"font": "mono", "bold": 1}}}),
    "trust": dict(_DARK_SEM, **{  # 理财：信任蓝 + 盈利绿
        "desc": "理财／机构：深海军底、信任蓝、盈利绿",
        "plate": ["#101A33", "#192134"], "plate_alpha": 0.93, "radius": 16,
        "text": "#FFFFFF", "muted": "#94A3B8", "accent": "#3B82F6", "on_accent": "#FFFFFF",
        "value": "#10B981", "border": {"w": 1, "color": "#2A3550"},
        "shadow": {"soft": 26, "alpha": 0.45, "dy": 10, "color": "#020617"},
        "signature": {"pattern": {"kind": "grid", "color": "#9CC4FF", "alpha": 0.040, "size": 40}},
        "text_engine": "ass", "body_font": "PingFang SC", "mono_font": "IBM Plex Mono",
        "type": {"title": {"bold": 1}, "heading": {"bold": 1}, "quote": {"bold": 1}, "row_title": {"bold": 1},
                 "kicker": {"bold": 1, "upper": 1, "tracking": 0.22}, "stamp": {"bold": 1},
                 "number": {"font": "mono", "bold": 1}, "badge": {"font": "mono", "bold": 1},
                 "name": {"bold": 1}, "item": {"bold": 1}, "row_tag": {"font": "mono", "bold": 1}}}),
    "mag": dict(_LIGHT_SEM, **{  # 杂志：纯白卡、近黑字、品红强调
        "desc": "杂志／评论：纯白卡、近黑字、品红强调",
        "plate": ["#FFFFFF", "#F4F4F5"], "plate_alpha": 0.97, "radius": 6,
        "text": "#09090B", "muted": "#475569", "accent": "#EC4899", "on_accent": "#FFFFFF",
        "border": {"w": 2, "color": "#E4E4E7"},
        "shadow": {"soft": 24, "alpha": 0.28, "dy": 9, "color": "#18181B"},
        "signature": {"topbar": {"h": 9}},
        "text_engine": "ass", "body_font": "PingFang SC", "mono_font": "IBM Plex Mono",
        "type": {"title": {"bold": 1}, "heading": {"bold": 1}, "quote": {"bold": 1, "italic": 1}, "row_title": {"bold": 1},
                 "kicker": {"bold": 1, "upper": 1, "tracking": 0.30}, "stamp": {"bold": 1, "upper": 1, "tracking": 0.08},
                 "number": {"font": "mono", "bold": 1}, "badge": {"font": "mono", "bold": 1, "upper": 1},
                 "name": {"bold": 1}, "item": {"bold": 1}, "row_tag": {"font": "mono", "bold": 1}}}),
    # —— 以下三套走 libass 富文本（混色高亮、字距、斜体、展示字体）——
    "otg": {  # 依据 otg-dashboard/BRAND.md
        "desc": "OTG 火箭风：深空黑、OTG 红、火焰点缀、红色光晕、毛玻璃、星空断章、激光扫光",
        "plate": ["#121216", "#0A0A0A"], "plate_alpha": 0.40, "radius": 18,   # 毛玻璃：看得穿
        "text": "#FFFFFF", "muted": "#8A8A94", "accent": "#E60012", "on_accent": "#FFFFFF",
        "accent2": "#FF6A1A", "gold": "#FFC01E", "hl": "#FF2A3A", "lite": 0,
        # 品牌规则：翡翠绿只做状态（涨幅／成功）；陈述色用余烬金而不是青
        "value": "#10B981", "state": "#FFC01E",
        "border": {"w": 2, "color": "#6A0A12"},
        "shadow": {"soft": 34, "alpha": 0.55, "dy": 0, "color": "#E60012"},   # 红色光晕
        "glass": {"sigma": 24}, "bleed_bg": "starfield", "starfield_alpha": 0.72, "lite_types": ["lower_third", "avatar"], "laser": True, "laser_color": "#FFE3E3",
        "row": "#16161B", "line": "#2A2A31",
        "text_engine": "ass", "body_font": "PingFang SC", "mono_font": "IBM Plex Mono",
        "display_font": {"file": ["~/Library/Fonts/Orbitron-VariableFont_wght.ttf",
                                  "~/.aaaai-editor/fonts/Orbitron[wght].ttf"], "wght": 900, "name": "OrbitronBlack"},
        "community": {"owner": "OTG 社群", "note": "社群风格：OTG 名称、配色与品牌元素 © OTG 社群；可以使用，请勿用来冒充 OTG"},
        "captions": "otg",
        "type": {"title": {"font": "display", "italic": 1, "upper": 1},
                 "heading": {"font": "display", "italic": 1, "upper": 1},
                 "kicker": {"bold": 1, "upper": 1, "tracking": 0.28},
                 "stamp": {"bold": 1, "upper": 1, "tracking": 0.12},
                 "number": {"font": "mono", "bold": 1}, "badge": {"font": "mono", "bold": 1},
                 "name": {"bold": 1}, "position": {"bold": 1}, "item": {"bold": 1},
                 "row_title": {"bold": 1}, "row_tag": {"font": "mono", "bold": 1}, "label": {"bold": 1}}},
    "mrone": {  # 参考你自己成片里的观感：近黑卡、白色粗标题、金黄高亮与编号
        "desc": "MR ONE 黑金：近黑卡、白色粗标题、金黄关键词与编号方块",
        "plate": ["#121215", "#0B0B0D"], "plate_alpha": 0.94, "radius": 22,
        "text": "#FFFFFF", "muted": "#A1A1AA", "accent": "#FFC933", "on_accent": "#111111", "hl": "@accent",
        "value": "#3DDC84", "state": "#FFC933",
        "border": {"w": 1, "color": "#2A2A30"},
        "shadow": {"soft": 28, "alpha": 0.50, "dy": 10, "color": "#000000"},
        "signature": {"sweep": {"color": "#FFE9A8", "peak": 0.20}},
        "row": "#1B1B1F", "line": "#2C2C31",
        "text_engine": "ass", "body_font": "PingFang SC", "captions": "mrone",
        "community": {"owner": "MR ONE", "note": "社群风格：MR ONE 的个人频道风格 © MR ONE；可以使用，请勿用来冒充 MR ONE"},
        "type": {"title": {"bold": 1}, "heading": {"bold": 1}, "quote": {"bold": 1},
                 "kicker": {"bold": 1, "upper": 1, "tracking": 0.22},
                 "stamp": {"bold": 1}, "row_title": {"bold": 1}, "row_tag": {"bold": 1},
                 "badge": {"font": "mono", "bold": 1}, "number": {"font": "mono", "bold": 1},
                 "name": {"bold": 1}, "item": {"bold": 1}}},
    "serif": dict(_LIGHT_SEM, **{  # 通用类型：纸感衬线
        "desc": "纸感衬线：暖米底、宋体标题、赭红强调、细线分隔",
        "plate": ["#FBF7EE", "#F3ECDD"], "plate_alpha": 0.97, "radius": 4,
        "text": "#1C1917", "muted": "#78716C", "accent": "#9A3412", "on_accent": "#FFFFFF", "hl": "@accent",
        "border": {"w": 1, "color": "#E4D8C0"},
        "shadow": {"soft": 22, "alpha": 0.25, "dy": 8, "color": "#3A2A15"},
        "signature": {"corners": {"len": 30, "w": 2, "inset": 16, "alpha": 0.40}},
        "row": "#F6F0E3", "line": "#E4D8C0",
        "text_engine": "ass", "body_font": "PingFang SC", "serif_font": "Songti SC",
        "type": {"title": {"font": "serif", "bold": 1}, "heading": {"font": "serif", "bold": 1},
                 "quote": {"font": "serif"}, "row_title": {"font": "serif", "bold": 1},
                 "kicker": {"upper": 1, "tracking": 0.20}, "number": {"font": "serif", "bold": 1}}}),
    # —— 带画面调色的风格：选了就连画面一起调（look，见 aaaai_editor/look.py）——
    "cozy": dict(_LIGHT_SEM, **{  # 暖调居家电影感博主风（Warm & Cozy Cinematic Vlog）
        "desc": "居家科技博主：奶油米白卡、焦糖强调、柔和阴影；画面暖调低对比＋黑柔＋细颗粒",
        "plate": ["#FBF4E8", "#F3E6D3"], "plate_alpha": 0.94, "radius": 28,
        "text": "#3B2A1E", "muted": "#8A7360", "accent": "#C8773A", "on_accent": "#FFF8EE", "hl": "#FFC27A",
        "lite_accent": "#FFC27A",   # 叠在画面上（无底板）时：焦糖色调亮后仍偏灰，小字看不清，改用琥珀色
        "value": "#6F8F3C", "state": "#A8653A",
        "border": {"w": 0, "color": "#E8D8C0"},
        "shadow": {"soft": 34, "alpha": 0.22, "dy": 12, "color": "#4A2E18"},
        "signature": {"pattern": {"kind": "dots", "color": "#B08A62", "alpha": 0.055, "size": 12}},
        "row": "#F6EBDB", "line": "#E6D4BB",
        "text_engine": "ass", "body_font": "PingFang SC", "mono_font": "IBM Plex Mono",
        "captions": "cozy", "look": "cozy",
        "type": {"title": {"bold": 1}, "heading": {"bold": 1}, "quote": {"bold": 1}, "row_title": {"bold": 1},
                 "kicker": {"bold": 1, "upper": 1, "tracking": 0.18}, "stamp": {"bold": 1},
                 "number": {"bold": 1}, "badge": {"bold": 1},
                 "name": {"bold": 1}, "item": {"bold": 1}, "row_tag": {"bold": 1}}}),
    # —— 贴纸弹跳（Sticker Pop）：贴纸卡片见 aaaai_editor/sticker.py；一般卡片在这个风格下也是贴纸外观 ——
    "sticker": dict(_LIGHT_SEM, **{
        "desc": "贴纸弹跳 Sticker Pop：奶油白卡、黑粗描边＋右下硬投影、粉／黄撞色、斜标签、打字框字幕",
        "plate": ["#FFFCF5", "#FFFCF5"], "plate_alpha": 1.0, "radius": 30,
        "text": "#0A0A0B", "muted": "#5A5560", "accent": "#FF4F9A", "on_accent": "#FFFFFF", "hl": "#FF4F9A",
        "accent2": "#FEDA62", "navy": "#1D1B49", "ink": "#0A0A0B", "paper": "#FFFCF5",
        "value": "#FF4F9A", "state": "#1D1B49",
        "lite": 0,   # 不用渐变遮罩：每张卡都是一张贴纸
        "border": {"w": 5, "color": "#0A0A0B"},
        "shadow": {"soft": 0, "alpha": 1.0, "dx": 10, "dy": 10, "color": "#0A0A0B", "ambient": False},
        "row": "#FFF3C4", "line": "#0A0A0B",
        "text_engine": "ass", "body_font": "Yuanti SC", "mono_font": "Arial Rounded MT Bold",
        "sticker_palette": True, "sticker_burst": True, "captions": "sticker",
        "type": {"title": {"bold": 1}, "heading": {"bold": 1}, "quote": {"bold": 1}, "row_title": {"bold": 1},
                 "kicker": {"bold": 1, "tracking": 0.06}, "stamp": {"bold": 1},
                 "number": {"bold": 1}, "badge": {"bold": 1},
                 "name": {"bold": 1}, "item": {"bold": 1}, "row_tag": {"bold": 1}, "text": {"bold": 1}}}),
}
DEFAULT_THEME = "ink"


def _custom_dirs(base_dir: Optional[str]) -> List[str]:
    ds = [os.path.join(REPO, "themes"), os.path.expanduser(os.path.join(
        os.environ.get("AAAAI_EDITOR_HOME") or "~/.aaaai-editor", "themes"))]
    if base_dir:
        ds.append(os.path.join(base_dir, "themes"))
    return ds


def all_themes(base_dir: Optional[str] = None) -> Dict[str, dict]:
    """内置 + 自定义（后加载的覆盖先加载的）。自定义 JSON 可用 "extends" 继承。"""
    out = {k: dict(v) for k, v in BUILTIN.items()}
    for d in _custom_dirs(base_dir):
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            try:
                j = json.load(open(f, encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise RuntimeError("风格文件读不了：%s（%s）" % (f, e))
            name = j.pop("name", os.path.splitext(os.path.basename(f))[0])
            parent = out.get(j.pop("extends", DEFAULT_THEME), out[DEFAULT_THEME])
            merged = dict(parent)
            merged.update(j)
            merged.setdefault("desc", "自定义（%s）" % os.path.basename(f))
            out[name] = merged
    return out


def resolve_colors(t: dict) -> dict:
    """颜色值写成 "@value" 表示引用另一个令牌。"""
    for _ in range(3):
        for k, v in list(t.items()):
            if isinstance(v, str) and v.startswith("@") and v[1:] in t:
                t[k] = t[v[1:]]
    return t


def is_community(t: dict) -> bool:
    return bool(t.get("community") or t.get("restricted"))


def theme(name: Optional[str], base_dir: Optional[str] = None, brand: Optional[dict] = None) -> dict:
    themes = all_themes(base_dir)
    key = name or DEFAULT_THEME
    if key not in themes:
        raise RuntimeError("没有这个风格：%s（可用：%s）" % (key, " ".join(themes)))
    t = dict(themes[key])
    if brand:
        t.update(brand)
    t["name"] = key
    return resolve_colors(t)


def list_themes(base_dir: Optional[str] = None, usable_only: bool = False) -> List[str]:
    """全部风格；社群风格（mrone、otg）排在最后——可以用，但不是首选。"""
    th = all_themes(base_dir)
    return [k for k in th if not is_community(th[k])] + [k for k in th if is_community(th[k])]
