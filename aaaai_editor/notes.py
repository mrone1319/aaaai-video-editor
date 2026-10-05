"""时间点留言：用户在 Studio 某个时间点（或某一段、某张字卡）留言，可以标「请 Claude 处理」。

存在 项目/work/notes.json，一律经过存取口（store.py），所以 Studio、对话里的 Claude、MCP 同时读写也不会互相覆盖。
格式：{"version": 1, "notes": [{"id", "t", "a", "b", "ref", "text", "to": "claude"|"me", "status": "open"|"done",
                               "reply", "created", "updated"}]}
时间都是成片时间（秒）。
"""
from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple

from . import store

REL = os.path.join("work", "notes.json")


def path(project_dir: str) -> str:
    return os.path.join(project_dir, REL)


def project_of(target: str) -> str:
    """项目文件夹或其中的 storyboard.json 都可以。"""
    t = os.path.abspath(os.path.expanduser(target))
    return os.path.dirname(t) if os.path.isfile(t) else t


def load(project_dir: str) -> Tuple[dict, str]:
    p = path(project_dir)
    if not os.path.isfile(p):
        return {"version": 1, "notes": []}, ""
    return store.read(p)


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def add(project_dir: str, text: str, t: float, to: str = "claude", a: Optional[float] = None,
        b: Optional[float] = None, ref: Optional[dict] = None, source: str = "studio") -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("留言是空的")
    made = {}

    def fn(doc):
        doc = doc or {"version": 1, "notes": []}
        doc.setdefault("notes", [])
        nid = max([int(n.get("id", 0)) for n in doc["notes"]] + [0]) + 1
        n = {"id": nid, "t": round(float(t), 2), "text": text[:2000], "to": "claude" if to == "claude" else "me",
             "status": "open", "created": _now()}
        if a is not None and b is not None:
            n["a"], n["b"] = round(float(a), 2), round(float(b), 2)
        if ref:
            n["ref"] = {k: ref[k] for k in ("k", "i", "label") if k in ref}
        doc["notes"].append(n)
        made.update(n)
        return doc

    _update(project_dir, fn, source)
    return made


def change(project_dir: str, nid: int, source: str = "studio", **kw) -> dict:
    """改一条留言：status、reply、text、to；delete=True 就删掉。"""
    hit = {}

    def fn(doc):
        doc = doc or {"version": 1, "notes": []}
        for k, n in enumerate(doc.get("notes", [])):
            if int(n.get("id", -1)) == int(nid):
                if kw.get("delete"):
                    doc["notes"].pop(k)
                else:
                    for key in ("status", "reply", "text", "to"):
                        if kw.get(key) is not None:
                            n[key] = kw[key]
                    n["updated"] = _now()
                    hit.update(n)
                return doc
        raise KeyError("没有第 %s 条留言" % nid)

    _update(project_dir, fn, source)
    return hit


def _update(project_dir: str, fn, source: str) -> str:
    p = path(project_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.isfile(p):
        store.write(p, {"version": 1, "notes": []}, expect="", source=source)
    return store.update(p, fn, source=source)


def pending(project_dir: str) -> List[dict]:
    doc, _v = load(project_dir)
    return [n for n in doc.get("notes", []) if n.get("to") == "claude" and n.get("status") == "open"]


def fmt_time(t: float) -> str:
    m = int(t // 60)
    return "%02d:%05.2f" % (m, t - m * 60)


def describe(n: dict) -> str:
    rng = "成片 %s–%s" % (fmt_time(n["a"]), fmt_time(n["b"])) if "a" in n else "成片 %s" % fmt_time(n["t"])
    ref = "（%s）" % n["ref"]["label"] if n.get("ref", {}).get("label") else ""
    st = "✅" if n.get("status") == "done" else ("🙋" if n.get("to") == "claude" else "📝")
    s = "%s #%d %s%s：%s" % (st, n["id"], rng, ref, n["text"])
    if n.get("reply"):
        s += "\n     ↳ 回覆：%s" % n["reply"]
    return s
