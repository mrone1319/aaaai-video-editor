# 环境与项目文件夹（§13）

## 自检

```bash
export PATH="/opt/homebrew/opt/ffmpeg-full/bin:/usr/local/opt/ffmpeg-full/bin:$PATH"   # ffmpeg-full 是 keg-only
PY=~/.aaaai-editor/bin/aaaai-editor-python
"$PY" -c "import numpy, scipy, PIL, fontTools; from playwright.sync_api import sync_playwright"   # 安装器已装
"$PY" "$SK/render_frames.py" --scene "$SK/../assets/scene_template.html" --dur 4 --out /tmp/mg_check --at 1,3   # 印出 renderer: GPU · ANGLE … Metal 即正常
```
任何一项失败：先重跑 aaaai-editor 套件的安装器，不要自行改系统 Python。脚本找 ffmpeg 的顺序：`$AAAAI_EDITOR_FFMPEG` → ffmpeg-full → PATH。

- **GPU**：macOS 用 Metal、Windows 用 D3D11、其他平台软件光栅；`--cpu` 强制软件光栅。
- **字体**：品牌字体放项目 `fonts/`（woff2 → `@font-face`）；没有就用系统字体（Helvetica Neue／苹方／IBM Plex Mono）或 `npm i @fontsource/<family>`。常备：几何 Display、Body、Mono（标签）、科技数字体（滚轮）。

## 可选依赖（需要时才装）

```bash
"$PY" -m pip install --user --break-system-packages opencv-python-headless   # logo_tools.py outline（3D Logo 描轮廓）
"$PY" -m pip install --user --break-system-packages PyMuPDF                  # 程序化读品牌书 PDF 的色值、图、文字层（import pymupdf）
```

## 项目文件夹

```
project/
├── scene.html            # 单场景片；多场景片：index.html＋common.js＋scenes/*.js（照 examples/showreel/）
├── mg-kit.js             # 必备；按需：mg-film.js、mg-gen.js、mg-three.js＋vendor/、swiss.css
├── fonts/  assets/       # 字体；Logo 原图、切件、字形、logo_outline.json、辉光 PNG、录屏帧
├── out/                  # score.wav、grid.json、成片 mp4、海报 jpg
└── tmp/                  # 抽查帧、预览、能量图、参考片分析
```
