#!/bin/bash
# 回归测试：同一份测试素材渲染两次、与基准逐字节比对。
#   bash scripts/regress.sh           比对（第一次跑会自动建立基准）
#   bash scripts/regress.sh --update  外观有意改变时，重建基准
# 测试素材与基准放在 ~/.cache/aaaai-editor/regress（不会被系统清掉的暂存区不在 /tmp）。
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
R="${AAAAI_EDITOR_REGRESS:-$HOME/.cache/aaaai-editor/regress}"
A="$ROOT/bin/aaaai-editor"
FF="$(PYTHONPATH="$ROOT" python3 -c 'from aaaai_editor import env; print(env.ffmpeg())' 2>/dev/null || echo ffmpeg)"
mkdir -p "$R/work" "$R/home"
# 独立的设置：成品不要复制到用户的「成品」文件夹
printf '{"projects_dir": "%s", "exports_dir": "", "profile": ""}\n' "$R" > "$R/home/config.json"
export AAAAI_EDITOR_HOME="$R/home"

if [ ! -f "$R/source.mp4" ]; then
  echo "建立测试素材…"
  say -v Tingting -o "$R/v.aiff" "大家好，今天我们来聊一聊。 [[slnc 800]] 第一步是转录，第二步是剪掉停顿。 [[slnc 900]] 第三步是加字幕和音乐，就这么简单，我们下期再见。"
  "$FF" -v error -y -f lavfi -i "testsrc2=s=1080x1920:r=30" -i "$R/v.aiff" -shortest \
        -c:v libx264 -pix_fmt yuv420p -c:a aac "$R/source.mp4"
  "$A" transcribe "$R/source.mp4" --out "$R/work/transcript.json" >/dev/null
  "$A" autocut "$R/source.mp4" --out "$R/sb_cut.json" >/dev/null
  python3 - "$R" <<'PY'
import json, sys
R = sys.argv[1]
s = json.load(open(R + "/sb_cut.json"))
s.update({"style": "ink", "music": {"file": "bgm:focus-quiet", "db": -18, "duck": True},
          "overlays": [
              {"type": "stamp", "t": [0.2, 2.5], "text": "NEW"},
              {"type": "title", "t": [0.3, 3.0], "kicker": "STEP 01", "text": "先定**构思**，再选效果", "sub": "一个载体"},
              {"type": "lower_third", "t": [3.2, 5.5], "name": "Alex Chen", "role": "内容创作者"},
              {"type": "stat", "t": [5.6, 8.0], "value": 24800, "suffix": "+", "label": "月活钱包", "kicker": "TOTAL"},
              {"type": "bullets", "t": [8.2, 11.0], "items": ["转录成文字", "剪掉停顿", "加字幕和配乐"]}]})
json.dump(s, open(R + "/storyboard.json", "w"), ensure_ascii=False, indent=1)
PY
fi

"$A" render "$R/storyboard.json" >/dev/null
cp "$R/work/video.mp4" "$R/run1.mp4"
"$A" render "$R/storyboard.json" >/dev/null
if ! cmp -s "$R/work/video.mp4" "$R/run1.mp4"; then echo "❌ 两次渲染结果不同（不确定性）"; exit 1; fi
if [ "${1:-}" = "--update" ] || [ ! -f "$R/baseline_video.mp4" ]; then
  cp "$R/work/video.mp4" "$R/baseline_video.mp4"; cp "$R/work/captions_full.ass" "$R/baseline.ass"
  echo "✅ 已建立基准（$R）"; exit 0
fi
ok=1
cmp -s "$R/work/video.mp4" "$R/baseline_video.mp4" && echo "✅ 画面与基准逐字节一致" || { echo "❌ 画面与基准不同"; ok=0; }
cmp -s "$R/work/captions_full.ass" "$R/baseline.ass" && echo "✅ 字幕与基准逐字节一致" || { echo "❌ 字幕与基准不同"; ok=0; }
[ "$ok" = 1 ]
