#!/usr/bin/env python3
"""Deterministic parallel frame renderer for code-authored motion graphics.

The scene is an HTML file that exposes `window.__render(frame)` and sets
`window.__ready = true`. This driver seeks by calling that function and captures
each frame, so nothing in the scene may depend on wall-clock time. `frame` may
be fractional (motion blur samples between frames), so scenes must compute
`t = frame / FPS` and never round the frame number for motion. Use
`Math.floor(frame)` only for things that should NOT move inside a frame (grain).

Modes:

  full render     --dur 35 --fps 60 --out frames/L            (JPEG sequence)
  straight to MP4 --dur 35 --fps 60 --video out/film.mp4 [--audio score.wav]
  motion preview  --dur 35 --preview --video tmp/preview.mp4 --audio score.wav
                  (half size, 30 fps, fast encode: judge motion and timing in
                   a minute or two before committing to the full render)
  spot check      --at 2.2,6.5,9.9   (renders only those timestamps)

Motion blur (--mblur):
  auto            frames whose content moved more than --mblur-thr since the
                  previous frame get N sub-frame samples averaged (forward
                  shutter [f, f+shutter), so a hard cut on a frame boundary is
                  never blended); slow and still frames stay single-sample
  scene           only inside the windows the scene declares (window.__mblur,
                  set by MG.blur() in mg-kit.js)
  a-b,c-d         only inside these time windows (seconds)
  A frame whose change is bigger than --cut-thr is treated as a hard cut and
  never blurred.

Speed: on a Mac the page is rasterised by the GPU through ANGLE/Metal (about
5x faster per worker than the SwiftShader software path, and WebGL runs on
the real GPU). Output is deterministic either way, but GPU and CPU differ by
sub-pixel anti-aliasing, so render a whole film with one backend — spot checks
included. --cpu forces the software path.

Pages are served from a throwaway localhost HTTP server rooted at the scene's
folder (--root to widen it), so ES modules (three.js) and fetch() (Lottie JSON)
work; file:// blocks both.
"""
import argparse
import base64
import functools
import http.server
import io
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from multiprocessing import Process

from playwright.sync_api import sync_playwright

BASE_ARGS = ["--force-device-scale-factor=1", "--hide-scrollbars",
             "--disable-lcd-text", "--font-render-hinting=none",
             "--force-color-profile=srgb", "--disable-gpu-vsync",
             "--disable-frame-rate-limit"]


def gpu_args():
    sysname = platform.system()
    if sysname == "Darwin":
        return ["--headless=new", "--use-angle=metal", "--enable-gpu",
                "--ignore-gpu-blocklist", "--enable-gpu-rasterization"]
    if sysname == "Windows":
        return ["--headless=new", "--use-angle=d3d11", "--enable-gpu",
                "--ignore-gpu-blocklist", "--enable-gpu-rasterization"]
    return []


def ffmpeg_bin():
    for c in (os.environ.get("AAAAI_EDITOR_FFMPEG"),
              "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
              "/usr/local/opt/ffmpeg-full/bin/ffmpeg"):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin():
    ff = ffmpeg_bin()
    p = os.path.join(os.path.dirname(ff), "ffprobe")
    return p if os.path.dirname(ff) and os.path.isfile(p) else (shutil.which("ffprobe") or "ffprobe")


# ---------------------------------------------------------------- http server
class _Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map,
                          **{".js": "text/javascript", ".mjs": "text/javascript",
                             ".json": "application/json", ".woff2": "font/woff2",
                             ".wasm": "application/wasm"})

    def log_message(self, *a):
        pass


class _Server(http.server.ThreadingHTTPServer):
    # the stdlib default backlog is 5: four browsers asking for scripts at once
    # overflow it, the refused <script> fails silently and the scene never boots
    request_queue_size = 128
    daemon_threads = True


def serve(root):
    """Start a localhost-only server for `root`; returns (base_url, server)."""
    handler = functools.partial(_Quiet, directory=root)
    srv = _Server(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d" % srv.server_address[1], srv


def scene_url(base, root, scene, w, h, fps, dur, extra):
    rel = os.path.relpath(os.path.abspath(scene), root).replace(os.sep, "/")
    q = f"w={w}&h={h}&fps={fps}&dur={dur}"
    if extra:
        q += "&" + extra.lstrip("&?")
    return f"{base}/{rel}?{q}"


# ---------------------------------------------------------------- motion blur
def parse_windows(spec):
    out = []
    for part in (spec or "").split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            out.append((float(a), float(b)))
    return out


def _small(jpg_bytes):
    """Tiny grey thumbnail for motion detection (JPEG draft decode is cheap)."""
    from PIL import Image
    import numpy as np
    im = Image.open(io.BytesIO(jpg_bytes))
    im.draft("L", (max(1, im.width // 8), max(1, im.height // 8)))
    return np.asarray(im.convert("L").resize((160, 90)), dtype=np.float32)


def _thumb(jpg_bytes):
    """Mid-size grey thumbnail: fine enough to see sub-frame stepping."""
    from PIL import Image
    import numpy as np
    im = Image.open(io.BytesIO(jpg_bytes))
    im.draft("L", (max(1, im.width // 4), max(1, im.height // 4)))
    return np.asarray(im.convert("L").resize((320, 180)), dtype=np.float32)


def _average(shots, quality):
    from PIL import Image
    import numpy as np
    acc = None
    for b in shots:
        a = np.asarray(Image.open(io.BytesIO(b)).convert("RGB"), dtype=np.float32)
        acc = a if acc is None else acc + a
    acc = np.clip(acc / len(shots) + 0.5, 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(acc).save(buf, "JPEG", quality=quality, subsampling=0)
    return buf.getvalue()


# ---------------------------------------------------------------- worker
def worker(url, w, h, fps, out_dir, frames, quality, wid, verbose, alpha,
           use_gpu, mblur, video, enc_args, stats_path):
    errors = []
    t0 = time.time()
    enc = None
    blurred = 0
    with sync_playwright() as pw:
        # transparent layers use the software path: the GPU capture is transparent
        # too, but its anti-aliased edges carry far fewer alpha levels (measured
        # 19 vs 75 on a rounded box), which shows as stair-steps over footage
        use_gpu = use_gpu and not alpha
        args = BASE_ARGS + (gpu_args() if use_gpu else [])
        browser = pw.chromium.launch(args=args)
        page = browser.new_page(viewport={"width": w, "height": h},
                                device_scale_factor=1)
        page.on("pageerror", lambda e: errors.append(str(e)))
        for attempt in range(3):     # a dropped request on a busy machine: reload rather than fail
            errors.clear()
            page.goto(url, wait_until="load")
            try:
                page.wait_for_function("window.__ready === true", timeout=20000 if attempt < 2 else 45000)
                break
            except Exception:
                if attempt == 2:
                    # A silent JS exception leaves __ready false and would otherwise
                    # produce a directory full of identical frames.
                    print(f"[w{wid}] scene never became ready. page errors: {errors[:3]}",
                          file=sys.stderr, flush=True)
                    browser.close()
                    raise SystemExit(2)
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(1200)          # let webfonts and images settle
        if wid == 0 and verbose:
            gl = page.evaluate("""(()=>{const c=document.createElement('canvas').getContext('webgl');
                if(!c) return 'no WebGL'; const d=c.getExtension('WEBGL_debug_renderer_info');
                return d ? c.getParameter(d.UNMASKED_RENDERER_WEBGL) : 'WebGL'})()""")
            print(f"  renderer: {'GPU' if use_gpu else 'CPU'} · {gl}", flush=True)

        scene_windows = page.evaluate("window.__mblur || []") or []   # MG.blur() in mg-kit.js

        cdp = page.context.new_cdp_session(page)
        if alpha:
            # Chromium composites the page onto this colour before capture;
            # zero alpha here is what actually makes the PNG transparent.
            cdp.send("Emulation.setDefaultBackgroundColorOverride",
                     {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        ext = "png" if alpha else "jpg"
        opts = ({"format": "png", "optimizeForSpeed": True} if alpha else
                {"format": "jpeg", "quality": quality, "optimizeForSpeed": True})
        sub_opts = {"format": "jpeg", "quality": 98, "optimizeForSpeed": True}

        def shot(f, o=opts):
            page.evaluate("(f)=>window.__render(f)", f)
            return base64.b64decode(cdp.send("Page.captureScreenshot", o)["data"])

        if video:
            enc = subprocess.Popen(
                [ffmpeg_bin(), "-y", "-v", "error", "-f", "image2pipe", "-c:v", "mjpeg",
                 "-framerate", str(fps), "-i", "-"] + enc_args + [video],
                stdin=subprocess.PIPE)

        mode = (mblur or {}).get("mode")
        windows = list((mblur or {}).get("windows") or [])
        if mode == "scene":
            windows = [(float(a), float(b)) for a, b in scene_windows]
        n_sub = (mblur or {}).get("samples", 8)
        shutter = (mblur or {}).get("shutter", 0.5)
        thr, cut_thr = (mblur or {}).get("thr", 1.2), (mblur or {}).get("cut", 30.0)
        max_sub, step_thr = (mblur or {}).get("max_samples", 64), (mblur or {}).get("step", 0.8)
        prev_small, prev_f, used = None, None, []

        for i, f in enumerate(frames):
            data = shot(f)
            if mode and not alpha:
                t = f / fps
                if mode == "auto":
                    if prev_f != f - 1:          # first frame of a chunk / spot check
                        prev_small = _small(shot(f - 1, sub_opts)) if f > 0 else None
                    cur = _small(data)
                    d = float(abs(cur - prev_small).mean()) if prev_small is not None else 0.0
                    want = thr < d < cut_thr
                    prev_small, prev_f = cur, f
                else:
                    want = any(a <= t < b for a, b in windows)
                if want:
                    # adaptive sampling: start with n_sub samples across the shutter and
                    # double (keeping the old ones) while neighbouring samples still differ
                    # enough to show as separate copies — fast whips need 32–64, drifts 8
                    n = n_sub
                    subs = {k / n: shot(f + k / n * shutter, sub_opts) for k in range(n)}
                    while n < max_sub:
                        keys = sorted(subs)
                        th = [_thumb(subs[k]) for k in keys]
                        step = max(float(abs(th[j + 1] - th[j]).mean()) for j in range(len(th) - 1))
                        if step <= step_thr:
                            break
                        n *= 2
                        for k in range(1, n, 2):
                            subs[k / n] = shot(f + k / n * shutter, sub_opts)
                    data = _average([subs[k] for k in sorted(subs)], quality)
                    blurred += 1
                    used.append(n)
            if enc:
                enc.stdin.write(data)
            else:
                with open(os.path.join(out_dir, f"f{f:05d}.{ext}"), "wb") as fh:
                    fh.write(data)
            if verbose and wid == 0 and (i + 1) % 100 == 0:
                el = time.time() - t0
                print(f"  w0 {i+1}/{len(frames)}  {el:.0f}s  {(i+1)/el:.2f} fps", flush=True)
        if errors:
            print(f"[w{wid}] page errors during render: {errors[:3]}",
                  file=sys.stderr, flush=True)
        browser.close()
    if enc:
        enc.stdin.close()
        enc.wait()
        if enc.returncode != 0:
            raise SystemExit(3)
    if stats_path:
        with open(stats_path, "w") as fh:
            fh.write("%d %d" % (blurred, max(used or [0])))


# ---------------------------------------------------------------- driver
def x264_args(fps, crf, preview):
    if preview:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p"]
    k = int(round(fps * 2))
    return ["-c:v", "libx264", "-profile:v", "high", "-level", "4.2", "-preset", "slow",
            "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-x264-params", f"keyint={k}:min-keyint={k}:scenecut=0:ref=4:bframes=3"]


def count_frames(path):
    n = subprocess.run([ffprobe_bin(), "-v", "error", "-count_packets", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", path],
                       capture_output=True, text=True).stdout.strip().strip(",").split(",")[0]
    return int(n) if n.isdigit() else 0


def render(scene, w, h, out_dir=None, fps=60, dur=30.0, extra="", quality=94,
           workers=0, at=None, verbose=True, alpha=False, use_gpu=True,
           mblur=None, video=None, audio=None, crf=17, preview=False, root=None):
    if not out_dir and not video:
        raise SystemExit("need --out (frame folder) or --video (mp4)")
    if alpha and video:
        raise SystemExit("--alpha writes a PNG folder: use --out, then encode.sh --alpha")
    if at and not out_dir:
        raise SystemExit("--at writes stills: use --out")
    root = os.path.abspath(root or os.path.dirname(os.path.abspath(scene)))
    base, srv = serve(root)
    url = scene_url(base, root, scene, w, h, fps, dur,
                    (extra + "&" if extra else "") + ("alpha=1" if alpha else ""))

    if at:
        frames = [int(round(float(x) * fps)) for x in at]
        workers = 1
        video = None
    else:
        frames = list(range(int(round(dur * fps))))
    if not workers:
        # measured on an 8-core M2: 4 browsers is the knee; more just queue on the GPU
        workers = max(1, min(4, (os.cpu_count() or 4) // 2))
    workers = max(1, min(workers, len(frames)))

    t0 = time.time()
    edges = [round(len(frames) * i / workers) for i in range(workers + 1)]
    chunks = [frames[edges[i]:edges[i + 1]] for i in range(workers)]   # contiguous slices

    tmp = None
    if video:
        os.makedirs(os.path.dirname(os.path.abspath(video)) or ".", exist_ok=True)
        tmp = os.path.abspath(video) + ".parts"
        os.makedirs(tmp, exist_ok=True)
    else:
        os.makedirs(out_dir, exist_ok=True)
    enc_args = x264_args(fps, crf, preview)

    procs, parts, stats = [], [], []
    for i, chunk in enumerate(chunks):
        if not chunk:
            continue
        part = os.path.join(tmp, "p%02d.mp4" % i) if tmp else None
        st = os.path.join(tmp or out_dir, ".mblur%02d" % i) if mblur else None
        parts.append(part)
        stats.append(st)
        p = Process(target=worker, args=(url, w, h, fps, out_dir, chunk, quality, i,
                                         verbose, alpha, use_gpu, mblur, part, enc_args, st))
        p.start()
        procs.append(p)
    for p in procs:
        p.join()
    srv.shutdown()
    ok = not any(p.exitcode for p in procs)
    for i, p in enumerate(procs):
        if p.exitcode:
            print(f"[w{i}] worker failed (exit {p.exitcode})", file=sys.stderr, flush=True)
    if video and ok:
        # every slice must hold exactly its frames — an encoder that silently drops
        # frames would otherwise produce a short film that "succeeded"
        for i, (part, chunk) in enumerate(zip(parts, [c for c in chunks if c])):
            n = count_frames(part) if os.path.isfile(part) else 0
            if n != len(chunk):
                print(f"[w{i}] slice has {n} frames, expected {len(chunk)} ({part})", file=sys.stderr, flush=True)
                ok = False

    blurred, peak = 0, 0
    for st in stats:
        if st and os.path.isfile(st):
            b_, p_ = (open(st).read() or "0 0").split()
            blurred, peak = blurred + int(b_), max(peak, int(p_))
            os.remove(st)

    if video and ok:
        # each worker encoded its own slice with identical settings and a closed
        # GOP, so the slices concatenate without re-encoding
        with open(os.path.join(tmp, "list.txt"), "w") as fh:
            for p in parts:
                fh.write("file '%s'\n" % os.path.basename(p))
        cmd = [ffmpeg_bin(), "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0",
               "-i", os.path.join(tmp, "list.txt")]
        if audio:
            # never let the soundtrack shorten the film: pad it with silence, cut it at the picture
            adur = subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio],
                                  capture_output=True, text=True).stdout.strip()
            vdur = len(frames) / fps
            if adur and float(adur) < vdur - 0.05:
                print(f"⚠ soundtrack is {float(adur):.2f}s but the film is {vdur:.2f}s — padded with silence "
                      f"(wrong or stale score file?)", file=sys.stderr, flush=True)
            cmd += ["-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", "apad",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", "%.4f" % vdur]
        else:
            cmd += ["-c", "copy"]
        subprocess.run(cmd + ["-movflags", "+faststart", video], check=True)
        done = count_frames(video)
        ok = done == len(frames)
        if not os.environ.get("MG_KEEP_PARTS"):
            shutil.rmtree(tmp, ignore_errors=True)
        where = video
    elif video:
        print(f"render failed; slices kept for inspection in {tmp}", file=sys.stderr, flush=True)
        done, where = 0, video
    else:
        ext = "png" if alpha else "jpg"
        done = len([x for x in os.listdir(out_dir) if x.endswith(f".{ext}")]) if out_dir else 0
        ok = ok and (at is not None or done >= len(frames))
        where = out_dir
    note = f", motion blur on {blurred} frames (up to {peak} samples)" if mblur else ""
    print(f"{w}x{h}@{fps}: {done}/{len(frames)} frames in {time.time()-t0:.0f}s "
          f"({workers} workers, {'GPU' if use_gpu and not alpha else 'CPU'}{note}) -> {where}", flush=True)
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, help="path to the scene HTML")
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--dur", type=float, default=30.0)
    ap.add_argument("--out", help="frame folder (JPEG sequence; PNG with --alpha)")
    ap.add_argument("--video", help="encode straight to this MP4 instead of a frame folder")
    ap.add_argument("--audio", help="with --video: mux this soundtrack")
    ap.add_argument("--crf", type=int, default=17)
    ap.add_argument("--preview", action="store_true",
                    help="fast motion preview: long side 960, 30 fps, quick encode (use with --video)")
    ap.add_argument("--workers", type=int, default=0, help="0 = auto")
    ap.add_argument("--quality", type=int, default=94)
    ap.add_argument("--cpu", action="store_true", help="software raster (SwiftShader) instead of GPU")
    ap.add_argument("--root", help="folder served to the page (default: the scene's folder)")
    ap.add_argument("--extra", default="",
                    help="extra query string passed to the scene, e.g. days=03&nf=ob")
    ap.add_argument("--at", default="",
                    help="comma-separated seconds for a spot check instead of a full render")
    ap.add_argument("--mblur", default="",
                    help="motion blur: 'auto', 'scene' (windows declared by the scene), or 'a-b,c-d' seconds")
    ap.add_argument("--mblur-samples", type=int, default=8, help="starting samples per blurred frame")
    ap.add_argument("--mblur-max", type=int, default=64, help="adaptive ceiling for very fast moves")
    ap.add_argument("--mblur-step", type=float, default=0.8,
                    help="refine while neighbouring samples differ by more than this (0-255, 320x180)")
    ap.add_argument("--shutter", type=float, default=0.5, help="fraction of a frame (0.5 = 180 degrees)")
    ap.add_argument("--mblur-thr", type=float, default=1.2,
                    help="auto: mean change (0-255, 160x90 thumbnail) above which a frame is blurred")
    ap.add_argument("--cut-thr", type=float, default=30.0,
                    help="change above this is a hard cut and is never blurred")
    ap.add_argument("--alpha", action="store_true",
                    help="capture transparent PNG frames instead of opaque JPEG — "
                         "for layers meant to be composited onto someone else's "
                         "footage. The scene must honour the alpha=1 query flag "
                         "(SKILL.md §6.7) by skipping its own background/glow.")
    a = ap.parse_args()
    w, h, fps, q = a.w, a.h, a.fps, a.quality
    if a.preview:
        k = 960.0 / max(w, h)
        w, h, fps, q = int(round(w * k)) & ~1, int(round(h * k)) & ~1, 30, 85
    mb = None
    if a.mblur:
        mode = a.mblur if a.mblur in ("auto", "scene") else "windows"
        mb = {"mode": mode, "windows": parse_windows(a.mblur) if mode == "windows" else [],
              "samples": a.mblur_samples, "shutter": a.shutter, "thr": a.mblur_thr, "cut": a.cut_thr,
              "max_samples": a.mblur_max, "step": a.mblur_step}
    ok = render(a.scene, w, h, a.out, fps, a.dur, a.extra, q, a.workers,
                [x for x in a.at.split(",") if x] or None, alpha=a.alpha,
                use_gpu=not a.cpu, mblur=mb, video=a.video, audio=a.audio,
                crf=a.crf, preview=a.preview, root=a.root)
    sys.exit(0 if ok else 1)
