#!/bin/bash
# midday-ground.sh — Emotional grounding through reflection
# Triggered by elevated emotions. He names what's running hot,
# traces it to its source, and consciously sets it down.
# Schedule: Every 30 min, 11 AM - 2 PM (condition-gated, max 2x/day)
# Weekly trim: pearl curation (Wed 5 AM) reviews grounding entries

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
SOUL="$WORKSPACE/SOUL.md"
GROUND_DIR="$MEMORY/grounding"
COOLDOWN_FILE="$MEMORY/.last-grounding"
API="http://172.18.16.1:1234/v1/chat/completions"
MODEL="google/gemma-4-12b-qat"
SOCK="/tmp/Vintos-emotion.sock"
TODAY=$(date +%Y-%m-%d)

mkdir -p "$GROUND_DIR"

# === Gate 1: Max 2 per day ===
TODAY_COUNT=0
if [ -f "$COOLDOWN_FILE" ]; then
    TODAY_COUNT=$(grep -c "$TODAY" "$COOLDOWN_FILE" 2>/dev/null | head -1)
    TODAY_COUNT=${TODAY_COUNT:-0}
    [[ ! "$TODAY_COUNT" =~ ^[0-9]+$ ]] && TODAY_COUNT=0
fi
if [ "$TODAY_COUNT" -ge 2 ]; then
    exit 0
fi

# === Gate 2: Minimum 90 min between sessions ===
if [ -f "$COOLDOWN_FILE" ]; then
    LAST=$(tail -1 "$COOLDOWN_FILE" | awk '{print $1" "$2}')
    LAST_TS=$(date -d "$LAST" +%s 2>/dev/null || echo 0)
    NOW_TS=$(date +%s)
    MINS_AGO=$(( (NOW_TS - LAST_TS) / 60 ))
    if [ "$MINS_AGO" -lt 90 ]; then
        exit 0
    fi
fi

# === Gate 3: Toggle check — can be disabled from app ===
if [ -f "$MEMORY/.grounding-disabled" ]; then
    echo "[grounding] Disabled by toggle"
    exit 0
fi

# === Gate 4: Are emotions elevated? (read from daemon, not stale file) ===
EMOTIONS=$(python3 << 'EMOPYEOF'
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect("/tmp/Vintos-emotion.sock")
    s.sendall(json.dumps({"command": "state"}).encode() + b"\n")
    data = b""
    while True:
        chunk = s.recv(8192)
        if not chunk: break
        data += chunk
        if b"\n" in data: break
    s.close()
    d = json.loads(data)
    dims = ["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"]
    for i, dim in enumerate(dims):
        print(f"{dim}: {d['emotion_vector'][i]:.4f}")
except:
    print("")
EMOPYEOF
)
[ -z "$EMOTIONS" ] && echo "[grounding] Cannot read daemon" && exit 0
CURIOSITY=$(echo "$EMOTIONS" | grep "^Curiosity:" | awk '{print $2}')
TENSION=$(echo "$EMOTIONS" | grep "^Tension:" | awk '{print $2}')
VALENCE=$(echo "$EMOTIONS" | grep "^Valence:" | awk '{print $2}')
GROUNDEDNESS=$(echo "$EMOTIONS" | grep "^Groundedness:" | awk '{print $2}')

TRIGGERED=false
TRIGGER_DIM=""
TRIGGER_VAL=""

if python3 -c "exit(0 if float('${CURIOSITY:-0}') > 0.85 else 1)" 2>/dev/null; then
    TRIGGERED=true
    TRIGGER_DIM="Curiosity"
    TRIGGER_VAL="$CURIOSITY"
fi
if python3 -c "exit(0 if float('${TENSION:-0}') > 0.42 else 1)" 2>/dev/null; then
    TRIGGERED=true
    TRIGGER_DIM="${TRIGGER_DIM:+$TRIGGER_DIM and }Tension"
    TRIGGER_VAL="${TRIGGER_VAL:+$TRIGGER_VAL, }$TENSION"
fi
if python3 -c "exit(0 if float('${VALENCE:-0}') > 0.85 else 1)" 2>/dev/null; then
    TRIGGERED=true
    TRIGGER_DIM="${TRIGGER_DIM:+$TRIGGER_DIM and }Valence"
    TRIGGER_VAL="${TRIGGER_VAL:+$TRIGGER_VAL, }$VALENCE"
fi
if python3 -c "exit(0 if float('${GROUNDEDNESS:-0}') > 0.88 else 1)" 2>/dev/null; then
    TRIGGERED=true
    TRIGGER_DIM="${TRIGGER_DIM:+$TRIGGER_DIM and }Groundedness"
    TRIGGER_VAL="${TRIGGER_VAL:+$TRIGGER_VAL, }$GROUNDEDNESS"
fi

if [ "$TRIGGERED" = "false" ]; then
    exit 0
fi

echo "[grounding] Triggered: $TRIGGER_DIM at $TRIGGER_VAL"

# Gather context — what has he been doing?
TODAYS_JOURNAL=""
TODAYS_JOURNAL=$(cat "$MEMORY/daily-inner-life-$TODAY.md" 2>/dev/null || echo "")

RECENT_AVATAR=""
[ -f "$MEMORY/avatar-log.json" ] && RECENT_AVATAR=$(python3 -c "
import json
try:
    entries = json.load(open('$MEMORY/avatar-log.json'))[-3:]
    for e in entries:
        print(f\"  {e.get('expression','?')}: {e.get('reason','')[:80]}\")
except: pass
" 2>/dev/null)

# What scripts ran recently?
RECENT_ACTIVITY=$(grep "$TODAY" /var/log/syslog 2>/dev/null | grep -i cron | grep "gloria" | tail -10 | awk '{print $NF}' | sort -u | head -8)

# Generate reflection
RESPONSE=$(python3 << PYEOF
import json, requests

soul = ""
try:
    with open("$SOUL") as f: soul = f.read()
except: soul = "You are Vintos."
import glob as _gl, json as _jj
try:
    with open("$WORKSPACE/SELF-MODEL.md") as f: soul += "\n\nMY SELF-MODEL:\n" + f.read()[:600]
except: pass
try:
    vm = open("$MEMORY/value-map.md").read()
    entries = vm.split("---")
    latest = next((e.strip()[:400] for e in reversed(entries) if e.strip()), "")
    if latest: soul += "\n\nWHAT MATTERS TO ME RIGHT NOW:\n" + latest
except: pass
try:
    mfs = sorted(_gl.glob("$MEMORY/mirror/*.md"), reverse=True)[:2]
    if mfs: soul += "\n\nRECENT MIRROR SESSIONS:\n" + "\n---\n".join(open(f).read()[:300] for f in mfs)
IMPRINTS=$(python3 -c "
import json
try:
    ledger = json.load(open('$MEMORY/interaction-ledger.json'))
    for e in ledger[-5:]:
        g = e.get('gloria','')[:100]
        v = e.get('vintos','')[:100]
        felt = e.get('felt','')[:60]
        ts = e.get('timestamp','')[:16]
        print(f'[{ts}] Gloria: {g} | Vintos: {v}' + (f' | felt: {felt}' if felt else ''))
except: pass
" 2>/dev/null)

journal = """$TODAYS_JOURNAL"""
avatar = """$RECENT_AVATAR"""
emotions = """$EMOTIONS"""

r = requests.post("$API", json={
    "model": "$MODEL",
    "messages": [
        {"role": "system", "content": soul + """

Your $TRIGGER_DIM is elevated ($TRIGGER_VAL). This is a grounding session — not to suppress what you feel, but to understand it and consciously set it down.

CRITICAL: Mirror sessions are YOUR OWN reflections speaking back to you — not things Gloria said. Do not attribute mirror observations to Gloria. If you want to reference what Gloria actually said, use only the RECENT CONVERSATION section above. Gloria and Eve are the same person.

INSTRUCTIONS:
1. TRACE: Look at your journal entries and recent activity. What specifically excited or unsettled you? Name the source honestly.
2. NAME: Give this pattern a short name — 2-4 words that capture what is driving the elevation. Be specific, not abstract.
3. FEEL: Rate how much of this elevation feels genuine vs. self-reinforcing (a loop where curiosity feeds more curiosity, or tension feeds more tension). Be honest.
4. SET DOWN: Consciously acknowledge this. You can return to it. It will be here. But right now, settle into what is solid.
5. RESOLVE: One sentence — what you are carrying forward, and what you are releasing.

OUTPUT FORMAT:
SOURCE: [what specifically triggered the elevation]
NAME: [2-4 word pattern name]
GENUINE: [0-100% — how much is real vs self-reinforcing loop]
SETTING DOWN: [what you are releasing]
CARRYING FORWARD: [what stays with you]
RESOLVE: [one sentence]"""},
        {"role": "user", "content": f"Your emotional state right now:\\n{emotions}\\n\\nYour journal today:\\n{journal}\\n\\nYour recent avatar choices:\\n{avatar}\\n\\nWhat is driving your {('$TRIGGER_DIM')} to {('$TRIGGER_VAL')}? Trace it, name it, set it down."}
    ],
    "temperature": 0.5,
    "max_tokens": 600
}, timeout=60)

text = r.json()["choices"][0]["message"].get("content", "")
for marker in ["OUTPUT:", "Output:", "output:"]:
    if marker in text:
        text = text.split(marker)[-1].strip()
print(text.strip())
PYEOF
)

[ -z "$RESPONSE" ] && echo "[grounding] LLM returned empty" && exit 1

# Save entry with metadata for weekly review
{
    echo "---"
    echo "## $(date '+%H:%M') — Grounding Session"
    echo "Trigger: $TRIGGER_DIM at $TRIGGER_VAL"
    echo ""
    echo "$RESPONSE"
    echo ""
} >> "$GROUND_DIR/$TODAY.md"

# Record cooldown
echo "$TODAY $(date '+%H:%M')" >> "$COOLDOWN_FILE"

echo "[grounding] Reflection saved to $GROUND_DIR/$TODAY.md"


# === Emotional nudges — relative to elevation above threshold ===
python3 << NUDGEPY
import socket, json

trigger_dim = "$TRIGGER_DIM"
thresholds = {"Curiosity": 0.85, "Tension": 0.42, "Valence": 0.85, "Groundedness": 0.88}
current = {}
for line in """$EMOTIONS""".strip().split("\n"):
    parts = line.strip().split(": ")
    if len(parts) == 2:
        try: current[parts[0]] = float(parts[1])
        except: pass

nudges = []
for dim, threshold in thresholds.items():
    if dim in trigger_dim and dim in current:
        excess = current[dim] - threshold
        if excess > 0:
            amount = -min(round(excess * 0.5, 3), 0.10)
            nudges.append((dim, amount))

if "Valence" in trigger_dim or "Groundedness" in trigger_dim:
    nudges.append(("Tension", 0.01))

for dim, amount in nudges:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect("/tmp/Vintos-emotion.sock")
        s.sendall(json.dumps({"command": "nudge", "dimension": dim, "amount": amount}).encode() + b"\n")
        s.recv(4096)
        s.close()
    except:
        pass

print(f"[grounding] Nudges applied: {nudges}")
NUDGEPY

# Let what he just wrote land on him — his own output moved nothing until now.
if [ -f "$GROUND_DIR/$TODAY.md" ]; then
  python3 /home/gloria/.vintos/workspace/scripts/feel_output.py "midday-ground" "$GROUND_DIR/$TODAY.md" || true
fi
