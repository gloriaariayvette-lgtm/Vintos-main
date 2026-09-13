#!/usr/bin/env bash
# One reload contract for Aegis Gemma. Thinking is an inference setting and is
# enforced by vintos_claude_shim.py; this door fixes the resident artifact.
set -euo pipefail
LMS="${VINTOS_LMS_CLI:-/mnt/c/Users/glori/.lmstudio/bin/lms.exe}"
BASE="${VINTOS_LM_STUDIO_BASE:-http://172.18.16.1:1234}"
SERVER_BIND="${VINTOS_LM_STUDIO_BIND:-172.18.16.1}"
SERVER_PORT="${VINTOS_LM_STUDIO_PORT:-1234}"
MODEL_KEY="google/gemma-4-12b-qat"
EXPECTED_VARIANT="google/gemma-4-12b-qat@q4_0"
IDENTIFIER="google/gemma-4-12b-qat"

# This CLI reports the precise installed artifact but loads it by its base key.
# Refuse to guess if that key ever stops resolving to the one expected Q4 build.
"$LMS" ls --json | python3 -c '
import json, sys
model_key, expected = sys.argv[1:]
rows = json.load(sys.stdin)
if isinstance(rows, dict): rows = rows.get("models", [])
matches = [row for row in rows if row.get("modelKey") == model_key]
ok = len(matches) == 1 and matches[0].get("selectedVariant") == expected \
     and (matches[0].get("quantization") or {}).get("name") == "Q4_0" \
     and int((matches[0].get("quantization") or {}).get("bits") or 0) == 4
if not ok: raise SystemExit("refusing Gemma load: installed artifact is not the expected Q4_0 variant")
' "$MODEL_KEY" "$EXPECTED_VARIANT"

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
if "$LMS" ps --json | python3 -c '
import json, sys
identifier = sys.argv[1]
rows = json.load(sys.stdin)
raise SystemExit(0 if any(row.get("identifier") == identifier for row in rows) else 1)
' "$IDENTIFIER"; then
  "$LMS" unload "$IDENTIFIER"
fi

exec "$LMS" load "$MODEL_KEY" --identifier "$IDENTIFIER" --gpu max \
  --context-length 32000 --parallel 1 --no-speculative-draft-mtp --yes
