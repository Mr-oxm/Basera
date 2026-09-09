#!/usr/bin/env bash
set -e

# Navigate to project root
cd "$(dirname "$0")"

echo "==================================================="
echo "              Launching Basera Photo Editor        "
echo "==================================================="
echo ""

# 1. Git pull
echo "[1/3] Checking for updates (git pull)..."
git pull || echo "[WARNING] Git pull failed. Continuing with local version..."
echo ""

# 2. Sync dependencies
echo "[2/3] Syncing dependencies (uv sync)..."
if ! command -v uv &> /dev/null; then
    echo "[ERROR] 'uv' is not installed or not in PATH."
    echo "Install it via: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

uv sync
echo ""

# 3. Run application
echo "[3/3] Starting Basera Photo Editor..."
echo ""
uv run python -m photo_editor "$@"
