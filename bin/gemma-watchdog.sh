#!/bin/bash
# gemma-watchdog.sh — reload a genuinely-down Gemma without ever stacking instances.
LMS="/mnt/c/Users/glori/.lmstudio/bin/lms.exe"
LOG="/home/gloria/.vintos/logs/gemma-watchdog.log"
MODEL="google/gemma-4-12b-qat"
LOCK="/tmp/gemma-watchdog.lock"
BASE="http://172.18.16.1:1234"
PING='{"model":"'"$MODEL"'","messages":[{"role":"user","content":"ok"}],"max_tokens":3}'

exec 9>"$LOCK"
flock -n 9 || { echo "[$(date '+%F %T')] another watchdog holds the lock — skip" >> "$LOG"; exit 0; }

MODELS=$(curl -s --max-time 10 "$BASE/v1/models" 2>/dev/null)
if echo "$MODELS" | grep -q "$MODEL"; then
  for attempt in 1 2; do
    RESP=$(curl -s --max-time 90 -X POST "$BASE/v1/chat/completions" -H "Content-Type: application/json" -d "$PING" 2>/dev/null)
    echo "$RESP" | grep -q '"choices"' && exit 0
    sleep 5
  done
  echo "[$(date '+%F %T')] Gemma loaded but unresponsive after 2 pings — reloading" >> "$LOG"
else
  echo "[$(date '+%F %T')] Gemma not loaded — loading one instance" >> "$LOG"
fi

"$LMS" unload --all >> "$LOG" 2>&1
sleep 3
"$LMS" load "$MODEL" --gpu max -c 32000 --parallel 1 >> "$LOG" 2>&1
sleep 3
RESP2=$(curl -s --max-time 90 -X POST "$BASE/v1/chat/completions" -H "Content-Type: application/json" -d "$PING" 2>/dev/null)
if echo "$RESP2" | grep -q '"choices"'; then
  echo "[$(date '+%F %T')] Gemma recovered (single instance)" >> "$LOG"
else
  echo "[$(date '+%F %T')] reload FAILED — needs manual attention" >> "$LOG"
  curl -s --max-time 10 -H "Title: Vintos" -H "Tags: warning" -d "Gemma hung and auto-reload failed — manual LM Studio restart." ntfy.sh/vintos-gloria-9kx > /dev/null 2>&1
fi
