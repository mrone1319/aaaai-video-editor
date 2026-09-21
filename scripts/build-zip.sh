#!/bin/bash
# 打包 zip 安装包：dist/aaaai-editor-v<版本>.zip（不含项目、缓存、git）
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; VER="$(cat "$ROOT/VERSION")"
mkdir -p "$ROOT/dist"; OUT="$ROOT/dist/aaaai-editor-v$VER.zip"; rm -f "$OUT"
STAGE="$(mktemp -d)/aaaai-editor-v$VER"; mkdir -p "$STAGE"
# 只打包 git 管理的文件（本地草稿不会混进去）；开发用文件（CLAUDE.md、开发计划）不发出去
(cd "$ROOT" && git ls-files -z | grep -zv -e '^CLAUDE.md$' -e '^docs/PLAN.md$' | rsync -a --from0 --files-from=- ./ "$STAGE/")
cat > "$STAGE/双击安装.command" <<'C'
#!/bin/bash
cd "$(dirname "$0")" && xattr -dr com.apple.quarantine . 2>/dev/null; bash install.sh
echo; read -r -p "按 Enter 关闭" _
C
chmod +x "$STAGE/双击安装.command" "$STAGE/install.sh" "$STAGE/uninstall.sh" "$STAGE/bin/aaaai-editor"
# 用 Python 打包：中文文件名带 UTF-8 标记（各种解压工具都不乱码），保留可执行权限，不夹带 __MACOSX
python3 - "$STAGE" "$OUT" <<'PY'
import os, sys, zipfile
src, out = sys.argv[1], sys.argv[2]
base = os.path.dirname(src)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for f in sorted(files):
            if f == ".DS_Store":
                continue
            p = os.path.join(root, f)
            zi = zipfile.ZipInfo.from_file(p, os.path.relpath(p, base))
            zi.compress_type = zipfile.ZIP_DEFLATED
            with open(p, "rb") as fh:
                z.writestr(zi, fh.read())
PY
echo "✅ $OUT（$(du -h "$OUT" | cut -f1)）"
