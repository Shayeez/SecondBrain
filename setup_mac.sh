#!/usr/bin/env bash
# ==============================================================================
# Second Brain - macOS One-Click Setup Script
# ==============================================================================
set -e

echo "🧠 Starting Second Brain macOS Setup..."
echo "------------------------------------------------"

# 1. Detect macOS Architecture
ARCH=$(uname -m)
OS=$(uname -s)

if [ "$OS" != "Darwin" ]; then
    echo "⚠️ This script is intended for macOS (Darwin). Detected: $OS"
fi

if [ "$ARCH" = "arm64" ]; then
    echo "⚡ Apple Silicon ($ARCH) detected. Metal GPU acceleration will be enabled."
else
    echo "💻 Intel Mac ($ARCH) detected."
fi

# 2. Check Xcode Command Line Tools (Required for ChromaDB C++ bindings)
if ! xcode-select -p &>/dev/null; then
    echo "📦 Installing Xcode Command Line Tools (required for ChromaDB native extensions)..."
    xcode-select --install
    echo "Please complete the Apple Xcode installation dialog and rerun this script."
    exit 1
fi
echo "✓ Xcode Command Line Tools verified."

# 3. Check for Homebrew
if ! command -v brew &>/dev/null; then
    echo "💡 Homebrew not found. We recommend installing it from https://brew.sh for managing Python & Ollama."
fi

# 4. Check Python 3 (3.10+)
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &>/dev/null; then
    echo "❌ python3 not found. Please install Python 3.10+ via Homebrew: brew install python@3.11"
    exit 1
fi

PY_VER=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Found Python $PY_VER"

# 5. Check or Install Ollama for Local LLM
if ! command -v ollama &>/dev/null; then
    echo "💡 Ollama not found in PATH."
    if command -v brew &>/dev/null; then
        echo "Installing Ollama via Homebrew..."
        brew install ollama
    else
        echo "Please download Ollama for macOS from https://ollama.com/download"
    fi
else
    echo "✓ Ollama is installed."
fi

# 6. Setup Python Virtual Environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "🔨 Creating Python virtual environment in .venv..."
    $PYTHON_CMD -m venv .venv
fi

echo "📦 Installing Python dependencies..."
./.venv/bin/pip install -U pip setuptools
./.venv/bin/pip install -e .

# 7. Setup Environment File (.env)
if [ ! -f ".env" ]; then
    echo "📝 Creating .env from template (.env.example)..."
    cp .env.example .env
    echo "⚠️ IMPORTANT: Please edit .env to insert your GEMINI_API_KEY before running."
fi

# 8. Setup Local macOS Storage Directory
DEFAULT_STORAGE="$HOME/SecondBrain"
if [ ! -d "$DEFAULT_STORAGE" ]; then
    echo "📁 Creating default storage directory at $DEFAULT_STORAGE..."
    mkdir -p "$DEFAULT_STORAGE"/{Raw_Inbox,Processed_Wiki,users}
fi

# 9. Pull Local Model with Ollama
if command -v ollama &>/dev/null; then
    echo "📥 Checking Local LLM (qwen2.5:1.5b)..."
    # Ensure Ollama service is responsive
    if ! pgrep -x "ollama" &>/dev/null; then
        echo "Starting Ollama in background..."
        ollama serve &>/dev/null &
        sleep 2
    fi
    echo "Pulling qwen2.5:1.5b (1.5B parameters, optimized for Apple Silicon Metal)..."
    ollama pull qwen2.5:1.5b || echo "⚠️ Could not pull model automatically. Run 'ollama pull qwen2.5:1.5b' manually."
fi

echo "------------------------------------------------"
echo "🎉 Setup Complete! To start Second Brain on macOS:"
echo "   ./run_mac.sh"
echo "   or open http://localhost:8020 in Safari/Chrome."
echo "------------------------------------------------"
