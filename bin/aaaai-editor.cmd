@echo off
rem aaaai-editor launcher (Windows cmd / PowerShell / MCP)
setlocal
set "PYTHONUTF8=1"
set "PYTHONPATH=%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -X utf8 -m aaaai_editor %*
) else (
  python -X utf8 -m aaaai_editor %*
)
exit /b %errorlevel%
