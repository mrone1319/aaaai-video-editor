@echo off
rem aaaai-editor: install HeyGen HyperFrames only (after Claude Code is installed)
rem The classic console window (conhost) has no Chinese glyphs, so Chinese text shows as "?".
rem If Windows Terminal is installed, re-open this script inside it (WT_SESSION is set there, so no loop).
rem Set AAAAI_NO_WT=1 to stay in the current window.
if not defined WT_SESSION if not defined AAAAI_NO_WT (
  where wt.exe >nul 2>nul
  if not errorlevel 1 (
    start "" wt.exe -d "%~dp0." cmd /c "%~f0" %*
    exit /b 0
  )
)
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -OnlyHyperframes %*
echo.
echo Install log: %USERPROFILE%\.aaaai-editor\install-log.txt
pause
