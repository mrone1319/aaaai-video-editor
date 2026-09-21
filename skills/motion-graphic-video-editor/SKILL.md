---
name: motion-graphic-video-editor
description: "代码化动效品牌片制作——用无头 Chromium（Playwright）+ Python（numpy/scipy/Pillow）+ ffmpeg 产出广播级 MP4（60fps、原创合成配乐、多画幅），不用 AE、不用模板、不用版权音乐。适用：宣传片、预告片、片头、倒计时、发布片、Logo 动画／Logo sting、品牌焕新、品牌片、动效、文字动画、数据动画／数字揭示、活动公告；用户丢来参考片要求仿其剪辑风格；品牌书 PDF 或 Logo 连同动画需求一起到达时。边界：讲解片／网站转影片／幻灯片／产品发布讲解 → HyperFrames；真人口播剪辑 → aaaai-editor。动手前必须先走 Intake（问需求、收素材、定方向）。Code-based motion graphics video editor: promo, teaser, countdown, launch film, logo sting, rebrand reveal, stat/data reveal, event announcement, title sequence, kinetic typography or animated logo delivered as a real video file; also when a reference clip is handed over to copy its editing style, or a brand book / logo arrives with an animation request. Explainers, website-to-video, slides and product-launch walkthroughs go to HyperFrames; talking-head footage edits go to aaaai-editor. ALWAYS run Intake before building."
---

# 通用型 Motion Graphic Video Editor — 整合技能手册

> 本手册是一套**与品牌无关（brand-agnostic）**的代码化 Motion Graphic 短片制作方法论。所有品牌参数
> （颜色、字体、Logo、文案、配乐方向）都是运行时输入——**制作前必须先走 §2 Intake：问需求、要素材、
> 定方向、选模式，确认后才动手。** 产出物：真实的 H.264 MP4（含原创配乐）+ 海报帧，非 AE 工程、非预览页面。
>
> 长内容已拆到 `references/`（渐进式披露）：本文件只保留流程、铁律与清单，每节末尾的"详见"指向全文。

## 环境设置（每个命令块开头都要带上）

```bash
export PATH="/opt/homebrew/opt/ffmpeg-full/bin:/usr/local/opt/ffmpeg-full/bin:$PATH"   # ffmpeg-full 是 keg-only，默认不在 PATH
PY=~/.aaaai-editor/bin/aaaai-editor-python          # 套件自带解释器：已装 numpy/scipy/pillow/playwright(Chromium)/fonttools/brotli/opencc
SK=<本 SKILL.md 所在目录>/scripts     # 脚本在本 SKILL.md 同目录的 scripts/ 下（记为 $SK）
```

- skill 可能装在 `~/.claude/skills/<name>`、`~/.agents/skills/<name>`（Codex）或插件缓存目录——**一律按本 SKILL.md 的实际路径推出 `$SK`**，不要写死。模板在同目录 `assets/`。
- **shell 变量不会在两次独立的命令调用之间保留**：每个命令块都要重新 `export PATH` / 设 `PY`、`SK`，或直接写绝对路径。
- 脚本内部自行解析 ffmpeg：`$AAAAI_EDITOR_FFMPEG` → `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` → `/usr/local/opt/ffmpeg-full/bin/ffmpeg` → PATH 上的 `ffmpeg`（ffprobe 取同目录）。
- 环境自检、可选增强依赖、项目目录结构：详见 `references/environment.md`（§13）。

核心管线（Verify 刻意放在昂贵的全量渲染**之前**）：

**intake → deconstruct → harvest → direction → ★concept → grid → author → prerender → verify → render → score → encode → deliver → iterate**

> `concept`（§4.7 构思定稿）是**不可跳过**的一步：先用一句话锁定"这支片是什么"，再去 §7 配方库取材。
> 跳过它 = 从效果目录里挑零件拼装 = 成片有"零件感"。

## 0. 五条操作原则

1. **结构可迁移，像素不可迁移。** 拿到参考片时提炼它的*剪辑公式*（段落结构、节奏、冲击点位置），不是抄它的画面。公式才能换品牌复用。
2. **确定性构建。** 每一帧必须仅由帧号决定。禁止墙钟时间、渲染期随机数、CSS 动画。
3. **先验证再渲染。** 单帧抽查每个时间轴地标只花几秒；一次报废的全量渲染是 15–25 分钟。永远不跳过 contact sheet。
4. **音乐和画面共用一张网格，但网格是参照不是磁铁。** 定一个 BPM，让**锚点**（唯一的硬冲击、数字锁定、drop、尾板进入、Logo 落定）精确卡在拍/小节线上；**其余事件由内容决定**（句子讲完、数字滚停、字读完、动作落定），不要四舍五入到网格。音画同步靠共用同一份 `T` 常量，不靠把所有东西吸附到拍上。详见 §5.2。
5. **冲击点越少越贵。** 一次果断的撞击 = 自信；多次 = 廉价预告片味。其余全部用缓动完成。（柔和模式甚至零硬切——见 §1 模式 B。）

---

## 1. 制作模式选择

七种经过实战验证的模式。**Intake 时根据需求选定一种（或以一种为主干挂载模块），并向用户复述确认。**
有参考片时以参考片拆解结果（§3）为准，模式服从参考片的结构。

| 模式 | 适用需求 | 结构骨架 | 典型时长 | 气质关键词 |
|---|---|---|---|---|
| **A · 冲击型品牌宣传片** | 活动倒计时、发布预告、数据/成就展示、品牌宣传 | 五拍结构：tension → burst → payload → breath → resolve；全片仅一次硬冲击（burst）；硬切走黑场 | 30–40s | 有力、仪式感、drop |
| **B · 柔和产品演示片** | 产品/App 演示、数据面板展示、"高级感"品牌片、静音自播 | 零硬切；转场只用 blur + scale + opacity；背景光晕色相全程漂移；里程表数字开场 → 产品推拉演示 → 逐字文案 → 坍缩留黑 → 尾板 | 18–25s | 产品级、克制、丝滑 |
| **C · Logo Sting / 变身片** | Logo 收尾签名、品牌重塑（旧变新）、快闪片头 | 5 小节 sting：seed/build → break（碎裂）→ 迁移/变形 → drop（新形象锁定）→ 色波脉冲 → hold | 8–12s | 精准、像素级、爆发 |
| **D · 社媒转化型** | 促销/招募/联名活动、带 CTA 的社媒投放、赞助商单 | 钩子问句 → 3D Logo 亮相 → 唯一黑场呼吸 → 数字滚动 → 权益/步骤卡片 → CTA 长驻(≥3s) → 擦除 → 联名尾板 | 20–24s | 转化、节奏快、信息密 |
| **E · 数据仪表盘揭示型** | 季度报告、年度回顾、KPI 播报 | 趋势线开场 → 逐项 KPI 卡片揭示（复用 §7.2 数字类）→ 排名/对比图表 → 洞察金句 → 总结卡 | 25–35s | 数据感、专业、克制 |
| **F · 循环片头 / Loop Intro** | 直播/活动开场循环 bumper | 无固定头尾——整段是循环单元，`t=0` 与 `t=loop_duration` 的所有缓动函数取值必须逐一相等（不是像素级，是参数值相等） | 4–8s（循环） | 氛围性、背景感、不抢眼 |
| **G · 见证 / 案例故事型** | 客户证言、before/after | 痛点场景 → 转折 → 见证引语（逐字扫光）→ 数据佐证（§7.2/§7.6）→ 品牌收尾 | 30–45s | 真实、有温度、克制的煽情 |
| **附加模块 · 真实产品录屏** | 可挂载于 A/B/D/G 的 "proof" 段 | 设备框 + canvas 逐帧回放 + playlist 映射，文案与画面逐拍对齐 | 挂载 5–12s | 真实、可信 |

- **冲击纪律**：A/C/D 允许硬冲击与 3 帧黑场硬切；**B/F 严禁任何硬切**（`select='gt(scene,0.1)'` 场景检测必须返回 0 个切点）。
- **循环纪律**：F 严禁任何黑场硬切与不对称头尾，渲染验证时额外检查首尾帧参数值差 = 0（不是查像素，是查驱动动画的每个变量取值）。
- **能量形状**：A/C 必须有 breakdown → drop；B 的能量是"亮度涨—平—落"的多峰呼吸；D 的最响点给数字锁定或 CTA；E 的最响点给核心 KPI 卡；G 的情绪峰值给见证引语的逐字扫光落点。
- **静音可读性**：D（以及所有社媒 9:16 投放）必须关声音看一遍全片仍然成立；B/F 天生适合静音版。
- 用户需求跨模式时（例如"倒计时 + 产品演示"），选一个主干模式，把另一模式的段落当模块插入，时长相应加整小节。

---

## 2. Intake — 制作前必问（不问不开工）

**原则：先问再做。改文字便宜，改帧贵（一次重渲 8–25 分钟）。**
用选择题形式问（Claude Code 用 AskUserQuestion；其他平台见文末），每轮 ≤4 题，给带倾向的选项。有附件时跳过对应项，直接从附件实测抽取（§4）。

### 2.1 内容硬门槛（每单必问，问不到不开工）

1. **这支片替谁说话？** 主品牌 vs 赞助商/联名方——决定谁当英雄镜头。有联名/赞助时走 §4.4 双品牌规则。
2. **核心信息是什么？** 一句话 + 一个关键数字（名额/天数/金额/人数——数字滚动段的落点；没有数字就问要不要用 "LIMITED" 类大字替代）。这决定 payload 放什么，整条时间轴围绕它排。
3. **CTA 是什么？** 精确文案 + **唯一**行动入口（URL/二维码）。多入口时逼用户选一个主入口，其余进尾板小字。
4. **画幅与渠道**：16:9 / 9:16 / 1:1 / 4:5（可多选）；发什么平台（决定安全区与封面帧要求，§10.4）。
5. **片长**：10–15s 快闪 / 20–25s 标准 / 30s+ 完整叙事。信息量和片长必须匹配，塞不下就砍信息或加时长。
6. **制作模式**（§1）：向用户描述 A/B/C/D 各一句话，让他选；或由参考片决定。

### 2.2–2.5 设计问询、素材清单、附件原则、结构确认

- **2.2 设计问询**（无 Brand Book 时必问）：颜色 HEX / 深浅底、风格、色调情绪、字体、配乐（情绪与 BPM 感觉）、尾板要素、禁忌、参考片。
- **2.3 素材清单**：Logo（**完全没有 Logo 就做纯文字排版片并明说——绝不伪造品牌资产**）、Brand Book、产品截图/录屏（**逐段隐私审查**）、文案（**大小写逐字确认**）、参考片。
- **2.4 有附件时**：能从附件里量出来的一律实测不目测；附件是唯一真相源；与品牌规则冲突时照用户要求做 + 一次性指出冲突；"你看着办"时把所有默认值在交付说明里逐条列出。
- **2.5 结构确认（动手前最后一步）**：用文字复述整片结构给用户确认（"开场 X 秒滚数字 → 中段 X 秒产品/信息 → 文案 X 秒 → 尾板 X 秒，色调从 A 漂到 B，模式 B 零硬切，对吗？"）。

详见 `references/intake-details.md`（§2.2–§2.5 全文，含每项的选项清单与降级方案表）。

---

## 3. Deconstruct — 参考片拆解方法论

拿到 reference clip 时，目的不是抄帧，是**提炼可迁移的结构**。产出=剪辑公式，先给用户看再动手。

- **一键分析**：`$PY "$SK/analyze_reference.py" ref.mp4 --out tmp/ref`（元数据 + contact sheet + 高清抽帧 + 响度/瞬态表）；切点检测用 `$PY "$SK/detect_cuts.py" ref.mp4 [预期帧数]`（自带管道校验——**结果为 0 时先证明管道确实产出了数据**）。
- 三条分析管道（元数据/抽帧、场景切点、音频包络）与三条"节奏谱"曲线、以及 8 条高频可迁移法则（§3.3），详见 `references/deconstruct.md`。

### 3.2 输出「剪辑公式」

按时间码列段落表（段名/画面事件/亮度/音频事件），压缩成：**一个时间轴常量对象 + 一条色温曲线 + 几条铁律**。多数短促品牌片是五拍结构的变体：

**tension（黑场引信 1–2s）→ burst（一次硬冲击）→ payload（核心信息/数字）→ breath（黑场呼吸+一句话）→ resolve（logo + CTA）**

音频硬 transient 的位置就是视觉剪辑点。**参考片只有一次冲击的，你加第二次就俗了。**
"权益列表"型 payload 可扩展为子段：痛点问句 → 概念/UI 抽象 → 黑场金句 → 逐词权益行 → 真实录屏 proof。

**公式库复用**（两个库都读）：
- 示例库（只读）：本 skill 的 `references/formula-library.md` 及其 `*-case.md`——全部是**作者示例案例（第三方品牌，仅作拆解学习）**，品牌色与文案不可套用。
- 用户库（读写）：`~/.aaaai-editor/formulas/formula-library.md` 与 `~/.aaaai-editor/formulas/<project>-case.md`。

动手拆解前先查两个库有没有相近气质/模式的既有公式可直接起步。新拆解完成后，**必须**把这次的公式追加进**用户库**（`mkdir -p ~/.aaaai-editor/formulas`；新增一行索引，细节多就新建 `~/.aaaai-editor/formulas/<project>-case.md`，格式参照 `references/abcd-colony-case.md`）。**不要写进 skill 目录**——套件更新时会被整个覆盖。

---

## 4. Harvest — 品牌资产收割

要点（全文详见 `references/harvest.md`，§4.1–§4.5）：
- **Logo**（`$PY "$SK/logo_tools.py"`）：平底色抠图后**重读保存的文件验证**；沿主轴逐像素采样真实色标；**尽早切开 lockup**；字形共用一条垂直裁切带；几何用连通域实测。
- **Brand Book**：HEX + 渐变 stop + 方向规定；**限用规则比色板本身更重要**；Misuse 页逐条当硬约束。
- **无色值时**：从 Logo 取两端色 + 主色，**回报用户确认后**使用。
- **双品牌**：票/产品/权益属于谁，谁当英雄镜头；不替赞助商编造产品功能。
- **录屏/截图**：数据一致性检查（片中数字与界面必须一致）；深色 UI 近无缝，浅色 UI 加机身框。

### 4.6 方向定稿（写场景前的强制对比稿）

品牌资产收割完成后、正式进入 Grid/Author **之前**，**必须**先出 2–3 版关键帧静态对比（配色方向、字体组合、整体气质），给用户选定方向再往下走——不要等整场景写完、用户看了成片才说"风格不对"再返工。

- 用 Pillow/HTML 快速出几张**静态**对比帧即可（几秒钟成本）；每版标注清楚差异点（如"A 高饱和撞色 / B 低饱和高级灰"）。
- 用户选定后，把选中方向的参数（色板、字体、风格关键词）写进 §6 场景的顶部常量，作为唯一真相源。这一步把 §11 里"主观二选一 → 渲对比静帧"提前成默认步骤。

### 4.7 ★ 构思定稿（One-Idea Lock）——动手前必须锁死，不可跳过

病症：成片"有配方、没构思"，像从效果目录里挑零件拼出来的。实测高完成度参考片（作者示例案例（第三方品牌，仅作拆解学习），如 JUP 系列）每一支都是**一个统一构思贯穿到底**；可学的是这个结构，其配色（如 JUP 的绿/青分工）**仅适用于 JUP 品牌，不可推广**。

**做法：在 §4.6 之后、写 §5 时间轴之前，用一句话写出构思并让用户确认。** 句式（三个要素缺一不可）：

```
这支片是「<一个贯穿性的东西/结构>」——
它在片中反复以 <形态A>、<形态B>、<形态C> 出现，
因此 <明确排除掉的效果类别> 一律不用。
```

例：「这支片是**一次从暗到亮再回暗的呼吸**」——暗场提问、亮场给答案、暗场收束，因此任何"多次冲击"的配方（多波色浪、连续 burst）一律不用。

**三条硬性约束：** ① **只能有一个构思**（两个都舍不得就选一个当主干，另一个降级为某段手法）；② **必须能指认一个贯穿性载体**（光、卡片、环、明暗、某个图形），至少以 **3 种不同形态**出现——指认不出的构思是空话（如"科技感""高级感"）；③ **必须排除东西**，写不出"因此不用什么"就等于没定。

**与 §7 的关系：** §7 是**取材库，不是菜单**——每挑一个配方都要答得出"它如何服务于这个构思"，答不出就不用，**即使它很好看**。验收在 §10.1。

四支参考片各自的构思对照表、更多例句，详见 `references/concept-lock.md`。

---

## 5. Grid — 音乐网格时间轴（全流程最高杠杆的两分钟）

### 5.1 信息密度校验（定 BPM 前先算）

**"太赶太挤"是 §11 里付过学费最多的一条反馈——用公式在动手前拦住。**

```
最短所需时长 ≈ max(文案总字数 / 4.5, 信息卡数量 × 2.5) + 尾板占比(10–13%)
```

- 中文舒适阅读速度基准 **~4–5 字/秒**（含理解停顿，取 4.5 做保守估算）；信息卡最短停留复用 §7.8 的"2s 地板"，这里保守取 2.5s。
- 若 Intake 定的片长小于这个下限，**在写场景前**就回头跟用户说明：要么精简文案，要么拉长片长——不要硬塞。

### 5.2 定 BPM 与时间轴

- 定 BPM。**120 BPM（beat=0.5s，bar=2.0s）是 promo 通用默认**；紧张倒计时 ≈128+，抒情 ≈90。片长凑整小节数（16/18/21/24s…）。
- **锚点**（全片就那 3–5 个：唯一的硬冲击、数字锁定、drop、尾板进入、Logo 落定）**必须精确卡在 beat/bar 线上**（帧级精度）。
- **其余所有事件的时间点，由内容本身决定**（句子讲完、数字滚停、读完最后一个字、物体落定），**不要四舍五入到网格上**。
- ⚠️ **不要用随机抖动伪造"人味"**——随机 jitter 读起来是邋遢。网格是**参照物，不是磁铁**。
- 时间轴写成场景文件顶部**单一常量对象 `T`**，所有渲染函数只引用它；**配乐脚本逐字复制这份常量**——"改时长"永远是两个文件的编辑（场景+配乐）。

为什么这样定（实测统计：卡拍与否是逐片、逐刀的选择）、带 ●/· 标注的 `T` 示例、以及 A/B/C/D 各模式验证过的时间轴骨架，详见 `references/grid-timing.md`。

---

## 6. Author — 场景编写铁律（单一自包含 HTML）

起步模板：`assets/scene_template.html`（占位文案与灰白双色板，**必须按用户品牌替换**）。核心铁律：

- **确定性契约**：`window.__render(frame)` 纯函数 + 资源全部 decode 后才 `window.__ready=true`；禁 `Date.now()`、渲染期 `Math.random()`、CSS animation/transition；随机用构建期 seeded PRNG；渲染器挂 `pageerror`。
- **脉冲只用窗口式 `imp()`**，绝不写 `1 - progress` 型闪光（整片洗灰）。按角色选缓动：`eExpo` 给"到位"，要*读*的揭示用 ~2s 慢 cubic。
- **布局**：居中 flex 列 + `width:max-content`；字号基准 `S = sqrt(W*H/(1920*1080))`；宏观布局走单一 `LAY` 对象；letter-spacing 必配等值 `text-indent`；**所有用户可能改的字符串提为顶部常量**。
- **叠加层顺序**：背景光晕 → 大字 → 产品层 → 文案/尾板 → 暗角 → 扫描线 multiply → 动态颗粒 → imp 闪光 → 收黑层。
- **模式 B**：转场只用 blur + scale + opacity、色相全程漂移、永不静止。
- **性能**：成本在栅格化不在 JS——先杀 blur 层；大层辉光预渲染 PNG；画外元素 `display:none`。
- **Alpha 图层**：`--alpha` 渲染时场景读 `alpha=1`，跳过所有背景/氛围/收黑层，只留前景；产出 PNG 序列，供以实拍为主的剪辑流程（aaaai-editor）叠加。

全文（含缓动词汇表代码、alpha 契约代码与命令）详见 `references/scene-authoring.md`（§6.1–§6.7）。

---

## 7. 效果配方库

> **⚠️ 进入本节前必须先完成 §4.7 构思定稿。** 这是**取材库，不是菜单**——每取一个配方，先回答"它如何服务于我锁定的那个构思"；答不出来就不用，**即使它很好看**。

分类：7.1 文字类（渐变扫光、逐字扫描、decode）· 7.2 数字类（老虎机计数器 / 里程表滚轮）· 7.3 Logo/3D 类（挤出、burst）· 7.4 变身/重组类（模式 C 核心）· 7.5 转场类 · 7.6 产品演示/录屏 · 7.7 背景/氛围（预渲染辉光边界契约）· 7.8 收尾类（坍缩留黑、分步信息卡 2s 地板、尾板、Logo 独立签名收尾）。

详见 `references/effects-cookbook.md`（§7 全文）；代码实现见 `references/motion-recipes.md`。

## 8. Prerender — 昂贵图层离线预算

两类东西必须用 Python 一次算好，绝不逐帧 CSS 算：

1. **辉光/光环/bloom PNG**（§7.7 边界契约；`$PY "$SK/make_glow.py" --out assets --spectrum "<品牌色…>"`，默认色只是灰白占位），场景内只动 transform/opacity，`mix-blend-mode:screen` 合成。CSS blur 逐帧全屏计算是渲染速度头号杀手。
2. **挤出 slabs**（`logo_tools.py slabs`）：亮度斜坡 0.58→0.18 + 冷色调离线生成；lockup 有独立动画的词就先切再各生成一套；生成前 strip 掉发丝线行。

## 9. Score — 原创配乐合成（numpy/scipy，零素材零版权）

**原则：编曲从视觉时间轴出发**——场景 `T` 常量原样复制进配乐脚本；每个视觉事件一个 hit，同步是查表。
关键：**没有 breakdown，drop 落不下来**；尾板前 groove 清空，留衰减主和弦托住 logo（held frame over silence 读作事故）；计数器 tick 密度与画面同一条缓动；验证每小节 RMS 形状与影片一致；**改片长 = 场景 + 配乐两个文件同改**；静音版必须关声音看一遍仍成立。

和声、乐器库、侧链、混响、验证与静音版全文，详见 `references/score.md`（开头为中文 §9 全文，后接英文代码）。

---

## 10. Verify → Render → Encode → Deliver

### 10.1 渲前验证（省时间最多的一步，每轮修改后都做）

```bash
export PATH="/opt/homebrew/opt/ffmpeg-full/bin:/usr/local/opt/ffmpeg-full/bin:$PATH"
PY=~/.aaaai-editor/bin/aaaai-editor-python; SK=<本 SKILL.md 所在目录>/scripts
# 每个时间轴地标各渲一帧 → 拼 contact sheet → 亲眼看
$PY "$SK/render_frames.py" --scene scene.html --w 1920 --h 1080 --fps 60 --dur 24 \
        --out tmp/check --at 1.9,4.2,6.6,9.6,12.4,15.8,18.6,22.0
ffmpeg -pattern_type glob -i "tmp/check/*.jpg" -vf "scale=480:270,tile=4x2" tmp/sheet.jpg
```

**数值哨兵**：逐帧 mean luma 打表（近黑帧 8–12；黑场呼吸帧 <5；>25 = 漏光，多半 `1-progress` 型闪光；全部趋同 = 场景挂了）；辉光 PNG 四角采样必须 [0,0,0]；粒子可见数 ≈ 一半 = spawn/wrap 不匹配；3D 要验证**落定角度**那帧（透视近端 +7% 可能切边）。

**设计自检**（与数值哨兵并列做，不是替代）：层次与主次是否清晰（一眼知道看哪里）？留白是否足够？色彩重心是否服务于品牌而非装饰性铺满？每个动作是否必要（§0 第 5 条，能删就删）？

**★构思落地验收（§4.7 的验收关口，必做）：** 从 contact sheet 里**随机抽三帧**（不要专挑最好看的），逐帧问：
1. 这一帧里，那个贯穿性载体在哪？以什么形态出现？
2. 三帧的载体形态**各不相同**吗？（相同 = 载体没有发展，只是重复贴同一个元素）
3. 指得出这三帧共同服务于同一个构思吗？

**指不出来 = 构思没落地。此时要改场景结构，不是加效果**——回 §4.7 重看构思，删掉不服务于它的图层。

### 10.2 渲染与编码

```bash
export PATH="/opt/homebrew/opt/ffmpeg-full/bin:/usr/local/opt/ffmpeg-full/bin:$PATH"
PY=~/.aaaai-editor/bin/aaaai-editor-python; SK=<本 SKILL.md 所在目录>/scripts
# 全量渲染：后台运行 + 轮询（工具超时不能杀进程；预算 ~1s/帧/worker）
nohup "$PY" "$SK/render_frames.py" --scene scene.html --w 1920 --h 1080 \
        --fps 60 --dur 24 --out frames/L --workers 2 > render.log 2>&1 &
# 轮询：tail -n 3 render.log ; ls frames/L | wc -l   （Claude Code 也可用 Bash 工具的后台模式跑同一命令）
bash "$SK/encode.sh" frames/L out/film_16x9.mp4 --audio out/score.wav --fps 60   # H.264 high/CRF17/+faststart
```

**编码后必验**：`nb_frames == dur×fps`、音视频时长逐位相等（被超时杀掉的 ffmpeg 会留下"能播放的截断文件"）、`ffmpeg -v error -i out.mp4 -f null -` 完整解码。多 worker、局部补渲（`--at`）、多画幅重导、运动模糊、兼容降级版，详见 `references/delivery.md` §10.2。

### 10.3 交片前六查（缺一不发）

1. 转场纪律符合模式（B：场景检测 0 切点；A/C/D：冲击次数 ≤ 设计值）。
2. 帧数 = 时长×fps，音视频同长。
3. 黑场检查：应黑帧均亮 5–12。
4. 静音可读：关声音看一遍，节奏纯视觉成立。
5. 数据一致：大字数字/日期/URL 与界面素材、与用户确认的逐字一致。
6. 多版本同源：所有画幅都是最新代码渲的。

### 10.4–10.5 平台安全区与交付包

- **每支片必须有至少一个封面级帧**（≥1.5–2s 稳定 hold、核心元素在安全区内、缩图可读），同尺寸 JPG 随片交付。9:16 的双重安全区是 **1080×1120, y 400–1520**。
- 交付：每尺寸一个 MP4（帧数验证过）+ 2–3 张海报帧；一两句话说明改了什么 + **明说哪些参数是一行改**；任何自主判断都要披露并给替代选项；命名 `{project}_{duration}s_{aspect}.mp4`；alpha 版用 ProRes 4444（`encode.sh --alpha`），**不要用 VP9/WebM 封 alpha**。

平台尺寸表、alpha 交付细节、大文件备用通道，详见 `references/delivery.md` §10.4–§10.5。

---

## 11. Iterate — 修改意见

**攒一轮意见一起改**（每轮 = 一次完整重渲），改完先 contact sheet 再全量。用户的批注是症状不是病因——先复现、看单帧、找真实缺陷。**用户说"只改这两处"就只改这两处**，不夹带优化。"再强一点"时**先别加效果**，多半是构思（§4.7）不够强。批注 → 动作 → 成本的完整路由表与付过学费的通则，详见 `references/iteration.md`。

## 12. 踩坑速查 · 13. 环境自检

- §12 症状 → 原因 → 修法速查表（中文）与诊断详解：详见 `references/gotchas.md`。调试任何画面问题前先读它。
- §13 环境自检命令、字体、性能预算、可选增强依赖（`$PY -m pip install --user …`）、项目目录结构：详见 `references/environment.md`。

---

## 14. 新项目执行清单（照此跑一遍即可复现全部能力）

1. 环境自检（§13）。
2. **Intake（§2）**：收附件；缺什么问什么（内容硬门槛 → 设计问询 → 素材清单）；选制作模式（§1，A–G 七选一或挂载模块）；**文字复述结构确认后才动工**。
3. 有参考片 → 先查示例库 `references/formula-library.md` 与用户库 `~/.aaaai-editor/formulas/` 有没有相近气质/模式的既有公式可直接起步；没有相近的才走 §3 从头拆解，给用户确认，拆完追加进**用户库**。
4. 收割品牌资产（§4）：实测取色、切 lockup、共用垂直带切字形、读 misuse 规则。
5. **方向定稿（§4.6）**：出 2–3 版关键帧静态对比，用户选定方向后再往下走。
6. **★构思定稿（§4.7）**：一句话锁定"这支片是什么"＋贯穿性载体＋明确排除的效果类别，用户确认后才进 §7 取材。**跳过这步 = 成片有零件感。**
7. 信息密度校验（§5.1）→ 定 BPM 写 `T` 对象（§5.2）。
8. 编写场景（§6）：确定性契约、seeded PRNG、居中 flex、S 缩放、常量提升、imp() 脉冲。**取 §7 配方前先过构思闸门**。
9. 预渲染辉光（验证零边界）与挤出 slabs（§8）。
10. 从视觉时间轴写配乐（§9）：同一 T、breakdown 在 drop 前、尾板前 groove 清空、验证每小节 RMS 形状。
11. 关键帧抽查 + contact sheet + 数值哨兵 + 设计自检 + **构思落地验收**（§10.1）。
12. 后台全量渲染 → 编码 → 验证 nb_frames（§10.2）。
13. 交片六查（§10.3）→ 交付 MP4 + 海报帧 + 一行改参数清单（§10.5）。
14. 攒批注按 §11 路由，重复 11–13。

---

## 在 aaaai-editor 套件里（与剪辑、收尾衔接）

本 skill 负责**动画与品牌片的创意和渲染**；成片的字幕、响度、封面、验收交给 `aaaai-editor`：

- **叠进口播**：场景按 §6.7 透明契约渲染 → `bash "$SK/encode.sh" <帧目录> <out.mov> --alpha` 出 ProRes 4444 `.mov` →
  在 aaaai-editor 的 storyboard 加 `{"type": "clip", "t": [起, 迄], "file": "<mov 路径>", "width": 1.0}`。
- **整支动画成片**：`~/.aaaai-editor/bin/aaaai-editor adopt <成片.mp4> --out <项目>/storyboard.json`（有人声就会转录）→
  照 aaaai-editor 流程做字幕／响度 -14 LUFS／封面 → 交给 social-content-pipeline。
- 需要更完整的时间轴工具、组件库、网站抓取：HeyGen HyperFrames（`/hyperframes`，Apache-2.0，安装器会装好；**仅 Claude Code 可用**）
  可作为渲染引擎，本 skill 的构思定稿、拆解方法与公式库照样适用。
- `references/*-case.md` 里的拆解案例 © MR ONE，是作者示例案例（第三方品牌，仅作拆解学习），随套件提供作为学习参考。

## 在其他平台使用（Codex 等）

本手册按 Claude Code 编写；在 ChatGPT Codex 等平台上照下面替代：

- **没有 AskUserQuestion**：把本轮要问的题（每题带编号选项和推荐项）一次性列在一条消息里，等用户回复编号再继续；§2 的"不问不开工"不变。
- **没有后台 Bash**：全量渲染与编码一律 `nohup <命令> > render.log 2>&1 &` 启动，再用 `tail -n 3 render.log`、`ls frames/L | wc -l` 轮询，直到帧数 = 时长×fps 后才编码。
- **没有 SendUserFile**：交付时直接给出成片、海报帧、alpha 序列的**绝对路径**清单。
- **HyperFrames 插件只在 Claude Code 可用**：Codex 上遇到讲解片／网站转影片／幻灯片类需求，告诉用户需在 Claude Code 里用 `/hyperframes`，或改用本 skill 的纯代码管线完成。
- 路径：skill 可能装在 `~/.agents/skills/motion-graphic-video-editor`，`$SK` 一律按本 SKILL.md 实际位置推出。
