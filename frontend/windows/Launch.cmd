@echo off
cd /d "%~dp0\..\.."
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "frontend\windows\launch.py"
) else (
  python "frontend\windows\launch.py"
  if errorlevel 1 pause
)
