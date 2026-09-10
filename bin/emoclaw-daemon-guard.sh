#!/bin/bash
# emoclaw-daemon-guard.sh — Start EmoClaw daemon safely.
# Prevents duplicate instances. Use this instead of launching daemon directly.
#
# Usage: bash emoclaw-daemon-guard.sh [ensure|start|stop|status|restart]
#   (no argument) / ensure — the cron entry point: if the daemon is down, request a
#   start (systemctl --user start $UNIT when that unit exists, else launch daemon.py
#   the way the unit would), with a bounded retry. Idempotent when already running.
# See docs/emoclaw-daemon.md for ownership, socket and protocol.

PID_FILE="${EMOCLAW_PID_FILE:-/tmp/Vintos-emotion.pid}"
SOCK_PATH="${EMOCLAW_SOCK_PATH:-/tmp/Vintos-emotion.sock}"
DAEMON_DIR="${EMOCLAW_DAEMON_DIR:-$HOME/.vintos/workspace/emotion_model}"
DAEMON_CMD="python3 daemon.py"
UNIT="${EMOCLAW_UNIT:-vintos-emotion.service}"
DAEMON_LOG="${EMOCLAW_DAEMON_LOG:-/tmp/emoclaw-daemon.log}"
STATE_FILE="${EMOCLAW_STATE_FILE:-$HOME/.vintos/workspace/memory/emotional-state.json}"
ENSURE_RETRIES="${EMOCLAW_ENSURE_RETRIES:-3}"
ENSURE_WAIT="${EMOCLAW_ENSURE_WAIT:-2}"

glog() {
    # one line per event, to the daemon's existing log path
    echo "$(date '+%Y-%m-%d %H:%M:%S') [EmoClaw Guard] $*" >> "$DAEMON_LOG" 2>/dev/null
}

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
    cd "$DAEMON_DIR" || { echo "[EmoClaw Guard] Cannot cd to $DAEMON_DIR"; glog "cannot cd to $DAEMON_DIR"; return 1; }
    source .venv/bin/activate 2>/dev/null


    # Always restore emotion_vector from last trajectory entry
    python3 -c "
import json
path = '$STATE_FILE'
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

    PY=".venv/bin/python3"; [ -x "$PY" ] || PY="python3"
    PYTHONPATH=.. nohup "$PY" daemon.py >> "$DAEMON_LOG" 2>&1 &
    NEW_PID=$!
    echo "$NEW_PID" > "$PID_FILE"
    echo "[EmoClaw Guard] Started daemon PID $NEW_PID"

    # Verify it's actually running after 2 seconds
    sleep 2
    if kill -0 "$NEW_PID" 2>/dev/null; then
        echo "[EmoClaw Guard] Daemon healthy"
    else
        echo "[EmoClaw Guard] WARNING: Daemon died immediately! Check $DAEMON_LOG"
        rm -f "$PID_FILE"
        return 1
    fi
}

unit_exists() {
    command -v systemctl >/dev/null 2>&1 || return 1
    systemctl --user list-unit-files "$UNIT" 2>/dev/null | grep -q "^$UNIT"
}

# Request a start the way the daemon is normally owned: the user unit if it is
# installed, otherwise the direct launch above. Returns non-zero if the request failed.
request_start() {
    if unit_exists; then
        glog "daemon down — requesting systemctl --user start $UNIT"
        systemctl --user start "$UNIT" >/dev/null 2>&1
    else
        glog "daemon down — unit $UNIT not installed, launching $DAEMON_DIR/daemon.py directly"
        start >/dev/null
    fi
}

ensure() {
    # Idempotent: a running daemon means nothing to do and no log line.
    if status >/dev/null 2>&1; then
        echo "[EmoClaw Guard] Daemon running — nothing to do"
        return 0
    fi
    local attempt=1
    while [ "$attempt" -le "$ENSURE_RETRIES" ]; do
        request_start
        sleep "$ENSURE_WAIT"
        if status >/dev/null 2>&1; then
            glog "daemon up after start request (attempt $attempt/$ENSURE_RETRIES)"
            echo "[EmoClaw Guard] Daemon started (attempt $attempt)"
            return 0
        fi
        attempt=$((attempt + 1))
    done
    glog "daemon still down after $ENSURE_RETRIES start attempts — giving up until next run"
    echo "[EmoClaw Guard] Daemon still down after $ENSURE_RETRIES attempts (see $DAEMON_LOG)"
    return 1
}

case "${1:-ensure}" in
    ensure) ensure ;;
    start)  start ;;
    stop)   stop ;;
    status) status ;;
    restart)
        stop
        sleep 2
        start
        ;;
    *)
        echo "Usage: emoclaw-daemon-guard.sh [ensure|start|stop|status|restart]"
        ;;
esac
