"""B-roll 流水线：免费素材 → 低价开源模型 → 可灵 →（指定时）Higgsfield，统一成可直接剪进片子的片段。

分层（没绑密钥的层自动跳过，全部可选）：
  第 0 层 stock       Pexels 免费素材库（$0；须标注 Pexels 与摄影师）
  第 1 层 opensource  Flux Schnell 首帧（约 $0.003）→ Wan 2.2 5B 图生视频（约 $0.15/条），经 fal
  第 2 层 kling       可灵 2.5 Turbo Pro 图生视频（约 $0.35/5 秒），同一把 fal 密钥
  第 3 层 higgsfield  Higgsfield DoP 图生视频（扣 Higgsfield 额度）——只在指定时用，不自动升级
  own                 用户自备素材（不生成）

费用：每次生成前估价、需确认；每个项目默认上限 $2，超出只提醒、可放行（--allow-over-budget）。
素材库：~/.aaaai-editor/broll-library/，同一个镜头（提示词＋来源＋画幅）再用不花钱。
所有产出统一成 30fps、H.264、无音轨、1080 宽／高，剪进片子时不会有格式问题。
价格为 2026-09 fal／Pexels／Higgsfield 官方页面所示，可能变动，以对方账单为准。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from typing import Dict, List, Optional, Tuple

from . import config, env, keys, net

# 官方网址；环境变量覆盖只给本机模拟测试用（只接受 https 或 localhost）
FAL_BASE = net.safe_base(os.environ.get("AAAAI_EDITOR_FAL_BASE"), "https://queue.fal.run")
PEXELS_BASE = net.safe_base(os.environ.get("AAAAI_EDITOR_PEXELS_BASE"), "https://api.pexels.com")
HF_BASE = net.safe_base(os.environ.get("AAAAI_EDITOR_HF_BASE"), "https://api.higgsfield.ai")
net.trust(FAL_BASE, PEXELS_BASE, HF_BASE)    # 密钥只会发给这三个主机

DEFAULTS = {
    "t2i": "fal-ai/flux/schnell",
    "i2v": "fal-ai/wan/v2.2-5b/image-to-video",
    "kling": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "hf_t2i": "higgsfield-ai/soul/v2/standard",
    "hf_i2v": "v1/image2video/dop",
    "hf_model": "dop-turbo",
    "budget": 2.0,
}
PRICE = {"stock": 0.0, "t2i": 0.003, "opensource": 0.15, "kling": 0.35, "higgsfield": None, "own": 0.0}
TIER_NAME = {"stock": "Pexels 免费素材", "opensource": "Wan 2.2（fal）", "kling": "可灵 2.5（fal）",
             "higgsfield": "Higgsfield", "own": "自备素材"}
NEED_KEY = {"stock": "PEXELS_API_KEY", "opensource": "FAL_KEY", "kling": "FAL_KEY", "higgsfield": "HF_CREDENTIALS"}
SIZE = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
FLUX_SIZE = {"9:16": "portrait_16_9", "16:9": "landscape_16_9", "1:1": "square_hd"}
PEXELS_ORIENT = {"9:16": "portrait", "16:9": "landscape", "1:1": "square"}


class OverBudget(RuntimeError):
    cost = 0.0      # 停下前这个镜头已经产生的费用（记进项目累计）


def cfg() -> dict:
    c = dict(DEFAULTS)
    c.update(config.load().get("broll") or {})
    return c


def lib_dir() -> str:
    d = config.path("broll-library")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------- 提示词增强
_PROMPTS = None


def _prompts() -> dict:
    global _PROMPTS
    if _PROMPTS is None:
        _PROMPTS = json.load(open(os.path.join(os.path.dirname(__file__), "broll_prompts.json"), encoding="utf-8"))
    return _PROMPTS


def enhance(prompt: str) -> Tuple[str, str, str]:
    """(首帧提示词, 运镜提示词, 镜头类型)。已经写了运镜词就不重复加。"""
    P = _prompts()
    low = prompt.lower()
    kind = next((k for k, v in P["kinds"].items() if k != "default" and any(m in low for m in v["match"])),
                "default")
    k = P["kinds"][kind]
    image = "%s, %s, no text, no watermark" % (prompt, k["image"])
    has_move = any(w in low for w in ("push", "pan", "dolly", "orbit", "tilt", "zoom", "tracking", "slow motion"))
    motion = prompt if has_move else "%s, %s" % (prompt, k["motion"])
    return image, motion, kind


# ---------------------------------------------------------------- 路由与估价
def available() -> Dict[str, bool]:
    st = keys.status()
    return {t: (st[k] if k else True) for t, k in NEED_KEY.items()}


def route(shot: dict, fallback_hf: bool = False) -> List[str]:
    p = (shot.get("provider") or "auto").lower()
    av = available()
    if p == "own":
        return ["own"]
    if p == "stock":
        chain = ["stock", "opensource", "kling"]
    elif p == "opensource":
        chain = ["opensource", "kling"]
    elif p == "kling":
        chain = ["kling"]
    elif p == "higgsfield":
        chain = ["higgsfield"]
    else:
        chain = ["opensource", "kling"] if shot.get("image") else ["stock", "opensource", "kling"]
    if fallback_hf and "higgsfield" not in chain:
        chain.append("higgsfield")
    return [t for t in chain if av.get(t)]


def tier_cost(tier: str, shot: dict) -> Optional[float]:
    base = PRICE.get(tier)
    if base is None:
        return None
    if tier in ("opensource", "kling") and not shot.get("image"):
        base += PRICE["t2i"]
    return round(base, 3)


def estimate(plan: dict, fallback_hf: bool = False) -> dict:
    rows, first, worst, unknown = [], 0.0, 0.0, False
    for s in plan.get("shots", []):
        if s.get("file") and os.path.isfile(_abs(plan, s["file"])):
            rows.append({"id": s["id"], "chain": ["已完成"], "first": 0.0, "worst": 0.0})
            continue
        hit = library_lookup(s, plan.get("aspect", "9:16"))
        if hit:
            rows.append({"id": s["id"], "chain": ["素材库复用"], "first": 0.0, "worst": 0.0})
            continue
        ch = route(s, fallback_hf or bool(s.get("fallback_higgsfield")))
        costs = [tier_cost(t, s) for t in ch]
        f = (costs[0] or 0.0) if costs else 0.0
        w = sum(c for c in costs if c is not None)
        if any(c is None for c in costs):
            unknown = True
        rows.append({"id": s["id"], "chain": [TIER_NAME[t] for t in ch] or ["（没有可用来源）"],
                     "first": f, "worst": w})
    first = sum(r["first"] or 0.0 for r in rows)
    worst = sum(r["worst"] or 0.0 for r in rows)
    budget = float(plan.get("budget", cfg()["budget"]))
    return {"rows": rows, "first": round(first, 3), "worst": round(worst, 3), "unknown": unknown,
            "budget": budget, "spent": float(plan.get("spent", 0.0))}


# ---------------------------------------------------------------- 素材库
def _key(shot: dict, aspect: str, provider: str) -> str:
    raw = json.dumps([shot.get("prompt") or "", shot.get("query") or shot.get("prompt") or "", shot.get("pick"),
                      shot.get("image") or None, aspect, provider],
                     ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]


def _index() -> List[dict]:
    p = os.path.join(lib_dir(), "index.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_index(rows: List[dict]) -> None:
    json.dump(rows, open(os.path.join(lib_dir(), "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def library_lookup(shot: dict, aspect: str) -> Optional[dict]:
    if shot.get("reuse") is False:
        return None
    p = (shot.get("provider") or "auto").lower()
    provs = [p] if p in ("stock", "opensource", "kling", "higgsfield") else ["stock", "opensource", "kling", "higgsfield"]
    for prov in provs:
        k = _key(shot, aspect, prov)
        for r in _index():
            if r["key"] == k and os.path.isfile(r["file"]):
                return r
    return None


def library_search(q: str = "") -> List[dict]:
    words = [w for w in re.split(r"[\s,，]+", q.lower()) if w]
    rows = [r for r in _index() if os.path.isfile(r["file"])]
    if not words:
        return rows
    return [r for r in rows if all(w in (r.get("prompt", "") + " " + r.get("query", "")).lower() for w in words)]


def _library_add(shot: dict, aspect: str, provider: str, src: str, cost: float, credit: str, extra: dict) -> dict:
    k = _key(shot, aspect, provider)
    dst = os.path.join(lib_dir(), "%s.mp4" % k)
    normalize(src, dst, aspect)
    rec = {"key": k, "file": dst, "provider": provider, "aspect": aspect, "prompt": shot.get("prompt", ""),
           "query": shot.get("query", ""), "cost": cost, "credit": credit,
           "created": time.strftime("%Y-%m-%d %H:%M")}
    rec.update(extra)
    rows = [r for r in _index() if r["key"] != k] + [rec]
    _save_index(rows)
    return rec


# ---------------------------------------------------------------- 统一格式
def normalize(src: str, dst: str, aspect: str, fps: int = 30, max_sec: float = 15.0) -> str:
    """铺满目标画幅、30fps、H.264、无音轨（B-roll 只要画面）。"""
    w, h = SIZE.get(aspect, SIZE["9:16"])
    env.run([env.ffmpeg(), "-y", "-v", "error", "-i", src, "-t", "%.2f" % max_sec, "-an", "-vf",
             "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,fps=%d,format=yuv420p" % (w, h, w, h, fps),
             "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-movflags", "+faststart", dst])
    return dst


IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff")


def _data_uri(path: str) -> str:
    """本地图片 → data URI（先缩到 1280 以内，避免请求太大）。iPhone 的 HEIC 先用系统 sips 转 JPEG。"""
    if not os.path.isfile(path):
        raise env.ToolError("找不到首帧图片：%s" % path)
    if not path.lower().endswith(IMAGE_EXT):   # 只上传图片：别的文件（文字、密钥档）不会被送出去
        raise env.ToolError("首帧只接受图片（%s）：%s" % (" ".join(IMAGE_EXT), os.path.basename(path)))
    d = tempfile.mkdtemp(prefix="aaaai-editor-up-")
    try:
        tmp = os.path.join(d, "up.jpg")
        if env.MAC and path.lower().endswith((".heic", ".heif")):
            env.run(["sips", "-s", "format", "jpeg", "-Z", "1280", path, "--out", tmp])
        else:
            env.run([env.ffmpeg(), "-y", "-v", "error", "-i", path, "-vf",
                     "scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease", "-q:v", "3", tmp])
        b = base64.b64encode(open(tmp, "rb").read()).decode("ascii")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return "data:image/jpeg;base64," + b


# ---------------------------------------------------------------- 各家接口
def pexels_search(query: str, aspect: str = "9:16", n: int = 8) -> List[dict]:
    k = keys.get("PEXELS_API_KEY")
    if not k:
        raise env.ToolError("没有绑定 Pexels 密钥（免费申请：%s，然后 aaaai-editor keys set PEXELS_API_KEY）"
                            % keys.KEYS["PEXELS_API_KEY"]["url"])
    from urllib.parse import urlencode
    url = "%s/v1/videos/search?%s" % (PEXELS_BASE, urlencode(
        {"query": query, "orientation": PEXELS_ORIENT.get(aspect, "portrait"), "size": "medium", "per_page": n}))
    data = net.request("GET", url, headers={"Authorization": k})
    tw, th = SIZE.get(aspect, SIZE["9:16"])
    out = []
    for v in data.get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("link") and (f.get("file_type") or "video/mp4") == "video/mp4"
                 and f.get("width") and f.get("height")]
        if not files:
            continue
        best = min(files, key=lambda f: abs(min(f["width"], f["height"]) - min(tw, th)))
        out.append({"id": v["id"], "url": v.get("url"), "user": (v.get("user") or {}).get("name", ""),
                    "user_url": (v.get("user") or {}).get("url", ""), "duration": v.get("duration"),
                    "thumb": v.get("image"), "file": best["link"], "w": best["width"], "h": best["height"]})
    return out


def fal_run(model: str, body: dict, timeout: int = 600) -> dict:
    k = keys.get("FAL_KEY")
    if not k:
        raise env.ToolError("没有绑定 fal 密钥")
    h = {"Authorization": "Key " + k}
    sub = net.request("POST", "%s/%s" % (FAL_BASE, model), headers=h, body=body)
    st_url, res_url = sub.get("status_url"), sub.get("response_url")
    if not st_url:
        raise env.ToolError("fal 没有返回 status_url：%s" % net.redact(str(sub)[:200], [k]))
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = net.request("GET", st_url, headers=h)
        s = st.get("status")
        if s == "COMPLETED":
            return net.request("GET", res_url, headers=h)
        if s not in ("IN_QUEUE", "IN_PROGRESS"):
            raise env.ToolError("fal 任务状态异常：%s" % net.redact(str(st)[:200], [k]))
        time.sleep(3)
    raise env.ToolError("fal 任务超时（%d 秒）" % timeout)


def hf_run(path: str, body: dict, timeout: int = 900) -> dict:
    c = keys.get("HF_CREDENTIALS")
    if not c:
        raise env.ToolError("没有绑定 Higgsfield 密钥（格式 KEY_ID:KEY_SECRET）")
    h = {"Authorization": "Key " + c}
    sub = net.request("POST", "%s/%s" % (HF_BASE, path.lstrip("/")), headers=h, body=body)
    st_url = sub.get("status_url") or ("%s/requests/%s/status" % (HF_BASE, sub.get("request_id")))
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = net.request("GET", st_url, headers=h)
        s = st.get("status")
        if s == "completed":
            return st
        if s in ("failed", "nsfw"):
            raise env.ToolError("Higgsfield 任务%s（额度已退还）" % ("失败" if s == "failed" else "被内容审核拒绝"))
        time.sleep(4)
    raise env.ToolError("Higgsfield 任务超时（%d 秒）" % timeout)


# ---------------------------------------------------------------- 单个镜头
def _first_frame(shot: dict, plan: dict, image_prompt: str, aspect: str, tier: str, cache: dict) -> Tuple[str, float]:
    """首帧：用户给的图（自己的照片／影片截图 → 生成的人会是你本人）优先，否则 Flux 生成。
    同一镜头换层重试时沿用已生成的首帧，不重复付费。"""
    if "img" in cache:
        return cache["img"], 0.0
    if shot.get("image"):
        cache["img"] = _data_uri(_abs(plan, shot["image"]))
        return cache["img"], 0.0
    if tier == "higgsfield" and not keys.has("FAL_KEY"):
        r = hf_run(cfg()["hf_t2i"], {"prompt": image_prompt})
        cache["img"] = r["images"][0]["url"]
        return cache["img"], 0.0
    r = fal_run(cfg()["t2i"], {"prompt": image_prompt, "image_size": FLUX_SIZE.get(aspect, "portrait_16_9"),
                               "num_inference_steps": 4})
    cache["img"] = r["images"][0]["url"]
    return cache["img"], PRICE["t2i"]


def gen_shot(shot: dict, plan: dict, work: str, allow_over: bool, fallback_hf: bool, log=print,
             fresh: bool = False) -> dict:
    aspect = plan.get("aspect", "9:16")
    hit = None if fresh else library_lookup(shot, aspect)
    if hit:
        log("  ♻️ %s 素材库已有（%s），直接复用，$0" % (shot["id"], TIER_NAME.get(hit["provider"], hit["provider"])))
        return {"file": hit["file"], "provider": hit["provider"], "cost": 0.0, "credit": hit.get("credit", "")}
    chain = route(shot, fallback_hf or bool(shot.get("fallback_higgsfield")))
    if not chain:
        raise env.ToolError("%s 没有可用来源：可绑定 Pexels（免费）或 fal（按次付费）密钥——aaaai-editor keys 看说明；"
                            "或者把自己的素材放进项目 assets/，写进计划的 file" % shot["id"])
    image_p, motion_p, kind = enhance(shot.get("prompt") or shot.get("query") or "")
    budget = float(plan.get("budget", cfg()["budget"]))
    errors, cache, sunk = [], {}, 0.0      # sunk：失败层已经产生的费用（例如首帧已生成）
    for tier in chain:
        c = tier_cost(tier, shot)
        if c and "img" in cache:
            c = round(c - PRICE["t2i"], 3) if not shot.get("image") else c
        if c and plan.get("spent", 0.0) + sunk + c > budget + 1e-9 and not allow_over:
            ob = OverBudget("%s 用 %s 要 $%.2f，会超过这个项目的上限 $%.2f（已花 $%.2f）——需要你同意才继续"
                            % (shot["id"], TIER_NAME[tier], c, budget, plan.get("spent", 0.0) + sunk))
            ob.cost = sunk
            raise ob
        try:
            tmp = os.path.join(work, "broll_raw_%s_%s.mp4" % (shot["id"], tier))
            spent, credit, extra = sunk, "", {"kind": kind}
            if tier == "stock":
                cands = pexels_search(shot.get("query") or shot.get("prompt", ""), aspect)
                if not cands:
                    raise env.ToolError("Pexels 没有结果")
                need = (float(shot["t"][1]) - float(shot["t"][0])) if shot.get("t") else 0.0
                long_enough = [x for x in cands if (x.get("duration") or 0) >= need] or cands   # 够长才不会循环跳接
                pick = next((x for x in cands if str(x["id"]) == str(shot.get("pick"))), long_enough[0])
                net.download(pick["file"], tmp)
                credit = "Pexels · %s（%s）%s" % (pick["user"], pick["user_url"], pick["url"])
                extra.update(pexels_id=pick["id"], picked=bool(shot.get("pick")))
            elif tier in ("opensource", "kling"):
                img, s1 = _first_frame(shot, plan, image_p, aspect, tier, cache)
                spent += s1
                sunk += s1
                model = cfg()["i2v"] if tier == "opensource" else cfg()["kling"]
                body = {"prompt": motion_p, "image_url": img}
                if tier == "kling":
                    body.update(duration="5", negative_prompt=_prompts()["negative"])
                r = fal_run(model, body)
                net.download(r["video"]["url"], tmp)
                spent += PRICE[tier]
                credit = "AI 生成（%s，fal）" % model
                extra.update(model=model)
            elif tier == "higgsfield":
                img, s1 = _first_frame(shot, plan, image_p, aspect, tier, cache)
                spent += s1
                sunk += s1
                r = hf_run(cfg()["hf_i2v"], {"model": cfg()["hf_model"], "prompt": motion_p,
                                             "input_images": [{"type": "image_url", "image_url": img}]})
                net.download(r["video"]["url"], tmp)
                credit = "AI 生成（Higgsfield %s）" % cfg()["hf_model"]
            else:
                raise env.ToolError("自备素材请直接写 file")
            rec = _library_add(shot, aspect, tier, tmp, spent, credit, extra)
            try:
                os.remove(tmp)
            except OSError:
                pass
            log("  ✅ %s ← %s%s" % (shot["id"], TIER_NAME[tier], ("，$%.3f" % spent) if spent else "，$0"))
            return {"file": rec["file"], "provider": tier, "cost": spent, "credit": credit}
        except (env.ToolError, net.HttpError, KeyError, IndexError, OSError) as e:
            errors.append("%s：%s" % (TIER_NAME[tier], e))
            log("  ⚠️ %s 用 %s 失败：%s%s" % (shot["id"], TIER_NAME[tier], str(e)[:160],
                                          "，改用下一层" if tier != chain[-1] else ""))
    e = env.ToolError("%s 所有来源都失败：%s%s" % (shot["id"], "；".join(errors),
                                                 "（首帧已花 $%.3f）" % sunk if sunk else ""))
    e.cost = sunk
    raise e


def _abs(plan: dict, p: str) -> str:
    return os.path.normpath(os.path.join(plan.get("_base", ""), os.path.expanduser(p)))


# ---------------------------------------------------------------- 计划档
def load_plan(path: str) -> dict:
    plan = json.load(open(path, encoding="utf-8"))
    plan["_base"] = os.path.dirname(os.path.abspath(path))
    plan.setdefault("aspect", "9:16")
    plan.setdefault("budget", cfg()["budget"])
    plan.setdefault("spent", 0.0)
    for i, s in enumerate(plan.get("shots", [])):
        s.setdefault("id", "s%d" % (i + 1))
    return plan


def save_plan(plan: dict, path: str) -> None:
    out = {k: v for k, v in plan.items() if not k.startswith("_")}
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def template(sb_path: str) -> str:
    """给项目建一份空的 B-roll 计划（Claude 照 cues 填镜头）。"""
    base = os.path.dirname(os.path.abspath(sb_path))
    p = os.path.join(base, "broll_plan.json")
    if not os.path.isfile(p):
        sb = json.load(open(sb_path, encoding="utf-8"))
        o = sb.get("output", {})
        w, h = int(o.get("width", 1080)), int(o.get("height", 1920))
        aspect = "9:16" if h > w else ("16:9" if w > h else "1:1")
        json.dump({"aspect": aspect, "budget": cfg()["budget"], "spent": 0.0, "shots": []},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return p


def generate(plan_path: str, allow_over: bool = False, fallback_hf: bool = False, only: Optional[List[str]] = None,
             log=print) -> dict:
    plan = load_plan(plan_path)
    work = os.path.join(plan["_base"], "work")
    os.makedirs(work, exist_ok=True)
    done, failed = 0, []
    for s in plan.get("shots", []):
        if only and s["id"] not in only:
            continue
        if s.get("file") and os.path.isfile(_abs(plan, s["file"])) and not only:   # --only 指名的镜头重做
            continue
        if (s.get("provider") or "") == "own":
            failed.append((s["id"], "自备素材要写 file"))
            continue
        try:
            r = gen_shot(s, plan, work, allow_over, fallback_hf, log, fresh=bool(only))   # --only＝重做，不拿素材库
            s.update(file=r["file"], source=r["provider"], cost=r["cost"], credit=r["credit"])
            plan["spent"] = round(plan.get("spent", 0.0) + r["cost"], 4)
            done += 1
        except OverBudget as e:
            plan["spent"] = round(plan.get("spent", 0.0) + e.cost, 4)
            log("⛔ " + str(e))
            save_plan(plan, plan_path)
            return {"done": done, "failed": failed, "stopped": str(e), "spent": plan["spent"]}
        except env.ToolError as e:
            plan["spent"] = round(plan.get("spent", 0.0) + getattr(e, "cost", 0.0), 4)
            failed.append((s["id"], str(e)))
        save_plan(plan, plan_path)   # 每完成一个就存，中途断掉不会重复付费
    return {"done": done, "failed": failed, "stopped": None, "spent": plan["spent"]}


def sheet(plan_path: str) -> str:
    """把每个镜头取中间一帧拼成审片图（给人看，决定要不要换）。"""
    plan = load_plan(plan_path)
    shots = [s for s in plan.get("shots", []) if s.get("file") and os.path.isfile(_abs(plan, s["file"]))]
    if not shots:
        raise env.ToolError("还没有生成好的镜头")
    work = os.path.join(plan["_base"], "work")
    tiles = []
    for s in shots:
        f = _abs(plan, s["file"])
        d = env.probe(f)["duration"]
        t = os.path.join(work, "broll_tile_%s.png" % s["id"])
        label = "%s %s" % (s["id"], s.get("source", ""))
        env.run([env.ffmpeg(), "-y", "-v", "error", "-ss", "%.2f" % (d / 2), "-i", f, "-frames:v", "1", "-vf",
                 "scale=270:-2,drawtext=text='%s':fontcolor=white:fontsize=18:box=1:boxcolor=black@0.6:x=8:y=8"
                 % label.replace(":", "\\:").replace("'", ""), t])
        tiles.append(t)
    out = os.path.join(work, "broll_sheet.png")
    args = [env.ffmpeg(), "-y", "-v", "error"]
    for t in tiles:
        args += ["-i", t]
    g = "".join("[%d:v]" % i for i in range(len(tiles))) + "hstack=inputs=%d[o]" % len(tiles) if len(tiles) > 1 \
        else "[0:v]null[o]"
    env.run(args + ["-filter_complex", g, "-map", "[o]", "-frames:v", "1", out])
    return out


def place(plan_path: str, sb_path: str) -> Tuple[int, str]:
    """把生成好的镜头写进 storyboard 的 overlays（替换先前放的同一镜头），并写出素材署名清单。"""
    plan = load_plan(plan_path)
    sb = json.load(open(sb_path, encoding="utf-8"))
    ovs = [o for o in sb.get("overlays", []) if not str(o.get("broll_id", "")).startswith("plan:")]
    n = 0
    for s in plan.get("shots", []):
        if not (s.get("file") and s.get("t")):
            continue
        o = {"type": "broll", "t": s["t"], "file": _abs(plan, s["file"]), "broll_id": "plan:%s" % s["id"],
             "mode": s.get("mode", "fullscreen")}
        slot = float(s["t"][1]) - float(s["t"][0])
        try:
            clip_d = env.probe(o["file"])["duration"] - float(s.get("from", 0))
            if clip_d + 0.05 < slot:
                print("⚠️ %s 片段只有 %.1f 秒、时段 %.1f 秒，会循环播放（看得出跳接）：缩短时段，或换一条更长的"
                      % (s["id"], clip_d, slot))
        except env.ToolError:
            pass
        for k in ("from", "fade", "lift", "motion"):
            if k in s:
                o[k] = s[k]
        ovs.append(o)
        n += 1
    sb["overlays"] = ovs
    from . import store
    store.write(sb_path, sb, source="broll")
    credits = [s["credit"] for s in plan.get("shots", []) if s.get("credit")]
    cp = os.path.join(os.path.dirname(os.path.abspath(sb_path)), "out", "broll_credits.txt")
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    with open(cp, "w", encoding="utf-8") as f:
        f.write("B-roll 素材来源（Pexels 素材请在贴文或简介中标注 Pexels 与摄影师）\n")
        for c in credits:
            f.write("· %s\n" % c)
    return n, cp


def clip(prompt: str, out: str, aspect: str = "9:16", provider: str = "auto", image: Optional[str] = None,
         query: Optional[str] = None, allow_over: bool = False, fallback_hf: bool = False, log=print) -> dict:
    """单条镜头（不需要项目）：给一句描述，出一条可直接用的 B-roll。"""
    shot = {"id": "clip", "prompt": prompt, "query": query or prompt, "provider": provider}
    if image:
        shot["image"] = os.path.abspath(os.path.expanduser(image))
    plan = {"aspect": aspect, "budget": cfg()["budget"], "spent": 0.0, "_base": os.getcwd(), "shots": [shot]}
    work = os.path.join(lib_dir(), "tmp")
    os.makedirs(work, exist_ok=True)
    r = gen_shot(shot, plan, work, allow_over, fallback_hf, log)
    out = os.path.abspath(os.path.expanduser(out))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.abspath(r["file"]) != out:
        import shutil
        shutil.copyfile(r["file"], out)
    r["out"] = out
    return r


def status_text() -> str:
    av, st = available(), keys.status()
    lines = ["B-roll 来源（全部可选，没绑的自动跳过）："]
    for t in ("stock", "opensource", "kling", "higgsfield"):
        k = NEED_KEY[t]
        lines.append("  %s %-14s %s" % ("✅" if av[t] else "—", TIER_NAME[t],
                                        "已绑定 %s" % k if st[k] else "未绑定（aaaai-editor keys set %s）" % k))
    lines.append("  ✅ 自备素材       永远可用（放进项目 assets/）")
    lines.append("每个项目默认花费上限 $%.2f（aaaai-editor config --set broll.budget=5 可改；超出会提醒、你同意才继续）"
                 % float(cfg()["budget"]))
    return "\n".join(lines)


def estimate_text(e: dict) -> str:
    lines = ["镜头   路线（失败才往下）                          预计"]
    for r in e["rows"]:
        hf = r["chain"] and r["chain"][0] == TIER_NAME["higgsfield"]
        lines.append("  %-5s %-42s %s%s" % (r["id"], " → ".join(r["chain"]),
                                             "扣 Higgsfield 额度" if hf else "$%.3f" % r["first"],
                                                ("（最坏 $%.2f）" % r["worst"]) if r["worst"] > r["first"] else ""))
    lines.append("合计：预计 $%.3f，最坏 $%.3f%s；本项目已花 $%.2f，上限 $%.2f"
                 % (e["first"], e["worst"], "（Higgsfield 另扣额度）" if e["unknown"] else "", e["spent"], e["budget"]))
    if e["spent"] + e["first"] > e["budget"]:
        lines.append("⚠️ 会超过上限：需要你同意（--allow-over-budget）才继续。")
    return "\n".join(lines)
