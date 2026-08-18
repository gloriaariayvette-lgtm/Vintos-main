#!/bin/bash
# vintos-emotion-decay.sh — exponential mean reversion toward Vintos's resting state.
# Baselines and half-lives come from his emotion_model/config.py — single source of truth.
if [ ! -S "/tmp/Vintos-emotion.sock" ]; then
    echo "[$(date)] Decay skipped — daemon socket missing" >> /tmp/vintos-emotion-decay.log
    exit 0
fi
cd /home/gloria/.vintos/workspace/emotion_model || exit 1
PYTHONPATH=/home/gloria/.vintos/workspace .venv/bin/python3 <<'PYEOF'
import socket, json, math, sys
from emotion_model import config

INTERVAL_HOURS = 0.25  # runs every 15 min

DIMS = ["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"]
baselines = dict(zip(DIMS, config.BASELINE_EMOTION))
half_lives = dict(zip(DIMS, config.DECAY_HALF_LIVES))

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect("/tmp/Vintos-emotion.sock")
except (ConnectionRefusedError, FileNotFoundError):
    print("Daemon socket not responding — skipping decay")
    sys.exit(0)
s.sendall(json.dumps({"command": "state"}).encode() + b"\n")
data = b""
while True:
    chunk = s.recv(8192)
    if not chunk: break
    data += chunk
    if b"\n" in data: break
s.close()
d = json.loads(data)
v = d["emotion_vector"]

for i, dim in enumerate(DIMS):
    current, baseline, half_life = v[i], baselines[dim], half_lives[dim]
    decay_factor = math.pow(0.5, INTERVAL_HOURS / half_life)
    nudge = (baseline + (current - baseline) * decay_factor) - current
    if abs(nudge) < 0.001:
        continue
    try:
        ns = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ns.settimeout(2)
        ns.connect("/tmp/Vintos-emotion.sock")
        ns.sendall(json.dumps({"command": "nudge", "dimension": dim, "amount": round(nudge, 4)}).encode() + b"\n")
        ns.recv(4096)
        ns.close()
        print(f"{dim}: {current:.3f} -> {current + nudge:.3f}")
    except Exception as e:
        print(f"{dim}: nudge failed {e}")
PYEOF
