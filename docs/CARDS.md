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
| `float` | `false` 关掉呼吸浮动（默认卡片落定后上下轻浮约 0.4% 画面高、周期 3.2 秒；章节、片尾、1.2 秒以下的卡片不浮） |
| `sparkle` | `false` 关掉闪光（标题、数据、金句、片尾默认在强调色处闪一两下） |

卡片默认避开画面底部 19%，不压字幕。`float`／`sparkle` 也可写在 storyboard 顶层，整支片一起关。

## 类型

```jsonc
{"type":"title",  "t":[1,4], "kicker":"STEP 01", "text":"先定构思，再选效果", "sub":"一个载体，出现三次以上"}
{"type":"stat",   "t":[5,8], "kicker":"TOTAL", "value":24800, "from":0, "suffix":"+", "label":"月活钱包",
                  "count":true, "count_dur":1.0, "digits":0, "format":"comma"}
{"type":"bullets","t":[9,14],"items":["转录成文字","剪掉停顿","加字幕和配乐"], "stagger":0.16}
{"type":"quote",  "t":[2,6], "text":"不要用随机抖动假装人味", "by":"剪辑笔记"}
{"type":"lower_third","t":[1,4],"name":"Alex Chen","role":"内容创作者"}
{"type":"avatar", "t":[1,4], "file":"assets/me.jpg", "name":"Alex Chen", "role":"内容创作者", "focus":[0.5,0.4]}
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

## 口播画面上的标题／金句／人名条（`lite`）

`title`、`quote`、`lower_third` 在所有风格里默认用**画面边缘渐变遮罩**代替方块：
- 标题、金句：画面上沿一层渐变遮罩，字左对齐、粗体，上方一条强调色短线；`**关键词**` 用强调色。默认放左上，避开脸。
- 人名条：画面下沿一层渐变遮罩，左边一条强调色竖线，姓名粗体、职务用强调色。默认放左下，字幕在它上方。
- 片尾（`outro`）：画面半透明压暗（人还看得到），居中大标题，上方强调色短线，副标题做成强调色按钮式标签；`"dim": 1` 为全黑。
- 遮罩颜色取风格的底板色；浅色风格（paper、mag、serif）自动改用深色遮罩配浅色字，并把强调色提亮，保证任何画面上都看得清。
- 数据跳数（`stat`）、清单（`bullets`）、编号行卡（`rows`）、对比（`compare`）也一样：默认放左上、渐变遮罩、左对齐。
  清单内容一长（会盖到脸），遮罩会自动压深，变成一个明确的「清单时刻」。
- 对比（`compare` 配方）改成上下两组：前一组淡色＋叉（你以为／以前），后一组价值色＋勾（其实／现在），第二组晚 0.6 秒出现（`reveal` 可调）。
- 章节断章（`chapter`）：整个画面压暗（人仍看得见）＋大号章节数字＋标题，放在画面中段偏左，字幕保持在最上层。
- 图标宫格（`icons`）：左上，标题左对齐，一排图标；标注（`callout`）的药丸放大 1.35 倍（配方可写 `scale`）。
- 卡片接管（`takeover`）：背景改成同一段画面放大、模糊、压暗，标题上方有强调色短线。
- otg 保留自己的特色：红框底板、星空章节页、星空接管背景，但卡片默认都放在上方。
- 想要旧的整块底板：卡片里写 `"lite": false`；风格 json 里写 `"lite": 0` 则整套风格都不用（`otg` 保持自己的红色底板）。
- 字幕默认位置见 `docs/STYLE.md`（`captions.margin_v`、`captions.size_scale`）。
- 字幕避脸（默认开）：人坐得低、脸落到字幕位置时，那几句移到下巴下面；关掉写 `"captions": {"avoid_face": false}`。
- 卡片避脸（默认开）：上方的标题、数据、清单、金句等，在它出现期间若压到眼睛，整张往上挪（最多挪到离顶 5%）；
  还是压到就改放在下巴下面（遮罩改成上下渐淡，只包住字）。单张关掉写 `"avoid_face": false`，整支片关掉在 storyboard 顶层写。
  文字穿插（`behind_subject`）的卡片不动。
- 印章（`stamp`）与标注（`callout`）一律画在其他卡片上面，不会被标题的遮罩盖住。

## 小组件与音效

```jsonc
{"type":"confetti",  "t":[30,32.6], "sfx":"confetti"}                    // 拉炮彩带（可写 x、y 喷出点比例）
{"type":"countdown", "t":[8.6,11.6], "from":3}                          // 圆环倒数＋大数字，每秒 tick（"sfx": "" 关掉）；at_xy 改位置
{"type":"glow",      "t":[13.6,17], "box":[0.035,0.695,0.60,0.098]}     // 关注框：[左, 上, 宽, 高] 比例，一呼一吸（pulse 秒数）
```

**转场**（写在 storyboard 顶层，不是 overlays）：

```jsonc
"transitions": [{"t": 14.9, "type": "whip"}, {"t": 34.4, "type": "whip", "dir": "right", "dur": 0.4, "sfx": ""}]
```

- `t` 写成片秒数，会吸附到 ±0.6 秒内最近的剪辑点；只动前后约 0.3 秒（`dur`）的帧，片长不变，卡片与字幕不受影响。
- `dir`：画面往 `left`（默认）或 `right` 甩；`sfx` 默认 `whoosh`，写 `""` 关掉。
- **只在用户明确要求时才加**；自动剪辑不会加转场。

- 组合卡片 `proof`（证据截图）、`flow`（工作流步骤）、`cta`（行动号召）的写法见 `docs/RECIPES.md`「卡片收合三连发」。
- 音效：任何卡片可写 `"sfx": "<名称>"`（卡片出现时响，`sfx_at` 改时间、`sfx_db` 调单个音量）；
  或 storyboard 顶层 `"sfx": [{"t": 秒, "sound": "coin", "db": 0}]`；整体音量 `"sfx_level": "quiet"／"normal"／"loud"`。
  `aaaai-editor sfx` 列出全部音效（金币、啵、叮、咻、喀、滴答、拉炮），都是程序合成的，没有版权问题。
