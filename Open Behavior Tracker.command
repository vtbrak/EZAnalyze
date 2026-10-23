#!/bin/bash
# Double-click launcher for the Behavior Tracker GUI (macOS).
# Uses the project's own virtual environment; creates it on first run.

# Move to this script's own directory (handles spaces in the path).
cd "$(dirname "$0")" || exit 1

VENV=".venv"
PY="$VENV/bin/python"

# First-run setup: build the venv and install dependencies.
if [ ! -x "$PY" ]; then
    echo "First run — setting up the environment (this can take a minute)…"
    python3 -m venv "$VENV" || { echo "Could not create virtual environment."; exit 1; }
    "$PY" -m pip install -r requirements.txt || { echo "Dependency install failed."; exit 1; }
fi

# Launch the app.
exec "$PY" gui.py
