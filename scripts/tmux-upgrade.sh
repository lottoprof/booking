#!/bin/bash
set -e

# ── Configuration ──────────────────────────────────────────
# Override via environment or edit defaults
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
DB_PATH="${DB_PATH:-$PROJECT_DIR/data/sqlite/booking.db}"
SESSION="upgrade"

# ── Derived paths ──────────────────────────────────────────
VENV="$PROJECT_DIR/venv/bin"
GATEWAY_DIR="$PROJECT_DIR/gateway"
BACKEND_DIR="$PROJECT_DIR/backend"
GATEWAY_CMD="cd $GATEWAY_DIR && PYTHONPATH=$PROJECT_DIR $VENV/uvicorn app.main:app --host 127.0.0.1 --port 8080"
BACKEND_CMD="cd $BACKEND_DIR && PYTHONPATH=$PROJECT_DIR $VENV/uvicorn app.main:app --host 127.0.0.1 --port 8000"

# ── Functions ──────────────────────────────────────────────

start() {
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "[warn] Session '$SESSION' already exists"
        exit 1
    fi

    echo "[start] Creating tmux session '$SESSION' in $PROJECT_DIR"

    tmux new-session -d -s "$SESSION" -n servers -c "$PROJECT_DIR"

    # Pane 1: gateway (8080)
    tmux send-keys -t "$SESSION:1.1" "$GATEWAY_CMD" Enter

    # Pane 2: backend (8000)
    tmux split-window -v -t "$SESSION:1" -c "$PROJECT_DIR"
    tmux send-keys -t "$SESSION:1.2" "$BACKEND_CMD" Enter

    # Window 2: sqlite
    tmux new-window -t "$SESSION" -n db -c "$PROJECT_DIR"
    tmux send-keys -t "$SESSION:2.1" "sqlite3 $DB_PATH" Enter

    # Focus on servers window
    tmux select-window -t "$SESSION:1"

    echo "[start] Done. Attach with: tmux attach -t $SESSION"
}

stop() {
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "[warn] Session '$SESSION' not found"
        exit 0
    fi

    echo "[stop] Killing session '$SESSION'"
    tmux kill-session -t "$SESSION"
    echo "[stop] Done"
}

restart() {
    echo "[restart] Restarting servers in session '$SESSION'"

    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "[warn] Session not found, starting fresh"
        start
        return
    fi

    # Restart gateway
    tmux send-keys -t "$SESSION:1.1" C-c
    sleep 1
    tmux send-keys -t "$SESSION:1.1" "find $PROJECT_DIR -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null; $GATEWAY_CMD" Enter

    # Restart backend
    tmux send-keys -t "$SESSION:1.2" C-c
    sleep 1
    tmux send-keys -t "$SESSION:1.2" "find $PROJECT_DIR -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null; $BACKEND_CMD" Enter

    echo "[restart] Done. Check logs with: $0 logs"
}

status() {
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "Session '$SESSION': STOPPED"
        exit 1
    fi

    echo "Session '$SESSION': RUNNING"
    echo ""

    # Check gateway
    if tmux capture-pane -t "$SESSION:1.1" -p 2>/dev/null | grep -q "Uvicorn running"; then
        echo "  gateway (8080): OK"
    else
        echo "  gateway (8080): UNKNOWN (check logs)"
    fi

    # Check backend
    if tmux capture-pane -t "$SESSION:1.2" -p 2>/dev/null | grep -q "Uvicorn running"; then
        echo "  backend (8000): OK"
    else
        echo "  backend (8000): UNKNOWN (check logs)"
    fi
}

logs() {
    local target="${1:-all}"
    case "$target" in
        gateway)
            tmux capture-pane -t "$SESSION:1.1" -p | tail -20
            ;;
        backend)
            tmux capture-pane -t "$SESSION:1.2" -p | tail -20
            ;;
        all)
            echo "=== Gateway ==="
            tmux capture-pane -t "$SESSION:1.1" -p | tail -10
            echo ""
            echo "=== Backend ==="
            tmux capture-pane -t "$SESSION:1.2" -p | tail -10
            ;;
        *)
            echo "Usage: $0 logs [gateway|backend|all]"
            ;;
    esac
}

# ── Main ───────────────────────────────────────────────────

case "${1:-}" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    logs)    logs "$2" ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [gateway|backend|all]}"
        echo ""
        echo "Environment variables:"
        echo "  PROJECT_DIR  Project root (default: auto-detect from script location)"
        echo "  DB_PATH      SQLite database path (default: \$PROJECT_DIR/data/sqlite/booking.db)"
        exit 1
        ;;
esac
