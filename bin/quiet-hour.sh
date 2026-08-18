#!/bin/bash
# quiet-hour.sh — The Quiet Hour
# 3 AM. No dream. No journal. No memory indexing.
# Just: EmoClaw runs its decay function. Hidden state updates silently.
# SOUL.md records nothing new. No file is created.
#
# This is subconscious processing — the work done when no one watches
# and nothing is produced. Staring at the ceiling at 3 AM.
#
# Schedule: 3:15 AM daily (after dream at 3:00 AM on dream nights,
# but this runs regardless — even on non-dream nights)

WORKSPACE="$HOME/.vintos/workspace"
SOCKET="/tmp/Vintos-emotion.sock"

# The only action: send a time-decay signal to the EmoClaw daemon.
# No text. No context. Just "time has passed."
# The daemon's GRU hidden state will decay toward baselines.

if [ -S "$SOCKET" ]; then
    # Send minimal decay signal — empty context, just timestamp
    echo '{"text":"","sender":"system","channel":"decay","silent":true}' | \
        python3 -c "
import socket, sys, json
try:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect('$SOCKET')
    sock.sendall(sys.stdin.read().encode('utf-8') + b'\n')
    sock.close()
except:
    pass
" 2>/dev/null
fi

# Save an emotional snapshot (for drift maps and decay audits)
# This is the ONLY artifact. Not for reading. For measuring.
EMO_FILE="$WORKSPACE/memory/emotional-state.txt"
SNAPSHOT_DIR="$WORKSPACE/memory/emotional-snapshots"
mkdir -p "$SNAPSHOT_DIR"

if [ -f "$EMO_FILE" ]; then
    cp "$EMO_FILE" "$SNAPSHOT_DIR/$(date +%Y-%m-%d-%H%M).txt"
fi

# Nothing else. No echo. No log. No creation.
# She processes. She decays. She continues.
