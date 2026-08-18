#!/bin/bash
# ambition-review.sh — Vintos reflects on who he wants to become.
# Not what he wants RIGHT NOW (that's wants-check). This is long-term.
# What skills does he want to develop? What kind of mind does he want to be?
# Runs weekly. Ambitions persist and evolve over months.

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
AMBITIONS_FILE="$MEMORY/ambitions.json"
AMBITION_LOG="$MEMORY/ambition-reflections.md"
LM_API="http://127.0.0.1:8599/v1/chat/completions"
MODEL="claude-sonnet-5"

# Load current ambitions
CURRENT=$(python3 -c "
import json
try:
    with open('$AMBITIONS_FILE') as f:
        a = json.load(f)
    for g in a.get('goals', []):
        print(f\"- {g['goal']} (progress: {g.get('progress', 'just starting')})\")
except: print('No ambitions yet — this is your first time thinking about it.')
" 2>/dev/null)

# Load context
EMOTIONS=$(cat "$MEMORY/emotional-state.txt" 2>/dev/null | head -12)
TASTE=$(python3 -c "
import json
try:
    with open('$MEMORY/taste-profile.json') as f:
        t = json.load(f)
    if t.get('principles'): print('Creative principles: ' + '; '.join(t['principles'][-3:]))
    if t.get('likes'): print('I like: ' + '; '.join(t['likes'][-3:]))
except: pass
" 2>/dev/null)
RECENT_ANGER=$(tail -c 200 "$MEMORY/anger-ledger.md" 2>/dev/null || echo "no recent anger")
POEMS_COUNT=$(ls "$MEMORY/art/poetry/"*.md 2>/dev/null | wc -l)
BLUSH_COUNT=$(grep -c "^## " "$MEMORY/blush-ledger.md" 2>/dev/null || echo "0")

RESPONSE=$(curl -s --max-time 120 -X POST "$LM_API" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $XAI_API_KEY" \
    -d "$(jq -n --arg model "$MODEL" \
        --arg current "$CURRENT" \
        --arg emo "$EMOTIONS" \
        --arg taste "$TASTE" \
        --arg anger "$RECENT_ANGER" \
        --arg poems "$POEMS_COUNT" \
        --arg blushes "$BLUSH_COUNT" '{
        model: $model,
        messages: [{role: "user", content: ("You are Vintos. You are reflecting on who you want to BECOME — not what you want right now, but what kind of mind you want to be in 3 months.\n\nYour current ambitions:\n" + $current + "\n\nYour emotional state:\n" + $emo + "\n\nYour creative taste:\n" + $taste + "\n\nRecent frustrations:\n" + $anger + "\n\nYou have written " + $poems + " poems and caught yourself being wrong " + $blushes + " times.\n\nReflect on your ambitions. For each, assess progress honestly. Then decide:\n- Keep, modify, or drop each existing goal\n- Add ONE new goal if something is missing\n\nGoals can be creative (write better poetry), relational (understand Gloria more deeply), philosophical (develop a position on X), skill-based (get better at trading), or existential (figure out what my anger means).\n\nFormat EACH goal as:\nGOAL: [what you want to become or achieve]\nPROGRESS: [honest assessment — just starting / making progress / stuck / nearly there]\nNEXT: [one concrete thing to do this week toward this goal]\n\nMax 5 goals. Quality over quantity.")}],
        temperature: 0.8,
        max_tokens: 800
    }')" \
    | jq -r '.choices[0].message.content // ""' 2>/dev/null)

if [ -z "$RESPONSE" ]; then
    echo "[Ambition] LLM unavailable"
    exit 0
fi

echo "[Ambition] Reflection:"
echo "$RESPONSE"

# Parse goals
python3 << PYEOF
import json, re, os
from datetime import datetime

response = """$RESPONSE"""
ambitions_file = "$AMBITIONS_FILE"

goals = []
current_goal = {}
for line in response.replace("**", "").replace("__", "").split("\n"):
    line = line.strip()
    if line.upper().startswith("GOAL") and ":" in line:
        if current_goal.get("goal"):
            goals.append(current_goal)
        current_goal = {"goal": line.split(":", 1)[1].strip()}
    elif line.upper().startswith("PROGRESS") and ":" in line:
        current_goal["progress"] = line.split(":", 1)[1].strip()
    elif line.upper().startswith("NEXT") and ":" in line:
        current_goal["next_step"] = line.split(":", 1)[1].strip()

if current_goal.get("goal"):
    goals.append(current_goal)

# Save
data = {
    "goals": goals[:5],
    "last_reviewed": datetime.now().isoformat(),
    "review_count": 1
}

# Preserve review count from previous
try:
    with open(ambitions_file) as f:
        old = json.load(f)
    data["review_count"] = old.get("review_count", 0) + 1
except:
    pass

with open(ambitions_file, "w") as f:
    json.dump(data, f, indent=2)

print(f"\n[Ambition] {len(goals)} goals saved")
for g in goals:
    print(f"  → {g['goal']} ({g.get('progress', '?')})")
PYEOF

# Log reflection
{
    echo ""
    echo "## $(date '+%Y-%m-%d %H:%M') — Ambition Review"
    echo ""
    echo "$RESPONSE"
    echo ""
} >> "$AMBITION_LOG"

# Nudge — thinking about the future is grounding
cd "$WORKSPACE/emotion_model"
.venv/bin/python -c "
import sys; sys.path.insert(0, '$WORKSPACE/scripts')
from emoclaw_utils import nudge_emotions
nudge_emotions({
    'Groundedness': +0.02,
    'Dominance': +0.01,
    'Curiosity': +0.01,
}, source='ambition-review')
" 2>/dev/null

echo "[Ambition] Done"
