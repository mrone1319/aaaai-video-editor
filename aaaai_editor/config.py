"""用户设置与数据位置（与程序分开：更新程序绝不覆盖用户的东西）。

~/.aaaai-editor/                 （可用环境变量 AAAAI_EDITOR_HOME 改）
  config.json             项目目录、当前频道档案、品牌档案库位置
  authorized.json         受限风格的授权确认（mrone © MR ONE、otg © OTG 社群）
  themes/  profiles/      用户自己的风格与频道档案
  glossary.json           用户自己的误听词表
  fonts/  models/         下载的开源字体、whisper 模型
  bin/aaaai-editor  app/         命令入口、程序本体（安装器维护）
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

HOME = os.path.expanduser(os.environ.get("AAAAI_EDITOR_HOME") or "~/.aaaai-editor")
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "projects_dir": "~/Movies/aaaai-editor",          # Finder 侧栏的「影片」里
    "exports_dir": "~/Movies/aaaai-editor/成品",       # 成片／封面自动复制一份到这里（按项目名命名）；设空字串就不复制
    "profile": "",
    "handle": "",          # 封面上印的账号名，例：@yourname
    "brand_dir": "~/Documents/brand-profiles",
    "history_dir": "~/Documents/content-history",
}


def path(*p: str) -> str:
    return os.path.join(HOME, *p)


def load() -> Dict[str, str]:
    c = dict(DEFAULTS)
    try:
        c.update(json.load(open(path("config.json"), encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return c


def save(c: Dict[str, str]) -> None:
    os.makedirs(HOME, exist_ok=True)
    json.dump(c, open(path("config.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def get(key: str) -> str:
    v = load().get(key, "")
    return os.path.expanduser(v) if isinstance(v, str) and ("dir" in key) else v


def authorized() -> List[str]:
    try:
        return list(json.load(open(path("authorized.json"), encoding="utf-8")).get("themes", []))
    except (OSError, ValueError):
        return []


def authorize(names: List[str]) -> List[str]:
    cur = sorted(set(authorized()) | set(names))
    os.makedirs(HOME, exist_ok=True)
    json.dump({"themes": cur, "note": "使用者自行确认：是该品牌的社群成员或已获得授权。"},
              open(path("authorized.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return cur


def export(src: str, project_dir: str, suffix: str = "") -> str:
    """把成品复制到「成品」文件夹，文件名＝项目名（＋后缀）。APFS 上用 cp -c 秒复制、不多占空间。返回目的路径（没设就返回空）。"""
    import shutil
    import subprocess
    d = get("exports_dir")
    if not d or not os.path.isfile(src):
        return ""
    os.makedirs(d, exist_ok=True)
    ext = os.path.splitext(src)[1]
    dst = os.path.join(d, os.path.basename(os.path.normpath(project_dir)) + suffix + ext)
    if os.path.exists(dst):
        os.remove(dst)
    if subprocess.run(["cp", "-c", src, dst], capture_output=True).returncode != 0:
        shutil.copyfile(src, dst)
    return dst


def profile_dirs() -> List[str]:
    """当前频道档案所在目录（程序自带的在前，用户自己的在后、可覆盖）。"""
    p = load().get("profile") or ""
    if not p:
        return []
    return [d for d in (os.path.join(APP, "profiles", p), path("profiles", p)) if os.path.isdir(d)]
