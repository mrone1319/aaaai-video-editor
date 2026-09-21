"""命令行入口：python3 -m aaaai_editor <子命令>"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, autocut, checks, env, icons, recipes, render, showcase, theme, transcribe


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
    json.dump(sb, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("✅ 接入 %.1fs 的影片 → %s（整段保留；之后照常 captions／render／cover）" % (info["duration"], out))
    return 0


def cmd_authorize(a) -> int:
    from . import config, theme as th
    allt = th.all_themes()
    for n in a.themes:
        t = allt.get(n)
        if not t or not t.get("restricted"):
            print("「%s」不是受限风格，不需要授权。" % n)
            return 1
        print("「%s」：%s" % (n, t["restricted"]["note"]))
    if not a.yes:
        ans = input("确认你是这些品牌的社群成员或已获授权？输入 yes：").strip().lower()
        if ans != "yes":
            print("未确认，没有改动。")
            return 1
    print("✅ 已确认：%s" % "、".join(config.authorize(a.themes)))
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
    print("  %-13s %s" % ("authorized", "、".join(config.authorized()) or "（无）"))
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
    json.dump(sb, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
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
    elif k == "phone":
        print("📱 %s（只供手机预览，不是交付物）" % T.phone(a.storyboard))
    elif k == "framing":
        print("🖼 %s（1.00x 是原构图；选定后写进 storyboard 的 framing）"
              % T.framing_sheet(a.storyboard, a.at, [float(x) for x in a.levels.split(",")], a.cy))
    elif k == "cover":
        files, warn = T.cover(a.storyboard, a.at, a.text, a.sub or "", a.handle, a.y)
        from . import config
        ex = config.get("exports_dir")
        for f in files:
            print(("📦 成品：%s" if ex and f.startswith(ex) else "🖼 %s") % f)
        if warn:
            print("⚠️ " + warn)
        elif not any("1080x1350" in f for f in files):   # 横版
            print("用 Read 看 cover_check.png（横版缩图）；挑没有字幕／卡片的一帧效果最好。")
        else:
            print("文字块没有压到脸。用 Read 看 cover_check.png（左：Reels 全画面，右：主页 4:5 裁切）。")
    return 0


def cmd_render(a) -> int:
    if getattr(a, "subs", False):
        path = render.preview_subs(a.storyboard, a.t_from, a.t_to)
        print("✅ 字幕预览：%s" % path)
        return 0
    path = render.render(a.storyboard, getattr(a, "only", None), proxy=getattr(a, "proxy", False))
    print("✅ 输出：%s" % path)
    return 0


def cmd_themes(a) -> int:
    from . import config
    base = os.path.dirname(os.path.abspath(a.storyboard)) if getattr(a, "storyboard", None) else None
    ok = set(config.authorized())
    for n, t in theme.all_themes(base).items():   # 不经授权检查：受限风格也列出来，标上锁
        lock = ""
        if t.get("restricted"):
            lock = "  ✅ 已授权" if n in ok else "  🔒 %s（aaaai-editor authorize %s）" % (t["restricted"]["note"], n)
        t = theme.resolve_colors(dict(t))
        print("%-7s 强调 %s  价值 %s  陈述 %s  %s%s" % (n, t["accent"], t["value"], t["state"], t.get("desc", ""), lock))
    print("\n字体：中文 %s\n      数字 %s" % (theme.cjk_font(), theme.num_font()))
    return 0


def cmd_icons(a) -> int:
    if a.sheet:
        n = icons.sheet(os.path.abspath(a.sheet))
        print("✅ %d 个图标 → %s" % (n, os.path.abspath(a.sheet)))
    names = icons.list_icons()
    print("图标（%d）：%s" % (len(names), " ".join(names)))
    print("别名：%s" % " ".join("%s→%s" % kv for kv in sorted(icons.ALIASES.items())))
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
    json.dump(track, open(tp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
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
    tl = Timeline([tuple(c) for c in sb["cuts"]], sb["output"]["fps"])
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
    au = sub.add_parser("authorize", help="确认你有权使用受限风格（mrone／otg）")
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
    r.set_defaults(fn=cmd_render)
    pv = sub.add_parser("preview", help="快速预览（等同 render --proxy）；--subs 只烧字幕、约一分钟")
    pv.add_argument("storyboard")
    pv.add_argument("--subs", action="store_true")
    pv.add_argument("--from", dest="t_from", type=float)
    pv.add_argument("--to", dest="t_to", type=float)
    pv.set_defaults(fn=cmd_render, only=None, proxy=True)
    t = sub.add_parser("bgm", help="列出常备配乐")
    t.set_defaults(fn=cmd_tools, tool="bgm")
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
    t = sub.add_parser("phone", help="手机预览版（720 宽、≤30MB）")
    t.add_argument("storyboard"); t.set_defaults(fn=cmd_tools, tool="phone")
    t = sub.add_parser("framing", help="同一帧几种推近倍率的对比图")
    t.add_argument("storyboard"); t.add_argument("--at", type=float, default=3.0)
    t.add_argument("--levels", default="1.0,1.15,1.3,1.45"); t.add_argument("--cy", type=float, default=0.4)
    t.set_defaults(fn=cmd_tools, tool="framing")
    t = sub.add_parser("cover", help="封面：招牌金大字、15%% 安全区，出 1080×1920 与 1080×1350")
    t.add_argument("storyboard"); t.add_argument("--at", type=float, required=True)
    t.add_argument("--text", required=True); t.add_argument("--sub"); t.add_argument("--handle", help="账号名；不写就用设置里的 handle，没设就不印")
    t.add_argument("--y", type=float, default=0.55)
    t.set_defaults(fn=cmd_tools, tool="cover")
    th = sub.add_parser("themes", help="列出风格与字体（给 storyboard 可一并列出项目自定义风格）")
    th.add_argument("storyboard", nargs="?")
    th.set_defaults(fn=cmd_themes)
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
