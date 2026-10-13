---
name: motion-graphic-video-editor
description: "代码化动效品牌片制作——用无头 Chromium（Playwright，GPU）+ Python + ffmpeg 产出广播级 MP4（60fps、多画幅；动作库＋真 3D＋生成式模块＋运动模糊；配乐优先用授权真实音乐并自动对拍，或原创合成），不用 AE、不用模板。适用：宣传片、预告片、片头、倒计时、发布片、Logo 动画／Logo sting、品牌焕新、品牌片、动效、文字动画、数据动画／数字揭示、活动公告、创意编程／设计工作室 showreel；用户丢来参考片要求仿其剪辑风格；品牌书 PDF 或 Logo 连同动画需求一起到达时。边界：讲解片／网站转影片／幻灯片／产品发布讲解 → HyperFrames；真人口播剪辑 → aaaai-editor。动手前必须先走 Intake（问需求、收素材、定方向）。Code-based motion graphics video editor: promo, teaser, countdown, launch film, logo sting, rebrand reveal, stat/data reveal, event announcement, title sequence, kinetic typography, creative-coding showreel or animated logo delivered as a real video file; also when a reference clip is handed over to copy its editing style, or a brand book / logo arrives with an animation request. Explainers, website-to-video, slides and product-launch walkthroughs go to HyperFrames; talking-head footage edits go to aaaai-editor. ALWAYS run Intake before building."
---

# Motion Graphic Video Editor

与品牌无关的代码化 MG 短片方法：品牌参数（颜色、字体、Logo、文案、配乐）全是运行时输入。产出真实的 H.264 MP4（含配乐）＋海报帧。
本文件只放流程、铁律、工具地图与清单；每一步的细节在 `references/`，做到那一步再读。

## 环境（每个命令块开头都带上——shell 变量不会跨命令保留）

```bash
export PATH="/opt/homebrew/opt/ffmpeg-full/bin:/usr/local/opt/ffmpeg-full/bin:$PATH"
PY=~/.aaaai-editor/bin/aaaai-editor-python
SK=<本 SKILL.md 所在目录>/scripts          # 按本文件的实际位置推出，不要写死
```

## 0. 五条原则

1. **结构可迁移，像素不可迁移。** 从参考片提炼剪辑公式（段落、节奏、冲击点），不抄画面。
2. **确定性。** 每一帧只由帧号决定（帧号可能是小数）：禁墙钟时间、渲染期随机数、CSS 动画。
3. **先验证再渲染。** 静帧抽查几秒、动态预览一分钟、全量渲染几分钟——永远按这个顺序。
4. **音乐和画面共用一张网格，但网格是参照不是磁铁。** 3–5 个锚点（唯一的冲击、数字锁定、drop、尾板、Logo 落定）卡在真实小节线上；其余由内容决定（读完、滚停、落定），不吸附、也不随机抖动。
5. **冲击越少越贵。** 一次果断的撞击＝自信，多次＝廉价预告片。其余靠有重量的缓动完成。

## 1. 制作模式（Intake 时选一种当主干，向用户复述确认；有参考片时服从参考片）

| 模式 | 适用 | 骨架 | 时长 |
|---|---|---|---|
| **A 冲击型品牌片** | 倒计时、发布预告、成就展示 | tension → burst（唯一冲击）→ payload（数字）→ breath（低亮段＋一句话）→ resolve | 30–40s |
| **B 柔和产品片** | 产品／App 演示、高级感品牌片 | 零硬切（blur＋scale＋opacity 转场）、色相全程漂移、坍缩留黑 → 尾板 | 18–25s |
| **C Logo sting／变身** | Logo 收尾、品牌焕新（旧变新） | seed → break 碎裂 → 迁移 → drop 新形象锁定 → 色波 → hold | 8–12s |
| **D 社媒转化** | 促销、招募、联名、带 CTA 投放 | 钩子 → 3D Logo → 黑场呼吸 → 数字 → 权益卡 → CTA 长驻 ≥3s → 联名尾板 | 20–24s |
| **E 数据揭示** | 季报、年度回顾、KPI | 趋势线 → 逐项 KPI 卡 → 对比图表 → 洞察金句 → 总结卡 | 25–35s |
| **F 循环片头** | 直播／活动开场 bumper | 首尾驱动变量逐一相等、无硬切 | 4–8s |
| **G 见证／案例** | 客户证言、before/after | 痛点 → 转折 → 引语逐字扫光 → 数据佐证 → 收尾 | 30–45s |
| **H 创意编程 showreel** | 设计工作室作品集、科技品牌形象片、设计系统发布 | 10–12 场**快慢交替**：极简开场 → 字体实验 → 生成式研究 → 粒子 → 3D 登场（最慢）→ 色块重击 → 编辑面板 → 线条／动作 → 字体混乱 → 主角 3D → 收束 → 结尾字停留 | 45–70s |
| 附加：真实录屏 | 挂在 A/B/D/G 当 proof | 设备框＋canvas 逐帧回放＋playlist 映射 | 5–12s |

- B／F 严禁硬切（成片测出 0 个硬切）；A／C／D 只有设计好的那一两次。
- 能量形状：A/C 要有 breakdown → drop；B 是多峰呼吸；D 最响给数字或 CTA；H 是锯齿（高能 0.2–0.4s 之后接真正慢的 3–7s）。
- 社媒 9:16 必须**关声音看一遍**仍然成立。
- 模式 H 用编辑设计风格（`references/style-swiss.md`）＋多场景主时间轴；完整示范 `examples/showreel/`。

## 2. Intake — 不问不开工（选择题，每轮 ≤4 题）

1. **替谁说话**（主品牌还是赞助／联名方——谁当英雄镜头）。
2. **核心信息**：一句话＋一个关键数字（数字段的落点）。
3. **CTA**：精确文案＋**唯一**入口。
4. **画幅与渠道**（16:9／9:16／1:1／4:5）——决定安全区。
5. **片长**；6. **模式**；7. **配乐来源**（用户授权音乐／HeyGen 音乐库／套件配乐库／合成）。
8. 没有品牌书时问颜色、深底或浅底、风格、字体、禁忌、参考片；要 Logo（**没有 Logo 就做纯文字排版片并明说，绝不伪造品牌资产**）、文案（**大小写逐字确认**）、录屏（**逐段隐私审查**）。
9. 动手前**用文字复述整片结构**给用户确认（文字便宜，帧很贵）。

细节：`references/intake.md`。

## 3. 流程

**Intake → 拆解 → 收割资产 → 方向定稿 → ★构思定稿 → 定音乐 → 时间轴 → 写场景 → 静帧验证 → ★动态预览＋能量验收 → 全量渲染 → 交付 → 修改**

| 步骤 | 做什么 | 工具 | 细节 |
|---|---|---|---|
| 拆解（有参考片时） | 段落表、硬切（自动区分真硬切与乱码帧）、能量曲线 → 剪辑公式；先查示例库与用户库 | `analyze_reference.py`、`check_motion.py` | `deconstruct.md`、`formulas.md` |
| 收割资产 | 实测取色、抠图、切 lockup、切字形、描轮廓（真 3D） | `logo_tools.py` | `brand-assets.md` |
| **方向定稿** | 出 2–3 张关键帧对比静帧（配色、字体、气质），用户选定才往下 | 渲染器 `--at` | — |
| **★构思定稿** | 一句话：「这支片是〈一个贯穿的东西〉——它以〈形态 A、B、C〉出现，因此〈某类效果〉一律不用」。用户确认后才取材 | — | `concept.md` |
| 定音乐 | 挑段落（从小节头开始、收在歌的自然结尾、高潮对上 drop）、统一 -14 LUFS，印出 `MUSIC` | `music_grid.py fit` | `timing.md` |
| 时间轴 | 信息密度校验；`T` 常量，锚点 ＝ `MUSIC.bars[i]` | — | `timing.md` |
| 写场景 | 动作用 **mg-kit**；长片用 **mg-film**；生成式用 **mg-gen**；3D 用 **mg-three**；编辑风格用 **swiss.css** | `assets/` | `authoring.md`、`effects.md`、`style-swiss.md` |
| 静帧验证 | 每个时间轴地标一帧 → contact sheet → 数值哨兵＋设计自检＋构思落地验收 | 渲染器 `--at` | 下方 §4 |
| ★动态预览 | 写的时候用播放器实时看；完成后渲低清预览＋能量验收，**发给用户看动作与节奏，确认后才全量** | `player.py`、`render_frames.py --preview`、`check_motion.py` | `delivery.md` |
| 全量渲染 | GPU、直接出 MP4、需要时运动模糊 | `render_frames.py --video --mblur scene` | `delivery.md` |
| 交付 | 七查 → MP4＋海报帧＋「哪些是一行改」 | — | `delivery.md` |
| 修改 | 攒一轮再改；批注是症状不是病因 | — | `iteration.md` |

## 4. 验证（每轮修改后都做）

- **数值哨兵**：应黑的帧亮度 8–12（>25 有层漏光，多半是 `1 - progress` 型闪光）；辉光 PNG 四角 `[0,0,0]`；3D 看**落定角度**那帧。
- **设计自检**：一眼知道看哪里吗？留白够吗？颜色服务于品牌而不是铺满？每个动作都必要吗（能删就删）？
- **构思落地验收**：从 contact sheet **随机**抽三帧——那个贯穿性载体在哪？三帧里形态各不相同吗？指得出它们服务于同一个构思吗？指不出来＝改结构，不是加效果。
- **能量验收**（`check_motion.py 预览.mp4 --scene scene.html`）：死时间（>2s 几乎不动，又不是 `MG.hold` 宣告的停留）→ 加镜头呼吸、视差、错峰或缩短；未宣告的跳变 → 元素没缓动；字太小（<画面高 2.2%）或超出安全区 → 改版面。

## 5. 铁律

- **动作一律用 mg-kit**（有重量的缓动、弹簧、遮罩出字、渐变扫光、计数器、解码、视差镜头、图形转场）——手写的 cubic／expo 只会「滑进来、停住」，这是旧片动作发平的主因。
- **用 `MG.blur／MG.hold／MG.cut` 宣告意图**：运动模糊区间、有意的停留、有意的硬切。
- **闪光只用 `MG.imp`**；所有用户叫得出名字的东西提为顶部常量。
- **品牌自己的资产优先于替代品**：Logo 切出的字形胜过任何字体；品牌名用 Logo 图不用字体排。
- **第一版永远太挤太快**：按 1.5× 时长预算；结尾用分步卡片（每张 ≥2s），用户嫌挤就拉长影片，不压缩卡片。
- **低亮段放内容不放空黑**；尾板＝品牌标独立＋保持＋音画同步淡出；每支片至少一个 ≥1.5s 的封面级停留帧。
- **踩坑先查** `references/gotchas.md`。

## 6. 交片七查（缺一不发）

1. 转场纪律符合模式；2. 帧数 ＝ 时长×fps、音视频同长；3. 能量验收无未宣告的问题；4. 黑场亮度 5–12；5. 关声音看一遍仍成立；6. 数字／日期／URL 与确认的逐字一致；7. 所有画幅都是最新代码渲的。
交付：每尺寸一个 MP4＋2–3 张海报帧（同尺寸 JPG）；说明改了什么、哪些参数是一行改；任何自主判断都披露并给替代选项。9:16 核心内容留在 **y 400–1520**。

## 7. 工具地图

| 文件 | 用途 |
|---|---|
| `assets/mg-kit.js` | 动作库（缓动、弹簧、关键帧、错峰、文字拆分与出场、计数器、解码、描线、变形、视差镜头、网格排版、裁切擦除、反转、推进、跑字、重击、波形场、Lottie、意图宣告、`MG.ready`） |
| `assets/mg-film.js` | 多场景主时间轴（每场一个文件，只渲染在播的场景） |
| `assets/mg-gen.js` | 生成式：力场粒子、字体网格、线框几何、手绘小人、动作骨架 |
| `assets/mg-three.js`＋`vendor/` | 真 3D：Logo 挤出、程序化雕塑、材质预设、摄影棚环境、柔和阴影、镜头组（three.js r170、lottie-web，MIT） |
| `assets/styles/swiss.css` | 编辑风格系统（四色、超大字、技术标签、细线） |
| `assets/scene_template.html` | 单场景起步模板 |
| `assets/player.html`＋`scripts/player.py` | 开发播放器：实时播放、拖动、逐帧、按场景跳、同步配乐 |
| `scripts/render_frames.py` | 渲染：GPU、自动 worker、`--video`、`--preview`、`--mblur`、`--alpha`、`--at` |
| `scripts/check_motion.py` | 能量验收：曲线图、死时间、跳变、黑场、字号与安全区 |
| `scripts/music_grid.py` | 真实配乐：拍点、小节、drop、自然结尾 → 挑段落、统一响度、`MUSIC` 常量 |
| `scripts/analyze_reference.py` | 参考片拆解：contact sheet、抽帧、响度、硬切分类（带管道校验） |
| `scripts/compare_ref.py` | 参考片与成片同时间点并排对照 |
| `scripts/logo_tools.py` | Logo：抠图、量版面、切 lockup、去细线、切字形、描轮廓 |
| `scripts/make_glow.py` | 预渲染辉光 PNG（边界精确归零） |
| `scripts/encode.sh` | 帧目录 → MP4／透明 ProRes 4444 |
| `examples/` | 可直接渲染的范本：`mgkit-demo.html`（动作）、`three-demo.html`（3D Logo）、`sculpture-demo.html`（雕塑）、`showreel/`（模式 H 全套，55 秒 12 场） |

## 在 aaaai-editor 套件里

本技能负责动画的创意与渲染；字幕、响度、封面、验收交给 `aaaai-editor`：
- **叠进口播**：`--alpha` 渲 PNG 序列（场景配合 `alpha=1`）→ `encode.sh --alpha` 出 ProRes 4444 `.mov` → aaaai-editor 剪辑表加 `{"type": "clip", "t": [起, 迄], "file": "<mov>", "width": 1.0}`。
- **整支动画成片**：`~/.aaaai-editor/bin/aaaai-editor adopt <成片.mp4> --out <项目>/storyboard.json` → 字幕／响度 -14 LUFS／封面 → social-content-pipeline。
- 讲解片、网站转影片、幻灯片：HeyGen HyperFrames（`/hyperframes`，仅 Claude Code）；本技能的构思定稿、拆解方法与公式库照样适用。

## 在其他平台（Codex 等）

- 没有 AskUserQuestion：把本轮问题（带编号选项与推荐项）一次列在一条消息里，等用户回编号。
- 没有后台 Bash：`nohup <命令> > render.log 2>&1 &`，再 `tail -n 3 render.log` 轮询。
- 没有 SendUserFile：交付时给出成片、海报帧的绝对路径。
- HyperFrames 只在 Claude Code 可用。
