"""命令行入口：python3 -m aaaai_editor <子命令>"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, autocut, checks, config, env, icons, recipes, render, showcase, store, theme, transcribe


def cmd_new(a) -> int:
    """在项目目录建一个新项目，印出路径（给 SKILL 接着用）。"""
    import datetime
    from . import config
    root = config.get("projects_dir")
    slug = "%s-%s" % (datetime.date.today().strftime("%Y%m%d"), a.slug)
    p = os.path.join(root, slug)
    os.makedirs(os.path.join(p, "work"), exist_ok=True)
    os.makedirs(os.path.join(p, "assets"), exist_ok=True)   # 自备 B-roll、logo、配乐放这里
    print(p)
    return 0


def cmd_adopt(a) -> int:
    """把其他格式做好的影片（Hyperframes／动画片等）接进来统一收尾：整段保留、可转录加字幕、锁响度、出封面。"""
    info = env.probe(a.video)
    out = os.path.abspath(a.out)
    base = os.path.dirname(out)
    os.makedirs(os.path.join(base, "work"), exist_ok=True)
    sb = {"version": 1, "source": os.path.abspath(a.video),
          "output": {"width": a.width or info.get("width", 1080), "height": a.height or info.get("height", 1920),
                     "fps": a.fps or round(info.get("fps", 30)), "path": "out/final.mp4"},
          "cuts": [[0.0, round(info["duration"], 3)]]}
    if a.style:
        sb["style"] = a.style
    if a.no_captions or not info.get("has_audio"):
        sb["captions"] = {"enabled": False}
    elif not a.no_transcribe:
        transcribe.transcribe(a.video, os.path.join(base, "work", "transcript.json"), a.lang)
    store.write(out, sb, source="adopt")
    print("✅ 接入 %.1fs 的影片 → %s（整段保留；之后照常 captions／render／cover）" % (info["duration"], out))
    return 0


def cmd_authorize(a) -> int:
    """旧版命令：社群风格现在人人可用，不需要授权。保留命令，免得旧说明照做时报错。"""
    from . import theme as th
    allt = th.all_themes()
    for n in a.themes:
        t = allt.get(n) or {}
        c = t.get("community")
        print("「%s」%s" % (n, ("是社群风格，现在不需要授权就能用（%s）" % c["note"]) if c else "不需要授权"))
    return 0


def cmd_config(a) -> int:
    from . import config, __version__
    c = config.load()
    if a.set:
        for kv in a.set:
            k, _, v = kv.partition("=")
            if k.startswith("broll.") and v.replace(".", "", 1).isdigit():
                v = float(v)
            if "." in k:   # 分组设置：broll.budget=5、broll.i2v=模型 id
                g, _, sk = k.partition(".")
                c[g] = dict(c.get(g) or {}, **{sk: v})
            else:
                c[k] = v
        config.save(c)
    print("aaaai-editor %s｜程序 %s｜用户资料 %s" % (__version__, config.APP, config.HOME))
    for k, v in c.items():
        print("  %-13s %s" % (k, v))
    return 0


def cmd_doctor(_a) -> int:
    return env.doctor()


def cmd_transcribe(a) -> int:
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.source)), "work", "transcript.json")
    doc = transcribe.transcribe(a.source, out, a.lang, a.prompt)
    print("✅ %d 段 → %s" % (len(doc["segments"]), out))
    st = doc.get("stats") or {}
    print("语言：%s" % doc.get("language"))
    if st:
        unit = st.get("unit", "字")
        print("%s数 %d ≈ %.0f 秒（按 %s）；频道档案有片长规定就照做"
              % (unit, st["chars"], st["est_seconds"], "203 字/分" if unit == "字" else "150 词/分"))
        print("人声比底噪高 %.0fdB%s" % (st["snr_db"], "" if st["snr_db"] >= 15 else
              "  ⚠️ 偏低：环境噪声大，后制救不回来（下次麦克风靠近／避开风扇、冷气出风口）"))
        for d in st.get("dropped") or []:
            print("  🗑 丢掉疑似幻听（几乎是静音）：%.1fs「%s」" % (d["start"], d["text"][:24]))
    for s in doc["segments"][:5]:
        print("  [%.1f–%.1f] %s" % (s["start"], s["end"], s["text"]))
    return 0


def cmd_autocut(a) -> int:
    info = env.probe(a.source)
    if not info.get("has_audio"):
        raise env.ToolError("素材没有音轨，没法按停顿剪。整段收尾请用：aaaai-editor adopt <视频>")
    if not (a.width and a.height):
        sw, sh = info.get("width", 1080), info.get("height", 1920)
        a.width, a.height = (1920, 1080) if sw > sh * 1.05 else ((1080, 1080) if sw >= sh * 0.95 else (1080, 1920))
        print("画幅：%d×%d（跟随素材%s；要做竖版短视频就加 --width 1080 --height 1920）"
              % (a.width, a.height, "横拍" if a.width > a.height else "竖拍" if a.height > a.width else "方形"))
    sil = autocut.detect_silences(a.source, a.noise if a.noise is not None else -35, a.min_silence)
    cuts = autocut.keep_ranges(info["duration"], sil, a.pad)
    if not a.no_refine:   # 按能量包络修剪点：段尾等尾音收完、段头留在起音前
        from . import audio
        e = audio.envelope(a.source)
        if a.noise is None:   # 静音门槛随底噪自适应（固定 -35dB 在底噪高的录音上找不到静音）
            sil = autocut.detect_silences(a.source, int(round(min(-25.0, e.voice_thr - 6))), a.min_silence)
            cuts = autocut.keep_ranges(info["duration"], sil, a.pad)
        cuts = autocut.refine(autocut.keep_ranges(info["duration"], sil, 0.0), e)
        bad = [j for j in audio.junctions(e, cuts) if j["tail_bad"] or j["head_bad"] or j["cont"]]
        print("剪点按尾音／起音修正（底噪 %.1fdB，衰减门槛 %.1fdB）；%d 个剪点仍不干净"
              % (e.floor, e.decay_thr, len(bad)))
        for j in bad:
            print("  ⚠️ 段 %d [%.2f–%.2f] %s" % (j["i"], j["a"], j["b"],
                  ("尾巴还在响 %.1fdB" % j["tail"]) if j["tail_bad"] else
                  ("字头已响 %.1fdB" % j["head"]) if j["head_bad"] else ("切点后还有人声 %.1fdB" % j["after"])))
    base = os.path.dirname(os.path.abspath(a.out))
    rel = os.path.relpath(os.path.abspath(a.source), base)
    src = rel if not rel.startswith("..") else os.path.abspath(a.source)   # 素材在项目外：写绝对路径，别写 ../../..
    sb = {"version": 1, "source": src,
          "output": {"width": a.width, "height": a.height, "fps": a.fps, "path": "out/final.mp4"},
          "cuts": cuts}
    store.write(a.out, sb, source="autocut")
    kept = sum(b - x for x, b in cuts)
    print("✅ %d 段保留 %.1fs / 原片 %.1fs（剪掉 %.0f%%）→ %s" % (len(cuts), kept, info["duration"],
                                                          100 * (1 - kept / info["duration"]), a.out))
    return 0


def cmd_tools(a) -> int:
    from . import tools as T
    k = a.tool
    if k == "bgm":
        for n, d in T.bgm_list():
            print("bgm:%-18s %s" % (n, d))
        print("用法：\"music\": {\"file\": \"bgm:<曲名>\", \"db\": -18, \"duck\": true}")
    elif k == "listen":
        for t, txt in T.listen(a.media, a.a, a.b, a.win, a.hop):
            print("%7.2f  %s" % (t, txt))
    elif k == "probe-cut":
        for t, ok, txt in T.probe_cut(a.media, a.mode, a.anchor, a.lo, a.hi, a.step, a.expect):
            print("%7.3f %s %s" % (t, "✅" if ok else "  ", txt))
    elif k == "music-ab":
        for f in T.music_ab(a.storyboard, a.at, a.dur, [float(x) for x in a.db.split(",")]):
            print("🎧 %s" % f)
        print("三支只差配乐音量，发给用户 A/B 听完再定 music.db。")
    elif k == "denoise-ab":
        for f in T.denoise_ab(a.storyboard, a.at, a.dur, a.levels.split(",")):
            print("🎧 %s" % f)
        print("三支只差降噪强度（原声／标准／加强），发给用户听完再定 storyboard 的 denoise。")
    elif k == "phone":
        print("📱 %s（只供手机预览，不是交付物）" % T.phone(a.storyboard))
    elif k == "framing":
        print("🖼 %s（1.00x 是原构图；选定后写进 storyboard 的 framing）"
              % T.framing_sheet(a.storyboard, a.at, [float(x) for x in a.levels.split(",")], a.cy))
    elif k == "cardpics":
        from . import cardpics as CP, config, render as R
        if a.list:
            items = CP.listing(R.load_storyboard(a.storyboard))
            if not items:
                print("这支片里没有可以出图卡的卡片（数据卡、清单卡、金句卡…）")
            for i, ov in enumerate(items, start=1):
                print("%2d  %-9s %5.1f–%4.1f 秒  %s" % (i, ov["type"], ov["t"][0], ov["t"][1], CP._label(ov)))
            print("挑几张：cardpics <storyboard> --pick 1,3 [--size 1350,1080] [--bg frame|blur|solid]")
            return
        pick = [int(x) for x in str(a.pick).split(",") if x.strip().isdigit()] if a.pick else None
        files, warns = CP.make(a.storyboard, tuple(str(a.size).split(",")), pick, a.bg)
        ex = config.get("exports_dir")
        for f in files:
            print(("📦 成品：%s" if ex and f.startswith(ex) else "🖼 %s") % f)
        for w in warns:
            print("⚠️ " + w)
    elif k == "cover-frames":
        from . import cover as C
        sheet, items = C.candidates(a.storyboard, a.n)
        print("🖼 候选封面总表：%s" % sheet)
        print("   " + "  ".join("%d＝%.1f 秒" % (x["n"], x["t"]) for x in items))
        print("发给用户挑一张，再执行 cover --pick <编号> --text「大标题」[--kicker …] [--sub …]")
    elif k == "cover":
        from . import cover as C, config
        files, warns = C.make(a.storyboard, a.at, a.pick, a.text, a.kicker, a.sub, a.handle, a.layout, a.color)
        ex = config.get("exports_dir")
        for f in files:
            print(("📦 成品：%s" if ex and f.startswith(ex) else "🖼 %s") % f)
        for w in warns:
            print("⚠️ " + w)
        print("用 Read 看 work/cover_check.png（竖版：左 Reels 全画面、右主页 4:5 裁切）。背景取自原片，没有字幕和卡片。")
    return 0


def cmd_render(a) -> int:
    if getattr(a, "subs", False):
        path = render.preview_subs(a.storyboard, a.t_from, a.t_to)
        print("✅ 字幕预览：%s" % path)
        return 0
    if getattr(a, "range", None):
        path = render.render_range(a.storyboard, a.range[0], a.range[1])
        print("✅ 这一段（%.2f–%.2f 秒，预览画质）：%s" % (a.range[0], a.range[1], path))
        return 0
    path = render.render(a.storyboard, getattr(a, "only", None), proxy=getattr(a, "proxy", False))
    print("✅ 输出：%s" % path)
    if getattr(a, "only", None) is None:
        from . import checks
        try:
            checks.quick(a.storyboard)
        except (env.ToolError, OSError, ValueError, KeyError) as e:
            print("ℹ️ 快速对时检查没跑成：%s" % e)
    return 0


def cmd_themes(a) -> int:
    from . import config
    base = os.path.dirname(os.path.abspath(a.storyboard)) if getattr(a, "storyboard", None) else None
    allt = theme.all_themes(base)
    for n in theme.list_themes(base):   # 社群风格排在最后、标出权利人：可以用，但不是首选
        t = allt[n]
        lock = "  ·社群风格 © %s（可用，非首选）" % t["community"]["owner"] if t.get("community") else ""
        t = theme.resolve_colors(dict(t))
        print("%-7s 强调 %s  价值 %s  陈述 %s  %s%s" % (n, t["accent"], t["value"], t["state"], t.get("desc", ""), lock))
    print("\n字体：中文 %s\n      数字 %s" % (theme.cjk_font(), theme.num_font()))
    return 0


def _jval(s: str):
    """--set 的值：先当 JSON 读（数字、true、"字串"、[...]、{...}），读不了就当普通字串。"""
    try:
        return json.loads(s)
    except ValueError:
        return s


def cmd_studio(a) -> int:
    """打开 Studio 图形剪辑界面（本机网页）。已经开着就沿用同一个，只回传网址。"""
    from .studio import server
    target = None
    if a.target:
        t = os.path.abspath(os.path.expanduser(a.target))
        d = os.path.dirname(t) if os.path.isfile(t) else t
        if not os.path.isfile(os.path.join(d, "storyboard.json")):
            print("❌ %s 里没有 storyboard.json" % d)
            return 1
        target = d
    url = server.running_url()
    if url:
        if target:
            # 已开着的 Studio 会扫描项目文件夹；不在里面的项目用新的一个来开
            root = os.path.realpath(config.get("projects_dir") or "")
            if not root or not os.path.realpath(target).startswith(root + os.sep):
                url = None
        if url:
            if target:
                url += "#p=" + server.Studio.pid(target)
            print("STUDIO_URL %s" % url)
            print("✅ Studio 已在运行，在浏览器打开上面的网址")
            return 0
    st = server.Studio(a.port)
    if target:
        st.register(target)
    url = st.url + ("#p=" + server.Studio.pid(target) if target else "")
    print("STUDIO_URL %s" % url, flush=True)
    print("✅ Studio 已启动（只有这台电脑能打开；按 Ctrl+C 结束）", flush=True)
    if not a.no_open:
        import webbrowser
        webbrowser.open(url)
    try:
        st.serve()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_notes(a) -> int:
    """Studio 的时间点留言：列出（默认只列请 Claude 处理、还没完成的）、回覆、标完成。"""
    from . import notes as N
    proj = N.project_of(a.target)
    if not os.path.isfile(os.path.join(proj, "storyboard.json")):
        print("❌ %s 不是项目文件夹" % proj)
        return 1
    if a.add:
        n = N.add(proj, a.add[1], float(a.add[0]), to="me", source="claude")
        print("✅ 加了第 %d 条留言" % n["id"])
        return 0
    if a.reply:
        n = N.change(proj, int(a.reply[0]), source="claude", reply=a.reply[1], status="done" if a.done_too else None)
        print("✅ 回覆了第 %d 条" % n["id"])
        return 0
    if a.done is not None:
        n = N.change(proj, a.done, source="claude", status="done")
        print("✅ 第 %d 条标为完成" % n["id"])
        return 0
    doc, _v = N.load(proj)
    rows = doc.get("notes", []) if a.all else N.pending(proj)
    if not rows:
        print("没有%s留言。" % ("" if a.all else "要 Claude 处理的"))
        return 0
    for n in rows:
        print(N.describe(n))
    if not a.all:
        print("\n处理完：notes <项目> --reply 编号 \"做了什么\" --done-too（Studio 会马上看到）")
    return 0


def cmd_patch(a) -> int:
    """带版本检查的小改动：Claude 改剪辑表／字幕轨一律用它，不直接覆盖文件（Studio 开着时不会互相盖掉）。"""
    path = os.path.abspath(a.file)
    if not os.path.isfile(path):
        print("❌ 找不到文件：%s" % path)
        return 1
    if a.show or not (a.set or a.delete or a.append):
        obj, ver = store.read(path)
        print("📄 %s　版本 %s" % (os.path.basename(path), ver))
        if isinstance(obj, dict) and "overlays" in obj:
            for i, o in enumerate(obj.get("overlays") or []):
                label = o.get("text") or o.get("kicker") or o.get("name") or o.get("question") or ""
                print("  overlays.%d  %-11s %s  %s" % (i, o.get("type", "?"), o.get("t"), str(label).replace("\n", " ")[:30]))
        if isinstance(obj, dict) and "pieces" in obj:
            for i, p in enumerate(obj["pieces"][:400]):
                print("  pieces.%d  %s  %s" % (i, p.get("s"), p.get("text", "")[:30]))
        return 0
    ops = []
    for x in a.set or []:
        if "=" not in x:
            print("❌ --set 要写成 路径=值，例：overlays.2.keyword=\"工具\"")
            return 1
        k, v = x.split("=", 1)
        ops.append(("set", k, _jval(v)))
    for x in a.append or []:
        k, v = x.split("=", 1)
        ops.append(("append", k, _jval(v)))
    for k in a.delete or []:
        ops.append(("del", k))
    _, ver = store.read(path)
    expect = a.expect or ver
    try:
        obj, now = store.read(path)
        if now != expect:
            raise store.Conflict(path, expect, now)
        store.apply_ops(obj, ops)
        new = store.write(path, obj, expect=expect, source=a.source)
    except store.Conflict as e:
        print("⚠️ %s" % e)
        return 2
    except (KeyError, IndexError, TypeError, ValueError) as e:
        print("❌ 改不了：%s（什么都没写入）" % e)
        return 1
    print("✅ %s：%d 处修改　版本 %s → %s" % (os.path.basename(path), len(ops), expect, new))
    return 0


def cmd_icons(a) -> int:
    if a.sheet:
        n = icons.sheet(os.path.abspath(a.sheet))
        print("✅ %d 个图标 → %s" % (n, os.path.abspath(a.sheet)))
    names = sorted(icons.ICONS)
    print("内建图标（%d）：%s" % (len(names), " ".join(names)))
    print("别名：%s" % " ".join("%s→%s" % kv for kv in sorted(icons.ALIASES.items())))
    lib = icons.library()
    print("图标库（套件 assets/icons/，%d）：%s" % (len(lib), " ".join(lib) if lib else "（还没有）"))
    print("加图标：通用的放套件 assets/icons/，只给某支片用的放 项目/assets/icons/；PNG 透明底、英文小写文件名＝图标名")
    return 0


def cmd_expand(a) -> int:
    sb = render.load_storyboard(a.storyboard)
    print(json.dumps({"overlays": sb.get("overlays"), "zooms": sb.get("zooms"),
                      "ending": sb.get("ending")}, ensure_ascii=False, indent=1))
    return 0


def cmd_captions(a) -> int:
    from . import captions as cp
    sb = render.load_storyboard(a.storyboard)
    cap = sb["captions"]
    tr = os.path.join(sb["_base"], cap.get("transcript", "work/transcript.json"))
    if not os.path.isfile(tr):
        raise env.ToolError("缺少转录文件 %s（先跑 aaaai-editor transcribe）" % tr)
    segs = json.load(open(tr, encoding="utf-8"))["segments"]
    p, n, wrote = cp.export_track(sb, segs, cp.fit(sb), a.force)
    print(("✅ 导出 %d 句 → %s" if wrote else "ℹ️ 已有字幕轨（%d 句）：%s  加 --force 重新导出会覆盖手改") % (n, p))
    if wrote and not a.no_align:
        # 刚导出的时间是按段落估的（一句能差好几秒）；马上对齐一次，后面排卡片、做 hook 拿到的才是准的时间
        print("⏱  先把每句贴到真实人声（改完字后再跑一次 align）…")
        try:
            cmd_align(argparse.Namespace(storyboard=a.storyboard, dry_run=False))
        except env.ToolError as e:
            print("⚠️ 自动对齐没成功（%s），字幕时间仍是估的；改完字后手动跑 align" % e)
    print("   改 text 修错字、填 en 出双语、hl 列关键词（或写 **关键词**）；删掉文件即回到自动字幕")
    return 0


def cmd_align(a) -> int:
    """把字幕轨每句的时间贴到真实人声上（改完字幕后跑）。"""
    from . import align as al, captions as cp
    sb = render.load_storyboard(a.storyboard)
    cap = sb["captions"]
    tr = os.path.join(sb["_base"], cap.get("transcript", "work/transcript.json"))
    doc = json.load(open(tr, encoding="utf-8"))
    tp = cp.track_path(sb)
    if not os.path.isfile(tp):
        cp.export_track(sb, doc["segments"], cp.fit(sb))
    track = json.load(open(tp, encoding="utf-8"))
    new, st = al.align(sb, track["pieces"], doc.get("language") or "zh")
    print("人声门槛 %.1fdB｜开口 %.2fs｜讲完 %.2fs" % (st["thr"], st["first_voice"], st["last_voice"]))
    print("对上 %d/%d 个字（%.0f%%）｜%d 句没对上、用插值｜%d 句移动超过 0.3s（最大 %.2fs）"
          % (st["matched_chars"], st["chars"], 100.0 * st["matched_chars"] / max(1, st["chars"]),
             st["missed"], st["moved_over_0.3"], st["max_move"]))
    if a.dry_run:
        for o, n in zip(track["pieces"], new):
            d = n["s"][0] - o["s"][0]
            print(" %s %7.2f → %7.2f (%+.2f)  %s" % ("  " if abs(d) < 0.3 else "⇢", o["s"][0], n["s"][0], d, n["text"][:22]))
        print("--dry-run：没有写回")
        return 0
    track["pieces"] = new
    track["aligned"] = True
    store.write(tp, track, source="align")
    print("✅ 已写回 %s。卡片时间若照旧的 cues 排过，重跑 cues 核对一下。" % os.path.relpath(tp, sb["_base"]))
    return 0


def cmd_cues(a) -> int:
    """按成片时间列出每句字幕：放卡片、配方、推近时照着这张表填时间。"""
    from . import captions as cp
    from .timeline import Timeline
    sb = render.load_storyboard(a.storyboard)
    cap = sb["captions"]
    tr = os.path.join(sb["_base"], cap.get("transcript", "work/transcript.json"))
    if not os.path.isfile(tr):
        raise env.ToolError("缺少转录文件 %s（先跑 aaaai-editor transcribe）" % tr)
    segs = json.load(open(tr, encoding="utf-8"))["segments"]
    pcs, track = cp.load_pieces(sb, segs, cp.fit(sb))
    tl = Timeline([tuple(c) for c in sb["cuts"]], sb["output"]["fps"], sb.get("speed"))
    print("成片时长 %.2fs（%s）" % (tl.duration, "手改字幕轨" if track else "自动字幕"))
    for a_, b_, t, ex in cp.to_events(pcs, tl):
        print("[%6.2f – %6.2f] %s%s" % (a_, b_, t, ("  | " + ex["en"]) if ex.get("en") else ""))
    return 0


def cmd_proof(a) -> int:
    """按卡片／推近时间自动抽检查帧（卡片落定、列表出齐之后），省掉手算时间点。"""
    sb = render.load_storyboard(a.storyboard)
    out = sb["output"]["path"]
    video = out if a.final else os.path.splitext(out)[0] + "_preview.mp4"
    if not os.path.isfile(video):
        raise env.ToolError("找不到 %s（先跑 %s）" % (video, "render" if a.final else "preview"))
    dur = env.probe(video)["duration"]
    marks = [(0.5, "开头")]
    for i, ov in enumerate(sb.get("overlays") or []):
        t0, t1 = float(ov["t"][0]), float(ov["t"][1])
        items = ov.get("items") or []
        ats = [float(it["at"]) for it in items if isinstance(it, dict) and it.get("at") is not None]
        if ats:
            t = max(ats) + 0.6
        elif items:
            t = t0 + 0.8 + 0.25 * len(items)
        else:
            t = t0 + 0.8
        t = max(t0 + 0.45, min(t, t1 - 0.35, dur - 0.1))
        marks.append((t, "%d:%s%s" % (i, ov.get("type"), (" " + str(ov.get("text") or ov.get("title") or ""))[:14])))
    for z in sb.get("zooms") or []:
        marks.append(((float(z["t"][0]) + float(z["t"][1])) / 2, "推近"))
    marks.append((max(0.0, dur - 0.3), "结尾"))
    d = os.path.join(sb["_base"], "work", "proof")
    os.makedirs(d, exist_ok=True)
    seen = set()
    for t, lab in sorted(marks):
        k = round(t, 1)
        if k in seen:
            continue
        seen.add(k)
        f = os.path.join(d, "t%06.2f.png" % t)
        env.run([env.ffmpeg(), "-y", "-v", "error", "-ss", "%.3f" % t, "-i", video, "-frames:v", "1",
                 "-vf", "scale=540:-2", f])
        print("%6.2fs  %-22s %s" % (t, lab, f))
    print("↑ 逐张用 Read 看：字有没有撑出卡片、压脸、压字幕，高亮对不对。")
    return 0


def cmd_showcase(a) -> int:
    print("✅ 风格对照表：%s" % showcase.run(a.out, a.only, a.project))
    return 0


def cmd_sfx(a) -> int:
    from . import sfx
    print(sfx.describe())
    print("\n用法：storyboard 写 \"sfx\": [{\"t\": 成片秒数, \"sound\": \"coin\"}]，或卡片上写 \"sfx\": \"pop\"（卡片出现时响，"
          "\"sfx_at\" 改时间）；整体音量 \"sfx_level\": quiet／normal／loud")
    return 0


def cmd_hook(a) -> int:
    from . import edit
    if a.suggest:
        cs = edit.suggest_hooks(a.storyboard, a.suggest)
        if not cs:
            print("没找到特别适合当开头的句子（没有数字、反差或强烈字眼）。可以直接用 --text 指定。")
            return 0
        print("适合放到开头当预告的句子（分数高的在前；选一句用 --text 放上去）：")
        for i, c in enumerate(cs, 1):
            print(" %d. [分数 %.1f｜成片 %s｜原片 %.2f–%.2f 秒] %s" % (i, c["score"], "%.1f 秒" % c["at"] if c["at"] is not None else "—",
                                                       c["s"][0], c["s"][1], c["text"]))
        return 0
    r = edit.hook(a.storyboard, a.text, a.t_from, a.t_to, a.mode)
    print("✅ 开头 hook：原片 %.2f–%.2f 秒（%.2f 秒），方式 %s；成片现在 %.1f 秒"
          % (r["range"][0], r["range"][1], r["len"], "预告（原位置保留）" if r["mode"] == "teaser" else "挪到开头", r["duration"]))
    if r.get("heard") is not None:
        print("🎧 剪出来的这段听起来是：「%s」" % r["heard"])
    if r.get("tail_missing"):
        print("⚠️ 句尾好像被切掉了（原话最后几个字没听到）：用 listen 听一下，必要时改用 --from/--to 给原片秒数。")
    print("卡片／推近的时间已跟着换算。开头那几秒原本的标题卡，现在排在 hook 之后——看预览决定要不要挪到 0 秒。")
    return 0


def cmd_speed(a) -> int:
    from . import edit
    r = edit.set_speed(a.storyboard, a.range[0], a.range[1], a.x)
    print("✅ 原片 %.2f–%.2f 秒改成 %.2g 倍速；成片现在 %.1f 秒（%s %.1f 秒），字卡已跟着换算"
          % (a.range[0], a.range[1], a.x, r["duration"], "少了" if r["saved"] >= 0 else "多了", abs(r["saved"])))
    return 0


def cmd_tidy(a) -> int:
    from . import edit
    if a.apply is not None:
        ids = [int(x) for x in a.apply.split(",") if x.strip()] if a.apply not in ("", "all") else None
        r = edit.apply(a.storyboard, ids)
        print("✅ 删掉 %d 处，省下 %.1f 秒；成片现在 %.1f 秒。字幕轨里若还留着重讲的字，改 work/captions.json 再跑 align。"
              % (r["removed"], r["saved"], r["duration"]))
        return 0
    props = edit.detect(a.storyboard, a.lang)
    if not props:
        print("没有找到口头禅或 NG。")
        return 0
    for p in props:
        print("%2d. [成片 %s 秒] %-6s 删 %.2f 秒  %s" % (p["id"], p["t"], p["kind"], p["len"], p["text"]))
    print("共 %d 处，合计 %.1f 秒。先用 listen 听有疑问的，确认后：tidy <storyboard> --apply all 或 --apply 1,3,5"
          % (len(props), sum(p["len"] for p in props)))
    return 0


def cmd_keys(a) -> int:
    from . import keys
    if a.action == "set":
        for n in (a.names or list(keys.KEYS)):
            if not sys.stdin.isatty():
                print("⚠️ 请在你自己的终端运行 aaaai-editor keys set %s（密钥不要贴进聊天）" % n)
                return 2
            ok = keys.set_interactive(n)
            print("✅ 已存进钥匙串" if ok else "— 跳过（没有存）")
        return 0
    if a.action == "remove":
        for n in a.names:
            print(("🗑  已移除 %s" if keys.remove(n) else "— 钥匙串里没有 %s") % n)
        return 0
    st = keys.status()
    for n, info in keys.KEYS.items():
        print("%s %-15s %s\n   费用：%s\n   申请：%s" % ("✅" if st[n] else "—", n, info["for"], info["cost"], info["url"]))
    print("全部可选。绑定：在你自己的终端运行 aaaai-editor keys set <名称>（钥匙串隐藏输入，不经过聊天）")
    return 0


def cmd_broll(a) -> int:
    from . import broll
    if a.action == "status":
        print(broll.status_text())
        return 0
    if a.action == "search":
        for c in broll.pexels_search(" ".join(a.args), a.aspect, a.n):
            print("%-10s %4ss %dx%d  %s  by %s" % (c["id"], c["duration"], c["w"], c["h"], c["url"], c["user"]))
        return 0
    if a.action == "library":
        rows = broll.library_search(" ".join(a.args))
        for r in rows:
            print("%s  %-10s %-5s $%.3f  %s  %s" % (r["created"], r["provider"], r["aspect"], r.get("cost", 0),
                                                   (r.get("prompt") or r.get("query") or "")[:60], r["file"]))
        print("共 %d 条（%s）" % (len(rows), broll.lib_dir()))
        return 0
    if a.action == "plan":
        print(broll.template(a.args[0] if a.args else "storyboard.json"))
        return 0
    if a.action == "clip":
        if not a.prompt or not a.out:
            raise env.ToolError("用法：aaaai-editor broll clip --prompt 描述 --out 文件.mp4 [--aspect 9:16] [--provider auto]")
        shot = {"id": "clip", "prompt": a.prompt, "provider": a.provider, "image": a.image}
        e = broll.estimate({"aspect": a.aspect, "budget": broll.cfg()["budget"], "shots": [shot]},
                           a.fallback_higgsfield)
        print(broll.estimate_text(e))
        if e["first"] > 0 and not a.yes:
            print("↑ 这一条要花钱。确认后加 --yes 再跑一次。")
            return 2
        r = broll.clip(a.prompt, a.out, a.aspect, a.provider, a.image, None, a.allow_over_budget,
                       a.fallback_higgsfield)
        print("✅ %s（%s，$%.3f）" % (r["out"], r["provider"], r["cost"]))
        return 0
    plan_path = a.args[0] if a.args else "broll_plan.json"
    if a.action == "estimate":
        print(broll.estimate_text(broll.estimate(broll.load_plan(plan_path), a.fallback_higgsfield)))
        return 0
    if a.action == "gen":
        e = broll.estimate(broll.load_plan(plan_path), a.fallback_higgsfield)
        print(broll.estimate_text(e))
        if e["first"] > 0 and not a.yes:
            print("↑ 要花钱。跟用户确认后加 --yes 再跑一次。")
            return 2
        r = broll.generate(plan_path, a.allow_over_budget, a.fallback_higgsfield, a.only)
        print("完成 %d 条，本项目累计 $%.3f" % (r["done"], r["spent"]))
        for sid, err in r["failed"]:
            print("❌ %s：%s" % (sid, err))
        return 3 if r["stopped"] else (1 if r["failed"] else 0)
    if a.action == "sheet":
        print("✅ 审片图：%s（用 Read 看，决定要不要换）" % broll.sheet(plan_path))
        return 0
    if a.action == "place":
        if len(a.args) < 2:
            raise env.ToolError("用法：aaaai-editor broll place broll_plan.json storyboard.json")
        n, cp = broll.place(a.args[0], a.args[1])
        print("✅ 放进 %d 条 B-roll；素材署名：%s" % (n, cp))
        return 0
    raise env.ToolError("未知动作 %s" % a.action)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aaaai-editor", description="aaaai-editor v%s" % __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap.add_argument("--version", action="version", version="aaaai-editor %s" % __version__)
    sub.add_parser("doctor", help="检查依赖").set_defaults(fn=cmd_doctor)
    n_ = sub.add_parser("new", help="在项目目录新建项目，印出路径")
    n_.add_argument("slug"); n_.set_defaults(fn=cmd_new)
    ad = sub.add_parser("adopt", help="把其他格式做好的影片接进来统一收尾（字幕／响度／封面／验收）")
    ad.add_argument("video"); ad.add_argument("--out", default="storyboard.json"); ad.add_argument("--style")
    ad.add_argument("--lang", default="auto", help="auto＝自动判断语言；也可写 zh／en／ja…"); ad.add_argument("--no-captions", action="store_true")
    ad.add_argument("--no-transcribe", action="store_true")
    ad.add_argument("--width", type=int); ad.add_argument("--height", type=int); ad.add_argument("--fps", type=int)
    ad.set_defaults(fn=cmd_adopt)
    au = sub.add_parser("authorize", help="（旧版命令）社群风格 mrone／otg 现在不需授权")
    au.add_argument("themes", nargs="+"); au.add_argument("--yes", action="store_true")
    au.set_defaults(fn=cmd_authorize)
    cf = sub.add_parser("config", help="查看／修改设置（--set projects_dir=~/Videos/aaaai-editor）")
    cf.add_argument("--set", nargs="*"); cf.set_defaults(fn=cmd_config)
    t = sub.add_parser("transcribe", help="转录成 transcript.json")
    t.add_argument("source")
    t.add_argument("--out")
    t.add_argument("--lang", default="auto", help="auto＝自动判断语言；也可写 zh／en／ja…")
    t.add_argument("--prompt")
    t.set_defaults(fn=cmd_transcribe)
    c = sub.add_parser("autocut", help="按静音自动生成 storyboard.json 的 cuts")
    c.add_argument("source")
    c.add_argument("--out", default="storyboard.json")
    c.add_argument("--noise", type=int, default=None, help="静音门槛 dB；不写就按底噪自适应")
    c.add_argument("--min-silence", type=float, default=0.5)
    c.add_argument("--pad", type=float, default=0.12, help="只在 --no-refine 时使用")
    c.add_argument("--no-refine", action="store_true", help="不按能量包络修剪点（旧行为）")
    c.add_argument("--width", type=int, help="不写就跟随素材方向：竖拍 1080×1920、横拍 1920×1080、方形 1080×1080")
    c.add_argument("--height", type=int)
    c.add_argument("--fps", type=int, default=30)
    c.set_defaults(fn=cmd_autocut)
    r = sub.add_parser("render", help="渲染 storyboard.json")
    r.add_argument("storyboard")
    r.add_argument("--only", choices=["video", "audio"])
    r.add_argument("--proxy", action="store_true", help="半分辨率快速预览")
    r.add_argument("--range", nargs=2, type=float, metavar=("开始", "结束"),
                   help="只渲染成片的这一段（秒，预览画质，声音截自整片混音），几秒钟就好")
    r.set_defaults(fn=cmd_render)
    pv = sub.add_parser("preview", help="快速预览（等同 render --proxy）；--subs 只烧字幕、约一分钟")
    pv.add_argument("storyboard")
    pv.add_argument("--subs", action="store_true")
    pv.add_argument("--from", dest="t_from", type=float)
    pv.add_argument("--to", dest="t_to", type=float)
    pv.set_defaults(fn=cmd_render, only=None, proxy=True)
    t = sub.add_parser("bgm", help="列出常备配乐")
    t.set_defaults(fn=cmd_tools, tool="bgm")
    t = sub.add_parser("sfx", help="列出音效（storyboard 的 sfx 或卡片上的 \"sfx\"）")
    t.set_defaults(fn=cmd_sfx)
    t = sub.add_parser("listen", help="滑动窗口听写：第几秒在讲什么（不带提示词）")
    t.add_argument("media"); t.add_argument("a", type=float); t.add_argument("b", type=float)
    t.add_argument("--win", type=float, default=2.5); t.add_argument("--hop", type=float, default=0.5)
    t.set_defaults(fn=cmd_tools, tool="listen")
    t = sub.add_parser("probe-cut", help="逐点试听剪点：end 找讲完的最早点／start 找以它开头的最晚点")
    t.add_argument("media"); t.add_argument("mode", choices=["end", "start"]); t.add_argument("anchor", type=float)
    t.add_argument("lo", type=float); t.add_argument("hi", type=float); t.add_argument("step", type=float)
    t.add_argument("expect")
    t.set_defaults(fn=cmd_tools, tool="probe-cut")
    t = sub.add_parser("music-ab", help="同一段出几种配乐音量的 MP3 给用户 A/B")
    t.add_argument("storyboard"); t.add_argument("--at", type=float, default=0.0)
    t.add_argument("--dur", type=float, default=35.0); t.add_argument("--db", default="-16,-18,-20")
    t.set_defaults(fn=cmd_tools, tool="music-ab")
    t = sub.add_parser("denoise-ab", help="同一段出「原声／标准降噪／加强降噪」三支 MP3 给用户 A/B")
    t.add_argument("storyboard"); t.add_argument("--at", type=float, default=0.0)
    t.add_argument("--dur", type=float, default=15.0); t.add_argument("--levels", default="off,on,strong")
    t.set_defaults(fn=cmd_tools, tool="denoise-ab")
    t = sub.add_parser("phone", help="手机预览版（720 宽、≤30MB）")
    t.add_argument("storyboard"); t.set_defaults(fn=cmd_tools, tool="phone")
    t = sub.add_parser("framing", help="同一帧几种推近倍率的对比图")
    t.add_argument("storyboard"); t.add_argument("--at", type=float, default=3.0)
    t.add_argument("--levels", default="1.0,1.15,1.3,1.45"); t.add_argument("--cy", type=float, default=0.4)
    t.set_defaults(fn=cmd_tools, tool="framing")
    t = sub.add_parser("cardpics", help="图卡：把片里的卡片出成静态图（发图文用），默认 1080×1350")
    t.add_argument("storyboard")
    t.add_argument("--list", action="store_true", help="先看这支片有哪些卡片可以出图卡")
    t.add_argument("--pick", help="要哪几张，例 1,3（不写就全部）")
    t.add_argument("--size", default="1350", help="1350（小红书／IG）｜1080（方版）｜1920（直版），可逗号多选")
    t.add_argument("--bg", default="frame", choices=["frame", "blur", "solid"], help="背景：原片干净帧／模糊帧／纯色")
    t.set_defaults(fn=cmd_tools, tool="cardpics")
    t = sub.add_parser("cover-frames", help="挑候选封面画面（从原片取、没有字幕），拼成编号总表给用户选")
    t.add_argument("storyboard"); t.add_argument("--n", type=int, default=8)
    t.set_defaults(fn=cmd_tools, tool="cover-frames")
    t = sub.add_parser("cover", help="封面：招牌版（小标签／大标题／说明／账号名＋暗黑渐层），出 1080×1920 与 1080×1350")
    t.add_argument("storyboard")
    t.add_argument("--pick", type=int, help="用 cover-frames 的第几张"); t.add_argument("--at", type=float, help="或直接写成片秒数")
    t.add_argument("--text", help="大标题；用 | 可自己指定断行（不写就按长度自动判断）")
    t.add_argument("--kicker", help="大标题上方的小标签，例：一人公司 · 支付安全")
    t.add_argument("--sub", help="第三行说明")
    t.add_argument("--handle", help="账号名；不写就用设定里的 handle，没设定就不印；写空字串不印")
    t.add_argument("--layout", choices=["signature", "center"], help="signature＝招牌版（默认）；center＝居中简洁版")
    t.add_argument("--color", help="大标题颜色（默认用风格的强调色）")
    t.set_defaults(fn=cmd_tools, tool="cover")
    th = sub.add_parser("themes", help="列出风格与字体（给 storyboard 可一并列出项目自定义风格）")
    th.add_argument("storyboard", nargs="?")
    th.set_defaults(fn=cmd_themes)
    pt = sub.add_parser("patch", help="带版本检查地改剪辑表／字幕轨（Claude 改文件一律用它）；不带修改＝列出内容与版本")
    pt.add_argument("file", help="storyboard.json 或 work/captions.json")
    pt.add_argument("--set", action="append", metavar="路径=值", help="例：overlays.2.keyword='\"工具\"'，值用 JSON")
    pt.add_argument("--delete", action="append", metavar="路径", help="删掉一项，例：overlays.3")
    pt.add_argument("--append", action="append", metavar="路径=值", help="在清单最后加一项，例：overlays='{...}'")
    pt.add_argument("--expect", help="你读到的版本；文件在那之后被改过就拒绝（不写就以现在的版本为准）")
    pt.add_argument("--source", default="claude", help="改动来源，记在 work/edits.log")
    pt.add_argument("--show", action="store_true", help="只列出内容与版本")
    pt.set_defaults(fn=cmd_patch)
    nt = sub.add_parser("notes", help="Studio 的时间点留言：列出要 Claude 处理的、回覆、标完成")
    nt.add_argument("target", help="项目文件夹或其中的 storyboard.json")
    nt.add_argument("--all", action="store_true", help="列出全部留言（包含已完成、给自己看的）")
    nt.add_argument("--reply", nargs=2, metavar=("编号", "回覆"))
    nt.add_argument("--done-too", action="store_true", help="回覆的同时标为完成")
    nt.add_argument("--done", type=int, metavar="编号")
    nt.add_argument("--add", nargs=2, metavar=("成片秒数", "文字"), help="加一条给用户看的留言")
    nt.set_defaults(fn=cmd_notes)
    so = sub.add_parser("studio", help="打开图形剪辑界面（本机网页，拖拉字卡与字幕、逐字稿剪片、体检、渲染一段）")
    so.add_argument("target", nargs="?", help="项目文件夹或其中的 storyboard.json；不写＝打开项目首页")
    so.add_argument("--port", type=int, default=0, help="指定端口（默认随机）")
    so.add_argument("--no-open", action="store_true", help="不自动开浏览器（Claude 会在应用内浏览器打开）")
    so.set_defaults(fn=cmd_studio)
    ic = sub.add_parser("icons", help="列出图标；--sheet 输出总表图")
    ic.add_argument("--sheet")
    ic.set_defaults(fn=cmd_icons)
    sub.add_parser("recipes", help="列出配方").set_defaults(fn=lambda a: print(recipes.listing()) or 0)
    ex = sub.add_parser("expand", help="打印配方展开后的 overlays／zooms（方便手动微调）")
    ex.add_argument("storyboard")
    ex.set_defaults(fn=cmd_expand)
    cp_ = sub.add_parser("captions", help="导出可手改的字幕轨 work/captions.json（修错字／双语／高亮）")
    cp_.add_argument("storyboard")
    cp_.add_argument("--force", action="store_true")
    cp_.add_argument("--no-align", action="store_true", help="导出后不自动对齐")
    cp_.set_defaults(fn=cmd_captions)
    al_ = sub.add_parser("align", help="字幕逐句对齐到真实人声（改完字幕轨后跑）")
    al_.add_argument("storyboard")
    al_.add_argument("--dry-run", action="store_true")
    al_.set_defaults(fn=cmd_align)
    cu = sub.add_parser("cues", help="按成片时间列出每句字幕（排卡片时间用）")
    cu.add_argument("storyboard")
    cu.set_defaults(fn=cmd_cues)
    pf = sub.add_parser("proof", help="按卡片时间自动抽检查帧（默认从 preview，--final 从成片）")
    pf.add_argument("storyboard")
    pf.add_argument("--final", action="store_true")
    pf.set_defaults(fn=cmd_proof)
    sc = sub.add_parser("showcase", help="渲染所有风格的对照表")
    sc.add_argument("--out", default="showcase.png")
    sc.add_argument("--only", nargs="*")
    sc.add_argument("--project", help="项目目录（把它的 themes/ 也纳入）")
    sc.set_defaults(fn=cmd_showcase)
    cs = sub.add_parser("check-sync", help="字幕对时体检（重转录成片音轨再逐句比时间）")
    cs.add_argument("storyboard")
    cs.add_argument("--tolerance", type=float, default=0.4)
    cs.set_defaults(fn=lambda a: checks.sync(a.storyboard, a.tolerance))
    hk = sub.add_parser("hook", help="把最强的一句放到片头（teaser＝开头先放一次、原位置保留；move＝挪过去）")
    hk.add_argument("storyboard"); hk.add_argument("--text", help="那句话的原文（一部分也行）")
    hk.add_argument("--from", dest="t_from", type=float, help="原片起点秒数"); hk.add_argument("--to", dest="t_to", type=float)
    hk.add_argument("--mode", choices=["teaser", "move"], default="teaser")
    hk.add_argument("--suggest", nargs="?", type=int, const=3, default=0, help="只列出最适合当开头的几句（默认 3 句），不改 storyboard")
    hk.set_defaults(fn=cmd_hook)
    spd = sub.add_parser("speed", help="一段变速：原片 开始 结束 秒改成 x 倍速（2＝快一倍、0.5＝慢动作、1＝恢复），字卡跟着换算")
    spd.add_argument("storyboard")
    spd.add_argument("--range", nargs=2, type=float, required=True, metavar=("原片开始", "原片结束"))
    spd.add_argument("--x", type=float, required=True, help="倍速 0.25～4")
    spd.set_defaults(fn=cmd_speed)
    td = sub.add_parser("tidy", help="找口头禅（嗯、呃…）与 NG（讲错重讲），列出来；--apply 套用")
    td.add_argument("storyboard"); td.add_argument("--lang", default="auto")
    td.add_argument("--apply", nargs="?", const="all", help="all 或编号，例：--apply 1,3,5")
    td.set_defaults(fn=cmd_tidy)
    ks = sub.add_parser("keys", help="API 密钥（全部可选）：list／set／remove，存在钥匙串")
    ks.add_argument("action", nargs="?", default="list", choices=["list", "set", "remove"])
    ks.add_argument("names", nargs="*")
    ks.set_defaults(fn=cmd_keys)
    br = sub.add_parser("broll", help="B-roll：status／search／plan／estimate／gen／sheet／place／library／clip")
    br.add_argument("action", choices=["status", "search", "plan", "estimate", "gen", "sheet", "place", "library",
                                       "clip"])
    br.add_argument("args", nargs="*")
    br.add_argument("--aspect", default="9:16", choices=["9:16", "16:9", "1:1"])
    br.add_argument("--n", type=int, default=8)
    br.add_argument("--prompt"); br.add_argument("--out"); br.add_argument("--image")
    br.add_argument("--provider", default="auto", choices=["auto", "stock", "opensource", "kling", "higgsfield"])
    br.add_argument("--only", nargs="*")
    br.add_argument("--yes", action="store_true", help="已跟用户确认费用")
    br.add_argument("--allow-over-budget", action="store_true", help="用户同意超出项目上限")
    br.add_argument("--fallback-higgsfield", action="store_true", help="其他都失败时再用 Higgsfield")
    br.set_defaults(fn=cmd_broll)
    mc = sub.add_parser("mcp", help="以 MCP 服务器运行（给 Claude Desktop／Codex／Cursor 调用）")
    mc.set_defaults(fn=lambda a: __import__("aaaai_editor.mcp", fromlist=["serve"]).serve())
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except KeyboardInterrupt:
        print("\n⏹ 已中断（做到一半的中间档留在 work/，下次会自动重做）", file=sys.stderr)
        return 130
    except json.JSONDecodeError as e:
        print("❌ JSON 格式错误（第 %d 行第 %d 列）：%s——多半是少了逗号或引号" % (e.lineno, e.colno, e.msg),
              file=sys.stderr)
        return 1
    except KeyError as e:
        print("❌ 缺少字段 %s（检查 storyboard.json／计划档是否写全）" % e, file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print("❌ 找不到文件：%s" % (e.filename or e), file=sys.stderr)
        return 1
    except PermissionError as e:
        print("❌ 没有权限写入：%s（换一个你有权限的目录）" % (e.filename or e), file=sys.stderr)
        return 1
    except (env.ToolError, RuntimeError, ValueError, OSError) as e:
        print("❌ %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
