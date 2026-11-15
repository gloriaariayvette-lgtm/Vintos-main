#!/usr/bin/env bash
# The Lab planner worm (c1: the Lab-planner LoRA fused on AEON, Q4_K_M, 7.4 GB) in AEON's place on Aegis's 16 GB card.
# Exit 3: refused before LM Studio was changed (AEON still resident). Any other failure: the caller reloads AEON.
# Called by lab_planner_trial (LAB_PLANNER_TRIAL_LOAD=swap) while it holds the Gemma watchdog lock; the caller puts
# AEON back with aegis-gemma-load.sh, which also takes lab-c1 off. Two 12B models never share the card: every LLM is
# unloaded first, and the load is refused if any is still resident.
set -euo pipefail
LMS="${VINTOS_LMS_CLI:-/mnt/c/Users/glori/.lmstudio/bin/lms.exe}"
BASE="${VINTOS_LM_STUDIO_BASE:-http://172.18.16.1:1234}"
MODEL_KEY="lab-c1-gemma-4-12b-aeon"
EXPECTED_PATH="vintos/lab-c1-gemma-4-12b-aeon-GGUF/lab-c1-gemma-4-12b-aeon.Q4_K_M.gguf"
EXPECTED_BYTES=7381381760     # sha256 8031c2ac...ed5be0, the Studio's exports/c1/q4km.gguf the worm's gate sealed
IDENTIFIER="lab-c1"
CONTEXT="${LAB_C1_CONTEXT:-20480}"   # the context its gate evaluated it at

"$LMS" ls --json </dev/null | python3 -c '
import json, sys
model_key, expected, size = sys.argv[1], sys.argv[2], int(sys.argv[3])
rows = json.load(sys.stdin)
if isinstance(rows, dict): rows = rows.get("models", [])
matches = [row for row in rows if row.get("modelKey") == model_key]
ok = len(matches) == 1 and matches[0].get("path") == expected and matches[0].get("architecture") == "gemma4" \
     and (matches[0].get("quantization") or {}).get("name") == "Q4_K_M" and int(matches[0].get("sizeBytes") or 0) == size
if not ok:
    print("refusing lab-c1 load: installed artifact is not the expected c1 Gemma 4 Q4_K_M file", file=sys.stderr)
    raise SystemExit(3)
' "$MODEL_KEY" "$EXPECTED_PATH" "$EXPECTED_BYTES"

curl -fsS --max-time 5 "$BASE/api/v1/models" >/dev/null || {
  echo "refusing lab-c1 load: LM Studio HTTP server is not answering at $BASE" >&2; exit 3; }

llms() {   # identifiers of every resident model that is not an embedding model (fails closed on an odd row)
  "$LMS" ps --json </dev/null | python3 -c '
import json, sys
rows = json.load(sys.stdin)
print("\n".join(str(r.get("identifier") or r.get("modelKey") or "?") for r in rows if r.get("type") != "embedding"))'
}
for resident in $(llms); do
  "$LMS" unload "$resident" </dev/null
done
left="$(llms)"
if [ -n "$left" ]; then
  echo "refusing lab-c1 load: still resident: $left" >&2; exit 1
fi
exec "$LMS" load "$MODEL_KEY" --identifier "$IDENTIFIER" --gpu max \
  --context-length "$CONTEXT" --parallel 1 --no-speculative-draft-mtp --yes </dev/null
