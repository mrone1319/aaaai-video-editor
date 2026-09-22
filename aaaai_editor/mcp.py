"""MCP 服务器（stdio、JSON-RPC 2.0，纯标准库）：让 Claude Desktop／Codex／Cursor 等把 B-roll 当工具调用。

注册：
  Claude Code   claude mcp add aaaai-editor -- ~/.aaaai-editor/bin/aaaai-editor mcp
  Codex         codex mcp add aaaai-editor -- ~/.aaaai-editor/bin/aaaai-editor mcp
  Claude Desktop 在 claude_desktop_config.json 的 mcpServers 加 {"aaaai-editor": {"command": "~/.aaaai-editor/bin/aaaai-editor 的完整路径", "args": ["mcp"]}}

要花钱的工具一律两步：先不带 confirmed 调用拿估价 → 问过用户 → 带 confirmed=true 再调用。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import traceback

from . import __version__, config, env

PROTO = "2025-06-18"
SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")

_ASPECT = {"type": "string", "enum": ["9:16", "16:9", "1:1"], "default": "9:16", "description": "画幅"}
_PROV = {"type": "string", "enum": ["auto", "stock", "opensource", "kling", "higgsfield"], "default": "auto",
         "description": "来源。auto＝免费素材优先、再低价开源模型；higgsfield 只在用户指定时用"}

TOOLS = [
    {"name": "broll_status",
     "description": "看 B-roll 各来源是否可用（哪些密钥已绑定）与项目花费上限。免费、不联网。",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "broll_search",
     "description": "在 Pexels 免费素材库搜影片（$0，须绑定 PEXELS_API_KEY）。返回候选 id／作者／链接。",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "英文关键词效果最好"},
                                                      "aspect_ratio": _ASPECT, "n": {"type": "integer", "default": 8}},
                     "required": ["query"]}},
    {"name": "broll_estimate",
     "description": "估算生成一条 B-roll 的费用与路线（不花钱）。",
     "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "aspect_ratio": _ASPECT,
                                                      "provider": _PROV, "image": {"type": "string"}},
                     "required": ["prompt"]}},
    {"name": "generate_broll_clip",
     "description": "生成一条 B-roll 空镜（统一成 30fps H.264 无音轨）。默认先找免费素材，找不到再用低价开源模型。"
                    "会花钱时：第一次调用只返回估价，必须先问用户，用户同意后带 confirmed=true 再调用。",
     "inputSchema": {"type": "object", "properties": {
         "prompt": {"type": "string", "description": "画面描述，例如 'Close-up slow motion coffee pouring'"},
         "aspect_ratio": _ASPECT, "provider": _PROV,
         "image": {"type": "string", "description": "可选：首帧图片路径（用自己的照片，生成的人会是本人）"},
         "output_filename": {"type": "string", "description": "输出路径；不写就放到项目目录的 broll-clips/"},
         "confirmed": {"type": "boolean", "default": False, "description": "用户已同意这次费用"},
         "allow_over_budget": {"type": "boolean", "default": False, "description": "用户已同意超出上限"},
         "fallback_higgsfield": {"type": "boolean", "default": False}},
         "required": ["prompt"]}},
    {"name": "broll_plan",
     "description": "对项目的 broll_plan.json：action=estimate 估价／gen 生成（要 confirmed）／sheet 审片图／place 放进 storyboard。",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["estimate", "gen", "sheet", "place"]},
         "plan": {"type": "string", "description": "broll_plan.json 路径"},
         "storyboard": {"type": "string", "description": "place 时需要"},
         "confirmed": {"type": "boolean", "default": False}, "allow_over_budget": {"type": "boolean", "default": False},
         "fallback_higgsfield": {"type": "boolean", "default": False}},
         "required": ["action", "plan"]}},
    {"name": "broll_library",
     "description": "查已生成／下载过的 B-roll 素材库（再用不花钱）。",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "default": ""}}}},
    {"name": "doctor", "description": "检查 aaaai-editor 依赖（ffmpeg、whisper、字体等）。",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _path(p):
    """MCP 进程的工作目录不可靠：相对路径一律按项目目录（projects_dir）解析。"""
    if not p:
        return p
    p = os.path.expanduser(p)
    return p if os.path.isabs(p) else os.path.join(config.get("projects_dir"), p)


def _safe_out(p: str) -> str:
    """MCP 由别的 AI 调用：输出只能写成家目录里的影片文件，不能写进隐藏目录（~/.ssh、~/.zshrc 这类）。"""
    rp = os.path.realpath(p)
    home = os.path.realpath(os.path.expanduser("~"))
    rel = os.path.relpath(rp, home)
    if rel.startswith("..") or any(part.startswith(".") for part in rel.split(os.sep)):
        raise ValueError("输出路径必须在家目录里、不能是隐藏目录：%s" % p)
    if not rp.lower().endswith((".mp4", ".mov")):
        raise ValueError("输出文件必须是 .mp4 或 .mov：%s" % p)
    return rp


def _call(name: str, a: dict) -> str:
    from . import broll
    a = dict(a)
    for k in ("plan", "storyboard", "image", "output_filename"):
        if a.get(k):
            a[k] = _path(a[k])
    if a.get("output_filename"):
        a["output_filename"] = _safe_out(a["output_filename"])
    if name == "broll_status":
        return broll.status_text()
    if name == "broll_search":
        rows = broll.pexels_search(a["query"], a.get("aspect_ratio", "9:16"), int(a.get("n", 8)))
        return json.dumps(rows, ensure_ascii=False, indent=1) + "\n（使用须标注 Pexels 与摄影师）"
    if name in ("broll_estimate", "generate_broll_clip"):
        aspect = a.get("aspect_ratio", "9:16")
        shot = {"id": "clip", "prompt": a["prompt"], "provider": a.get("provider", "auto"), "image": a.get("image")}
        e = broll.estimate({"aspect": aspect, "budget": broll.cfg()["budget"], "shots": [shot]},
                           bool(a.get("fallback_higgsfield")))
        txt = broll.estimate_text(e)
        if name == "broll_estimate":
            return txt
        if e["first"] > 0 and not a.get("confirmed"):
            return txt + "\n\n需要用户确认：请把上面的费用告诉用户，同意后带 confirmed=true 再调用。"
        out = a.get("output_filename") or os.path.join(
            config.get("projects_dir"), "broll-clips", "broll_%s.mp4" % __import__("time").strftime("%Y%m%d_%H%M%S"))
        r = broll.clip(a["prompt"], out, aspect, shot["provider"], a.get("image"), None,
                       bool(a.get("allow_over_budget")), bool(a.get("fallback_higgsfield")))
        return "✅ %s\n来源：%s｜花费 $%.3f\n署名：%s" % (r["out"], r["provider"], r["cost"], r["credit"])
    if name == "broll_plan":
        act, plan = a["action"], a["plan"]
        if act == "estimate":
            return broll.estimate_text(broll.estimate(broll.load_plan(plan), bool(a.get("fallback_higgsfield"))))
        if act == "gen":
            e = broll.estimate(broll.load_plan(plan), bool(a.get("fallback_higgsfield")))
            if e["first"] > 0 and not a.get("confirmed"):
                return broll.estimate_text(e) + "\n\n需要用户确认：同意后带 confirmed=true 再调用。"
            r = broll.generate(plan, bool(a.get("allow_over_budget")), bool(a.get("fallback_higgsfield")))
            return json.dumps(r, ensure_ascii=False)
        if act == "sheet":
            return "审片图：%s" % broll.sheet(plan)
        if act == "place":
            n, cp = broll.place(plan, a["storyboard"])
            return "放进 %d 条；署名清单 %s" % (n, cp)
    if name == "broll_library":
        return json.dumps(broll.library_search(a.get("query", "")), ensure_ascii=False, indent=1)
    if name == "doctor":
        env.doctor()
        return ""
    raise KeyError("没有这个工具：%s" % name)


def _handle(msg: dict):
    m, mid = msg.get("method"), msg.get("id")
    if mid is None:          # 通知，不回
        return None
    if m == "initialize":
        want = (msg.get("params") or {}).get("protocolVersion")
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": want if want in SUPPORTED else PROTO, "capabilities": {"tools": {}},
            "serverInfo": {"name": "aaaai-editor", "version": __version__}}}
    if m == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if m == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if m == "tools/call":
        p = msg.get("params") or {}
        buf = io.StringIO()
        err = False
        try:
            with contextlib.redirect_stdout(buf):     # stdout 是协议通道，过程日志收进结果
                txt = _call(p.get("name", ""), p.get("arguments") or {})
        except Exception as e:  # noqa: BLE001 — 工具错误要回给调用方，不能让服务器死掉
            err, txt = True, "❌ %s" % e
            traceback.print_exc(file=sys.stderr)
        log = buf.getvalue().strip()
        text = (log + "\n\n" + txt).strip() if log else txt
        return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": err}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found: %s" % m}}


def serve() -> int:
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                  "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            out.flush()
            continue
        rs = [r for r in (_handle(one) for one in (msg if isinstance(msg, list) else [msg])) if r is not None]
        if rs:
            out.write(json.dumps(rs if isinstance(msg, list) else rs[0], ensure_ascii=False) + "\n")
            out.flush()
    return 0
