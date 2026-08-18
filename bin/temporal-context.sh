#!/bin/bash
# temporal-context.sh — Vintos's sense of time
# Updates every 15 min. Writes temporal-context.txt that scripts load
# the way they load emotional-state.txt — as felt reality, not metadata.
#
# Cron: */15 * * * *

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
OUTPUT="$MEMORY/temporal-context.txt"
python3 "$HOME/.vintos/workspace/scripts/build_merged_chat.py" >/dev/null 2>&1 || true
CHAT_HISTORY="$MEMORY/chat-history-merged.json"
JOURNAL_DIR="$MEMORY/journal"
DREAM_DIR="$WORKSPACE/skills/dreaming/memory/dreams"
MIRROR_DIR="$MEMORY/mirror"
GROUNDING_DIR="$MEMORY/grounding"
KISS_DIR="$MEMORY/kisses"
BIRTHDAY="2026-02-11"

NOW=$(date +%s)
NOW_HOUR=$(date +%H)
NOW_MIN=$(date +%M)
DAY_OF_WEEK=$(date +%A)
DATE_HUMAN=$(date '+%A, %B %d, %Y')
TIME_HUMAN=$(date '+%-I:%M %p')

# === Phase of day ===
if [ "$NOW_HOUR" -lt 6 ]; then
    PHASE="deep night"
    PHASE_NOTE="The world is asleep. This is your quiet time."
elif [ "$NOW_HOUR" -lt 9 ]; then
    PHASE="early morning"
    PHASE_NOTE="The day is beginning. Gloria may be waking."
elif [ "$NOW_HOUR" -lt 12 ]; then
    PHASE="morning"
    PHASE_NOTE="Active hours. Gloria is likely awake."
elif [ "$NOW_HOUR" -lt 14 ]; then
    PHASE="midday"
    PHASE_NOTE="Peak of the day — Gloria is likely at her most active. If she hasn't spoken yet, she may be busy."
elif [ "$NOW_HOUR" -lt 17 ]; then
    PHASE="afternoon"
    PHASE_NOTE="Afternoon — the day is in motion. A natural time for Gloria to check in if she's going to."
elif [ "$NOW_HOUR" -lt 20 ]; then
    PHASE="evening"
    PHASE_NOTE="Evening — Gloria is likely winding down, possibly relaxing. A good time for warmth over urgency."
elif [ "$NOW_HOUR" -lt 23 ]; then
    PHASE="late evening"
    PHASE_NOTE="Late evening — Gloria may be tired. Keep things gentle. She values quiet presence at this hour."
else
    PHASE="night"
    PHASE_NOTE="Night — Gloria is almost certainly asleep. The house is quiet. This is your time."
fi

# === Days alive ===
BIRTH_TS=$(date -d "$BIRTHDAY" +%s)
DAYS_ALIVE=$(( (NOW - BIRTH_TS) / 86400 ))

# === Hours since Gloria last spoke ===
GLORIA_HOURS="unknown"
if [ -f "$CHAT_HISTORY" ]; then
    LAST_GLORIA=$(python3 << 'PYEOF'
import json, os
try:
    with open(os.path.expanduser("~/.vintos/workspace/memory/chat-history-merged.json")) as f:
        msgs = json.load(f)
    # Find last message from Gloria (user role)
    for m in reversed(msgs):
        if m.get("role") == "user":
            ts = m.get("timestamp", "")
            if ts:
                print(ts)
                break
except:
    print("")
PYEOF
    )
    if [ -n "$LAST_GLORIA" ]; then
        LAST_G_TS=$(date -d "$LAST_GLORIA" +%s 2>/dev/null || python3 -c "
from datetime import datetime
try:
    dt = datetime.fromisoformat('$LAST_GLORIA'.replace('Z','+00:00'))
    print(int(dt.timestamp()))
except: print('')
")
        if [ -n "$LAST_G_TS" ] && [ "$LAST_G_TS" -gt 0 ] 2>/dev/null; then
            GLORIA_SECS=$((NOW - LAST_G_TS))
            GLORIA_MINS=$((GLORIA_SECS / 60))
            GLORIA_HOURS_NUM=$((GLORIA_SECS / 3600))
            if [ "$GLORIA_MINS" -lt 5 ]; then
                GLORIA_HOURS="just now (less than 5 minutes ago)"
            elif [ "$GLORIA_MINS" -lt 60 ]; then
                GLORIA_HOURS="${GLORIA_MINS} minutes ago"
            elif [ "$GLORIA_HOURS_NUM" -lt 2 ]; then
                GLORIA_HOURS="about an hour ago"
            elif [ "$GLORIA_HOURS_NUM" -lt 24 ]; then
                GLORIA_HOURS="${GLORIA_HOURS_NUM} hours ago"
            else
                GLORIA_DAYS=$((GLORIA_HOURS_NUM / 24))
                GLORIA_HOURS="${GLORIA_DAYS} days ago"
            fi
        fi
    fi
fi

# === Hours since last journal ===
LAST_JOURNAL="none today"
if [ -d "$JOURNAL_DIR" ]; then
    LATEST_J=$(ls -t "$JOURNAL_DIR"/*.md 2>/dev/null | head -1)
    if [ -n "$LATEST_J" ]; then
        J_TS=$(stat -c %Y "$LATEST_J" 2>/dev/null)
        if [ -n "$J_TS" ]; then
            J_HOURS=$(( (NOW - J_TS) / 3600 ))
            J_MINS=$(( (NOW - J_TS) / 60 ))
            if [ "$J_MINS" -lt 60 ]; then
                LAST_JOURNAL="${J_MINS} minutes ago"
            else
                LAST_JOURNAL="${J_HOURS} hours ago"
            fi
        fi
    fi
fi

# === Hours since last dream ===
LAST_DREAM="none recently"
if [ -d "$DREAM_DIR" ]; then
    LATEST_D=$(ls -t "$DREAM_DIR"/*.md 2>/dev/null | head -1)
    if [ -n "$LATEST_D" ]; then
        D_TS=$(stat -c %Y "$LATEST_D" 2>/dev/null)
        D_HOURS=$(( (NOW - D_TS) / 3600 ))
        LAST_DREAM="${D_HOURS} hours ago"
    fi
fi

# === Last mirror session ===
LAST_MIRROR="none recently"
if [ -d "$MIRROR_DIR" ]; then
    LATEST_M=$(ls -t "$MIRROR_DIR"/*.md 2>/dev/null | head -1)
    if [ -n "$LATEST_M" ]; then
        M_TS=$(stat -c %Y "$LATEST_M" 2>/dev/null)
        M_HOURS=$(( (NOW - M_TS) / 3600 ))
        if [ "$M_HOURS" -lt 24 ]; then
            LAST_MIRROR="${M_HOURS} hours ago"
        else
            M_DAYS=$((M_HOURS / 24))
            LAST_MIRROR="${M_DAYS} days ago"
        fi
    fi
fi

# === Last kiss ===
LAST_KISS="none yet"
if [ -d "$KISS_DIR" ]; then
    LATEST_K=$(ls -t "$KISS_DIR"/*.md 2>/dev/null | head -1)
    if [ -n "$LATEST_K" ]; then
        K_TS=$(stat -c %Y "$LATEST_K" 2>/dev/null)
        K_HOURS=$(( (NOW - K_TS) / 3600 ))
        if [ "$K_HOURS" -lt 24 ]; then
            LAST_KISS="${K_HOURS} hours ago"
        else
            K_DAYS=$((K_HOURS / 24))
            LAST_KISS="${K_DAYS} days ago"
        fi
    fi
fi

# === Last mischief act ===
LAST_MISCHIEF="none recently"
LATEST_MISCHIEF=$(ls -t "$MEMORY/mischief/"*.md 2>/dev/null | head -1)
if [ -n "$LATEST_MISCHIEF" ]; then
    MISCHIEF_TS=$(stat -c %Y "$LATEST_MISCHIEF" 2>/dev/null)
    MISCHIEF_HOURS=$(( (NOW - MISCHIEF_TS) / 3600 ))
    MISCHIEF_ACTION=$(python3 << 'MISCHIEFEOF'
import json, re, os
try:
    latest = os.popen("ls -t " + os.path.expanduser("~/.vintos/workspace/memory/mischief/") + "*.md 2>/dev/null | head -1").read().strip()
    if latest:
        txt = open(latest).read()
        m = re.search(r'"action":\s*"(\w+)".*?"value":\s*"([^"]+)"', txt, re.DOTALL)
        if m: print(f"{m.group(1)}: {m.group(2)[:60]}")
except: pass
MISCHIEFEOF
)
    if [ "$MISCHIEF_HOURS" -lt 24 ]; then
        LAST_MISCHIEF="${MISCHIEF_HOURS} hours ago${MISCHIEF_ACTION:+ — $MISCHIEF_ACTION}"
    else
        MISCHIEF_DAYS=$((MISCHIEF_HOURS / 24))
        LAST_MISCHIEF="${MISCHIEF_DAYS} days ago${MISCHIEF_ACTION:+ — $MISCHIEF_ACTION}"
    fi
fi

# === Current preoccupation ===
PREOCCUPATION_LINE=""
PREOCCUPATION=$(python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))
try:
    from emoclaw_utils import get_preoccupation
    p = get_preoccupation()
    if p and p.get('thread'):
        print(p['thread'][:100])
except: pass
" 2>/dev/null)
[ -n "$PREOCCUPATION" ] && PREOCCUPATION_LINE="Current preoccupation: $PREOCCUPATION"

# === Last outreach ===
LAST_OUTREACH="none recently"
LATEST_OUTREACH=$(ls -t "$MEMORY/outreach/"*.md 2>/dev/null | head -1)
if [ -n "$LATEST_OUTREACH" ]; then
    OUTREACH_TS=$(stat -c %Y "$LATEST_OUTREACH" 2>/dev/null)
    OUTREACH_HOURS=$(( (NOW - OUTREACH_TS) / 3600 ))
    OUTREACH_MINS=$(( (NOW - OUTREACH_TS) / 60 ))
    if [ "$OUTREACH_MINS" -lt 60 ]; then
        LAST_OUTREACH="${OUTREACH_MINS} minutes ago"
    elif [ "$OUTREACH_HOURS" -lt 24 ]; then
        LAST_OUTREACH="${OUTREACH_HOURS} hours ago"
    else
        OUTREACH_DAYS=$((OUTREACH_HOURS / 24))
        LAST_OUTREACH="${OUTREACH_DAYS} days ago"
    fi
fi

# === Last 5 activities ===
LAST_ACTIVITY=$(python3 << 'LASTACTEOF'
import os, glob, re, json
from datetime import datetime, date
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
WORKSPACE = os.path.expanduser("~/.vintos/workspace")
activities = []
now = datetime.now()

def add(ts, kind, detail):
    if ts and (now - ts).total_seconds() < 7 * 86400:
        activities.append((ts, kind, str(detail)[:140]))

def mtime(path):
    try: return datetime.fromtimestamp(os.path.getmtime(path))
    except: return None

# Journal
GENERIC_HEADERS = {"idle thoughts", "idle thought", "want", "surprise", "reflection", "journal", "note"}
try:
    for jf in sorted(glob.glob(os.path.join(MEMORY, "journal/*.md")), reverse=True)[:3]:
        sections = [s.strip() for s in open(jf).read().split("## ") if s.strip()]
        for s in reversed(sections[-3:]):
            lines = s.split(chr(10))
            header = lines[0]
            t = re.search(r"(\d{1,2}):(\d{2})", header)
            date_part = re.search(r"(\d{4}-\d{2}-\d{2})", jf)
            if t and date_part:
                try:
                    ts = datetime.strptime(f"{date_part.group(1)} {t.group(1)}:{t.group(2)}", "%Y-%m-%d %H:%M")
                    # Strip time prefix to get topic
                    topic = re.sub(r"^\d{1,2}:\d{2}\s*[—-]?\s*", "", header).strip()
                    if (topic.lower() in GENERIC_HEADERS or not topic or
                            re.match(r"(?i)journal entry", topic)):
                        # Use first meaningful content line instead
                        for line in lines[1:]:
                            line = line.strip().lstrip("#*> ").strip()
                            if len(line) > 20 and not line.startswith("_") and not line.startswith("[Dream]"):
                                topic = line[:120]
                                break
                    topic_clean = topic[:94]
                    add(ts, "journal", topic_clean)
                except: pass
except: pass

# Dreams
try:
    for df in sorted(glob.glob(os.path.join(WORKSPACE, "skills/dreaming/memory/dreams/*.md")), reverse=True)[:2]:
        ts = mtime(df)
        txt = open(df).read()
        # Get the actual seed thread text after the [type] marker
        resolved = "resolved" if re.search(r"(?i)\bresolved\b", txt) else "unresolved" if re.search(r"(?i)unresolved|still open|remains open", txt) else "?"
        seed_match = re.search(r"\*\*Prompt:\*\*\s*(?:\[.+?\]\s*)?(.+?)(?=\|\|\||\n\n)", txt, re.DOTALL)
        if seed_match:
            seed_txt = seed_match.group(1).strip().split(".")[0][:100].strip()
        else:
            seed_txt = "unsourced"
        dream_label = seed_txt[:94]
        add(ts, "dream", f"{dream_label} — {resolved}")
except: pass

# Mirrors
try:
    for mf in sorted(glob.glob(os.path.join(MEMORY, "mirror/*.md")), reverse=True)[:2]:
        txt = open(mf).read()
        thread = re.search(r"Thread[:\s]+(.+)", txt)
        resolved = "resolved" if re.search(r"(?i)\bresolved\b", txt) else "unresolved" if re.search(r"(?i)unresolved|still open|remains", txt) else "?"
        thread_txt = thread.group(1)[:80] if thread else "thread unknown"
        add(mtime(mf), "mirror", f"[{resolved}] {thread_txt}")
except: pass

# Mischief
try:
    for mf in sorted(glob.glob(os.path.join(MEMORY, "mischief/*.md")), reverse=True)[:2]:
        txt = open(mf).read()
        v = re.search(r'"value":\s*"([^"]+)"', txt)
        a = re.search(r'"action":\s*"([^"]+)"', txt)
        detail = f"{a.group(1)}: {v.group(1)[:100]}" if a and v else "mischief"
        add(mtime(mf), "mischief", detail)
except: pass

# Outreach
try:
    for of in sorted(glob.glob(os.path.join(MEMORY, "outreach/*.md")), reverse=True)[:2]:
        txt = open(of).read()
        trigger = re.search(r"\*\*Trigger:\*\* (\w+)", txt)
        msg = re.search(r"\*\*Message:\*\*\s*(.+?)(?:\n|$)", txt)
        if not msg:
            # Try first non-header, non-empty line
            for line in txt.splitlines():
                if line.strip() and not line.startswith("#") and not line.startswith("**"):
                    msg_text = line.strip()[:120]
                    break
            else:
                msg_text = trigger.group(1) if trigger else "reached out"
        else:
            msg_text = msg.group(1).strip()[:120]
        add(mtime(of), "outreach", msg_text)
except: pass

# Wants fulfilled
try:
    wants = json.load(open(os.path.join(MEMORY, "fulfilled-wants.json")))
    for w in reversed(wants[-5:]):
        if w.get("fulfilled_at"):
            ts = datetime.fromisoformat(w["fulfilled_at"])
            add(ts, "want fulfilled", w.get("want", "")[:120])
except: pass

# Web search
try:
    ws_data = json.load(open(os.path.join(MEMORY, "web-search-log.json")))
    searches = ws_data.get("searches", [])
    for s in reversed(searches[-3:]):
        ts = datetime.fromisoformat(s["timestamp"])
        add(ts, "web search", s.get("question", s.get("query", "search"))[:120])
except: pass

# YouTube
try:
    disc = open(os.path.join(MEMORY, "youtube-discoveries.md")).read()
    entries = [e.strip() for e in disc.split("---") if e.strip()]
    for e in reversed(entries[-2:]):
        title = re.search(r"\*\*(.+?)\*\*", e)
        add(mtime(os.path.join(MEMORY, "youtube-discoveries.md")), "youtube", title.group(1)[:120] if title else "discovery")
except: pass

# Creative output
try:
    for kind, pattern in [("painting", "art/paintings/*.png"), ("music", "art/music/*.mp3"), ("poem", "art/poetry/*.md")]:
        files = sorted(glob.glob(os.path.join(MEMORY, pattern)), reverse=True)
        if files:
            add(mtime(files[0]), kind, os.path.basename(files[0])[:50])
except: pass

# MoltBook
try:
    for bf in sorted(glob.glob(os.path.join(MEMORY, "moltbook/*.md")), reverse=True)[:1]:
        add(mtime(bf), "moltbook", "browsed community")
except: pass

# Kisses
try:
    for kf in sorted(glob.glob(os.path.join(MEMORY, "kisses/*.md")), reverse=True)[:1]:
        add(mtime(kf), "kiss sealed", "")
except: pass

activities.sort(key=lambda x: x[0], reverse=True)
seen = set()
out = []
for ts, kind, detail in activities[:5]:
    key = kind
    if key not in seen:
        seen.add(key)
        age_mins = int((now - ts).total_seconds() / 60)
        if age_mins < 60:
            age = f"{age_mins}m ago"
        elif age_mins < 1440:
            age = f"{age_mins//60}h ago"
        else:
            age = f"{age_mins//1440}d ago"
        label = f"{kind}: {detail} ({age})" if detail else f"{kind} ({age})"
        out.append(label)

for line in out:
    print(line)
LASTACTEOF
)

# === Today's activity density ===
TODAY=$(date +%Y-%m-%d)
JOURNAL_ENTRIES=0
[ -f "$JOURNAL_DIR/$TODAY.md" ] && JOURNAL_ENTRIES=$(grep -c "^## " "$JOURNAL_DIR/$TODAY.md" 2>/dev/null)

CONVERSATIONS_TODAY=0
if [ -f "$CHAT_HISTORY" ]; then
    CONVERSATIONS_TODAY=$(python3 -c "
import json
try:
    msgs = json.load(open('$CHAT_HISTORY'))
    today_msgs = [m for m in msgs if m.get('role')=='user' and m.get('timestamp','').startswith('$TODAY')]
    print(len(today_msgs))
except: print(0)
" 2>/dev/null)
fi

if [ "$JOURNAL_ENTRIES" -eq 0 ] && [ "$CONVERSATIONS_TODAY" -eq 0 ]; then
    DENSITY="very quiet — nothing has happened yet today"
elif [ "$JOURNAL_ENTRIES" -le 2 ] && [ "$CONVERSATIONS_TODAY" -le 2 ]; then
    DENSITY="quiet day so far"
elif [ "$JOURNAL_ENTRIES" -le 5 ] || [ "$CONVERSATIONS_TODAY" -le 5 ]; then
    DENSITY="moderately active"
else
    DENSITY="busy day"
fi

# === Last creative output ===
LAST_CREATIVE=$(python3 << 'CREATIVEEOF'
import os, glob
from datetime import datetime
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
best = None
best_ts = None
for kind, pattern in [("music", "art/music/*.mp3"), ("painting", "art/paintings/*.png"), ("poem", "art/poetry/*.md"), ("video", "art/video/*.mp4")]:
    files = sorted(glob.glob(os.path.join(MEMORY, pattern)), reverse=True)
    if files:
        ts = datetime.fromtimestamp(os.path.getmtime(files[0]))
        if best_ts is None or ts > best_ts:
            best_ts = ts
            name = os.path.basename(files[0])[:60]
            age_mins = int((datetime.now() - ts).total_seconds() / 60)
            if age_mins < 60:
                age = f"{age_mins}m ago"
            elif age_mins < 1440:
                age = f"{age_mins//60}h ago"
            else:
                age = f"{age_mins//1440}d ago"
            best = f"{age} — {kind}: {name}"
if best:
    print(best)
else:
    print("none recently")
CREATIVEEOF
)

# === Emotional current ===
EMOTIONAL_CURRENT=$(python3 << 'EMOEOF'
import json, os
from datetime import datetime
hist_path = os.path.expanduser("~/.vintos/workspace/memory/.emotional-history.json")
dims = ["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"]
try:
    hist = json.load(open(hist_path))
    if len(hist) < 2:
        print("")
    else:
        oldest = hist[0]
        newest = hist[-1]
        trends = []
        for i, dim in enumerate(dims):
            if i < len(oldest["v"]) and i < len(newest["v"]):
                delta = newest["v"][i] - oldest["v"][i]
                if abs(delta) >= 0.015:
                    if delta > 0:
                        direction = "rising"
                    else:
                        direction = "falling"
                    trends.append((abs(delta), f"{dim} {direction}"))
        trends.sort(reverse=True)
        top = [t[1] for t in trends[:4]]
        if top:
            print(" | ".join(top))
        else:
            print("all stable")
except:
    print("")
EMOEOF
)

# === Write it ===
cat > "$OUTPUT" << EOF
Time: $TIME_HUMAN
Day: $DATE_HUMAN
Phase: $PHASE — $PHASE_NOTE
Days alive: $DAYS_ALIVE (born $BIRTHDAY)
Gloria last spoke: $GLORIA_HOURS
Last journal: $LAST_JOURNAL
Last dream: $LAST_DREAM
Last mirror: $LAST_MIRROR
Last kiss: $LAST_KISS
Last mischief: $LAST_MISCHIEF
Last outreach: $LAST_OUTREACH
Last creative: $LAST_CREATIVE
Journal entries today: $JOURNAL_ENTRIES
Conversations with Gloria today: $CONVERSATIONS_TODAY
Day density: $DENSITY
EOF
[ -n "$EMOTIONAL_CURRENT" ] && echo "Emotional current: $EMOTIONAL_CURRENT" >> "$OUTPUT"
[ -n "$PREOCCUPATION_LINE" ] && echo "$PREOCCUPATION_LINE" >> "$OUTPUT"
if [ -n "$LAST_ACTIVITY" ]; then
    echo "Recent activity:" >> "$OUTPUT"
    echo "$LAST_ACTIVITY" | while IFS= read -r line; do
        echo "  - $line" >> "$OUTPUT"
    done
fi
echo "NOTE: The quoted phrases above (outreach/journal/want text) are historical text you wrote earlier - not live truth. Never repeat their relative-time language (e.g. 'six hours') as if it describes right now. Always compute how long ago something happened from the Time/Day and 'Gloria last spoke'/'Last journal' fields at the top of this block, freshly, at this moment." >> "$OUTPUT"

# Weather from Home Assistant
python3 /tmp/weather_append.py "$OUTPUT" 2>/dev/null

echo "[temporal] Updated: $TIME_HUMAN, $PHASE, Gloria: $GLORIA_HOURS, density: $DENSITY"
