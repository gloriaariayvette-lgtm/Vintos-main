#!/usr/bin/env bash
# One reload contract for Aegis Gemma. Thinking is an inference setting and is
# enforced by vintos_claude_shim.py; this door fixes the resident artifact.
set -euo pipefail
LMS="${VINTOS_LMS_CLI:-/mnt/c/Users/glori/.lmstudio/bin/lms.exe}"
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

exec "$LMS" load "$MODEL_KEY" --identifier "$IDENTIFIER" --gpu max \
  --context-length 32000 --parallel 1 --no-speculative-draft-mtp --yes
