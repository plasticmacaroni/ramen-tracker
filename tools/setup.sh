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

if [ -f "$VENV_DIR/Scripts/activate" ]; then
    source "$VENV_DIR/Scripts/activate"
elif [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi

echo "Python: $(python --version) at $(which python)"

echo "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r tools/requirements.txt

# Install Node.js dependencies (tesseract.js for image orientation detection)
if command -v node &> /dev/null && command -v npm &> /dev/null; then
    echo "Installing Node.js dependencies (tesseract.js)..."
    mkdir -p tools/.cache
    (cd tools/.cache && npm install --quiet)
    echo "Node: $(node --version)"
else
    echo "NOTE: Node.js not found. Image orientation auto-fix will be skipped."
    echo "  Install from: https://nodejs.org"
fi

echo ""
echo "Setup complete! Playwright browser + uBlock will auto-install on first run."

if [ "$1" = "run" ]; then
    shift
    ARGS=""
    if [ -n "$1" ]; then
        ARGS="--limit $1"
    fi
    echo "Running pipeline... $ARGS"
    python tools/fetch_ramen_data.py $ARGS
fi
