# 渲染、编码与交付细则（§10.2–§10.5）

> 本文件内容从 SKILL.md 移出（渐进式披露），节号沿用 SKILL.md 原编号，方便交叉引用。
> `$SK` = 本 skill 的 `scripts/` 目录；`$PY` = `~/.aaaai-editor/bin/aaaai-editor-python`（见 SKILL.md 开头的环境设置）。

### 10.2 渲染与编码

```bash
# 全量渲染：后台 detached + 轮询帧数（工具超时不能杀进程；预算 ~1s/帧/worker）
nohup ~/.aaaai-editor/bin/aaaai-editor-python "$SK/render_frames.py" --scene scene.html --w 1920 --h 1080 \
        --fps 60 --dur 24 --out frames/L --workers 2 > render.log 2>&1 &
# 然后轮询：tail -n 3 render.log ; ls frames/L | wc -l
# （Claude Code 里也可以直接用 Bash 工具的后台模式跑同一条命令，再轮询日志）

# 编码：H.264 high, CRF 17, yuv420p, 2s GOP, +faststart, AAC 192-224k
bash "$SK/encode.sh" frames/L out/film_16x9.mp4 --audio out/score.wav --fps 60
```

- 多 worker 各领**连续不相交帧段**；CDP `Page.captureScreenshot {optimizeForSpeed:true}` 截帧（远快于高层 API）；Chromium 加 `--force-color-profile=srgb --disable-lcd-text --font-render-hinting=none`。
- **局部补渲**：只改了某段就 `--at` 传该区间逐帧时间，覆盖同名帧文件重编码——改 3 秒段 ≈1 分钟，不重渲全片。
- 多画幅：同一场景换 `--w/--h`，`LAY` 分支自动成立；改过共享代码后**所有画幅全部重导**，不留旧代码渲的版本。
- 运动模糊：`render_frames.py --mblur scene`（只在场景用 `MG.blur(a,b)` 宣告的区间）或 `--mblur auto`（自动找快速移动的帧）。做法是在快门时间内渲多个子帧再平均，采样数自适应（慢的 8、快速甩镜加密到 32–64），硬切不会被糊。比旧的「2× fps＋tmix=2」真实得多；旧做法只剩兼容用途。
- **编码后必验**：`nb_frames == dur×fps`、音视频时长逐位相等（被超时杀掉的 ffmpeg 留下"能播放的截断文件"）、`ffmpeg -v error -i out.mp4 -f null -` 完整解码、moov 在文件头。兼容降级版备用：`-profile:v baseline -level 3.1 -vf "scale=720:1280,fps=30"`。

### 10.3 交片前六查（缺一不发）

1. 转场纪律符合模式（B：场景检测 0 切点；A/C/D：冲击次数 ≤ 设计值）。
2. 帧数 = 时长×fps，音视频同长。
3. 黑场检查：应黑帧均亮 5–12。
4. 静音可读：关声音看一遍，节奏纯视觉成立。
5. 数据一致：大字数字/日期/URL 与界面素材、与用户确认的逐字一致。
6. 多版本同源：所有画幅都是最新代码渲的。

### 10.4 平台尺寸与安全区（2026）

| 目标 | 尺寸 | 备注 |
|---|---|---|
| Web / YouTube / 大屏 | 1920×1080 | |
| IG feed / 轮播 | 1080×1350 (4:5) | 网格缩图裁 3:4 → 关键内容留在居中 ~1012×1350 |
| Reels / TikTok / Shorts | 1080×1920 (9:16) | **双重安全区**：网格裁 3:4（y 240–1680）∩ Reels UI（上 ~200px 下 ~400px 遮挡）= **1080×1120, y 400–1520**。核心内容（logo/大字/关键数字）留在区内；特效可出血。另留 ~6% 顶 / ~15% 底给平台 UI |
| X / 方版 | 1080×1080 | |

**每支片必须有至少一个封面级帧**：≥1.5–2s 稳定 hold、核心元素在安全区内、缩图可读、不在特效中段——同尺寸 JPG 随片交付（平台支持自传封面，胜过拖进度条选）。

### 10.5 交付包

- 每尺寸一个 MP4（帧数验证过）+ 2–3 张关键帧海报图（封面 + 可选一张动作中帧）。
- 需要时：静音版；alpha 版——`render_frames.py --alpha`（§6.7）截透明 PNG 序列，多数下游场景（如叠加进真实素材的剪辑流程）直接要这份 PNG 序列，不用再打包；只有明确要一个独立文件时才用 `encode.sh --alpha` 封装成 ProRes 4444（`.mov`，`yuva444p10le`）——**不要用 VP9/WebM 封 alpha**，ffmpeg 8.1.2 实测这条路径 alpha 通道解码回来会全部变不透明，且编码时不报任何错误，容易被误判为成功；ProRes 4444 逐帧验证过 alpha 数值完全还原，代价是文件大很多，只适合内部/NLE 交接，不适合网页直接播放。
- 一两句话说明改了什么 + **明说哪些参数是一行改**（文案/日期/URL/数字/尺寸/时长）。
- 任何自主判断（默认风格、画内修图、加拍）都要披露并给出替代选项。
- 大文件失败备用通道：小体积兼容版 → zip → 写入用户本地目录。
- 命名：`{project}_{duration}s_{aspect}.mp4`。

---
