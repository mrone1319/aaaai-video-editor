# 参考片拆解细则（§3.1 分析管道、§3.3 可迁移法则）

> 本文件内容从 SKILL.md 移出（渐进式披露），节号沿用 SKILL.md 原编号，方便交叉引用。
> `$SK` = 本 skill 的 `scripts/` 目录；`$PY` = `~/.aaaai-editor/bin/aaaai-editor-python`（见 SKILL.md 开头的环境设置）。

> 更省事的做法：`$PY "$SK/analyze_reference.py" ref.mp4 --out tmp/ref`（元数据 + contact sheet + 高清抽帧 + 响度/瞬态表），
> 以及 `$PY "$SK/detect_cuts.py" ref.mp4 [预期帧数]`（带管道有效性校验的切点检测）。下面是手动管道与原理。

### 3.1 三条分析管道（全部跑）

```bash
# 1) 元数据 + 抽帧 contact sheet（人眼过一遍段落）
ffprobe -v error -show_format -show_streams -print_format json ref.mp4
ffmpeg -i ref.mp4 -vf "fps=4,scale=480:-1" f%03d.png && ffmpeg -i f%03d.png -vf tile=6x4 sheet.png

# 2) 场景切点检测（阈值 0.1）—— 返回 0 个切点说明全片都是重叠转场，这本身是重要结论
ffmpeg -i ref.mp4 -vf "select='gt(scene,0.1)',metadata=print:file=sc.txt" -an -f null -

# 3) 音频包络 + onset（RMS 全程 -inf = 静音自播片，节奏全靠视觉）
ffmpeg -i ref.mp4 -af "astats=metadata=1:reset=6,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=rms.txt" -f null -
```

再用 Python 对低清全帧序列算三条曲线——这就是这支片子的"节奏谱"：

- **帧差能量曲线**（相邻帧差均值）：峰 = 事件/剪辑点，谷 = 呼吸。数峰的个数与高度。
- **平均亮度曲线**：找"收口前留黑"的位置和深度；应呈多峰山形。
- **边缘/高饱和像素颜色随时间**：检测背景色相是否全程漂移（高级感的隐形来源）。


### 3.3 高频可迁移法则（实测反复成立）

1. **零硬切风格**（模式 B）：段落感全靠"亮度涨—平—落"完成，落到底才允许换主体。
2. **全片只给一次黑场额度**（~0.15s），放在"是什么→怎么用"的切换点（约全片 25–30% 处）。多了变 PPT。
3. **一个贯穿性动态元素兼任四职**：转场笔 / 环境粒子 / 打字机 / 擦除元素。选取标准：轮廓可辨认、任意旋转不穿帮、有长边可做擦除。这是统一感的来源，比堆转场有效得多。
4. **前景/背景双层景深**：每帧都要有失焦元素压最前，且近景层要有元素飞出画框——2D 合成像实拍的最便宜手段。
5. **数字必须"滚"不能"跳"**：纯数字镜头给 1.1–2s 专属时间；各数位滚不同整圈数，落位有先后。
6. **逐字动画的节奏 = 音效 onset 的节奏**：先做字，再按字的进入帧铺 tick。
7. **尾板静止 ≥2s + 0.3s 淡黑**，占全片 10–13%。少于 1.5s 等于没做。
8. **匹配保持（match hold）**：跨段落切换时钉住一个元素（通常是 mini lockup），品牌存在感不断线，全片才是一体而不是幻灯片。

---
