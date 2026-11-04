#!/usr/bin/env bash
# One reload contract for Aegis's local model. Thinking is an inference setting and is
# enforced by vintos_claude_shim.py; this door fixes the resident artifact.
# Since 4 November it is AEON, an abliterated Gemma 4 12B (Gloria: only Gemma 4, abliterated): Q4_K_M,
# 7.4 GB, mradermacher's GGUF of AEON-7/Gemma-4-12B-it-AEON-Abliterated-K4. On Aegis it scored 23/88 on
# the physics lab's tasks against Google's QAT Q4_0's 20/88, at 11.1 GB of VRAM with a 32000 context.
# Every caller asks for the identifier "aeon/gemma-4-12b", so logs say which model really answered.
set -euo pipefail
LMS="${VINTOS_LMS_CLI:-/mnt/c/Users/glori/.lmstudio/bin/lms.exe}"
BASE="${VINTOS_LM_STUDIO_BASE:-http://172.18.16.1:1234}"
SERVER_BIND="${VINTOS_LM_STUDIO_BIND:-172.18.16.1}"
SERVER_PORT="${VINTOS_LM_STUDIO_PORT:-1234}"
MODEL_KEY="gemma-4-12b-it-aeon-abliterated-k4"
EXPECTED_PATH="mradermacher/Gemma-4-12B-it-AEON-Abliterated-K4-BF16-GGUF/Gemma-4-12B-it-AEON-Abliterated-K4-BF16.Q4_K_M.gguf"
IDENTIFIER="aeon/gemma-4-12b"

# This CLI reports the precise installed artifact but loads it by its base key.
# Refuse to guess if that key ever stops resolving to the one expected Gemma 4 Q4_K_M file.
"$LMS" ls --json | python3 -c '
import json, sys
model_key, expected = sys.argv[1:]
rows = json.load(sys.stdin)
if isinstance(rows, dict): rows = rows.get("models", [])
matches = [row for row in rows if row.get("modelKey") == model_key]
ok = len(matches) == 1 and matches[0].get("path") == expected \
     and matches[0].get("architecture") == "gemma4" \
     and (matches[0].get("quantization") or {}).get("name") == "Q4_K_M" \
     and int((matches[0].get("quantization") or {}).get("bits") or 0) == 4
if not ok: raise SystemExit("refusing local model load: installed artifact is not the expected AEON Gemma 4 Q4_K_M file")
' "$MODEL_KEY" "$EXPECTED_PATH"

if ! curl -fsS --max-time 5 "$BASE/api/v1/models" >/dev/null; then
  # LM Studio defaults to Windows loopback, which WSL cannot reach. A listener
  # can therefore be "ON" to Windows and still be absent to the house.
  "$LMS" server stop >/dev/null 2>&1 || true
  "$LMS" server start --bind "$SERVER_BIND" --port "$SERVER_PORT"
  for _attempt in 1 2 3 4 5 6; do
    sleep 2
    curl -fsS --max-time 5 "$BASE/api/v1/models" >/dev/null && break
  done
fi
curl -fsS --max-time 5 "$BASE/api/v1/models" >/dev/null || {
  echo "refusing Gemma load: LM Studio HTTP server is not answering at $BASE" >&2
  exit 1
}

# A reload contract must also work when the expected identifier is already
# resident. Unload only this model; the Nomic embedding model stays untouched.
# The model it replaced (Google's QAT, until 4 November) is unloaded too: LM Studio stacks models rather than
# swapping them, and the two together (about 21 GB) do not fit Aegis's 16 GB card.
for resident in "$IDENTIFIER" "google/gemma-4-12b-qat"; do
  if "$LMS" ps --json | python3 -c '
import json, sys
identifier = sys.argv[1]
rows = json.load(sys.stdin)
raise SystemExit(0 if any(row.get("identifier") == identifier for row in rows) else 1)
' "$resident"; then
    "$LMS" unload "$resident"
  fi
done

exec "$LMS" load "$MODEL_KEY" --identifier "$IDENTIFIER" --gpu max \
  --context-length 32000 --parallel 1 --no-speculative-draft-mtp --yes
