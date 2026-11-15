#!/usr/bin/env bash
# One reload contract for Aegis's house model, the one 12B model on the 16 GB card (Gloria, 14 November 2026).
#
# The house model is the Lab planner worm c1 (the Lab-planner LoRA fused on AEON, Gemma 4 12B ablit, Q4_K_M), loaded
# as "lab-c1": on a check of every caller's task types it lost only on the causality evaluator. So causality runs in a
# window (aegis-model-window.sh) with plain AEON ("aeon/gemma-4-12b") on the card and the Lab paused. Callers keep
# asking for aeon/gemma-4-12b; the house shim maps that to whichever of the two is resident.
#
# Which model: AEGIS_HOUSE_MODEL (environment, else ~/.vintos/vintos.env) = worm | aeon. Unset or anything else is
# aeon: removing the line is the revert to plain AEON everywhere. Inside a live causality window it is aeon.
#
#   aegis-gemma-load.sh            unload every resident LLM, load the house model (AEON if the worm will not load)
#   aegis-gemma-load.sh --which    print the identifier the house model should have now, change nothing
#   aegis-gemma-load.sh --unload   unload every resident LLM (Evo 2, ESMFold); the caller reloads after
#
# Thinking is an inference setting, enforced by vintos_claude_shim.py; this door fixes the resident artifact.
set -euo pipefail
LMS="${VINTOS_LMS_CLI:-/mnt/c/Users/glori/.lmstudio/bin/lms.exe}"
BASE="${VINTOS_LM_STUDIO_BASE:-http://172.18.16.1:1234}"
SERVER_BIND="${VINTOS_LM_STUDIO_BIND:-172.18.16.1}"
SERVER_PORT="${VINTOS_LM_STUDIO_PORT:-1234}"
ENV_FILE="${VINTOS_ENV_FILE:-$HOME/.vintos/vintos.env}"
WINDOW_STATE="${AEGIS_WINDOW_STATE:-$HOME/.vintos/workspace/memory/aegis-model-window.json}"
LOG="${AEGIS_MODEL_LOG:-$HOME/.vintos/logs/aegis-model.log}"

AEON_KEY="gemma-4-12b-it-aeon-abliterated-k4"
AEON_PATH="mradermacher/Gemma-4-12B-it-AEON-Abliterated-K4-BF16-GGUF/Gemma-4-12B-it-AEON-Abliterated-K4-BF16.Q4_K_M.gguf"
AEON_ID="aeon/gemma-4-12b"
WORM_KEY="lab-c1-gemma-4-12b-aeon"
WORM_PATH="vintos/lab-c1-gemma-4-12b-aeon-GGUF/lab-c1-gemma-4-12b-aeon.Q4_K_M.gguf"
WORM_BYTES=7381381760     # sha256 8031c2ac...ed5be0, the Studio's exports/c1/q4km.gguf the worm's gate sealed
WORM_ID="lab-c1"

note() { mkdir -p "$(dirname "$LOG")" 2>/dev/null || true; echo "[$(date '+%F %T')] $*" >> "$LOG" 2>/dev/null || true; }

window_open() {   # a causality window whose owner is alive and whose time is not up
  [ -f "$WINDOW_STATE" ] || return 1
  python3 - "$WINDOW_STATE" <<'PY'
import json, os, sys, time
try:
    s = json.load(open(sys.argv[1]))
    os.kill(int(s["pid"]), 0)
    raise SystemExit(0 if float(s["until"]) > time.time() else 1)
except Exception:
    raise SystemExit(1)
PY
}

wanted() {
  local choice="${AEGIS_HOUSE_MODEL:-}"
  if [ -z "$choice" ] && [ -f "$ENV_FILE" ]; then
    choice="$(grep -E '^AEGIS_HOUSE_MODEL=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r' || true)"
  fi
  if [ "$choice" = "worm" ] && ! window_open; then echo "$WORM_ID"; else echo "$AEON_ID"; fi
}

if [ "${1:-}" = "--which" ]; then wanted; exit 0; fi

installed_ok() {   # key path bytes(optional): exactly one installed Gemma 4 Q4_K_M artifact with that key and path
  "$LMS" ls --json </dev/null | python3 -c '
import json, sys
key, path, size = sys.argv[1], sys.argv[2], int(sys.argv[3] or 0)
rows = json.load(sys.stdin)
if isinstance(rows, dict): rows = rows.get("models", [])
m = [r for r in rows if r.get("modelKey") == key]
ok = len(m) == 1 and m[0].get("path") == path and m[0].get("architecture") == "gemma4" \
     and (m[0].get("quantization") or {}).get("name") == "Q4_K_M" \
     and int((m[0].get("quantization") or {}).get("bits") or 0) == 4 \
     and (not size or int(m[0].get("sizeBytes") or 0) == size)
raise SystemExit(0 if ok else 1)
' "$1" "$2" "${3:-0}"
}

resident() {   # identifiers of every resident model that is not an embedding model (an odd row counts as resident)
  "$LMS" ps --json </dev/null | python3 -c '
import json, sys
print("\n".join(str(r.get("identifier") or r.get("modelKey") or "?") for r in json.load(sys.stdin)
                if r.get("type") != "embedding"))'
}

unload_all() {
  local id
  for id in $(resident); do "$LMS" unload "$id" </dev/null; done
  if [ -n "$(resident)" ]; then
    echo "refusing: still resident after unload: $(resident | tr '\n' ' ')" >&2; return 1
  fi
}

if ! curl -fsS --max-time 5 "$BASE/api/v1/models" >/dev/null; then
  # LM Studio defaults to Windows loopback, which WSL cannot reach. A listener
  # can therefore be "ON" to Windows and still be absent to the house.
  "$LMS" server stop >/dev/null 2>&1 </dev/null || true
  "$LMS" server start --bind "$SERVER_BIND" --port "$SERVER_PORT" </dev/null
  for _attempt in 1 2 3 4 5 6; do
    sleep 2
    curl -fsS --max-time 5 "$BASE/api/v1/models" >/dev/null && break
  done
fi
curl -fsS --max-time 5 "$BASE/api/v1/models" >/dev/null || {
  echo "refusing model change: LM Studio HTTP server is not answering at $BASE" >&2; exit 1; }

if [ "${1:-}" = "--unload" ]; then
  unload_all; note "unloaded every LLM (${AEGIS_CALLER:-caller unnamed})"; exit 0
fi

target="$(wanted)"
if [ "$target" = "$WORM_ID" ] && ! installed_ok "$WORM_KEY" "$WORM_PATH" "$WORM_BYTES"; then
  note "worm artifact not as expected; loading AEON instead"
  echo "the worm's installed artifact is not the expected c1 file; loading AEON" >&2
  target="$AEON_ID"
fi
if [ "$target" = "$AEON_ID" ]; then
  installed_ok "$AEON_KEY" "$AEON_PATH" || {
    echo "refusing local model load: installed artifact is not the expected AEON Gemma 4 Q4_K_M file" >&2; exit 1; }
  key="$AEON_KEY"
else
  key="$WORM_KEY"
fi

# LM Studio stacks models rather than swapping them, and two 12B models do not fit the 16 GB card: every resident LLM
# goes first (AEON, the worm, Google's old QAT), the Nomic embedding model stays.
unload_all
"$LMS" load "$key" --identifier "$target" --gpu max \
  --context-length 32000 --parallel 1 --no-speculative-draft-mtp --yes </dev/null
# A load whose client was cut off (a timeout, a killed caller) can still land after the unloads above: the house
# model is the one LLM this contract leaves resident.
for extra in $(resident); do
  [ "$extra" = "$target" ] || "$LMS" unload "$extra" </dev/null
done
note "loaded $target (${AEGIS_CALLER:-caller unnamed})"
