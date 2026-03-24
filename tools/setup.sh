#!/usr/bin/env bash
# Setup script for the Ramen Rater data pipeline.
# Creates a venv (if needed), installs dependencies, and ensures
# Playwright + uBlock Origin Lite are ready.
#
# Usage:
#   bash tools/setup.sh          # setup only
#   bash tools/setup.sh run      # setup + run the pipeline
#   bash tools/setup.sh run 20   # setup + run with --limit 20

set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

VENV_DIR="$ROOT/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python -m venv "$VENV_DIR"
fi

# Resolve venv Python/pip directly (more reliable than source activate on Windows)
if [ -f "$VENV_DIR/Scripts/python.exe" ]; then
    PYTHON="$VENV_DIR/Scripts/python.exe"
    PIP="$VENV_DIR/Scripts/pip.exe"
elif [ -f "$VENV_DIR/bin/python" ]; then
    PYTHON="$VENV_DIR/bin/python"
    PIP="$VENV_DIR/bin/pip"
else
    echo "ERROR: Could not find Python in venv at $VENV_DIR"
    exit 1
fi

echo "Python: $("$PYTHON" --version) at $PYTHON"

echo "Installing Python dependencies..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r tools/requirements.txt

echo ""
echo "Setup complete! Playwright browser + uBlock will auto-install on first run."
echo "PaddleOCR orientation model will download automatically on first run."

if [ "$1" = "run" ]; then
    shift
    ARGS=""
    if [ -n "$1" ]; then
        ARGS="--limit $1"
    fi
    echo "Running pipeline... $ARGS"
    "$PYTHON" tools/fetch_ramen_data.py $ARGS
fi
