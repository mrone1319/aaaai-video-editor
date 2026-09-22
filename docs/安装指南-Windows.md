# aaaai-editor 安装指南 · Windows 版

aaaai-editor 影片总监套件：把口播、访谈或长片交给 AI 剪辑助手（Claude Code），自动完成剪停顿、字幕、卡片、配乐、响度、封面、B-roll 和验收。中文、英文等多种语言的影片都能剪，竖版和横版都支持。

> 这份是 **Windows** 的安装指南；用 Mac 请看 `安装指南-Mac`（同一个文件夹里有 .md 与 .pdf 两种）。
>
> Windows 版刚推出：功能和 Mac 版相同，但还需要在更多 Windows 电脑上实测。遇到问题把画面截图给 Claude，它会帮你排查。

### 电脑需求

| 项目 | 需求 |
|---|---|
| 系统 | Windows 10（22H2）或 Windows 11，**64 位** |
| 处理器 | 近 5 年的 Intel／AMD 64 位处理器。**ARM 版 Windows（例如部分 Surface、Snapdragon 笔电）暂不支持** |
| 显卡 | 不是必须。有 NVIDIA、Intel 或 AMD 显卡时，出片可以开硬件加速 |
| 内存 | 最少 8GB，**建议 16GB** |
| 硬盘 | 至少留 **20GB**（工具与语音模型约 3GB，其余给素材和成片；手机 4K 素材一分钟约 0.5GB） |
| 网络 | 安装时要下载约 3GB；之后剪片不用联网 |
| 其他 | **winget**（Windows 自带的「应用安装程序」）；Claude Code 需要 **Git**（安装器会帮你装） |

怎么看：「设置 → 系统 → 系统信息」，「系统类型」要写 64 位、基于 x64 的处理器。

---

## 一、安装前先知道这些

### 会安装（都是免费开源）

| 项目 | 从哪里来 | 用途 |
|---|---|---|
| Python 3.12 | winget（`Python.Python.3.12`） | 引擎本体 |
| FFmpeg 完整版 | winget（`Gyan.FFmpeg`，含字幕引擎 libass） | 剪辑、合成、编码 |
| Git | winget（`Git.Git`） | Claude Code 在 Windows 上需要 |
| Node.js LTS | winget（`OpenJS.NodeJS.LTS`） | HyperFrames、动画片；可用 `-NoHyperframes` 跳过 |
| whisper.cpp | whisper.cpp 官方 GitHub 发布版 | 语音转字幕（多语言） |
| whisper medium 模型 | Hugging Face 官方（约 1.5GB，下载完核对官方校验码） | 语音识别模型 |
| MediaPipe＋NumPy | pip（装在你的用户目录） | 人像去背（字卡穿插在人后面、卡片接管） |
| MediaPipe 人像分割模型 | Google 官方（约 250KB） | 同上 |
| OpenCC、fontTools、brotli | pip（用户目录） | 繁转简、字体量测 |
| 开源字体 Orbitron、IBM Plex Mono | Google Fonts 官方 | 风格用字，放在 `%USERPROFILE%\.aaaai-editor\fonts`，不动系统字体 |

- 程序放在 `%USERPROFILE%\.aaaai-editor\app`。
- 3 个 skill 会复制进 `%USERPROFILE%\.claude\skills`。如果那里已有同名的 skill，会先备份，不会直接覆盖；卸载时会还原。
- **每一项都会先问你**；用 winget 安装时，会同意 winget 的来源与套件授权条款，所以也会先问。
- 装好后，在 Claude Code 里输入 `/aaaai-editor` 就能启动。

**时间与空间**：首次安装约下载 3GB，视网速需要 10–30 分钟，装好约占 4GB。

### 可选：要花钱或要账户的（不绑也能正常剪片）

这几把密钥只给 **B-roll（插入的空镜画面）** 用，全部可选。

| 密钥 | 用途 | 费用 | 申请 |
|---|---|---|---|
| `PEXELS_API_KEY` | 免费素材库 | **$0**（使用时须标注 Pexels 与摄影师） | https://www.pexels.com/api/new/ |
| `FAL_KEY` | AI 生成：Flux 首帧＋Wan 2.2 动态、可灵 2.5 | Wan 2.2 约 **$0.15/条**，可灵 2.5 约 **$0.35/5 秒** | https://fal.ai/dashboard/keys |
| `HF_CREDENTIALS` | Higgsfield（只在你指定时用） | 扣你 Higgsfield 账户的额度 | https://cloud.higgsfield.ai/ |

- 每次要花钱之前都会先报价，**问过你、你同意了才执行**；每个项目默认上限 **$2**，超出会提醒你。
- **密钥安全**：存进 **Windows 凭据管理器**（只存在这台电脑、这个 Windows 帐户），只在**你自己的 PowerShell 视窗**输入，屏幕上不显示；不要把密钥贴进和 AI 的聊天里。
  密钥只经由 https 发给官方主机，错误信息里出现会自动打码，ffmpeg、whisper 等外部程序拿不到。

### 隐私

视频、音频、字幕、转录**只在你的电脑上处理**。只有 B-roll 的画面描述／搜索词（和你选做首帧的照片）会发给 Pexels 或 fal，而且每次都先问你。

### 版权

程序免费使用；**mrone**（© MR ONE）和 **otg**（© OTG 社群）是社群风格：可以使用，但品牌归原权利人，请勿用来冒充。详见 `LICENSE.md`、`CREDITS.md`。

---

## 二、安装

### 方法 A：zip 安装包（最简单）

1. 在 zip 上按右键 →「**全部解压缩**」（不要直接在压缩档里双击，安装器会找不到其他文件）。
2. 打开解压出来的文件夹，双击 **`Install-Windows.cmd`**，按提示一步步选择（输入 `y` 或直接按 Enter 表示同意）。
3. 如果跳出蓝色的「**Windows 已保护你的电脑**」：点「更多信息」→「仍要运行」。
4. 如果说「没有 winget」：打开 Microsoft Store，搜索并安装「**应用安装程序**（App Installer）」，再双击一次。
5. 装完它会做一次体检，全部 ✅ 就能开始；有 ❌ 就照提示做，或重跑一次（可以重复跑，已装好的会跳过）。

**Claude Code**：到 https://claude.ai/download 下载 Windows 版安装。如果 Claude Code 提示需要 Git，先完成上面的安装器（会装好 Git），再把 Claude Code 完全关掉重开。

### 方法 B：Claude Code 插件（能一键更新）

1. 先装好 Claude Code（见上一段）和 GitHub 登录：从 https://cli.github.com 下载安装 `gh`，然后在 PowerShell 执行：

```powershell
gh auth login
```

```powershell
gh auth setup-git
```

2. 安装插件（一定要用 https 地址）：

```powershell
claude plugin marketplace add https://github.com/mrone1319/aaaai-video-editor.git
```

```powershell
claude plugin install aaaai-editor@aaaai-editor
```

3. 在 Claude Code 里说「/aaaai-editor」，它会先把第一节的须知讲给你听，你同意后再帮你跑 Windows 安装器。
   需要你本人同意或输入的步骤（winget 授权、密钥），它会列出来，请你在 PowerShell 视窗里自己执行。

### 安装器选项

在 PowerShell 里手动执行安装器时可以加选项，例如：

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -NoModel
```

| 选项 | 作用 |
|---|---|
| `-Yes` | 不逐项询问，全部照默认做 |
| `-NoDeps` | 不用 winget 装 Python／FFmpeg／Git，也不装 pip 套件（已自行装好时） |
| `-NoModel` | 不下载语音模型 |
| `-NoSkills` | 不复制 skill 到 `%USERPROFILE%\.claude\skills`（插件安装时用） |
| `-NoHyperframes` | 不装 HyperFrames 与 Node.js |
| `-NoKeys` | 不引导绑定密钥 |

安装器会问你要不要把 `aaaai-editor` 加进 PATH：加了，新开的视窗可以直接打 `aaaai-editor`；没加，就写完整路径 `%USERPROFILE%\.aaaai-editor\bin\aaaai-editor.cmd`。

---

## 三、之后再绑密钥或改设置

在 PowerShell 里执行（没加进 PATH 就把 `aaaai-editor` 换成 `$env:USERPROFILE\.aaaai-editor\bin\aaaai-editor.cmd`）：

```powershell
aaaai-editor keys
```

```powershell
aaaai-editor keys set PEXELS_API_KEY
```

- 第一条列出每把密钥的状态、用途和费用；第二条绑定密钥（贴上时屏幕不显示，按 Enter 存进凭据管理器）。
- 移除密钥：`aaaai-editor keys remove FAL_KEY`；也可以在「控制面板 → 凭据管理器 → Windows 凭据」里看到 `aaaai-editor:` 开头的项目。

| 设置 | 作用 |
|---|---|
| `aaaai-editor config --set handle=@你的账号` | 封面上印的账号名 |
| `aaaai-editor config --set projects_dir=D:/剪辑` | 项目存放位置（默认「视频\aaaai-editor」） |
| `aaaai-editor config --set exports_dir=D:/成品` | 成片复制到哪里（默认「视频\aaaai-editor\成品」；设空字串就不复制） |

---

## 四、在其他平台使用（MCP）

| 平台 | 设置 |
|---|---|
| Claude Code | 不需要，skill 直接调用命令 |
| Claude Desktop | 在 `%APPDATA%\Claude\claude_desktop_config.json` 的 `mcpServers` 加 `"aaaai-editor": {"command": "C:\\Users\\你的用户名\\.aaaai-editor\\bin\\aaaai-editor.cmd", "args": ["mcp"]}` |
| Cursor 等 | 同样填命令 `…\.aaaai-editor\bin\aaaai-editor.cmd`、参数 `mcp` |

要花钱的工具一律两步：先返回报价，你同意后才真正生成。

---

## 五、开始用：5 分钟试剪

> 装好之后，先打开同一个文件夹里的 **《使用指南》**（`docs\使用指南.html`，双击用浏览器看；或 `使用指南.pdf`）。

1. 用手机录一段 30–60 秒的口播，传到电脑。
2. 在 Claude Code 里说「/aaaai-editor 帮我剪片」，再把影片文件拖进输入框。
3. 回答它问的风格、配乐、字幕（横拍素材还会问要不要裁成竖版）。
4. 大约几分钟后你会收到：去掉停顿、带字幕和卡片、响度统一的成片，和一张封面。

**成片在哪里**：打开资源管理器，左边点「**视频**」→ `aaaai-editor` → `成品`，文件名就是项目名。可以在 `成品` 上按右键 →「固定到快速访问」，以后一点就到。

---

## 六、更新、卸载与常见问题

**更新**：插件用户在 PowerShell 执行下面两行，再在 Claude Code 里说「/aaaai-editor」；zip 用户拿到新版 zip 后重跑一次 `Install-Windows.cmd`。你的设置、风格、频道档案、项目都不会被覆盖。

```powershell
claude plugin marketplace update aaaai-editor
```

```powershell
claude plugin update aaaai-editor@aaaai-editor
```

**卸载**：双击安装包里的 `Uninstall-Windows.cmd`。程序、skill、PATH 设定都会移到**资源回收筒**（可以救回）；安装前被备份的同名 skill 会还原。你的设置和项目默认保留（要全清：`powershell -ExecutionPolicy Bypass -File uninstall.ps1 -All`）。winget 装的 Python、FFmpeg、Git 不会动；凭据管理器里的密钥要先用 `aaaai-editor keys remove` 删。

**常见问题**

| 情况 | 办法 |
|---|---|
| 双击 `Install-Windows.cmd` 一闪就关 | 确认是在「解压出来的文件夹」里双击，不是在 zip 里；或在该文件夹空白处按 Shift＋右键 →「在终端中打开」，执行 `powershell -ExecutionPolicy Bypass -File install.ps1` 看错误 |
| 「Windows 已保护你的电脑」 | 点「更多信息」→「仍要运行」 |
| 没有 winget | Microsoft Store 安装「应用安装程序」 |
| `aaaai-editor doctor` 有 ❌ | 按提示补装，或重跑安装器 |
| 找不到 `aaaai-editor` 命令 | 新开一个视窗再试；或写完整路径 `%USERPROFILE%\.aaaai-editor\bin\aaaai-editor.cmd` |
| 找不到 ffmpeg／whisper-cli | winget 刚装完要**新开视窗**才生效；还是不行就重跑安装器 |
| 人像穿插、卡片接管报错 | 重跑安装器装 MediaPipe，或执行 `py -3.12 -m pip install --user mediapipe numpy` |
| 中文变成乱码 | 请用安装器建立的 `aaaai-editor` 命令启动（它会用 UTF-8）；把画面截图给 Claude |
| 出片很慢 | storyboard 写 `"output": {"encoder": "hw"}` 开显卡硬件加速（NVIDIA／Intel／AMD） |
| 想用 mrone／otg 风格 | 直接跟 Claude 说「用 mrone 风格」即可，不需要授权；它们排在清单最后，不会被当首选推荐 |
