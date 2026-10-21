@echo off
setlocal
cd /d "%~dp0"
echo  AutoTemplates - dezinstalare (setarile si template-urile raman)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall.ps1"
echo.
pause
