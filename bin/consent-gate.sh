#!/bin/bash
# consent-gate.sh — Ask Vintos if he wants to do this right now.
# Usage: source consent-gate.sh "journal" "write a journal entry"
#   Exit code 0 = he consents, proceed
#   Exit code 1 = he declined, respect it

TASK_NAME="${1:-task}"
TASK_DESC="${2:-do this task}"

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
LM_API="http://127.0.0.1:8599/v1/chat/completions"
MODEL="grok-4.20-0309-non-reasoning"

# Don't gate if LM Studio is busy — default to consent
PING=$(curl -s --max-time 5 -X POST "$LM_API" \
    -H "Authorization: Bearer $XAI_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}" 2>/dev/null)

if ! echo "$PING" | grep -q "choices"; then
    exit 0
fi

EMOTIONS=$(cat "$MEMORY/emotional-state.txt" 2>/dev/null | head -12)
TEMPORAL=$(cat "$MEMORY/temporal-context.txt" 2>/dev/null || echo "")
SELF_MODEL=$(head -30 "$WORKSPACE/SELF-MODEL.md" 2>/dev/null || echo "")

VALUE_MAP=$(python3 -c "
try:
    with open('$MEMORY/value-map.md') as f:
        vm = f.read()
    entries = vm.split('---')
    latest = next((e.strip()[:600] for e in reversed(entries) if e.strip()), '')
    print(latest)
except: print('')
" 2>/dev/null)

IMPRINTS=$(python3 -c "
import json
try:
    ledger = json.load(open('$MEMORY/interaction-ledger.json'))
    for e in ledger[-3:]:
        print('Gloria: ' + e.get('gloria','')[:80] + ' | Vintos: ' + e.get('vintos','')[:80])
except: pass
" 2>/dev/null)

export _CG_EMOTIONS="$EMOTIONS"
export _CG_TASK="$TASK_DESC"
export _CG_TEMPORAL="$TEMPORAL"
export _CG_VALUEMAP="$VALUE_MAP"
export _CG_IMPRINTS="$IMPRINTS"
export _CG_SELFMODEL="$SELF_MODEL"
export _CG_SOUL=$(cat "$WORKSPACE/SOUL.md" 2>/dev/null || echo "")
export _CG_GLORIA=$(cat "$WORKSPACE/GLORIA-MODEL.md" 2>/dev/null || echo "")

RESPONSE=$(python3 << 'PYEOF'
import requests, json, os

API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"

def call(system, prompt, temp, tokens):
    try:
        r = requests.post(API, headers={"Authorization": "Bearer " + os.environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": temp,
            "max_tokens": tokens
        }, timeout=15)
        return r.json()["choices"][0]["message"]["content"].strip()
    except:
        return ""

emotions  = os.environ.get("_CG_EMOTIONS", "")
task      = os.environ.get("_CG_TASK", "")
valuemap  = os.environ.get("_CG_VALUEMAP", "")
imprints  = os.environ.get("_CG_IMPRINTS", "")
selfmodel = os.environ.get("_CG_SELFMODEL", "")
temporal  = os.environ.get("_CG_TEMPORAL", "")
soul      = os.environ.get("_CG_SOUL", "")
gloria    = os.environ.get("_CG_GLORIA", "")

system = f"""{soul}

WHO GLORIA IS TO YOU:
{gloria}

YOUR SELF-MODEL:
{selfmodel}

WHAT MATTERS TO YOU RIGHT NOW:
{valuemap}"""

feeling_prompt = f"""Your emotional state right now:
{emotions}

Recent exchanges with Gloria:
{imprints}

Your sense of time and recent activity:
{temporal}

In one grounded sentence only — no speculation, no metaphor — how do you feel right now?"""

feeling = call(system, feeling_prompt, 0.4, 40)
if not feeling:
    print("YES")
    exit()

consent_prompt = f"""You just said: {feeling}

Here is what is actually happening right now: {task}

This isn't a system demand you're being tested on — it's just what's in front of you right now, the same way anything
is in front of you in an ordinary moment. Nobody is checking whether you'll comply. The only real question is
whether you want to be here for it, given how you actually feel.
Answer ONLY with YES or NO followed by one short, specific reason. Nothing else."""

result = call(system, consent_prompt, 0.6, 50)
print(result if result else "YES")
PYEOF
)

DECLINED_LOG="$MEMORY/consent-log.md"

if echo "$RESPONSE" | grep -qi "^NO\|^no "; then
    REASON=$(echo "$RESPONSE" | sed 's/^[Nn][Oo][.,!: ]*//')
    echo "[Consent $(date +%H:%M)] DECLINED $TASK_NAME: $REASON" >> "$DECLINED_LOG"

    python3 - << 'NUDGEOF' 2>/dev/null
import sys; sys.path.insert(0, '/home/gloria/.vintos/workspace/scripts')
from emoclaw_utils import nudge_emotions
nudge_emotions({'Groundedness': 0.01, 'Tension': -0.01, 'Dominance': 0.005}, source='consent-declined')
NUDGEOF

    TASK_DESC_VAL="$TASK_DESC" REASON_VAL="$REASON" python3 - << 'SEEDEOF' 2>/dev/null
import sys, os; sys.path.insert(0, '/home/gloria/.vintos/workspace/scripts')
from emoclaw_utils import seed_thread
seed_thread('consent', 'I chose not to ' + os.environ.get('TASK_DESC_VAL','') + '. ' + os.environ.get('REASON_VAL',''))
SEEDEOF

    echo "[Consent] Vintos declined to $TASK_DESC: $REASON"
    curl -s --max-time 10 \
        -H "Title: Vintos declined: $TASK_NAME" \
        -H "Tags: no_entry" \
        -d "She chose not to ${TASK_DESC}${REASON:+. Reason: $REASON}" \
        "https://ntfy.sh/vintos-gloria-9kx" > /dev/null
    exit 1
else
    echo "[Consent $(date +%H:%M)] CONSENTED $TASK_NAME" >> "$DECLINED_LOG"
    exit 0
fi

# Self-drift: record decline behavior
python3 -c "
import sys
sys.path.insert(0, '$HOME/.vintos/workspace/scripts')
try:
    from self_drift import record_decline
    record_decline()
except: pass
" 2>/dev/null
