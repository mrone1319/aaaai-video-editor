# aaaai-editor 影片总监套件

**© 2026 MR ONE（@mrone.ai）** · 免费提供给被授权人 · macOS · 见 `LICENSE.md`

在 Claude Code（或 ChatGPT Codex）里说一句「/aaaai-editor」、丢一段视频，就能完成：转录 → 剪掉停顿 → 中英双语字幕与关键词高亮 →
按内容加卡片（数据跳数、编号清单、章节断章、人物穿插、卡片接管）与 B-roll（自备、Pexels 免费素材、低价 AI 生成，先报价再执行）→ 配乐闪避 → 响度锁定 -14 LUFS → 封面 →
逐帧验收 → 交给发布流水线。口播以外的格式（品牌动画、讲解片、网站转影片、产品发布、音乐影片、幻灯片）
由它派给对的工具，做完再回来统一收尾。

## 套件内容

| 组件 | 做什么 |
|---|---|
| `aaaai-editor`（skill）＋ `aaaai-editor` 引擎 | 总监：派工、口播剪辑、字幕、卡片、人像、响度、封面、验收 |
| `motion-graphic-video-editor`（skill） | 品牌片与动效：拆解参考片、构思定稿、公式库、透明图层输出 |
| `social-content-pipeline`（skill） | 发布：搜集、角度、X/IG 文案、出图、打包 |
| HeyGen HyperFrames（安装器从官方装） | 讲解片、网站转影片、产品发布、音乐影片、幻灯片等格式 |
| 9 套风格、41 个图标、10 条配方、7 首原创配乐 | `aaaai-editor showcase` 看风格对照表 |

## 安装

**先看 [`docs/00-快速安装.md`](docs/00-快速安装.md)**：里面写了会装什么、哪些可选、哪些要花钱、隐私、耗时与空间、更新、卸载和常见问题。

- **zip 安装包**（最简单）：解压后双击「双击安装.command」。如果被 macOS 拦下：打开「系统设置 → 隐私与安全性」，点「仍要打开」。
- **Claude Code 插件**（能一键更新）：先装好 Claude Code 和 GitHub 登录（`gh auth login` 和 `gh auth setup-git`），再用 **https 地址**安装：
  ```bash
  claude plugin marketplace add https://github.com/mrone1319/aaaai-video-editor.git
  ```
  ```bash
  claude plugin install aaaai-editor@aaaai-editor
  ```
  然后在 Claude Code 里说「/aaaai-editor」，它会讲清须知、经你同意后帮你装好依赖。

## 第一次用

> 📘 **新手先看《使用指南》**：`docs/使用指南.html`（双击用浏览器打开；也有 `docs/使用指南.pdf`）——
> 手把手第一次剪片、提示词格式范本、29 种小组件图鉴、风格、配乐与音效、改片说法、发布前验收。

- 在 Claude Code 里说「/aaaai-editor」，或直接丢一段视频说「帮我剪」；在 Codex 里说「用 aaaai-editor 剪 <文件>」。
  它会先问你：风格、配乐、字幕；如果素材是横拍的，还会问要不要裁成竖版。
- 中文、英文等语言会自动识别；竖版、横版、方形都能做。
- **社群风格**：`mrone`（© MR ONE）、`otg`（© OTG 社群）人人可用，排在风格清单最后、不作首选推荐；品牌归原权利人，请勿用来冒充。
- **建自己的频道档案**（剪辑规则、误听词）：复制 `~/.aaaai-editor/app/profiles/TEMPLATE` 到 `~/.aaaai-editor/profiles/<名字>`，
  再执行 `~/.aaaai-editor/bin/aaaai-editor config --set profile=<名字>`。
- **自己的风格**：放在 `~/.aaaai-editor/themes/*.json`（写法见 `themes/README.md`）。
- **B-roll 密钥（可选）**：`~/.aaaai-editor/bin/aaaai-editor keys` 看用途与价格，在自己的终端执行 `~/.aaaai-editor/bin/aaaai-editor keys set <名称>` 绑定。
  每次花钱前都会报价问你；每个项目默认上限 $2，超出会提醒。
- **封面账号名**：`~/.aaaai-editor/bin/aaaai-editor config --set handle=@你的账号`。
- **Codex、Claude Desktop、Cursor**：可以把 B-roll 做成 MCP 工具，命令是 `~/.aaaai-editor/bin/aaaai-editor mcp`（见快速安装第四节）。
- **成片在哪里**：Finder 侧栏点「影片」→ `aaaai-editor` → `成品`。每次正式渲染完，成片和封面会以项目名放一份在这里（例：`20260921-我的主题.mp4`）。
  项目本身（中间档、字幕轨）在 `影片/aaaai-editor/<日期-主题>/`。想换位置：`~/.aaaai-editor/bin/aaaai-editor config --set projects_dir=<路径> exports_dir=<路径>`。

## 资料放在哪里

| 位置 | 内容 | 更新时 |
|---|---|---|
| `~/.aaaai-editor/app/` | 程序本体 | 会被新版替换 |
| `~/.aaaai-editor/`（config.json、themes/、profiles/、glossary.json、fonts/、models/） | 你的设置与自定义 | **不动** |
| `~/Movies/aaaai-editor/`（Finder 的「影片」） | 你的项目；`成品/` 里是每支片的成片与封面 | **不动** |

## 命令总览（Claude 会替你执行，一般不用手打；没加进 PATH 时 `aaaai-editor` 写成 `~/.aaaai-editor/bin/aaaai-editor`）

```bash
aaaai-editor doctor                                  # 检查依赖
aaaai-editor transcribe clip.mp4                     # → work/transcript.json（自动判断语言，中文输出简体）
aaaai-editor autocut clip.mp4 --out storyboard.json  # 按静音生成 cuts（画幅跟随素材）
aaaai-editor render storyboard.json                  # → out/final.mp4
aaaai-editor preview storyboard.json                 # 半分辨率快速预览，先看版面节奏
aaaai-editor themes                                  # 列出风格与字体
aaaai-editor check-sync storyboard.json              # 字幕对时体检（重转录成片音轨逐句比）
aaaai-editor showcase --out showcase.png             # 渲染所有风格的对照表
aaaai-editor icons --sheet icons.png                 # 图标总表
aaaai-editor recipes                                 # 列出配方
aaaai-editor expand storyboard.json                  # 打印配方展开结果
aaaai-editor captions storyboard.json                # 导出可手改的字幕轨并自动对齐（--no-align 不对齐）
aaaai-editor cues storyboard.json                    # 按成片时间列出每句字幕（排卡片时间用）
aaaai-editor proof storyboard.json [--final]         # 按卡片时间自动抽检查帧
aaaai-editor align storyboard.json                   # 字幕逐句贴到真实人声
aaaai-editor preview storyboard.json --subs          # 只烧字幕的一分钟预览（可加 --from/--to）
aaaai-editor bgm                                     # 常备配乐（7 首原创，music.file 写 bgm:<曲名>）
aaaai-editor sfx                                     # 音效清单（金币、啵、叮、咻…，卡片上写 "sfx"）
aaaai-editor music-ab storyboard.json --at 10        # 三种配乐音量的 A/B 样片
aaaai-editor denoise-ab storyboard.json --at 10      # 降噪 A/B（默认已开标准档；"denoise": "strong"／false）
aaaai-editor tidy storyboard.json [--apply all|1,3]  # 找口头禅（嗯／呃）与讲到一半重讲；确认后才删
aaaai-editor hook storyboard.json --suggest           # 列出最适合当开头的几句
aaaai-editor hook storyboard.json --text "…"         # 把片中一句剪到开头当预告（--mode move 为搬移）
aaaai-editor framing storyboard.json --at 3          # 推近倍率对比图（选定写 framing）
aaaai-editor cover storyboard.json --at 5 --text "别怕 AI"   # 封面：竖版 1080×1920＋1080×1350；横版 1920×1080
aaaai-editor phone storyboard.json                   # 手机预览版（≤30MB）
aaaai-editor listen <素材> <起> <迄>                  # 滑动窗口听写（不带提示词）
aaaai-editor probe-cut <素材> end|start …            # 逐点试听剪点
aaaai-editor keys                                    # API 密钥（全部可选）
aaaai-editor broll status|plan|estimate|gen|sheet|place   # B-roll 流水线
aaaai-editor mcp                                     # 以 MCP 服务器运行
```

完整剪片流程（开工前提问、修字幕、设计卡片、验收、交接发布）见套件里的 `skills/aaaai-editor/SKILL.md`（唤醒词 `/aaaai-editor`）。

## storyboard.json

```json
{
  "version": 1,
  "source": "clip.mp4",
  "output": {"width": 1080, "height": 1920, "fps": 30, "path": "out/final.mp4"},
  "cuts": [[0.0, 4.9], [6.5, 11.9]],
  "captions": {"style": "clean", "max_width": 15},
  "music": {"file": "bgm.wav", "db": -18, "duck": true},
  "loudness": -14,
  "style": "ink",
  "overlays": [
    {"type": "title", "t": [1, 4], "kicker": "STEP 01", "text": "先定构思，再选效果"},
    {"type": "stat", "t": [5, 8], "value": 24800, "suffix": "+", "label": "月活钱包"}
  ],
  "zooms": [{"t": [5, 8], "to": 1.12}]
}
```

路径相对 storyboard 所在目录。字幕样式：`clean` / `punch` / `box`。

## 流程

1. 视频通道：trim + concat → 缩放裁切 → 推近 → 卡片 → 烧字幕，**全程只编码一次**（crf15/slow）。
   卡片底板由纯 Python 画（圆角／渐变／描边／柔和投影），文字由 ffmpeg drawtext 排，
   不启动浏览器、不逐帧截图；底板按内容哈希缓存，改文案不重画。
2. 音频通道：分段拼接（8ms 淡入淡出）→ 人声与配乐各自正规化到 -16 LUFS（配乐再压 db、人声闪避）→
   增益＋192k 过采样限幅、割线法迭代到 -14 LUFS ±0.1，AAC 后真峰值 ≤ -1 dBTP（见 `aaaai_editor/loud.py`）。
3. 封装：视频/音频 stream copy。

卡片、推近与人像去背见 `docs/CARDS.md`，长片分段与对时体检见 `docs/LONG.md`，
风格／图标／卡片新选项见 `docs/STYLE.md`，配方见 `docs/RECIPES.md`。

## 开发与测试

改完程序发版前跑这两个（测试素材与输出都在 `~/.cache/aaaai-editor/`，不碰你的项目和「成品」文件夹）：

```bash
bash scripts/regress.sh    # 回归：同一素材渲染两次、与基准逐字节比对（外观有意改变时加 --update）
bash scripts/smoke.sh      # 冒烟：每个命令真的跑一次（B-roll 只测不花钱的部分）
```
