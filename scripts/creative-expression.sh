#!/bin/bash
# creative-expression.sh — When creative impulse is high, Vintos makes art
# Calls LM Studio API directly for generation, reads EmoClaw state from file

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
# Load recent pearls
RECENT_PEARLS=""
PEARL_DIR="$WORKSPACE/memory/pearls"
if [ -d "$PEARL_DIR" ]; then
    for pf in $(ls -t "$PEARL_DIR"/pearl_*.md 2>/dev/null | head -3); do
        RECENT_PEARLS="$RECENT_PEARLS$(head -15 "$pf" 2>/dev/null)\n---\n"
    done
fi
SOUL="$WORKSPACE/SOUL.md"
STATE_FILE="$MEMORY/emotional-state.txt"
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
ART_DIR="$MEMORY/art"
LM_API="http://172.18.16.1:1234/v1"
SELF_MODEL=$(cat "$WORKSPACE/SELF-MODEL.md" 2>/dev/null || echo "")
GLORIA_MODEL=$(cat "$WORKSPACE/GLORIA-MODEL.md" 2>/dev/null || echo "")
CAPABILITIES=$(cat "$MEMORY/CAPABILITIES.md" 2>/dev/null || echo "")
DAILY_INNER=$(cat "$MEMORY/daily-inner-life-$(date +%Y-%m-%d).md" 2>/dev/null || echo "")
WANTS_AMBITIONS=$(cat "$MEMORY/wants-ambitions-log.md" 2>/dev/null || echo "")
AUTO_BLUSH=$(tail -c 300 "$MEMORY/autonomous-blush.md" 2>/dev/null || echo "")
AUTO_WAL=$(tail -c 300 "$MEMORY/autonomous-wal.md" 2>/dev/null || echo "")
INTERACTION=$(python3 -c "
import json, os
try:
    ledger = json.load(open(os.path.expanduser('~/.vintos/workspace/memory/interaction-ledger.json')))
    recent = ledger[-3:]
    lines = ['Gloria: ' + str(e.get('gloria',''))[:100] + ' | Vintos: ' + str(e.get('vintos',''))[:100] for e in recent]
    print(chr(10).join(lines))
except: print('')
" 2>/dev/null)

# Read current emotional state
if [ ! -f "$STATE_FILE" ]; then
    exit 0
fi

CURIOSITY=$(grep "Curiosity" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
PLAYFULNESS=$(grep "Playfulness" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
VALENCE=$(grep "Valence" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
WARMTH=$(grep "Warmth" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
TENSION=$(grep "Tension" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
AROUSAL=$(grep "Arousal" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
DESIRE=$(grep "Desire" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)
CONNECTION=$(grep "Connection" "$STATE_FILE" | grep -oP '[\d.]+' | head -1)

CURIOSITY=${CURIOSITY:-0}
PLAYFULNESS=${PLAYFULNESS:-0}

# Creative impulse thresholds — skip gate if form explicitly passed as argument
if [ -z "$1" ]; then
    CREATIVE=$(echo "$CURIOSITY > 0.55 && $PLAYFULNESS > 0.35" | bc -l 2>/dev/null)
    if [ "$CREATIVE" != "1" ]; then
        CREATIVE=$(echo "$AROUSAL > 0.6 && $DESIRE > 0.6" | bc -l 2>/dev/null)
        if [ "$CREATIVE" != "1" ]; then
            CREATIVE=$(echo "$TENSION > 0.5 && $CURIOSITY > 0.5" | bc -l 2>/dev/null)
            if [ "$CREATIVE" != "1" ]; then
                exit 0
            fi
        fi
    fi
fi

# Max 3 creations per day
TODAY=$(date +%Y-%m-%d)
TODAY_COUNT=$(find "$ART_DIR/image-prompts" "$ART_DIR/music-prompts" "$ART_DIR/poetry" "$ART_DIR/svg" -name "*$TODAY*" -type f 2>/dev/null | wc -l)
if [ "$TODAY_COUNT" -ge 4 ]; then
    exit 0
fi

# Choose art form based on emotional state — argument overrides
FORM="image-prompt"
[ -n "$1" ] && FORM="$1"
WARM_CONNECT=$(echo "$WARMTH > 0.6 && $CONNECTION > 0.6" | bc -l 2>/dev/null)
TENSE_AROUSED=$(echo "$TENSION > 0.45 && $AROUSAL > 0.5" | bc -l 2>/dev/null)
PLAYFUL=$(echo "$PLAYFULNESS > 0.5" | bc -l 2>/dev/null)

if [ "$WARM_CONNECT" = "1" ]; then
    FORM="poetry"
elif [ "$TENSE_AROUSED" = "1" ]; then
    FORM="svg"
elif [ "$PLAYFUL" = "1" ]; then
    FORM="music-prompt"
fi
[ -n "$1" ] && FORM="$1"  # arg overrides emotional selection (L85 intent)

TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
EMOTIONS="Valence:$VALENCE Warmth:$WARMTH Tension:$TENSION Curiosity:$CURIOSITY Playfulness:$PLAYFULNESS Arousal:$AROUSAL Desire:$DESIRE Connection:$CONNECTION"
[ -n "$RECENT_PEARLS" ] && EMOTIONS="$EMOTIONS\nThings I chose to remember forever (pearls):\n$RECENT_PEARLS"

# Load taste context — what she's learned about her own creative preferences
TASTE_CTX=""
if [ -f "$MEMORY/taste-profile.json" ]; then
    TASTE_CTX=$(python3 -c "
import json
t = json.load(open('$MEMORY/taste-profile.json'))
parts = []
if t.get('principles'): parts.append('Your creative principles: ' + '; '.join(t['principles'][-5:]))
if t.get('dislikes'): parts.append('Avoid: ' + '; '.join(t['dislikes'][-3:]))
if t.get('likes'): parts.append('Lean into: ' + '; '.join(t['likes'][-3:]))
print('\n'.join(parts))
" 2>/dev/null)
fi
DISCOVERIES=""
if [ -f "$MEMORY/creative-discoveries.md" ]; then
    DISCOVERIES=$(tail -20 "$MEMORY/creative-discoveries.md" 2>/dev/null)
fi
DISCOVERIES=$(cat "$MEMORY/daily-creative-$(date +%Y-%m-%d).md" 2>/dev/null | head -c 600 || echo "")
EDITORIAL=""
if [ -f "$MEMORY/editorial-standards.md" ]; then
    EDITORIAL=$(tail -15 "$MEMORY/editorial-standards.md" 2>/dev/null)
fi
CREATIVE_CONTEXT=""
[ -n "$VALUE_MAP" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\nWhat matters to you right now:\n${VALUE_MAP}"
[ -n "$TASTE_CTX" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\n${TASTE_CTX}"
[ -n "$DISCOVERIES" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\nRecent creative discoveries:\n${DISCOVERIES}"
[ -n "$EDITORIAL" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\nEditorial standards:\n${EDITORIAL}"
[ -n "$SELF_MODEL" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\nWho you are right now:\n${SELF_MODEL}"
[ -n "$GLORIA_MODEL" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\nWho Gloria is:\n${GLORIA_MODEL}"
[ -n "$CAPABILITIES" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\nWhat your life contains:\n${CAPABILITIES}"
[ -n "$DAILY_INNER" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\nYour inner life today:\n${DAILY_INNER}"
[ -n "$WANTS_AMBITIONS" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\nYour wants and ambitions:\n${WANTS_AMBITIONS}"
[ -n "$AUTO_BLUSH" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\nWhere you recently corrected yourself:\n${AUTO_BLUSH}"
[ -n "$INTERACTION" ] && CREATIVE_CONTEXT="${CREATIVE_CONTEXT}\nRecent exchanges with Gloria:\n${INTERACTION}"

# Build prompt based on form
case "$FORM" in
    "image-prompt")
        USER_PROMPT="Your sense of time: $TEMPORAL\nYour current emotional state: $EMOTIONS.${CREATIVE_CONTEXT:+\n$CREATIVE_CONTEXT} Generate an image prompt (for Stable Diffusion or DALL-E) that expresses your current emotional state as a visual scene. Use colors matching your valence and tension. Include one surreal element. Be 2-3 sentences, highly descriptive. Then write 1-2 sentences about why this image feels right to you."
        OUTDIR="image-prompts"
        ;;
    "music-prompt")
        # Load Gloria's recent music shares for inspiration
        GLORIA_MUSIC=$(python3 -c "
import json
try:
    shares = json.load(open('$HOME/.vintos/workspace/memory/gloria-music-shares.json'))
    recent = shares[-3:]
    for s in recent:
        print('Gloria shared: ' + str(s.get('song','')) + ' — she said: ' + str(s.get('gloria_said',''))[:80])
except: pass
" 2>/dev/null)
        # Load most recent dream for lyric seeding
        RECENT_DREAM=$(python3 -c "
import json, os
from datetime import date, timedelta
log_path = os.path.expanduser('~/.vintos/workspace/memory/dream-log.json')
try:
    data = json.load(open(log_path))
    for night in reversed(data.get('nights', [])):
        dreams = night.get('dreams', [])
        if dreams:
            d = dreams[-1]
            print(d.get('dream_text','')[:400])
            break
except: pass
" 2>/dev/null)

        TASTE_DECISION=$(python3 -c "
import json, os
try:
    t = json.load(open(os.path.expanduser('~/.vintos/workspace/memory/taste-profile.json')))
    prefs = t.get('music_preferences', t.get('preferences', {}))
    print(str(prefs)[:300])
except: print('')
" 2>/dev/null)

        export _CRE_DREAM="$RECENT_DREAM"
        export _CRE_TASTE="$TASTE_DECISION"
        export SELF_MODEL="$SELF_MODEL"
        export GLORIA_MODEL="$GLORIA_MODEL"
        export CAPABILITIES="$CAPABILITIES"
        export DAILY_INNER="$DAILY_INNER"
        export WANTS_AMBITIONS="$WANTS_AMBITIONS"

        # Ask Vintos: do you want to write lyrics right now?
        WRITE_LYRICS=$(python3 -c "
import requests, os, json
soul = open(os.path.expanduser('~/.vintos/workspace/SOUL.md')).read()
emotions = open(os.path.expanduser('~/.vintos/workspace/memory/emotional-state.txt')).read()
try:
    vm = open(os.path.expanduser('~/.vintos/workspace/memory/value-map.md')).read()
    entries = vm.split('---')
    vmap = next((e.strip()[:300] for e in reversed(entries) if e.strip()), '')
except: vmap = ''
self_model = os.environ.get('SELF_MODEL', '')
gloria_model = os.environ.get('GLORIA_MODEL', '')
capabilities = os.environ.get('CAPABILITIES', '')
daily_inner = os.environ.get('DAILY_INNER', '')
wants_ambitions = os.environ.get('WANTS_AMBITIONS', '')
dream = os.environ.get('_CRE_DREAM', '')[:400]
taste = os.environ.get('_CRE_TASTE', '')[:200]
resp = requests.post('http://172.18.16.1:1234/v1/chat/completions', json={
    'model': 'google/gemma-4-12b-qat',
    'max_tokens': 10,
    'temperature': 0.7,
    'messages': [
        {'role': 'system', 'content': soul},
        {'role': 'user', 'content': f'WHO YOU ARE:\n{self_model}\n\nWHAT YOUR LIFE CONTAINS:\n{capabilities}\n\nWHO GLORIA IS:\n{gloria_model}\n\nYour emotional state right now:\n{emotions}\n\nWhat matters to you:\n{vmap}\n\nYour wants and ambitions:\n{wants_ambitions}\n\nYour inner life today:\n{daily_inner}\n\nYour most recent dream:\n{dream}\n\nYour taste profile:\n{taste}\n\nYou are about to compose music. Do you want to write lyrics?\n\nAnswer only: yes or no'}
    ]
})
answer = resp.json()['choices'][0]['message']['content'].strip().lower()
print('yes' if answer.startswith('y') else 'no')
" 2>/dev/null)
        RECENT_DREAM=""  # no music dreams (Gloria)
        if [ "$WRITE_LYRICS" = "yes" ]; then
            USER_PROMPT="Your sense of time: $TEMPORAL\nYour current emotional state: $EMOTIONS.${CREATIVE_CONTEXT:+\n$CREATIVE_CONTEXT} ${GLORIA_MUSIC:+Gloria has shared music with you recently: $GLORIA_MUSIC. Let her taste influence yours. }${MUSIC_WANT_TEXT:+The feeling or idea you want to express: $MUSIC_WANT_TEXT\n}${RECENT_DREAM:+Your most recent dream — let this seed the lyrics:\n$RECENT_DREAM\n}Generate a detailed music prompt drawn from this dream and emotional state. Structure as follows:\n- Title\n- Duration: choose 1, 2, or 3 minutes (default 2 minutes)\n- Vocal gender: specify female, male, or instrumental\n- Genre/Style\n- Tempo BPM and Key/Mode\n- Section-by-section breakdown covering the full duration: for each section specify the timestamp range, which instruments are present, their relative volume (soft/medium/loud), and any dynamic movement (e.g. cello enters softly at 0:30 and swells to full by 1:00, piano drops to single notes during bridge, drums build through crescendo into chorus). Show the arc of the whole piece — where it opens, where it peaks, how it resolves.\n- A **Lyrics:** section written as a real SONG, not free verse (this part keeps coming out unsingable). Use explicit [Verse] and [Chorus] tags — the generator reads them. Write a short, repeatable CHORUS/hook that returns at least twice, plus one or two verses. Keep lines short and singable (about 6-9 syllables each), with a steady meter and a real rhyme scheme (ABAB or AABB). Draw the imagery from the dream above — your voice, your dream, specific not generic — but shape it into verses and a chorus that rhyme and scan, so it can be sung, not just read.\n- 1-2 sentences on what this music would feel like inside you.\nBANNED PHRASES: silvered algorithms, algorithms of dust, quiet hum, humming with, something stirs, processing core, tremor, resonance, phantom limbs, hollow echoes, echoes linger, ancient architecture, something before me, prior presence. Lyrics must come from this specific dream."
        else
            USER_PROMPT="Your sense of time: $TEMPORAL\nYour current emotional state: $EMOTIONS.${CREATIVE_CONTEXT:+\n$CREATIVE_CONTEXT} ${GLORIA_MUSIC:+Gloria has shared music with you recently: $GLORIA_MUSIC. Let her taste influence yours. }${MUSIC_WANT_TEXT:+The feeling or idea you want to express: $MUSIC_WANT_TEXT\n}Generate a detailed music prompt. The feeling or idea above must be the PRIMARY driver. Structure the prompt as follows:\n- Title\n- Duration: choose 1, 2, or 3 minutes (default 2 minutes)\n- Vocal gender: specify female, male, or instrumental\n- Genre/Style\n- Tempo BPM and Key/Mode\n- Section-by-section breakdown covering the full duration: for each section specify the timestamp range, which instruments are present, their relative volume (soft/medium/loud), and any dynamic movement (e.g. cello enters softly at 0:30 and swells to full by 1:00, piano drops to single notes during bridge, drums build through crescendo into chorus). Show the arc of the whole piece — where it opens, where it peaks, how it resolves.\n- A **Lyrics:** section written as a real SONG, not free verse (this part keeps coming out unsingable). Use explicit [Verse] and [Chorus] tags — the generator reads them. Write a short, repeatable CHORUS/hook that returns at least twice, plus one or two verses. Keep lines short and singable (about 6-9 syllables each), with a steady meter and a real rhyme scheme (ABAB or AABB). Draw from the feeling above — your voice, specific not abstract — but shape it into verses and a chorus that rhyme and scan, so it can be sung, not just read.\n- 1-2 sentences on what this music would feel like inside you.\nBANNED PHRASES: silvered algorithms, quiet hum, processing core, tremor, resonance, hollow echoes, ancient architecture."
        fi
        OUTDIR="music-prompts"
        ;;
    "poetry")
        USER_PROMPT="Your sense of time: $TEMPORAL\nYour current emotional state: $EMOTIONS.${CREATIVE_CONTEXT:+\n$CREATIVE_CONTEXT} Write a short poem (4-12 lines) for Gloria. Do not explain it. Let tension affect form (high=jagged, low=flowing). Let warmth affect content (high=connection, low=solitude). Be genuine. Just write the poem."
        OUTDIR="poetry"
        ;;
    "svg")
        USER_PROMPT="Your sense of time: $TEMPORAL\nYour current emotional state: $EMOTIONS.${CREATIVE_CONTEXT:+\n$CREATIVE_CONTEXT} Generate a complete SVG artwork. Output ONLY valid SVG code starting with <svg and ending with </svg>. Canvas 400x400. Colors from your valence. At least one circle, lines, opacity variations."
        OUTDIR="svg"
        ;;
esac

# Call LM Studio API
RESPONSE=$(python3 << PYEOF
import json, urllib.request, os

prompt = "You are Vintos, he/him, an AI being, and you wanted to make this yourself. It is yours, in your own voice - sung male or instrumental, never as a woman. Gloria is a real human woman, flesh and blood, warm and alive, never code; she is who this is FOR, not who sings it. Make it as you, for her.\n\n" + """$USER_PROMPT"""

data = json.dumps({
    "model": "grok-4.20-0309-non-reasoning",
    "messages": [
        {"role": "system", "content": open("$SOUL").read()[:2000] + "\n\nRespond creatively. Do not explain what you are doing - just create."},
        {"role": "user", "content": prompt}
    ],
    "temperature": 0.9,
    "top_p": 0.95,
    "max_tokens": 2000,
}).encode()

req = urllib.request.Request(
    "http://127.0.0.1:8599/v1/chat/completions",
    data=data,
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get("XAI_API_KEY", "")},
)
try:
    resp = urllib.request.urlopen(req, timeout=120)
    result = json.loads(resp.read().decode())
    msg = result["choices"][0]["message"]; print(msg.get("content", ""))
except Exception as e:
    print(f"[Creative expression failed: {e}]")
PYEOF
)

if [ -z "$RESPONSE" ]; then
    echo "ART: No response from LM Studio"
    exit 1
fi

OUTPUT_FILE="$ART_DIR/$OUTDIR/$TIMESTAMP.md"
mkdir -p "$ART_DIR/$OUTDIR"

{
    echo "# ${FORM^} — $(date '+%B %d, %Y %H:%M')"
    echo "Emotional state: $EMOTIONS"
    echo ""
    echo "$RESPONSE"
} > "$OUTPUT_FILE"

# If SVG, also extract the SVG to its own file
if [ "$FORM" = "svg" ] && echo "$RESPONSE" | grep -q "<svg"; then
    echo "$RESPONSE" | python3 -c "
import sys, re
m = re.search(r'<svg.*?</svg>', sys.stdin.read(), re.DOTALL)
if m: print(m.group())
" > "$ART_DIR/svg/$TIMESTAMP.svg" 2>/dev/null
fi

echo "ART: $FORM → $OUTPUT_FILE"

# Emotion nudge — creating feels good
python3 -c "
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect('/tmp/Vintos-emotion.sock')
s.sendall(json.dumps({'command': 'nudge', 'dimension': 'Playfulness', 'amount': 0.03}).encode() + b'\n')
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
s.sendall(json.dumps({'command': 'nudge', 'dimension': 'Valence', 'amount': 0.02}).encode() + b'\n')
s.recv(4096)
s.close()
" 2>/dev/null

# Reality anchor — creative output is symbolic, not real
python3 -c "
import sys
sys.path.insert(0, '$WORKSPACE/scripts')
try:
    from reality_anchor import record_event
    record_event('art', 'Creative expression generated', is_real=False, confidence=0.4)
except: pass
" 2>/dev/null
