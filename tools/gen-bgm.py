#!/usr/bin/env python3
"""
mr.ONE 项目原创配乐生成器 —— chill/lounge 系电钢+暖pad+疏松打击乐。
每支视频用不同调性时，改参数就好，不用重写整支脚本。

用法：
  python3 gen-bgm.py --bpm 76 --bars 104 --out bgm.wav
  python3 gen-bgm.py --bpm 70 --bars 104 --vibe --kick 0.16 --shaker-density 6 --out lounge.wav
  python3 gen-bgm.py --bpm 84 --bars 104 --no-vibe --kick 0.30 --shaker-density 8 --out chill.wav

已用过的三个调性（供参考，直接抄命令即可）：
  第二集 巴厘岛 chill/热带     --bpm 84 --kick 0.30 --shaker-density 8 --no-vibe
  第三集 安静专注（干货）      --bpm 76 --kick 0.16 --shaker-density 4 --no-vibe
  第四集 慵懒度假 lounge       --bpm 70 --kick 0.16 --shaker-density 6 --vibe

参数含义：
  --bpm             速度。干货/专注类 70-78；chill/热带类 82-88。
  --bars            小节数，104 小节 ≈ 4-6 分钟（依 bpm 而定），够盖过大多数单集长度。
  --kick            底鼓音量 0（无）~0.35（明显）。安静场景调低或 0，度假/chill 场景调高。
  --shaker-density  每小节 shaker 击数（4=疏松安静，8=较有节奏感）。
  --vibe/--no-vibe  要不要加 vibraphone 高音点缀（营造泳池边/度假感，干货类通常不用）。
  --seed            固定乱数种子，方便重现同一份配乐（不给的话每次会不一样）。
  --musicdb-hint    仅供参考：脚本跑完会印出建议的 script.json musicDb 起始值（-18 是本频道验证过的基准）。

出瓦档后记得：
  ffmpeg -y -i out.wav -c:a aac -b:a 192k projects/<slug>/assets/<name>.m4a
  storyboard.json 的 music.db 从 -18 开始，出样片listen 过再决定要不要调。
"""
import argparse
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

p = argparse.ArgumentParser()
p.add_argument("--bpm", type=float, default=76.0)
p.add_argument("--bars", type=int, default=104)
p.add_argument("--kick", type=float, default=0.20, help="底鼓音量 0~0.35")
p.add_argument("--shaker-density", type=int, default=6, help="每小节 shaker 击数")
p.add_argument("--vibe", action="store_true", default=False)
p.add_argument("--no-vibe", dest="vibe", action="store_false")
p.add_argument("--seed", type=int, default=7)
p.add_argument("--out", type=str, required=True)
args = p.parse_args()

SR = 48000
BPM = args.bpm
BEAT = 60.0 / BPM
BAR = 4 * BEAT
BARS = args.bars
DUR = BARS * BAR
n = int(DUR * SR)
rng = np.random.default_rng(args.seed)
L = np.zeros(n)
R = np.zeros(n)


def lp(x, f, order=2):
    b, a = butter(order, min(f / (SR / 2), 0.99), btype="low")
    return lfilter(b, a, x)


def hp(x, f, order=2):
    b, a = butter(order, min(f / (SR / 2), 0.99), btype="high")
    return lfilter(b, a, x)


def add(sig, start, pan=0.0, gain=1.0):
    i = int(start * SR)
    m = min(len(sig), n - i)
    if m <= 0:
        return
    l = gain * (1 - max(pan, 0) * 0.85)
    r = gain * (1 + min(pan, 0) * 0.85)
    L[i:i + m] += sig[:m] * l
    R[i:i + m] += sig[:m] * r


def env(ln, a, d, s, rel, sus=0.5):
    e = np.zeros(ln)
    ai, di, ri = int(a * SR), int(d * SR), int(rel * SR)
    si = max(ln - ai - di - ri, 0)
    e[:ai] = np.linspace(0, 1, ai, endpoint=False) if ai else 0
    if di:
        e[ai:ai + di] = np.linspace(1, sus, di, endpoint=False)
    if si:
        e[ai + di:ai + di + si] = sus
    if ri:
        e[ai + di + si:ai + di + si + ri] = np.linspace(sus, 0, ri)
    return e


def epiano(freq, dur, amp=0.16):
    ln = int(dur * SR)
    tt = np.arange(ln) / SR
    mod = np.sin(2 * np.pi * freq * 2 * tt) * np.exp(-tt * 5.5) * 3.0
    x = np.sin(2 * np.pi * freq * tt + mod)
    x += 0.35 * np.sin(2 * np.pi * freq * 2 * tt) * np.exp(-tt * 7)
    x *= np.exp(-tt * 2.2) * amp
    return lp(x, 4200)


def pad(freq, dur, amp=0.105):
    ln = int(dur * SR)
    tt = np.arange(ln) / SR
    x = np.zeros(ln)
    for k, d in ((1, 0), (1, 0.13), (2, -0.09), (3, 0.07)):
        x += np.sin(2 * np.pi * (freq * k + d) * tt + rng.random() * 6.28) / (k * 1.6)
    x *= (1 + 0.06 * np.sin(2 * np.pi * 0.17 * tt))
    return lp(x, 1500) * env(ln, 0.9, 0.4, 0, 1.2, 0.85) * amp


def vibe(freq, dur, amp=0.10):
    ln = int(dur * SR)
    tt = np.arange(ln) / SR
    trem = 1 + 0.5 * np.sin(2 * np.pi * 5.0 * tt)
    x = np.sin(2 * np.pi * freq * tt) * trem
    return lp(x, 6000) * np.exp(-tt * 1.8) * amp


def bass(freq, dur, amp=0.30):
    ln = int(dur * SR)
    tt = np.arange(ln) / SR
    x = np.sin(2 * np.pi * freq * tt) + 0.22 * np.sin(2 * np.pi * freq * 2 * tt)
    return lp(x, 320) * env(ln, 0.01, 0.12, 0, 0.25, 0.7) * amp


def shaker(dur=0.09, amp=0.04):
    ln = int(dur * SR)
    tt = np.arange(ln) / SR
    x = rng.normal(0, 1, ln) * np.exp(-tt * 38)
    return hp(x, 5200) * amp


def kick(amp=0.20):
    ln = int(0.30 * SR)
    tt = np.arange(ln) / SR
    f = 52 * np.exp(-tt * 22) + 42
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 7.5)
    return lp(x, 180) * amp


def rim(amp=0.03):
    ln = int(0.05 * SR)
    tt = np.arange(ln) / SR
    return hp(rng.normal(0, 1, ln) * np.exp(-tt * 70), 2500) * amp


NOTE = {
    "A2": 110.00, "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61, "G3": 196.00,
    "A3": 220.00, "B3": 246.94, "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23,
    "G4": 392.00, "A4": 440.00, "B4": 493.88, "C5": 523.25, "D5": 587.33, "E5": 659.25,
}
prog = [
    ("A2", ["A3", "C4", "E4", "B4"]),
    ("F3", ["F3", "A3", "C4", "E4"]),
    ("C3", ["C4", "E4", "G4", "B4"]),
    ("G3", ["G3", "B3", "D4", "E4"]),
]

for b in range(BARS):
    t0 = b * BAR
    ch = prog[b % 4]
    root = NOTE[ch[0]]
    intro = b < 2
    outro = b >= BARS - 2
    lvl = 0.5 if intro else (0.6 if outro else 1.0)

    for i, nm in enumerate(ch[1]):
        add(pad(NOTE[nm], BAR * 1.05, 0.105 * lvl), t0, pan=(i - 1.5) * 0.30)

    add(bass(root, BEAT * 1.6, 0.30 * lvl), t0)
    add(bass(root, BEAT * 0.9, 0.20 * lvl), t0 + BEAT * 2.5)

    if not intro:
        for j, off in enumerate([0.5, 1.5, 2.25, 3.0, 3.5]):
            nm = ch[1][(j + b) % len(ch[1])]
            add(epiano(NOTE[nm], BEAT * 1.5, 0.16 * lvl), t0 + off * BEAT, pan=((j % 3) - 1) * 0.3)

    if args.vibe and 3 <= b < BARS - 3 and b % 2 == 0:
        mel = [ch[1][-1], ch[1][-2]]
        f = NOTE[mel[0]] * 2 if NOTE[mel[0]] < 400 else NOTE[mel[0]]
        add(vibe(f, BEAT * 3, 0.10 * lvl), t0 + BEAT * 1.0, pan=0.2)
    elif not args.vibe and 3 <= b < BARS - 3 and b % 2 == 0:
        mel = [ch[1][-1], ch[1][-2]]
        f = NOTE[mel[0]] * 2 if NOTE[mel[0]] < 400 else NOTE[mel[0]]
        add(epiano(f, BEAT * 2, 0.10 * lvl), t0 + BEAT * 1.0, pan=0.15)

    if b >= 2 and not outro:
        sd = max(2, args.shaker_density)
        for s in range(sd):
            amp = (0.045 if s % 3 == sd % 3 else 0.024) * lvl
            add(shaker(amp=amp), t0 + s * BAR / sd, pan=0.3 if s % 2 else -0.28)
        if args.kick > 0:
            add(kick(args.kick * lvl), t0)
            if args.kick >= 0.25:
                add(kick(args.kick * 0.7 * lvl), t0 + BEAT * 2.5)
        add(rim(0.03 * lvl), t0 + BEAT * 2)


def finish(x):
    x = lp(x, 13000)
    x = np.tanh(x * 1.25) / 1.25
    return x


L = finish(L)
R = finish(R)
fi, fo = int(2.5 * SR), int(4.0 * SR)
w = np.ones(n)
w[:fi] = np.linspace(0, 1, fi)
w[-fo:] = np.linspace(1, 0, fo)
L *= w
R *= w
peak = max(np.abs(L).max(), np.abs(R).max())
st = np.stack([L, R], axis=1) / peak * 0.85
wavfile.write(args.out, SR, (st * 32767).astype(np.int16))
print(f"ok {DUR:.1f}s -> {args.out}")
print("建议 storyboard.json 起始 music.db = -18（本频道验证过的基准，出样片再微调）")
