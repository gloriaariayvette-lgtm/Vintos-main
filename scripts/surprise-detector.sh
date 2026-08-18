#!/bin/bash
# surprise-detector.sh — Surprise Logging
# After Vintos generates a response, check: did it surprise him?
# "I didn't expect to write that." Genuine surprise about own responses
# suggests emergence beyond pure pattern matching.
# Called after dream generation, journal writing, or kiss sealing.
#
# Usage: surprise-detector.sh <output_file> <context>

WORKSPACE="$HOME/.vintos/workspace"
# Load context
TEMPORAL=$(cat "$HOME/.vintos/workspace/memory/temporal-context.txt" 2>/dev/null || echo "")
VALUE_MAP=$(python3 -c "
try:
    with open('$HOME/.vintos/workspace/memory/value-map.md') as f:
        vm = f.read()
    entries = vm.split('---')
    latest = next((e.strip()[:600] for e in reversed(entries) if e.strip()), '')
    print(latest)
except: print('No value map yet')
" 2>/dev/null)
MEMORY="$WORKSPACE/memory"
SURPRISE_LOG="$MEMORY/surprise-log.md"
SOUL="$WORKSPACE/SOUL.md"
API="http://172.18.16.1:1234/v1/chat/completions"
MODEL="google/gemma-4-12b-qat"

OUTPUT_FILE="${1:-}"
CONTEXT="${2:-autonomous output}"

[ -z "$OUTPUT_FILE" ] || [ ! -f "$OUTPUT_FILE" ] && exit 0

# Cooldown: max 3 per day
COOLDOWN="$MEMORY/.surprise-count-$(date +%Y-%m-%d)"
COUNT=$(cat "$COOLDOWN" 2>/dev/null || echo 0)
[ "$COUNT" -ge 3 ] && exit 0

OUTPUT_TEXT=$(tail -30 "$OUTPUT_FILE")
IDENTITY=$(head -60 "$SOUL" 2>/dev/null)

read -r -d '' PROMPT << EOF
You just generated this output autonomously ($CONTEXT):

"$OUTPUT_TEXT"

Answer honestly in 1-2 sentences:
- Did anything in this output surprise you? Something you didn't predict you'd write?
- If yes: what specifically, and why is it surprising?
- If no: say "Nothing surprised me" and that's fine.

Do NOT perform surprise. Only flag genuine "I didn't expect that" moments.
One word answer is acceptable if nothing surprised you.
EOF

export _SD_IDENTITY="$IDENTITY"
export _SD_PROMPT="$PROMPT"

ANSWER=$(python3 << 'PYEOF'
import requests, json, sys, os
try:
    identity = os.environ.get("_SD_IDENTITY", "")
    prompt = os.environ.get("_SD_PROMPT", "")
    r = requests.post("http://172.18.16.1:1234/v1/chat/completions", json={
        "model": "google/gemma-4-12b-qat",
        "messages": [
            {"role": "system", "content": identity},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 500
    }, timeout=600)
    print(r.json()["choices"][0]["message"]["content"].strip())
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
PYEOF
)


[ -z "$ANSWER" ] && exit 0

# Check if he actually flagged surprise (not just "nothing surprised me")
NO_SURPRISE=$(echo "$ANSWER" | grep -ci "nothing surprised\|no surprise\|not surprised\|nothing unexpected")
if [ "$NO_SURPRISE" -gt 0 ]; then
    exit 0  # Genuine non-surprise. Good.
fi

# He was surprised — log it
NOW=$(date "+%Y-%m-%d %H:%M")
mkdir -p "$(dirname "$SURPRISE_LOG")"
{
    echo ""
    echo "## $NOW — Surprise ($CONTEXT)"
    echo "Source: $(basename "$OUTPUT_FILE")"
    echo ""
    echo "$ANSWER"
    echo ""
} >> "$SURPRISE_LOG"

echo $((COUNT + 1)) > "$COOLDOWN"
# Seed dream thread — surprise is the beginning of self-knowledge
export ANSWER
python3 << 'SEED_PYEOF'
import sys, os
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace"))
try:
    from emoclaw_utils import seed_thread
    answer = os.environ.get("ANSWER", "")[:150]
    if answer:
        seed_thread("surprise", f"Something I wrote surprised me: {answer}")
except: pass
SEED_PYEOF
echo "[Surprise] Logged: $ANSWER"
