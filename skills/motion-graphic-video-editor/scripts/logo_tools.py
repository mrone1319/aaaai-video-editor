#!/usr/bin/env python3
"""Turn a flat logo image into animatable parts.

Subcommands
-----------
key     Alpha-key a logo off a solid background (screenshots and brand-book
        exports usually arrive as opaque PNGs on near-black or white).
bands   Report the row/column bands of opaque content — this is how you find
        where one word ends and the next begins, or which row is the hairline
        strapline, without eyeballing pixel coordinates.
split   Cut the image into left/right parts at a column, each kept on the
        original full-size canvas so both can be layered at left:0;top:0 and
        stay in register. Needed whenever one word animates independently.
letters Crop individual letterforms. Animating the brand's own glyphs instead
        of substituting a typeface is the single cheapest way to make a section
        look unmistakably on-brand.
slabs   Build the brightness ramp used for 3D extrusion.
strip   Zero the alpha below/above a row — used to drop hairline text out of an
        extrusion source (thin strokes comb between slabs).
outline Trace the logo's alpha into vector outlines (outer contours + holes) as
        JSON, for a real 3D extrusion in three.js (assets/mg-three.js). The
        front face is then textured with the original PNG, so gradients and
        colours stay exact. Needs OpenCV (optional): $PY -m pip install --user
        opencv-python-headless

Note on `letters`: crops share one vertical band (the mark's own cap and base
lines) rather than each letter's own bounding box. That keeps true relative
proportions and a common baseline, so ascenders stay tall and x-height letters
stay short. Cropping each to its own box makes 'a' and 'c' look oversized next
to 'b' and 'd' and instantly reads as wrong.
"""
import argparse
import json
import os

import numpy as np
from PIL import Image, ImageFilter


# ---------------------------------------------------------------- helpers
def load(path):
    return Image.open(path).convert("RGBA")


def runs(profile):
    """Contiguous ranges where profile > 0, as [(start, end), ...]."""
    out, inr, st = [], False, 0
    for i, v in enumerate(profile > 0):
        if v and not inr:
            st, inr = i, True
        elif not v and inr:
            out.append((st, i - 1))
            inr = False
    if inr:
        out.append((st, len(profile) - 1))
    return out


def bands_of(img, thresh=30):
    a = np.asarray(img)[..., 3] > thresh
    return {"rows": runs(a.sum(axis=1)), "cols": runs(a.sum(axis=0))}


# ---------------------------------------------------------------- commands
def cmd_key(args):
    """Un-multiply a logo off a flat background into clean straight alpha."""
    src = Image.open(args.src).convert("RGB")
    a = np.asarray(src).astype(np.float32)
    if args.bg:
        bg = np.array([float(v) for v in args.bg.split(",")], np.float32)
    else:
        # sample the four corners; brand exports are almost always flat there
        bg = np.mean([a[2, 2], a[2, -3], a[-3, 2], a[-3, -3]], axis=0)
    print(f"background sampled as {bg.round(1).tolist()}")

    d = np.clip(a - bg, 0, 255)
    al = d.max(axis=2) / 255.0
    al = np.clip((al - args.floor) / (1.0 - args.floor), 0, 1)   # kill faint glow
    safe = np.clip(al, 1e-6, 1)
    col = np.clip(d / safe[..., None], 0, 255)
    out = Image.fromarray(np.dstack([col, al * 255]).astype(np.uint8), "RGBA")
    if args.crop:
        out = out.crop(out.getbbox())
    out.save(args.out)
    print(f"wrote {args.out} {out.size}")
    print("bands:", json.dumps(bands_of(out), indent=1))


def cmd_bands(args):
    print(json.dumps(bands_of(load(args.src), args.thresh), indent=1))


def cmd_split(args):
    """Split at a column, keeping both halves on the original canvas."""
    full = load(args.src)
    A = np.asarray(full).astype(np.float32)
    os.makedirs(args.out, exist_ok=True)
    for name, keep_left in (("part_left", True), ("part_right", False)):
        o = A.copy()
        if keep_left:
            o[:, args.x:, 3] = 0.0
        else:
            o[:, :args.x, 3] = 0.0
        im = Image.fromarray(o.astype(np.uint8), "RGBA")
        p = os.path.join(args.out, f"{name}.png")
        im.save(p)
        print(f"wrote {p} {im.size} (full canvas, layer at left:0;top:0)")


def cmd_strip(args):
    """Zero alpha from a row down (or up), e.g. to drop a hairline strapline."""
    full = load(args.src)
    A = np.asarray(full).astype(np.float32).copy()
    b = bands_of(full)["rows"]
    if args.row is not None:
        y0 = args.row
    else:
        if len(b) < 2:
            print("only one row band found; nothing to strip")
            return
        y0 = b[-1][0] - 2
        print(f"stripping the last row band, starting at y={y0}")
    # NOTE the channel index must be the third axis: A[y0:, :, 3].
    # A[y0:, 3] silently slices *column* 3 instead and looks like it worked.
    if args.above:
        A[:y0, :, 3] = 0.0
    else:
        A[y0:, :, 3] = 0.0
    im = Image.fromarray(A.astype(np.uint8), "RGBA")
    im.save(args.out)
    print(f"wrote {args.out} — remaining bands: {bands_of(im)['rows']}")


def cmd_letters(args):
    """Crop each letterform against a shared vertical band."""
    full = load(args.src)
    a = np.asarray(full)[..., 3] > 30
    if args.max_x:
        a = a.copy()
        a[:, args.max_x:] = False

    row_bands = runs(a.sum(axis=1))
    top, bottom = row_bands[0]          # the mark band, excluding any strapline
    cols = [r for r in runs(a.sum(axis=0)) if (r[1] - r[0]) >= args.min_w]
    chars = list(args.chars)
    if len(cols) != len(chars):
        print(f"found {len(cols)} glyph columns {cols} but {len(chars)} chars "
              f"were given — adjust --min-w or --max-x")
        return

    os.makedirs(args.out, exist_ok=True)
    meta = {}
    for ch, (x0, x1) in zip(chars, cols):
        g = full.crop((x0, top, x1 + 1, bottom + 1))
        p = os.path.join(args.out, f"glyph_{ch}.png")
        g.save(p)
        meta[ch] = {"w": g.width, "h": g.height, "x0": int(x0)}
        print(f"wrote {p} {g.size}")
    meta_path = os.path.join(args.out, "glyphs.json")
    with open(meta_path, "w") as f:
        json.dump({"band": [int(top), int(bottom)], "glyphs": meta}, f, indent=1)
    print(f"wrote {meta_path}")
    print("All crops share one band, so displaying them at equal height keeps "
          "the real proportions and a common baseline.")


def cmd_slabs(args):
    """Brightness ramp for stacked-plane 3D extrusion.

    Side walls must stay clearly visible: too dark and the extrusion vanishes
    against a black background even though the geometry is correct. The default
    floor of 0.18 and near value of 0.58 read as a shaded solid without
    competing with the front face.
    """
    src = load(args.src)
    w = args.width
    im = src.resize((w, round(w * src.height / src.width)), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)
    tint = np.array([float(v) for v in args.tint.split(",")], np.float32)
    os.makedirs(args.out, exist_ok=True)
    for i in range(args.levels):
        k = i / (args.levels - 1)                 # 0 = nearest behind the face
        bright = args.floor + args.near * (1 - k) ** 1.05
        o = a.copy()
        o[..., :3] = np.clip(o[..., :3] * bright * tint, 0, 255)
        p = os.path.join(args.out, f"{args.prefix}_{i}.png")
        Image.fromarray(o.astype(np.uint8), "RGBA").save(p)
    print(f"wrote {args.levels} slab levels to {args.out}/{args.prefix}_*.png")
    print("In the scene, place ~40 copies at translateZ(-i * step) with")
    print("step ~= 0.003 * displayWidth, choosing the level by i/(N-1).")
    print("Paint order: deepest first, front face last.")


def cmd_reflect(args):
    """Faded, flipped copy for a floor reflection."""
    src = load(args.src)
    w = args.width
    im = src.resize((w, round(w * src.height / src.width)), Image.LANCZOS)
    im = im.transpose(Image.FLIP_TOP_BOTTOM)
    a = np.asarray(im).astype(np.float32)
    h = a.shape[0]
    fade = np.clip(1.0 - np.arange(h) / (h * 0.85), 0, 1)[:, None] ** 1.6
    a[..., 3] *= fade * args.strength
    out = Image.fromarray(a.astype(np.uint8), "RGBA").filter(
        ImageFilter.GaussianBlur(args.blur))
    out.save(args.out)
    print(f"wrote {args.out}")


def cmd_outline(args):
    try:
        import cv2
    except ImportError:
        raise SystemExit("outline needs OpenCV: ~/.aaaai-editor/bin/aaaai-editor-python -m pip install --user "
                         "opencv-python-headless")
    img = load(args.src)
    a = np.asarray(img)[..., 3]
    if args.scale != 1.0:   # trace at a higher resolution for smoother curves on small logos
        a = cv2.resize(a, None, fx=args.scale, fy=args.scale, interpolation=cv2.INTER_CUBIC)
    m = (a > args.thresh).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))   # drop single-pixel specks
    cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        raise SystemExit("no opaque pixels found (is the logo keyed? try `key` first)")
    hier = hier[0]
    k = 1.0 / args.scale
    shapes, dropped = [], 0
    min_area = args.min_area * args.scale * args.scale

    def poly(c):
        c = cv2.approxPolyDP(c, args.eps * args.scale, True)[:, 0, :].astype(float) * k
        return [[round(x, 2), round(y, 2)] for x, y in c]

    for i, c in enumerate(cs):
        if hier[i][3] != -1:            # holes are collected under their parent
            continue
        if cv2.contourArea(c) < min_area:
            dropped += 1
            continue
        holes, j = [], hier[i][2]
        while j != -1:
            if cv2.contourArea(cs[j]) >= min_area * 0.25:
                holes.append(poly(cs[j]))
            j = hier[j][0]
        shapes.append({"outer": poly(c), "holes": holes})
    out = {"w": img.width, "h": img.height, "shapes": shapes}
    with open(args.out, "w") as fh:
        json.dump(out, fh)
    pts = sum(len(s_["outer"]) + sum(len(h) for h in s_["holes"]) for s_ in shapes)
    print(f"wrote {args.out}: {len(shapes)} shapes, {sum(len(s_['holes']) for s_ in shapes)} holes, "
          f"{pts} points" + (f" ({dropped} specks dropped)" if dropped else ""))


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("key", help="alpha-key off a flat background")
    p.add_argument("src"); p.add_argument("out")
    p.add_argument("--bg", default="", help="r,g,b of the background; sampled if omitted")
    p.add_argument("--floor", type=float, default=0.10,
                   help="alpha below this is discarded — removes ambient glow blobs")
    p.add_argument("--crop", action="store_true", help="crop to the content bbox")
    p.set_defaults(f=cmd_key)

    p = sub.add_parser("bands", help="report row/column content bands")
    p.add_argument("src"); p.add_argument("--thresh", type=int, default=30)
    p.set_defaults(f=cmd_bands)

    p = sub.add_parser("split", help="split into two full-canvas layers")
    p.add_argument("src"); p.add_argument("--x", type=int, required=True)
    p.add_argument("--out", default="assets")
    p.set_defaults(f=cmd_split)

    p = sub.add_parser("strip", help="zero alpha below (or above) a row")
    p.add_argument("src"); p.add_argument("out")
    p.add_argument("--row", type=int, default=None)
    p.add_argument("--above", action="store_true")
    p.set_defaults(f=cmd_strip)

    p = sub.add_parser("letters", help="crop letterforms on a shared band")
    p.add_argument("src"); p.add_argument("--chars", required=True)
    p.add_argument("--out", default="assets")
    p.add_argument("--min-w", type=int, default=100)
    p.add_argument("--max-x", type=int, default=0)
    p.set_defaults(f=cmd_letters)

    p = sub.add_parser("slabs", help="brightness ramp for 3D extrusion")
    p.add_argument("src"); p.add_argument("--out", default="assets")
    p.add_argument("--prefix", default="slab")
    p.add_argument("--levels", type=int, default=9)
    p.add_argument("--width", type=int, default=1120)
    p.add_argument("--floor", type=float, default=0.18)
    p.add_argument("--near", type=float, default=0.40)
    p.add_argument("--tint", default="0.74,0.82,1.04")
    p.set_defaults(f=cmd_slabs)

    p = sub.add_parser("reflect", help="faded flipped copy for a floor reflection")
    p.add_argument("src"); p.add_argument("out")
    p.add_argument("--width", type=int, default=1120)
    p.add_argument("--strength", type=float, default=0.40)
    p.add_argument("--blur", type=float, default=3.0)
    p.set_defaults(f=cmd_reflect)

    p = sub.add_parser("outline", help="vector outlines (JSON) for a real 3D extrusion")
    p.add_argument("src"); p.add_argument("out")
    p.add_argument("--thresh", type=int, default=128, help="alpha cut-off")
    p.add_argument("--eps", type=float, default=0.6, help="simplification tolerance in px")
    p.add_argument("--scale", type=float, default=2.0, help="trace at this upscale for smoother curves")
    p.add_argument("--min-area", type=float, default=40.0, help="ignore blobs smaller than this (px²)")
    p.set_defaults(f=cmd_outline)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
