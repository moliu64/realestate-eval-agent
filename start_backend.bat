@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found. Run: python -m venv .venv
  pause
  exit /b 1
)
echo Starting backend at http://127.0.0.1:8000
".venv\Scripts\python.exe" run_backend.py
pause
