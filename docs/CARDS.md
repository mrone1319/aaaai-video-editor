# 卡片与推近

卡片写在 `storyboard.json` 的 `overlays` 里，推近写在 `zooms` 里。
两者都并入主滤镜链，**不增加一次转码**。

## 通用字段

| 字段 | 说明 |
|---|---|
| `t` | `[入, 出]` 秒，按**成片**时间轴（剪掉停顿之后） |
| `pos` | `center`(默认) / `top` / `bottom` / `top_left` / `top_right` / `bottom_left` / `bottom_right` / `left` / `right` |
| `anim` | `rise`(默认) / `fall` / `left` / `right` / `pop` / `fade` |
| `style` | 覆盖该卡片的风格（任一风格名，`~/.aaaai-editor/bin/aaaai-editor themes` 查看） |
| `under_captions` | `true` 时排在字幕下层（默认在字幕之上） |
| `scale` | 字号倍数，默认 1.0 |

卡片默认避开画面底部 19%，不压字幕。

## 类型

```jsonc
{"type":"title",  "t":[1,4], "kicker":"STEP 01", "text":"先定构思，再选效果", "sub":"一个载体，出现三次以上"}
{"type":"stat",   "t":[5,8], "kicker":"TOTAL", "value":24800, "from":0, "suffix":"+", "label":"月活钱包",
                  "count":true, "count_dur":1.0, "digits":0, "format":"comma"}
{"type":"bullets","t":[9,14],"items":["转录成文字","剪掉停顿","加字幕和配乐"], "stagger":0.16}
{"type":"quote",  "t":[2,6], "text":"不要用随机抖动假装人味", "by":"剪辑笔记"}
{"type":"lower_third","t":[1,4],"name":"Alex Chen","role":"内容创作者"}
{"type":"stamp",  "t":[0,3], "text":"NEW"}
{"type":"text",   "t":[1,3], "text":"没有底板的纯文字", "color":"#FFFFFF"}
{"type":"image",  "t":[2,4], "file":"logo.png", "width":0.22, "pos":"top_right", "disc":true}  // disc：黑色 logo 垫白底圆片
{"type":"clip",   "t":[6,9], "file":"mg.mov", "width":1.0}
```

- `stat` 的数字用等宽字体，计数时不会左右跳动。计数被摊成最多 20 个区间，
  所以千分位、前后缀都能正常显示（ffmpeg 表达式做不到千分位）。
- `clip` 吃带透明通道的片段（ProRes 4444 `.mov` 或 VP9-alpha `.webm`），
  可以直接放 `motion-graphic-video-editor` 输出的 MG 成品。

## 推近

```jsonc
"zooms":[
  {"t":[2,5], "to":1.12, "style":"smooth", "ease":0.45, "anchor":[0.5,0.42]},
  {"t":[8.4,8.9], "to":1.25, "style":"punch"}
]
```

`smooth` 缓入缓出，`punch` 瞬切瞬回。多段会合成一条 `zoompan`，互不打架。
推近只作用于底片，卡片不会跟着放大。

## 风格

`~/.aaaai-editor/bin/aaaai-editor themes` 看全部风格与字体（详见 `docs/STYLE.md`）。想改配色／圆角／投影：在 `~/.aaaai-editor/themes/` 放一个继承现有风格的 json（写法见 `themes/README.md`），
不要改程序里的 `aaaai_editor/theme.py`（更新会被覆盖）。开发者加卡片类型：在 `aaaai_editor/cards.py` 写一个 `blocks_*` 函数。

## 人像去背（文字穿插 / 人物抠出）

任何卡片加 `"behind_subject": true`，这张卡片就会排在**人物后面**——
文字被人挡住一部分，是短视频里最常用的穿插效果。

```jsonc
{"type":"title","t":[1,4],"text":"现场直击","behind_subject":true}
{"type":"cutout","t":[1,4],"width":0.62,"pos":"bottom"}   // 把人抠出来贴到别处
```

图层顺序（由下往上）：底片 → `behind_subject` 卡片 → 人物重贴 → `under_captions` 卡片 →
字幕 → 其余卡片。

遮罩参数（顶层 `matte`，全部可省）：

| 字段 | 默认 | 说明 |
|---|---|---|
| `quality` | `balanced` | `fast` / `balanced` / `accurate` |
| `scale` | `0.5` | 分割的工作分辨率倍数，越小越快 |
| `feather` | `2.0` | 遮罩边缘羽化像素 |

- 分割用系统的 Vision 框架，助手程序首次使用时自动编译并缓存，**不下载模型**。
  需要 Xcode Command Line Tools（`xcode-select --install`）。
- 只对用到的时间段做分割，不是整支片子，遮罩按内容哈希缓存。
- 这段没认出人时会打印提醒，渲染照常完成，只是去背无效果。
- 和推近同时使用时，遮罩会跟着一起推近，不会错位。


## 字幕：双语、高亮、手改字幕轨

```bash
~/.aaaai-editor/bin/aaaai-editor captions storyboard.json      # 导出 work/captions.json
```
每句：`s`（原片时间，改剪辑点不会错位）、`text`（可修错字）、`en`（填了就出英文第二行）、
`hl`（要高亮的词）。也可在 text 里写 `**关键词**`，或在 storyboard 写全局
`"captions": {"highlight": ["MR ONE"]}`。有这个文件渲染就用它，删掉即回到自动字幕。

字幕样式不写时跟随卡片风格：`mrone`、`otg` 有配套的双语高亮字幕样式；其余默认 `clean`。
没有英文、没有高亮时，字幕输出与之前逐字节相同。

## 全局推近（framing）

机位坐得远时：`"framing": {"zoom": 1.2, "cx": 0.5, "cy": 0.4}`，并进第一次编码（不多压一代），
人像遮罩、卡片坐标都跟着走。先用 `~/.aaaai-editor/bin/aaaai-editor framing storyboard.json --at 3` 出对比图选倍率（约 1.15–1.25× 安全）。

## B-roll

```jsonc
{"type":"broll","t":[25,28],"file":"assets/broll.mp4","from":3}                 // 满版铺满，口播声音照常
{"type":"broll","t":[6,8],"file":"assets/screen.mp4","mode":"letterbox"}         // 横式素材完整显示，上下黑边
{"type":"broll","t":[6,8],"file":"assets/screen.mp4","mode":"blur","fade":0.2}   // 横式素材完整显示，背后铺模糊放大版
{"type":"broll","t":[9,11],"file":"assets/photo.jpg","motion":"in"}              // 图片：缓慢推近（out＝拉远，none＝静止）
```

| 字段 | 说明 |
|---|---|
| `t` | 成片时间（照 `aaaai-editor cues` 填） |
| `from` | 从素材第几秒开始取；素材比时段短会自动循环 |
| `mode` | `fullscreen`（默认，裁切铺满）／`letterbox`／`blur` |
| `motion` | 图片专用：`in`（默认）／`out`／`none` |
| `fade` | 淡入淡出秒数，默认 0（硬切） |
| `lift` | B-roll 期间字幕抬到画面中上；`fullscreen` 默认开，其余默认关 |

B-roll 画在底片之上、卡片与字幕之下（B-roll 上面照样能叠卡片）。B-roll 的声音不混进成片。
B-roll 时段内不要用 `behind_subject`（人物会被重贴到 B-roll 上面）。

不想自己找素材：`aaaai-editor broll plan／estimate／gen／sheet／place` 从 Pexels 免费素材或 AI 生成，自动写进 overlays（流程见 SKILL 的「B-roll 流程」）。
