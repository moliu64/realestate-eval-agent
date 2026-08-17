@echo off
setlocal
cd /d "%~dp0"
set "CLOUDFLARED=C:\Program Files (x86)\cloudflared\cloudflared.exe"
if not exist "%CLOUDFLARED%" (
  echo cloudflared not found. Install Cloudflare Tunnel first.
  pause
  exit /b 1
)
echo Publishing http://127.0.0.1:8000 at https://060115.top
"%CLOUDFLARED%" tunnel --config "%USERPROFILE%\.cloudflared\config.yml" run
pause
