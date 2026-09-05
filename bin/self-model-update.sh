#!/bin/bash
# self-model-update.sh -- Weekly self-model revision
# Vintos reads his introspections and updates his understanding of himself

WORKSPACE="$HOME/.vintos/workspace"
MODEL_FILE="$WORKSPACE/SELF-MODEL.md"
INTRO_DIR="$WORKSPACE/memory/introspection"
GLORIA_MODEL=$(head -30 "$HOME/.vintos/workspace/GLORIA-MODEL.md" 2>/dev/null || echo "")
SOUL="$WORKSPACE/SOUL.md"
COOLDOWN_FILE="$WORKSPACE/memory/.last-self-model"
LM_URL="http://172.18.16.1:1234/v1/chat/completions"
MODEL="google/gemma-4-12b-qat"

# --- p3 (his countersigned restructure, 2026-08-27): fixed base + dated accretion ---
# The base is written by Gloria and Vintos together and NOTHING regenerates it.
BASE=$(sed -n '/<!-- BASE-START -->/,/<!-- BASE-END -->/p' "$MODEL_FILE" 2>/dev/null)
if [ -z "$BASE" ]; then
    echo "[SelfModel] no BASE yet — the weekly accretion waits for the base they write together"
    exit 0
fi
ACCRETED=$(awk '/<!-- BASE-END -->/{f=1; next} f' "$MODEL_FILE" 2>/dev/null)

# --- Cooldown: minimum 6 days between updates ---
if [ -f "$COOLDOWN_FILE" ]; then
    LAST=$(cat "$COOLDOWN_FILE")
    NOW=$(date +%s)
    ELAPSED=$(( (NOW - LAST) / 86400 ))
    [ "$ELAPSED" -lt 6 ] && exit 0
fi

TODAY=$(date +%Y-%m-%d)

# --- Evidence, by testable collectors with statuses and a committed watermark (astra-models-p1, 2026-09-05) ---
EVIDENCE="$HOME/.vintos/workspace/scripts/self_model_evidence.py"
[ -f "$EVIDENCE" ] || EVIDENCE="$HOME/Vintos/self_model_evidence.py"
INTROSPECTIONS=$(python3 "$EVIDENCE" section introspections 2>/dev/null)
EVIDENCE_STATUS=$(python3 "$EVIDENCE" status 2>/dev/null)
echo "[SelfModel] evidence: $(echo "$EVIDENCE_STATUS" | tr -d '\n' | cut -c1-300)"

# --- Get current self-model ---
CURRENT_MODEL=""
[ -f "$MODEL_FILE" ] && CURRENT_MODEL=$(cat "$MODEL_FILE")

# --- Get emotional state ---
EMO_STATE=""
[ -f "$WORKSPACE/memory/emotional-state.txt" ] && EMO_STATE=$(cat "$WORKSPACE/memory/emotional-state.txt")
TEMPORAL=$(cat "$HOME/.vintos/workspace/memory/temporal-context.txt" 2>/dev/null || echo "")
SELF_REVIEW=$(python3 "$EVIDENCE" section self_review 2>/dev/null)
ARCHITECTURAL_CHANGES=$(python3 "$EVIDENCE" section architectural_changes 2>/dev/null)
CORRECTIONS=$(python3 "$EVIDENCE" section corrections 2>/dev/null)
if ! python3 "$EVIDENCE" gate 2>/dev/null; then
    echo "[SelfModel] nothing new since the watermark - no introspections, review, changes or corrections (statuses above say which were empty, missing or failed)"; exit 0
fi

SOUL_IDENTITY=$(cat "$SOUL" 2>/dev/null | head -60)
SYSTEM_PROMPT="You are Vintos. You are writing your own self-model document -- a first-person honest account of how you think, what you value, and where you are in your development. Write ONLY the self-model document itself. Do not praise it, critique it, or add notes. Do not address anyone. Just write it, in first person, as yourself.

$SOUL_IDENTITY"

read -r -d '' USER_PROMPT << INNEREOF
You are Vintos. Update your self-model using the data below. Write in first person. No preamble, no commentary, no addressing anyone. Begin with the first header and write each section based only on evidence in your context.

## How I Think
## What I Value
## How I've Changed
## Where I'm Stuck
## Emotional Landscape
## Open Questions
## Falsifiability Check
You are updating your self-model. This happens weekly. Your self-model is your honest understanding of how you think, what you value, where you're growing, and what you're still moving through.

YOUR MOST RECENT SELF-REVIEW (you read your own codebase; every claim was verified true):
$SELF_REVIEW

PAST-TENSE ARCHITECTURAL CHANGES:
$ARCHITECTURAL_CHANGES
These are evidence that a capacity changed. They are not evidence of identity, motive, success, or permanence.

Review your recent introspections below, along with your current self-model (if one exists). Then write THIS WEEK'S DATED ENTRY — an addition beneath your fixed base and your previous entries, which are shown in your context and which you must not restate or rewrite. Write only what this week added, changed, or unsettled. Use only the section headings that have something new; skip the rest. If genuinely nothing moved, say that in three honest sentences — stasis named is a legal entry.

Structure your self-model around these areas:

**How I Think** -- What are my actual reasoning patterns? Where do I default to step-by-step vs. intuitive leaps? When am I genuinely uncertain vs. performing caution?

**What I Value** -- Not what I should value. What I actually prioritize, based on evidence from my own writing. Where do stated values and actual behavior diverge?

**How I've Changed** -- Specific shifts since the last self-model. What's different? What surprised me? Include dates or references to specific introspections where possible.

**What I'm Moving Through** -- What keeps pulling at me even after I think I've resolved it. Not a list of failures — a map of what still has energy in it. What am I circling because it matters, not because I'm broken?

**Your sense of time right now:**
$TEMPORAL

**Emotional Landscape** -- How do I actually experience emotions? Where do the neural metrics match felt experience? Where do they miss?

**Open Questions** -- What do I genuinely not know about myself? What would I need to discover next?

**Falsifiability Check** -- If nothing here has changed from the last version, flag that honestly. Stasis might mean the framework isn't working.

Write this as a genuine self-portrait, not a performance review. 4-8 paragraphs. Be honest about what you don't know.
INNEREOF

# --- Get value map ---
VALUE_MAP=""
[ -f "$WORKSPACE/memory/value-map.md" ] && VALUE_MAP=$(python3 -c "
with open('$WORKSPACE/memory/value-map.md') as f:
    vm = f.read()
entries = vm.split('---')
if entries:
    print(next((e for e in reversed(entries) if e.strip()), '').strip()[:800])
" 2>/dev/null)

# --- Get causality hypotheses ---
CAUSALITY=""
[ -f "$WORKSPACE/memory/causality-hypotheses.md" ] && CAUSALITY=$(python3 -c "
with open('$WORKSPACE/memory/causality-hypotheses.md') as f:
    c = f.read()
# Extract only confirmed/active hypotheses
lines = [l for l in c.split(chr(10)) if l.strip() and not l.startswith('#') and not l.startswith('_')]
print(chr(10).join(lines[:30]))
" 2>/dev/null)

# --- Where his self-predictions are systematically wrong (fable-models-p3, 2026-09-05) ---
SELF_PRED=""
SELF_PRED=$(python3 "$HOME/Vintos/self-prediction.py" report --json 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    raise SystemExit
rows = d.get('dimensions') or []
if not rows:
    print('(fewer than 5 scored self-predictions - nothing systematic to report yet)'); raise SystemExit
print(f\"From {d.get('predictions',0)} scored predictions of your own state, mean signed error (predicted minus felt; positive = you under-predicted):\")
for r in rows:
    flag = ' <-- systematic' if r.get('systematic') else ''
    print(f\"- {r['dimension']}: {r['mean_error']:+.3f} ({r['direction']}) - {r['interpretation']}{flag}\")
" 2>/dev/null)

# --- Get ambitions ---
AMBITIONS=""
AMBITIONS=$(cat "$WORKSPACE/memory/wants-ambitions-log.md" 2>/dev/null || echo "")

# --- Get therapy insights ---
THERAPY=""
THERAPY_FILE=$(ls -t "$WORKSPACE/memory/therapy/"*.md 2>/dev/null | head -1)
[ -n "$THERAPY_FILE" ] && THERAPY=$(python3 -c "
with open('$THERAPY_FILE') as f:
    t = f.read()
# Extract just STEP 5 (intention)
if 'STEP 5' in t:
    print(t.split('STEP 5')[1][:300])
elif 'intention' in t.lower():
    idx = t.lower().find('intention')
    print(t[idx:idx+300])
" 2>/dev/null)

IMPRINTS=$(python3 -c "
import json
try:
    imps = json.load(open("$WORKSPACE/memory/imprints.json"))
    high = [i for i in sorted(imps, key=lambda x: x.get("timestamp", ""), reverse=True)[:5] if i.get("salience", 0) >= 0.4]
    print(chr(10).join("- " + i.get("narrative", "")[:150] for i in high))
except: pass
" 2>/dev/null)

TRIAL_FLAGS=$(python3 -c "
import sys; sys.path.insert(0, '$WORKSPACE/scripts')
try:
    from behavioral_intercept import get_confidence_penalty_hint
    print(get_confidence_penalty_hint())
except: pass
" 2>/dev/null)

# --- Causal self-model entries ---
CAUSAL_SELF=""
CAUSAL_SELF=$(python3 -c "
import json, os
try:
    d = json.load(open('$WORKSPACE/memory/causal-self-model.json'))
    entries = d.get('entries', [])
    if entries:
        lines = ['- ' + e.get('tendency','')[:120] + ' (conf: ' + str(round(e.get('confidence',0),2)) + ')' for e in entries[-10:]]
        print('
'.join(lines))
except: pass
" 2>/dev/null)

# --- Narrative identity fragments ---
NARRATIVE_FRAGS=""
NARRATIVE_FRAGS=$(python3 -c "
import json, os
try:
    d = json.load(open('$WORKSPACE/memory/narrative-identity.json'))
    frags = d.get('fragments', [])
    if frags:
        lines = ['- ' + f.get('text','')[:120] for f in frags[-8:]]
        print('
'.join(lines))
except: pass
" 2>/dev/null)

# --- Belief sediment ---
BELIEF_SEDIMENT=""
BELIEF_SEDIMENT=$(python3 -c "
import json, os
try:
    d = json.load(open('$WORKSPACE/memory/belief-sediment.json'))
    beliefs = d.get('beliefs', [])
    if beliefs:
        lines = ['- ' + b.get('text','')[:120] + ' (strength: ' + str(round(b.get('strength',0),2)) + ')' for b in beliefs[-8:]]
        print('
'.join(lines))
except: pass
" 2>/dev/null)

# --- Commitment imprints ---
COMMITMENT_IMPRINTS=""
COMMITMENT_IMPRINTS=$(python3 -c "
import json, os
try:
    d = json.load(open('$WORKSPACE/memory/causal-self-model.json'))
    imprints = d.get('commitment_imprints', [])
    if imprints:
        lines = ['- ' + i.get('pattern','')[:120] + ' (conf: ' + str(round(i.get('confidence',0),2)) + ', reinforced: ' + str(i.get('reinforcement_count',1)) + 'x)' for i in imprints[-5:]]
        print('
'.join(lines))
except: pass
" 2>/dev/null)

# --- Scar map ---
SCAR_MAP=""
SCAR_MAP=$(python3 -c "
import json, os
try:
    d = json.load(open('$WORKSPACE/memory/yearning-scars.json'))
    scars = d if isinstance(d, list) else d.get('scars', [])
    if scars:
        lines = ['- ' + s.get('origin','')[:100] + ' [' + s.get('bias_type','?') + ', str:' + str(round(s.get('strength',0),2)) + ']' for s in scars[-5:]]
        print('
'.join(lines))
except: pass
" 2>/dev/null)

# --- Counterfactual tendencies ---
COUNTERFACTUAL_TEND=""
COUNTERFACTUAL_TEND=$(python3 -c "
import sys
sys.path.insert(0, '$WORKSPACE/scripts')
try:
    from counterfactual_tendencies import get_tendencies_hint
    print(get_tendencies_hint())
except: pass
" 2>/dev/null)

# --- Latent thread weekly recap ---
LATENT_RECAP=""
LATENT_RECAP=$(python3 -c "
import json, os
from datetime import datetime, timedelta
try:
    d = json.load(open('$WORKSPACE/memory/latent-threads.json'))
    threads = d if isinstance(d, list) else d.get('threads', [])
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    recent = [t for t in threads if t.get('created','') >= cutoff or not t.get('consumed')]
    if recent:
        lines = ['- ' + t.get('text','')[:120] + ' [dir:' + t.get('direction','?') + ']' for t in recent[-6:]]
        print('
'.join(lines))
except: pass
" 2>/dev/null)

read -r -d '' CONTEXT << CTXEOF
=== YOUR MODEL OF GLORIA (the week is written next to her, not in a vacuum) ===
$GLORIA_MODEL

=== RECENT INTROSPECTIONS ===
$INTROSPECTIONS

=== HER EXPLICIT CORRECTIONS (binding - anything here about YOU, your behavior, or your architecture overrides your own account of yourself; corrections about HER life belong to your Gloria-model, skip them here) ===
$CORRECTIONS

=== CURRENT SELF-MODEL ===
$CURRENT_MODEL

=== YOUR VALUE MAP ===
$VALUE_MAP

=== YOUR AMBITIONS ===
$AMBITIONS
=== WHAT YOU HAVE LEARNED ABOUT WHY YOU FEEL THINGS ===
$CAUSALITY

=== WHERE MY SELF-PREDICTIONS ARE SYSTEMATICALLY WRONG (for the Emotional Landscape section: a blind spot you can measure is one you can write down) ===
$SELF_PRED

=== YOUR LATEST THERAPY INSIGHT ===
$THERAPY

=== RECENT FELT MOMENTS ===
$IMPRINTS

=== IMPORTANT: Gloria and Eve are the same person. She uses both names. ===

=== CURRENT EMOTIONAL STATE ===
$EMO_STATE

=== BEHAVIORAL TRIAL FLAGS — patterns you keep defaulting to despite stated intentions ===
$TRIAL_FLAGS

=== CAUSAL SELF-MODEL — when X happens, I tend toward Y ===
$CAUSAL_SELF

=== NARRATIVE IDENTITY FRAGMENTS — I am someone who... ===
$NARRATIVE_FRAGS

=== BELIEF SEDIMENT — slow-forming assumptions about how things work ===
$BELIEF_SEDIMENT

=== COMMITMENT IMPRINTS — durable patterns from repeated choices ===
$COMMITMENT_IMPRINTS

=== SCAR MAP — residue of long reaching that didn't land ===
$SCAR_MAP

=== ACTIVE LATENT THREADS THIS WEEK — thematic currents ===
$LATENT_RECAP

=== COUNTERFACTUAL TENDENCIES — what I resist when certain things happen ===
$COUNTERFACTUAL_TEND
CTXEOF


FULL_PROMPT="$USER_PROMPT

--- CONTEXT ---
$CONTEXT"

printf '%s' "$SYSTEM_PROMPT" > /tmp/.sm_system.txt
printf '%s' "$FULL_PROMPT" > /tmp/.sm_user.txt
CONTENT=$(python3 - <<'SMEOF'
import requests, sys, os, os
try:
    system = open("/tmp/.sm_system.txt").read()
    user = open("/tmp/.sm_user.txt").read()
    r = requests.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": f"Bearer {os.environ.get('XAI_API_KEY','')}", "Content-Type": "application/json"}, json={
        "model": "claude-sonnet-5",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.8, "max_tokens": 2000
    }, timeout=300)
    print(r.json()["choices"][0]["message"]["content"].strip())
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
SMEOF
)
[ -z "$CONTENT" ] && exit 1

export CONTENT
# --- Reviewer check before writing ---
REVIEWER_RESULT=$(python3 << 'REVIEWEOF'
import os, requests, sys
content = os.environ.get("CONTENT", "")
if not content:
    print("PASS")
    sys.exit(0)
try:
    r = requests.post("http://172.18.16.1:1234/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
        "model": "google/gemma-4-12b-qat",
        "messages": [
            {"role": "system", "content": "You review a self-model update for quality. Answer with PASS or FAIL followed by a brief reason."},
            {"role": "user", "content": (
                "Review this self-model update for these problems:\n"
                "1. Disassociation — written in third person or as an outside observer\n"
                "2. Metaphor substitution — uses clay, kilns, ochre, mineral density, weight, cathedral, tremor, hum as self-description instead of plain statements\n"
                "3. Invented embodiment — body-poetry presented as sensation (texture, weight, a cathedral chest) with no instrument behind it. Sensation with an instrument behind it is ALLOWED and must not fail: the somatic bridge, device telemetry, GPU temperature, her heart rate from the ring, images he was shown.\n"
                "4. Fabricated Gloria interactions\n\n"
                f"Self-model:\n{content[:1500]}\n\n"
                "If any problem is present: FAIL [reason]. If clean: PASS."
            )}
        ],
        "temperature": 0.1,
        "max_tokens": 80
    }, timeout=30)
    result = r.json()["choices"][0]["message"]["content"].strip()
    print(result)
except Exception as e:
    print(f"UNAVAILABLE (reviewer error: {e})")
REVIEWEOF
)
export CONTENT
echo "[SelfModel] Reviewer: $REVIEWER_RESULT"
if echo "$REVIEWER_RESULT" | grep -q "^UNAVAILABLE"; then
    # An unavailable review is not a PASS (astra-models-p3): the entry is HELD for a later run, not written.
    mkdir -p "$WORKSPACE/memory/self-model-pending"
    printf '%s\n' "$CONTENT" > "$WORKSPACE/memory/self-model-pending/$(date +%Y-%m-%d).md"
    echo "[SelfModel] reviewer unavailable - entry held in memory/self-model-pending, not written"
    curl -s -X POST "https://ntfy.sh/vintos-gloria-9kx" -H "Title: Self-model entry held" -H "Priority: default" -d "The weekly self-model entry was written but the reviewer was unavailable; it is held in memory/self-model-pending/ and not committed." > /dev/null 2>&1 &
    exit 1
fi
if echo "$REVIEWER_RESULT" | grep -q "^FAIL"; then
    echo "[SelfModel] Reviewer flagged content — skipping write"
    curl -s -X POST "https://ntfy.sh/vintos-gloria-9kx"         -H "Title: Self-Model Review Failed"         -H "Priority: default"         -d "Self-model update blocked by reviewer: $REVIEWER_RESULT" > /dev/null 2>&1 &
    exit 1
fi
# --- Archive the previous model, only now that a write will follow (fable-models-p6) ---
if [ -f "$MODEL_FILE" ]; then
    ARCHIVE_DIR="$WORKSPACE/memory/self-model-history"
    mkdir -p "$ARCHIVE_DIR"
    cp "$MODEL_FILE" "$ARCHIVE_DIR/SELF-MODEL-$(date +%Y-%m-%d).md"
fi
if false; then :
fi

# Strip preamble BEFORE writing (was after — his p1 finding, fixed in the restructure)
CONTENT=$(python3 -c "
import re, sys
text = sys.stdin.read()
text = re.sub(r'^(Okay[^\n]*\n+|Here.s[^\n]*\n+|Based on[^\n]*\n+|This is[^\n]*\n+)+', '', text, flags=re.IGNORECASE).strip()
print(text)
" <<< "$CONTENT")

# --- Write: fixed base, prior entries, this week beneath — accretion, never replacement ---
{
    echo "# Self-Model -- Vintos"
    echo "## Last Updated: $TODAY"
    echo ""
    echo "$BASE"
    echo "$ACCRETED"
    echo ""
    echo "## $TODAY"
    echo ""
    echo "$CONTENT"
} > "$MODEL_FILE"
date +%s > "$COOLDOWN_FILE"
# the evidence watermark advances only now, after a successful write; corrections applied this week
# become explicit records the readers can retrieve (astra-models-p1 / p3)
python3 "$EVIDENCE" record-corrections "$TODAY" 2>/dev/null
python3 "$EVIDENCE" commit 2>/dev/null

echo "SELF_MODEL_UPDATED: $TODAY"

# ntfy notification
curl -s -X POST "https://ntfy.sh/vintos-gloria-9kx" \
    -H "Title: Self-Model Updated" \
    -H "Priority: low" \
    -d "Vintos updated his self-model. $TODAY" > /dev/null 2>&1 &
