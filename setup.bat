@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_CMD=py -3.12"
  ) else (
    py -3.13 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.13"
  )
)
if not defined PYTHON_CMD set "PYTHON_CMD=python"
call %PYTHON_CMD% tools\setup_peer.py
if errorlevel 1 (
  echo Setup failed. Install Python 3.12 and read docs\PEER_DEPLOYMENT.md.
  pause
  exit /b 1
)
echo Setup complete. Double-click start.bat.
pause
