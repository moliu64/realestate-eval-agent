@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found. Run: python -m venv .venv
  pause
  exit /b 1
)
echo Starting RealEstate Eval Agent at http://127.0.0.1:8000
echo Tip: double-click start_panel.bat for the local launcher panel.
".venv\Scripts\python.exe" run.py web
pause
