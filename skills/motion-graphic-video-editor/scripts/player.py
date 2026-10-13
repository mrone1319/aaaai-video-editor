#!/usr/bin/env python3
"""Serve a scene with the development player (assets/player.html): real-time
playback, scrubbing, frame stepping, scene markers and the soundtrack in sync.

  $PY player.py --scene scene.html [--root .] [--audio out/score.wav] [--dur 24] [--w 1920 --h 1080]

Prints a localhost URL (and opens it with --open). Keeps serving until Ctrl-C.
In Claude Code, start it with the Bash tool's background mode and open the URL in
the Browser pane. Paths for --scene/--audio are relative to --root (default: the
scene's folder). The player itself is served from the skill at /__mg/.
"""
import argparse
import functools
import http.server
import os
import subprocess
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.normpath(os.path.join(HERE, "..", "assets"))
sys.path.insert(0, HERE)
from render_frames import _Quiet, _Server  # noqa: E402


class Handler(_Quiet):
    def translate_path(self, path):
        p = urllib.parse.urlparse(path).path
        if p.startswith("/__mg/"):
            return os.path.join(ASSETS, os.path.normpath(urllib.parse.unquote(p[len("/__mg/"):])).lstrip(os.sep))
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # edits show up on reload
        super().end_headers()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True)
    ap.add_argument("--root")
    ap.add_argument("--audio")
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--dur", type=float, help="film length (default: from the scene table, else 30)")
    ap.add_argument("--extra", default="", help="extra query string for the scene")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--open", action="store_true", help="open in the default browser")
    a = ap.parse_args()
    root = os.path.abspath(a.root or os.path.dirname(os.path.abspath(a.scene)))
    rel = lambda p: "/" + os.path.relpath(os.path.abspath(p), root).replace(os.sep, "/")
    srv = _Server(("127.0.0.1", a.port), functools.partial(Handler, directory=root))
    q = {"scene": rel(a.scene), "w": a.w, "h": a.h, "fps": a.fps}
    if a.dur:
        q["dur"] = a.dur
    if a.audio:
        q["audio"] = rel(a.audio)
    if a.extra:
        q["extra"] = a.extra
    url = "http://127.0.0.1:%d/__mg/player.html?%s" % (srv.server_address[1], urllib.parse.urlencode(q))
    print("MG player: " + url, flush=True)
    if a.open:
        subprocess.run(["open" if sys.platform == "darwin" else ("start" if os.name == "nt" else "xdg-open"), url],
                       shell=os.name == "nt")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
