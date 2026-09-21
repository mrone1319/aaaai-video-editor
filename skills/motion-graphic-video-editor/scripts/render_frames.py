#!/usr/bin/env python3
"""Deterministic parallel frame renderer for code-authored motion graphics.

The scene is an HTML file that exposes `window.__render(frame)` and sets
`window.__ready = true`. This driver seeks by calling that function and captures
each frame, so nothing in the scene may depend on wall-clock time.

Two modes:

  full render   --dur 35 --fps 60 --out frames/L
  spot check    --at 2.2,6.5,9.9   (renders only those timestamps)

Always spot-check before committing to a full render: a full pass is minutes to
tens of minutes, a spot check is seconds, and almost every visual bug shows up
in a single frame.

Speed notes: style updates cost almost nothing (hundreds of fps) — the entire
cost is rasterisation. If a render is slow, reduce blur passes in the scene
rather than simplifying the JavaScript. Capturing through the CDP endpoint with
optimizeForSpeed is noticeably faster than the high-level screenshot API.
"""
import argparse
import base64
import os
import sys
import time
from multiprocessing import Process

from playwright.sync_api import sync_playwright


def _scene_url(scene, w, h, fps, dur, extra):
    scene = os.path.abspath(scene)
    q = f"w={w}&h={h}&fps={fps}&dur={dur}"
    if extra:
        q += "&" + extra.lstrip("&?")
    return f"file://{scene}?{q}"


def worker(scene, w, h, fps, dur, extra, out_dir, frames, quality, wid, verbose,
           alpha=False):
    """Render an explicit list of frame indices."""
    if alpha:
        # The scene reads this flag (location.search) and must skip its own
        # background/glow layers when set — see SKILL.md §6.7. Without that,
        # the transparency below has nothing to show through.
        extra = (extra + "&" if extra else "") + "alpha=1"
    url = _scene_url(scene, w, h, fps, dur, extra)
    errors = []
    t0 = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=[
            "--force-device-scale-factor=1", "--hide-scrollbars",
            "--disable-lcd-text", "--font-render-hinting=none",
            "--force-color-profile=srgb", "--disable-gpu-vsync",
            "--disable-frame-rate-limit"])
        page = browser.new_page(viewport={"width": w, "height": h},
                                device_scale_factor=1)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url, wait_until="load")
        try:
            page.wait_for_function("window.__ready === true", timeout=45000)
        except Exception:
            # A silent JS exception leaves __ready false and would otherwise
            # produce a directory full of identical frames.
            print(f"[w{wid}] scene never became ready. page errors: {errors[:3]}",
                  file=sys.stderr, flush=True)
            browser.close()
            raise SystemExit(2)
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(1200)          # let webfonts and images settle

        cdp = page.context.new_cdp_session(page)
        if alpha:
            # Chromium composites the page onto this colour before capture;
            # zero alpha here is what actually makes the PNG transparent —
            # the page's own CSS background being "none" is necessary but
            # not sufficient on its own.
            cdp.send("Emulation.setDefaultBackgroundColorOverride",
                     {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        ext = "png" if alpha else "jpg"
        shot_opts = ({"format": "png", "optimizeForSpeed": True} if alpha else
                     {"format": "jpeg", "quality": quality, "optimizeForSpeed": True})
        for i, f in enumerate(frames):
            page.evaluate("(f)=>window.__render(f)", f)
            shot = cdp.send("Page.captureScreenshot", shot_opts)
            with open(os.path.join(out_dir, f"f{f:05d}.{ext}"), "wb") as fh:
                fh.write(base64.b64decode(shot["data"]))
            if verbose and wid == 0 and (i + 1) % 100 == 0:
                el = time.time() - t0
                print(f"  w0 {i+1}/{len(frames)}  {el:.0f}s  {(i+1)/el:.2f} fps",
                      flush=True)
        if errors:
            print(f"[w{wid}] page errors during render: {errors[:3]}",
                  file=sys.stderr, flush=True)
        browser.close()


def render(scene, w, h, out_dir, fps=60, dur=30.0, extra="", quality=94,
           workers=2, at=None, verbose=True, alpha=False):
    os.makedirs(out_dir, exist_ok=True)

    if at:
        frames = [int(round(float(x) * fps)) for x in at]
        workers = 1
    else:
        frames = list(range(int(round(dur * fps))))

    t0 = time.time()
    chunks = [frames[i::workers] for i in range(workers)] if workers > 1 else [frames]
    # contiguous slices keep each browser's animation state local, which is
    # slightly kinder to the rasteriser than interleaving
    if workers > 1:
        edges = [round(len(frames) * i / workers) for i in range(workers + 1)]
        chunks = [frames[edges[i]:edges[i + 1]] for i in range(workers)]

    procs = []
    for i, chunk in enumerate(chunks):
        if not chunk:
            continue
        p = Process(target=worker, args=(scene, w, h, fps, dur, extra, out_dir,
                                        chunk, quality, i, verbose, alpha))
        p.start()
        procs.append(p)
    for p in procs:
        p.join()

    ext = "png" if alpha else "jpg"
    done = len([x for x in os.listdir(out_dir) if x.endswith(f".{ext}")])
    print(f"{w}x{h}: {done}/{len(frames)} frames in {time.time()-t0:.0f}s",
          flush=True)
    return done == len(frames)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, help="path to the scene HTML")
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--dur", type=float, default=30.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--quality", type=int, default=94)
    ap.add_argument("--extra", default="",
                    help="extra query string passed to the scene, e.g. days=03&nf=ob")
    ap.add_argument("--at", default="",
                    help="comma-separated seconds for a spot check instead of a full render")
    ap.add_argument("--alpha", action="store_true",
                    help="capture transparent PNG frames instead of opaque JPEG — "
                         "for layers meant to be composited onto someone else's "
                         "footage. The scene must honour the alpha=1 query flag "
                         "(SKILL.md §6.7) by skipping its own background/glow.")
    a = ap.parse_args()
    ok = render(a.scene, a.w, a.h, a.out, a.fps, a.dur, a.extra, a.quality,
                a.workers, [x for x in a.at.split(",") if x] or None,
                alpha=a.alpha)
    sys.exit(0 if ok else 1)
