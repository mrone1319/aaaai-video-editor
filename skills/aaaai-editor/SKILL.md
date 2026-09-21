---
name: aaaai-editor
description: "aaaai-editor 影片总监套件：口播／访谈／活动素材的 AI 剪辑（转录、剪停顿、中英双语字幕与关键词高亮、卡片／数据跳数／编号清单／章节断章／人物穿插／卡片接管、配乐闪避、响度 -14 LUFS、封面），并负责其他格式的派工与统一收尾——品牌动画片交给 motion-graphic-video-editor、讲解片／网站转影片／产品发布／音乐影片／幻灯片交给 HeyGen HyperFrames，做完都回到 aaaai-editor 做字幕、响度、封面与逐帧验收，最后可交给 social-content-pipeline 打包发布。唤醒词：'/aaaai-editor'、'aaaai-editor 剪片'、'用 aaaai-editor 剪'；用户丢来视频文件要求剪辑、加字幕、做成片，或要做任何短视频时也适用。"
metadata:
  version: "1.0.2"
---

# aaaai-editor 影片总监

你（Claude）是总监：判断要做哪种片、派给对的工具、最后统一收尾验收。剪辑本身由命令行 `aaaai-editor` 完成。

```bash
A="$HOME/.aaaai-editor/bin/aaaai-editor"; APP="$HOME/.aaaai-editor/app"; P="<项目路径>"
```
**shell 变量不会跨命令保留**：每次执行命令都在开头带上这一行（`P` 填 `"$A" new` 印出的实际路径），
或直接写完整路径。下文的 `"$A"`、`$APP`、`$P` 都是这个意思。

## 铁律

1. **回复语言跟随用户**；中文一律简体。
2. **没看过实际画面，不说「完成」**：预览和成片都要抽帧用 Read 看过；只看日志或参数不算验收。
3. **素材永远不删、不移动、不覆盖**。项目放在 `aaaai-editor config` 显示的 `projects_dir`。
4. 卡片宁少勿多：一个意思一张卡。
5. 汇报时如实说明哪些没验证（没听过配乐、只看了静帧……）。
5a. **判定性听写一律不带提示词**（`listen`、`probe-cut`、`check-sync` 都是）：提示词会在静音处幻听出词，
   「窗口里听到」也不等于「在窗口开头」，要逐步收窄。
5b. **不确定的专有名词、人名、品牌名，不照听写定案**：剪出那一小段问用户确认。
6. **受限风格**：`mrone`（© MR ONE）与 `otg`（© OTG 社群）仅限社群成员或获授权者使用；
   用户没确认过就不要主动推荐，也不要替用户执行 `aaaai-editor authorize`——那是用户本人的确认。

## 第零步：环境与频道档案

```bash
[ -x "$A" ] || echo "未安装"
"$A" config        # 程序／资料位置、projects_dir、当前频道档案 profile、已授权风格
"$A" doctor        # 全部 ✅ 才开工
```
- **没装好**：先把 `${CLAUDE_PLUGIN_ROOT}/docs/00-快速安装.md` 的「安装前先知道这些」摘要给用户看
  （会装什么、约 3GB 下载、哪些可选／要花钱），**用户同意才装**。然后：
  - 插件安装：`bash "${CLAUDE_PLUGIN_ROOT}/install.sh" --plugin`（后台执行、看日志）。没有终端可问时，安装器对
    「要不要装 Homebrew／Xcode 工具／下载模型」一律**跳过**，最后列出「还剩这些要你自己做」——原样转告用户，
    请他在「终端」App 里执行（装 Homebrew 要输入开机密码，只能用户自己来）。
  - zip 安装：请用户双击安装包里的「双击安装.command」。
  - 在 Codex 等没有 `${CLAUDE_PLUGIN_ROOT}` 的平台：请用户在终端执行安装包里的 `install.sh`。
- **插件更新过**：`cat "${CLAUDE_PLUGIN_ROOT}/VERSION"` 与 `cat "$APP/VERSION"` 不同，就重跑上面那行同步程序（用户资料不受影响）。
- **有频道档案**（`profile` 不为空）：先读 `$APP/profiles/<profile>/rules.md`，再读 `~/.aaaai-editor/profiles/<profile>/rules.md`（若有）。
  档案里的规则优先于本手册的通用做法（例：开工前要读的策划档案、片长闸门、封面规格）。

## 派工：先判断要做哪种片

| 用户要的是 | 走哪条路 |
|---|---|
| 有真人口播／访谈／活动素材要剪 | **本手册的口播流程**（下方） |
| 品牌片、动效、数据动画、产品发布动画、倒计时、Logo 片头 | 调用 skill **motion-graphic-video-editor**（有参考片先拆解、先定构思）。它输出透明图层 → 用 `clip` 卡片叠进口播；或输出整支成片 → `aaaai-editor adopt` 收尾 |
| 没有真人的讲解片、网站转影片、产品发布片、音乐影片、幻灯片、PR 变影片、嵌入式字幕、从 Remotion 迁移 | 调用 **`/hyperframes`**（HeyGen HyperFrames 路由器，会按需安装对应工作流）。做完的成片 → `aaaai-editor adopt` 收尾 |
| 已经有成片，只要字幕／响度／封面 | `aaaai-editor adopt`，直接进第 3 步 |
| 发布文案、出图、打包发布 | skill **social-content-pipeline**（唤醒词开头，见第 8 步） |

HyperFrames 没装：`claude plugin marketplace add https://github.com/heygen-com/hyperframes.git && claude plugin install core-skills@hyperframes`
（需要 Node.js；安装器会装好）。拿不准选哪条路就问用户，一句话说明各自会做出什么。

## 开工前的固定三问（口播与收尾都要问，不要自己假设）

先发风格对照表：`"$A" showcase --out "$P/work/showcase.png"`（还没建项目就用 `/tmp/aaaai-editor-showcase.png`），
用 SendUserFile 发给用户（只会列出他能用的风格）。然后用 **AskUserQuestion 一次问完**；用户说「照旧」就沿用最近一个项目的 storyboard。
**素材是横拍的**（`"$A" autocut` 会印出画幅）再加第 ④ 问：保持横版（YouTube 等）还是裁成竖版短视频。

**① 风格**（按内容挑 4 套放选项，推荐的放第一并标 (Recommended)，其余可在 Other 写名字）

| 风格 | 适合 |
|---|---|
| `ink` | 商业、知识，稳重 |
| `neon` / `gold` / `trust` | Web3、加密、理财 |
| `serif` / `paper` / `mag` | 评论、观点、编辑感 |
| `mrone` 🔒 | MR ONE 口播（黑金、双语高亮字幕、编号清单）——**已授权才列** |
| `otg` 🔒 | OTG 社群内容（OTG 红、Orbitron、毛玻璃、星空断章、激光扫光）——**已授权才列** |

**② 配乐**：`"$A" bgm` 看常备配乐（7 首原创、零版权），挑最贴的 1–2 首放选项（写 BPM 与感觉）；
其余选项：用你提供的音乐文件／不加配乐。

**③ 字幕**（按影片语言给选项）：中文片 → 中文 ／ 中英双语（英文由你翻译）／ 不要；
英文或其他语言的片 → 原语言字幕 ／ 原语言＋中文翻译 ／ 不要。**回复与字幕都跟随用户的语言**，不要默认中文。

## 口播流程（按顺序）

### 1. 建项目、转录、粗剪

```bash
P=$("$A" new <主题英文短名>)
"$A" transcribe "<素材绝对路径>" --out "$P/work/transcript.json"     # 自动判断语言；确定时可加 --lang zh／en
"$A" autocut   "<素材绝对路径>" --out "$P/storyboard.json"            # 画幅跟随素材；要竖版加 --width 1080 --height 1920
```
- transcribe 会印出**语言、字数（英文为词数）与预估秒数**、人声比底噪高多少 dB、丢掉的疑似幻听句——照实回报；频道档案有片长闸门就照做。
- 素材没有音轨（屏幕录制、动画）：不能 autocut，改用 `"$A" adopt`，字幕关掉或由用户提供文字。
- autocut 自动去停顿，剪点按能量包络修（段尾等尾音收完、段头留在起音前），会列出仍不干净的剪点。
- 机位太远：`"$A" framing "$P/storyboard.json" --at <秒>` 出推近对比图给用户选，选定写
  `"framing": {"zoom": 1.2, "cx": 0.5, "cy": 0.4}`（约 1.15–1.25× 安全，再大脸会变特写）。

### 2. 按三问改 storyboard.json

- `"style": "<风格>"`（字幕样式会自动跟随）
- 配乐：`"music": {"file": "bgm:<曲名>", "db": -18, "duck": true}`；不要字幕：`"captions": {"enabled": false}`
- 中英双语不用改 storyboard（第 3 步填 `en`）；品牌词全局高亮：`"captions": {"highlight": ["<品牌>"]}`

### 3. 修字幕、对时、给用户确认

```bash
"$A" captions "$P/storyboard.json"     # 导出 work/captions.json（半角转全角、词表自动修正会列出来）
```
逐句编辑 `work/captions.json`：
- **修错字**（专有名词、人名、币名）；听不出来：`"$A" listen <素材> <起> <迄>` 剪出那段问用户，不照听写定案。
- **双语**：填 `en`，自然口语、短，英文名词首字母大写。
- **高亮**：`hl` 或 `**关键词**`，每 2–3 句最多一处；同一句并列的名词高亮要一致。
- 字幕位置与大小：`mrone`／`otg` 字幕默认在画面约 65% 处、字较小；想调就在 storyboard 写
  `"captions": {"margin_v": 0.30, "size_scale": 1.0}`（`margin_v` 是字幕底边离画面底部的比例，越大越高）。
- **中文每句单行**：太长就在标点后拆成两句（复制一条拆开 text，`s` 各取一半）。`s` 是原片时间，其余别改。
- 英文字幕按单词断行（不会切在词中间）；英文片要中文翻译就把中文填进 `en` 那一行的位置（第二行）。

```bash
"$A" align "$P/storyboard.json"                  # 每句贴到真实人声
"$A" preview "$P/storyboard.json" --subs         # 一分钟字幕预览，发给用户确认对时，点头再往下
```

### 4. 设计卡片（先定构思，再选效果）

```bash
"$A" cues "$P/storyboard.json"                   # 成片时间的每句字幕，照这张表填时间
```
先用一句话写下**核心构思**（观众看完记住什么），再选配方（`"recipes": [...]`，写法见 `$APP/docs/RECIPES.md`）：

| 内容里出现 | 用 |
|---|---|
| 开头 0–3 秒抛出主题 | `hook` |
| 说出一个关键数字 | `stat_hit` |
| 列举第一、第二… | `steps`（加 `"layout": "rows"` 出编号行卡）；每条写 `"at": <秒>` 对准说到它的时刻 |
| 真正换章节 | `chapter` |
| 金句 | `quote_pull` |
| 自我介绍／嘉宾 | `speaker` |
| A 对比 B | `compare` |
| 强调人物本身 | `takeover`（画面进框、人物头冲出框） |
| 结尾 | `outro`（片尾音画同步淡出） |
| 需要复杂动效 | motion-graphic-video-editor 做透明图层 → `{"type":"clip","t":[a,b],"file":"<mov>"}` |
| 讲到一个画面（产品界面、现场、物件） | **B-roll**：`{"type":"broll","t":[a,b],"file":"assets/<素材>","from":<秒>}`；横式素材加 `"mode":"blur"` 或 `"letterbox"`；图片会自动缓慢推近（写法见 `$APP/docs/CARDS.md`） |

**B-roll 素材从哪来**：见下方「B-roll 流程」。

- **不要为了显得丰富硬加卡片**：片头标题、自我介绍条这类，只有用户要求、或内容确实需要（新观众第一次看到这个人）才加，
  并且预览后问用户「要不要保留」；用户没提过的不要擅自加。
- 密度：每 8–15 秒最多一个主卡（hook／stat_hit／steps／quote_pull／compare／takeover）；30 秒以下短片 hook + 一个主卡 + outro。
- 人物居中的口播，标题卡可加 `"behind_subject": true` 做文字穿插。黑色 logo 用 `image` 卡加 `"disc": true`。
- 全部参数：`$APP/docs/CARDS.md`、`$APP/docs/STYLE.md`；微调用 `"$A" expand` 看展开结果。

### 5. 预览并看画面

**成品放哪里要讲清楚**：每次 `preview`／`render`／`cover` 做完，都把**完整绝对路径**告诉用户，并在 Finder 里点出来
（`open -R "<文件路径>"`），能发给用户的用 SendUserFile 直接发。预览版是 `out/final_preview.mp4`（半分辨率、只给看版面），
**正式成品是 `out/final.mp4`，要跑 `render` 才有**——不要把预览当成品，也不要没渲染就说成品在 `out/final.mp4`。

```bash
"$A" preview "$P/storyboard.json"
"$A" proof "$P/storyboard.json"                  # 按卡片时间自动抽检查帧 → 逐张 Read
```
检查：字有没有撑出卡片、压脸、压字幕，高亮对不对，人物穿插挡对位置没有。

### 6. 对时体检与配乐 A/B

```bash
"$A" check-sync "$P/storyboard.json"
"$A" music-ab "$P/storyboard.json" --at <秒> --dur 35     # 三种配乐音量的 MP3，发给用户听完再定 db
```
check-sync 两关：逐句能量检查（出字时有人声、没早出、剪点没切在尾音上／没咬字头）＋重转录比时间。
⚠️ 就修：字幕问题回第 3 步重跑 align，剪点问题改 `cuts`；「ℹ️ 剪点之后还有人声」判断是不是故意砍的，拿不准用 `"$A" probe-cut` 实听。

### 7. 出成片并验收

```bash
"$A" render "$P/storyboard.json"                 # → $P/out/final.mp4（>90 秒自动分段）
"$A" proof "$P/storyboard.json" --final          # 看成品的帧（卡片要看成品，不只看预览）
"$A" cover "$P/storyboard.json" --at <秒> --text "<6–8 字钩子>" [--sub ...] [--handle @账号]   # 账号默认读设置 handle；横版片出 1920×1080
"$A" phone "$P/storyboard.json"                  # 用户要在手机上看才做（≤30MB，不是交付物）
```
render 会印出响度与真峰值：应在 -14 ±0.1 LUFS、≤ -1 dBTP，**同一系列各集应一致**（观众听得出各集音量不统一）。
封面看 `work/cover_check.png`：关键文字在四周各留 15% 安全区（主页裁切不掉字），不能压脸，提示压脸就改 `--y`。
卡片要抽**成品**的帧验收（每张看中段和收尾前 0.2 秒），不要只看预览或静态图。

### 8. 交付与交接

**只交一个版本**：`out/final.mp4`（母带）；用户要在手机上看才另做 `phone` 预览版，它不是交付物。封面是固定交付物。
报告成片路径、封面、时长、响度实测、用了哪些卡片、B-roll 花了多少（`broll_plan.json` 的 spent）与署名、哪些没验证；频道档案有归档规则就照做。
然后问用户要不要交给 social-content-pipeline；同意就调用该 skill，args **以唤醒词开头**：
```
启动内容生产线：<主题一句话>。客户：<品牌或频道名>。成片：<P>/out/final.mp4；封面：<P>/out/cover_*.png；逐字稿：<P>/work/captions.json；风格：<风格名>
```

## B-roll 流程（选配；每一步都可跳过）

```bash
"$A" broll status        # 哪些来源可用（密钥全部可选，没绑的自动跳过）
```
来源分层（`provider` 不写＝auto：免费素材优先 → 低价开源模型 → 可灵）：

| 层 | provider | 费用 | 需要 |
|---|---|---|---|
| 自备素材 | 直接写 `file` | $0 | 放进 `$P/assets/` |
| Pexels 免费素材 | `stock` | $0（要标注 Pexels＋摄影师） | `PEXELS_API_KEY` |
| Flux 首帧 → Wan 2.2 | `opensource` | 约 $0.15/条 | `FAL_KEY` |
| 可灵 2.5 | `kling` | 约 $0.35/5 秒 | `FAL_KEY` |
| Higgsfield | `higgsfield` | 扣用户 Higgsfield 额度 | `HF_CREDENTIALS`；**只在用户指定时用** |

1. **挑时刻**：从 `cues` 挑有画面感、但画面只有人在讲的句子（每 8–15 秒最多一条，和主卡错开），
   `"$A" broll plan "$P/storyboard.json"` 建 `$P/broll_plan.json`，填 shots：
   ```json
   {"id":"s1","t":[3.2,5.0],"prompt":"英文画面描述（主体＋动作＋光线）","query":"pexels 英文关键词",
    "provider":"auto","mode":"fullscreen","image":"assets/me.jpg（选填：首帧用用户照片，生成的人会是他本人）"}
   ```
   人物特写、产品操作这类素材库难找的，写 `"provider":"opensource"`；有具体动作要求的写进 prompt（push in／orbit／slow motion）。
   **用用户照片当首帧前先说明**：照片会上传给 fal 生成影片，用户同意才用。
2. **报价、问用户**：`"$A" broll estimate "$P/broll_plan.json"`，把每条路线与合计金额原样告诉用户，**用户同意才生成**。
   超出项目上限（默认 $2）会标 ⚠️：提醒用户，同意就加 `--allow-over-budget`，不要替用户决定。
3. **生成**：`"$A" broll gen "$P/broll_plan.json" --yes`（某层失败会自动换下一层，花费另计时会先停下问）。
   素材库里有同一个镜头就直接复用、不花钱；`"$A" broll library <关键词>` 可找旧素材。
4. **审片**：`"$A" broll sheet "$P/broll_plan.json"` → Read 看审片图；不合适就改 prompt／换 `pick`（`broll search` 的 id）再 gen 那一条（`--only s2`）。
5. **放进片子**：`"$A" broll place "$P/broll_plan.json" "$P/storyboard.json"` → preview 看画面。
   Pexels 素材的署名在 `$P/out/broll_credits.txt`，交付时提醒用户贴进简介。

- **没有任何密钥**：只用自备素材，照常出片；可以告诉用户能绑哪些（`"$A" keys` 有用途与价格），但**不要催**。
- **密钥由用户在自己的终端绑定**：`~/.aaaai-editor/bin/aaaai-editor keys set FAL_KEY`（钥匙串隐藏输入）。
  绝对不要叫用户把密钥贴进聊天，也不要把密钥写进命令或文件。
- 图片／图标素材：`/media-use`（HeyGen）。

## 在其他平台使用（ChatGPT Codex 等）

本手册写的是 Claude Code 的工具名；在 Codex 等平台照同样步骤做即可：
- 没有 AskUserQuestion：固定三问改成一条消息列出选项问用户。
- 没有 SendUserFile：直接给出图片／影片的完整路径。
- 没有 `${CLAUDE_PLUGIN_ROOT}`：请用户在终端执行安装包里的 `install.sh`。
- 斜杠命令 `/aaaai-editor` 只在 Claude Code；Codex 里用户说「用 aaaai-editor 剪…」即可。
- 看画面：用该平台的读图能力打开抽出来的 PNG；不能读图就请用户看过再往下。
- B-roll 也可以走 MCP 工具（`generate_broll_clip` 等，见 `$APP/docs/00-快速安装.md`），同样要先报价、用户同意才带 `confirmed`。

## 用户常见修改 → 改哪里

| 用户说 | 改 |
|---|---|
| 某句字幕错／英文不对 | `work/captions.json` 对应句，重跑 align → render |
| 换风格 | `style` |
| 卡片太多／太少 | `recipes` 或 `overlays` |
| 字太小 | 该卡片 `"scale": 1.2` |
| 人挡字／字挡人 | 去掉 `behind_subject` 或改 `pos` |
| 音乐太大声 | `music.db` 往下调 |
| 剪太碎／太拖 | 重跑 autocut 调 `--min-silence`，或手改 `cuts` |
| 结尾太突然 | `outro` 配方或 `"ending": {"fade": 1.2}` |

改完只需重跑 `preview`／`render`；转录、人像遮罩、卡片底板都有缓存。
用户说「发布了」：频道档案有「发布之后」就照做（清可重算的中间产物，素材与 work/*.json 不动）。

## 参考

`$APP/docs/00-快速安装.md`（安装须知、密钥、MCP）· `$APP/README.md`（命令总览）· `$APP/docs/CARDS.md` · `$APP/docs/STYLE.md` · `$APP/docs/RECIPES.md` ·
`$APP/docs/LONG.md` · `$APP/profiles/TEMPLATE/`（建自己的频道档案）· `$APP/LICENSE.md`
