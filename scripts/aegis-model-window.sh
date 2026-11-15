#!/usr/bin/env bash
# The causality window (Gloria, 14 November 2026): "Just pause the lab while causality runs and reload the worm after."
#
#   aegis-model-window.sh COMMAND [ARGS...]
#
# When the house model is the worm (AEGIS_HOUSE_MODEL=worm), COMMAND runs with plain AEON on Aegis's card:
#   1. pause the Lab: take the window lock exclusively. Every Lab model call (chemistry_lab._ask, the planner trial,
#      Evo 2, ESMFold) holds it shared, so the in-flight call finishes first and the next one waits here, not falls back;
#   2. mark the window (aegis-model-window.json: this pid, a deadline) and load AEON under the Gemma watchdog lock;
#   3. run COMMAND, killed after AEGIS_WINDOW_TIMEOUT seconds (default 4500: causality "lasts up to an hour");
#   4. always, whatever happened (EXIT/INT/TERM/HUP trap): unmark the window, load the house model again (the worm),
#      retrying once, then resume the Lab by letting the lock go.
# Each transition is a line in ~/.vintos/logs/aegis-model-window.log. When the house model is already AEON, COMMAND
# runs as it is. A window killed outright (SIGKILL) leaves a mark whose owner is dead: the loader ignores it and the
# five-minute watchdog puts the worm back.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOADER="${AEGIS_MODEL_LOADER:-$HERE/aegis-gemma-load.sh}"
MEM="${AEGIS_WINDOW_MEM:-$HOME/.vintos/workspace/memory}"
LOG="${AEGIS_WINDOW_LOG:-$HOME/.vintos/logs/aegis-model-window.log}"
HOLD="$MEM/.aegis-model-window.lock"
WATCHDOG_LOCK="$MEM/.gemma-watchdog.lock"
STATE="${AEGIS_WINDOW_STATE:-$MEM/aegis-model-window.json}"
TIMEOUT="${AEGIS_WINDOW_TIMEOUT:-4500}"
PAUSE_WAIT="${AEGIS_WINDOW_PAUSE_WAIT:-2400}"   # above a Lab instrument's longest hold (Evo 2: about 1630 s)
AEON_ID="aeon/gemma-4-12b"

log() { mkdir -p "$(dirname "$LOG")" 2>/dev/null || true; echo "[$(date '+%F %T')] window $$: $*" >> "$LOG"; }

[ "$#" -ge 1 ] || { echo "usage: aegis-model-window.sh COMMAND [ARGS...]" >&2; exit 2; }
if [ "${AEGIS_MODEL_WINDOW:-}" = "held" ]; then exec "$@"; fi      # already inside a window
export AEGIS_MODEL_WINDOW=held

if [ "$(bash "$LOADER" --setting 2>/dev/null || echo aeon)" != "worm" ]; then
  log "house model is AEON (AEGIS_HOUSE_MODEL is not worm); running without a window: $*"
  exec "$@"
fi

swap() {   # why [model]: under the watchdog lock, so the watchdog and Evo 2 never change LM Studio at the same moment
  local why="$1" force="${2:-}" attempt
  for attempt in 1 2; do
    if ( flock -w 300 9 || exit 1
         if [ -n "$force" ]; then export AEGIS_HOUSE_MODEL="$force"; fi
         AEGIS_CALLER="causality window: $why" bash "$LOADER" ) 9>"$WATCHDOG_LOCK" \
         >>"$LOG" 2>&1; then
      return 0
    fi
    log "$why: load attempt $attempt failed"
    sleep 10
  done
  return 1
}

closed=0
swapped=0
close_window() {
  trap '' INT TERM HUP                 # a second signal must not cut the swap back short
  [ "$closed" = 1 ] && return
  closed=1
  rm -f "$STATE"
  if [ "$swapped" = 1 ]; then
    if swap "back to the house model"; then log "house model back: $(bash "$LOADER" --which 2>/dev/null)"
    else log "SWAP-BACK FAILED; the five-minute watchdog will load the house model"; fi
  fi
  exec 8>&- 2>/dev/null || true
  log "Lab resumed; window closed"
}
trap 'close_window' EXIT
trap 'log "signal received"; exit 143' INT TERM HUP

mkdir -p "$MEM"
exec 8>"$HOLD"
if flock -w "$PAUSE_WAIT" 8; then log "Lab paused (its model calls wait)"
else log "Lab did not reach a pause within ${PAUSE_WAIT}s; not running (no swap): $*"; exit 75; fi

python3 - "$STATE" "$$" "$TIMEOUT" <<'PY' || { log "could not mark the window; not running: $*"; exit 1; }
import json, os, sys, time
path, pid, timeout = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
tmp = path + ".tmp"
json.dump({"pid": pid, "until": time.time() + timeout + 300, "model": "aeon/gemma-4-12b",
           "opened": time.strftime("%Y-%m-%dT%H:%M:%S")}, open(tmp, "w"))
os.replace(tmp, path)
PY
log "window open for: $*"
swapped=1
if ! swap "AEON for the window" aeon; then
  log "AEON did not load; not running: $*"
  exit 1
fi
log "AEON loaded; running (timeout ${TIMEOUT}s)"
timeout --kill-after=30 "$TIMEOUT" "$@" &
child=$!
# a signal ends the command now (bash runs a trap only between commands, so the command runs in the background)
trap 'log "signal received; stopping the command"; kill -TERM "$child" 2>/dev/null; wait "$child"; exit 143' INT TERM HUP
wait "$child"
rc=$?
log "command ended rc=$rc"
exit "$rc"
