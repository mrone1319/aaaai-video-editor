@echo off
rem aaaai-editor: double-click to uninstall on Windows (files go to the Recycle Bin)
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
echo.
pause
