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
t cover-frames "$A" cover-frames "$SB" --n 4
t cardpics-l  "$A" cardpics "$SB" --list
t cardpics    "$A" cardpics "$SB" --pick 1 --size 1350,1080 --bg blur
t cover       "$A" cover "$SB" --pick 2 --kicker "测试 · 封面" --text "冒烟测试" --sub "第三行"
t cover-2line "$A" cover "$SB" --at 3 --text "这是一个比较长的封面标题测试" --layout center
t phone       "$A" phone "$SB"
t showcase    "$A" showcase --out "$S/showcase.png" --only ink neon
t adopt       "$A" adopt "$S/p/out/final.mp4" --out "$S/adopted" --no-transcribe --no-captions
t hook        "$A" hook "$SB" --text "第三步是加字幕和音乐"
t sfx         "$A" sfx
# 卡片收合＋组合卡片＋小组件＋音效（测试画面没有人，接管不做头冲出框）
python3 - "$R" "$S" <<'PYX'
import json, os, subprocess, sys
R, S = sys.argv[1:]
os.makedirs(S + "/c/work", exist_ok=True); os.makedirs(S + "/c/assets", exist_ok=True)
subprocess.run(["ffmpeg" if not os.path.exists("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg") else "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
                "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=#E8EEF5:s=800x500", "-frames:v", "1", S + "/c/assets/shot.png"], check=True)
s = json.load(open(R + "/storyboard.json")); s["source"] = R + "/source.mp4"; s.pop("music", None)
s["recipes"] = [{"use": "takeover", "t": [1.0, 5.0], "bg": "paper", "popout": False, "sfx": "whoosh"},
                {"use": "takeover", "t": [9.0, 14.0], "bg": "paper", "popout": False, "hold": True}]
s["overlays"] = [{"type": "proof", "t": [1.2, 5.0], "file": "assets/shot.png", "kicker": "示例", "pill": "9/22", "stamp": "+$1", "stamp_at": 2.0, "stamp_sfx": "coin"},
                 {"type": "confetti", "t": [6.0, 8.0], "sfx": "confetti"},
                 {"type": "countdown", "t": [6.0, 8.0], "from": 2},
                 {"type": "glow", "t": [6.0, 8.5], "box": [0.1, 0.6, 0.8, 0.1]},
                 {"type": "flow", "t": [9.2, 11.0], "kicker": "流程", "steps": [{"icon": "camera", "top": "拍", "big": "3 分钟", "at": 9.3}, {"icon": "money", "top": "赚", "big": "进账", "at": 10.0}]},
                 {"type": "cta", "t": [11.0, 14.0], "hold": True, "question": "怎么**入门**", "keyword": "留言", "badge": "发给你", "sfx": "ding"},
                 {"type": "cta", "t": [8.2, 9.0], "question": "旧版**药丸**", "keyword": "工具", "style": "pill"}]
s["overlays"] += [{"type": "gauge", "t": [14.2, 16.0], "kicker": "完成度", "value": 0.72, "label": "测试"},
                  {"type": "rank", "t": [16.2, 18.0], "title": "排行", "items": [{"label": "A", "value": 30}, {"label": "B", "value": 12}]},
                  {"type": "timeline", "t": [18.2, 20.0], "title": "流程", "items": [{"time": "09:00", "text": "拍"}, {"time": "10:00", "text": "发"}]},
                  {"type": "rating", "t": [20.2, 22.0], "kicker": "评价", "value": 4.6, "label": "测试"}]
os.makedirs(S + "/c/assets/icons", exist_ok=True)   # 项目图标库：一张单色图片图标
subprocess.run(["ffmpeg" if not os.path.exists("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg") else "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
                "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=white@1:s=128x128,format=rgba",
                "-frames:v", "1", S + "/c/assets/icons/smoke-icon.png"], check=True)
s["overlays"].append({"type": "icons", "t": [22.2, 24.0], "title": "图标库",
                      "items": [{"icon": "rocket", "label": "内建"}, {"icon": "smoke-icon", "label": "图片"}]})
s["recipes"] = [{"use": "brand_open", "t": [0.3, 2.4], "kicker": "测试", "text": "品牌片头", "sub": "@demo"}]
s["transitions"] = [{"t": 6.0, "type": "whip"}]
json.dump(s, open(S + "/c/storyboard.json", "w"), ensure_ascii=False)
PYX
cp "$R/work/transcript.json" "$S/c/work/"
t card-mode   "$A" preview "$S/c/storyboard.json"
# 贴纸弹跳风格：每种贴纸（含图片贴纸）＋斜色带转场＋打字框字幕
python3 - "$R" "$S" <<'PYK'
import json, os, shutil, sys
R, S = sys.argv[1:]
os.makedirs(S + "/k/work", exist_ok=True); os.makedirs(S + "/k/assets", exist_ok=True)
shutil.copy(S + "/c/assets/shot.png", S + "/k/assets/shot.png")
s = json.load(open(R + "/storyboard.json")); s["source"] = R + "/source.mp4"; s.pop("music", None); s.pop("recipes", None)
s["style"] = "sticker"; s["transitions"] = [{"t": 6.0, "type": "band"}]
s["overlays"] = [{"type": "sticker", "kind": "box", "t": [0.3, 1.8], "text": "我**不想**拍==短视频==[[AI]]", "tag": "只需", "icon": "phone_play"},
                 {"type": "sticker", "kind": "tag", "t": [0.5, 1.8], "text": "最快", "fill": "yellow", "xy": [0.3, 0.6]},
                 {"type": "sticker", "kind": "slam", "t": [2.0, 3.2], "text": "赶快"},
                 {"type": "sticker", "kind": "icon", "t": [2.0, 3.2], "name": "camera_off", "xy": [0.75, 0.3]},
                 {"type": "sticker", "kind": "badge", "t": [3.4, 5.4], "values": [8, 22, 24], "unit": "小时", "label": "最快"},
                 {"type": "sticker", "kind": "checklist", "t": [6.4, 8.4], "items": ["选**模板**", "上传", "生成"]},
                 {"type": "sticker", "kind": "cta", "t": [8.6, 10.6], "text": "点击链接"},
                 {"type": "sticker", "kind": "polaroid", "t": [10.8, 12.2], "file": "assets/shot.png"},
                 {"type": "sticker", "kind": "fan", "t": [12.4, 13.8], "files": ["assets/shot.png"] * 3},
                 {"type": "sticker", "kind": "flip", "t": [14.0, 15.6], "files": ["assets/shot.png", "assets/shot.png"]},
                 {"type": "title", "t": [16.0, 18.0], "text": "普通卡片也是**贴纸**"}]
json.dump(s, open(S + "/k/storyboard.json", "w"), ensure_ascii=False)
PYK
cp "$R/work/transcript.json" "$S/k/work/"
t sticker     "$A" preview "$S/k/storyboard.json"
# 关键词触发＋章节目录＋整屏特效＋掉落字／留言列／影片网格
python3 - "$R" "$S" <<'PYR'
import json, os, shutil, sys
R, S = sys.argv[1:]
os.makedirs(S + "/r/work", exist_ok=True); os.makedirs(S + "/r/assets", exist_ok=True)
shutil.copy(S + "/c/assets/shot.png", S + "/r/assets/shot.png")
s = json.load(open(R + "/storyboard.json")); s["source"] = R + "/source.mp4"; s.pop("music", None); s.pop("recipes", None)
s["style"] = "sticker"; s["toc"] = {"title": "测试目录", "footer": "收藏"}
s["triggers"] = [{"say": "转录", "fx": {"type": "phone"}, "dur": 1.6, "toc": "手机框"},
                 {"say": "停顿", "card": {"type": "sticker", "kind": "drop", "text": "CUT", "sub": "掉落字"}, "dur": 1.6, "toc": "掉落字"},
                 {"say": "字幕", "fx": {"type": "split"}, "dur": 1.6, "toc": "前后对比"},
                 {"say": "音乐", "fx": {"type": "film"}, "dur": 1.6, "toc": "底片感"},
                 {"say": "简单", "card": {"type": "sticker", "kind": "comment", "text": "收藏了"}, "dur": 1.6, "toc": "留言列"}]
s["postfx"] = [{"t": [0.4, 1.8], "type": "swipe", "file": R + "/source.mp4", "start": 3}]
s["overlays"] = [{"type": "sticker", "kind": "grid", "t": [2.0, 3.6], "files": [R + "/source.mp4", "assets/shot.png", {"path": R + "/source.mp4", "start": 5}]}]
json.dump(s, open(S + "/r/storyboard.json", "w"), ensure_ascii=False)
PYR
cp "$R/work/transcript.json" "$S/r/work/"
t triggers    "$A" triggers "$S/r/storyboard.json"
t reels       "$A" preview "$S/r/storyboard.json"
echo "== Studio 地基"
t store-tests python3 "$ROOT/scripts/test_store.py"
t patch-show  "$A" patch "$SB"
t patch-set   "$A" patch "$SB" --set 'output.fps=30'
t render-range "$A" render "$SB" --range 1.0 3.5
t studio-engine python3 - "$ROOT" "$SB" <<'PYS'
import json, os, sys
sys.path.insert(0, sys.argv[1])
from aaaai_editor import render, cardpics
p = render.proxy_source(sys.argv[2]); assert os.path.getsize(p) > 1000, p
sb = json.load(open(sys.argv[2]))
ov = next(o for o in sb["overlays"] if o["type"] in ("title", "stat", "bullets"))
c = cardpics.card_png(sys.argv[2], ov); assert os.path.getsize(c) > 1000, c
PYS
t studio-tests python3 "$ROOT/scripts/test_studio.py"
t studio-help "$A" studio --help
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
t mcp-storyboard python3 - "$A" "$SB" <<'PY'
import json, subprocess, sys
def call(i, name, args): return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}
msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, call(2, "storyboard_show", {"file": sys.argv[2]}),
        call(3, "storyboard_patch", {"file": sys.argv[2], "expect": "000000000000", "set": {"output.fps": 30}})]
p = subprocess.run([sys.argv[1], "mcp"], input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, timeout=60)
rs = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
assert json.loads(rs[1]["result"]["content"][0]["text"])["version"], p.stdout[-300:]
assert "版本已变" in rs[2]["result"]["content"][0]["text"], p.stdout[-300:]
PY
echo "==========================================="
echo "通过 $pass 项，失败 $fail 项${failed:+：$failed}"
[ "$fail" = 0 ]
