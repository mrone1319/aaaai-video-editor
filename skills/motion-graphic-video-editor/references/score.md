# Score and sound design

## 中文摘要（原 SKILL.md §9 全文）

## 9. Score — 原创配乐合成（numpy/scipy，零素材零版权）

**原则：编曲从视觉时间轴出发**——场景 `T` 常量原样复制进配乐脚本；每个视觉事件一个 hit，同步是查表。

### 9.1 和声与编排形状

- E 自然小调是科技/商业片安全默认；每小节一个和弦，**信息最重的小节落主和弦**。
- 编排照画面写：安静 bar1 → burst 进鼓 → 全速 groove →（文案段）**breakdown 撤鼓只留 pad——没有 breakdown，drop 落不下来，全程响 = 没有高潮**→ money 帧 = drop 最响小节 → groove 回落 → 尾板前 groove 清空，留 3–5s 衰减主和弦 + 一次轻 sub swell 托住 logo → 静音。**held frame over silence 读作事故；over a decaying chord 读作结束。**

### 9.2 乐器库（全部正弦/噪声合成，各 ~5 行）

kick（音高下扫正弦 128→45Hz + 咔哒头）/ sub bass（八分根音低通 260Hz 给 kick 让路，每小节末八分升八度）/ hats（高通噪声 22ms 反拍 + 十六分 shaker）/ clap（双段带通噪声 2/4 拍）/ pad（失谐锯齿低通 1500Hz）/ 十六分琶音（和弦音跨两个八度 + 附点八分回声进湿声总线——中段能量来源）/ riser（上行带通扫频、平方幅度斜坡，每次大 hit 前 1.2–2s 一条）/ impact（tanh 饱和 sub 下坠 + 瞬态 crack + 分块带通下行 whoosh）/ shatter（crack + 40–60 粒 2–9kHz 随机正弦颗粒 + 下坠 whoosh + 小 sub 重击）/ chime（正弦叠泛音 f:2f:3.01f 重湿声）/ crash（可反转做 reverse cymbal）。

### 9.3 与画面锁死的细节

- **计数器 tick 密度由与画面完全相同的缓动曲线驱动**——听到的减速就是看到的减速；每位落位一记轻响，末位完整锁定音+impact。
- 视觉事件重复 N 次（波/脉冲/列表项）就 N 声，音高或亮度**沿组递升**。
- 逐字动画：每字一 tick，音高沿渐变爬升。
- 黑场呼吸处音频同步挖静（dip 到 5%）。
- **侧链**：每个 kick 附近 pad/bass 压到 ~0.62 再恢复，否则低频糊。
- 混响 = 指数衰减噪声卷积（~2s，LP 7k / HP 150）；湿声 ~9ms Haas 延迟做宽度，**干声保持单声道**（低频才稳）；tanh 软限幅；归一 0.95；结尾 fade 与画面淡黑同步。

### 9.4 验证

打印每小节 RMS，柱形必须和影片形状一致：开场安静 → burst 跳升 → 中段饱满 → breakdown 明显凹下 → drop 最响 → 衰减到近零。缺凹 = drop 不成立；末尾不衰减 = 画面完了音乐没完。
**改片长 = 场景 + 配乐两个文件必须同改，配乐重新合成。**

### 9.5 静音版

社媒自播可交静音版（同帧序列去音轨编码），但**先关声音看一遍全片**——节奏必须纯视觉成立；靠音效才看得懂的片子在信息流里是废片。

---

以下是英文详解与代码。

An original arrangement synthesised with numpy, on the same grid as the picture.
Not sound effects sprinkled over a bed — a real arrangement with a progression,
a groove, a breakdown and a drop, where the drop is the frame you want people to
remember.

Two reasons to write it from code rather than licensing a track. It can be
*composed to the cut* — the groove thins exactly where the picture goes quiet and
hits hardest where the picture does, which no library track will do. And when the
duration changes (it will), regenerating takes seconds.

## The grid is the whole trick

Share one timeline between the score and the scene. Copy the scene's constants
into the score file verbatim:

```python
BURST, NUM_IN, LOCK = 2.00, 6.00, 8.00
PIL, PIL_BEAT       = 12.00, 1.00
STMT, DROP          = 16.00, 20.00
BEAT, BAR           = 0.5, 2.0            # 120 BPM
bar = lambda n: (n - 1) * BAR
```

Now "the kick lands on the cut" is arithmetic, not nudging. And a change to the
scene's timeline is a copy-paste away from being reflected in the music.

## Arrangement shape

Write the arrangement *from* the visual structure. A 35-second film in 18 bars:

| bars | seconds | picture | music |
|---|---|---|---|
| 1 | 0–2 | tension, riser | pad only, very quiet |
| 2 | 2–4 | **burst** | impact on the downbeat, kick + bass enter |
| 3–4 | 4–8 | tunnel, counter spins | full groove, arpeggio enters, ticks |
| 5 | 8–10 | **counter locks** | lock hit + bell on the bar line |
| 6 | 10–12 | payload holds | groove continues, slight thin-out |
| 7–8 | 12–16 | four section cards | one stab per card, rising notes |
| 9–10 | 16–20 | statement, black | **breakdown**: kick and hats out, pad carries |
| 11–12 | 20–24 | **3D reveal** | **drop**: loudest bar, bell motif |
| 13–14 | 24–28 | information cards | groove eased back, room for text |
| 15 | 28–30 | last card appears | groove clears, long chord begins |
| 16–18 | 30–35 | held card, logo fade | chord decays, one soft swell, silence |

The breakdown is what makes the drop land. Do not skip it — a film that is loud
throughout has no climax, and the reveal you spent the most effort on will land
softest.

## Harmony

E natural minor is a safe, slightly serious choice for tech and Web3 brands.
Store roots and triads and index by bar:

```python
CH = {
  'Em': (82.41,  [164.81, 196.00, 246.94]),
  'C' : (65.41,  [130.81, 164.81, 196.00]),
  'G' : (98.00,  [196.00, 246.94, 293.66]),
  'D' : (73.42,  [146.83, 185.00, 220.00]),
  'Am': (110.00, [220.00, 261.63, 329.63]),
}
PROG = ['Em','Em','Em','C','G','D','Em','C','Am','Em','Em','C','G','D','Em','Em','Em','Em']
```

Put the reveal bar on the tonic (Em here) — resolution under the money frame.

## Building blocks

Scaffold — two buses so reverb can be applied selectively:

```python
SR, DUR = 48000, 35.0
N   = int(SR * DUR)
dry = np.zeros(N); wet = np.zeros(N)
rs  = np.random.default_rng(20260728)      # seed it; renders should be identical
idx = lambda x: int(round(x * SR))

def add(buf, start, sig, gain=1.0):
    a = idx(start)
    if a < 0: sig = sig[-a:]; a = 0
    b = min(N, a + len(sig))
    if b > a: buf[a:b] += sig[:b-a] * gain

def env(n, atk=0.002, dec=0.3, p=1.0):
    e = np.ones(n); na = max(1, idx(atk))
    e[:na] = np.linspace(0, 1, na) ** 0.6
    return e * np.exp(-(np.arange(n)/SR) / max(1e-4, dec)) ** p

def lp(x,f,o=2): return signal.sosfilt(signal.butter(o,min(.99,f/(SR/2)),'low', output='sos'),x)
def hp(x,f,o=2): return signal.sosfilt(signal.butter(o,min(.99,f/(SR/2)),'high',output='sos'),x)
def bp(x,lo,hi): return signal.sosfilt(signal.butter(2,[lo/(SR/2),min(.99,hi/(SR/2))],'band',output='sos'),x)

def saw(f, n, det=0.0):                     # additive; cheap and clean
    k = np.arange(n)/SR; out = np.zeros(n)
    for h in range(1, 15):
        out += np.sin(2*np.pi*f*h*k + h*0.7) / h
        if det: out += np.sin(2*np.pi*f*(1+det)*h*k) / h * 0.6
    return out / 2.2
```

**Kick** — pitch-swept sine, the workhorse:

```python
n = idx(0.45); k = np.arange(n)/SR
f = 128*np.exp(-k/0.05) + 45                       # 128 Hz down to 45
kick  = np.sin(np.cumsum(2*np.pi*f/SR)) * env(n, 0.001, 0.135) * 0.60
kick += hp(rs.standard_normal(n), 3200) * env(n, 0.0004, 0.010) * 0.05   # click
```

**Sub bass** — root on eighths, low-passed at 260 Hz to stay out of the kick's way.
Octave-up on the last eighth of a bar gives forward motion.

**Hats** — high-passed noise, ~22 ms decay, on offbeat eighths. Add a quieter
sixteenth shaker from the third bar.

**Clap** — two band-passed noise bursts (1.1–4.2 kHz short, 0.7–2 kHz longer) on
beats 2 and 4.

**Arpeggio** — sixteenth-note plucks cycling chord tones over two octaves, with a
dotted-eighth echo into the wet bus. This is what gives the middle its energy;
without it the groove is just drums.

**Impact** — the burst. Sub drop, transient crack, and a descending whoosh:

```python
n = idx(1.7); k = np.arange(n)/SR
f   = 94*np.exp(-k/0.30) + 33
sub = np.tanh(np.sin(np.cumsum(2*np.pi*f/SR)) * env(n,0.001,0.44) * 1.5) * 0.68
tr  = hp(rs.standard_normal(n), 1800) * env(n, 0.0005, 0.045) * 0.40
# whoosh: band-pass sweeping down, in chunks
wh = np.zeros(n); nz = rs.standard_normal(n)
for i in range(0, n, 480):
    j = min(n, i+480); fr = 4400*np.exp(-(i/SR)/0.42) + 220
    wh[i:j] = bp(nz[i:j], fr*0.6, fr*1.6)
wh *= env(n, 0.004, 0.48) * 0.28
```

**Riser** — the reverse of the whoosh: band-pass sweeping *up* over 2 seconds
with a squared amplitude ramp, plus a rising sine. Put one before the burst and
one before the drop.

**Ticks** — for a spinning counter, drive the click density from *the same easing
curve as the visual*, so the sound decelerates exactly as the reel does:

```python
ease = lambda p: 0.0 if p <= 0 else (1.0 if p >= 1 else 1 - 2**(-10*p))
x = 0.0
while x < LOCK - NUM_IN:
    p = x / (LOCK - NUM_IN)
    x += 1.0 / (30*(1-ease(p)) + 3.2)          # 30/s down to ~3/s
    add(dry, NUM_IN + x, click)
```

**Chimes** — short sine stacks (fundamental + 2nd + 3rd) with 0.2s decay, sent
heavily to reverb. One per resolved character in a decode, or a rising motif over
a reveal.

## Sidechain ducking

Without this the low end is mud. Duck the pad and bass around each kick:

```python
duck = np.ones(N)
t = BURST
while t < DUR:
    if kick_on(t):
        a, n = idx(t), idx(0.16)
        b = min(N, a+n)
        duck[a:b] = np.minimum(duck[a:b], 0.62 + 0.38*np.linspace(0,1,b-a)**0.55)
    t += BEAT
dry *= duck
wet *= 0.75 + 0.25*duck        # duck the reverb less, so it breathes
```

## Reverb and master

Convolution with exponentially decaying noise is plenty:

```python
ir = rs.standard_normal(idx(2.0)) * np.exp(-np.arange(idx(2.0))/(SR*0.46))
ir = hp(lp(ir, 7000), 150); ir /= np.abs(ir).max() * 26
rev = signal.fftconvolve(wet, ir)[:N]
```

Stereo width via a tiny Haas delay on the reverb only (~9 ms), soft-clip with
`tanh`, normalise to about 0.95, and fade the last 0.85s:

```python
revs = np.roll(rev, idx(0.009))
L = np.tanh((dry + rev*0.87 + revs*0.30) * 1.10)
R = np.tanh((dry + revs*0.87 + rev*0.30) * 1.10)
```

Keep the dry bus mono — a centred low end is what makes it feel solid.

## Verify by looking at the numbers

Print per-bar RMS and read it as a shape:

```python
for i in range(len(PROG)):
    s = stereo[idx(i*BAR):idx((i+1)*BAR)]
    print('bar %2d %-3s rms %.3f' % (i+1, PROG[i], np.sqrt((s**2).mean())))
```

You are looking for: quiet bar 1, a jump at the burst, a steady middle, a clear
dip at the breakdown, the maximum at the drop, then a decay to near zero. If the
dip is missing the drop will not land. If the last bars are not decaying the film
will end before the music does.

## Endings

When the picture holds on a final card or logo, the groove must clear out *before*
the hold, leaving a long decaying chord underneath. A held frame over silence
reads as a mistake; over a decaying chord it reads as an ending. Cut kick, clap,
hats and arpeggio at the start of the hold, start a 3–4 second chord there, and
add one soft sub swell as the logo appears.
