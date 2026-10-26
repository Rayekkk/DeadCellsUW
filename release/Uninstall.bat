@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dcuw.ps1" uninstall %*
pause
