# 风格、图标、卡片新选项

## 风格

`~/.aaaai-editor/bin/aaaai-editor themes` 列出全部，`~/.aaaai-editor/bin/aaaai-editor showcase --out s.png` 渲染对照表（用真实管线）。

| 名称 | 气质 | 来源 |
|---|---|---|
| `ink` | 商业／知识：墨底、米白字、琥珀强调 | 自有 |
| `neon` | Web3：近黑底、青绿强调、细描边 | 自有 |
| `paper` | 编辑／印刷：米白底、深墨字、朱红强调 | 自有 |
| `gold` | 金融加密：石板底、金色信任、紫色科技 | uupm-design 色板 |
| `trust` | 理财／机构：深海军底、信任蓝、盈利绿 | uupm-design 色板 |
| `mag` | 杂志／评论：纯白卡、近黑字、品红强调 | uupm-design 色板 |
| `otg` | OTG 火箭风：深空黑、OTG 红、Orbitron Black 斜体大写标题、红色光晕、毛玻璃、星空断章、激光扫光 | OTG 社群品牌规范 |
| `mrone` | MR ONE 黑金：近黑卡、白色粗标题、金黄关键词、黄色编号方块；配套双语高亮字幕 | MR ONE 频道成片 |
| `serif` | 纸感衬线：暖米底、宋体标题、赭红强调 | 通用类型 |

`otg`／`mrone`／`serif` 的卡片文字走 **libass 富文本通路**（混色、字距、斜体、展示字体）；
其余六套仍走 drawtext，旧成片逐位不变。两条通路按字体度量对齐字号与位置（实测墨迹宽度一致）。
OTG 的语义色按品牌规则：翡翠绿只做涨幅／状态，陈述色用余烬金。

每套都有两个**语义色**（来自剪辑公式库 4/4 验证的结论）：
`value` 绿＝能量／价值（数据、增长），`state` 青＝静息／陈述（章节、说明）。

- **项目自定义风格**：见 `themes/README.md`，用 `extends` 继承。
- **临时品牌色**：storyboard 顶层 `"brand": {"accent": "#9B5CFF"}`，覆盖所选风格。
- **单张卡片改色**：`"colors": {"accent": "@value"}`。

## 图标

`~/.aaaai-editor/bin/aaaai-editor icons --sheet icons.png` 输出总表。41 个自绘线性图标（24 单位网格、距离场栅格化，
任意尺寸都锐利）：

- Web3：wallet token candlestick chainlink contract gas nft x telegram discord chart_up chart_down swap lock shield key
- 通用：check cross arrow_right arrow_up star bolt rocket user users clock calendar globe heart eye play mic idea target trophy money chat camera bell fire link
- 别名：twitter／x-twitter→x、coin→token、chain→chainlink、candle→candlestick、growth→chart_up 等

X、Telegram、Discord 是自绘的简化字形。正式品牌露出建议用官方素材走 `image` 卡片。

与卡片同时出现的图标**直接烤进底板**，不增加 ffmpeg 输入；错峰出现的才单独一层。

## 卡片新选项（全部可选，不写时与之前完全一样）

| 选项 | 用在 | 说明 |
|---|---|---|
| `icon` / `icon_badge` / `icon_scale` | title stat quote | 顶部主图标；`icon_badge: true` 为实心圆底 |
| `icon` | stamp | 字前小图标 |
| `items: [{"text","icon"}]` | bullets | 每项用图标代替编号 |
| `title` / `kicker` | bullets icons | 列表／宫格的标题 |
| `stagger: "auto"` | bullets icons | 按上一条字数错峰（内容驱动，非随机、非等距） |
| `bleed: true` / `opacity` | 任意 | 整屏底板（章节断章、尾板） |
| `width: 0.43` | 任意 | 指定底板宽度占比（并排卡片用） |
| `colors` | 任意 | 单张卡片改令牌 |

新卡片类型 `icons`：图标宫格，`{"type":"icons","t":[a,b],"title":"生态","items":[{"icon":"wallet","label":"钱包"}],"cols":4}`。

## 关键词高亮（任何风格）

任何文字里写 `**关键词**` 就会用风格的高亮色（`hl`，默认等于强调色）：
`"text": "我一个人\n但公司有**六个员工**"`。

## 编号行卡 `rows`

```jsonc
{"type":"rows","t":[a,b],"kicker":"MR ONE · AI 编程表","title":"我一个人\n但公司有**六个员工**",
 "items":[{"title":"策略顾问","tag":"Claude · Chat","desc":"帮我理清想法。"}]}
```
每条一张小卡，左边强调色方块编号；小卡与编号方块烤进底板，文字逐条错峰。

## 卡片接管 `frame`（配方 `takeover`）

整屏底 → 口播画面收进圆角框 → 顶部标题 → 人物从框上缘冲出（用人像遮罩）。
参数：`top`／`height` 框的位置与高度（占画面比例），`zoom` 画面放大，`focus` 框内取景偏上程度，
`popout: false` 关掉冲出。OTG 风格的整屏底是星空。

## OTG 专属效果（风格里开关）

`glass`（卡片底下画面模糊＝毛玻璃）、`bleed_bg: "starfield"`（整屏断章换星空跃迁＋发射火光，
循环素材缓存一次）、`laser`（标题／数据卡落定后一道光带扫过）、红色 `shadow`＝光晕。
自定义风格也能开这些开关。

## 片尾淡出

`"ending": {"fade": 1.2}`：最后 1.2 秒音画同步淡出（`outro` 配方会自动加）。
