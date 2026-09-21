#!/usr/bin/env python3
"""Pre-render glow layers (spectrum ring, hot core, ambient bloom) as PNGs.

Why offline instead of a CSS filter: a blurred full-frame layer costs one blur
pass per frame per layer and is usually the single biggest drag on render speed.
Baked as an image, the scene only animates transform and opacity, which is
nearly free. These composite with `mix-blend-mode: screen`, so black adds
nothing and no alpha channel is needed.

The critical detail is `pad`. The glow profile has to reach true black well
inside the canvas border, otherwise the square edge of the image shows up as a
visible rectangle once screen-composited over a dark background — a subtle
artifact that reads as "cheap" and is maddening to diagnose after the fact. Two
defences are applied: the profile is drawn small inside a padded canvas, and a
hard radial window forces the outer ring of pixels to exactly zero (re-applied
after blurring, since blur pulls energy back outward).

Because of the padding, the on-screen display size must be scaled up to
compensate. The generator prints the factor for each image; use it directly:

    ring   width = ring_display_factor  * min(W, H)
    bloom  width = bloom_display_factor * min(W, H)

Usage (必须按用户品牌替换 —— the defaults are a neutral grey/white placeholder,
never ship them; pass the brand's own measured spectrum and glow colours):
    ~/.aaaai-editor/bin/aaaai-editor-python make_glow.py --out assets \
        --spectrum "#<brand1>,#<brand2>,#<brand3>"
    ~/.aaaai-editor/bin/aaaai-editor-python make_glow.py --out assets \
        --core-rgb 243,243,238 --bloom-rgb <r,g,b> --bloom-rgb2 <r,g,b>
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageFilter


def hex_rgb(h):
    h = h.strip().lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def spec_lut(stops, n=1024):
    """stops: list of (position 0..1, (r,g,b))."""
    xs = np.linspace(0, 1, n)
    pos = np.array([s[0] for s in stops], dtype=np.float32)
    col = np.array([s[1] for s in stops], dtype=np.float32)
    out = np.zeros((n, 3), np.float32)
    for c in range(3):
        out[:, c] = np.interp(xs, pos, col[:, c])
    return out


def _smooth(a, b, v):
    k = np.clip((v - a) / (b - a), 0, 1)
    return k * k * (3 - 2 * k)


def _edge_window(rn, inner=0.42, outer=0.485):
    """1 inside, 0 by `outer` of the canvas — guarantees black borders."""
    return 1.0 - _smooth(inner, outer, rn)


def make_ring(size, stops, r0=0.395, width=0.045, blur=0.020, gain=1.0,
              start_deg=-58, pad=1.60, dip=0.42, span=0.865):
    """A closed spectrum donut.

    `span` is the fraction of the circumference the spectrum occupies; the
    remainder blends the last colour back to the first. That return arc is
    darkened by `dip` so the ring closes without a hard seam and without
    inventing an off-brand hue in the middle (interpolating orange to cyan
    through RGB passes through a muddy green, which a shaded arc hides).
    """
    lut = spec_lut(stops)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2.0
    dx, dy = x - c, y - c
    rn = np.sqrt(dx * dx + dy * dy) / size          # 0 .. 0.707 at the corners
    r = rn * pad                                    # profile space
    ang = (np.degrees(np.arctan2(dy, dx)) - start_deg) % 360.0
    u = ang / 360.0

    idx = np.clip((np.clip(u / span, 0, 1) * (len(lut) - 1)).astype(np.int32),
                  0, len(lut) - 1)
    col = lut[idx].copy()
    m = u > span
    if m.any():
        k = ((u[m] - span) / (1.0 - span))[:, None]
        col[m] = lut[-1] * (1 - k) + lut[0] * k
        shade = 1.0 - (1.0 - dip) * np.sin(np.pi * k[:, 0]) ** 0.7
        col[m] *= shade[:, None]

    prof = np.exp(-0.5 * ((r - r0) / width) ** 2)
    prof += 0.16 * np.exp(-0.5 * ((r - r0) / (width * 2.6)) ** 2)
    prof = np.clip(prof, 0, 1.6)

    edge = _edge_window(rn)
    img = np.clip(col * (prof * edge)[..., None] * gain, 0, 255).astype(np.uint8)
    im = Image.fromarray(img, "RGB")
    if blur > 0:
        im = im.filter(ImageFilter.GaussianBlur(size * blur))
    arr = np.asarray(im).astype(np.float32) * edge[..., None]   # re-clamp
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB"), r0 / pad


def make_core(size, hot=(243, 243, 238), halo=(200, 200, 200), pad=1.7):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2.0
    rn = np.sqrt((x - c) ** 2 + (y - c) ** 2) / size
    r = rn * pad
    a = np.exp(-0.5 * (r / 0.075) ** 2)
    b = np.exp(-0.5 * (r / 0.17) ** 2)
    img = np.zeros((size, size, 3), np.float32)
    for i in range(3):
        img[..., i] = hot[i] * a + halo[i] * b
    edge = _edge_window(rn, 0.40, 0.485)
    img *= edge[..., None]
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
    im = im.filter(ImageFilter.GaussianBlur(size * 0.02))
    arr = np.asarray(im).astype(np.float32) * edge[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB"), 0.075 / pad


def make_bloom(size, rgb=(150, 150, 150), rgb2=(90, 90, 90), pad=1.9):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2.0
    rn = np.sqrt((x - c) ** 2 + (y - c) ** 2) / size
    r = rn * pad
    a = np.exp(-0.5 * (r / 0.20) ** 2)
    b = np.exp(-0.5 * (r / 0.36) ** 2)
    img = np.zeros((size, size, 3), np.float32)
    for i in range(3):
        img[..., i] = rgb[i] * 0.42 * a + rgb2[i] * 0.26 * b
    img *= _edge_window(rn, 0.40, 0.485)[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB"), 0.36 / pad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="assets")
    # 必须按用户品牌替换：以下默认值只是中性灰/白双色占位，不代表任何品牌。
    ap.add_argument("--spectrum",
                    default="#8A8A8A,#F2F2F2",
                    help="comma-separated hex colours, evenly spaced "
                         "(placeholder grey/white — 必须按用户品牌替换)")
    ap.add_argument("--positions", default="",
                    help="optional comma-separated stop positions 0..1, same count")
    ap.add_argument("--start-deg", type=float, default=-58.0)
    ap.add_argument("--core-rgb", default="243,243,238")
    ap.add_argument("--core-halo", default="200,200,200")
    ap.add_argument("--bloom-rgb", default="150,150,150")
    ap.add_argument("--bloom-rgb2", default="90,90,90")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    cols = [hex_rgb(h) for h in a.spectrum.split(",")]
    if a.positions:
        pos = [float(x) for x in a.positions.split(",")]
    else:
        pos = list(np.linspace(0, 1, len(cols)))
    stops = list(zip(pos, cols))

    ring, ring_f = make_ring(1000, stops, start_deg=a.start_deg)
    ring.save(f"{a.out}/ring.png")
    soft, soft_f = make_ring(820, stops, r0=0.375, width=0.072, blur=0.042,
                             gain=0.80, start_deg=a.start_deg, pad=1.85)
    soft.save(f"{a.out}/ring_soft.png")
    core, core_f = make_core(460, tuple(int(v) for v in a.core_rgb.split(",")),
                             tuple(int(v) for v in a.core_halo.split(",")))
    core.save(f"{a.out}/core.png")
    bloom, bloom_f = make_bloom(560,
                                tuple(int(v) for v in a.bloom_rgb.split(",")),
                                tuple(int(v) for v in a.bloom_rgb2.split(",")))
    bloom.save(f"{a.out}/bloom.png")

    print("written to", a.out)
    print("\nDisplay sizes — multiply by min(W,H). These undo the padding, so the")
    print("on-screen glow ends up the size the profile was designed for:")
    print(f"  ring.png       width = {0.74 / (2 * ring_f):.3f} * min(W,H)")
    print(f"  ring_soft.png  width = {0.76 / (2 * soft_f):.3f} * min(W,H)")
    print(f"  core.png       width = {0.033 / core_f:.3f} * min(W,H)")
    print(f"  bloom.png      width = {0.396 / bloom_f:.3f} * min(W,H)")
    print("\nComposite each with mix-blend-mode: screen and animate only")
    print("transform/opacity. Do not add a CSS blur filter — it is already baked in.")

    for n in ("ring", "ring_soft", "core", "bloom"):
        arr = np.asarray(Image.open(f"{a.out}/{n}.png").convert("RGB")).astype(int)
        h, w, _ = arr.shape
        border = max(arr[1, 1].max(), arr[h // 2, 1].max(), arr[1, w // 2].max())
        flag = "OK" if border == 0 else f"WARNING border={border} (will show a square)"
        print(f"  {n}.png border check: {flag}")
