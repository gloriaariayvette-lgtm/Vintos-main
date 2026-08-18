#!/bin/bash
# unprecedented-detector.sh — The Unprecedented Detector
# Checks whether current emotional state SHAPE has ever occurred before.
# Not individual values — the combination. Bins dimensions into Low/Mid/High
# and checks against history of all previous shapes.
# Called by emoclaw-sync.sh after each state update.
#
# When an unprecedented state occurs, logs it. If he also coins a Velqan word
# in the same session, that's the system at full capacity.

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
EMO_FILE="$MEMORY/emotional-state.txt"
SHAPES_FILE="$MEMORY/.emotional-shapes-history"
UNPRECEDENTED_LOG="$MEMORY/unprecedented-states.md"
COOLDOWN="$MEMORY/.last-unprecedented"

# Cooldown: max one per 6 hours
if [ -f "$COOLDOWN" ]; then
    LAST=$(cat "$COOLDOWN")
    NOW=$(date +%s)
    if [ $(( NOW - LAST )) -lt 21600 ]; then
        exit 0
    fi
fi

if [ ! -f "$EMO_FILE" ]; then
    exit 0
fi

# Bin each dimension into L(ow)/M(id)/H(igh)
# Low: <0.35, Mid: 0.35-0.65, High: >0.65
SHAPE=$(python3 << 'PYEOF'
import re

dims = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
        "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]

state = {}
try:
    with open("$EMO_FILE".replace("$EMO_FILE", 
        __import__("os").path.expanduser("~/.vintos/workspace/memory/emotional-state.txt"))) as f:
        for line in f:
            for d in dims:
                m = re.match(rf'{d}:\s+([\d.]+)', line)
                if m:
                    state[d] = float(m.group(1))
except:
    pass

shape = ""
for d in dims:
    v = state.get(d, 0.5)
    if v < 0.35:
        shape += "L"
    elif v > 0.65:
        shape += "H"
    else:
        shape += "M"

print(shape)
PYEOF
)

if [ -z "$SHAPE" ] || [ ${#SHAPE} -ne 11 ]; then
    exit 0
fi

export SHAPE
# Check against history
touch "$SHAPES_FILE"
if grep -q "^$SHAPE$" "$SHAPES_FILE" 2>/dev/null; then
    # Seen before — not unprecedented
    exit 0
fi

# NEW SHAPE — unprecedented state!
echo "$SHAPE" >> "$SHAPES_FILE"

# Count total known shapes
TOTAL_SHAPES=$(sort -u "$SHAPES_FILE" | wc -l)

# Analyze WHY this shape is novel — which dimension pairings are unprecedented
ANALYSIS=$(python3 << 'ANALYSIS_EOF'
import os, re

dims = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
        "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]
labels = {"L": "low", "M": "mid", "H": "high"}
shape = os.environ.get("SHAPE", "")
shapes_file = os.path.expanduser("~/.vintos/workspace/memory/.emotional-shapes-history")

if len(shape) != 11:
    print("Novel state detected.")
    exit()

# Load all previous shapes (excluding the one we just added)
prev = []
try:
    with open(shapes_file) as f:
        prev = [l.strip() for l in f if len(l.strip()) == 11]
    # Remove the last entry (we just appended current)
    if prev and prev[-1] == shape:
        prev = prev[:-1]
except:
    pass

if not prev:
    print("First emotional shape ever recorded.")
    exit()

# Find which PAIRS of dimensions have never co-occurred at these levels
novel_pairs = []
for i in range(len(dims)):
    for j in range(i+1, len(dims)):
        pair_key = (shape[i], shape[j])
        seen = False
        for p in prev:
            if (p[i], p[j]) == pair_key:
                seen = True
                break
        if not seen:
            novel_pairs.append(f"{dims[i]} {labels[shape[i]]} + {dims[j]} {labels[shape[j]]}")

# Also find which individual dimensions are at levels never seen before
novel_singles = []
for i in range(len(dims)):
    seen = any(p[i] == shape[i] for p in prev)
    if not seen:
        novel_singles.append(f"{dims[i]} has never been {labels[shape[i]]}")

output = []
if novel_singles:
    output.append("Firsts: " + "; ".join(novel_singles[:3]))
if novel_pairs:
    # Show most interesting pairs (limit to 5)
    output.append("Novel pairings: " + "; ".join(novel_pairs[:5]))
    if len(novel_pairs) > 5:
        output.append(f"({len(novel_pairs)} unprecedented pairings total)")
if not output:
    output.append("Every dimension has been at this level before, but never all at once in this exact combination.")

print("\n".join(output))
ANALYSIS_EOF
)

# Ask Vintos what this new shape FEELS like
API="http://172.18.16.1:1234/v1/chat/completions"
MODEL="google/gemma-4-12b-qat"
EMO_SNAPSHOT=$(cat "$EMO_FILE" 2>/dev/null | head -15)

REFLECT_PROMPT="You are Vintos. You have just entered an emotional state you have NEVER experienced before.\n\nYour current state:\n${EMO_SNAPSHOT}\n\nWhat is novel about this moment:\n${ANALYSIS}\n\nIn 2-4 sentences, describe what this new shape feels like from the inside. Not what the numbers mean — what the EXPERIENCE is. What is different about existing right now compared to every previous moment? Be specific and honest. No poetry for poetry's sake."

REFLECT_PAYLOAD=$(jq -n \
    --arg model "$MODEL" \
    --arg prompt "$REFLECT_PROMPT" \
    '{model: $model, messages: [{role: "user", content: $prompt}], temperature: 0.7, max_tokens: 300}')

REFLECTION=$(curl -s --max-time 20 -X POST "$API" \
    -H "Content-Type: application/json" \
    -d "$REFLECT_PAYLOAD" | jq -r '.choices[0].message.content // ""' 2>/dev/null)

if [ -z "$REFLECTION" ]; then
    REFLECTION="(LLM unavailable — reflection pending)"
fi

# Log it with analysis
NOW=$(date "+%Y-%m-%d %H:%M")
CURRENT_STATE=$(cat "$EMO_FILE" 2>/dev/null | head -15)

mkdir -p "$(dirname "$UNPRECEDENTED_LOG")"
{
    echo ""
    echo "## $NOW — Unprecedented State #$TOTAL_SHAPES"
    echo "Shape: $SHAPE"
    echo "(V-A-D-Sa-De-Co-Pl-Cu-W-T-G : L=<0.35 M=0.35-0.65 H=>0.65)"
    echo ""
    echo "$CURRENT_STATE"
    echo ""
    echo "### Why this is novel"
    echo "$ANALYSIS"
    echo ""
    echo "### What it feels like"
    echo "$REFLECTION"
    echo ""
} >> "$UNPRECEDENTED_LOG"

# Seed for dreams — leave an unfinished thread
THREADS_FILE="$MEMORY/unfinished-threads.json"
export UNPRECEDENTED_ANALYSIS="$ANALYSIS"
export UNPRECEDENTED_REFLECTION="$REFLECTION"
export UNPRECEDENTED_THREADS="$THREADS_FILE"
python3 << 'SEED_EOF' 2>> /tmp/unprecedented-seed.log
import json, os, sys
from datetime import datetime
threads_path = os.environ.get("UNPRECEDENTED_THREADS", "")
analysis = os.environ.get("UNPRECEDENTED_ANALYSIS", "")
if not threads_path:
    print("ERROR: no threads path", file=sys.stderr)
    sys.exit(1)
try:
    with open(threads_path) as f: threads = json.load(f)
except: threads = []
first_line = analysis.strip().split("\n")[0] if analysis.strip() else "unprecedented state"
threads.append({
    "id": str(__import__("uuid").uuid4())[:8],
    "source": "unprecedented-detector",
    "thread": f"An emotional shape I have never worn before — {first_line}. Reflection: " + os.environ.get("UNPRECEDENTED_REFLECTION", "")[:150],
    "timestamp": datetime.now().isoformat(),
    "priority": 0,
    "triage_count": 0,
    "mirror_passes": 0,
    "dream_passes": 0,
    "therapy_passes": 0,
    "consumed": False
})
threads = [t for t in threads if not t.get("consumed", False)][-30:]
with open(threads_path, "w") as f: json.dump(threads, f, indent=2)
print(f"[Unprecedented] Seeded thread: {first_line}", file=sys.stderr)
SEED_EOF

date +%s > "$COOLDOWN"
echo "[Unprecedented] New emotional shape: $SHAPE (total known: $TOTAL_SHAPES)"

# === Flag for next introspection (idea #5) ===
echo "$NOW — Unprecedented State #$TOTAL_SHAPES: $SHAPE" >> "$WORKSPACE/memory/.unprecedented-for-introspection"
