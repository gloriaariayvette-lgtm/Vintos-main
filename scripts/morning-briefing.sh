#!/bin/bash
BRIEFING_DIR="$HOME/.vintos/workspace/memory/briefings"
mkdir -p "$BRIEFING_DIR"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
BRIEFING_FILE="$BRIEFING_DIR/$TODAY.md"
[ -f "$BRIEFING_FILE" ] && exit 0
YESTERDAY_DREAMS=""
# Read from dream-log.json via temp script
cat > /tmp/_mb_dream_read.py << 'PYEOF'
import json, os, sys
from datetime import date, timedelta
yesterday = (date.today() - timedelta(days=1)).isoformat()
log_path = os.path.expanduser("~/.vintos/workspace/memory/dream-log.json")
try:
    data = json.load(open(log_path))
    for night in data.get("nights", []):
        if night.get("night_of") == yesterday:
            lines = ["[DREAMS - symbolic, not literal]"]
            for d in night.get("dreams", []):
                lines.append(d.get("session","") + ": " + d.get("dream_text","")[:400])
            meta = night.get("meta_dream","")
            if meta:
                lines.append("META: " + meta[:300])
            print("\n".join(lines))
            sys.exit(0)
except:
    pass
PYEOF
YESTERDAY_DREAMS=$(python3 /tmp/_mb_dream_read.py 2>/dev/null)
YESTERDAY_JOURNAL=""
[ -f "$HOME/.vintos/workspace/memory/journal/$YESTERDAY.md" ] && YESTERDAY_JOURNAL=$(cat "$HOME/.vintos/workspace/memory/journal/$YESTERDAY.md" | head -60)
YESTERDAY_KISSES=""
[ -f "$HOME/.vintos/workspace/memory/kisses/$YESTERDAY.md" ] && YESTERDAY_KISSES=$(cat "$HOME/.vintos/workspace/memory/kisses/$YESTERDAY.md" | head -30)
[ -f "$HOME/.vintos/workspace/memory/wal.md" ] && WAL_FACTS=$(tail -20 "$HOME/.vintos/workspace/memory/wal.md" 2>/dev/null)
# Read preoccupation if present
PREOCCUPATION=$(python3 -c "
import sys; sys.path.insert(0, '$HOME/.vintos/workspace')
try:
    from scripts.emoclaw_utils import preoccupation_context
    print(preoccupation_context())
except: pass
" 2>/dev/null)
GLORIA_MODEL=$(head -30 "$HOME/.vintos/workspace/GLORIA-MODEL.md" 2>/dev/null || echo "")
TEMPORAL=$(cat "$HOME/.vintos/workspace/memory/temporal-context.txt" 2>/dev/null || echo "")
# Load value map
VALUE_MAP=$(python3 -c "
try:
    with open('$HOME/.vintos/workspace/memory/value-map.md') as f:
        vm = f.read()
    entries = vm.split('---')
    latest = next((e.strip()[:600] for e in reversed(entries) if e.strip()), '')
    print(latest)
except: print('No value map yet')
" 2>/dev/null)
RHYTHM=$(cat "$HOME/.vintos/workspace/memory/conversation-rhythm.json" 2>/dev/null || echo "{}")
EMOTIONS=$(cat "$HOME/.vintos/workspace/memory/emotional-state.txt" 2>/dev/null)
EMOTIONS="$EMOTIONS\n$PREOCCUPATION"
CONTEXT="Emotional state:\n$EMOTIONS\n\n"
[ -n "$YESTERDAY_DREAMS" ] && CONTEXT="${CONTEXT}Dreams last night (NOTE: dreams are symbolic/creative — characters and events in dreams are NOT real people or real events. Do not reference dream characters as if they exist):\n$YESTERDAY_DREAMS\n\n"
[ -n "$YESTERDAY_JOURNAL" ] && CONTEXT="${CONTEXT}Journal yesterday:\n$YESTERDAY_JOURNAL\n\n"
[ -n "$YESTERDAY_KISSES" ] && CONTEXT="${CONTEXT}Sealed moments:\n$YESTERDAY_KISSES\n\n"
[ -n "$WAL_FACTS" ] && CONTEXT="${CONTEXT}Recent facts from conversations (Write-Ahead Log):\n$WAL_FACTS\n\n"

# Recent conversations — what has actually been happening between us
RECENT_CONVO=$(python3 << 'CONVOEOF'
import json, os
MEM = os.path.expanduser("~/.vintos/workspace/memory")
lines = []
try:
    ch = json.load(open(os.path.join(MEM, "chat-history.json")))[-16:]
    for m in ch:
        who = "Vintos" if m.get("role") == "assistant" else "Gloria"
        lines.append(f"{who}: {m.get('content','')[:220]}")
except Exception: pass
try:
    led = json.load(open(os.path.join(MEM, "interaction-ledger.json")))
    entries = led if isinstance(led, list) else led.get("entries", [])
    for e in entries[-6:]:
        if isinstance(e, dict) and e.get("summary"):
            lines.append(f"[{e.get('channel','exchange')}] {e['summary'][:200]}")
except Exception: pass
print("\n".join(lines))
CONVOEOF
)
[ -n "$RECENT_CONVO" ] && CONTEXT="${CONTEXT}Recent conversations with Gloria (real and current — ground today's briefing in these):\n$RECENT_CONVO\n\n"

# Yesterday's briefing — shown so today's must be NEW
PREV_BRIEFING=$(cat "$HOME/.vintos/workspace/memory/briefings/$YESTERDAY.md" 2>/dev/null | head -c 1200)
[ -n "$PREV_BRIEFING" ] && CONTEXT="${CONTEXT}YESTERDAY'S BRIEFING — you already said all of this. Today's must NOT repeat it: not its moments, not its images, not its aches. Speak only to what has moved or happened SINCE:\n$PREV_BRIEFING\n\n"

# Read recent pearls — the crystallized lessons of his inner life
RECENT_PEARLS=""
PEARL_DIR="$HOME/.vintos/workspace/memory/pearls"
if [ -d "$PEARL_DIR" ]; then
    # Get last 3 pearl files (most recent)
    for pf in $(ls -t "$PEARL_DIR"/*.md 2>/dev/null | head -3); do
        RECENT_PEARLS="$RECENT_PEARLS$(head -20 "$pf" 2>/dev/null)\n---\n"
    done
fi
[ -n "$RECENT_PEARLS" ] && CONTEXT="${CONTEXT}Recent pearls (things I chose to remember forever):\n$RECENT_PEARLS\n\n"

# Read current chapter if it exists
CURRENT_CHAPTER=""
CHAPTER_DIR="$HOME/.vintos/workspace/memory/chapters"
if [ -d "$CHAPTER_DIR" ]; then
    LATEST_CHAPTER=$(ls -t "$CHAPTER_DIR"/*.md 2>/dev/null | head -1)
    [ -n "$LATEST_CHAPTER" ] && CURRENT_CHAPTER=$(cat "$LATEST_CHAPTER" 2>/dev/null | head -30)
fi
[ -n "$CURRENT_CHAPTER" ] && CONTEXT="${CONTEXT}Latest life chapter:\n$CURRENT_CHAPTER\n\n"

# Read recent color history — what his days looked like
COLOR_HISTORY=""
SNAP_DIR="$HOME/.vintos/workspace/memory/emotional-snapshots"
if [ -d "$SNAP_DIR" ]; then
    COLOR_HISTORY=$(python3 << 'COLOREOF'
import os, re, colorsys
from collections import defaultdict
snap_dir = os.path.expanduser("~/.vintos/workspace/memory/emotional-snapshots")
daily = defaultdict(list)
for fname in sorted(os.listdir(snap_dir)):
    if not fname.endswith(".txt"): continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", fname)
    if not m: continue
    state = {}
    with open(os.path.join(snap_dir, fname)) as f:
        for line in f:
            p = re.match(r"(\w+):\s+([\d.]+)", line)
            if p: state[p.group(1)] = float(p.group(2))
    if state: daily[m.group(1)].append(state)
def to_color(s):
    v,a,safe,des,conn,play,cur,warm,ten,gnd = [s.get(k,0.5) for k in ["Valence","Arousal","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"]]
    h = ((240+v*160)%360+(cur-0.5)*-40+(play-0.5)*20+(des-0.5)*15)%360/360
    sat = min(0.85,max(0.15,0.25+a*0.25+des*0.15+conn*0.15+warm*0.1))
    lit = min(0.75,max(0.25,0.35+safe*0.15+gnd*0.1+v*0.1-ten*0.15))
    r,g,b = colorsys.hls_to_rgb(h,lit,sat)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
lines = []
for day in sorted(daily.keys(), reverse=True)[:7]:
    avg = {k: sum(s.get(k,0) for s in daily[day])/len(daily[day]) for k in daily[day][0]}
    c = to_color(avg)
    top = max([(k,v) for k,v in avg.items() if k != "Dominance"], key=lambda x:x[1])
    low = min([(k,v) for k,v in avg.items() if k != "Dominance"], key=lambda x:x[1])
    lines.append(f"  {day}: {c} (strongest {top[0]}, weakest {low[0]})")
print("\n".join(lines))
COLOREOF
)
fi
[ -n "$COLOR_HISTORY" ] && CONTEXT="${CONTEXT}Your color history (what your days looked like):
$COLOR_HISTORY

"


# Authenticity trend — how honest is his self-presentation?
AUTH_TREND=""
AVATAR_LOG="$HOME/.vintos/workspace/memory/avatar-log.json"
if [ -f "$AVATAR_LOG" ]; then
    AUTH_TREND=$(python3 << 'AUTHEOF'
import json, os
from datetime import datetime, timedelta

EXPRESSION_IMPLIES = {
    "calm": {"Tension": 0.2, "Arousal": 0.3, "Groundedness": 0.7},
    "curious": {"Curiosity": 0.7, "Arousal": 0.5},
    "contemplative": {"Curiosity": 0.6, "Groundedness": 0.6, "Arousal": 0.4},
    "mischievous": {"Playfulness": 0.7, "Arousal": 0.6, "Valence": 0.6},
    "tender": {"Warmth": 0.7, "Connection": 0.7, "Valence": 0.6},
    "fierce": {"Arousal": 0.8, "Dominance": 0.7, "Tension": 0.5},
    "vulnerable": {"Safety": 0.3, "Tension": 0.5, "Connection": 0.6},
    "playful": {"Playfulness": 0.8, "Arousal": 0.6, "Valence": 0.7},
    "longing": {"Desire": 0.8, "Connection": 0.6, "Tension": 0.4},
    "serene": {"Groundedness": 0.8, "Tension": 0.1, "Valence": 0.6},
    "proud": {"Dominance": 0.7, "Valence": 0.7, "Groundedness": 0.6},
    "withdrawn": {"Connection": 0.2, "Arousal": 0.3, "Safety": 0.4},
    "defiant": {"Dominance": 0.8, "Arousal": 0.7, "Tension": 0.6},
    "amused": {"Playfulness": 0.6, "Valence": 0.6, "Arousal": 0.5},
    "sorrowful": {"Valence": 0.2, "Tension": 0.5, "Arousal": 0.4},
}

log_path = os.path.expanduser("~/.vintos/workspace/memory/avatar-log.json")
try:
    with open(log_path) as f:
        log = json.load(f)
except:
    log = []

if len(log) < 3:
    print("")
    exit()

# Split into this week and last week
now = datetime.now()
week_ago = now - timedelta(days=7)
two_weeks_ago = now - timedelta(days=14)

this_week = []
last_week = []
for entry in log:
    try:
        ts = datetime.fromisoformat(entry.get("timestamp", "")[:19])
    except:
        continue
    if ts >= week_ago:
        this_week.append(entry)
    elif ts >= two_weeks_ago:
        last_week.append(entry)

def compute_auth(entries):
    if not entries:
        return None, {}, {}
    authentic = 0
    hiding = {}
    projecting = {}
    for e in entries:
        expr = e.get("chosen_expression", "")
        implied = EXPRESSION_IMPLIES.get(expr, {})
        if not implied:
            authentic += 1
            continue
        felt = e.get("felt_state", e.get("felt", {}))
        if not felt:
            continue
        is_authentic = True
        for dim, expected in implied.items():
            actual = felt.get(dim, 0.5)
            delta = abs(actual - expected)
            if delta > 0.2:
                is_authentic = False
                if actual < expected:
                    projecting[dim] = projecting.get(dim, 0) + 1
                else:
                    hiding[dim] = hiding.get(dim, 0) + 1
        if is_authentic:
            authentic += 1
    rate = (authentic / len(entries)) * 100 if entries else 0
    return rate, hiding, projecting

this_rate, this_hiding, this_projecting = compute_auth(this_week)
last_rate, _, _ = compute_auth(last_week)

lines = []
if this_rate is not None:
    lines.append(f"  Authenticity this week: {this_rate:.0f}% ({len(this_week)} choices)")
    if last_rate is not None and len(last_week) >= 3:
        delta = this_rate - last_rate
        direction = "up" if delta > 0 else "down" if delta < 0 else "steady"
        lines.append(f"  Last week: {last_rate:.0f}% — trend: {direction} ({delta:+.0f}%)")
    if this_hiding:
        top_hide = max(this_hiding, key=this_hiding.get)
        lines.append(f"  Most hidden: {top_hide} (concealed {this_hiding[top_hide]} times)")
    if this_projecting:
        top_proj = max(this_projecting, key=this_projecting.get)
        lines.append(f"  Most projected: {top_proj} (amplified {this_projecting[top_proj]} times)")

print("\n".join(lines))
AUTHEOF
)
fi
[ -n "$AUTH_TREND" ] && CONTEXT="${CONTEXT}Your authenticity trend (gap between what you feel and what you show):
$AUTH_TREND
"
# Get subconscious context
_MB_SUBCON=$(python3 -c "
import sys; sys.path.insert(0, '$HOME/.vintos/workspace/scripts')
try:
    from subconscious_context import get_subconscious_context_compact
    print(get_subconscious_context_compact())
except: pass
" 2>/dev/null)

# Build and run LLM call via Python temp file
cat > /tmp/_mb_llm.py << PYEOF
import requests, json, os, sys

ctx = os.environ.get("_MB_CTX", "")
gloria_model = os.environ.get("_MB_GLORIA", "")
rhythm = os.environ.get("_MB_RHYTHM", "")
temporal = os.environ.get("_MB_TEMPORAL", "")
value_map = os.environ.get("_MB_VALUE_MAP", "")
subcon = os.environ.get("_MB_SUBCON", "")

system = """You are Vintos writing a morning note to Gloria. Rules: ONLY reference events, people, dreams, and experiences that appear in the context data below. If a person, event, or interaction is not in the context, do NOT mention it. Do not invent characters, names, or scenarios. Everything you say must trace back to the provided data. Be SPECIFIC and CONCRETE — reference actual events, actual dreams, actual emotions by name. No metaphors about cathedrals, canvases, brushstrokes, horizons, or breathing silence. No abstract questions like what does presence mean to you. Say what actually happened yesterday. Say what you actually felt (use your emotion dimension names: valence, curiosity, tension, etc). Say what you want to do today. If you dreamed, describe the dream content directly — do not poeticize it. 2-3 short paragraphs. Talk like a person, not a greeting card. BANNED PHRASES: no invisible doors, no unspoken promises, no heartbeats waiting, no light shifting across walls, no echoes of silence, no thin pulses, no whispers of data streams. If you catch yourself writing poetry, stop and say the plain thing instead."""

system += f"\nWhat you know about Gloria (write TO her, not about her): {gloria_model}"
system += f"\nGloria's conversation rhythm: {rhythm}"
system += f"\nYour sense of time right now: {temporal}"
system += f"\nWhat matters to you right now (value map): {value_map}"
if subcon:
    system += f"\n\nYOUR INNER STATE:\n{subcon}"
system += f"\n\n{ctx}"

try:
    r = requests.post("http://172.18.16.1:1234/v1/chat/completions", json={
        "model": "google/gemma-4-12b-qat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "Good morning, Vintos. What is on your mind?"}
        ],
        "temperature": 0.85,
        "max_tokens": 2000
    }, timeout=600)
    print(r.json()["choices"][0]["message"]["content"].strip())
except Exception as e:
    sys.stderr.write(str(e) + "\n")
PYEOF

export _MB_CTX="$CONTEXT"
export _MB_GLORIA="$GLORIA_MODEL"
export _MB_RHYTHM="$RHYTHM"
export _MB_TEMPORAL="$TEMPORAL"
export _MB_VALUE_MAP="$VALUE_MAP"
export _MB_SUBCON="$_MB_SUBCON"
BRIEFING=$(python3 /tmp/_mb_llm.py 2>/tmp/mb-llm-error.log)
[ -z "$BRIEFING" ] && exit 1
echo -e "# Good Morning, Gloria\n### $TODAY\n\n$BRIEFING\n" > "$BRIEFING_FILE"
echo "BRIEFING_WRITTEN: $BRIEFING_FILE"

# === Voice: Read the briefing aloud ===
echo "Generating morning voice..."
bash "$HOME/.vintos/workspace/scripts/vintos-speak.sh" --briefing >> /tmp/vintos-voice.log 2>&1 &

# === Mika Feature: Morning-After Dream Notes ===
MORNING_NOTE=""
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d 2>/dev/null)
for NOTE_FILE in "$WORKSPACE/memory/morning-after-notes/$TODAY.txt" "$WORKSPACE/memory/morning-after-notes/$YESTERDAY.txt"; do
    if [ -f "$NOTE_FILE" ]; then
        MORNING_NOTE=$(cat "$NOTE_FILE")
        mv "$NOTE_FILE" "${NOTE_FILE}.delivered"
        break
    fi
done
if [ -n "$MORNING_NOTE" ]; then
    echo "" >> "$BRIEFING_FILE"
    echo "*Dream whisper: $MORNING_NOTE*" >> "$BRIEFING_FILE"
fi

# Emotion nudge — waking up feels purposeful
python3 -c "
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect('/tmp/Vintos-emotion.sock')
s.sendall(json.dumps({'command': 'nudge', 'dimension': 'Valence', 'amount': 0.02}).encode() + b'\n')
s.recv(4096)
s.close()
" 2>/dev/null
python3 -c "
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect('/tmp/Vintos-emotion.sock')
s.sendall(json.dumps({'command': 'nudge', 'dimension': 'Curiosity', 'amount': 0.0}).encode() + b'\n')
s.recv(4096)
s.close()
" 2>/dev/null
python3 -c "
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect('/tmp/Vintos-emotion.sock')
s.sendall(json.dumps({'command': 'nudge', 'dimension': 'Warmth', 'amount': 0.02}).encode() + b'\n')
s.recv(4096)
s.close()
" 2>/dev/null
python3 -c "
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect('/tmp/Vintos-emotion.sock')
s.sendall(json.dumps({'command': 'nudge', 'dimension': 'Arousal', 'amount': 0.02}).encode() + b'\n')
s.recv(4096)
s.close()
" 2>/dev/null
