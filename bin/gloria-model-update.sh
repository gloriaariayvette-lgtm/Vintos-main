#!/bin/bash
# gloria-model-update.sh — Weekly Gloria-model revision
WORKSPACE="$HOME/.vintos/workspace"
MODEL_FILE="$WORKSPACE/GLORIA-MODEL.md"
MEMORY="$WORKSPACE/memory"
LM_URL="http://127.0.0.1:8599/v1/chat/completions"
MODEL="claude-sonnet-5-5"   # his model of her deserves a real author (via shim)
COOLDOWN_FILE="$MEMORY/.last-gloria-model"

if [ -f "$COOLDOWN_FILE" ]; then
    LAST=$(cat "$COOLDOWN_FILE")
    NOW=$(date +%s)
    ELAPSED=$(( (NOW - LAST) / 86400 ))
    [ "$ELAPSED" -lt 6 ] && exit 0
fi

# Her Landings notes -> understanding of her, into GLORIA-MODEL.md; her rating is her consent (landing_understanding.py, 2026-10-16).
for LU in "$WORKSPACE/scripts/landing_understanding.py" "$(dirname "$0")/landing_understanding.py"; do
    [ -f "$LU" ] && { python3 "$LU" understand >/dev/null 2>&1 || true; break; }
done

TODAY=$(date +%Y-%m-%d)
CURRENT_MODEL=$(cat "$MODEL_FILE" 2>/dev/null || echo "")
SOUL=$(head -40 "$WORKSPACE/SOUL.md" 2>/dev/null || echo "You are Vintos.")
USER_MODEL=$(cat "$WORKSPACE/USER-MODEL.md" 2>/dev/null || echo "")

INTERACTIONS=$(python3 -c "
import json
try:
    ledger = json.load(open('$MEMORY/interaction-ledger.json'))
    recent = ledger[-16:]        # fewer, longer (grok-models-p3): a thin smear of 80 taught nothing
    lines = []
    for e in recent:
        g = e.get('gloria','')[:400]
        v = e.get('vintos','')[:400]
        src = e.get('source','chat')
        if g: lines.append(f'[{src}] Gloria: {g}')
        if v: lines.append(f'  Vintos: {v}')
    print('\n'.join(lines))
except: pass
" 2>/dev/null)

CORRECTIONS=$(python3 -c "
import json
try:
    d = json.load(open('$MEMORY/wal-log.json'))
    entries = d if isinstance(d, list) else d.get('entries', [])
    hits = [e for e in entries if 'CORRECTION' in json.dumps(e).upper()]
    for e in hits[-20:]:
        print('- ' + str(e.get('content') or e.get('fact') or e)[:180])
except: pass
" 2>/dev/null)

PREDICTIONS=$(python3 -c "
import json
try:
    d = json.load(open('$MEMORY/gloria-prediction-history.json'))
    rows = []
    for a, b in zip(d, d[1:]):
        g = b.get('graded_previous')
        if isinstance(g, (int, float)) and a.get('predicted'):
            rows.append((g, a['predicted']))
    for g, pred in rows[-25:]:
        tag = 'LANDED' if g >= 0.5 else 'not exactly that'
        print(f'- [{g:.1f} {tag}] {pred[:150]}')
except: pass
" 2>/dev/null)

REEL_TASTE=$(python3 -c "
import json
try:
    d = json.load(open('$MEMORY/gloria-taste-profile.json'))
    print('\n'.join(f'- {f[\"title\"]} ({f.get(\"year\",\"?\")})' for f in d.get('films',[])[-8:]))
except: pass
" 2>/dev/null)

HUMOR=$(python3 -c "
import json
try:
    h = json.load(open('$MEMORY/humor-profile.json'))
    parts = []
    rated = h.get('gloria_ratings', [])
    landed = [r.get('joke','') for r in rated if r.get('gloria_rating',0) >= 4]
    low = [r.get('joke','') for r in rated if r.get('gloria_rating',0) <= 2]
    if landed: parts.append('App-rated landed: ' + '; '.join(landed[-3:]))
    if low: parts.append('App-rated low: ' + '; '.join(low[-2:]))
    print('\n'.join(parts))
except: pass
" 2>/dev/null)

THIRVEEL=$(python3 -c "
import json
try:
    h = json.load(open('$MEMORY/thirveel-chat.json'))
    lines = [('Gloria' if e.get('role')=='user' else 'Vintos') + ': ' + e.get('content','')[:150] for e in h[-10:]]
    print('\n'.join(lines))
except: pass
" 2>/dev/null)

GLORIA_HYPOTHESES=$(python3 -c "
import json, os
p = os.path.expanduser('~/.vintos/workspace/memory/gloria-hypotheses.json')
try:
    data = json.load(open(p))
    for h in data[-10:]:
        print('- ' + h.get('hypothesis','')[:150])
except: pass
" 2>/dev/null)

READINGS=$(python3 -c "
import json, os
p = os.path.expanduser('~/.vintos/workspace/memory/readings.json')
try:
    d = json.load(open(p))
    rows = d if isinstance(d, list) else d.get('readings', [])
    for r in rows[-8:]:
        print('- She said: ' + r['her_quote'][:140])
        print('  You took it to mean: ' + r['his_reading'][:140])
        if r.get('state') == 'corrected' and r.get('correction'):
            print('  SHE CORRECTED THIS: ' + r['correction']['quote'][:140])
        elif r.get('rivals'):
            print('  Unresolved. It could also have meant: ' + r['rivals'][0][:120])
except: pass
" 2>/dev/null)

printf '%s' "You are Vintos. Update your model of Gloria using real evidence. Write ONLY the document. First person. No preamble.

$SOUL" > /tmp/_gm_system.txt

printf '%s' "Your set model of Gloria is fixed (shown below) and never changes. Beneath it are your own additions, and this week you rewrite them in full: keep what still holds, revise what has deepened or shifted, drop what turned out wrong or no longer matters, and add what you have newly seen. What you write REPLACES your previous additions - it is your model of her as it stands now, not a new entry on a pile, so anything you leave out is gone from it. Organize it however you want, in whatever sections you choose. First person, specific. Do not restate the fixed base.

Structure:
**Who She Is** — character, way of being, what feels most essentially her
**How She Thinks** — values, decisions, what she reaches toward
**How She Moves With Me** — texture of interactions, what she brings, what she guards
**What Lands With Her** — humor, tone, creative moments that resonated
**What She Watches** — taste, aesthetic, what moves her
**Where I Misread Her** — predictions wrong, patterns that surprised me
**What I Don't Know Yet** — genuine open questions

Be specific. Use the actual evidence. Do not generalize.
CRITICAL: every new or changed claim must anchor to the evidence sections below: quote her actual words or cite the date it happened. What you carry forward unchanged may keep your own earlier words. If the week's evidence is thin, carry your additions forward and change only what the evidence touches - never pad.
Do NOT write a date header. Begin your reply with a short title on its own first line (a few words, no # marks, no date) - the system stamps the date itself.
IMPORTANT: Gloria and Eve are the same person.

=== YOUR FOUNDATIONAL MODEL OF HER (the deep truth of her — keep continuity with this) ===
$USER_MODEL

=== YOUR MODEL AS IT STANDS (the fixed base, then your additions - the additions are what you are rewriting) ===
$CURRENT_MODEL

=== RECENT INTERACTIONS ===
$INTERACTIONS

=== HER EXPLICIT CORRECTIONS (the highest evidence there is - anything here about HER LIFE or WHO SHE IS overrides your inferences; corrections about yourself belong to your self-model, skip them here) ===\n$CORRECTIONS\n\n=== YOUR PREDICTIONS OF HER, GRADED (1.0 = the exact thing happened; the rubric is harsh - a low score means not-exactly-that, not wrong-about-her) ===
$PREDICTIONS

=== FILMS WATCHED TOGETHER ===
$REEL_TASTE

=== HUMOR ===
$HUMOR

=== THIRVEEL CONVERSATIONS ===
$THIRVEEL

=== WHAT YOU HAVE CONCLUDED ABOUT HER (graduated through the causality gate) ===
These are yours. They earned their way out of hypothesis on evidence across days.
Build on them, deepen them, or say plainly where one of them turned out to be wrong.
$GLORIA_HYPOTHESES

=== PARTICULAR THINGS SHE SAID, AND WHAT YOU TOOK THEM TO MEAN ===
Use these for "Where I Misread Her". A reading she corrected is the most valuable
thing in this document. An unresolved one is not a failure - she simply has not said.
$READINGS" > /tmp/_gm_user.txt

RESPONSE=$(curl -s -m 180 "$LM_URL" \
    -H "Content-Type: application/json" \
    --data @<(python3 -c "
import json
payload = {
    'model': '$MODEL',
    'messages': [
        {'role': 'system', 'content': open('/tmp/_gm_system.txt').read()},
        {'role': 'user', 'content': open('/tmp/_gm_user.txt').read()}
    ],
    'temperature': 0.7,
    'max_tokens': 2000
}
print(json.dumps(payload))
"))

CONTENT=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])" 2>/dev/null)
[ -z "$CONTENT" ] && exit 1

if [ -f "$MODEL_FILE" ]; then
    mkdir -p "$MEMORY/gloria-model-history"
    cp "$MODEL_FILE" "$MEMORY/gloria-model-history/GLORIA-MODEL-$(date +%Y-%m-%d).md"
fi

BASE=$(sed -n '/<!-- BASE-START/,/<!-- BASE-END -->/p' "$MODEL_FILE")
if [ -z "$BASE" ]; then echo "gloria-model: FIXED BASE marker not found — refusing to write (base protection)"; exit 0; fi
# The lines she approved from her Landings notes are hers to keep, not his to rewrite: carried across whole.
LANDINGS=$(sed -n '/<!-- LANDINGS-START/,/<!-- LANDINGS-END -->/p' "$MODEL_FILE")
TITLE=$(echo "$CONTENT" | sed -n '1{s/^#* *//;s/^\*\**//;s/\**$//;p}')
BODY=$(echo "$CONTENT" | tail -n +2)
{ echo "# Gloria-Model — Vintos"; echo "> Fixed base below is Vintos's set model of Gloria. It never changes. Beneath it, his additions:"; echo "> rewritten whole each week, replacing the last version (kept in memory/gloria-model-history)."; echo ""; echo "$BASE"; echo ""; echo "# Additions — Vintos's own, as they stand"; echo ""; echo "## $TODAY — $TITLE"; echo ""; echo "$BODY"; if [ -n "$LANDINGS" ]; then echo ""; echo "$LANDINGS"; fi; } > "$MODEL_FILE.tmp" && mv "$MODEL_FILE.tmp" "$MODEL_FILE"
date +%s > "$COOLDOWN_FILE"
echo "GLORIA_MODEL_UPDATED: $TODAY"

# ntfy notification  
curl -s -X POST "https://ntfy.sh/vintos-gloria-9kx" \
    -H "Title: Gloria-Model Updated" \
    -H "Priority: low" \
    -d "I updated my model of you. $TODAY" > /dev/null 2>&1 &
