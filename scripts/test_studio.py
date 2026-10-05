"""Studio 本机服务的测试：安全（通行码、Host、路径穿越）、存档版本检查、逐字稿剪片、渲染工作、体检、诊断。
    python3 scripts/test_studio.py
在临时目录里用合成的测试影片跑，不碰任何项目，也不动正在运行的 Studio。
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from aaaai_editor import env, store  # noqa: E402
from aaaai_editor.studio import server  # noqa: E402

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  ✅ %s" % name)
    else:
        fail += 1
        print("  ❌ %s %s" % (name, detail))


def req(url, body=None, headers=None, data=None):
    if data is None and body is not None:
        data = json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        with urllib.request.urlopen(r, timeout=120) as f:
            raw = f.read()
            return f.status, (json.loads(raw) if f.headers.get("Content-Type", "").startswith("application/json") else raw), f.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def project(d):
    os.makedirs(os.path.join(d, "raw"))
    os.makedirs(os.path.join(d, "work"))
    env.run([env.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=8",
             "-f", "lavfi", "-i", "sine=f=220:d=8", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", os.path.join(d, "raw", "a.mp4")])
    segs = [{"start": 0.2, "end": 1.8, "text": "第一句话"}, {"start": 2.0, "end": 3.6, "text": "第二句要剪掉"},
            {"start": 3.8, "end": 5.6, "text": "第三句"}, {"start": 5.8, "end": 7.6, "text": "最后一句"}]
    json.dump({"segments": segs}, open(os.path.join(d, "work", "transcript.json"), "w"), ensure_ascii=False)
    sb = {"version": 1, "source": "raw/a.mp4", "output": {"width": 540, "height": 960, "fps": 30, "path": "out/final.mp4"},
          "cuts": [[0.0, 8.0]], "style": "mrone", "avoid_face": False, "captions": {"enabled": True},
          "overlays": [{"type": "title", "t": [0.5, 1.8], "kicker": "测试", "text": "标题**重点**"},
                       {"type": "stat", "t": [4.0, 6.0], "value": 3, "unit": "倍", "label": "说明"}]}
    p = os.path.join(d, "storyboard.json")
    store.write(p, sb, source="test")
    return p


def main():
    d = tempfile.mkdtemp(prefix="studio-test-")
    sbp = project(d)
    st = server.Studio(0)          # 不调用 serve()：不写 ~/.aaaai-editor/studio.json，不影响正在用的 Studio
    pid = st.register(d)
    threading.Thread(target=st.httpd.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
    B = st.url

    print("== 安全")
    check("没有通行码＝404", req("http://127.0.0.1:%d/api/ping" % st.port)[0] == 404)
    check("通行码错＝404", req("http://127.0.0.1:%d/s/wrong/api/ping" % st.port)[0] == 404)
    check("Host 不对＝404（防 DNS rebinding）", req(B + "api/ping", headers={"Host": "evil.example"})[0] == 404)
    check("路径穿越＝404", req(B + "f/%s/..%%2F..%%2F..%%2Fetc%%2Fpasswd" % pid)[0] == 404)
    check("只给项目里的文件", req(B + "f/%s/storyboard.json" % pid)[0] == 200)
    check("只听 127.0.0.1", st.httpd.server_address[0] == "127.0.0.1")

    print("== 打开与存档")
    c, j, _ = req(B + "api/open?p=" + pid)
    check("打开项目", c == 200 and j["source_ok"] and len(j["storyboard"]["overlays"]) == 2, str(j)[:200])
    check("没有字幕轨时给自动字幕", j["captions"] is None and len(j["captions_auto"] or []) >= 4)
    c, sc, _ = req(B + "api/schema")
    check("栏位表", c == 200 and "title" in sc["cards"] and "stat" in sc["true_look"])
    v0 = j["sb_version"]
    before = open(sbp, "rb").read()
    sb = j["storyboard"]
    sb["overlays"][0]["text"] = "改过的**标题**"
    c, r, _ = req(B + "api/save", {"p": pid, "storyboard": sb, "sb_expect": "000000000000"})
    check("版本过期＝不写入、回传冲突", c == 200 and r.get("conflict") and open(sbp, "rb").read() == before)
    c, r, _ = req(B + "api/save", {"p": pid, "storyboard": sb, "sb_expect": v0})
    v1 = r.get("sb_version")
    check("版本对＝写入", v1 and v1 != v0 and json.load(open(sbp))["overlays"][0]["text"] == "改过的**标题**")
    log = open(os.path.join(d, "work", "edits.log"), encoding="utf-8").read().splitlines()
    check("修改纪录写明来自 studio", json.loads(log[-1])["source"] == "studio")
    check("存档格式与引擎相同", open(sbp, "rb").read() == store._dump(sb))
    pcs = [dict(p, s=[round(p["s"][0], 3), round(p["s"][1], 3)]) for p in j["captions_auto"]]
    pcs[0]["en"] = "first line"
    capdoc = {"version": 1, "pieces": pcs, "aligned": False}
    c, r, _ = req(B + "api/save", {"p": pid, "captions": capdoc, "cap_expect": ""})
    check("第一次改字幕＝建字幕轨", r.get("cap_version") and os.path.isfile(os.path.join(d, "work", "captions.json")))
    c, ver, _ = req(B + "api/version?p=" + pid)
    check("版本查询", ver["sb_version"] == v1 and ver["cap_version"] == r["cap_version"])
    subprocess.run([sys.executable, "-m", "aaaai_editor", "patch", sbp, "--set", 'overlays.1.label="对话改的"'],
                   cwd=ROOT, capture_output=True)
    c, ver2, _ = req(B + "api/version?p=" + pid)
    check("对话里 patch 后界面看得到新版本", ver2["sb_version"] != v1)

    print("== 逐字稿剪片")
    _, j, _ = req(B + "api/open?p=" + pid)
    sb0 = j["storyboard"]
    c, r, _ = req(B + "api/recut", {"storyboard": json.loads(json.dumps(sb0)), "remove": [[2.0, 3.8]]})
    nsb = r["storyboard"]
    check("删一句＝cuts 扣掉那段", nsb["cuts"] == [[0.0, 2.0], [3.8, 8.0]], str(nsb["cuts"]))
    check("后面的字卡跟着往前", abs(nsb["overlays"][1]["t"][0] - 2.2) < 1e-6 and abs(nsb["overlays"][1]["t"][1] - 4.2) < 1e-6,
          str(nsb["overlays"][1]["t"]))
    check("前面的字卡不动", nsb["overlays"][0]["t"] == sb0["overlays"][0]["t"])
    check("记下删掉的区间（还原用）", nsb.get("studio", {}).get("removed") == [[2.0, 3.8]])
    c, r2, _ = req(B + "api/recut", {"storyboard": nsb, "restore": [[2.0, 3.8]]})
    check("还原＝回到原样", r2["storyboard"] == sb0, json.dumps(r2["storyboard"])[:300])
    c, r3, _ = req(B + "api/recut", {"storyboard": json.loads(json.dumps(sb0)), "remove": [[0.0, 8.0]]})
    check("全部删掉＝拒绝", c == 500 and b"\xe8\x87\xb3\xe5\xb0\x91" in r3)   # 「至少要留一段画面」

    print("== 引擎：字卡真样子、渲染一段、一次一个、取消")
    c, r, _ = req(B + "api/card", {"p": pid, "overlay": sb0["overlays"][0], "height": 640})
    png = os.path.join(d, r.get("url", "x/x/x")[len("f/%s/" % pid):])
    check("字卡真样子 PNG", c == 200 and os.path.isfile(png) and open(png, "rb").read(4) == b"\x89PNG")
    c, r, _ = req(B + "api/render", {"p": pid, "kind": "range", "a": 3.5, "b": 6.0})
    jid = r.get("job")
    c2, busy, _ = req(B + "api/render", {"p": pid, "kind": "range", "a": 0, "b": 2})
    check("一次只跑一个渲染", busy.get("busy"))
    t0, seen = time.time(), 0.0
    while time.time() - t0 < 180:
        _, jv, _ = req(B + "api/job?id=" + jid)
        seen = max(seen, jv["progress"])
        if jv["status"] != "running":
            break
        time.sleep(0.5)
    out = os.path.join(d, (jv.get("result") or "x/x/x")[len("f/%s/" % pid):])
    check("渲染一段完成、有成品", jv["status"] == "done" and os.path.isfile(out), json.dumps(jv, ensure_ascii=False)[:400])
    check("进度有真实数字", seen > 0)
    if os.path.isfile(out):
        info = env.probe(out)
        check("片段长度约 2.5 秒", abs(info["duration"] - 2.5) < 0.3, str(info["duration"]))
        c, body, h = req(B + "f/%s/%s" % (pid, jv["result"].split("/", 2)[2]), headers={"Range": "bytes=0-99"})
        check("影片支持拖动播放（Range）", c == 206 and len(body) == 100)
    c, r, _ = req(B + "api/render", {"p": pid, "kind": "final", "duration": 8})
    jid = r["job"]
    time.sleep(2.5)
    req(B + "api/cancel", {"id": jid})
    time.sleep(1.5)
    _, jv, _ = req(B + "api/job?id=" + jid)
    proc = st.jobs[jid].get("proc")
    check("取消＝停掉引擎进程", jv["status"] == "cancelled" and (proc is None or proc.poll() is not None))

    print("== 阶段 2：画面拖拉（xy）、素材、设定清单、开头钩子")
    from aaaai_editor import cards, render as R, theme
    sbx = R.load_storyboard(sbp)
    th = theme.theme(sbx.get("style"), sbx["_base"], sbx.get("brand"))
    ov = dict(sb0["overlays"][1], anim="fade", t=[0, 9])
    b0 = cards.layout(ov, th, 540, 960, 30)["_box"]
    b1 = cards.layout(dict(ov, xy=[0.5, 0.6]), th, 540, 960, 30)["_box"]
    check("xy＝把字卡放到指定位置（水平中心、上缘）", abs(b1[0] + b1[2] / 2 - 270) <= 1 and abs(b1[1] - 576) <= 1, "%s → %s" % (b0, b1))
    b2 = cards.layout(dict(ov, xy=[0.0, 2.0]), th, 540, 960, 30)["_box"]
    check("拖出画面会被拉回安全边内", b2[0] >= round(540 * cards.MARGIN_X) - 1 and b2[1] + b2[3] <= 960 + 1, str(b2))
    c, r, _ = req(B + "api/card", {"p": pid, "overlay": dict(sb0["overlays"][1], xy=[0.5, 0.6]), "height": 640})
    check("字卡真样子附带占的范围", c == 200 and r.get("box") and abs(r["box"][0] + r["box"][2] / 2 - 0.5) < 0.01, str(r)[:200])
    c, o, _ = req(B + "api/options?p=" + pid)
    check("设定清单（配乐、字幕样式、安全区、音效）", c == 200 and o["bgm"] and o["caption_styles"] and o["safe"]["top"] > 0 and o["sounds"])
    png = open(os.path.join(ROOT, "assets", "icons", os.listdir(os.path.join(ROOT, "assets", "icons"))[0]), "rb").read() \
        if os.path.isdir(os.path.join(ROOT, "assets", "icons")) and os.listdir(os.path.join(ROOT, "assets", "icons")) else b"\x89PNG\r\n\x1a\n" + b"0" * 64
    up = lambda name, data: req(B + "api/upload?p=%s&name=%s" % (pid, urllib.request.quote(name)), data=data)
    c1, r1, _ = up("图 1.png", png)
    c2, r2, _ = up("图 1.png", png)
    check("上传素材进 assets/、同名不覆盖", c1 == 200 and r1["path"] == "assets/图 1.png" and r2["path"] == "assets/图 1-2.png", "%s %s" % (r1, r2))
    c3, _, _ = up("run.sh", b"echo hi")
    check("不收图片／影片／声音以外的文件", c3 == 400 and not os.path.exists(os.path.join(d, "assets", "run.sh")))
    c4, r4, _ = up("../../escape.png", png)
    check("上传不能跑出 assets/", c4 == 200 and r4["path"] == "assets/escape.png" and not os.path.exists(os.path.join(os.path.dirname(d), "escape.png")))
    check("被拒的上传不会弄坏下一个请求", req(B + "api/ping")[0] == 200)
    c, al, _ = req(B + "api/assets?p=" + pid)
    check("素材清单", c == 200 and {"assets/图 1.png", "assets/escape.png"} <= {a["path"] for a in al["assets"]})
    c, hk, _ = req(B + "api/hook", {"p": pid})
    check("推荐开头钩子", c == 200 and isinstance(hk.get("items"), list))
    v_before = store.current_version(sbp)
    c, hr, _ = req(B + "api/hook", {"p": pid, "a": 5.9, "b": 7.5, "mode": "teaser"})
    hsb = json.load(open(sbp))
    check("套用开头钩子（经存取口、版本更新）", c == 200 and hsb.get("hook") and hsb["cuts"][0][0] > 5 and store.current_version(sbp) != v_before,
          str(hr)[:200] + str(hsb.get("cuts")))
    store.write(sbp, sb0, source="test")

    print("== 体检与诊断")
    c, r, _ = req(B + "api/check", {"p": pid})
    check("体检回传清单", c == 200 and isinstance(r.get("items"), list), str(r)[:300])
    c, r, _ = req(B + "api/diag", {"p": pid})
    check("诊断报告（不含影片）", c == 200 and "aaaai-editor" in r["text"] and r["path"] and os.path.isfile(r["path"]))
    check("诊断报告不含金钥字样", "KEY=" not in r["text"] and "sk-" not in r["text"])

    st.httpd.shutdown()
    print("\n通过 %d 项，失败 %d 项" % (ok, fail))
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
