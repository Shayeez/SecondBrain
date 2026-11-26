#!/usr/bin/env bash
# ==============================================================================
# Second Brain - VPS SSH Tunnel Manager (Ollama Port Forwarding)
# ==============================================================================

VPS_USER="app_test"
VPS_HOST="51.81.203.132"
LOCAL_PORT="11434"
REMOTE_PORT="11434"

function status_tunnel() {
    if curl -s -m 1.5 http://127.0.0.1:${LOCAL_PORT}/api/tags &>/dev/null; then
        echo "✅ VPS SSH Tunnel is ACTIVE and responding on http://127.0.0.1:${LOCAL_PORT}"
        echo "Installed models on VPS:"
        curl -s http://127.0.0.1:${LOCAL_PORT}/api/tags | grep -o '"name":"[^"]*"' | tr -d '"' | sed 's/name:/  • /'
    else
        echo "❌ VPS SSH Tunnel is NOT active on port ${LOCAL_PORT}."
    fi
}

function start_tunnel() {
    if curl -s -m 1.5 http://127.0.0.1:${LOCAL_PORT}/api/tags &>/dev/null; then
        echo "ℹ️  Tunnel is already running on port ${LOCAL_PORT}."
        return 0
    fi

    echo "🔗 Opening background SSH tunnel to ${VPS_USER}@${VPS_HOST}..."
    ssh -f -N -L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT} ${VPS_USER}@${VPS_HOST}
    sleep 1

    status_tunnel
}

function stop_tunnel() {
    echo "🛑 Terminating SSH tunnel on port ${LOCAL_PORT}..."
    pkill -f "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" || true
    echo "Done."
}

case "$1" in
    start)
        start_tunnel
        ;;
    stop)
        stop_tunnel
        ;;
    status)
        status_tunnel
        ;;
    foreground)
        echo "🔗 Opening foreground SSH tunnel (Ctrl+C to quit)..."
        ssh -N -L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT} ${VPS_USER}@${VPS_HOST}
        ;;
    *)
        echo "Usage: $0 {start|stop|status|foreground}"
        echo ""
        echo "Commands:"
        echo "  start       - Launch background SSH tunnel to VPS Ollama"
        echo "  stop        - Close the SSH tunnel"
        echo "  status      - Check if Ollama port is responding"
        echo "  foreground  - Run interactive tunnel in current terminal tab"
        exit 1
        ;;
esac
