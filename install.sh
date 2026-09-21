#!/bin/bash
# ============================================================
# aaaai-editor 影片总监套件 —— 安装器（macOS）
# © 2026 MR ONE（@mrone.ai）。见 LICENSE.md。
#
# 用法：bash install.sh [选项]
#   --yes            不逐项询问（下载模型等照默认进行）
#   --no-deps        不装 Homebrew 套件（已自行装好时）
#   --no-model       不下载 whisper 模型（约 1.5GB）
#   --no-mg          不装动画渲染用的 Playwright/Chromium
#   --no-skills      不把 skill 复制到 ~/.claude/skills（插件安装时自动如此）
#   --no-hyperframes 不安装 HeyGen HyperFrames 插件
#   --dev            开发模式：程序与 skill 用符号链接指回这个文件夹（改代码立刻生效）
#   --plugin         由 Claude Code 插件调用（skill 已由插件提供，不复制）
#   --no-keys        不引导绑定 API 密钥（B-roll 用，全部可选；之后可 aaaai-editor keys set）
#   --no-codex       不为 ChatGPT Codex 安装 skill／MCP
#
# 安装前须知的完整说明：docs/00-快速安装.md
# 可重复执行：已装的会跳过；更新程序不会动你的设置、风格、频道档案与项目（都在 ~/.aaaai-editor 与项目目录）。
# ============================================================
set -u
SRC="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="${AAAAI_EDITOR_HOME:-$HOME/.aaaai-editor}"
YES=0; DEPS=1; MODEL=1; MG=1; SKILLS=1; HF=1; DEV=0; KEYS=1; CODEX=1
for a in "$@"; do case "$a" in
  --yes) YES=1;; --no-deps) DEPS=0;; --no-model) MODEL=0;; --no-mg) MG=0;; --no-skills) SKILLS=0;;
  --no-hyperframes) HF=0;; --dev) DEV=1;; --no-keys) KEYS=0;; --no-codex) CODEX=0;; --plugin) PLUGIN_FLAG=1;; *) echo "未知选项：$a"; exit 2;; esac; done
PLUGIN=0
case "$SRC" in */plugins/cache/*|*/.claude/plugins/*) PLUGIN=1;; esac
[ "${PLUGIN_FLAG:-0}" = 1 ] && PLUGIN=1
[ "$PLUGIN" = 1 ] && SKILLS=0

ok()   { printf "  \033[32m✔\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m⚠\033[0m %s\n" "$1"; }
step() { printf "\n\033[1m%s\033[0m\n" "$1"; }
TTY=0; [ -t 0 ] && TTY=1
TODO=()   # 没有终端可问（例如由 AI 代跑）而跳过的项目，结束时列给用户
todo() { TODO+=("$1"); }
# 问是否要做：--yes 一律做；没有终端可问就一律「不做」并记下来（绝不替用户默认同意）
ask()  { [ "$YES" = 1 ] && return 0; [ "$TTY" = 1 ] || return 1; read -r -p "  $1 [Y/n] " r; [ -z "$r" ] || [ "$r" = y ] || [ "$r" = Y ]; }

VER="$(cat "$SRC/VERSION" 2>/dev/null || echo "?")"
echo "aaaai-editor 影片总监套件 v$VER 安装器"
[ "$(uname -s)" = Darwin ] || { echo "目前只支持 macOS。"; exit 1; }

# ---------- 0. 安装前须知 ----------
cat <<'NOTICE'

────────────────── 安装前须知（请先看完） ──────────────────
会安装（免费、开源）：
  · Homebrew 套件：FFmpeg、whisper.cpp、Python 3.12、Node.js（Node 给动画片／HyperFrames 用；没有 Homebrew 会先问你，需要开机密码）
  · Python 套件（装在你的用户目录，pip --user）：OpenCC、fontTools、brotli、Playwright＋Chromium（约 1GB）、NumPy／SciPy／Pillow
  · 开源字体 Orbitron、IBM Plex Mono（放在 ~/.aaaai-editor/fonts，不动系统）
  · whisper 语音识别模型约 1.5GB（会先问）
  · Xcode Command Line Tools（人像去背用，会先问，走 Apple 官方安装窗口）
  · 程序放在 ~/.aaaai-editor/app；3 个 skill 复制进 ~/.claude/skills（同名的旧 skill 会先备份，不会直接覆盖）
  · 首次安装共约 3GB 下载，视网速 10–30 分钟
会接入的其他工具（免费）：
  · Claude Code（没有的话会问你要不要装）
  · HeyGen HyperFrames 官方 skill（Apache-2.0，讲解片／产品发布等格式）
  · 如果电脑有 ChatGPT Codex：一并装 skill，并可选把 aaaai-editor 注册成 Codex 的 MCP 工具
可选、要你自己决定的（不绑也能正常剪片，只是少了 AI 生成 B-roll）：
  · Pexels API 密钥 —— 免费素材库，$0，要标注 Pexels 与摄影师
  · fal API 密钥 —— 按次付费：Wan 2.2 约 $0.15/条、可灵 2.5 约 $0.35/5 秒（在 fal 预充值）
  · Higgsfield 密钥 —— 扣你 Higgsfield 账户的额度，只在你指定时使用
  密钥存进 macOS 钥匙串，只在你自己的终端输入，不经过聊天、不写进任何文件。
  每次要花钱前都会先报价、问过你才执行；每个项目默认上限 $2，超出会提醒，你同意就继续。
在 Claude 里会用到（Claude 自带／连接器，第一次用时会提示）：
  · 发布流水线「出图」可连接 Canva 连接器（Canva 账户，免费或付费版都行）
  · Claude 内建的文件 skill（docx／pdf 等）只在你要求导出文件时使用
隐私：视频、音频、字幕都只在你的电脑上处理。只有 B-roll 的画面描述／搜索词（和你选填的首帧照片）
  会发给 Pexels 或 fal，而且每次都会先问你。
版权：程序免费给指定的人用；mrone（© MR ONE）、otg（© OTG 社群）两套风格
  只限社群成员或获授权者（详见 LICENSE.md）。
────────────────────────────────────────────────────────────
NOTICE
if [ "$YES" != 1 ] && [ "$TTY" = 1 ]; then read -r -p "  看完了，继续安装？[Y/n] " r; case "$r" in n|N) echo "已取消。"; exit 0;; esac
elif [ "$TTY" = 0 ] && [ "$YES" != 1 ]; then echo "  （没有终端可问：需要你同意的项目一律跳过，结束时列出来给你）"; fi

# ---------- 1. 系统依赖 ----------
step "1. 系统依赖"
BREW="$(command -v brew || true)"
[ -z "$BREW" ] && [ -x /opt/homebrew/bin/brew ] && BREW=/opt/homebrew/bin/brew
if [ -z "$BREW" ]; then
  warn "没有 Homebrew（装 FFmpeg、Python 等都靠它）。"
  if ask "现在安装 Homebrew？过程中会要求输入你的开机密码"; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && BREW="$b" && break; done
  fi
  [ -z "$BREW" ] && { echo "  没有 Homebrew 无法继续：请在「终端」App 里执行"
                      echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
                      echo "  装好后重跑本安装器。"; exit 1; }
  eval "$("$BREW" shellenv)"; ok "Homebrew"
fi
# 新装的 Homebrew 不在 PATH 上：写进 ~/.zprofile，之后开的终端（和 Claude）才找得到 brew 装的工具
if ! grep -qs "brew shellenv" "$HOME/.zprofile" && [ "$(command -v brew)" != "$BREW" -o -z "$(command -v brew)" ]; then
  echo "eval \"\$($BREW shellenv)\"" >> "$HOME/.zprofile" && ok "已把 Homebrew 加进 ~/.zprofile"
fi
if [ "$DEPS" = 1 ]; then
  PKGS="ffmpeg-full whisper-cpp python@3.12"; { [ "$MG" = 1 ] || [ "$HF" = 1 ]; } && PKGS="$PKGS node"
  for f in $PKGS; do
    if "$BREW" list --versions "$f" >/dev/null 2>&1; then ok "$f 已安装"
    else echo "  安装 $f …"; "$BREW" install "$f" >/dev/null && ok "$f" || warn "$f 安装失败（稍后可手动 brew install $f）"; fi
  done
fi
PY="$( [ -x /opt/homebrew/bin/python3.12 ] && echo /opt/homebrew/bin/python3.12 || command -v python3.12 || command -v python3 )"
if xcode-select -p >/dev/null 2>&1; then ok "Xcode Command Line Tools（人像去背用）"
else
  warn "没有 Xcode Command Line Tools（人像穿插／卡片接管需要）"
  if ask "现在弹出系统安装窗口？（装完不用重跑本安装器，第一次用到人像功能时会自动编译）"; then
    xcode-select --install >/dev/null 2>&1 && ok "已弹出安装窗口，请按提示完成" || warn "请手动执行 xcode-select --install"
  else todo "（选装）人像去背：在终端执行 xcode-select --install"; fi
fi
if [ "$DEPS" = 1 ]; then
  "$PY" -m pip install --user --break-system-packages -q opencc fonttools brotli >/dev/null 2>&1 \
    && ok "Python 可选依赖（OpenCC、fontTools）" || warn "Python 可选依赖没装上（不影响出片）"
  if [ "$MG" = 1 ]; then
    if "$PY" -c "import playwright" >/dev/null 2>&1; then ok "Playwright 已安装"
    else "$PY" -m pip install --user --break-system-packages -q playwright >/dev/null 2>&1 && ok "Playwright" || warn "Playwright 没装上"; fi
    "$PY" -m playwright install chromium >/dev/null 2>&1 && ok "Chromium（动画渲染）" || warn "Chromium 没装上（动画片需要）"
    "$PY" -m pip install --user --break-system-packages -q numpy scipy pillow >/dev/null 2>&1 \
      && ok "NumPy／SciPy／Pillow（动画脚本、配乐合成）" || warn "NumPy／SciPy／Pillow 没装上"
  fi
fi

# ---------- 2. 程序本体 ----------
step "2. 程序本体 → $HOME_DIR/app"
mkdir -p "$HOME_DIR"/{bin,themes,profiles,fonts,models,bgm}
if [ "$DEV" = 1 ]; then
  rm -rf "$HOME_DIR/app"; ln -s "$SRC" "$HOME_DIR/app"; ok "开发模式：app → $SRC"
elif [ "$SRC" != "$HOME_DIR/app" ]; then
  [ -L "$HOME_DIR/app" ] && rm "$HOME_DIR/app"
  rsync -a --delete --exclude projects --exclude dist --exclude .git --exclude __pycache__ \
        --exclude .DS_Store --exclude 'work/' --exclude CLAUDE.md "$SRC/" "$HOME_DIR/app/" && ok "已复制 v$VER"
fi
cat > "$HOME_DIR/bin/aaaai-editor" <<'W'
#!/bin/bash
exec "${AAAAI_EDITOR_HOME:-$HOME/.aaaai-editor}/app/bin/aaaai-editor" "$@"
W
cat > "$HOME_DIR/bin/aaaai-editor-python" <<W
#!/bin/bash
exec "$PY" "\$@"
W
chmod +x "$HOME_DIR/bin/aaaai-editor" "$HOME_DIR/bin/aaaai-editor-python" "$HOME_DIR/app/bin/aaaai-editor" 2>/dev/null
if grep -qs "$HOME_DIR/bin" "$HOME/.zprofile"; then ok "命令：aaaai-editor（已在 PATH）"
elif ask "把 aaaai-editor 命令加进 PATH（之后在终端直接打 aaaai-editor）？"; then
  echo "export PATH=\"$HOME_DIR/bin:\$PATH\"" >> "$HOME/.zprofile" && ok "已加进 ~/.zprofile（新开的终端生效）"
else ok "命令：$HOME_DIR/bin/aaaai-editor"; fi
[ -f "$HOME_DIR/config.json" ] || echo '{"projects_dir": "~/Movies/aaaai-editor", "exports_dir": "~/Movies/aaaai-editor/成品", "profile": ""}' > "$HOME_DIR/config.json"
ok "设置档 $HOME_DIR/config.json（已存在的不会覆盖）"

# ---------- 3. 开源字体（下载到 ~/.aaaai-editor/fonts，不装进系统） ----------
step "3. 开源字体（SIL OFL）"
fetch_font() {  # $1 目标文件名 $2 URL $3 已安装的系统位置
  if [ -f "$HOME_DIR/fonts/$1" ] || [ -f "$3" ]; then ok "$1"; return; fi
  curl -fsSL "$2" -o "$HOME_DIR/fonts/$1" && ok "$1（已下载）" || warn "$1 下载失败（OTG 风格标题／数字会退回系统字体）"
}
fetch_font "Orbitron[wght].ttf" "https://github.com/google/fonts/raw/main/ofl/orbitron/Orbitron%5Bwght%5D.ttf" "$HOME/Library/Fonts/Orbitron-VariableFont_wght.ttf"
fetch_font "IBMPlexMono-Bold.ttf" "https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Bold.ttf" "$HOME/Library/Fonts/IBMPlexMono-Bold.ttf"

# ---------- 4. whisper 模型 ----------
step "4. 语音识别模型"
# 只认完整的多语言 medium／large（英文专用 *.en、tiny／base 中文不行；小于 500MB 多半是下载中断）
FOUND=""
for f in "$HOME_DIR"/models/ggml-*.bin "$HOME"/.cache/*/models/ggml-*.bin "$HOME"/.cache/whisper*/ggml-*.bin; do
  [ -f "$f" ] || continue
  case "$(basename "$f")" in *.en.bin|*.en-*) continue;; *medium*|*large*) ;; *) continue;; esac
  [ "$(stat -f %z "$f")" -gt 500000000 ] && FOUND="$f" && break
done
MURL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"; MDST="$HOME_DIR/models/ggml-medium.bin"
if [ -n "$FOUND" ]; then ok "已有：$FOUND"
elif [ "$MODEL" = 1 ] && ask "下载 whisper medium 模型（约 1.5GB，多语言，中英文都能认）？"; then
  # 先下到 .part（中断可续传），完整了才改名，半截文件不会被当成「已有」
  curl -fL -C - --progress-bar "$MURL" -o "$MDST.part" && [ "$(stat -f %z "$MDST.part")" -gt 1400000000 ] \
    && mv "$MDST.part" "$MDST" && ok "ggml-medium.bin" || warn "下载没完成（重跑安装器会接着下载）"
else warn "还没有语音模型：转录前需要它"
  todo "下载语音模型（约 1.5GB，可续传）：curl -fL -C - $MURL -o $MDST.part && mv $MDST.part $MDST"; fi

# ---------- 5. Claude Code skills ----------
step "5. Claude Code skills"
if [ "$SKILLS" = 1 ]; then
  mkdir -p "$HOME/.claude/skills"; TS="$(date +%Y%m%d-%H%M%S)"
  for d in "$SRC"/skills/*/; do
    n="$(basename "$d")"; dst="$HOME/.claude/skills/$n"
    if [ -e "$dst" ] && ! { [ -L "$dst" ] && [ "$(readlink "$dst")" = "${d%/}" ]; }; then
      # 是本套件装的旧版（有 .aaaai-editor-suite 标记）就直接换新；别人的同名 skill 才备份
      if [ ! -f "$dst/.aaaai-editor-suite" ] && ! diff -rq "$d" "$dst" >/dev/null 2>&1; then
        mkdir -p "$HOME/.claude/skills-backup-$TS"; mv "$dst" "$HOME/.claude/skills-backup-$TS/$n"
        warn "原有的 $n 已备份到 ~/.claude/skills-backup-$TS/"
      else rm -rf "$dst"; fi
    fi
    if [ "$DEV" = 1 ]; then ln -sfn "${d%/}" "$dst"; else rm -rf "$dst"; cp -R "${d%/}" "$dst"; touch "$dst/.aaaai-editor-suite"; fi
    ok "$n"
  done
elif [ "$PLUGIN" = 1 ]; then ok "插件安装：skill 由 Claude Code 插件提供（在 Claude Code 里输入 /aaaai-editor 使用）"
else ok "跳过（--no-skills）"; fi

# ---------- 6. HeyGen HyperFrames（其他格式） ----------
step "6. HeyGen HyperFrames（讲解片／网站转影片／产品发布／音乐影片等格式，Apache-2.0）"
if [ "$HF" = 1 ] && ! command -v claude >/dev/null 2>&1; then
  warn "没找到 Claude Code（本套件在 Claude Code 里使用）"
  if ask "现在用官方安装程序安装 Claude Code？"; then
    curl -fsSL https://claude.ai/install.sh | bash && export PATH="$HOME/.local/bin:$PATH"
  else todo "（选装）Claude Code：curl -fsSL https://claude.ai/install.sh | bash"; fi
fi
if [ "$HF" = 1 ] && command -v claude >/dev/null 2>&1; then
  claude plugin marketplace add https://github.com/heygen-com/hyperframes.git >/dev/null 2>&1 || true   # 用 https：没设 SSH 的电脑用简写会失败
  if claude plugin list 2>/dev/null | grep -q "core-skills"; then ok "已安装"
  else claude plugin install core-skills@hyperframes >/dev/null 2>&1 && ok "core-skills@hyperframes" \
       || warn "没装上：之后在 Claude Code 里执行 claude plugin install core-skills@hyperframes"; fi
elif [ "$HF" = 1 ]; then warn "没找到 claude 命令，HyperFrames 跳过"
  todo "（选装）HyperFrames：装好 Claude Code 后执行 claude plugin marketplace add https://github.com/heygen-com/hyperframes.git && claude plugin install core-skills@hyperframes"
else ok "跳过"; fi

# ---------- 7. ChatGPT Codex（可选） ----------
step "7. ChatGPT Codex"
if [ "$CODEX" = 1 ] && { command -v codex >/dev/null 2>&1 || [ -d "$HOME/.codex" ]; }; then
  mkdir -p "$HOME/.agents/skills"; TS="${TS:-$(date +%Y%m%d-%H%M%S)}"
  for d in "$SRC"/skills/*/; do
    n="$(basename "$d")"; dst="$HOME/.agents/skills/$n"
    if [ -e "$dst" ] && ! { [ -L "$dst" ] && [ "$(readlink "$dst")" = "${d%/}" ]; } && [ ! -f "$dst/.aaaai-editor-suite" ] \
       && ! diff -rq "$d" "$dst" >/dev/null 2>&1; then
      mkdir -p "$HOME/.agents/skills-backup-$TS"; mv "$dst" "$HOME/.agents/skills-backup-$TS/$n"
      warn "原有的 $n 已备份到 ~/.agents/skills-backup-$TS/"
    fi
    if [ "$DEV" = 1 ]; then ln -sfn "${d%/}" "$dst"; else rm -rf "$dst"; cp -R "${d%/}" "$dst"; touch "$dst/.aaaai-editor-suite"; fi
  done
  ok "skill 已放进 ~/.agents/skills（Codex 读这里）"
  if command -v codex >/dev/null 2>&1; then
    if codex mcp list 2>/dev/null | grep -q "^aaaai-editor"; then ok "MCP 已注册"
    elif ask "把 aaaai-editor 注册成 Codex 的 MCP 工具（B-roll 生成等，可不注册，Codex 也能直接跑命令）？"; then
      codex mcp add aaaai-editor -- "$HOME_DIR/bin/aaaai-editor" mcp >/dev/null 2>&1 && ok "codex mcp add aaaai-editor" \
        || warn "没注册上：之后执行 codex mcp add aaaai-editor -- $HOME_DIR/bin/aaaai-editor mcp"
    else todo "（选装）Codex MCP：codex mcp add aaaai-editor -- $HOME_DIR/bin/aaaai-editor mcp"; fi
  else warn "找到 ~/.codex 但没有 codex 命令：之后可执行 codex mcp add aaaai-editor -- $HOME_DIR/bin/aaaai-editor mcp"; fi
elif [ "$CODEX" = 1 ]; then ok "没发现 Codex，跳过（之后装了 Codex 重跑本安装器即可）"
else ok "跳过（--no-codex）"; fi

# ---------- 8. API 密钥（全部可选） ----------
step "8. API 密钥（B-roll 用，全部可选，不绑也能剪片）"
"$HOME_DIR/bin/aaaai-editor" keys 2>/dev/null | grep -E "^(✅|—)" | sed 's/^/  /'
if [ "$KEYS" = 1 ] && [ "$YES" != 1 ] && [ -t 0 ]; then
  for k in PEXELS_API_KEY FAL_KEY HF_CREDENTIALS; do
    if "$HOME_DIR/bin/aaaai-editor" keys 2>/dev/null | grep -q "^✅ $k"; then continue; fi
    case "$k" in
      PEXELS_API_KEY) q="绑定 Pexels 免费素材库密钥（\$0，推荐）？先到 https://www.pexels.com/api/new/ 免费申请";;
      FAL_KEY) q="绑定 fal 密钥（AI 生成 B-roll，按次付费，每次会先问你）？申请：https://fal.ai/dashboard/keys";;
      HF_CREDENTIALS) q="绑定 Higgsfield 密钥（只在你指定时用，扣账户额度）？申请：https://cloud.higgsfield.ai/";;
    esac
    read -r -p "  $q [y/N] " r
    case "$r" in y|Y) "$HOME_DIR/bin/aaaai-editor" keys set "$k" || warn "没存上，之后可执行 aaaai-editor keys set $k";; *) ok "跳过 $k";; esac
  done
else ok "之后想绑：在终端执行 $HOME_DIR/bin/aaaai-editor keys set <名称>（aaaai-editor keys 看说明）"
  [ "$KEYS" = 1 ] && todo "（选装）B-roll 密钥：在「终端」App 执行 $HOME_DIR/bin/aaaai-editor keys set PEXELS_API_KEY（免费）"; fi

# ---------- 9. 体检 ----------
step "9. 体检"
"$HOME_DIR/bin/aaaai-editor" doctor || true
if [ "${#TODO[@]}" -gt 0 ]; then
  step "还剩这些要你自己决定／在「终端」App 里做"
  for t in "${TODO[@]}"; do echo "  · $t"; done
fi
echo
echo "完成。在 Claude Code 里说「/aaaai-editor」或丢一段视频进去就能开始。"
echo "发布流水线要「出图」的话：在 Claude 里连接 Canva 等设计工具的连接器（第一次用时 Claude 会提示）。"
echo "Claude Desktop／Cursor 想用 B-roll 工具：把 MCP 服务器设为命令 $HOME_DIR/bin/aaaai-editor、参数 mcp（见 docs/00-快速安装.md）。"
echo "受限风格 mrone（© MR ONE）、otg（© OTG 社群）只给社群成员或获授权者：确认后执行"
echo "    $HOME_DIR/bin/aaaai-editor authorize mrone   （或 otg）"
echo "建立自己的频道档案：复制 $HOME_DIR/app/profiles/TEMPLATE 到 $HOME_DIR/profiles/<名字>，再"
echo "    $HOME_DIR/bin/aaaai-editor config --set profile=<名字>"
