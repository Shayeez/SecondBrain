#!/usr/bin/env bash
# ==============================================================================
# Second Brain - macOS Launcher
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please run ./setup_mac.sh first."
    exit 1
fi

# Ensure Ollama is running if installed
if command -v ollama &>/dev/null; then
    if ! pgrep -x "ollama" &>/dev/null; then
        echo "🦙 Starting local Ollama engine..."
        ollama serve &>/dev/null &
        sleep 1
    fi
fi

source .venv/bin/activate
echo "🧠 Starting Second Brain Web Deck on http://127.0.0.1:8020 ..."
exec start-brain
