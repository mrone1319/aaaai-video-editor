# 环境自检、可选依赖与项目目录（§13 全文）

> 本文件内容从 SKILL.md 移出（渐进式披露），节号沿用 SKILL.md 原编号，方便交叉引用。
> `$SK` = 本 skill 的 `scripts/` 目录；`$PY` = `~/.aaaai-editor/bin/aaaai-editor-python`（见 SKILL.md 开头的环境设置）。

## 13. 环境自检与项目目录

```bash
# ffmpeg-full 是 keg-only，不在 PATH 上——先补 PATH（每个独立的命令块都要重新设）
export PATH="/opt/homebrew/opt/ffmpeg-full/bin:/usr/local/opt/ffmpeg-full/bin:$PATH"
which ffmpeg ffprobe            # 也可以用环境变量 AAAAI_EDITOR_FFMPEG 指定 ffmpeg 绝对路径（脚本优先用它）
~/.aaaai-editor/bin/aaaai-editor-python -c "import numpy, scipy, PIL, fontTools, brotli"   # 安装器已装：numpy/scipy/pillow/playwright/fonttools/brotli/opencc
~/.aaaai-editor/bin/aaaai-editor-python -c "from playwright.sync_api import sync_playwright"   # Chromium 由 aaaai-editor 安装器装好
npm i @fontsource/<family>        # 字体一律走 npm（woff2 → 本地 @font-face），不指望系统字体
# woff2→ttf（Pillow 画字修图用）直接用已装的 fontTools：
~/.aaaai-editor/bin/aaaai-editor-python -c "from fontTools.ttLib import TTFont as F; f=F('in.woff2'); f.flavor=None; f.save('out.ttf')"
```

任何一项失败：先跑一次 aaaai-editor 套件的安装器修复环境，不要自行改系统 Python。

常备字体五件套：几何 Display(600) / Body(500) / Mono(400 全大写 metadata 用) / 科技数字体（如 Orbitron 600，滚轮专用）/ 按品牌书补装。
性能预算（2026-10 实测，M2 8 核）：渲染器默认用 GPU（ANGLE/Metal）＋自动 4 个 worker，简单场景 1080p60 约 20–40 帧/秒，35s×60fps 约 1–2 分钟；`--preview`（960 宽、30fps）8 秒片约 5 秒。`--cpu` 退回软件光栅（约慢 5 倍）。改动仍然攒一轮再全量渲。

### 13.1 增强依赖（可选，默认未安装；需要时再装，装进套件自带的解释器）

```bash
# 渲染性能：GPU（ANGLE/Metal）已是 render_frames.py 默认，不用再手动加参数
# 3D Logo 描轮廓（logo_tools.py outline）需要 OpenCV：
~/.aaaai-editor/bin/aaaai-editor-python -m pip install --user --break-system-packages opencv-python-headless
brew install vips && ~/.aaaai-editor/bin/aaaai-editor-python -m pip install --user --break-system-packages pyvips   # 辉光/挤出层大图预渲染，比 Pillow 快一个数量级

# 品牌资产自动化（§4.2/§4.3 现在靠人眼读 PDF/手动采样，这两个库可半自动化）
~/.aaaai-editor/bin/aaaai-editor-python -m pip install --user --break-system-packages PyMuPDF extcolors
# 用 `import pymupdf`（不用已弃用的 `import fitz`）：programmatically 抓 PDF 里的嵌入色值/图片/文字层
# extcolors：无 Brand Book 时自动跑调色板提取，替代手动采样

# 音频精度（§3.1/§9.3 现在只用 ffmpeg astats 粗测、手写混响）
~/.aaaai-editor/bin/aaaai-editor-python -m pip install --user --break-system-packages librosa pedalboard
# librosa：onset detection + BPM 估算，比 ffmpeg RMS 精度高得多，直接提升"剪辑公式"提炼准确度
# pedalboard：专业级 reverb/EQ/压缩，替代手写指数衰减噪声卷积混响
```

GPU 渲染由 render_frames.py 自动处理（macOS：Metal；Windows：D3D11；其他平台用软件光栅）。同一支片从头到尾用同一种（GPU 与 CPU 的抗锯齿差不到 1 像素，但混用会让局部补渲的帧对不上）。

```
project/
├── scene.html          # 单文件场景（常量区 → 时间轴 T → 构建 → 渲染函数）
├── mg-kit.js           # 从 assets/ 复制：动作库（缓动、弹簧、遮罩文字、描线、变形、视差镜头、Lottie）
├── mg-three.js、vendor/ # 需要真 3D／Lottie 时从 assets/ 复制
├── score.wav、grid.json # 真实配乐（music_grid.py fit）或 score.py 合成的临时配乐
├── fonts/              # display/body/mono/digit .woff2 (+ttf)
├── assets/             # logo 原图/切件/字形/挤出 slabs/辉光 PNG/录屏帧序列/cells.json
├── frames/L | frames/P # 渲染帧（横/竖）
├── out/                # score.wav、成片 mp4、海报 jpg、render.log
└── tmp/                # contact sheets、抽查帧、分析产物
```
