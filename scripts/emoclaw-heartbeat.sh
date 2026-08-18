#!/bin/bash
# emoclaw-heartbeat.sh — Health monitor for EmoClaw daemon.
# Checks: daemon alive, emotional state fresh, socket responsive.
# Auto-restarts on failure. Sends ntfy alert.
# Runs every 10 minutes via cron.

PID_FILE="/tmp/Vintos-emotion.pid"
SOCK_PATH="/tmp/Vintos-emotion.sock"
EMO_FILE="$HOME/.vintos/workspace/memory/emotional-state.txt"
GUARD="$HOME/.vintos/workspace/scripts/emoclaw-daemon-guard.sh"
NTFY_TOPIC="vintos-alerts"
LOG="/tmp/emoclaw-heartbeat.log"
MAX_STALE_MINUTES=30

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

alert() {
    local msg="$1"
    local priority="${2:-default}"
    log "ALERT: $msg"
    curl -s --max-time 30 -o /dev/null \
        -H "Title: EmoClaw Health" \
        -H "Priority: $priority" \
        -H "Tags: heart,warning" \
        -d "$msg" \
        "https://ntfy.sh/$NTFY_TOPIC" 2>/dev/null
}

# === CHECK 1: Is daemon process alive? ===
DAEMON_ALIVE=false
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        # Verify it's actually emoclaw, not a recycled PID
        CMDLINE=$(cat /proc/$PID/cmdline 2>/dev/null | tr '\0' ' ')
        if echo "$CMDLINE" | grep -qi "emoclaw\|emotion.*daemon"; then
            DAEMON_ALIVE=true
        else
            log "WARN — PID $PID alive but not emoclaw (recycled PID). Cmdline: $CMDLINE"
            rm -f "$PID_FILE"
        fi
    fi
fi

# Also check socket
if [ -S "$SOCK_PATH" ]; then
    SOCK_PIDS=$(lsof "$SOCK_PATH" 2>/dev/null | awk 'NR>1{print $2}' | sort -u | head -1)
    if [ -n "$SOCK_PIDS" ]; then
        DAEMON_ALIVE=true
    fi
fi

# === CHECK 2: Is emotional state fresh? ===
STATE_FRESH=false
if [ -f "$EMO_FILE" ]; then
    # File age in minutes
    FILE_AGE=$(( ($(date +%s) - $(stat -c %Y "$EMO_FILE" 2>/dev/null || echo 0)) / 60 ))
    if [ "$FILE_AGE" -lt "$MAX_STALE_MINUTES" ]; then
        STATE_FRESH=true
    fi
fi

# === CHECK 3: Can we talk to the socket? ===
SOCKET_RESPONSIVE=false
if [ -S "$SOCK_PATH" ]; then
    # Quick socket test — send empty and see if we get a response
    REPLY=$(echo '{"text":"heartbeat check","source":"heartbeat"}' | timeout 5 socat - UNIX-CONNECT:"$SOCK_PATH" 2>/dev/null)
    if [ -n "$REPLY" ]; then
        SOCKET_RESPONSIVE=true
    fi
fi

# === DECIDE ===
if $DAEMON_ALIVE && $STATE_FRESH; then
    # Healthy — log silently
    log "OK — daemon alive, state fresh (${FILE_AGE}m old)"
    exit 0
fi

# Something's wrong
if ! $DAEMON_ALIVE; then
    log "FAIL — daemon not alive, restarting..."
    alert "EmoClaw daemon dead — auto-restarting" "high"
    bash "$GUARD" restart >> "$LOG" 2>&1
    sleep 3

    # Verify restart worked
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        log "Restart successful"
        alert "EmoClaw restarted successfully" "default"
    else
        log "RESTART FAILED"
        alert "EmoClaw restart FAILED — needs manual intervention" "urgent"
    fi

elif ! $STATE_FRESH; then
    log "STALE — emotional state is ${FILE_AGE}m old (max ${MAX_STALE_MINUTES}m)"
    
    if $DAEMON_ALIVE; then
        # Daemon alive but state stale — maybe sync isn't running
        alert "EmoClaw state stale (${FILE_AGE}m) but daemon alive — possible sync issue" "high"
        # Force a sync
        bash "$HOME/.vintos/workspace/scripts/emoclaw-sync.sh" >> /tmp/vintos-emoclaw-sync.log 2>&1
        log "Forced sync"
    else
        alert "EmoClaw state stale AND daemon dead — restarting" "urgent"
        bash "$GUARD" restart >> "$LOG" 2>&1
    fi
fi
