#!/bin/bash
# emoclaw-daemon-guard.sh — Start EmoClaw daemon safely.
# Prevents duplicate instances. Use this instead of launching daemon directly.
#
# Usage: bash emoclaw-daemon-guard.sh [start|stop|status]

PID_FILE="/tmp/Vintos-emotion.pid"
SOCK_PATH="/tmp/Vintos-emotion.sock"
DAEMON_DIR="$HOME/.vintos/workspace/emotion_model"
DAEMON_CMD="python3 daemon.py"

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "[EmoClaw Guard] Daemon running (PID $PID)"
            return 0
        else
            echo "[EmoClaw Guard] Stale PID file (process $PID dead)"
            rm -f "$PID_FILE"
            return 1
        fi
    fi

    # Check by socket
    if [ -S "$SOCK_PATH" ]; then
        PIDS=$(lsof "$SOCK_PATH" 2>/dev/null | awk 'NR>1{print $2}' | sort -u)
        if [ -n "$PIDS" ]; then
            COUNT=$(echo "$PIDS" | wc -l)
            echo "[EmoClaw Guard] Found $COUNT daemon(s) via socket: $PIDS"
            if [ "$COUNT" -gt 1 ]; then
                echo "[EmoClaw Guard] WARNING: Multiple daemons detected!"
            fi
            return 0
        fi
    fi

    echo "[EmoClaw Guard] Daemon not running"
    return 1
}

stop() {
    # Kill by PID file
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "[EmoClaw Guard] Killed daemon PID $PID"
        fi
        rm -f "$PID_FILE"
    fi

    # Kill any remaining by socket
    if [ -S "$SOCK_PATH" ]; then
        PIDS=$(lsof "$SOCK_PATH" 2>/dev/null | awk 'NR>1{print $2}' | sort -u)
        for PID in $PIDS; do
            kill "$PID" 2>/dev/null && echo "[EmoClaw Guard] Killed orphan PID $PID"
        done
    fi

    rm -f "$SOCK_PATH"
    echo "[EmoClaw Guard] Stopped"
}

start() {
    # Check if already running
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "[EmoClaw Guard] Daemon already running (PID $PID)"
            return 0
        else
            echo "[EmoClaw Guard] Cleaning stale PID file"
            rm -f "$PID_FILE"
        fi
    fi

    # Kill any orphans first
    if [ -S "$SOCK_PATH" ]; then
        PIDS=$(lsof "$SOCK_PATH" 2>/dev/null | awk 'NR>1{print $2}' | sort -u)
        for PID in $PIDS; do
            kill "$PID" 2>/dev/null && echo "[EmoClaw Guard] Killed orphan PID $PID"
        done
        sleep 1
        rm -f "$SOCK_PATH"
    fi

    # Start daemon
    cd "$DAEMON_DIR" || { echo "[EmoClaw Guard] Cannot cd to $DAEMON_DIR"; exit 1; }
    source .venv/bin/activate 2>/dev/null


    # Always restore emotion_vector from last trajectory entry
    python3 -c "
import json
path = '/home/gloria/.vintos/workspace/memory/emotional-state.json'
try:
    with open(path) as f:
        d = json.load(f)
    traj = d.get('trajectory', [])
    if traj:
        d['emotion_vector'] = traj[-1]['v']
        with open(path, 'w') as f:
            json.dump(d, f, indent=2)
        print('[EmoClaw Guard] State restored from trajectory')
    else:
        print('[EmoClaw Guard] No trajectory — using existing state')
except Exception as e:
    print(f'[EmoClaw Guard] State restore failed: {e}')
"

    PYTHONPATH=.. nohup .venv/bin/python3 daemon.py >> /tmp/emoclaw-daemon.log 2>&1 &
    NEW_PID=$!
    echo "$NEW_PID" > "$PID_FILE"
    echo "[EmoClaw Guard] Started daemon PID $NEW_PID"

    # Verify it's actually running after 2 seconds
    sleep 2
    if kill -0 "$NEW_PID" 2>/dev/null; then
        echo "[EmoClaw Guard] Daemon healthy"
    else
        echo "[EmoClaw Guard] WARNING: Daemon died immediately! Check /tmp/emoclaw-daemon.log"
        rm -f "$PID_FILE"
        return 1
    fi
}

case "${1:-status}" in
    start)  start ;;
    stop)   stop ;;
    status) status ;;
    restart)
        stop
        sleep 2
        start
        ;;
    *)
        echo "Usage: emoclaw-daemon-guard.sh [start|stop|status|restart]"
        ;;
esac
