"""存取口（store.py）与 patch 命令的测试：原子写入、版本冲突、并发、格式不变。
    python3 scripts/test_store.py
在临时目录里跑，不碰任何项目。
"""
import json
import multiprocessing
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from aaaai_editor import store  # noqa: E402

CLI = [sys.executable, "-m", "aaaai_editor"]
ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  ✅ %s" % name)
    else:
        fail += 1
        print("  ❌ %s %s" % (name, detail))


def _bump(path, n):
    sys.path.insert(0, ROOT)
    from aaaai_editor import store as st
    for _ in range(n):
        st.update(path, lambda o: o.__setitem__("n", o["n"] + 1), source="test")


def cli(*args):
    p = subprocess.run(CLI + list(args), cwd=ROOT, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    d = tempfile.mkdtemp(prefix="store-test-")
    sb = os.path.join(d, "storyboard.json")
    sample = {"version": 1, "source": "raw/a.mp4", "cuts": [[0.0, 5.5]],
              "overlays": [{"type": "title", "t": [1, 3], "text": "中文**重点**"},
                           {"type": "cta", "t": [3, 5], "keyword": "留言「工具」"}]}

    print("== 格式与原本逐字节相同")
    with open(sb, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=1)
    old = open(sb, "rb").read()
    store.write(sb, sample, source="test")
    check("store.write 写出的字节和 json.dump 一样", open(sb, "rb").read() == old)

    print("== 版本与冲突")
    obj, v1 = store.read(sb)
    check("版本是内容哈希", v1 == store.version_of(old))
    obj["overlays"][0]["text"] = "改过"
    v2 = store.write(sb, obj, expect=v1, source="test")
    check("带对版本可以写", v2 != v1)
    try:
        store.write(sb, sample, expect=v1, source="test")
        check("拿旧版本写会被拒绝", False, "没有抛 Conflict")
    except store.Conflict:
        check("拿旧版本写会被拒绝", True)
    check("被拒绝时文件没变", store.current_version(sb) == v2)

    print("== 并发：两个程序各加 40 次")
    cnt = os.path.join(d, "counter.json")
    store.write(cnt, {"n": 0})
    ps = [multiprocessing.Process(target=_bump, args=(cnt, 40)) for _ in range(2)]
    [p.start() for p in ps]
    [p.join() for p in ps]
    check("锁住读改写，一次都没丢", store.read(cnt)[0]["n"] == 80, store.read(cnt)[0])
    check("没有残留临时文件或锁", not [x for x in os.listdir(d) if x.startswith(".tmp-") or x.endswith(".lock")])

    print("== 改动纪录")
    log = os.path.join(d, "work", "edits.log")
    lines = open(log, encoding="utf-8").read().splitlines() if os.path.isfile(log) else []
    check("work/edits.log 有记录", len(lines) >= 2 and json.loads(lines[-1])["source"] == "test")

    print("== patch 命令")
    store.write(sb, sample, source="test")
    rc, out = cli("patch", sb, "--set", 'overlays.1.keyword="工具"')
    check("--set 改值", rc == 0 and store.read(sb)[0]["overlays"][1]["keyword"] == "工具", out)
    rc, out = cli("patch", sb, "--append", 'overlays={"type":"stamp","t":[0,1],"text":"NEW"}')
    check("--append 加一项", rc == 0 and store.read(sb)[0]["overlays"][-1]["text"] == "NEW", out)
    rc, out = cli("patch", sb, "--delete", "overlays.2")
    check("--delete 删一项", rc == 0 and len(store.read(sb)[0]["overlays"]) == 2, out)
    before = store.current_version(sb)
    rc, out = cli("patch", sb, "--set", "overlays.9.text=x")
    check("路径不存在：报错且不写入", rc == 1 and store.current_version(sb) == before, out)
    rc, out = cli("patch", sb, "--expect", "000000000000", "--set", "overlays.0.text=y")
    check("版本过期：拒绝（退出码 2）且不写入", rc == 2 and store.current_version(sb) == before, out)
    rc, out = cli("patch", sb)
    check("不带修改＝列出内容与版本", rc == 0 and before in out and "overlays.1" in out, out)

    print("== 迁移")
    m, changed = store.migrate(dict(sample))
    check("第 1 版剪辑表不需要升级", not changed and m == sample)

    print("通过 %d 项，失败 %d 项" % (ok, fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
