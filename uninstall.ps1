# aaaai-editor 卸载（Windows）：程序、skill、MCP 注册都移到「资源回收筒」（可救回）。
# 你的设置、风格、频道档案、字体、模型（~\.aaaai-editor 里的）和项目目录默认保留；加 -All 连 ~\.aaaai-editor 也移到资源回收筒。
# Windows 凭据管理器里的 API 密钥不会动：要删就先执行 aaaai-editor keys remove <名称>。
param([switch]$All)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
Add-Type -AssemblyName Microsoft.VisualBasic
$HOME_DIR = if ($env:AAAAI_EDITOR_HOME) { $env:AAAAI_EDITOR_HOME } else { Join-Path $env:USERPROFILE ".aaaai-editor" }
function Recycle($p) {
  if (-not (Test-Path $p)) { return $false }
  if ((Get-Item $p) -is [System.IO.DirectoryInfo]) {
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p, 'OnlyErrorDialogs', 'SendToRecycleBin')
  } else {
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p, 'OnlyErrorDialogs', 'SendToRecycleBin')
  }
  return $true
}
if (Recycle (Join-Path $HOME_DIR "app")) { Write-Host "✔ 程序已移到资源回收筒" }
Recycle (Join-Path $HOME_DIR "bin") | Out-Null
$skills = Join-Path $env:USERPROFILE ".claude\skills"
foreach ($n in @("aaaai-editor", "motion-graphic-video-editor", "social-content-pipeline")) {
  $d = Join-Path $skills $n
  if (Recycle $d) { Write-Host "✔ skill $n 已移到资源回收筒" }
  $b = Get-ChildItem -Directory (Join-Path $env:USERPROFILE ".claude") -Filter "skills-backup-*" -ErrorAction SilentlyContinue |
       Sort-Object Name | ForEach-Object { Join-Path $_.FullName $n } | Where-Object { Test-Path $_ } | Select-Object -Last 1
  if ($b) { Move-Item $b $d; Write-Host "  ↩ 还原安装前的 $n" }
}
if (Get-Command claude -ErrorAction SilentlyContinue) {
  & claude mcp remove aaaai-editor *> $null; if ($LASTEXITCODE -eq 0) { Write-Host "✔ 已取消 Claude Code 的 MCP 注册" }
  if ((& claude plugin list 2>$null | Out-String) -match "aaaai-editor@aaaai-editor") { & claude plugin uninstall aaaai-editor@aaaai-editor *> $null; Write-Host "✔ 已卸载 Claude Code 插件" }
}
$binDir = Join-Path $HOME_DIR "bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -and ($userPath.Split(";") -contains $binDir)) {
  [Environment]::SetEnvironmentVariable("Path", (($userPath.Split(";") | Where-Object { $_ -and $_ -ne $binDir }) -join ";"), "User")
  Write-Host "✔ 已从使用者 PATH 移除 aaaai-editor"
}
if ($All -and (Test-Path $HOME_DIR)) { Recycle $HOME_DIR | Out-Null; Write-Host "✔ 设置／风格／档案／模型也已移到资源回收筒" }
else { Write-Host "保留：$HOME_DIR 里的设置／风格／频道档案／字体／模型，以及你的项目目录（要全清：uninstall.ps1 -All）。" }
Write-Host "winget 装的 Python、FFmpeg、Git 没动（别的程序可能也在用）；HyperFrames 要移除：claude plugin uninstall core-skills@hyperframes"
