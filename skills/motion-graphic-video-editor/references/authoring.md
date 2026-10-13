# 场景编写（§6）

起步：单场景片（≤ ~35s）复制 `assets/scene_template.html`；多场景片（模式 H、>35s 或 >6 场）复制 `examples/showreel/` 的结构。工具件从 `assets/` 复制进项目（`mg-kit.js` 必备；`mg-film.js`、`mg-gen.js`、`mg-three.js`＋`vendor/`、`styles/swiss.css` 按需）。

## 1. 确定性契约（不可违反）

```js
window.__render = function (frame) { const t = frame / FPS; /* 只由 t 设置所有样式 */ };
MG.ready();   // 字体、图片、Lottie、自定义 Promise 都好了，才渲第 0 帧并设 __ready
```
- 同一 `frame` 必须产出相同画面：禁 `Date.now()`、渲染期 `Math.random()`、CSS animation/transition、`<video>`（录屏用 canvas 逐帧画）。随机一律构建期 `MG.rand(seed)` 生成。
- **小数帧**：运动模糊在帧与帧之间取样，`frame` 可能是小数——一律 `t = frame / FPS`，不对帧号取整；只有颗粒这类「一帧之内不该动」的才用 `Math.floor(frame)`。
- 尺寸经网址参数传入（`?w=1920&h=1080&fps=60&dur=24`），一份场景出所有画幅；字号基准 `S = sqrt(W*H/(1920*1080))`。
- **所有用户叫得出名字的东西提为顶部常量**（文案、数字、日期、URL、字体、色板、时长）；最常改的开放成网址参数。经验：最后全会被要求改。
- 渲染器挂了 `pageerror`：构建期 JS 异常（最常见：const 声明前就引用）会让场景永远不 ready，渲染器会报错退出，不会产出一模一样的帧。

## 2. 动作库 mg-kit.js（动作一律用它，不要手写缓动）

| 要做的事 | 用法 |
|---|---|
| 区间进度＋缓动 | `MG.at(t, a, b, MG.ease.out)`；`MG.prog(t,a,b)` 线性 0→1；`MG.imp(t, t0, w)` 一次性脉冲（闪光、撞击的唯一安全写法） |
| 按角色选缓动 | `smooth`（AE Easy Ease：移动到位）`out`（进场落定）`in`（离场）`snap`（果断到位）`read`（要读的慢揭示 ~2s）`whip`（甩镜）`expo` `anticipate` `overshoot` `anticipateOvershoot` `steps(n)`；任意曲线 `MG.bezier(x1,y1,x2,y2)` |
| 有重量的弹出、落定 | `MG.spring(t - t0, {stiffness: 300, damping: 18})`（过冲回弹；`170/26` 柔和落定；`120/8` 俏皮慎用）；`MG.springTo(t, t0, from, to, opt)` |
| 关键帧 | `MG.tween(t, [[t0, v0], [t1, v1, MG.ease.out], ...])`（数字／数组／`#颜色`）；颜色混合 `MG.mix(a, b, p)` |
| 文字出场 | `parts = MG.split(el, 'chars'｜'words'｜'lines')`（字体载入后调用；中文按字切）→ `MG.reveal(parts, t, t0, {style, each, dur, out})`：`mask`（从遮罩边缘滑出，最有设计感）`sweep`（四通道渐变扫光：透明度＋颜色 `tint→color`＋上移＋模糊，「高级感」来源）`rise` `blur` `pop` `scale` `type` |
| 数字滚动 | `MG.counter(el, '20,000,000', {t0, t1, stagger, turns})` → 每帧 `ctl.at(t)`：每位转不同圈数、高位先锁、模糊与遮罩羽化跟转速、锁定回弹 |
| 解码乱码 | `MG.decode(el, 'REASON 7', {t0, each, pool, flash})` → `ctl.at(t)`：左→右锁定；`pool` 用品牌字形最好；字位宽度固定不抖 |
| 错峰 | `MG.stagger(i, n, {each｜total, from: 'start'｜'center'｜'edges'｜'end'｜'random'})` |
| 描线、变形 | `MG.draw(path, p, {from})`；`MG.morph(dA, dB, p)`（两条路径指令结构要相同） |
| 视差镜头、有机漂移 | `MG.camera([{el, z, focus}], {x, y, zoom, rot, dof})`；`MG.noise(t*0.3, seed)`（连续、可跳转；**不要用随机抖动**） |
| 编辑网格排版 | `g = MG.grid({cols:12, rows:8})` → `g.cell(i, j, 宽, 高)`、`g.col()`、`g.row()`、`g.lines()`；`MG.place(el, rect)`；`MG.rect(a, b, p)`（格子扩成全屏） |
| 图形转场 | `MG.clip(el, p, 'left｜right｜up｜down｜center｜circle｜diag｜blinds:N｜cols:N')`（p 1→2 同方向擦出）；`MG.invert(t, [翻转时间])`＋`MG.swap(el, inv, ink, paper)`（黑白同帧反转）；`MG.zoomTo(p, fx, fy, W, H, 倍率)`（推进穿越） |
| 字体节奏 | `MG.marquee(t, 速度, 宽, 方向)`（跑字，字放两遍无缝）；`MG.hit(t, t0, 起始倍率)`（重击放大落定）；`MG.wave(i, j, t, {kind})`（字体网格的波形场） |
| Lottie | `ctl = MG.lottie(el, {path, start, speed, loop})` → `ctl.at(t)`（需 `vendor/lottie.min.js`；只用有授权的 Lottie） |
| 告诉工具意图 | `MG.blur(a, b)` 这段要运动模糊；`MG.hold(a, b)` 有意的停留（封面帧、尾板、收束）；`MG.cut(t)` 有意的硬切——能量验收就不会误报 |

## 3. 多场景主时间轴 mg-film.js（长片用）

```js
FILM.config({ W, H, fps: FPS, dur: MUSIC.dur, root: stage });
const L = FILM.layer('intro');                       // 场景自己的图层
FILM.scene({ id: '01 intro', start: B(0), end: B(2), el: L,
  setup(ctx) { return document.fonts.ready.then(() => { /* 量字宽、拆字 */ }); },
  render(lt, ctx) { /* lt = 本场秒数；ctx.t 全片秒数；ctx.p 本场进度 */ } });
FILM.start();                                        // 所有场景文件载入之后
```
- 每场一个文件；边界落在 `MUSIC.bars`；`in: 'over'`＋`pre/post` 让相邻两场重叠做转场，默认硬切（自动 `MG.cut`）。
- 只渲染在播的场景，其余 `display:none`；setup 阶段图层参与排版但不可见（量得到字宽——隐藏的图层量出来是 0）。
- `window.__scenes` 给开发播放器（按场景跳）与验收工具用；`FILM.check()` 报场景之间的空隙与重叠。

## 4. 生成式模块 mg-gen.js（Canvas，全部可跳转）

| 模块 | 用法要点 |
|---|---|
| `GEN.particles(cv, opt)` | 数千点在旋度噪声力场里流动（`scale` 场的尺度、`speed`、`drift` 场的演化）；`attractors: [{x,y,strength,radius,t0,t1}]`（负值＝排斥）；`target`（`GEN.textPoints('FIELD', n, W, H)`／`GEN.shapePoints('circle'｜'disc'｜'grid'｜'line'｜'sphere')`）＋`form: t => 0..1` 聚成形状再散开；`accent`＋`accentOn(t)` 少数点上点缀色。固定步长＋检查点缓存，任意时间点（含倒退、小数帧）都对 |
| `GEN.typeGrid(cv, opt)` | 一个字铺满网格，每格由 `MG.wave` 驱动：`mode: 'scale'｜'invert'｜'weight'｜'cycle'｜'mixed'`；`glyphs` 可以是函数 `(i, j, t) => 字`；`appear(t)` 对角线逐格出现 |
| `GEN.wire(cv, opt)` | `items: [{type: 'cube'｜'grid'｜'axes'｜'cloud'｜'circle', size, pos, accent}]` → `render(t, {rx, ry, rz, dist, fov, cx, cy, draw})`，`draw` 0→1 逐段画出 |
| `GEN.figure(cv, opt)` | 手绘线条小人：`render(t, {kind: 'walk'｜'run'｜'jump'｜'wave', x, y, h, draw, travel, ground})`；线条 8fps「沸腾」读作手绘 |
| `GEN.motion(cv, opt)` | 动作分析骨架：关节、骨骼、轨迹（`trail` 秒）、角度读数；`render(t, {kind, freq, h, trail, draw})` |

## 5. 真 3D mg-three.js（ES 模块）

```js
import { stage3d, studioEnv, studioLights, softShadows, sculpture, extrudeLogo, material, rig, orbit, particles, loadTexture, THREE } from './mg-three.js';
const st = stage3d(canvas, W, H, { background: '#F2EFE8', fov: 30 });
studioEnv(st, { base: '#2E2E32', rimA: '#ffffff', rimB: brandAccent });   // 金属必须有环境反射
const L = studioLights(st.scene, { key: 2.4 }); softShadows(st, L.key, { y: -2.9 });
```
- **环境**：金属没有环境反射就是一片黑。白棚拍铬也要用**暗底＋亮柔光板**（`base: '#2E2E32'`）——环境太亮太均匀，铬会变成灰塑料。
- **Logo**：`logo_tools.py outline` 描轮廓 → `extrudeLogo(outline, {texture, width, depth, bevel, sideColor, sideMetal})`，正面贴原 PNG（渐变完全保留）。
- **雕塑**：`sculpture({strands, seed, size, radius, breathe, materials})` → 每帧 `sc.update(t)`（呼吸形变，可跳转）；`material('chrome'｜'pearl'｜'glass'｜'lime'｜'iridescent'｜'ceramic')`。
- **镜头**：`rig(cam, t, [[时间, [x,y,z], [看向x,y,z]], ...], 缓动)`（微距 → 全景）；`orbit(cam, t, {radius, height, speed, target})`。镜头**目标点偏离物体**＝物体在画面一侧（非对称构图，另一侧留给文字）。
- 每帧最后 `st.render()`。只在 GPU 渲染下快；透射材质（glass）一个画面最多一两个；阴影贴图 2048 够用。

## 6. 版面

两套系统，按风格选，不要混：
- **居中堆叠**（模式 A–G 的默认）：`.stack{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;width:max-content}`——`max-content` 必加；任何画幅都自动居中，不手算 `top`。
- **编辑网格**（Swiss／模式 H／设计感品牌片）：`MG.grid` 定网格，元素落在格线上，**非对称**、大量留白（`style-swiss.md`）。
- 竖版：内容占宽 ≈ 0.90（横版 ≈ 0.62，1:1 ≈ 0.86，4:5 ≈ 0.84）；宏观布局分支写进一个 `LAY` 对象。
- 有字距的文字加等值 `text-indent`（否则整行左偏半个字距）。小号技术标签加 `data-deco`、刻意出血的大字加 `data-bleed`（验收豁免）。
- 每种字体量过数字宽度再推格宽，绝不写死（数字宽 0.54–0.83em 不等）。

## 7. 叠层顺序

```
背景（光晕／网格）→ 底层内容（大字）→ 产品／3D 层 → 顶层内容（文案、尾板）→ 暗角 →
（可选）扫描线 multiply → 颗粒 overlay ~5%（每帧移动）→ 闪光 screen（只由 imp 驱动）→ 收黑层
```
- 文案、尾板必须在产品层**之上**（重叠转场时，淡出中的产品会盖住进场文字）。
- 颗粒必须每帧动（静态读作镜头脏了）；扫描线用 multiply（否则雾化黑场）。
- **绝不写 `1 - progress` 型闪光**：触发前恒为满亮，整片从第 0 帧洗灰。应黑的帧平均亮度应在 8–12，>25 就是有层在漏光。

## 8. 模式 B（柔和产品片）专属纪律

- 转场只用 blur＋scale＋opacity，任何两段重叠 ≥0.15s；加位移甩尾、擦除、翻页，气质立刻从「产品级」掉到「模板级」。
- 背景光晕用纯 `radial-gradient` 画环形亮带（尺寸 ≈`W*1.42`，亮带落 48–70% 半径）；竖版纵向拉椭圆 `scaleY≈(H/W)*0.92`，否则上下死黑。
- **色相全程漂移**（或首尾一致的弧线）：观众意识不到，但它把所有段落缝成一体。
- 永不静止：「静态」尾板也以 −1～−3%/s 缓缩，光晕微呼吸 `1+0.035*sin(t*1.05)`。

## 9. 效能

- 渲染器默认 GPU（Metal），成本在栅格化不在 JS：慢的时候先减 blur 层、再减绘制面积，不要优化 JS。大面积辉光预渲染成 PNG（`make_glow.py`），场景里只动 transform／opacity。
- 视窗外的元素组 `display:none`，不是 `opacity:0`（隐形元素也在付栅格化成本）。字体网格、跑字这类几百个字用 Canvas（`GEN.typeGrid`），不要几百个 span。
- 3D：重复物件用 `InstancedMesh`；重建几何先 `dispose()`（套件已做）。粒子 7 000 点要 1–3 秒暖机（每个 worker 从 0 秒算到自己的段落），超过 2 万点改用 three.js `Points`。

## 10. 透明图层（叠进实拍用）

渲染加 `--alpha` 时网址带 `alpha=1`，场景必须配合：**跳过所有背景、光晕、暗角、扫描线、颗粒、收黑层**，只留前景（Logo、文字、图卡）；收场用透明度归零，不用收黑。产出 PNG 序列，用 `encode.sh --alpha` 封成 ProRes 4444（`.mov`）；**不要用 VP9/WebM 封透明**（实测解码回来全不透明，且不报错）。透明图层走软件渲染（GPU 的透明边缘只有 19 级渐变，叠在实拍上会锯齿）。
