@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Python virtual environment not found. Run: python -m venv .venv
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "launcher.py"
