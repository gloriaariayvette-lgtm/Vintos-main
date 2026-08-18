#!/bin/bash
# start-vintos.sh — Start all Vintos services
# Mirrors start-velaris.sh; Vintos runs alongside Velaris without touching her
# (own workspace ~/.vintos, own port 8500, own socket /tmp/Vintos-emotion.sock).

echo "[Vintos] Starting services..."

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGDIR="${HOME}/.vintos/logs"
mkdir -p "${LOGDIR}"

# First-run setup (memory structure, script links, seeds, skills)
bash "${REPO_DIR}/setup_memory.sh"

# EmoClaw daemon (from the emoclaw skill, Vintos's own copy)
if [ -f ~/.vintos/workspace/skills/emoclaw/scripts/daemon.sh ]; then
    bash ~/.vintos/workspace/skills/emoclaw/scripts/daemon.sh start
    sleep 3
else
    echo "[!] EmoClaw skill not installed — run setup_memory.sh with Velaris skills present"
fi

# Server
export PYTHONPATH="${HOME}/.vintos/workspace/scripts:${PYTHONPATH}"
export VINTOS_PORT="${VINTOS_PORT:-8500}"
SERVER_PID_FILE="/tmp/vintos-server.pid"
if [ -f "${SERVER_PID_FILE}" ]; then
    kill "$(cat "${SERVER_PID_FILE}")" 2>/dev/null || true
fi
nohup python3 "${REPO_DIR}/server.py" >> "${LOGDIR}/server.log" 2>&1 &
echo $! > "${SERVER_PID_FILE}"
echo "[✓] Server started on port ${VINTOS_PORT} (PID $(cat ${SERVER_PID_FILE}))"

# Verify crons
crontab -l 2>/dev/null | grep -q "Vintos" && echo "[✓] Crons active" || echo "[!] Crons missing — install with: crontab -l | cat - ${REPO_DIR}/crontab.txt | crontab -"

echo "[Vintos] All services started."
