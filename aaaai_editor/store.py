"""剪辑表（storyboard.json）与字幕轨（work/captions.json）的唯一存取口。

为什么要有它：剪辑表会被好几个地方改——对话里的命令、封面、B-roll 放置、口误清理、开头钩子，
以后还有 Studio 图形界面。原本各处直接覆盖文件，两边同时改时后存的会把先存的盖掉。这里统一做三件事：

1. 原子写入：先写同目录的临时文件再整个替换，写到一半中断也不会留下半个坏文件。
2. 版本号：文件内容的哈希就是版本（不往文件里加任何栏位，旧项目、旧引擎都不受影响）。
   写入时可以带上「我读到的版本」，文件在这之间被别人改过就拒绝写入（Conflict），绝不静默覆盖。
3. 改动纪录：每次写入在 work/edits.log 记一行（时间、来源、前后版本），Studio 的复原与对话同步靠它。

写出的 JSON 格式与原本完全相同（ensure_ascii=False、indent=1），成片结果不会因此改变。
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import time
from typing import Any, Callable, Iterator, Optional, Tuple

SCHEMA = 1                  # 剪辑表目前的格式版本（文件里的 "version"）
MIGRATIONS: dict = {}       # 旧版本 → 升级函数；格式第一次改版时才会有内容
LOCK_STALE = 30.0           # 锁文件超过这么多秒还在，视为上次当掉留下的，直接接管


class Conflict(RuntimeError):
    """文件在你读取之后被别人改过。"""

    def __init__(self, path: str, expected: str, actual: str):
        super().__init__("%s 在你读取之后被改过（你读到的版本 %s，现在是 %s），请重新读取再改"
                         % (os.path.basename(path), expected, actual))
        self.path, self.expected, self.actual = path, expected, actual


def version_of(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


def _dump(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")


def current_version(path: str) -> str:
    """文件现在的版本；文件不存在时是空字串。"""
    try:
        with open(path, "rb") as f:
            return version_of(f.read())
    except FileNotFoundError:
        return ""


def read(path: str) -> Tuple[Any, str]:
    """读出 (内容, 版本)。"""
    with open(path, "rb") as f:
        raw = f.read()
    return json.loads(raw.decode("utf-8")), version_of(raw)


@contextlib.contextmanager
def lock(path: str, timeout: float = 10.0) -> Iterator[None]:
    """同一个文件同一时间只让一个程序做「读→改→写」。跨平台：用独占建档当锁。"""
    lp = path + ".lock"
    t0 = time.time()
    while True:
        try:
            fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lp) > LOCK_STALE:
                    os.remove(lp)
                    continue
            except OSError:
                continue
            if time.time() - t0 > timeout:
                raise TimeoutError("%s 正被其他程序修改中，请稍后再试" % os.path.basename(path))
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(lp)
        except OSError:
            pass


def _log(path: str, source: str, before: str, after: str) -> None:
    """在项目的 work/edits.log 记一行（剪辑表在项目根目录，字幕轨在 work/ 里）。"""
    d = os.path.dirname(os.path.abspath(path))
    work = d if os.path.basename(d) == "work" else os.path.join(d, "work")
    try:
        os.makedirs(work, exist_ok=True)
        with open(os.path.join(work, "edits.log"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(time.time(), 3), "file": os.path.basename(path),
                                "source": source, "from": before, "to": after}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _atomic(path: str, data: bytes) -> None:
    """先写同目录临时文件、落盘，再整个替换：中途当掉也不会留下半个文件。"""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write(path: str, obj: Any, expect: Optional[str] = None, source: str = "engine") -> str:
    """原子写入，回传新版本。expect＝你读到的版本；文件已被别人改过就抛 Conflict。"""
    data = _dump(obj)
    with lock(path):
        before = current_version(path)
        if expect is not None and before != expect:
            raise Conflict(path, expect, before)
        _atomic(path, data)
        after = version_of(data)
    if after != before:
        _log(path, source, before, after)
    return after


def update(path: str, fn: Callable[[Any], Any], source: str = "engine") -> str:
    """锁住文件做「读→改→写」：fn 收到现在的内容，回传（或就地改好）新内容。回传新版本。"""
    with lock(path):
        obj, ver = read(path)
        new = fn(obj)
        obj = obj if new is None else new
        data = _dump(obj)
        _atomic(path, data)
        after = version_of(data)
    if after != ver:
        _log(path, source, ver, after)
    return after


def migrate(sb: dict) -> Tuple[dict, bool]:
    """旧格式的剪辑表升级到目前格式。回传 (剪辑表, 有没有升级)。目前只有第 1 版，什么都不做。"""
    v = int(sb.get("version", 1) or 1)
    changed = False
    while v < SCHEMA and v in MIGRATIONS:
        sb = MIGRATIONS[v](sb)
        v += 1
        sb["version"] = v
        changed = True
    return sb, changed


# ---------------------------------------------------------------- 路径式修改（给 patch 命令用）
def _parse(path: str) -> list:
    """overlays.2.keyword → ["overlays", 2, "keyword"]；也接受 overlays[2].keyword。"""
    out = []
    for part in path.replace("[", ".").replace("]", "").split("."):
        if part == "":
            continue
        out.append(int(part) if part.lstrip("-").isdigit() else part)
    return out


def _walk(obj: Any, keys: list) -> Any:
    for k in keys:
        obj = obj[k]
    return obj


def apply_ops(obj: Any, ops: list) -> Any:
    """ops：[("set", path, value) | ("del", path) | ("append", path, value)]。路径不存在就报错，不猜。"""
    for op in ops:
        kind, p = op[0], _parse(op[1])
        if not p:
            raise ValueError("路径是空的")
        parent = _walk(obj, p[:-1])
        last = p[-1]
        if kind == "set":
            if isinstance(parent, list) and isinstance(last, int) and not -len(parent) <= last < len(parent):
                raise IndexError("%s 超出范围（只有 %d 项）" % (op[1], len(parent)))
            parent[last] = op[2]
        elif kind == "del":
            del parent[last]
        elif kind == "append":
            target = parent[last]
            if not isinstance(target, list):
                raise TypeError("%s 不是清单，不能 append" % op[1])
            target.append(op[2])
        else:
            raise ValueError("不认识的操作：%s" % kind)
    return obj
