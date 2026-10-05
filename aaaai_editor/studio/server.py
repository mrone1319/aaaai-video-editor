"""Studio 本机服务：只听 127.0.0.1、网址带随机通行码，只用 Python 内建模块（Mac／Windows 都能跑）。

界面（web/）只做两件事：读写剪辑表与字幕轨（一律经过 store.py，带版本检查），以及请引擎做事
（代理影片、字卡真样子、渲染一段、出片、体检）。界面自己不渲染任何东西，成片永远由同一个引擎出。

网址形如 http://127.0.0.1:<端口>/s/<通行码>/ ；没有通行码、或 Host 不对（防 DNS rebinding）一律 404。
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import platform
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .. import __version__, config, env, store

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
MAX_BODY = 20 * 1024 * 1024
STATE = config.path("studio.json")      # 正在跑的 Studio（让第二次启动直接沿用）


class Studio:
    def __init__(self, port: int = 0):
        self.token = secrets.token_urlsafe(18)
        self.projects: Dict[str, str] = {}          # id → 项目文件夹
        self.lock = threading.Lock()
        self.job: Optional[dict] = None             # 一次只跑一个渲染
        self.jobs: Dict[str, dict] = {}
        self.errors: list = []                      # 诊断报告用：最近的错误
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _handler(self))
        self.port = self.httpd.server_address[1]

    # ------------------------------------------------------------ 项目
    @staticmethod
    def pid(d: str) -> str:
        return hashlib.sha1(os.path.realpath(d).encode("utf-8")).hexdigest()[:10]

    def register(self, d: str) -> str:
        d = os.path.realpath(d)
        i = self.pid(d)
        self.projects[i] = d
        return i

    def scan(self) -> list:
        root = config.get("projects_dir") or ""
        out = []
        if root and os.path.isdir(root):
            for name in os.listdir(root):
                d = os.path.join(root, name)
                sb = os.path.join(d, "storyboard.json")
                if os.path.isfile(sb):
                    out.append(self._summary(self.register(d), d, sb))
        for i, d in list(self.projects.items()):   # 用 studio <路径> 直接打开、不在项目文件夹里的
            if not any(x["id"] == i for x in out) and os.path.isfile(os.path.join(d, "storyboard.json")):
                out.append(self._summary(i, d, os.path.join(d, "storyboard.json")))
        out.sort(key=lambda x: -x["mtime"])
        return out

    def _summary(self, i: str, d: str, sb_path: str) -> dict:
        thumb = None
        for c in ("out/cover_1080x1350.png", "out/cover_1080x1920.png", "out/cover_1920x1080.png"):
            if os.path.isfile(os.path.join(d, c)):
                thumb = "f/%s/%s" % (i, c)
                break
        try:
            sb = json.load(open(sb_path, encoding="utf-8"))
            src = os.path.normpath(os.path.join(d, sb.get("source", "")))
            has_src = os.path.isfile(src)
            n_ov = len(sb.get("overlays") or [])
        except (OSError, ValueError):
            has_src, n_ov = False, 0
        return {"id": i, "name": os.path.basename(d), "dir": d, "mtime": os.path.getmtime(sb_path),
                "thumb": thumb, "source_ok": has_src, "overlays": n_ov,
                "final": os.path.isfile(os.path.join(d, "out", "final.mp4"))}

    def sbp(self, i: str) -> str:
        d = self.projects.get(i)
        if not d:
            raise KeyError("没有这个项目")
        return os.path.join(d, "storyboard.json")

    def capp(self, i: str) -> str:
        from .. import captions
        sb = json.load(open(self.sbp(i), encoding="utf-8"))
        rel = (sb.get("captions") or {}).get("track") or captions.TRACK
        return os.path.join(self.projects[i], rel)

    # ------------------------------------------------------------ 打开一个项目
    def open(self, i: str) -> dict:
        from .. import captions, render, theme
        from ..timeline import Timeline
        sbp = self.sbp(i)
        raw, ver = store.read(sbp)
        d = self.projects[i]
        src = os.path.normpath(os.path.join(d, raw.get("source", "")))
        source_ok = os.path.isfile(src)
        capp = self.capp(i)
        cap_doc, cap_ver = (store.read(capp) if os.path.isfile(capp) else (None, ""))
        auto = None
        if cap_doc is None:   # 还没有手改字幕轨：先给界面看自动切好的句子，第一次改字时才产生字幕轨文件
            try:
                sb = render.load_storyboard(sbp)
                tr = os.path.join(d, sb["captions"].get("transcript", "work/transcript.json"))
                if os.path.isfile(tr):
                    segs = json.load(open(tr, encoding="utf-8"))["segments"]
                    auto, _ = captions.load_pieces(sb, segs, captions.fit(sb))
            except Exception as e:   # noqa: BLE001 — 自动字幕失败不影响打开项目
                self.note("自动字幕：%s" % e)
        out = raw.get("output") or {}
        fps = float(out.get("fps", 30))
        dur = Timeline([tuple(c) for c in raw.get("cuts") or []], fps).duration if raw.get("cuts") else 0.0
        styles = {}
        for name in theme.all_themes(d):
            try:
                t = theme.theme(name, d, None)
                styles[name] = {"accent": t.get("accent"), "desc": t.get("desc", "")}
            except Exception:   # noqa: BLE001
                pass
        proxy = None
        if source_ok:
            try:
                pp = render.proxy_path(sbp)
                proxy = self.rel_url(i, pp) if os.path.isfile(pp) else None
            except Exception as e:   # noqa: BLE001
                self.note("代理影片：%s" % e)
        final = os.path.join(d, "out", "final.mp4")
        return {"id": i, "name": os.path.basename(d), "dir": d, "storyboard": raw, "sb_version": ver,
                "captions": cap_doc, "cap_version": cap_ver, "captions_auto": auto,
                "duration": dur, "fps": fps, "W": int(out.get("width", 1080)), "H": int(out.get("height", 1920)),
                "styles": styles, "source_ok": source_ok, "proxy": proxy,
                "final": self.rel_url(i, final) if os.path.isfile(final) else None}

    def rel_url(self, i: str, path: str) -> str:
        return "f/%s/%s" % (i, os.path.relpath(path, self.projects[i]).replace(os.sep, "/"))

    def versions(self, i: str) -> dict:
        capp = self.capp(i)
        return {"sb_version": store.current_version(self.sbp(i)),
                "cap_version": store.current_version(capp) if os.path.isfile(capp) else ""}

    def save(self, body: dict) -> dict:
        i = body["p"]
        res = {}
        try:
            if "storyboard" in body:
                res["sb_version"] = store.write(self.sbp(i), body["storyboard"], expect=body.get("sb_expect") or "",
                                                source="studio")
            if "captions" in body and body["captions"] is not None:
                capp = self.capp(i)
                os.makedirs(os.path.dirname(capp), exist_ok=True)
                res["cap_version"] = store.write(capp, body["captions"], expect=body.get("cap_expect") or "",
                                                 source="studio")
        except store.Conflict as e:
            fresh = self.open(i)
            return {"conflict": True, "msg": str(e), "fresh": fresh, **res}
        return res

    # ------------------------------------------------------------ 逐字稿剪片：删一句／还原一句
    @staticmethod
    def recut(body: dict) -> dict:
        """在界面目前的剪辑表上（还没存）从 cuts 扣掉或补回原片区间，字卡／推近／配方／音效的成片时间跟着换算。
        规则与 tidy／hook 相同（引擎 edit._subtract、edit._remap 的做法）；落在被删区间里的卡片移到删除点。
        回传新的剪辑表，由界面放进复原纪录再存档。"""
        from .. import edit
        from ..timeline import Timeline
        sb = body["storyboard"]
        fps = float((sb.get("output") or {}).get("fps", 30))
        old_cuts = [(float(a), float(b)) for a, b in sb["cuts"]]
        old = Timeline(old_cuts, fps)
        st = sb.setdefault("studio", {})
        removed = [tuple(x) for x in st.get("removed") or []]
        if body.get("remove"):
            rm = [(float(a), float(b)) for a, b in body["remove"]]
            new_cuts = edit._subtract(old_cuts, rm)
            removed += rm
        else:
            add = [(float(a), float(b)) for a, b in body["restore"]]
            merged = sorted(old_cuts + add)
            new_cuts = []
            for a, b in merged:
                if new_cuts and a <= new_cuts[-1][1] + 1e-3:
                    new_cuts[-1] = (new_cuts[-1][0], max(new_cuts[-1][1], b))
                else:
                    new_cuts.append((a, b))
            removed = [r for r in removed if not any(abs(r[0] - x[0]) < 1e-3 and abs(r[1] - x[1]) < 1e-3 for x in add)]
        if not new_cuts:
            raise ValueError("至少要留一段画面")
        new = Timeline(new_cuts, fps)

        def m(t: float) -> float:
            src = old.to_source(t)
            hits = new.clip(src, src + 1e-3)
            if hits:
                return round(hits[0][0], 3)
            later = [a for a, _b in new.clip(src, 1e9)]   # 落在删掉的地方：移到删除点
            return round(later[0] if later else new.duration, 3)

        for key in ("overlays", "zooms", "recipes"):
            for it in sb.get(key) or []:
                if isinstance(it.get("t"), list) and len(it["t"]) == 2:
                    a, b = float(it["t"][0]), float(it["t"][1])
                    na = m(a)
                    nb = min(round(na + (b - a), 3), round(new.duration, 3))
                    it["t"] = [na, max(nb, round(na + 0.3, 3))]
                if isinstance(it.get("at"), (int, float)):
                    it["at"] = m(float(it["at"]))
                for sub in it.get("items") or []:
                    if isinstance(sub, dict) and isinstance(sub.get("at"), (int, float)):
                        sub["at"] = m(float(sub["at"]))
        for x in sb.get("sfx") or []:
            if isinstance(x, dict) and isinstance(x.get("t"), (int, float)):
                x["t"] = m(float(x["t"]))
        if isinstance(sb.get("cover"), dict) and isinstance(sb["cover"].get("at"), (int, float)):
            sb["cover"]["at"] = m(float(sb["cover"]["at"]))
        sb["cuts"] = [[round(a, 3), round(b, 3)] for a, b in new_cuts]
        st["removed"] = [[round(a, 3), round(b, 3)] for a, b in removed]
        if not st["removed"]:
            del st["removed"]
        if not st:
            del sb["studio"]
        return {"storyboard": sb, "duration": round(new.duration, 3), "saved": round(old.duration - new.duration, 3)}

    # ------------------------------------------------------------ 波形（原片时间，每格 0.05 秒）
    def peaks(self, i: str) -> dict:
        from .. import audio, render
        sb = render.load_storyboard(self.sbp(i))
        e = audio.envelope(sb["source"])
        step = max(1, int(round(0.05 / audio.HOP)))
        vals = []
        for k in range(0, len(e.db), step):
            v = max(e.db[k:k + step])
            vals.append(round(max(0.0, min(1.0, (v - e.floor) / max(6.0, e.loud + 6.0 - e.floor))), 3))
        return {"hop": step * audio.HOP, "v": vals}

    # ------------------------------------------------------------ 字卡真样子
    def card(self, body: dict) -> dict:
        from .. import cardpics
        png = cardpics.card_png(self.sbp(body["p"]), body["overlay"], int(body.get("height", 960)))
        return {"url": self.rel_url(body["p"], png)}

    # ------------------------------------------------------------ 体检
    def check(self, i: str) -> dict:
        from .. import captions, checks, loud, render
        from ..timeline import Timeline
        sbp = self.sbp(i)
        sb = render.load_storyboard(sbp)
        tl = Timeline([tuple(c) for c in sb["cuts"]], sb["output"]["fps"])
        items = []
        cap = sb["captions"]
        tr = os.path.join(sb["_base"], cap.get("transcript", "work/transcript.json"))
        if cap.get("enabled") and os.path.isfile(tr):
            segs = json.load(open(tr, encoding="utf-8"))["segments"]
            pcs, _ = captions.load_pieces(sb, segs, captions.fit(sb))
            events = captions.to_events(pcs, tl)
            for x in checks.energy_items(sb, tl, events):
                if "src" in x:
                    t = None
                    acc = 0.0
                    for a, b in tl.cuts:   # 剪点：原片时间 → 成片时间
                        if a - 0.05 <= x["src"] <= b + 0.05:
                            t = acc + max(0.0, min(b - a, x["src"] - a))
                            break
                        acc += b - a
                    x["t"] = t
                items.append(x)
            W, H = int(sb["output"]["width"]), int(sb["output"]["height"])
            for txt in captions.too_long(pcs, cap, W, H):
                ev = next((e for e in events if e[2] == txt), None)
                items.append({"level": "problem", "kind": "long", "t": ev[0] if ev else None, "text": txt,
                              "msg": "这句字幕太长、放不进一行：「%s」（在标点处拆成两句）" % txt})
        else:
            items.append({"level": "note", "kind": "nocap", "msg": "没有字幕或没有转录文件，跳过对时检查"})
        if not sb.get("avoid_face", True):
            items.append({"level": "note", "kind": "face", "msg": "这支片关掉了「字卡避开脸」（avoid_face: false），没检查字卡压脸"})
        if sb.get("avoid_face", True) and sb["overlays"]:   # 字卡压到脸：和出片时同一套判定（overlays.face_lift）
            try:
                import contextlib
                import io
                from .. import faces, overlays, schema, theme
                W, H = int(sb["output"]["width"]), int(sb["output"]["height"])
                fc = faces.track(sb, tl, W, H)
                th = theme.theme(sb.get("style"), sb["_base"], sb.get("brand"))
                for ov in sb["overlays"]:
                    if not isinstance(ov.get("t"), list):
                        continue
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        overlays.face_lift(dict(ov), th, W, H, float(sb["output"]["fps"]), fc)
                    msg = buf.getvalue().strip()
                    if msg:
                        items.append({"level": "problem" if msg.startswith("⚠") else "note", "kind": "face",
                                      "t": float(ov["t"][0]),
                                      "msg": msg.lstrip("⚠️🙂 ").replace("已挪到最上面", "出片时会挪到最上面")
                                      .replace("的%s卡片" % ov.get("type"), "的%s" % schema.CARDS.get(ov.get("type"), (ov.get("type"),))[0])})
            except Exception as e:   # noqa: BLE001
                items.append({"level": "note", "kind": "face", "msg": "没检查到字卡与脸的位置：%s" % e})
        final = os.path.join(sb["_base"], "out", "final.mp4")
        if os.path.isfile(final):
            if os.path.getmtime(final) < os.path.getmtime(sbp):
                items.append({"level": "note", "kind": "stale", "msg": "成片比剪辑表旧：改过之后还没重新出片"})
            try:
                lu, tp = loud.measure(final)
                ok = abs(lu - float(sb["loudness"])) <= 0.5 and tp <= -0.9
                items.append({"level": "ok" if ok else "problem", "kind": "loud",
                              "msg": "成片响度 %.1f LUFS、真峰值 %.1f dBTP%s" % (lu, tp, "" if ok else "（目标 %.0f LUFS、≤ −1 dBTP）" % float(sb["loudness"]))})
            except Exception as e:   # noqa: BLE001
                items.append({"level": "note", "kind": "loud", "msg": "量不到成片响度：%s" % e})
        return {"items": items}

    # ------------------------------------------------------------ 渲染工作（一次一个，可取消，有真实进度）
    def start_job(self, body: dict) -> dict:
        with self.lock:
            if self.job and self.job["status"] == "running":
                return {"busy": True, "msg": "正在%s，等它完成或先取消" % self.job["label"]}
            i, kind = body["p"], body["kind"]
            jid = secrets.token_hex(6)
            sbp = self.sbp(i)
            job = {"id": jid, "p": i, "kind": kind, "status": "running", "progress": 0.0, "stage": "准备中",
                   "log": [], "result": None, "started": time.time(), "proc": None}
            if kind == "range":
                a, b = float(body["a"]), float(body["b"])
                job.update(label="渲染 %.1f–%.1f 秒" % (a, b), a=a, b=b,
                           cmd=["render", sbp, "--range", "%.3f" % a, "%.3f" % b], total=b - a, t0=a)
            elif kind == "final":
                job.update(label="出片", cmd=["render", sbp], total=float(body.get("duration") or 1), t0=0.0)
            elif kind == "proxy":
                job.update(label="准备播放用的影片", total=1.0, t0=0.0)
            else:
                raise ValueError("不认识的工作：%s" % kind)
            self.job = job
            self.jobs[jid] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return {"job": jid}

    def _run(self, job: dict) -> None:
        try:
            if job["kind"] == "proxy":
                from .. import render
                job["stage"] = "转成播放用的低清影片（只需一次）"
                p = render.proxy_source(self.sbp(job["p"]))
                job["result"] = self.rel_url(job["p"], p)
                job["progress"], job["status"] = 1.0, "done"
                return
            pdir = tempfile.mkdtemp(prefix="aaaai-progress-")
            envv = dict(os.environ, AAAAI_PROGRESS_DIR=pdir, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "aaaai_editor"] + job["cmd"], cwd=root,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                    errors="replace", env=envv, **kw)
            job["proc"] = proc
            job["stage"] = "渲染画面"
            reader = threading.Thread(target=self._read_out, args=(job, proc), daemon=True)
            reader.start()
            while proc.poll() is None:
                job["progress"] = max(job["progress"], self._progress(pdir, job))
                if job["progress"] >= 0.97 and job["kind"] == "final":
                    job["stage"] = "混音、响度、封装"
                time.sleep(0.4)
            reader.join(timeout=2)
            if job["status"] == "cancelled":
                return
            if proc.returncode != 0:
                job["status"] = "error"
                job["stage"] = "失败"
                self.note("%s 失败：%s" % (job["label"], "\n".join(job["log"][-8:])))
                return
            m = None
            for line in job["log"]:
                m = re.search(r"[：:]\s*(/.+?\.mp4|[A-Za-z]:\\.+?\.mp4)\s*$", line) or m
            if m:
                job["result"] = self.rel_url(job["p"], m.group(1))
            job["progress"], job["status"], job["stage"] = 1.0, "done", "完成"
        except Exception as e:   # noqa: BLE001
            job["status"], job["stage"] = "error", str(e)
            self.note("%s：%s" % (job.get("label"), traceback.format_exc()[-1200:]))

    @staticmethod
    def _read_out(job: dict, proc) -> None:
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                job["log"].append(line)
                job["log"] = job["log"][-200:]

    @staticmethod
    def _progress(pdir: str, job: dict) -> float:
        best = 0.0
        try:
            for f in os.listdir(pdir):
                m = re.match(r"p_(\d+)\.txt$", f)
                if not m:
                    continue
                seg0 = int(m.group(1)) / 1000.0
                us = 0
                with open(os.path.join(pdir, f), encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if line.startswith("out_time_us="):
                            try:
                                us = int(line.split("=", 1)[1])
                            except ValueError:
                                pass
                done = seg0 + us / 1e6 - job["t0"]
                best = max(best, done / max(0.01, job["total"]))
        except OSError:
            pass
        return min(0.97, best * 0.97)

    def cancel(self, jid: str) -> dict:
        job = self.jobs.get(jid)
        if not job or job["status"] != "running":
            return {"ok": False}
        job["status"], job["stage"] = "cancelled", "已取消"
        p = job.get("proc")
        if p and p.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                else:
                    os.killpg(p.pid, signal.SIGTERM)
            except OSError:
                pass
        return {"ok": True}

    def job_view(self, jid: str) -> dict:
        j = self.jobs.get(jid)
        if not j:
            return {"status": "gone"}
        return {k: j.get(k) for k in ("id", "kind", "label", "status", "progress", "stage", "result")} | \
               {"elapsed": round(time.time() - j["started"], 1), "log": j["log"][-6:]}

    # ------------------------------------------------------------ 诊断
    def note(self, msg: str) -> None:
        self.errors.append("%s  %s" % (time.strftime("%H:%M:%S"), msg))
        self.errors = self.errors[-50:]

    def diag(self, i: Optional[str]) -> dict:
        lines = ["aaaai-editor %s · Studio 诊断报告 · %s" % (__version__, time.strftime("%Y-%m-%d %H:%M:%S")),
                 "系统：%s %s · Python %s" % (platform.system(), platform.release(), platform.python_version())]
        try:
            lines.append("ffmpeg：%s" % env.ffmpeg())
        except Exception as e:   # noqa: BLE001
            lines.append("ffmpeg：找不到（%s）" % e)
        if i and i in self.projects:
            d = self.projects[i]
            try:
                raw, ver = store.read(self.sbp(i))
                lines.append("项目：%s · 剪辑表版本 %s · %d 段剪辑 · %d 张字卡 · %d 个配方 · 风格 %s"
                             % (os.path.basename(d), ver, len(raw.get("cuts") or []), len(raw.get("overlays") or []),
                                len(raw.get("recipes") or []), raw.get("style")))
                lines.append("原片：%s" % ("在" if os.path.isfile(os.path.normpath(os.path.join(d, raw.get("source", "")))) else "不在"))
            except Exception as e:   # noqa: BLE001
                lines.append("剪辑表读不了：%s" % e)
            log = os.path.join(d, "work", "edits.log")
            if os.path.isfile(log):
                lines.append("最近修改：")
                lines += ["  " + x for x in open(log, encoding="utf-8").read().splitlines()[-8:]]
        lines.append("最近错误：" + ("无" if not self.errors else ""))
        lines += ["  " + x for x in self.errors[-15:]]
        text = "\n".join(lines)
        path = None
        if i and i in self.projects:
            path = os.path.join(self.projects[i], "work", "studio", "diag-%s.txt" % time.strftime("%Y%m%d-%H%M%S"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w", encoding="utf-8").write(text)
        return {"text": text, "path": path}

    # ------------------------------------------------------------ 启动
    @property
    def url(self) -> str:
        return "http://127.0.0.1:%d/s/%s/" % (self.port, self.token)

    def serve(self) -> None:
        try:
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            json.dump({"url": self.url, "pid": os.getpid(), "port": self.port}, open(STATE, "w"))
        except OSError:
            pass
        try:
            self.httpd.serve_forever(poll_interval=0.3)
        finally:
            try:
                if json.load(open(STATE)).get("pid") == os.getpid():
                    os.remove(STATE)
            except (OSError, ValueError):
                pass


def running_url() -> Optional[str]:
    """已经有 Studio 在跑就回传它的网址（第二次启动直接沿用，不开第二个）。"""
    try:
        st = json.load(open(STATE))
        os.kill(int(st["pid"]), 0)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    import urllib.request
    try:
        with urllib.request.urlopen(st["url"] + "api/ping", timeout=1.5) as r:
            if r.status == 200:
                return st["url"]
    except OSError:
        return None
    return None


# ---------------------------------------------------------------- HTTP
def _handler(studio: Studio):
    class H(BaseHTTPRequestHandler):
        server_version = "aaaai-studio"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):   # 安静：不往终端机灌请求纪录
            pass

        # -- 共用 --
        def _ok_host(self) -> bool:
            h = (self.headers.get("Host") or "").split(":")[0]
            return h in ("127.0.0.1", "localhost")

        def _route(self):
            u = urlparse(self.path)
            pre = "/s/%s/" % studio.token
            if not self._ok_host() or not u.path.startswith(pre):
                return None, None
            return u.path[len(pre):], parse_qs(u.query)

        def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8",
                  extra: Optional[dict] = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _404(self):
            self._send(404, b"not found", "text/plain")

        def _file(self, path: str):
            """支持 Range（影片能拖动播放）。"""
            size = os.path.getsize(path)
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            rng = self.headers.get("Range")
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)", rng)
                a = int(m.group(1)) if m and m.group(1) else 0
                b = int(m.group(2)) if m and m.group(2) else size - 1
                b = min(b, size - 1)
                if a > b:
                    self._send(416, b"", "text/plain", {"Content-Range": "bytes */%d" % size})
                    return
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Range", "bytes %d-%d/%d" % (a, b, size))
                self.send_header("Content-Length", str(b - a + 1))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(path, "rb") as f:
                    f.seek(a)
                    left = b - a + 1
                    while left > 0:
                        chunk = f.read(min(1 << 20, left))
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        left -= len(chunk)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return

        # -- GET --
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            r, q = self._route()
            if r is None:
                return self._404()
            try:
                if r in ("", "index.html"):
                    return self._file(os.path.join(WEB, "index.html"))
                if r in ("app.js", "app.css"):
                    return self._file(os.path.join(WEB, r))
                if r.startswith("fonts/"):
                    from .. import fonts
                    name = os.path.basename(unquote(r[6:]))
                    p = os.path.join(fonts.FONT_DIR, name)
                    if name.lower().endswith((".ttf", ".otf")) and os.path.isfile(p):
                        return self._file(p)
                    return self._404()
                if r.startswith("f/"):   # 项目里的文件：只给项目文件夹之内的
                    parts = unquote(r[2:]).split("/", 1)
                    if len(parts) != 2 or parts[0] not in studio.projects:
                        return self._404()
                    base = os.path.realpath(studio.projects[parts[0]])
                    p = os.path.realpath(os.path.join(base, parts[1]))
                    if not (p == base or p.startswith(base + os.sep)) or not os.path.isfile(p):
                        return self._404()
                    return self._file(p)
                if r == "api/ping":
                    return self._json({"ok": True, "version": __version__})
                if r == "api/projects":
                    return self._json({"projects": studio.scan(), "projects_dir": config.get("projects_dir")})
                if r == "api/open":
                    return self._json(studio.open(q["p"][0]))
                if r == "api/version":
                    return self._json(studio.versions(q["p"][0]))
                if r == "api/schema":
                    from .. import schema
                    return self._json(schema.as_dict())
                if r == "api/peaks":
                    return self._json(studio.peaks(q["p"][0]))
                if r == "api/job":
                    return self._json(studio.job_view(q["id"][0]))
                return self._404()
            except KeyError as e:
                return self._json({"error": "找不到：%s" % e}, 404)
            except Exception as e:   # noqa: BLE001
                studio.note("GET %s：%s" % (r, traceback.format_exc()[-800:]))
                return self._json({"error": str(e)}, 500)

        # -- POST --
        def do_POST(self):
            r, _q = self._route()
            if r is None:
                return self._404()
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._json({"error": "内容太大"}, 413)
            try:
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                if r == "api/save":
                    return self._json(studio.save(body))
                if r == "api/recut":
                    return self._json(studio.recut(body))
                if r == "api/card":
                    return self._json(studio.card(body))
                if r == "api/check":
                    return self._json(studio.check(body["p"]))
                if r == "api/render":
                    return self._json(studio.start_job(body))
                if r == "api/cancel":
                    return self._json(studio.cancel(body["id"]))
                if r == "api/diag":
                    return self._json(studio.diag(body.get("p")))
                return self._404()
            except KeyError as e:
                return self._json({"error": "找不到：%s" % e}, 404)
            except Exception as e:   # noqa: BLE001
                studio.note("POST %s：%s" % (r, traceback.format_exc()[-800:]))
                return self._json({"error": str(e)}, 500)
    return H
