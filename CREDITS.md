# 出处与致谢

## 原创声明

aaaai-editor 由 MR ONE 与 Claude（Anthropic）于 2026 年 9 月**从零编写**。
它**不包含** Remote Editor Kit（© Fyn Chang）的任何代码、模板、设计系统或文档：
重写只依照「能力清单」自行设计架构与数据格式，未参阅该套件的源码。
迁入的自建工具（字幕对齐、对时体检、剪点探测、滑动窗口听写、配乐生成器与 7 首常备配乐）是 MR ONE 自己的成果，
迁入前经逐行机器比对，与该套件只重合通用样板行。
`motion-graphic-video-editor` 与 `social-content-pipeline` 两个 skill 由 MR ONE 自行开发，随本套件提供。

## 安装时从官方来源取得（不内附于本套件）

| 元件 | 用途 | 授权 |
|---|---|---|
| FFmpeg（Homebrew `ffmpeg-full`，含 libx264、libass、FreeType） | 剪辑、合成、编码、字幕、响度 | LGPL 2.1+ / GPL |
| whisper.cpp（Homebrew `whisper-cpp`） | 语音转文字 | MIT |
| Whisper 模型权重 ggml-medium（Hugging Face ggerganov/whisper.cpp） | 语音识别 | MIT（OpenAI） |
| HeyGen HyperFrames（Claude Code 插件 `core-skills@hyperframes`） | 讲解片、网站转影片、产品发布、音乐影片、幻灯片等格式 | Apache-2.0 |
| Node.js（Homebrew） | HyperFrames 执行环境 | MIT |
| Playwright + Chromium | 动画场景渲染（motion-graphic-video-editor） | Apache-2.0 / BSD |
| Orbitron、IBM Plex Mono（Google Fonts） | OTG 风格标题、数字 | SIL Open Font License 1.1 |
| OpenCC、fontTools、NumPy、SciPy（pip，可选） | 繁→简、字体固化、配乐合成 | Apache-2.0 / MIT / BSD |
| Apple Vision / CoreVideo | 人像分割（自写的 Swift 助手，源码在 `aaaai_editor/matte.py`） | macOS 系统框架 |

另使用 macOS 自带字体 Hiragino Sans GB、PingFang SC、Songti SC、Avenir Next（依 macOS 授权，只在本机渲染，不散布字体文件）。
`OrbitronBlack` 是安装后在本机由 Orbitron 固化出的 900 字重静态实例，不随套件散布。

## 设计来源

- `ink`／`neon`／`paper`／`serif`、41 个线性图标、卡片版式、配方：本套件原创。
- `gold`／`trust`／`mag` 的配色参考 ui-ux-pro-max（uupm-design）skill 的产品色板数据。
- `otg` 依据 OTG 社群的品牌规范；OTG 名称、标志与品牌元素归 OTG 社群所有。
- `mrone` 参考 MR ONE 自己既有成片与分享卡的视觉语言。
- 剪辑规则与节奏配方来自 MR ONE 频道 ep01–ep11 的实战经验，以及 `motion-graphic-video-editor` 的剪辑公式库。

## 配乐

`assets/bgm/` 的 7 首曲目由 `tools/gen-bgm.py` 原创合成，零第三方版权。
