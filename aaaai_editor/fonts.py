"""字体准备：把可变字体固化成指定字重的静态实例，放进缓存字体目录。

drawtext 和 libass 都只会用可变字体的默认字重（Orbitron 默认是 Regular），
品牌要的 Black 900 必须先实例化。实例化用 fontTools；当前解释器没有就借用装了它的解释器。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

FONT_DIR = os.path.expanduser(os.path.join(os.environ.get("AAAAI_EDITOR_HOME") or "~/.aaaai-editor", "fonts"))

_SCRIPT = r'''
import sys
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
src, dst, wght, name = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
f = TTFont(src)
axes = {a.axisTag: a for a in f["fvar"].axes} if "fvar" in f else {}
loc = {}
if "wght" in axes:
    a = axes["wght"]
    loc["wght"] = max(a.minValue, min(a.maxValue, wght))
for tag, a in axes.items():
    loc.setdefault(tag, a.defaultValue)
inst = instancer.instantiateVariableFont(f, loc) if axes else f
nt = inst["name"]
for rec in list(nt.names):
    if rec.nameID in (16, 17, 21, 22, 25):
        nt.removeNames(nameID=rec.nameID)
for nid, val in ((1, name), (2, "Regular"), (4, name), (6, name.replace(" ", ""))):
    nt.setName(val, nid, 3, 1, 0x409)
    nt.setName(val, nid, 1, 0, 0)
if "OS/2" in inst:
    inst["OS/2"].usWeightClass = 400      # 静态实例当 Regular 用，避免 libass 再合成一次粗体
    inst["OS/2"].fsSelection = (inst["OS/2"].fsSelection & ~0b1100001) | 0b1000000
if "head" in inst:
    inst["head"].macStyle = 0
inst.save(dst)
'''


def _python_with_fonttools() -> str:
    for exe in (sys.executable, os.path.join(FONT_DIR, "..", "bin", "aaaai-editor-python"), "/opt/homebrew/bin/python3.12",
                "/usr/local/bin/python3.12", shutil.which("python3.12") or "",
                shutil.which("python3") or ""):
        if exe and os.path.isfile(exe):
            if subprocess.run([exe, "-c", "import fontTools"], capture_output=True).returncode == 0:
                return exe
    raise RuntimeError("固化可变字体需要 fontTools：python3 -m pip install --user fonttools")


def instance(src, wght: float, name: str) -> str:
    """返回静态实例路径（已存在就直接用）。name 是给 libass 找字体用的家族名。src 可给多个候选。"""
    cands = [os.path.expanduser(x) for x in (src if isinstance(src, list) else [src])]
    src = next((c for c in cands if os.path.isfile(c)), None)
    if not src:
        raise RuntimeError("找不到字体文件（重跑 install.sh 会自动下载开源字体）：%s" % "、".join(cands))
    os.makedirs(FONT_DIR, exist_ok=True)
    dst = os.path.join(FONT_DIR, "%s.ttf" % name.replace(" ", ""))
    if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return dst
    p = subprocess.run([_python_with_fonttools(), "-c", _SCRIPT, src, dst, str(wght), name],
                       capture_output=True, text=True)
    if p.returncode != 0 or not os.path.isfile(dst):
        raise RuntimeError("固化字体失败：%s" % (p.stderr or "")[-600:])
    return dst


def display(th: dict):
    """风格的展示字体 → (文件路径, libass 家族名)；没配置返回 (None, None)。"""
    d = th.get("display_font")
    if not d:
        return None, None
    return instance(d["file"], float(d.get("wght", 400)), d["name"]), d["name"]
