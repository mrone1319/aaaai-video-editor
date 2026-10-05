"""每种字卡／组合卡／配方有哪些栏位：名称、说明、输入方式。

Studio 的属性面板按这里自动生成表单——引擎加一种字卡，只要在这里补一行，界面就有它的表单。
没列在这里的栏位不会被藏起来：界面会把它们放进「其他栏位（JSON）」照样能改。

栏位格式：(键, 标签, 种类[, 选项])
种类：text 单行字｜textarea 多行字｜num 数字｜bool 开关｜lines 一行一条的清单｜json 结构化内容｜select 选项
"""
from __future__ import annotations

ANIMS = [["", "默认"], ["rise", "上浮（带超调）"], ["pop", "弹出"], ["fade", "淡入"], ["left", "左滑入"],
         ["right", "右滑入"], ["fall", "下落"]]
SFX = [["", "无"], ["pop", "啵"], ["ding", "叮"], ["whoosh", "咻"], ["coin", "金币"], ["click", "喀"],
       ["tick", "滴答"], ["confetti", "拉炮"]]
ICON_STYLES = [["", "跟随风格"], ["line", "描边"], ["duo", "双色"], ["bold", "加粗"]]

TITLE_HINT = "**两个星号**包住＝强调色；换行直接按 Enter"

CARDS = {
    "title": ("标题卡", [("kicker", "小标", "text"), ("text", "标题（" + TITLE_HINT + "）", "textarea"),
                         ("sub", "副标", "text"), ("icon", "图标名称", "text"), ("type_in", "逐字打出", "bool")]),
    "stat": ("数据卡", [("kicker", "小标", "text"), ("value", "数值", "num"), ("from", "从多少开始跳", "num"),
                        ("unit", "单位（小一号、强调色）", "text"), ("prefix", "前缀", "text"), ("suffix", "后缀", "text"),
                        ("label", "说明", "text"), ("bar", "量感条（0–1）", "num"), ("of", "总量（自动算量感条）", "num"),
                        ("count", "数字跳动", "bool")]),
    "bullets": ("清单卡", [("kicker", "小标", "text"), ("title", "标题", "text"), ("items", "清单（一行一条）", "lines"),
                           ("stagger", "一条条出现的间隔（秒）", "num")]),
    "quote": ("金句卡", [("text", "金句", "textarea"), ("by", "出处", "text")]),
    "lower_third": ("人名条", [("name", "名字", "text"), ("role", "头衔", "text")]),
    "avatar": ("头像牌", [("file", "照片（项目 assets/ 里的文件）", "text"), ("name", "名字", "text"), ("role", "头衔", "text")]),
    "stamp": ("印章", [("text", "文字", "text")]),
    "callout": ("标注", [("text", "文字", "text"), ("icon", "图标名称", "text")]),
    "text": ("纯文字", [("text", "文字", "textarea"), ("color", "颜色（#RRGGBB）", "text")]),
    "rows": ("编号行卡", [("kicker", "小标", "text"), ("title", "标题", "text"), ("sub", "说明", "text"), ("items", "每一行", "json")]),
    "icons": ("图标格", [("kicker", "小标", "text"), ("title", "标题", "text"), ("items", "每一格（icon、label）", "json"),
                         ("icon_style", "图标风格", "select", ICON_STYLES)]),
    "compare": ("对比卡", [("kicker", "小标", "text"), ("left", "以前（title、items）", "json"), ("right", "现在（title、items）", "json")]),
    "gauge": ("进度圈", [("kicker", "小标", "text"), ("value", "数值（0–1，或配合总量）", "num"), ("of", "总量", "num"),
                         ("label", "说明", "text"), ("count", "会动", "bool")]),
    "rank": ("排行榜", [("kicker", "小标", "text"), ("title", "标题", "text"), ("items", "每一条（label、value）", "json"),
                        ("suffix", "单位", "text")]),
    "timeline": ("时间轴", [("kicker", "小标", "text"), ("title", "标题", "text"), ("items", "每个节点（time、text）", "json")]),
    "rating": ("评分星", [("kicker", "小标", "text"), ("value", "分数", "num"), ("of", "满分", "num"), ("label", "说明", "text")]),
    "cta": ("行动号召", [("kicker", "小标", "text"), ("question", "问题（" + TITLE_HINT + "）", "textarea"),
                         ("keyword", "关键词（观众要打的那几个字）", "text"), ("badge", "下面一行小字", "text"),
                         ("question_at", "问题出现（秒）", "num"), ("cta_at", "开始打字（秒）", "num"),
                         ("style", "版式", "select", [["", "评论框"], ["pill", "药丸（旧版）"]])]),
    "flow": ("流程卡", [("kicker", "小标", "text"), ("steps", "每一步（icon、top、big、at）", "json")]),
    "proof": ("证据截图", [("file", "截图（assets/…）", "text"), ("kicker", "小标", "text"), ("pill", "日期胶囊", "text"),
                           ("stamp", "金额印章", "text")]),
    "countdown": ("倒数", [("from", "从几开始", "num")]),
    "confetti": ("彩带", []),
    "glow": ("关注框", [("box", "位置 [x, y, 宽, 高]（0–1）", "json")]),
    "image": ("图片", [("file", "文件（assets/…）", "text"), ("width", "宽度（0–1）", "num"), ("pos", "位置", "text")]),
    "clip": ("透明影片", [("file", "文件（assets/…）", "text"), ("width", "宽度（0–1）", "num")]),
    "broll": ("B-roll", [("file", "文件（assets/…）", "text"), ("from", "从素材第几秒开始", "num"),
                         ("mode", "方式", "select", [["", "满版"], ["letterbox", "上下黑边"], ["blur", "模糊垫底"]])]),
    "cutout": ("去背人像", [("width", "宽度（0–1）", "num"), ("pos", "位置", "text")]),
}

COMMON = [("anim", "入场动画", "select", ANIMS), ("sfx", "音效", "select", SFX), ("scale", "大小", "num"),
          ("lite", "遮罩版（看得见画面）", "bool")]

# 能直接出「真样子」PNG 的基本字卡（组合卡、配方要渲染一段才看得到）
TRUE_LOOK = ("title", "stat", "bullets", "quote", "lower_third", "stamp", "callout", "text", "rows", "icons",
             "compare", "gauge", "rank", "timeline", "rating")


def as_dict() -> dict:
    """给界面用的 JSON：{cards: {type: {name, fields}}, common, true_look, recipes}。"""
    from . import recipes
    def f(fields):
        return [{"key": x[0], "label": x[1], "kind": x[2], **({"options": x[3]} if len(x) > 3 else {})}
                for x in fields]
    rec = {}
    for name, r in sorted(recipes.REG.items()):
        req, opt = r.get("required", ()), r.get("optional", ())
        rec[name] = {"name": name, "desc": r.get("desc", ""), "required": list(req), "optional": list(opt)}
    return {"cards": {k: {"name": v[0], "fields": f(v[1])} for k, v in CARDS.items()},
            "common": f(COMMON), "true_look": list(TRUE_LOOK), "recipes": rec}
