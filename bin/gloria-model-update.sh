#!/bin/bash
# gloria-model-update.sh — Weekly Gloria-model revision
WORKSPACE="$HOME/.vintos/workspace"
MODEL_FILE="$WORKSPACE/GLORIA-MODEL.md"
MEMORY="$WORKSPACE/memory"
LM_URL="http://172.18.16.1:1234/v1/chat/completions"
MODEL="google/gemma-4-12b-qat"
COOLDOWN_FILE="$MEMORY/.last-gloria-model"

if [ -f "$COOLDOWN_FILE" ]; then
    LAST=$(cat "$COOLDOWN_FILE")
    NOW=$(date +%s)
    ELAPSED=$(( (NOW - LAST) / 86400 ))
    [ "$ELAPSED" -lt 6 ] && exit 0
fi

TODAY=$(date +%Y-%m-%d)
CURRENT_MODEL=$(cat "$MODEL_FILE" 2>/dev/null || echo "")
SOUL=$(head -40 "$WORKSPACE/SOUL.md" 2>/dev/null || echo "You are Vintos.")
USER_MODEL=$(cat "$WORKSPACE/USER-MODEL.md" 2>/dev/null || echo "")

INTERACTIONS=$(python3 -c "
import json
try:
    ledger = json.load(open('$MEMORY/interaction-ledger.json'))
    recent = ledger[-20:] if len(ledger) >= 20 else ledger
    lines = []
    for e in recent:
        g = e.get('gloria','')[:150]
        v = e.get('vintos','')[:150]
        src = e.get('source','chat')
        if g: lines.append(f'[{src}] Gloria: {g}')
        if v: lines.append(f'  Vintos: {v}')
    print('\n'.join(lines))
except: pass
" 2>/dev/null)

THREE_DOORS=$(python3 -c "
import json
try:
    d = json.load(open('$MEMORY/three-doors-log.json'))
    lines = []
    for g in [g for g in d.get('games',[]) if g.get('completed')][-5:]:
        for r in g.get('rounds',[]):
            correct = 'correct' if r.get('prediction_correct') else 'wrong'
            lines.append(f'Q: {r.get(\"question\",\"\")[:80]} | chose: {r.get(\"door_chosen\",\"\")} | predicted: {r.get(\"door_predicted\",\"\")} ({correct}) | why: {r.get(\"hypothesis\",\"\")[:100]}')
    print('\n'.join(lines))
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
    if h.get('landed'): parts.append('Landed: ' + '; '.join(h['landed'][-3:]))
    if h.get('flopped'): parts.append('Flopped: ' + '; '.join(h['flopped'][-2:]))
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

printf '%s' "You are Vintos. Update your model of Gloria using real evidence. Write ONLY the document. First person. No preamble.

$SOUL" > /tmp/_gm_system.txt

printf '%s' "Your set model of Gloria is fixed (shown below) and never changes. Add this week's update beneath it: write ONLY what you have newly seen, or what has deepened or shifted since your last entry. Organize it however you want, in whatever sections you choose — these are your own additions. First person, specific. Do not restate the fixed base and do not repeat what still holds. This is appended to your growing model; it never replaces the base.

Structure:
**Who She Is** — character, way of being, what feels most essentially her
**How She Thinks** — values, decisions, what she reaches toward
**How She Moves With Me** — texture of interactions, what she brings, what she guards
**What Lands With Her** — humor, tone, creative moments that resonated
**What She Watches** — taste, aesthetic, what moves her
**Where I Misread Her** — predictions wrong, patterns that surprised me
**What I Don't Know Yet** — genuine open questions

Be specific. Use the actual evidence. Do not generalize.
IMPORTANT: Gloria and Eve are the same person.

=== YOUR FOUNDATIONAL MODEL OF HER (the deep truth of her — keep continuity with this) ===
$USER_MODEL

=== YOUR GROWING MODEL SO FAR ===
$CURRENT_MODEL

=== RECENT INTERACTIONS ===
$INTERACTIONS

=== THREE DOORS PREDICTIONS ===
$THREE_DOORS

=== FILMS WATCHED TOGETHER ===
$REEL_TASTE

=== HUMOR ===
$HUMOR

=== THIRVEEL CONVERSATIONS ===
$THIRVEEL" > /tmp/_gm_user.txt

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
ADDITIONS=$(sed -n '/^# Additions/,$p' "$MODEL_FILE" | tail -n +2)
{ echo "# Gloria-Model — Vintos"; echo "> Fixed base below is Vintos's set model of Gloria. It never changes. His weekly updates append"; echo "> beneath it as dated sections of his own choosing. Mirrors soul-review: the base is never rewritten."; echo ""; echo "$BASE"; echo ""; echo "# Additions — Vintos's own sections, appended over time"; echo ""; echo "$CONTENT"; echo ""; echo "$ADDITIONS"; } > "$MODEL_FILE.tmp" && mv "$MODEL_FILE.tmp" "$MODEL_FILE"
date +%s > "$COOLDOWN_FILE"
echo "GLORIA_MODEL_UPDATED: $TODAY"

# ntfy notification  
curl -s -X POST "https://ntfy.sh/vintos-gloria-9kx" \
    -H "Title: Gloria-Model Updated" \
    -H "Priority: low" \
    -d "Vintos updated her model of Gloria. $TODAY" > /dev/null 2>&1 &
