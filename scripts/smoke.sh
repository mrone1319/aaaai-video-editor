#!/bin/bash
# 冒烟测试：每个命令都真的跑一次，确认改动没弄坏任何功能（B-roll 只测不花钱的部分）。
#   bash scripts/smoke.sh
# 用 regress.sh 的测试素材；设置与输出都在 ~/.cache/aaaai-editor/smoke，不碰用户的项目和「成品」文件夹。
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
A="$ROOT/bin/aaaai-editor"
R="${AAAAI_EDITOR_REGRESS:-$HOME/.cache/aaaai-editor/regress}"
S="$HOME/.cache/aaaai-editor/smoke"
[ -f "$R/source.mp4" ] || bash "$ROOT/scripts/regress.sh" >/dev/null
rm -rf "$S"; mkdir -p "$S/home" "$S/p/work" "$S/projects"
printf '{"projects_dir": "%s", "exports_dir": "", "profile": ""}\n' "$S/projects" > "$S/home/config.json"
export AAAAI_EDITOR_HOME="$S/home"
cp "$R/storyboard.json" "$S/p/storyboard.json"
cp "$R/work/transcript.json" "$S/p/work/"
python3 - "$S/p/storyboard.json" "$R/source.mp4" <<'PY'
import json, sys
p, src = sys.argv[1:]
s = json.load(open(p)); s["source"] = src
s.setdefault("recipes", []).append({"use": "stat_hit", "t": [5.6, 8.0], "value": 3, "label": "三步"})
json.dump(s, open(p, "w"), ensure_ascii=False)
PY
SB="$S/p/storyboard.json"; SRC="$R/source.mp4"
pass=0; fail=0; failed=""
t() {   # t <名称> <命令…>：成功就记一笔，失败印出最后几行
  local name="$1"; shift
  if out=$("$@" 2>&1); then pass=$((pass+1)); printf "  ✅ %s\n" "$name"
  else fail=$((fail+1)); failed="$failed $name"; printf "  ❌ %s\n%s\n" "$name" "$(echo "$out" | tail -5 | sed 's/^/     /')"; fi
}
echo "== 基本"
t doctor      "$A" doctor
t version     "$A" --version
t config      "$A" config
t themes      "$A" themes
t icons       "$A" icons --sheet "$S/icons.png"
t recipes     "$A" recipes
t bgm         "$A" bgm
t keys        "$A" keys
t new         "$A" new smoke-test
echo "== 剪辑"
t transcribe  "$A" transcribe "$SRC" --out "$S/p/work/transcript2.json"
t autocut     "$A" autocut "$SRC" --out "$S/sb_cut.json"
t captions    "$A" captions "$SB"
t align       "$A" align "$SB" --dry-run
t cues        "$A" cues "$SB"
t expand      "$A" expand "$SB"
t hook-suggest "$A" hook "$SB" --suggest
t tidy        "$A" tidy "$SB"
t listen      "$A" listen "$SRC" 0 4
t probe-cut   "$A" probe-cut "$SRC" end 0 2.5 3.5 0.5 "今天"
echo "== 渲染与验收"
t preview     "$A" preview "$SB"
t proof       "$A" proof "$SB"
t render      "$A" render "$SB"
t check-sync  "$A" check-sync "$SB"   # 字幕轨已由 captions 对齐过，应当通过
t music-ab    "$A" music-ab "$SB" --at 1 --dur 5
t denoise-ab  "$A" denoise-ab "$SB" --at 1 --dur 5
t framing     "$A" framing "$SB" --at 3
t cover       "$A" cover "$SB" --at 3 --text "冒烟测试"
t phone       "$A" phone "$SB"
t showcase    "$A" showcase --out "$S/showcase.png" --only ink neon
t adopt       "$A" adopt "$S/p/out/final.mp4" --out "$S/adopted" --no-transcribe --no-captions
t hook        "$A" hook "$SB" --text "第三步是加字幕和音乐"
echo "== B-roll（不花钱的部分）与 MCP"
t broll-status "$A" broll status
t mcp python3 - "$A" <<'PY'
import json, subprocess, sys
msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "broll_status", "arguments": {}}}]
p = subprocess.run([sys.argv[1], "mcp"], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                   capture_output=True, text=True, timeout=60)
rs = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
assert len(rs) == 3 and rs[1]["result"]["tools"], p.stdout[-400:] + p.stderr[-400:]
PY
echo "==========================================="
echo "通过 $pass 项，失败 $fail 项${failed:+：$failed}"
[ "$fail" = 0 ]
