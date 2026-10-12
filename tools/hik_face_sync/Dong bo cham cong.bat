@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dong-bo-cham-cong.ps1" %*
echo.
pause
