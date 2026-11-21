"""招牌动态图卡：DM 对话重演（chat）、漏斗图（funnel）。

都是 sticker 的 kind（{"type": "sticker", "kind": "chat", ...}），用同一套矢量引擎（sticker.py）：
外观跟着风格走（贴纸风＝黑粗描边＋硬投影；其他风格＝风格自己的描边与柔和阴影），文字标记一样能用：
**强调色字**　==荧光笔底条==　[[实底块]]。

chat：私信／聊天对话一句句重演
  {"type": "sticker", "kind": "chat", "t": [3.0, 9.0], "title": "粉丝 Amy",
   "messages": [{"from": "them", "text": "请问剪片要**多久**？"},
                {"from": "me", "text": "用 AI ==五分钟==", "at": 2.2}],
   "seen": "已读"}
  · from：them（对方，左边、卡片底色泡泡、先出「…」正在输入）｜me（我，右边、强调色泡泡）
  · at：相对卡片开始的秒数（不写就自动排：前一句出现后按字数留阅读时间）
  · title：上方联系人名牌；seen：最后一句「我」下面的小字（例「已读」）
  · 对话太长会像手机一样往上滚，最上面的淡出；height（占短边比例，默认 0.62）改可视高度
  · them_fill／me_fill 换泡泡颜色；typing: false 关掉「…」

funnel：倒三角漏斗图，一层层从上往下弹出
  {"type": "sticker", "kind": "funnel", "t": [3.0, 7.0], "title": "转化漏斗",
   "items": [{"label": "曝光", "value": "10 万"}, {"label": "点进主页", "value": "8,000", "rate": "8%"},
             {"label": "私信", "value": "600", "rate": "7.5%"}, {"label": "成交", "value": "45"}]}
  · rate：从上一层到这一层的转化率，画在右边的小标签
  · step：每层出现的间隔（默认 0.32 秒）；fills：每层颜色（不写＝强调色往深色渐变；贴纸风格粉黄奶油海军轮流）
"""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

from . import richtext
from .sticker import (El, Group, _cl, _lines, _mix, _pill, color, ease_io, ellipse, on, parse, poly, rrect,
                      shape_of, text_block, text_w, wrap)


def _rrect4(x: float, y: float, w: float, h: float, tl: float, tr: float, br: float, bl: float):
    """四个角各自圆角的矩形（聊天泡泡：靠说话人那一角小圆角）。"""
    def k(r):
        return 0.5523 * r
    m = min(w, h) / 2.0
    tl, tr, br, bl = (max(0.0, min(r, m)) for r in (tl, tr, br, bl))
    return [("m", (x + tl, y)), ("l", (x + w - tr, y)),
            ("b", (x + w - tr + k(tr), y, x + w, y + tr - k(tr), x + w, y + tr)), ("l", (x + w, y + h - br)),
            ("b", (x + w, y + h - br + k(br), x + w - br + k(br), y + h, x + w - br, y + h)), ("l", (x + bl, y + h)),
            ("b", (x + bl - k(bl), y + h, x, y + h - bl + k(bl), x, y + h - bl)), ("l", (x, y + tl)),
            ("b", (x, y + tl - k(tl), x + tl - k(tl), y, x + tl, y))]


# ---------------------------------------------------------------- 聊天对话
def _near(a: str, b: str, tol: int = 90) -> bool:
    x, y = a.lstrip("#"), b.lstrip("#")
    return sum(abs(int(x[i:i + 2], 16) - int(y[i:i + 2], 16)) for i in (0, 2, 4)) < tol


def chat_times(ov: dict) -> List[Tuple[float, float]]:
    """每句的 (开始打字的时刻, 泡泡出现的时刻)，相对卡片开始。音效也用这个。"""
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    msgs = [m for m in ov.get("messages") or [] if isinstance(m, dict)]
    typing = ov.get("typing", True)
    tdur = 0.55
    out: List[Tuple[float, float]] = []
    cur = 0.25
    for m in msgs:
        them = str(m.get("from", "them")) != "me"
        if m.get("at") is not None:
            pop = float(m["at"])
            start = pop - (tdur if them and typing else 0.0)
        else:
            start = cur
            pop = start + (tdur if them and typing else 0.0)
        out.append((max(0.0, start), max(0.0, pop)))
        n = len(str(m.get("text", "")).replace("**", "").replace("==", ""))
        cur = pop + min(1.6, 0.45 + 0.055 * n)
    # 自动排的时间放不进卡片：整体按比例压缩（写了 at 的不动）
    last = max([p for _s, p in out] or [0.0])
    room = max(0.5, (t1 - t0) - 0.9)
    if last > room and not any(m.get("at") is not None for m in msgs):
        k = room / last
        out = [(s * k, p * k) for s, p in out]
    return out


def _chat(ov, th, W, H, U, fam, cx, cy, layer, sc) -> Group:
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    g = Group(t0, t1, cx, cy, ov.get("anim", "rise"), ov.get("out", "fade"), layer)
    msgs = [m for m in ov.get("messages") or [] if isinstance(m, dict)]
    em = U * 0.046 * sc
    bw, sd = _lines(U)
    pw = U * float(ov.get("width", 0.80)) * sc          # 对话区宽
    view_h = U * float(ov.get("height", 0.62)) * sc     # 可视高度（超过就往上滚）
    padx, pady = em * 0.70, em * 0.46
    av = em * 1.15                                      # 对方头像圆点
    maxw = pw * 0.78 - 2 * padx
    gap_same, gap_turn = em * 0.28, em * 0.62
    them_fill = color(ov.get("them_fill") or "cream", th)
    me_fill = color(ov.get("me_fill") or "pink", th)
    if them_fill.upper() == me_fill.upper():
        them_fill = "#FFFFFF"
    avatar_col = color(ov.get("avatar") or "yellow", th)
    times = chat_times(ov)
    typing = ov.get("typing", True)

    top = -view_h / 2.0
    hdr_h = 0.0
    title = ov.get("title")
    if title:   # 联系人名牌：头像圆点＋名字，压在对话区上方
        hem = em * 0.86
        tw = text_w(str(title), hem, fam)
        hw, hh = tw + hem * 1.25 + hem * 1.5, hem * 2.0
        hx = -pw / 2.0 + hw / 2.0
        hy = top + hh / 2.0
        p_, pw_, ph_, _a, _b = shape_of(rrect(0, 0, hw, hh, hh / 2.0))
        hfill = color("navy", th)
        g.add(El("shape", hx, hy, ax=hx, ay=hy, layer=0, path=p_, w=pw_, h=ph_, fill=hfill, bord=bw * 0.8,
                 shad=sd * 0.6, anim="pop"))
        ap, *_r = shape_of(ellipse(0, 0, hem * 0.62, hem * 0.62))
        g.add(El("shape", -pw / 2.0 + hem * 0.5 + hem * 0.62, hy, ax=hx, ay=hy, layer=1, path=ap, fill=avatar_col,
                 bord=bw * 0.5, shad=0.0, ghostable=False, anim="pop"))
        g.add(El("text", -pw / 2.0 + hem * 1.25 + hem * 0.75 + tw / 2.0, hy, ax=hx, ay=hy, layer=2,
                 body=richtext._esc(str(title)), em=hem, fam=fam, color=on(hfill, th), anim="pop"))
        hdr_h = hh + em * 0.55
    stack_top = top + hdr_h
    vis_h = view_h - hdr_h

    # 先量每个泡泡：宽高与在对话里的上缘（未滚动时）
    lay = []
    y = 0.0
    prev = None
    for i, m in enumerate(msgs):
        me = str(m.get("from", "them")) == "me"
        chars = parse(str(m.get("text", "")))
        lines = wrap(chars, em, fam, maxw)
        tw = max(text_w("".join(c for c, _ in ln).rstrip(), em, fam) for ln in lines)
        lh = em * 1.32
        tbh = lh * len(lines) - (lh - em) * 0.6
        bw_, bh_ = max(em * 1.6, tw + 2 * padx), tbh + 2 * pady
        if prev is not None:
            y += gap_same if prev == me else gap_turn
        lay.append(dict(me=me, chars=chars, w=bw_, h=bh_, y=y))
        y += bh_
        prev = me
    seen = ov.get("seen")
    seen_h = em * 0.95 if seen and any(L["me"] for L in lay) else 0.0

    # 滚动：每一句（或它的「…」）出现时，如果底部超出可视区，就在 0.28 秒内往上推
    events: List[Tuple[float, float]] = []   # (时刻, 目标位移)
    for L, (st, _pp) in zip(lay, times):
        bottom = L["y"] + L["h"] + (seen_h if L is lay[-1] else 0.0)
        events.append((st, max(0.0, bottom - vis_h)))
    SCR = 0.28

    def scroll(u: float) -> float:
        cur = 0.0
        for ta, tgt in events:
            if u <= ta:
                break
            q = _cl((u - ta) / SCR)
            cur = cur + (max(cur, tgt) - cur) * ease_io(q)
        return cur

    scroll_wins = [(ta, ta + SCR + 0.04) for ta, tgt in events if tgt > 0]

    def wrap_el(el: El, base_oy: float, h_: float, from_u: float):
        """让元素跟着对话一起往上滚，滚出可视区上缘就淡出。"""
        d0 = el.dyn
        el.windows = list(el.windows) + [w_ for w_ in scroll_wins if w_[1] > from_u]

        def dyn(u, d0=d0, base_oy=base_oy, h_=h_):
            d = d0(u) if d0 else {}
            if d is None:
                return None
            d = dict(d)
            sc_ = scroll(u)
            d["dy"] = d.get("dy", 0.0) - sc_     # 加在支点变换之后：入场弹出的支点也一起滚
            oy = d.get("oy", base_oy) - sc_
            vis = _cl((oy - h_ / 2.0 - stack_top) / max(1.0, h_ * 0.45) + 1.0)   # 上缘一过名牌就很快淡掉
            if vis <= 0.01:
                return None
            if vis < 1.0:
                d["a"] = d.get("a", 1.0) * vis
            return d
        el.dyn = dyn

    for i, (L, (st, pop)) in enumerate(zip(lay, times)):
        me = L["me"]
        fill = me_fill if me else them_fill
        x_left = -pw / 2.0 + (0.0 if me else av + em * 0.35)
        bx = (pw / 2.0 - L["w"] / 2.0) if me else (x_left + L["w"] / 2.0)
        by = stack_top + L["y"] + L["h"] / 2.0
        r = min(L["h"] / 2.0, em * 0.95)
        small = em * 0.22
        corners = (r, r, small, r) if me else (r, r, r, small)
        p_, pw_, ph_, _a, _b = shape_of(_rrect4(0, 0, L["w"], L["h"], *corners))
        # 支点：泡泡靠说话人那一角（从那里弹出来）
        ax = bx + (L["w"] / 2.0 if me else -L["w"] / 2.0)
        ay = by + L["h"] / 2.0
        grp_els: List[El] = []
        tmp = Group(0, 0, 0, 0)
        tmp.add(El("shape", bx, by, ax=ax, ay=ay, layer=10 + i * 8, delay=pop, anim="pop", path=p_, w=pw_, h=ph_,
                   fill=fill, bord=bw * 0.8, shad=sd * 0.7))
        ak = color("pink", th)
        if _near(ak, fill):   # **强调字** 和泡泡同色：改用深色块的颜色（还是太近就用白字）
            ak = color("navy", th) if not _near(color("navy", th), fill) else "#FFFFFF"
        mk = color("yellow", th)
        if _near(mk, fill):   # 荧光笔底条和泡泡同色就看不见：改用另一个泡泡的颜色或白色
            dark_txt = on(fill, th) != "#FFFFFF"   # 深字配浅底条、白字配深一点的底条
            mk = "#FFFFFF" if dark_txt else (color("pink", th) if not _near(color("pink", th), fill) else color("navy", th))
        text_block(tmp, L["chars"], em, fam, maxw, bx, by, th, on(fill, th), 11 + i * 8, None, 0.05,
                   align="left", delay=pop, anim="pop", marker=mk, accent=ak)
        for el in tmp.els:
            if el.kind == "text" or el.p.get("path") == "":
                el.ax, el.ay = ax, ay
            wrap_el(el, el.oy, L["h"], pop)
            grp_els.append(el)
        if not me:   # 对方头像圆点（贴在泡泡左下）
            ap, *_r = shape_of(ellipse(0, 0, av / 2.0, av / 2.0))
            ay_ = by + L["h"] / 2.0 - av / 2.0
            el = El("shape", -pw / 2.0 + av / 2.0, ay_, layer=10 + i * 8 + 6, delay=pop, anim="pop", path=ap,
                    fill=avatar_col, bord=bw * 0.5, shad=0.0, ghostable=False)
            wrap_el(el, ay_, av, pop)
            grp_els.append(el)
            if typing and pop - st > 0.05:   # 「…」正在输入：小泡泡里三个点轮流跳
                tw_, th_ = em * 2.5, em * 1.55
                tx = x_left + tw_ / 2.0
                ty = stack_top + L["y"] + th_ / 2.0
                tp, tpw, tph, _a, _b = shape_of(_rrect4(0, 0, tw_, th_, th_ / 2, th_ / 2, th_ / 2, small))
                el = El("shape", tx, ty, ax=tx - tw_ / 2.0, ay=ty + th_ / 2.0, layer=10 + i * 8, delay=st, anim="pop",
                        path=tp, w=tpw, h=tph, fill=them_fill, bord=bw * 0.8, shad=sd * 0.7, until=pop)
                wrap_el(el, ty, th_, st)
                grp_els.append(el)
                dot = em * 0.30
                dp, *_r = shape_of(ellipse(0, 0, dot / 2.0, dot / 2.0))
                dcol = _mix(on(them_fill, th), them_fill, 0.45)
                for j in range(3):
                    dx = tx + (j - 1) * dot * 1.7

                    def bounce(u, j=j, ty=ty, st=st):
                        ph = ((u - st) * 2.6 - j * 0.18) % 1.0
                        return {"oy": ty - em * 0.16 * max(0.0, math.sin(2 * math.pi * ph))}
                    el = El("shape", dx, ty, ax=tx - tw_ / 2.0, ay=ty + th_ / 2.0, layer=10 + i * 8 + 1, delay=st,
                            anim="pop", path=dp, fill=dcol, bord=0.0, shad=0.0, ghostable=False, until=pop,
                            windows=[(st, pop)], dyn=bounce)
                    wrap_el(el, ty, th_, st)
                    grp_els.append(el)
        for el in grp_els:
            g.add(el)
    if seen_h:
        li = max(i for i, L in enumerate(lay) if L["me"])
        L = lay[li]
        sem = em * 0.56
        sy = stack_top + L["y"] + L["h"] + sem * 0.95
        stw = text_w(str(seen), sem, fam, bold=False)
        at = times[li][1] + 0.6
        el = El("text", pw / 2.0 - stw / 2.0, sy, layer=5, delay=at, anim="fade", body=richtext._esc(str(seen)),
                em=sem, fam=fam, color="#FFFFFF", bold=False, tshad=2.0)
        wrap_el(el, sy, sem, at)
        g.add(el)
    return g


# ---------------------------------------------------------------- 漏斗图
def _funnel_fills(ov: dict, th: dict, n: int) -> List[str]:
    fills = ov.get("fills")
    if fills:
        return [color(str(fills[i % len(fills)]), th) for i in range(n)]
    if th.get("sticker_palette"):
        cyc = ("pink", "yellow", "cream", "navy")
        return [color(cyc[i % 4], th) for i in range(n)]
    a, d = color("pink", th), color("navy", th)
    return [_mix(a, d, 0.45 * i / max(1, n - 1)) for i in range(n)]


def funnel_times(ov: dict) -> List[float]:
    n = len(ov.get("items") or [])
    step = float(ov.get("step", 0.32))
    base = 0.18 if ov.get("title") else 0.0
    return [base + step * i for i in range(n)]


def _funnel(ov, th, W, H, U, fam, cx, cy, layer, sc) -> Group:
    t0, t1 = float(ov["t"][0]), float(ov["t"][1])
    g = Group(t0, t1, cx, cy, ov.get("anim", "pop"), ov.get("out", "fade"), layer)
    items = [x if isinstance(x, dict) else {"label": str(x)} for x in ov.get("items") or []]
    n = max(1, len(items))
    em = U * 0.050 * sc
    bw, sd = _lines(U)
    wtop = U * float(ov.get("width", 0.78)) * sc
    wbot = wtop * float(ov.get("narrow", 0.34))
    bh = em * 2.25
    gap = em * 0.24
    total_h = n * bh + (n - 1) * gap
    title = ov.get("title")
    title_h = em * 1.9 if title else 0.0
    y0 = -(total_h + title_h) / 2.0 + title_h
    fills = _funnel_fills(ov, th, n)
    times = funnel_times(ov)
    rot_t = -4.0 if th.get("sticker_palette") else 0.0
    if title:
        _pill(g, str(title), em * 0.78, fam, color("navy", th), th, 0.0, y0 - title_h / 2.0 - gap, rot_t, 90,
              anim="pop", U=U)

    def width_at(y):   # y 从漏斗顶部量起：宽度线性收窄
        return wtop + (wbot - wtop) * (y / total_h)
    for i, it in enumerate(items):
        ya = i * (bh + gap)
        yb = ya + bh
        wa, wb = width_at(ya), width_at(yb)
        pts = [(-wa / 2.0, 0.0), (wa / 2.0, 0.0), (wb / 2.0, bh), (-wb / 2.0, bh)]
        p_, pw_, ph_, pcx, pcy = shape_of(poly(pts))
        by = y0 + ya + bh / 2.0
        at = times[i]
        fill = fills[i]
        g.add(El("shape", 0.0, by, ax=0.0, ay=by, layer=i * 6, delay=at, anim="drop" if ov.get("drop") else "pop",
                 path=p_, w=pw_, h=ph_, fill=fill, bord=bw, shad=sd))
        txt = on(fill, th)
        val = str(it.get("value", "")) if it.get("value") is not None else ""
        lab = str(it.get("label", ""))
        vem, lem = em * 1.0, em * 0.62
        if val and lab:
            g.add(El("text", 0.0, by - bh * 0.15, ax=0.0, ay=by, layer=i * 6 + 1, delay=at, anim="pop",
                     body=richtext._esc(val), em=vem, fam=fam, color=txt))
            g.add(El("text", 0.0, by + bh * 0.25, ax=0.0, ay=by, layer=i * 6 + 1, delay=at + 0.04, anim="pop",
                     body=richtext._esc(lab), em=lem, fam=fam, color=_mix(txt, fill, 0.18), bold=False))
        elif val or lab:
            g.add(El("text", 0.0, by, ax=0.0, ay=by, layer=i * 6 + 1, delay=at, anim="pop",
                     body=richtext._esc(val or lab), em=vem * 0.86, fam=fam, color=txt))
        rate = it.get("rate")
        if rate and i > 0:   # 转化率：在这一层和上一层交界的右边，小胶囊
            rx = width_at(ya - gap / 2.0) / 2.0 + em * 0.35
            rem = em * 0.56
            rw = text_w("↓ " + str(rate), rem, fam) + rem * 1.24
            _pill(g, "↓ " + str(rate), rem, fam, color("yellow", th), th, rx + rw / 2.0, y0 + ya - gap / 2.0,
                  0.0, 80 + i * 2, delay=at + 0.12, anim="pop", U=U)
    return g


def sfx(ov: dict) -> Optional[List[Tuple[float, str, float]]]:
    kind = ov.get("kind")
    if kind == "chat":
        out = []
        for m, (_st, pop) in zip([m for m in ov.get("messages") or [] if isinstance(m, dict)], chat_times(ov)):
            out.append((pop, "click" if str(m.get("from", "them")) == "me" else "pop", -3.0))
        return out
    if kind == "funnel":
        return [(at, "pop", -4.0) for at in funnel_times(ov)]
    return None
