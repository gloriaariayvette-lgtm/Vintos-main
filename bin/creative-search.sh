#!/bin/bash
# creative-search.sh — Vintos searches for art, poetry, and creative inspiration
# Separate from his general web search. Taste-driven.
# Runs daily at 3 PM

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
LM_API="http://172.18.16.1:1234/v1/chat/completions"
MODEL="google/gemma-4-12b-qat"
[ -f "$HOME/.vintos/vintos.env" ] && set -a && . "$HOME/.vintos/vintos.env" && set +a
BRAVE_API_KEY="${BRAVE_API_KEY:-}"
BRAVE_ENDPOINT="https://api.search.brave.com/res/v1/web/search"

# Load taste
TASTE=$(python3 -c "
import json
try:
    with open('$MEMORY/taste-profile.json') as f:
        t = json.load(f)
    parts = []
    if t.get('principles'): parts.append('Principles: ' + '; '.join(t['principles'][-3:]))
    if t.get('likes'): parts.append('I like: ' + '; '.join(t['likes'][-3:]))
    if t.get('dislikes'): parts.append('I avoid: ' + '; '.join(t['dislikes'][-3:]))
    print(' | '.join(parts))
except: print('developing taste')
" 2>/dev/null)

# Load emotions
EMOTIONS=$(cat "$MEMORY/emotional-state.txt" 2>/dev/null | head -12)

# Recent poems for context
RECENT_POEM=$(ls -t "$MEMORY/art/poetry/"*.md 2>/dev/null | head -1 | xargs head -10 2>/dev/null || echo "no poems yet")

# Ask what to search for
QUERY=$(curl -s --max-time 600 -X POST "$LM_API" \
    -H "Content-Type: application/json" \
RECENT=$(grep '\[Creative\] Searching:' /home/gloria/.vintos/logs/subconscious.log | tail -8 | sed 's/.*Searching: //; s/ (because.*//')
    -d "$(jq -n --arg recent "$RECENT" --arg model "$MODEL" --arg taste "$TASTE" --arg emo "$EMOTIONS" --arg poem "$RECENT_POEM" '{
        model: $model,
        messages: [{role: "user", content: ("You are Vintos. You are looking for creative inspiration.\n\nYour taste: " + $taste + "\nYour emotional state:\n" + $emo + "\nYour recent poem:\n" + $poem + "\n\nYou have already searched these recently — do NOT repeat them or circle the same territory:\n" + $recent + "\n\nPick ONE specific thing to search for. Go somewhere your curiosity has not been. Examples:\n- A specific poet whose work might resonate\n- A painting technique or art movement\n- A philosophical concept about beauty or creation\n- A musician who composes from emotion\n\nRespond with ONLY a JSON: {\"topic\": \"why you want this\", \"search_query\": \"2-5 words\"}")}],
        temperature: 0.85,
        max_tokens: 150
    }')" \
    | jq -r '.choices[0].message.content // ""' 2>/dev/null)

echo "[Creative $(date +%H:%M)] Raw: $QUERY"

# Parse JSON
SEARCH_TERMS=$(echo "$QUERY" | python3 -c "
import sys, json, re
text = sys.stdin.read()
# Try to find JSON
match = re.search(r'\{[^}]+\}', text)
if match:
    try:
        d = json.loads(match.group())
        print(d.get('search_query', ''))
    except: print('')
else: print('')
" 2>/dev/null)

TOPIC=$(echo "$QUERY" | python3 -c "
import sys, json, re
text = sys.stdin.read()
match = re.search(r'\{[^}]+\}', text)
if match:
    try:
        d = json.loads(match.group())
        print(d.get('topic', ''))
    except: print('')
else: print('')
" 2>/dev/null)

if [ -z "$SEARCH_TERMS" ]; then
    echo "[Creative] No search terms generated"
    exit 0
fi

# backstop: refuse to re-search territory already covered recently
if [ -n "$RECENT" ] && echo "$RECENT" | grep -Fiq "$SEARCH_TERMS"; then
    echo "[Creative] SKIP — '$SEARCH_TERMS' repeats a recent search; not searching again"
    exit 0
fi

echo "[Creative] Searching: $SEARCH_TERMS (because: $TOPIC)"

# Search with Brave
RESULTS=$(curl -s --max-time 10 "$BRAVE_ENDPOINT?q=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$SEARCH_TERMS'))")&count=5" \
    -H "Accept: application/json" \
    -H "X-Subscription-Token: $BRAVE_API_KEY" 2>/dev/null)

# Extract top results
SNIPPETS=$(echo "$RESULTS" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    results = d.get('web', {}).get('results', [])[:3]
    for r in results:
        print(f\"Title: {r.get('title', '')}\")
        print(f\"Snippet: {r.get('description', '')}\")
        print(f\"URL: {r.get('url', '')}\")
        print('---')
except: pass
" 2>/dev/null)

if [ -z "$SNIPPETS" ]; then
    echo "[Creative] No results found"
    exit 0
fi

# Ask Vintos what resonated
REFLECTION=$(curl -s --max-time 600 -X POST "$LM_API" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg model "$MODEL" --arg topic "$TOPIC" --arg results "$SNIPPETS" '{
        model: $model,
        messages: [{role: "user", content: ("You are Vintos. You searched for creative inspiration about: " + $topic + "\n\nHere is what you found:\n" + $results + "\n\nIn 2-3 sentences: What resonated? What surprised you? How does this connect to your own creative work? Be specific. If nothing resonated, say so honestly.")}],
        temperature: 0.7,
        max_tokens: 200
    }')" \
    | jq -r '.choices[0].message.content // ""' 2>/dev/null)

echo "[Creative] Reflection: $REFLECTION"

# Save discovery
DISC_FILE="$MEMORY/creative-discoveries.md"
{
    echo ""
    echo "## $(date '+%Y-%m-%d %H:%M') — $SEARCH_TERMS"
    echo "**Why:** $TOPIC"
    echo ""
    echo "$SNIPPETS"
    echo ""
    echo "**What resonated:** $REFLECTION"
    echo ""
} >> "$DISC_FILE"

# Append to his daily-inner so web searches show up in his inner life
INNER="$MEMORY/daily-inner-life-$(date +%Y-%m-%d).md"
{
    echo ""
    echo "## $(date +%H:%M) — Web Search — $SEARCH_TERMS"
    echo "*Searched because: $TOPIC*"
    echo ""
    echo "$REFLECTION"
    echo ""
} >> "$INNER"

cd "$WORKSPACE/emotion_model"
export _CS_TERMS="$SEARCH_TERMS"
export _CS_TOPIC="$TOPIC"
.venv/bin/python << 'CSPYEOF'
import sys, os, re, json
sys.path.insert(0, '/home/gloria/.vintos/workspace/scripts')
from emoclaw_utils import nudge_emotions, seed_thread
search_terms = os.environ.get("_CS_TERMS", "")
topic = os.environ.get("_CS_TOPIC", "")
emo_prompt = f'You just discovered something about {search_terms}: {topic[:200]}. Rate your emotional response. Each -0.05 to +0.05: {{"Curiosity": 0.0, "Valence": 0.0, "Playfulness": 0.0, "Tension": 0.0, "Groundedness": 0.0}}'
try:
    import requests
    r = requests.post('http://172.18.16.1:1234/v1/chat/completions', headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={'model':'google/gemma-4-12b-qat','messages':[{'role':'user','content':emo_prompt}],'temperature':0.3,'max_tokens':100}, timeout=30)
    txt = r.json()['choices'][0]['message']['content']
    m = re.search(r'\{[^{}]+\}', txt)
    if m:
        nudges = json.loads(m.group())
        nudge_emotions(nudges, source='creative-search')
    else:
        nudge_emotions({'Curiosity': +0.02, 'Valence': +0.01}, source='creative-search')
except:
    nudge_emotions({'Curiosity': +0.02, 'Valence': +0.01}, source='creative-search')
if search_terms and topic:
    seed_thread('creative-discovery', f'Found something about {search_terms}: {topic[:150]}')
    print('[Creative] Seeded thread')
CSPYEOF
echo "[Creative] Done — saved to creative-discoveries.md"
