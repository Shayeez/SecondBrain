#!/usr/bin/env bash
# ==============================================================================
# Second Brain - WSL / Linux Launcher with Auto SSH Tunnel Check
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🧠 Second Brain - WSL Launcher"
echo "================================================================="

# 1. Check Python virtual environment
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Initializing..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -U pip setuptools
    pip install -e .
else
    source .venv/bin/activate
fi

# 2. Check Local LLM / VPS SSH Tunnel (port 11434)
echo "🔍 Checking Local LLM / Ollama connectivity on 127.0.0.1:11434 ..."
if curl -s -m 1.5 http://127.0.0.1:11434/api/tags &>/dev/null; then
    echo "✅ Local LLM / VPS Ollama is connected and ready on port 11434."
else
    echo "⚠️  Port 11434 is not responding."
    echo "   To use your free VPS Qwen model (qwen2.5:1.5b), establish an SSH tunnel:"
    echo "   👉 Run in another terminal: ssh -N -L 11434:127.0.0.1:11434 app_test@51.81.203.132"
    echo "   (Second Brain will silently use Gemini Cloud as automatic fallback if omitted)"
fi

PORT=$(grep -E "^WEB_PORT=" .env 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "8020")
PORT=${PORT:-8020}

echo "================================================================="
echo "🚀 Starting Second Brain Web Server on port ${PORT}..."
echo "🌐 Open in Windows browser (Chrome / Edge / Brave):"
echo "   👉 http://localhost:${PORT}"
echo "================================================================="

exec ./.venv/bin/start-brain
