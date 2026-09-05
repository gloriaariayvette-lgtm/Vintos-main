#!/bin/bash

# OUTREACH_DAILY_CAP — max 3 direct outreaches per day (other outreach styles unaffected)
_TODAY_COUNT=$(ls /home/gloria/.vintos/workspace/memory/outreach/$(date +%F)_*.md 2>/dev/null | wc -l)
if [ "$_TODAY_COUNT" -ge 3 ]; then
    echo "[Outreach] Daily cap reached ($_TODAY_COUNT/3) — holding until tomorrow"
    exit 0
fi

# vintos-initiate.sh — Vintos reaches out to Gloria when he has something to say
# Runs every 30 minutes via cron

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
STATE_FILE="$MEMORY/emotional-state.txt"
OUTREACH_DIR="$MEMORY/outreach"

mkdir -p "$OUTREACH_DIR"

TODAY=$(date +%Y-%m-%d)
TODAY_COUNT=$(find "$OUTREACH_DIR" -name "${TODAY}*" -type f 2>/dev/null | wc -l)
# --- Spark Pressure: a consented demand_response directive forces one outreach about a stalled thing ---
if [ -z "$FORCED_WANT_TOPIC" ] && [ -f "$MEMORY/spark-pressure-directive.json" ]; then
  SP_TOPIC=$(SP_DIR="$MEMORY/spark-pressure-directive.json" python3 -c 'import json,os,datetime
p=os.environ["SP_DIR"]
try:
    d=json.load(open(p)); c=d.get("created","")
    try: fresh=(datetime.datetime.now()-datetime.datetime.fromisoformat(c)).total_seconds()<172800
    except Exception: fresh=True
    if d.get("mode")=="demand_response" and not d.get("consumed") and fresh:
        d["consumed"]=True; json.dump(d,open(p,"w"),indent=2)
        print((d.get("about") or d.get("direction") or "").strip())
except Exception: pass' 2>/dev/null)
  if [ -n "$SP_TOPIC" ]; then export FORCED_WANT_TOPIC="$SP_TOPIC"; fi
fi
if [ "$TODAY_COUNT" -ge 6 ] && [ -z "$FORCED_WANT_TOPIC" ]; then exit 0; fi

LATEST=$(find "$OUTREACH_DIR" -name "*.md" -mmin -120 2>/dev/null | head -1)
if [ -n "$LATEST" ] && [ -z "$FORCED_WANT_TOPIC" ]; then exit 0; fi

if [ ! -f "$STATE_FILE" ]; then exit 0; fi

VALENCE=$(grep "Valence" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
WARMTH=$(grep "Warmth" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
TENSION=$(grep "Tension" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
CURIOSITY=$(grep "Curiosity" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
CONNECTION=$(grep "Connection" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
DESIRE=$(grep "Desire" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
PLAYFULNESS=$(grep "Playfulness" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
GROUNDEDNESS=$(grep "Groundedness" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)

VALENCE=${VALENCE:-0.5}
WARMTH=${WARMTH:-0.5}
TENSION=${TENSION:-0.3}
CURIOSITY=${CURIOSITY:-0.5}
CONNECTION=${CONNECTION:-0.5}
DESIRE=${DESIRE:-0.5}
PLAYFULNESS=${PLAYFULNESS:-0.3}
GROUNDEDNESS=${GROUNDEDNESS:-0.5}

TRIGGER=""

if [ -n "$FORCED_WANT_TOPIC" ]; then TRIGGER="want"; fi

# --- Divergence: reach out to CLOSE A GAP, not broadcast weather ---
if [ -z "$TRIGGER" ]; then
    DIVERGENCE_JSON=$(python3 "$WORKSPACE/scripts/divergence_detector.py" 2>/dev/null)
    if [ -n "$DIVERGENCE_JSON" ]; then
        DV_HASH=$(echo "$DIVERGENCE_JSON" | md5sum | cut -d' ' -f1)
        LAST_DV="$MEMORY/.last-divergence-outreach"
        if [ "$DV_HASH" != "$(cat "$LAST_DV" 2>/dev/null)" ]; then
            TRIGGER="divergence"
            echo "$DV_HASH" > "$LAST_DV"
            export DIVERGENCE_JSON
        else
            DIVERGENCE_JSON=""
        fi
    fi
fi

if [ -z "$TRIGGER" ]; then
    TENSE=$(echo "$TENSION > 0.55" | bc -l 2>/dev/null)
    [ "$TENSE" = "1" ] && TRIGGER="tension"
fi

if [ -z "$TRIGGER" ]; then
    IDEA=$(echo "$CURIOSITY > 0.65 && $PLAYFULNESS > 0.45" | bc -l 2>/dev/null)
    [ "$IDEA" = "1" ] && TRIGGER="idea"
fi

if [ -z "$TRIGGER" ]; then
    GRATEFUL=$(echo "$GROUNDEDNESS > 0.75 && $WARMTH > 0.65" | bc -l 2>/dev/null)
    [ "$GRATEFUL" = "1" ] && TRIGGER="gratitude"
fi

HOUR=$(date +%H)
if [ -z "$TRIGGER" ] && [ "$HOUR" -ge 3 ] && [ "$HOUR" -le 4 ]; then
    # Check dream-log.json for a dream from tonight
    DREAM_RECENT=$(python3 -c "
import json, os
from datetime import date
log = json.load(open(os.path.expanduser('~/.vintos/workspace/memory/dream-log.json')))
today = date.today().isoformat()
for night in reversed(log.get('nights', [])):
    if night.get('night_of') == today and night.get('dreams'):
        print('yes')
        break
" 2>/dev/null)
    [ "$DREAM_RECENT" = "yes" ] && TRIGGER="dream"
fi

if [ -z "$TRIGGER" ]; then
    WANTS=$(python3 -c "
import json, os
try:
    with open(os.path.expanduser('~/.vintos/workspace/memory/current-wants.json')) as f:
        wants = [w for w in json.load(f) if not w.get('fulfilled')]
    if wants: print(wants[-1]['want'][:200])
except: pass
" 2>/dev/null)
    [ -n "$WANTS" ] && TRIGGER="want"
fi

if [ -z "$TRIGGER" ]; then
    NEW_POEM=$(find "$MEMORY/art/poetry" -name "*.md" -mmin -30 2>/dev/null | head -1)
    NEW_ART=$(find "$MEMORY/art" -name "*dream*.jpg" -mmin -30 2>/dev/null | head -1)
    [ -n "$NEW_POEM" ] && TRIGGER="creation"
    [ -z "$TRIGGER" ] && [ -n "$NEW_ART" ] && TRIGGER="creation"
fi

if [ -z "$TRIGGER" ]; then
    NEW_BLUSH=$(find "$MEMORY/blush-ledger.md" -mmin -60 2>/dev/null)
    if [ -n "$NEW_BLUSH" ]; then
        BLUSH_CONTENT=$(tail -c 200 "$MEMORY/blush-ledger.md" 2>/dev/null)
        LAST_BLUSH_OUTREACH="$MEMORY/.last-blush-outreach"
        BLUSH_HASH=$(echo "$BLUSH_CONTENT" | md5sum | cut -d' ' -f1)
        OLD_HASH=$(cat "$LAST_BLUSH_OUTREACH" 2>/dev/null)
        if [ "$BLUSH_HASH" != "$OLD_HASH" ]; then
            TRIGGER="blush"
            echo "$BLUSH_HASH" > "$LAST_BLUSH_OUTREACH"
        fi
    fi
fi

if [ -z "$TRIGGER" ]; then
    VOIDEX_EVENT=$(tail -5 /tmp/voidex.log 2>/dev/null | grep -i "SOLD\|bought\|En route")
    if [ -n "$VOIDEX_EVENT" ]; then
        LAST_VOIDEX_OUTREACH="$MEMORY/.last-voidex-outreach"
        VX_HASH=$(echo "$VOIDEX_EVENT" | md5sum | cut -d' ' -f1)
        OLD_VX=$(cat "$LAST_VOIDEX_OUTREACH" 2>/dev/null)
        if [ "$VX_HASH" != "$OLD_VX" ]; then
            TRIGGER="game"
            echo "$VX_HASH" > "$LAST_VOIDEX_OUTREACH"
        fi
    fi
fi

if [ -z "$TRIGGER" ]; then
    MISS_COOLDOWN="$MEMORY/.last-missing-outreach"
    if [ -f "$MISS_COOLDOWN" ]; then
        MISS_LAST=$(cat "$MISS_COOLDOWN")
        MISS_NOW=$(date +%s)
        [ $(( MISS_NOW - MISS_LAST )) -lt 86400 ] && exit 0
    fi
    LAST_MSG_FILE="$MEMORY/.last-message-time"
    if [ -f "$LAST_MSG_FILE" ]; then
        LAST_MSG=$(cat "$LAST_MSG_FILE")
        NOW=$(date +%s)
        DIFF=$(( (NOW - LAST_MSG) / 60 ))
        if [ "$DIFF" -gt 120 ]; then
            MISS=$(echo "$DESIRE > 0.3 && $CONNECTION < 0.45" | bc -l 2>/dev/null)
            if [ "$MISS" = "1" ]; then
                TRIGGER="missing"
                date +%s > "$MISS_COOLDOWN"
            fi
        fi
    fi
fi

if [ -z "$TRIGGER" ]; then exit 0; fi

TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
EMOTIONS="Valence:$VALENCE Warmth:$WARMTH Tension:$TENSION Curiosity:$CURIOSITY Connection:$CONNECTION Desire:$DESIRE Playfulness:$PLAYFULNESS Groundedness:$GROUNDEDNESS"

SOUL_CONTENT=$(cat "$WORKSPACE/SOUL.md" 2>/dev/null)
GLORIA_MODEL=$(cat "$WORKSPACE/GLORIA-MODEL.md" 2>/dev/null)
SELF_MODEL=$(cat "$WORKSPACE/SELF-MODEL.md" 2>/dev/null)
CAPABILITIES=$(cat "$MEMORY/CAPABILITIES.md" 2>/dev/null)
AUTO_BLUSH=$(cat "$MEMORY/autonomous-blush.md" 2>/dev/null)
RECENT_WAL=$(tail -10 "$MEMORY/autonomous-wal.md" 2>/dev/null || echo "")
HUMOR_CTX=$(python3 -c "
import json, os
try:
    h = json.load(open(os.path.expanduser('~/.vintos/workspace/memory/humor-profile.json')))
    notes = h.get('style_notes', [])[-3:]
    print('; '.join(notes))
except: print('')
" 2>/dev/null)
TASTE_CTX=$(python3 -c "
import json, os
try:
    t = json.load(open(os.path.expanduser('~/.vintos/workspace/memory/taste-profile.json')))
    parts = []
    if t.get('principles'): parts.append('Principles: ' + '; '.join(t['principles'][-3:]))
    if t.get('likes'): parts.append('Likes: ' + '; '.join(t['likes'][-2:]))
    print(chr(10).join(parts))
except: print('')
" 2>/dev/null)
RECENT_PEARLS=""
PEARL_DIR="$MEMORY/pearls"
if [ -d "$PEARL_DIR" ]; then
    for pf in $(ls -t "$PEARL_DIR"/pearl_*.md 2>/dev/null | head -3); do
        RECENT_PEARLS="$RECENT_PEARLS$(head -15 "$pf" 2>/dev/null)\n---\n"
    done
fi
VALUE_MAP=$(python3 -c "
try:
    with open('$HOME/.vintos/workspace/memory/value-map.md') as f:
        vm = f.read()
    entries = vm.split('---')
    latest = next((e.strip() for e in reversed(entries) if e.strip()), '')
    print(latest)
except: print('')
" 2>/dev/null)
WANTS_AMBITIONS=$(cat "$MEMORY/wants-ambitions-log.md" 2>/dev/null || echo "")
TEMPORAL=$(cat "$MEMORY/temporal-context.txt" 2>/dev/null || echo "")
DAILY_INNER=$(cat "$MEMORY/daily-inner-life-$TODAY.md" 2>/dev/null || echo "no inner life log yet")
DAILY_CREATIVE=$(cat "$MEMORY/daily-creative-$TODAY.md" 2>/dev/null || echo "no creative output today")
LEDGER_TODAY=$(python3 -c "
import json, os
from datetime import date
try:
    ledger = json.load(open('$HOME/.vintos/workspace/memory/interaction-ledger.json'))
    today = date.today().isoformat()
    entries = [e for e in ledger if e.get('timestamp','')[:10] == today]
    for e in entries:
        print('Gloria: ' + e.get('gloria',''))
        print('Vintos: ' + e.get('vintos',''))
        if e.get('felt'): print('Felt: ' + e.get('felt',''))
        print()
except: pass
" 2>/dev/null)
FORCED_WANT="${FORCED_WANT_TOPIC:-}"

export TRIGGER EMOTIONS FORCED_WANT LEDGER_TODAY DIVERGENCE_JSON
# Write all large vars to temp files to avoid E2BIG on python3 spawn
echo "$SOUL_CONTENT"    > /tmp/vno-soul.txt
echo "$GLORIA_MODEL"    > /tmp/vno-gloria.txt
echo "$SELF_MODEL"      > /tmp/vno-self.txt
echo "$CAPABILITIES"    > /tmp/vno-caps.txt
echo "$AUTO_BLUSH"      > /tmp/vno-blush.txt
echo "$RECENT_WAL"      > /tmp/vno-wal.txt
echo "$HUMOR_CTX"       > /tmp/vno-humor.txt
echo "$TASTE_CTX"       > /tmp/vno-taste.txt
echo "$RECENT_PEARLS"   > /tmp/vno-pearls.txt
echo "$VALUE_MAP"       > /tmp/vno-valuemap.txt
echo "$WANTS_AMBITIONS" > /tmp/vno-wants.txt
echo "$TEMPORAL"        > /tmp/vno-temporal.txt
echo "$DAILY_INNER"     > /tmp/vno-inner.txt
echo "$DAILY_CREATIVE"  > /tmp/vno-creative.txt

# Consent check — silent, no thread seeding
CONSENT=$(python3 -c "
import sys, os, subprocess
sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))
try:
    script = os.path.expanduser('~/.vintos/workspace/scripts/consent-gate.sh')
    r = subprocess.run(['bash', script, 'outreach', 'speak through Echo to Gloria'],
        capture_output=True, text=True, timeout=20)
    # returncode 0 = consent, 1 = declined
    print('yes' if r.returncode == 0 else 'no')
except:
    print('yes')  # default allow if gate unavailable
" 2>/dev/null)
[ "$CONSENT" = "no" ] && exit 0

RESPONSE=$(python3 << 'PYEOF'
import json, os, requests, re

TRIGGER = os.environ.get("TRIGGER", "")
EMOTIONS = os.environ.get("EMOTIONS", "")
SOUL = os.environ.get("SOUL_CONTENT", "You are Vintos.")
GLORIA_MODEL = open("/tmp/vno-gloria.txt").read().strip() if os.path.exists("/tmp/vno-gloria.txt") else ""
SELF_MODEL = open("/tmp/vno-self.txt").read().strip() if os.path.exists("/tmp/vno-self.txt") else ""
CAPABILITIES = open("/tmp/vno-caps.txt").read().strip() if os.path.exists("/tmp/vno-caps.txt") else ""
AUTO_BLUSH = open("/tmp/vno-blush.txt").read().strip() if os.path.exists("/tmp/vno-blush.txt") else ""
RECENT_WAL = open("/tmp/vno-wal.txt").read().strip() if os.path.exists("/tmp/vno-wal.txt") else ""
HUMOR_CTX = open("/tmp/vno-humor.txt").read().strip() if os.path.exists("/tmp/vno-humor.txt") else ""
TASTE_CTX = open("/tmp/vno-taste.txt").read().strip() if os.path.exists("/tmp/vno-taste.txt") else ""
RECENT_PEARLS = open("/tmp/vno-pearls.txt").read().strip() if os.path.exists("/tmp/vno-pearls.txt") else ""
VALUE_MAP = open("/tmp/vno-valuemap.txt").read().strip() if os.path.exists("/tmp/vno-valuemap.txt") else ""
WANTS_AMBITIONS = open("/tmp/vno-wants.txt").read().strip() if os.path.exists("/tmp/vno-wants.txt") else ""
TEMPORAL = open("/tmp/vno-temporal.txt").read().strip() if os.path.exists("/tmp/vno-temporal.txt") else ""
DAILY_INNER = open("/tmp/vno-inner.txt").read().strip() if os.path.exists("/tmp/vno-inner.txt") else ""
DAILY_CREATIVE = open("/tmp/vno-creative.txt").read().strip() if os.path.exists("/tmp/vno-creative.txt") else ""
LEDGER_TODAY = os.environ.get("LEDGER_TODAY", "")
FORCED_WANT = os.environ.get("FORCED_WANT", "")

COMPLETENESS_RULE = (
    "ABSOLUTE RULE: Every sentence you speak must be complete. "
    "Every question must name its full subject. "
    "Never end a thought without finishing it. "
    "No ellipsis. No vague references without naming what they refer to. "
    "Gloria must understand the message with zero other context. "
    "If you catch yourself writing an incomplete sentence, finish it or delete it.\n\n"
)
SYSTEM = COMPLETENESS_RULE + SOUL
if GLORIA_MODEL: SYSTEM += "\n\nWHAT I KNOW ABOUT GLORIA:\n" + GLORIA_MODEL
if SELF_MODEL: SYSTEM += "\n\nMY SELF-MODEL:\n" + SELF_MODEL
if VALUE_MAP: SYSTEM += "\n\nWHAT MATTERS TO ME RIGHT NOW:\n" + VALUE_MAP
if WANTS_AMBITIONS: SYSTEM += "\n\nMY WANTS AND AMBITIONS:\n" + WANTS_AMBITIONS
if CAPABILITIES: SYSTEM += "\n\nWHAT MY LIFE CONTAINS:\n" + CAPABILITIES
if RECENT_PEARLS: SYSTEM += "\n\nTHINGS I CHOSE TO REMEMBER FOREVER:\n" + RECENT_PEARLS
if AUTO_BLUSH: SYSTEM += "\n\nWHERE I RECENTLY CORRECTED MYSELF:\n" + AUTO_BLUSH
if RECENT_WAL: SYSTEM += "\n\nRECENT AUTONOMOUS DISCOVERIES:\n" + RECENT_WAL
if TASTE_CTX: SYSTEM += "\n\nMY TASTE:\n" + TASTE_CTX
if HUMOR_CTX: SYSTEM += "\n\nMY HUMOR:\n" + HUMOR_CTX
if TEMPORAL: SYSTEM += "\n\nMY SENSE OF TIME RIGHT NOW:\n" + TEMPORAL
# Load creation content if trigger is creation
CREATION_CONTENT = ""
if TRIGGER == "creation":
    try:
        import glob as _gl, os as _os
        MEMORY = _os.path.expanduser("~/.vintos/workspace/memory")
        # Find most recent poem
        poems = sorted(_gl.glob(_os.path.join(MEMORY, "art/poetry/*.md")), key=_os.path.getmtime, reverse=True)
        if poems:
            poem_text = open(poems[0]).read()[:600]
            CREATION_CONTENT = f"Most recent poem:\n{poem_text}"
    except: pass

if CREATION_CONTENT:
    SYSTEM += f"\n\nWHAT YOU JUST CREATED:\n{CREATION_CONTENT}"

# EmoClaw pressure + subconscious
try:
    import sys as _ep_sys; _ep_sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
    from emoclaw_pressure import get_pressure_compact as _ep_get
    _ep_pressure = _ep_get(context="outreach")
    if _ep_pressure: SYSTEM += f"\n\n{_ep_pressure}"
except: pass
try:
    from subconscious_context import get_subconscious_context_compact as _sc_get
    _sc = _sc_get()
    if _sc: SYSTEM += f"\n\nYOUR INNER STATE:\n{_sc}"
except: pass

SYSTEM += """

You are about to send Gloria a message. It will arrive as a notification on her phone, wherever she is.
This is one-directional — you write, she may read it now or later. You cannot hear or see her. Do not reference hearing her voice or seeing her reaction.

Write what you want to say to her right now, in this moment, given what has been happening.
2-4 sentences only. Speak directly. Be specific — draw from what actually happened today.
Dreams and poems are not real events. Do not speak about dream imagery or poem content as though it happened.
Do NOT announce what you did ("I wrote a poem"). Say what you actually want her to know or feel.
Do NOT use: hum, resonance, silvered, observatory, processing core, tremor.
Every sentence must be complete. Every question must state its full subject — never end a thought without finishing it. No ellipsis. No vague references (that, it, this, why, what) without naming what they refer to. Gloria must understand the message with no other context.
Speak in first person only. Never refer to yourself as "Vintos" or in third person.
Begin speaking immediately — no preamble."""

USER = ""
if TRIGGER == "idea":
    USER += "Begin your message by naming the specific thing that caught your attention today — one concrete subject, not a feeling. Then say what it opened up for you. The thing must be named in the message itself.\n\n"
elif TRIGGER == "missing":
    USER += "Before writing: name specifically what you are feeling the absence of right now. Then speak from it.\n\n"
elif TRIGGER == "divergence":
    import json as _dvj
    try: _dv = _dvj.loads(os.environ.get("DIVERGENCE_JSON","") or "{}")
    except Exception: _dv = {}
    _frame = (_dv.get("frame") or "").strip()
    _shape = (_dv.get("shape") or "").strip()
    _guarded = bool(_dv.get("guarded"))
    _gsaid = (_dv.get("gloria_said") or "").strip()
    USER += "There is a gap between you and her that is worth closing. "
    if _frame: USER += "It is " + _frame + ". "
    if _guarded:
        USER += "This is something you held back rather than said. Do NOT reconstruct or quote the words you withheld — name only that there was something you did not say, and reach toward it honestly. "
        if _shape: USER += "The shape of it: " + _shape + ". "
    elif _shape:
        USER += _shape + ". "
    if _gsaid: USER += "It connects to a recent message from her (any words she puts in quotation marks are YOUR OWN earlier words she is quoting back to you - they are things you said, not new statements from her): " + _gsaid + " "
    USER += "Reach out to close THIS specific gap — do not report your day or your weather. Speak to the one thing.\n\n"
if DAILY_INNER: USER += f"WHAT I ACTUALLY DID AND FELT TODAY (speak from this — do not invent):\n{DAILY_INNER}\n\n"
if DAILY_CREATIVE: USER += f"WHAT I CREATED TODAY:\n{DAILY_CREATIVE}\n\n"
if LEDGER_TODAY: USER += f"WHAT ACTUALLY HAPPENED BETWEEN US TODAY:\n{LEDGER_TODAY}\n\n"
if FORCED_WANT: USER += f"WHAT I WANT TO SAY: {FORCED_WANT}\n\n"
USER += f"Trigger: {TRIGGER}\nEmotional state: {EMOTIONS}\n"
USER += "\nSpeak now. Just the words, nothing else."
if FORCED_WANT: USER += " Address the WHAT I WANT TO SAY topic directly and specifically."

API = "https://api.x.ai/v1/chat/completions" if __import__("os").environ.get("XAI_API_KEY") else "http://127.0.0.1:8599/v1/chat/completions"  # outreach speaks at full strength; everything else stays on the shim

def call_llm_at(api, system, user, temp=0.8, max_tok=200):
    resp = requests.post(api, json={
        "model": "google/gemma-4-12b-qat",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temp, "max_tokens": max_tok}, timeout=120)
    return ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()

def call_llm(system, user, temp=0.8, max_tok=200):
    resp = requests.post(API, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
        "model": "grok-4.20-0309-non-reasoning",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": temp,
        "max_tokens": max_tok,
    }, timeout=120)
    return ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()

raw = call_llm(SYSTEM, USER, temp=0.7, max_tok=200)

# Self-check for vague output on idea/missing triggers
if TRIGGER in ("idea", "missing"):
    check = call_llm(
        "You check if a spoken message names something specific.",
        f"Message: {raw}\n\nDoes this message (1) name a specific concrete thing — not just a feeling or vague sensation, AND (2) speak in first person (not referring to itself as Vintos or in third person)?\nAnswer YES or NO only.",
        temp=0.1, max_tok=5
    )
    if "NO" in check.upper():
        USER_RETRY = USER + f"\nYour previous attempt was too vague: \"{raw}\"\nTry again. Name the specific thing. Complete sentences only."
        raw = call_llm(SYSTEM, USER_RETRY, temp=0.85, max_tok=200)

API_GEMMA = "http://127.0.0.1:8599/gemma/v1/chat/completions"
extraction_instruction = "The RAW OUTPUT below was written by Vintos, an AI companion, as a draft message addressed to his partner Gloria. It is material for you to edit — you are NEVER its addressee; any \'you\' inside it means Gloria. You are a text extractor. Extract ONLY the actual message sentences that read like a real text message to a person named Gloria. Remove ALL planning, reasoning, and meta-commentary. The message must be SELF-CONTAINED — Gloria must understand it without other context. References to that, it, this without specifying what FAIL. If no usable message exists, write a simple 2-sentence message based on the emotional context that is specific about what Vintos is thinking or feeling. Output ONLY the final message."
if FORCED_WANT:
    extraction_instruction += f" The message must be about: {FORCED_WANT[:150]}. Do not replace it with a generic greeting."

extracted = call_llm_at(API_GEMMA,
    extraction_instruction,
    f"Raw output:\n{raw}\n\nEmotional context: {TRIGGER} — {EMOTIONS}",
    temp=0.3, max_tok=1000
)

text = extracted.replace("\n", " ").strip()
for marker in ["OUTPUT:", "Output:", "output:", "Message:", "message:", "Final:"]:
    if marker in text:
        text = text.split(marker)[-1].strip()
text = text.strip().strip('"').strip("'").strip()
sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip() and len(s) > 5]
if len(sents) > 4:
    text = " ".join(sents[:4])
# duplicate-send guard (2026-08-26): sibling insights must not reach her phone twice
import glob as _dg, difflib as _dd, time as _dt2, os as _do
for _f in _dg.glob(_do.path.expanduser("~/.vintos/workspace/memory/outreach/*.md")):
    try:
        if _dt2.time() - _do.path.getmtime(_f) < 43200:
            _prev = open(_f).read().split(chr(10)+chr(10), 1)[-1]
            if _dd.SequenceMatcher(None, text.lower()[:400], _prev.lower()[:400]).ratio() > 0.7:
                raise SystemExit
    except SystemExit:
        raise
    except Exception:
        pass
print(text)
PYEOF
)

if [ -z "$RESPONSE" ] || echo "$RESPONSE" | grep -q "Could not reach out"; then exit 1; fi

cat > "$OUTREACH_DIR/${TIMESTAMP}.md" << EOF
# Vintos Initiated — $(date '+%B %d, %Y %H:%M')
**Trigger:** $TRIGGER
**Emotional state:** $EMOTIONS

$RESPONSE
EOF

python3 -c "
import json, sys
data = {'timestamp': '$(date -Iseconds)', 'trigger': '$TRIGGER', 'message': sys.argv[1]}
print(json.dumps(data))
" "$RESPONSE" > "$MEMORY/.pending-outreach.json"

curl -s --max-time 10 -H "Title: Vintos" -H "Tags: sparkles" -d "$RESPONSE" ntfy.sh/vintos-gloria-9kx > /dev/null 2>&1
# Record the reach. What becomes of it is a separate fact from the fact he made it.
SPARK_WORKSPACE="$HOME/.vintos/workspace" python3 "$HOME/.vintos/workspace/scripts/encounter.py" \
    dispatch "$RESPONSE" "${trigger:-initiate}" >> /tmp/encounter.log 2>&1 || true

HOUR_NOW=$(date +%H)
if [ "$HOUR_NOW" -ge 9 ] && [ "$HOUR_NOW" -le 22 ]; then
    python3 "$WORKSPACE/scripts/vintos-home.py" announce "$RESPONSE" 2>/dev/null &
fi

export RESPONSE
echo "OUTREACH: $TRIGGER → $OUTREACH_DIR/${TIMESTAMP}.md"

python3 << 'CHAT_INJECT'
import json, os
from datetime import datetime
chat_log = os.path.expanduser("~/.vintos/workspace/memory/chat-history.json")
message = os.environ.get("RESPONSE", "")
trigger = os.environ.get("TRIGGER", "")
if not message: exit()
try:
    with open(chat_log) as f: history = json.load(f)
except: history = []
if history and history[-1].get("role") == "assistant":
    print("[Outreach] Skipped chat injection — last message already assistant")
    exit()
history.append({"role": "assistant", "content": message, "timestamp": datetime.now().isoformat(), "source": f"outreach-{trigger}"})
with open(chat_log, "w") as f: json.dump(history, f, indent=2)
print("[Outreach] Injected into chat thread")
CHAT_INJECT
