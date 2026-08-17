@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_online.ps1"
if errorlevel 1 (
  echo Failed to start the online deployment.
  pause
  exit /b 1
)
echo Online deployment started: https://060115.top
timeout /t 3 /nobreak >nul
