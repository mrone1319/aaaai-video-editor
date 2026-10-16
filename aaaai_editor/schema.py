"""每种字卡／组合卡／配方有哪些栏位：名称、说明、输入方式。

Studio 的属性面板按这里自动生成表单——引擎加一种字卡，只要在这里补一行，界面就有它的表单。
没列在这里的栏位不会被藏起来：界面会把它们放进「其他栏位（JSON）」照样能改。

栏位格式：(键, 标签, 种类[, 选项])
种类：text 单行字｜textarea 多行字｜num 数字｜bool 开关｜lines 一行一条的清单｜json 结构化内容｜select 选项
"""
from __future__ import annotations

ANIMS = [["", "默认"], ["rise", "上浮（带超调）"], ["pop", "弹出"], ["fade", "淡入"], ["left", "左滑入"],
         ["right", "右滑入"], ["fall", "下落"],
         ["slam", "重砸（贴纸）"], ["ghost", "描边→填满（贴纸）"], ["drop", "掉下来（贴纸）"],
         ["slide", "侧滑带转（贴纸）"], ["none", "不动（贴纸）"]]
SFX = [["", "无"], ["pop", "啵"], ["ding", "叮"], ["whoosh", "咻"], ["coin", "金币"], ["click", "喀"],
       ["tick", "滴答"], ["confetti", "拉炮"]]
OUTS = [["", "淡出（默认）"], ["fall", "下落淡出"], ["rise", "上浮淡出"], ["left", "左滑出"], ["right", "右滑出"],
        ["cut", "直接消失"]]
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
    "sticker": ("贴纸", [("kind", "种类", "select", [["box", "台词框"], ["tag", "斜标签"], ["slam", "重砸大字"],
                                                    ["icon", "卡通图标"], ["badge", "圆环计数"], ["checklist", "打勾清单"],
                                                    ["cta", "点击按钮"], ["polaroid", "拍立得"], ["fan", "扇形卡片"],
                                                    ["flip", "翻面卡片"]]),
                         ("text", "文字（**粉字**　==黄底条==　[[粉色实底]]）", "textarea"),
                         ("tag", "框角斜标签", "text"),
                         ("fill", "底色", "select", [["", "默认"], ["cream", "奶油白"], ["pink", "粉"], ["yellow", "黄"],
                                                    ["navy", "海军蓝"], ["white", "白"]]),
                         ("name", "图标（phone_play、camera_off、moon、megaphone、bolt、link、cursor、pencil、"
                                  "scissors、checkbox、star、heart、sparkle、fire）", "text"),
                         ("icon", "框角图标", "text"), ("values", "计数的数字（一行一个）", "lines"), ("unit", "单位", "text"),
                         ("label", "徽章斜标签", "text"), ("items", "清单（一行一条）", "lines"),
                         ("file", "图片（assets/…）", "text"), ("files", "多张图片（扇形／翻面）", "lines"),
                         ("xy", "位置 [中心 x, 中心 y]（0–1）", "json"), ("rot", "倾斜（度）", "num"),
                         ("burst", "彩纸小爆发", "bool"), ("typing", "逐字打出", "bool")]),
    "blur": ("打码", [("mode", "方式", "select", [["", "模糊"], ["mosaic", "马赛克"]]), ("strength", "强度（1＝标准，越大越糊）", "num"),
                      ("box", "范围 [x, y, 宽, 高]（0–1；画面上拖框更方便）", "json")]),
}

COMMON = [("anim", "入场动画", "select", ANIMS), ("out", "出场动画", "select", OUTS), ("sfx", "音效", "select", SFX), ("scale", "大小", "num"),
          ("lite", "遮罩版（看得见画面）", "bool"), ("avoid_face", "自动避开脸", "bool"),
          ("behind_subject", "放到人后面（文字穿插，需要人像去背）", "bool")]

# 能直接出「真样子」PNG 的基本字卡（组合卡、配方要渲染一段才看得到）
TRUE_LOOK = ("title", "stat", "bullets", "quote", "lower_third", "stamp", "callout", "text", "rows", "icons",
             "compare", "gauge", "rank", "timeline", "rating", "sticker")


# Studio「＋ 字卡」新增时的起始内容（之后在属性面板改）；顺序＝选单顺序
NEW = [
    ("常用", [("title", {"kicker": "小标", "text": "新的**标题**"}, "小标＋大标题"),
              ("stat", {"kicker": "数据", "value": 50, "unit": "倍", "label": "说明一行"}, "大数字＋单位"),
              ("bullets", {"title": "三个重点", "items": ["第一点", "第二点", "第三点"]}, "一条条出现"),
              ("quote", {"text": "一句值得记住的话", "by": "出处"}, "金句"),
              ("lower_third", {"name": "名字", "role": "头衔"}, "名字＋头衔")]),
    ("数据", [("gauge", {"kicker": "完成度", "value": 0.72, "label": "说明一行", "count": True}, "会动的百分比"),
              ("rating", {"kicker": "评价", "value": 4.5, "of": 5, "label": "说明一行"}, "支持半星"),
              ("rank", {"title": "排行", "items": [{"label": "第一名", "value": 90}, {"label": "第二名", "value": 70},
                                                   {"label": "第三名", "value": 45}]}, "横条排行"),
              ("compare", {"left": {"title": "以前", "items": ["慢", "贵"]}, "right": {"title": "现在", "items": ["快", "便宜"]}},
               "以前 vs 现在")]),
    ("排版", [("rows", {"title": "标题", "items": [{"title": "第一行", "desc": "说明"}, {"title": "第二行", "desc": "说明"}]},
               "编号行"),
              ("icons", {"title": "标题", "items": [{"icon": "bolt", "label": "快"}, {"icon": "shield", "label": "稳"},
                                                    {"icon": "heart", "label": "好用"}]}, "图标格"),
              ("timeline", {"title": "时间轴", "items": [{"time": "2024", "text": "开始"}, {"time": "2026", "text": "现在"}]},
               "节点"),
              ("text", {"text": "一行字"}, "纯文字"),
              ("stamp", {"text": "重点"}, "印章"),
              ("callout", {"text": "看这里"}, "标注")]),
    ("贴纸（Sticker Pop）", [
        ("sticker:box", {"kind": "box", "text": "我**不想**拍==短视频==", "tag": "只需", "xy": [0.5, 0.42]}, "台词框＋斜标签"),
        ("sticker:slam", {"kind": "slam", "text": "赶快", "xy": [0.5, 0.40]}, "重砸大字"),
        ("sticker:tag", {"kind": "tag", "text": "最快", "fill": "yellow", "xy": [0.3, 0.40]}, "斜标签"),
        ("sticker:icon", {"kind": "icon", "name": "phone_play", "xy": [0.75, 0.38]}, "卡通贴纸图标"),
        ("sticker:badge", {"kind": "badge", "values": [8, 22, 24], "unit": "小时", "label": "最快", "xy": [0.5, 0.42]},
         "圆环计数"),
        ("sticker:checklist", {"kind": "checklist", "items": ["第一步", "第二步", "第三步"], "xy": [0.5, 0.42]},
         "打勾清单"),
        ("sticker:cta", {"kind": "cta", "text": "点击链接", "xy": [0.5, 0.45]}, "按钮＋手形光标"),
        ("sticker:polaroid", {"kind": "polaroid", "file": "assets/photo.png", "xy": [0.6, 0.38]}, "拍立得（换图片）")]),
    ("互动", [("cta", {"question": "你最想学**哪一个**？", "keyword": "工具", "badge": "留言领取"}, "评论框打字"),
              ("countdown", {"from": 3}, "3、2、1")]),
]
# 「＋ 字卡」里的配方（一个配方展开成几张卡＋推近；真样子要「渲染这一段」）
NEW_RECIPES = [
    ("hook", {"text": "开场**金句**", "kicker": "小标"}, "开场钩子：印章＋大标题＋推近"),
    ("stat_hit", {"value": 100, "suffix": "%", "label": "说明一行"}, "数字跳动＋落定推近"),
    ("quote_pull", {"text": "一句值得记住的话"}, "金句＋推近"),
    ("steps", {"title": "三个步骤", "items": ["第一步", "第二步", "第三步"]}, "一步步出现"),
    ("speaker", {"name": "名字", "role": "头衔"}, "人名条"),
    ("chapter", {"title": "第一章", "index": 1}, "章节断章（画面压暗）"),
    ("takeover", {"text": "结论**一句话**", "kicker": "重点"}, "卡片接管：画面收进圆角框"),
    ("outro", {"text": "谢谢观看", "sub": "关注我"}, "片尾：整屏卡片＋淡出"),
    ("brand_open", {"text": "品牌名"}, "品牌片头"),
    ("brand_close", {"text": "品牌名"}, "品牌片尾"),
]
NEW_LEN = {"takeover": 6.0, "outro": 3.0, "brand_open": 2.6, "brand_close": 3.0, "chapter": 2.0, "hook": 3.0,
           "cta": 6.0, "countdown": 3.0, "stamp": 2.0, "callout": 2.0, "lower_third": 3.0,
           "sticker:box": 1.6, "sticker:slam": 1.3, "sticker:tag": 1.4, "sticker:icon": 1.4, "sticker:badge": 2.2,
           "sticker:checklist": 2.4, "sticker:cta": 3.0, "sticker:polaroid": 2.2}


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
            "common": f(COMMON), "true_look": list(TRUE_LOOK), "recipes": rec,
            "new": [[g, [[t, d, h] for t, d, h in items]] for g, items in NEW], "new_len": NEW_LEN,
            "new_recipes": [[n, d, h] for n, d, h in NEW_RECIPES]}
