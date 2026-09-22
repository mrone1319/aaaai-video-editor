# ============================================================
# aaaai-editor 影片总监套件 —— Windows 安装器（Windows 10 22H2／11，64 位）
# 见 LICENSE.md。与 macOS 的 install.sh 同一套步骤；用法（在 PowerShell 里）：
#   powershell -ExecutionPolicy Bypass -File install.ps1 [-Yes] [-NoDeps] [-NoModel] [-NoSkills] [-NoHyperframes] [-NoKeys]
# 或直接双击 Install-Windows.cmd。可重复执行：已装的会跳过；不会动你的设置、风格、频道档案与项目。
# 没有互动视窗可问（例如由 AI 代跑）时：需要你同意的项目一律跳过，结束时列出来给你。
# ============================================================
param([switch]$Yes, [switch]$NoDeps, [switch]$NoModel, [switch]$NoSkills, [switch]$NoHyperframes, [switch]$NoKeys)
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$SRC = Split-Path -Parent $MyInvocation.MyCommand.Path
$HOME_DIR = if ($env:AAAAI_EDITOR_HOME) { $env:AAAAI_EDITOR_HOME } else { Join-Path $env:USERPROFILE ".aaaai-editor" }
$VER = (Get-Content (Join-Path $SRC "VERSION") -Raw).Trim()
$TTY = -not [Console]::IsInputRedirected
$TODO = New-Object System.Collections.Generic.List[string]

function Ok($m)   { Write-Host "  ✔ $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ⚠ $m" -ForegroundColor Yellow }
function Step($m) { Write-Host ""; Write-Host $m -ForegroundColor White }
function Todo($m) { $TODO.Add($m) | Out-Null }
# 问是否要做：-Yes 一律做；没有互动视窗就一律「不做」并记下来（绝不替用户默认同意）
function Ask($q) {
  if ($Yes) { return $true }
  if (-not $TTY) { return $false }
  $r = Read-Host "  $q [Y/n]"
  return ($r -eq "" -or $r -eq "y" -or $r -eq "Y")
}
function Has($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

if ([Environment]::OSVersion.Platform -ne "Win32NT") { Write-Host "这个安装器给 Windows 用；macOS 请用 install.sh。"; exit 1 }
if (-not [Environment]::Is64BitOperatingSystem) { Write-Host "需要 64 位 Windows。"; exit 1 }

# ---------- 0. 安装前须知 ----------
Write-Host @"

────────────────── 安装前须知（请先看完） ──────────────────
会安装（免费、开源），都用 Windows 自带的 winget 或官方网址下载：
  · Python 3.12、FFmpeg（Gyan 完整版，含字幕引擎）、Git（Claude Code 在 Windows 上需要 Git）
  · whisper.cpp 语音识别（官方 GitHub 发布版）与 whisper 模型约 1.5GB（会先问，下载完核对官方校验码）
  · Python 套件（装在你的用户目录，pip --user）：OpenCC、fontTools、brotli、MediaPipe＋NumPy（人像去背用）
  · MediaPipe 官方人像分割模型（约 250KB）、开源字体 Orbitron、IBM Plex Mono（放在 ~\.aaaai-editor，不动系统）
  · 程序放在 ~\.aaaai-editor\app；3 个 skill 复制进 ~\.claude\skills（同名的旧 skill 会先备份）
  · 首次安装共约 3GB 下载，视网速 10–30 分钟
可选、要你自己决定的（不绑也能正常剪片）：
  · Pexels（免费素材）、fal（AI 生成 B-roll，按次付费）、Higgsfield 密钥
  密钥存进 Windows 凭据管理器，只在你自己的视窗输入，不经过聊天、不写进任何文件。
  每次要花钱前都会先报价、问过你才执行；每个项目默认上限 `$2。
隐私：视频、音频、字幕都只在你的电脑上处理。只有 B-roll 的画面描述／搜索词会发给 Pexels 或 fal，每次都先问你。
版权：程序免费使用；mrone（© MR ONE）、otg（© OTG 社群）是社群风格，可以使用但品牌归原权利人（详见 LICENSE.md）。
────────────────────────────────────────────────────────────
"@
if (-not $Yes -and $TTY) {
  $r = Read-Host "  看完了，继续安装？[Y/n]"
  if ($r -eq "n" -or $r -eq "N") { Write-Host "已取消。"; exit 0 }
} elseif (-not $TTY -and -not $Yes) { Write-Host "  （没有互动视窗可问：需要你同意的项目一律跳过，结束时列出来给你）" }

# ---------- 1. 系统依赖 ----------
Step "1. 系统依赖"
$winget = Has "winget"
if (-not $winget) { Warn "没有 winget（Windows 的「应用程序安装程序」）：请到 Microsoft Store 安装「App Installer」后重跑。" }
function Winget-Install($id, $label) {
  if (-not $winget) { Todo "安装 $label：winget install -e --id $id"; return }
  $listed = (winget list -e --id $id 2>$null | Out-String)
  if ($listed -match [regex]::Escape($id)) { Ok "$label 已安装"; return }
  if (Ask "用 winget 安装 $label（会同意 winget 的来源与套件授权条款）？") {
    winget install -e --id $id --silent --accept-source-agreements --accept-package-agreements | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok $label } else { Warn "$label 没装上：之后执行 winget install -e --id $id" }
  } else { Todo "安装 $label：winget install -e --id $id" }
}
if (-not $NoDeps) {
  Winget-Install "Python.Python.3.12" "Python 3.12"
  Winget-Install "Gyan.FFmpeg" "FFmpeg（完整版）"
  Winget-Install "Git.Git" "Git（Claude Code 需要）"
  if (-not $NoHyperframes) { Winget-Install "OpenJS.NodeJS.LTS" "Node.js（HyperFrames／动画片用）" }
  # winget 刚装完的程序不在这个视窗的 PATH 上：把使用者与系统的 PATH 重新读进来
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
$PY = $null; $PYARGS = @()
if (Has "py") { $PY = "py"; $PYARGS = @("-3.12"); & py -3.12 --version *> $null; if ($LASTEXITCODE -ne 0) { $PYARGS = @("-3") } }
elseif (Has "python") { $PY = "python" }
if (-not $PY) { Warn "找不到 Python：装好 Python 3.12 后重跑本安装器"; Todo "安装 Python 3.12：winget install -e --id Python.Python.3.12" }

New-Item -ItemType Directory -Force -Path (Join-Path $HOME_DIR "tools"), (Join-Path $HOME_DIR "models"), (Join-Path $HOME_DIR "fonts"), (Join-Path $HOME_DIR "bin"), (Join-Path $HOME_DIR "themes"), (Join-Path $HOME_DIR "profiles"), (Join-Path $HOME_DIR "bgm") | Out-Null

# whisper.cpp：官方 GitHub 发布版（x64）
$wdir = Join-Path $HOME_DIR "tools\whisper"
$wcli = Get-ChildItem -Path $wdir -Recurse -Include "whisper-cli.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($wcli) { Ok "whisper.cpp 已安装" }
elseif (-not $NoDeps -and (Ask "从 whisper.cpp 官方 GitHub 下载 Windows 版（约 5MB）？")) {
  $zip = Join-Path $env:TEMP "whisper-bin-x64.zip"
  & curl.exe -fL --progress-bar "https://github.com/ggml-org/whisper.cpp/releases/latest/download/whisper-bin-x64.zip" -o $zip
  if ($LASTEXITCODE -eq 0) {
    Expand-Archive -Path $zip -DestinationPath $wdir -Force; Remove-Item $zip -ErrorAction SilentlyContinue
    if (Get-ChildItem -Path $wdir -Recurse -Include "whisper-cli.exe" -ErrorAction SilentlyContinue) { Ok "whisper.cpp" } else { Warn "解压后找不到 whisper-cli.exe" }
  } else { Warn "whisper.cpp 下载失败（重跑本安装器会再试）" }
} else { Todo "下载 whisper.cpp：重跑本安装器并同意下载" }

if ($PY -and -not $NoDeps) {
  & $PY @PYARGS -m pip install --user -q opencc fonttools brotli *> $null
  if ($LASTEXITCODE -eq 0) { Ok "Python 可选依赖（OpenCC、fontTools）" } else { Warn "Python 可选依赖没装上（不影响出片）" }
  & $PY @PYARGS -m pip install --user -q mediapipe numpy *> $null
  if ($LASTEXITCODE -eq 0) { Ok "MediaPipe＋NumPy（人像去背）" } else { Warn "MediaPipe 没装上（人像穿插／卡片接管需要）"; Todo "（选装）人像去背：py -3.12 -m pip install --user mediapipe numpy" }
}
$seg = Join-Path $HOME_DIR "models\selfie_segmenter.tflite"
if (-not (Test-Path $seg)) {
  & curl.exe -fsSL "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite" -o $seg
  if ($LASTEXITCODE -eq 0 -and (Get-Item $seg).Length -gt 100000) { Ok "MediaPipe 人像分割模型" } else { Remove-Item $seg -ErrorAction SilentlyContinue; Warn "人像分割模型下载失败（重跑本安装器会再试）" }
} else { Ok "MediaPipe 人像分割模型" }

# ---------- 2. 程序本体 ----------
Step "2. 程序本体 → $HOME_DIR\app"
$app = Join-Path $HOME_DIR "app"
if ((Resolve-Path $SRC).Path -ne $app) {
  & robocopy $SRC $app /MIR /NFL /NDL /NJH /NJS /NP /XD projects dist .git __pycache__ work /XF CLAUDE.md .DS_Store | Out-Null
  if ($LASTEXITCODE -lt 8) { Ok "已复制 v$VER" } else { Warn "复制程序失败（robocopy $LASTEXITCODE）" }
}
# 启动器：.cmd 给命令提示字元／PowerShell／MCP；无扩展名的给 Git Bash（Claude Code 在 Windows 上用它执行命令）
Set-Content -Path (Join-Path $HOME_DIR "bin\aaaai-editor.cmd") -Encoding ASCII -Value "@echo off`r`ncall `"%~dp0..\app\bin\aaaai-editor.cmd`" %*`r`nexit /b %errorlevel%"
[IO.File]::WriteAllText((Join-Path $HOME_DIR "bin\aaaai-editor"), "#!/bin/bash`nexec `"`${AAAAI_EDITOR_HOME:-`$HOME/.aaaai-editor}/app/bin/aaaai-editor`" `"`$@`"`n")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User"); if (-not $userPath) { $userPath = "" }
$binDir = Join-Path $HOME_DIR "bin"
if ($userPath.Split(";") -contains $binDir) { Ok "命令：aaaai-editor（已在 PATH）" }
elseif (Ask "把 aaaai-editor 命令加进 PATH（之后在新视窗直接打 aaaai-editor）？") {
  [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $binDir), "User"); Ok "已加进使用者 PATH（新开的视窗生效）"
} else { Ok "命令：$binDir\aaaai-editor.cmd" }
$cfg = Join-Path $HOME_DIR "config.json"
if (-not (Test-Path $cfg)) {
  [IO.File]::WriteAllText($cfg, '{"projects_dir": "~/Videos/aaaai-editor", "exports_dir": "~/Videos/aaaai-editor/成品", "profile": ""}', (New-Object System.Text.UTF8Encoding($false)))
}
Ok "设置档 $cfg（已存在的不会覆盖）"

# ---------- 3. 开源字体 ----------
Step "3. 开源字体（SIL OFL）"
function Fetch-Font($name, $url) {
  $dst = Join-Path $HOME_DIR "fonts\$name"
  if (Test-Path $dst) { Ok $name; return }
  & curl.exe -fsSL $url -o $dst
  if ($LASTEXITCODE -eq 0) { Ok "$name（已下载）" } else { Remove-Item $dst -ErrorAction SilentlyContinue; Warn "$name 下载失败（OTG 标题／数字会退回系统字体）" }
}
Fetch-Font "Orbitron[wght].ttf" "https://github.com/google/fonts/raw/main/ofl/orbitron/Orbitron%5Bwght%5D.ttf"
Fetch-Font "IBMPlexMono-Bold.ttf" "https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Bold.ttf"

# ---------- 4. whisper 模型 ----------
Step "4. 语音识别模型"
$MURL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"
$MDST = Join-Path $HOME_DIR "models\ggml-medium.bin"
$MSHA1 = "fd9727b6e1217c2f614f9b698455c4ffd82463b4"
if (Test-Path $MDST) { Ok "已有：$MDST" }
elseif (-not $NoModel -and (Ask "下载 whisper medium 模型（约 1.5GB，多语言，中英文都能认）？")) {
  & curl.exe -fL -C - --progress-bar $MURL -o "$MDST.part"
  if ($LASTEXITCODE -eq 0 -and (Get-Item "$MDST.part").Length -gt 1400000000) {
    # 下载完核对官方校验码（whisper.cpp 公布的 SHA-1）：被篡改或下载损坏的模型不会被启用
    if ((Get-FileHash "$MDST.part" -Algorithm SHA1).Hash.ToLower() -eq $MSHA1) { Move-Item "$MDST.part" $MDST -Force; Ok "ggml-medium.bin（校验码正确）" }
    else { Move-Item "$MDST.part" "$MDST.bad" -Force; Warn "模型校验码不对（下载损坏或被篡改），没有启用；请重跑安装器" }
  } else { Warn "下载没完成（重跑安装器会接着下载）" }
} else { Warn "还没有语音模型：转录前需要它"; Todo "下载语音模型（约 1.5GB）：重跑本安装器并同意下载" }

# ---------- 5. Claude Code skills ----------
Step "5. Claude Code skills"
if (-not $NoSkills) {
  $skills = Join-Path $env:USERPROFILE ".claude\skills"; New-Item -ItemType Directory -Force -Path $skills | Out-Null
  $TS = Get-Date -Format "yyyyMMdd-HHmmss"
  Get-ChildItem -Directory (Join-Path $SRC "skills") | ForEach-Object {
    $dst = Join-Path $skills $_.Name
    if ((Test-Path $dst) -and -not (Test-Path (Join-Path $dst ".aaaai-editor-suite"))) {
      $bk = Join-Path $env:USERPROFILE ".claude\skills-backup-$TS"; New-Item -ItemType Directory -Force -Path $bk | Out-Null
      Move-Item $dst (Join-Path $bk $_.Name); Warn "原有的 $($_.Name) 已备份到 ~\.claude\skills-backup-$TS\"
    } elseif (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    Copy-Item $_.FullName $dst -Recurse; New-Item -ItemType File -Path (Join-Path $dst ".aaaai-editor-suite") -Force | Out-Null
    Ok $_.Name
  }
} else { Ok "跳过（-NoSkills）" }

# ---------- 6. HeyGen HyperFrames（其他格式） ----------
Step "6. HeyGen HyperFrames（讲解片／网站转影片／产品发布／音乐影片等格式，Apache-2.0）"
if (-not $NoHyperframes -and (Has "claude")) {
  & claude plugin marketplace add https://github.com/heygen-com/hyperframes.git *> $null
  if ((& claude plugin list 2>$null | Out-String) -match "core-skills") { Ok "已安装" }
  else { & claude plugin install core-skills@hyperframes *> $null; if ($LASTEXITCODE -eq 0) { Ok "core-skills@hyperframes" } else { Warn "没装上：之后执行 claude plugin install core-skills@hyperframes" } }
} elseif (-not $NoHyperframes) {
  Warn "没找到 Claude Code（本套件在 Claude Code 里使用）：到 https://claude.ai/download 下载安装"
  Todo "（选装）HyperFrames：装好 Claude Code 后执行 claude plugin marketplace add https://github.com/heygen-com/hyperframes.git ; claude plugin install core-skills@hyperframes"
} else { Ok "跳过" }

# ---------- 7. API 密钥（全部可选） ----------
Step "7. API 密钥（B-roll 用，全部可选，不绑也能剪片）"
$A = Join-Path $HOME_DIR "bin\aaaai-editor.cmd"
& $A keys 2>$null | Where-Object { $_ -match "^(✅|—)" } | ForEach-Object { "  $_" }
if (-not $NoKeys -and -not $Yes -and $TTY) {
  foreach ($k in @("PEXELS_API_KEY", "FAL_KEY", "HF_CREDENTIALS")) {
    if ((& $A keys 2>$null | Out-String) -match "✅ $k") { continue }
    $q = switch ($k) {
      "PEXELS_API_KEY" { "绑定 Pexels 免费素材库密钥（`$0，推荐）？先到 https://www.pexels.com/api/new/ 免费申请" }
      "FAL_KEY" { "绑定 fal 密钥（AI 生成 B-roll，按次付费，每次会先问你）？申请：https://fal.ai/dashboard/keys" }
      default { "绑定 Higgsfield 密钥（只在你指定时用，扣账户额度）？申请：https://cloud.higgsfield.ai/" }
    }
    $r = Read-Host "  $q [y/N]"
    if ($r -eq "y" -or $r -eq "Y") { & $A keys set $k } else { Ok "跳过 $k" }
  }
} else {
  Ok "之后想绑：在视窗执行 $A keys set <名称>"
  if (-not $NoKeys) { Todo "（选装）B-roll 密钥：执行 $A keys set PEXELS_API_KEY（免费）" }
}

# ---------- 8. 体检 ----------
Step "8. 体检"
& $A doctor
if ($TODO.Count -gt 0) { Step "还剩这些要你自己决定／在视窗里做"; foreach ($t in $TODO) { Write-Host "  · $t" } }
Write-Host ""
Write-Host "完成。在 Claude Code 里说「/aaaai-editor」或丢一段视频进去就能开始。"
Write-Host "Claude Desktop／Cursor 想用 B-roll 工具：把 MCP 服务器设为命令 $A、参数 mcp（见 docs\00-快速安装.md）。"
Write-Host "社群风格 mrone（© MR ONE）、otg（© OTG 社群）可以直接使用，品牌归原权利人，请勿用来冒充。"
