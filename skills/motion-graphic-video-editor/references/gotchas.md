# Gotchas

## 踩坑速查（中文，原 SKILL.md §12：症状 → 原因 → 修法，全部付过学费）

| 症状 | 原因 | 修法 |
|---|---|---|
| 整片发灰黑不下去 | 闪光写成 `1-progress`，第 0 帧满亮 | 窗口式 imp()；打印帧均值验证 8–12 |
| 辉光外有方形框 | PNG 边界非精确零，screen 混合放大 | padding+硬径向窗归零，blur 后重套窗，四角采样验证 |
| 3D 几何对但画面平 | preserve-3d 子树内有 blend/群组 opacity/filter（opacity 0 也触发） | 淡入淡出移到非 3D 祖先或叶元素 |
| numpy 改 alpha 无效 | `arr[y:,3]` 切的是列 | `arr[y:,:,3]`；重读保存文件验证 |
| 挤出侧壁隐形 | 斜坡低于 ~0.18 | 0.58→0.18 + 冷色调 |
| 细线挤出成百叶窗 | slab 步长超过线宽 | 更多更薄 slab + 细线 strip 掉平贴 front |
| 渲染 ~1fps 优化 JS 没用 | 成本在栅格化（blur 层） | 辉光转 PNG → 深度分片 → 容器级 smear → 加 worker |
| 粒子丢一半 | spawn 区间 ≠ wrap 距离 | 同一常量用于两处 |
| 计数器落错数字 | 落位算法混加 | `total = wholeTurns*10 + digit`，别的都不行 |
| 滚轮裁字/露邻位/落定发暗 | 1 格窗硬裁；固定掩罩 | 窗 1.3×(或 1.04×)格高 + 羽化挂转速、锁定归零 |
| 滚动中数字清晰像乱码 | 模糊用进度不用速度驱动 | 位置差分真速度 → 驱动 blur |
| 科技字体互相压字 | 按单字符宽累加 | 前缀宽度定位 + 补字距 |
| 后补符号让整组偏移 | 符号挂在居中盒外 | 主体同步反移半个符号宽 |
| 换画幅偏离中心 | 手算 top / 残留 translateX | 居中 flex 列 + width:max-content |
| 字距文字偏左半格 | 尾空格 | text-indent = letter-spacing |
| 3D 揭示一闪而过 | easeOutExpo 前 22% 完成 79% | 旋转用 ~2s 慢 cubic；落定 12–16° |
| 宽图旋转后切边 | 透视放大近端 ~7% | 竖版 ≤78%W；按落定角度验证 |
| 全部帧一模一样 | 构建期 JS 异常，__ready 未置位 | pageerror 钩子；查 const 声明顺序 |
| 成片比预期短还能播 | 超时杀掉 ffmpeg/渲染 | `nohup … > render.log 2>&1 &` 后台（或 Claude Code 后台 Bash）；核对 nb_frames |
| 颗粒像镜头脏了 | 静态噪声 | 每帧由 t 推 background-position |
| 光谱环有接缝 | conic 首尾相撞 | 铺 ~86% 圆周 + 回程弧压暗 |
| 画面还在音乐停了 | 改时长没重生成配乐 | 两文件同改；验证每小节 RMS |
| 手机缩放原点跑偏 | 中间层塌成 0×0 | 每层显式宽高 + transform-origin |
| 文字被淡出的产品盖住 | z 顺序错 | 文案/尾板独立顶层容器 |
| 竖版上下死黑 | 正圆光晕按宽度定尺寸 | 纵拉椭圆 scaleY≈(H/W)*0.92 |
| 竖版推进卡片顶出画外 | 沿用横版写死 zoom | 按画幅反推 ZMAX，横版上限锁死 |
| 场景检测误报硬切（B 模式） | 某次闪光过亮 | imp 系数压 ≤0.15 重测 |
| 变身飞行中字形撕碎 | 全局排名映射 | bbox 归一化位置匹配 |
| 变身块之间发丝缝 | 格子正好等于 pitch | 格子尺寸 ×1.12 |
| 飞入的新格子像碎片 | 没穿新形象颜色 | 新元素全程带新色 |
| 扫描线雾化黑场 | normal 混合 | multiply |
| 多重色波读作闪烁 | 波间隔 <0.4s | 整拍间隔（2 拍有仪式感） |

下面是其中最耗时的若干条的英文详解（含诊断方法）。

---

Every entry below cost real time to diagnose. They are ordered roughly by how
much: the first four each ate the better part of an hour, and none of them
announce themselves — the code looks correct, the maths looks correct, and the
picture is just quietly wrong.

Read this before debugging anything visual. Faster still: render a contact sheet
of single frames at each timeline landmark *before* the full render, because
most of these are obvious in one still and invisible in a code review.

## Contents

- [The whole film looks washed-out grey](#the-whole-film-looks-washed-out-grey)
- [A faint square outline around a glow](#a-faint-square-outline-around-a-glow)
- [3D extrusion is geometrically correct but invisible](#3d-extrusion-is-geometrically-correct-but-invisible)
- [An alpha channel edit silently does nothing](#an-alpha-channel-edit-silently-does-nothing)
- [Extrusion side walls exist but read as flat](#extrusion-side-walls-exist-but-read-as-flat)
- [Thin strokes comb into stripes when extruded](#thin-strokes-comb-into-stripes-when-extruded)
- [Renders are slow and simplifying the JS does not help](#renders-are-slow-and-simplifying-the-js-does-not-help)
- [Half the particles are missing](#half-the-particles-are-missing)
- [The counter lands on the wrong number](#the-counter-lands-on-the-wrong-number)
- [Rolling digits look like broken glyphs](#rolling-digits-look-like-broken-glyphs)
- [Elements drift off-centre at other aspect ratios](#elements-drift-off-centre-at-other-aspect-ratios)
- [A 3D reveal is over before it registers](#a-3d-reveal-is-over-before-it-registers)
- [Ultra-wide art sits inside the frame but clips when rotated](#ultra-wide-art-sits-inside-the-frame-but-clips-when-rotated)
- [Every frame is identical](#every-frame-is-identical)
- [The output is truncated](#the-output-is-truncated)
- [Grain looks like a dirty lens](#grain-looks-like-a-dirty-lens)
- [A conic gradient ring has a visible seam](#a-conic-gradient-ring-has-a-visible-seam)
- [The film outlasts its music](#the-film-outlasts-its-music)

---

## The whole film looks washed-out grey

**Symptom.** Everything is milky. Blacks sit around 60/255 instead of 8/255.
The first frame may be almost white.

**Cause.** An impact flash written as `1 - progress`. Before the trigger time,
`seg(t, t0, t0+w)` is 0, so `1 - 0 = 1` — the flash is at *full brightness from
frame zero*, and stays there until its window opens. With several flashes summed
(a burst, a lock, four section hits, a finale) the constant offset can exceed 1.0
and lift the entire film.

**Fix.** Use a windowed one-shot impulse that is explicitly zero outside its
window:

```js
const imp = (t,t0,w,k=2.4)=> (t<t0||t>=t0+w) ? 0 : Math.pow(1-(t-t0)/w,k);
```

**How to catch it early.** Print the mean pixel value of a few frames. Frames
that should be near-black should read 8–12; anything above ~25 means a layer is
leaking. This one is much easier to find numerically than by eye.

---

## A faint square outline around a glow

**Symptom.** A soft rectangle, roughly centred, visible in dark areas. Reads as
a compression artifact or a bad export, and survives re-encoding.

**Cause.** A pre-rendered glow PNG whose profile has not decayed to zero by the
image border. Composited with `mix-blend-mode: screen`, any non-zero border
pixel adds light, so the square edge of the texture becomes visible. A gaussian
falloff that looks like it reaches black often still carries 15–120/255 at the
edge midpoint — and a ring whose radius exceeds half the canvas is simply cut
off by it.

**Fix.** Draw the profile inside a padded canvas *and* apply a hard radial
window that forces the outer band to exactly zero, re-applied after blurring
(blur pulls energy back outward). Then scale the display size up by the padding
factor so the on-screen glow is unchanged. `scripts/make_glow.py` does all of
this and prints a border check.

**How to catch it early.** Sample the image corners and edge midpoints — they
must be exactly `[0,0,0]`. Also scan a horizontal line across a dark frame: a
step in the values marks the texture boundary.

---

## 3D extrusion is geometrically correct but invisible

**Symptom.** A stacked-plane extrusion renders flat. Measuring the bounding
boxes proves the layers *are* being projected — the deepest slab is offset and
scaled — but the picture shows no depth.

**Cause.** A descendant of the `transform-style: preserve-3d` container has
`mix-blend-mode`, `opacity` other than 1, or a `filter`. Any of those force the
3D context to flatten. The transform tree still reports 3D positions, which is
why measurements mislead — only the *painting* collapses. A specular sweep
overlay with `mix-blend-mode: screen` will do it even while its opacity is 0,
because the layer's presence is enough.

**Fix.** Keep the preserve-3d subtree free of blend modes, group opacity and
filters. Put fades on an ancestor that is not itself preserve-3d, or on leaf
elements (a leaf has no 3D descendants to flatten). Replace `screen` blending
with a normal-blended white gradient at partial alpha — slightly less punchy,
and it keeps the depth.

**How to catch it early.** Render one frame with the suspect layer set to
`display:none`. If the extrusion appears, that layer is the culprit.

---

## An alpha channel edit silently does nothing

**Symptom.** Code that zeroes part of an alpha channel appears to run — no
error, and a verification check even reports success — but the pixels are
unchanged downstream.

**Cause.** In numpy, `arr[y0:, 3] = 0` on an `(H, W, 4)` array slices *column 3*,
not the alpha channel. It is valid, it silently modifies a one-pixel-wide
column, and a verification written the same wrong way agrees with it.

**Fix.** Always index the channel on the third axis: `arr[y0:, :, 3] = 0`.

**How to catch it early.** Verify by re-deriving the content bands from the
saved file rather than from the in-memory array. If the band you removed is
still in the file, the edit did not land where you think.

---

## Extrusion side walls exist but read as flat

**Symptom.** The slabs are in the right places, but the logo still looks like a
sticker.

**Cause.** The brightness ramp bottoms out too dark. Side walls at 5–10% of the
face brightness are indistinguishable from a black background, so the extruded
body has no silhouette.

**Fix.** Keep the ramp inside a visible band — roughly 0.58 nearest the face
down to 0.18 at the deepest slab, with a slight cool tint so it reads as shadow
rather than a dimmer copy. `logo_tools.py slabs` defaults to this.

---

## Thin strokes comb into stripes when extruded

**Symptom.** Heavy letterforms extrude cleanly, but a hairline strapline or
light-weight text turns into a venetian blind.

**Cause.** Stacked planes only look solid where consecutive slabs overlap on
screen. The screen-space step is `slabStep * sin(rotationY)`; when that exceeds
the stroke width, gaps open between slabs.

**Fix.** Two moves, and use both. Reduce the step and raise the slab count to
keep total depth (40 slabs at 0.3% of width beats 20 at 0.6%). And cut hairline
elements out of the extrusion source entirely — leave them flat on the front
face, which is also how a real 3D logo would be built. `logo_tools.py strip`
removes a row band for exactly this.

---

## Renders are slow and simplifying the JS does not help

**Symptom.** ~1 fps. Optimising the render function changes nothing.

**Cause.** The cost is rasterisation, not scripting. Measured on a small box,
style updates run at ~350 fps while capture runs at ~2 fps — so the JavaScript
is 0.5% of the budget. Blur is the expensive part: one full-frame blur pass per
filtered layer per frame.

**Fix, in order of payoff.**

1. Bake blurred glows into PNGs (removes several full-frame passes).
2. Replace per-element blur with **depth-sliced containers**: bucket particles
   into ~10–16 layers by depth, put one blur on each container, and reparent a
   particle only when its bucket changes. This turns 120 blur passes into 12
   with no visible difference, since depth-of-field is a smooth function of
   depth anyway.
3. Apply transient blur (motion smear) as a single filter on the parent
   container rather than per element.
4. Capture through CDP `Page.captureScreenshot` with `optimizeForSpeed: true`.
5. Run one browser process per core over disjoint frame ranges.

Note that per-element blur requires 3D transforms on each element, while
depth-sliced containers require flattening to 2D — a container filter would
break `preserve-3d` anyway. Project the perspective yourself:

```js
const sc = PD/(PD - z);                       // PD = perspective distance
const x  = worldX*sc, y = worldY*sc;
// tumble approximated as rotate + axis foreshortening; visually indistinguishable
const fx = 0.12 + 0.88*Math.abs(Math.cos(angleY));
const fy = 0.12 + 0.88*Math.abs(Math.cos(angleX));
el.style.transform = `translate(${x}px,${y}px) rotate(${angleZ}deg) scale(${sc*fx},${sc*fy})`;
```

---

## Half the particles are missing

**Symptom.** A particle field looks sparse. Raising the count barely helps.

**Cause.** The spawn range and the recycle wrap distance disagree. If depth is
seeded over a span of 6100 units but wrapping subtracts 3610, particles drift
into a region that fails the visibility test and never return.

**Fix.** Seed `z` over exactly `[Z_FAR, Z_NEAR]` and wrap by exactly
`Z_NEAR - Z_FAR`. One span, one constant, used in both places.

**How to catch it early.** Count how many particles pass the visibility test on
a mid-film frame. If it is roughly half the total, this is why.

---

## The counter lands on the wrong number

**Symptom.** A slot-machine counter meant to stop at `03` stops at `06`.

**Cause.** The reel position is a continuous count of digit-heights, so the digit
shown at rest is `total % 10`. A "spin 6 turns then land on 3" written as
`60 + 3 + 3` lands on 6.

**Fix.** Choose the total as `wholeTurns*10 + targetDigit` and nothing else:
`totalTens = 30 + tensDigit`, `totalOnes = 60 + onesDigit`. Different whole-turn
counts per reel also make the reels settle at different speeds, which is what
sells the mechanism.

---

## Rolling digits look like broken glyphs

**Symptom.** Mid-spin, digits are chopped flat top and bottom into fragments.
At rest, a ghost of the neighbouring digit hovers above the locked one.

**Cause.** A reel window exactly one cell tall hard-crops its neighbours. Adding
a fixed soft mask fixes the crop but then dims the settled digit, and if the
window is tall enough to show the neighbour at all, the neighbour is visible at
rest.

**Fix.** Two constraints together. Size the window so a neighbouring glyph can
never enter it (window half-height < the gap from centre to the neighbour's
glyph edge — roughly 1.3× the cell height for typical faces). And tie the
mask's falloff width to the spin speed, so it is soft while moving and exactly
zero once locked:

```js
const fw = (1 - spinProgress) * 0.19;   // fraction of the window
```

---

## Elements drift off-centre at other aspect ratios

**Symptom.** A layout tuned at 16:9 sits too low at 9:16, or a group's parts
separate.

**Cause.** Hand-computed `top` values as fractions of height. Every ratio needs
its own numbers, and any content change invalidates them.

**Fix.** Absolutely-positioned centred flex columns:

```css
.grp{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
     display:flex;flex-direction:column;align-items:center}
```

The stack centres itself at any ratio and stays centred when content changes.
Two follow-ons: children of a flex column must not keep a `translateX(-50%)`
from an earlier absolute layout, and letter-spaced text needs
`text-indent: <same value>` to cancel the trailing space that otherwise shifts
it left by half a letter-space.

---

## A 3D reveal is over before it registers

**Symptom.** A logo rotating in from a steep angle reads as flat. Frames a
third of a second apart look identical.

**Cause.** `easeOutExpo` reaches 79% in the first 22% of its duration. It is
right for something *arriving* — snappy and settled — and wrong for anything the
viewer needs to *read*, because all the interesting middle of the motion is
compressed into a few frames.

**Fix.** Split the easings by role: a fast expo for opacity and scale (it should
feel like it snaps in), a slower cubic ease-out over roughly 2 seconds for the
rotation. And keep the settled angle honest — 12–16° of Y rotation keeps the
extrusion legible, whereas settling to 5° throws away the depth you built.

---

## Ultra-wide art sits inside the frame but clips when rotated

**Symptom.** A lockup sized to 90% of frame width fits when flat, then clips at
both edges once it settles into its 3/4 rotation.

**Cause.** Perspective magnifies whatever is nearest the camera. At a settled
Y-rotation the near end sits at `z = (width/2)·sin(angle)` and is scaled by
`PD/(PD - z)` — around 7% larger for typical values. Projected half-width can
therefore exceed the flat half-width even though the cosine term shrinks it.

**Fix.** Budget for it: keep wide art at ~78% of frame width in portrait
(vs ~52% in landscape), or compute the projected extent and solve for the size.
Verify on a single frame at the settled angle, not at the start of the move.

---

## Every frame is identical

**Symptom.** A full render completes and every file is the same image.

**Cause.** A JavaScript exception during scene construction. `window.__ready`
never becomes true, and if the renderer's wait is lenient it proceeds anyway,
calling a `__render` that never got defined — or one whose dependencies were
never built.

**Fix.** Hook `pageerror` on every render (the bundled renderer does, and exits
non-zero on a ready timeout). The most common cause is a `const` referenced
before its declaration line — the module-level code runs top to bottom, so a
helper array declared below the builder that uses it throws
`X is not defined`.

---

## The output is truncated

**Symptom.** A 32-second film encodes to 9.85 seconds.

**Cause.** The encode was interrupted — usually a tool-call timeout killing a
foreground ffmpeg — leaving a partially written file that plays fine for its
truncated length.

**Fix.** Run long renders and encodes detached and poll the log. Linux-only detach helpers do
not exist on macOS — use `nohup <cmd> > render.log 2>&1 &` (or, in Claude Code,
the Bash tool's background mode).
Always verify duration and frame count afterwards:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=nb_frames -show_entries format=duration \
  -of csv=p=0 out.mp4
```

`nb_frames` must equal `duration × fps`.

---

## Grain looks like a dirty lens

**Symptom.** Film grain is present but feels like a smudge on the sensor.

**Cause.** A static noise texture. Real grain resamples every frame.

**Fix.** Move the noise `background-position` each frame, derived from `t` so it
stays deterministic:

```js
const g  = Math.sin(t*913.7)*4373.2;
const gx = (g - Math.floor(g))*260*S;
```

Keep it subtle — around 5% opacity in `overlay` blend mode.

---

## A conic gradient ring has a visible seam

**Symptom.** A spectrum ring shows a hard line where the last colour meets the
first.

**Cause.** A conic gradient wraps, so the two ends of a linear palette collide.
Interpolating directly between them invents an off-brand hue (orange to cyan
passes through muddy green).

**Fix.** Two options. Let the spectrum span ~86% of the circumference and blend
the remainder back to the start with a brightness dip, so the return arc reads
as the unlit side of the ring — a closed ring with no seam. Or fade the
intensity to zero across the join, giving a deliberate arc with a soft gap.
`make_glow.py` implements the first.

---

## The film outlasts its music

**Symptom.** The picture is still resolving and the audio has stopped.

**Cause.** Extending the duration without regenerating the score.

**Fix.** Keep the score's timeline constants in sync with the scene's, and treat
"change the duration" as a two-file edit. When you add a hold at the end, the
groove should clear out *before* the hold and leave a long decaying chord under
it — a held final card over silence reads as a mistake, over a decaying chord it
reads as an ending. Verify by printing per-bar RMS: the shape of that column
should match the shape of the film.
