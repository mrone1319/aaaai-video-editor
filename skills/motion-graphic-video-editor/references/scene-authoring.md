# 场景编写铁律全文（§6.1–§6.7）

> 本文件内容从 SKILL.md 移出（渐进式披露），节号沿用 SKILL.md 原编号，方便交叉引用。
> `$SK` = 本 skill 的 `scripts/` 目录；`$PY` = `~/.aaaai-editor/bin/aaaai-editor-python`（见 SKILL.md 开头的环境设置）。

> 起步模板：`assets/scene_template.html`（占位文案与灰白色板，必须按用户品牌替换）。英文实现细节见 `motion-recipes.md`。

### 6.1 确定性渲染契约（不可违反）

```js
window.__render = function(frame){ const t = frame / FPS; /* 纯函数设置所有样式 */ };
window.__ready  = true;   // 仅在字体与全部图片 decode 完成后置 true
```

- 同一 `frame` 必须产出**逐字节相同**的画面。禁止 `Date.now()`、渲染期 `Math.random()`、CSS animation/transition。
- 随机散布用 seeded PRNG（mulberry32，seed 用项目日期）在**构建期**一次生成。
- 资源门控：`Promise.all([document.fonts.ready, ...imgs.map(i=>i.decode())])` 之后才 `__ready=true`；渲染器必须挂 `pageerror` 钩子——静默 JS 异常（最常见：const 声明前引用）= 2000 张一模一样的帧。
- 几何经 query string 传入：`scene.html?w=1920&h=1080&fps=60`，一份工程服务所有画幅。

### 6.2 缓动与脉冲词汇表（照抄使用）

```js
const cl    = v => Math.max(0, Math.min(1, v));
const seg   = (t,a,b) => cl((t-a)/(b-a));                  // 0→1 over [a,b]
const sstep = (a,b,v) => { const x = cl((v-a)/(b-a)); return x*x*(3-2*x); };
const eOut  = p => 1 - Math.pow(1-p, 3);                   // cubic out
const eExpo = p => p>=1 ? 1 : 1 - Math.pow(2, -10*p);      // expo out
// ONE-SHOT IMPULSE — 闪光/撞击唯一安全写法：
const imp   = (t,t0,w,k=2.4) => (t<t0 || t>=t0+w) ? 0 : Math.pow(1-(t-t0)/w, k);
```

- **绝不写 `1 - progress` 型闪光**——触发前恒为满亮，整片从第 0 帧洗灰。验证：应黑帧平均像素 8–12，>25 = 有层在漏光。
- **按角色选缓动**：`eExpo` 给"到位"类（opacity/scale，干脆）；观众要*读*的旋转/揭示用 ~2s 慢 cubic（easeOutExpo 前 22% 就完成 79%，3D 揭示还没看清就结束了）。3D 旋转停在 12–16° Y，别停 ~5°（深度感消失）。

### 6.3 布局（一份场景吃所有画幅）

- 一切用**居中 flex 列**：`.grp{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;width:max-content}`——`max-content` 必加，否则 shrink-to-fit 让离中列夹偏。绝不手算 top 值。
- 字号基准 `S = sqrt(W*H/(1920*1080))`；竖版文字系数 ×1.02。
- 宏观布局分支走单一 `LAY` 对象（横版=内容在设备旁；竖版=设备在上内容在下、横排 chip 变竖排、logo 相应加宽）。内容占宽参考：16:9 ≈0.62，1:1 ≈0.86，4:5 ≈0.84，9:16 ≈0.90。
- 有 letter-spacing 的文字必须加等值 `text-indent`，否则整行左偏半个字距。
- **所有用户可能改的字符串提为顶部常量**（文案/数字/日期/URL/字体/色板/时长），最易变的暴露成 query 参数（`?days=03&nf=ob`）。经验：用户最终全部都会要求改。
- 每字体记 metrics（数字 advance ratio 0.54–0.83em 不等），滚轮格宽从中推导，绝不写死。

### 6.4 叠加层与 z 顺序

```
背景光晕 → 底层内容(大字) → 设备/产品层 → 顶层内容(文案/尾板) → 暗角 →
(可选)扫描线 multiply → 动态颗粒 overlay ~5%(每帧由 t 推 background-position) →
径向闪光 screen(只由 imp 驱动) → 收黑层
```

- 文案/尾板必须在产品层**之上**——重叠转场交叉窗里，淡出中的产品会盖住进场文字。
- 扫描线用 `multiply`（否则雾化黑场）；静态颗粒像镜头脏了，必须每帧动。
- 硬切走黑场 = 收黑层上 ~3 帧尖峰（模式 A/C/D 专用；模式 B 禁用）。

### 6.5 模式 B 专属纪律

- **转场三件套**：全片只允许 blur + scale + opacity 做转场，任何两段重叠 ≥0.15s。做完用场景检测验证 0 切点。加位移甩尾/擦除/翻页，气质立刻从"产品级"掉到"模板级"。
- **背景光晕**：纯 `radial-gradient` 画环形亮带（禁 CSS blur），尺寸基准 ≈`W*1.42`，亮带落 48–70% 半径，中心与四角留黑；竖版纵向拉椭圆 `scaleY≈(H/W)*0.92` 否则上下死黑。
- **色相全程漂移**：沿品牌光谱做关键帧插值，从第一帧漂到最后一帧一刻不停——观众意识不到，但它把所有段落缝成连续体。最容易被省略也最不该省略的"隐形高级感"。
- **永不静止**：没有任何一帧完全静止；"静态"尾板也以 -3%/s 缩放漂移；光晕微呼吸 `1+0.035*sin(t*1.05)`。

### 6.6 性能铁律

- 成本全在栅格化不在 JS（样式更新 ~350fps，截帧 0.8–2.5fps/worker）。渲染慢时：**先杀 blur 层，再减绘制面积，永远不用优化 JS**。
- 大层辉光一律预渲染 PNG（§8 prerender），场景内只动 transform/opacity。
- 视窗外的元素组 `display:none`，不是 opacity:0（隐形 div 也在付栅格化成本）。
- ~1000–1500 个动画 div @1080p 双 worker ≈2.5–5fps 截帧，可接受。

### 6.7 Alpha 图层输出（场景要配合的透明契约）

当渲染带 `--alpha` 时，`render_frames.py` 会在场景 URL 后面自动加 `alpha=1`，并让 Chromium 用透明色合成再截 PNG。**场景本身也必须配合**，不然透明只是"截图格式支持"，画面上还是有东西挡住：

```js
const params = new URLSearchParams(location.search);
const ALPHA = params.get('alpha') === '1';
```

- `ALPHA` 为真时**跳过**所有背景/氛围层：`html/body` 背景色、径向光晕、暗角、扫描线、颗粒 overlay（§6.4 叠加层顺序里"背景光晕→…→收黑层"这一路全部不画）。
- 只保留真正要被合成到别处素材上的前景元素：Logo、文字、图卡、粒子本体。
- 收黑层/硬切黑场在 alpha 模式下**禁用**（黑色收场在透明合成里会变成一块不透明黑幕，不是"变暗"）——用透明度归零代替。
- 这一层产出的是**PNG 序列**，不是最终成片；不需要额外做 §9 配乐、§10.3 交片六查那一整套，只需按 §10.1 抽帧核对透明区域确实是透明（比如用 Pillow 读 alpha 通道，边缘应为 0，前景应接近 255，不能整张图都是低透明度的灰蒙蒙）。
- 用途：把这个 skill 当作"特效层供应商"，被以实拍为主的剪辑流程（aaaai-editor）用 ffmpeg `overlay` 滤镜叠加使用，而不是自己产出完整片子。

```bash
~/.aaaai-editor/bin/aaaai-editor-python "$SK/render_frames.py" --scene scene.html --w 1920 --h 1080 --fps 60 --dur 6 \
        --out frames/alpha --alpha
# 直接把 frames/alpha/*.png 序列交给下游流程叠加使用（首选路径，不需要再打包）；
# 需要一个独立的透明视频文件时才用 encode.sh：
bash "$SK/encode.sh" frames/alpha out/layer.mov --alpha --fps 60   # ProRes 4444，验证过 alpha 能正确还原；文件大，给 NLE 用不是给网页用
```

---
