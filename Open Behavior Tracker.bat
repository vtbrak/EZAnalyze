@echo off
REM Double-click launcher for the Behavior Tracker GUI (Windows).
REM Uses the project's own virtual environment; creates it on first run.
REM (Mac equivalent: "Open Behavior Tracker.command")

REM Move to this script's own folder (handles spaces in the path).
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"

if exist "%PY%" goto launch

echo First run - setting up the environment (this can take a few minutes)...

REM Prefer the "py" launcher that the python.org installer adds; fall back to python.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if not exist "%PY%" (
    echo.
    echo Could not create the virtual environment.
    echo Install Python 3 from https://www.python.org/downloads/ and tick
    echo "Add python.exe to PATH" during setup, then run this again.
    pause
    exit /b 1
)

"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Dependency install failed. See the messages above.
    pause
    exit /b 1
)

:launch
REM Runs in this console window so any error messages stay visible.
"%PY%" gui.py
if errorlevel 1 (
    echo.
    echo The app closed with an error. See the messages above.
    pause
)
