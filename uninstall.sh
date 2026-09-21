#!/bin/bash
# aaaai-editor 卸载：程序、skill、Codex／Claude 的 MCP 注册、插件都移除（移到废纸篓，可救回）。
# 你的设置、风格、频道档案、字体、模型（~/.aaaai-editor 里的）和项目目录默认保留；加 --all 连 ~/.aaaai-editor 也移到废纸篓。
# 钥匙串里的 API 密钥不会动：要删就先执行 ~/.aaaai-editor/bin/aaaai-editor keys remove <名称>。
HOME_DIR="${AAAAI_EDITOR_HOME:-$HOME/.aaaai-editor}"
ALL=0; [ "${1:-}" = "--all" ] && ALL=1
T="$HOME/.Trash/aaaai-editor-卸载-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$T"
[ -e "$HOME_DIR/app" ] && mv "$HOME_DIR/app" "$T/" && echo "✔ 程序已移到废纸篓"
[ -e "$HOME_DIR/bin" ] && mv "$HOME_DIR/bin" "$T/"
for base in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
  for n in aaaai-editor motion-graphic-video-editor social-content-pipeline; do
    d="$base/$n"
    [ -e "$d" ] || [ -L "$d" ] || continue
    sub="$T/$(basename "$(dirname "$base")")"; mkdir -p "$sub"
    mv "$d" "$sub/" && echo "✔ skill $n（$base）已移到废纸篓"
    b="$(ls -d "$base"-backup-*/"$n" 2>/dev/null | tail -1)"   # 安装时备份过的同名旧 skill：放回原位
    [ -n "$b" ] && mv "$b" "$d" && echo "  ↩ 还原安装前的 $n"
  done
done
if command -v codex >/dev/null 2>&1; then
  for m in aaaai-editor; do
    codex mcp list 2>/dev/null | grep -q "^$m\b" && codex mcp remove "$m" >/dev/null 2>&1 && echo "✔ 已取消 Codex 的 MCP 注册（$m）"
  done
fi
if command -v claude >/dev/null 2>&1; then
  for m in aaaai-editor; do
    claude mcp remove "$m" >/dev/null 2>&1 && echo "✔ 已取消 Claude Code 的 MCP 注册（$m）"
  done
  for pl in aaaai-editor@aaaai-editor; do
    claude plugin list 2>/dev/null | grep -q "$pl" && claude plugin uninstall "$pl" >/dev/null 2>&1 && echo "✔ 已卸载 Claude Code 插件 $pl"
  done
fi
if grep -qs "$HOME_DIR/bin" "$HOME/.zprofile"; then
  cp "$HOME/.zprofile" "$T/zprofile.bak" && sed -i '' "\|$HOME_DIR/bin|d" "$HOME/.zprofile" \
    && echo "✔ 已从 ~/.zprofile 移除 aaaai-editor 的 PATH（原档备份在废纸篓）"
fi
if [ "$ALL" = 1 ] && [ -d "$HOME_DIR" ]; then
  mv "$HOME_DIR" "$T/aaaai-editor-资料" && echo "✔ 设置／风格／档案／模型也已移到废纸篓"
else
  echo "保留：$HOME_DIR 里的设置／风格／频道档案／字体／模型，以及你的项目目录（要全清：bash uninstall.sh --all）。"
fi
echo "HeyGen HyperFrames 是独立插件，要移除：claude plugin uninstall core-skills@hyperframes"
echo "Homebrew 装的 ffmpeg-full、whisper-cpp 等没动（别的程序可能也在用）。"
