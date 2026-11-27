@echo off
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  python launch.py
) else (
  py -3 launch.py
)
if errorlevel 1 pause
