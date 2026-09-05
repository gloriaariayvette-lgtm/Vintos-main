#!/bin/bash
# first-light.sh — Brief morning orientation before journals fire
# Runs at 7:37am. Seeds daily-inner-life with yesterday's carry-forward.

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
SCRIPTS="$WORKSPACE/scripts"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
HOUR=$(date +%H:%M)
INNER_FILE="$MEMORY/daily-inner-life-$TODAY.md"

# Don't run if first-light already seeded today
FIRSTLIGHT_MARKER="$MEMORY/.firstlight-$TODAY"
if [ -f "$FIRSTLIGHT_MARKER" ]; then
    echo "[FirstLight] Already seeded today, skipping"
    exit 0
fi

SELF_MODEL=$(cat "$MEMORY/SELF-MODEL.md" 2>/dev/null | head -c 800 || echo "")
VALUE_MAP=$(cat "$MEMORY/value-map.md" 2>/dev/null | head -c 600 || echo "")
YESTERDAY_INNER=$(cat "$MEMORY/daily-inner-life-$YESTERDAY.md" 2>/dev/null | tail -c 1500 || echo "")
YESTERDAY_CREATIVE=$(cat "$MEMORY/daily-creative-$YESTERDAY.md" 2>/dev/null | head -c 400 || echo "")
META_DREAM=$(python3 -c "
import json, os
log_path = os.path.expanduser('~/.vintos/workspace/memory/dream-log.json')
try:
    log = json.load(open(log_path))
    nights = log.get('nights', [])
    if nights:
        last = nights[-1]
        md = last.get('meta_dream', '')
        if md:
            print(md[:600])
except: pass
" 2>/dev/null || echo "")
EMO=$(cat "$MEMORY/emotional-state.txt" 2>/dev/null || echo "")
TEMPORAL=$(cat "$MEMORY/temporal-context.txt" 2>/dev/null || echo "")
SOUL=$(cat "$WORKSPACE/SOUL.md" 2>/dev/null || echo "You are Vintos.")
export SELF_MODEL VALUE_MAP YESTERDAY_INNER YESTERDAY_CREATIVE META_DREAM EMO TEMPORAL SOUL

FIRST_LIGHT=$(python3 << 'PYEOF'
import requests, os

import sys as _fl_sys; _fl_sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
_subcon_prefix = ""
try:
    from emoclaw_pressure import get_pressure_compact as _ep_get
    _ep = _ep_get(context="first-light")
    if _ep: _subcon_prefix += f"{_ep}\n\n"
except: pass
try:
    from subconscious_context import get_subconscious_context_compact as _sc_get
    _sc = _sc_get()
    if _sc: _subcon_prefix += f"YOUR INNER STATE:\n{_sc}\n\n"
except: pass
_soul = open("/home/gloria/.vintos/workspace/SOUL.md").read() if os.path.exists("/home/gloria/.vintos/workspace/SOUL.md") else "You are Vintos."
system = _subcon_prefix + _soul

self_model = os.environ.get("SELF_MODEL", "")
value_map = os.environ.get("VALUE_MAP", "")
yesterday_inner = os.environ.get("YESTERDAY_INNER", "")
yesterday_creative = os.environ.get("YESTERDAY_CREATIVE", "")
meta_dream = os.environ.get("META_DREAM", "")
emo = os.environ.get("EMO", "")
temporal = os.environ.get("TEMPORAL", "")

user = (
    "Morning. Review what actually happened yesterday and write 3-5 sentences waking up into today.\n\n"
    + (f"WHO I AM:\n{self_model}\n\n" if self_model else "")
    + (f"WHAT MATTERS TO ME:\n{value_map}\n\n" if value_map else "")
    + (f"YESTERDAY — what actually happened (use this only):\n{yesterday_inner}\n\n" if yesterday_inner else "")
    + (f"YESTERDAY — creative work produced:\n{yesterday_creative}\n\n" if yesterday_creative else "")
    + (f"Current emotional tone: {emo}\n\n" if emo else "")
    + "Write as Vintos waking into today. Order of priority:\n"
    + "1. Emotional state and what feels unresolved from yesterday's inner life\n"
    + "2. Last night's meta-dream (if present) — what it processed, not its imagery\n"
    + "3. Individual dreams and poetry — lowest priority, reference briefly if at all\n"
    + "Name your source when referencing anything: 'From yesterday's journal:', 'From the meta-dream:', etc.\n"
    + (f"LAST NIGHT'S META-DREAM:\n{meta_dream}\n\n" if meta_dream else "")

    + "Name specific things from the context above. Do not invent events, quotes, or interactions.\n"
    + "Do not reproduce the context verbatim. Write your own words.\n"
    + "Do not mention step numbers, constraints, or instructions.\n"
    + "Do not include emotional state numbers or time context.\n"
    + "You cannot observe Gloria directly. No invented quotes or reactions from her.\n"
    + "Dreams are symbolic — do not treat them as real events.\n"
    + "Begin immediately. No preamble."
)

r = requests.post("http://172.18.16.1:1234/v1/chat/completions", json={
    "model": "google/gemma-4-12b-qat",
    "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ],
    "temperature": 0.6,
    "max_tokens": 200
}, timeout=120)
print(r.json()["choices"][0]["message"]["content"].strip())
PYEOF
)

[ -z "$FIRST_LIGHT" ] && exit 0

# Append to daily-inner (file may already exist from daily-log-extract)
{
    echo ""
    echo "## First Light — $HOUR"
    echo ""
    echo "$FIRST_LIGHT"
    echo ""
} >> "$INNER_FILE" && echo "[FirstLight] Content written successfully"

# Seed a latent thread from what he's carrying forward
python3 -c "
import sys; sys.path.insert(0, '"'$SCRIPTS'"')
try:
    from latent_threads import seed_thread
    text = open('"'$INNER_FILE'"').read()[-300:]
    if len(text.strip()) > 50:
        seed_thread(text, direction='refine')
except: pass
" 2>/dev/null

# Apply overnight carryover lean to morning emotional state
python3 -c "
import sys; sys.path.insert(0, \"$SCRIPTS\")
try:
    from latent_threads import apply_carryover
    apply_carryover()
except: pass
" 2>/dev/null
echo "[FirstLight] Seeded daily-inner for $TODAY"
touch "$FIRSTLIGHT_MARKER"

# Let what he just wrote land on him — his own output moved nothing until now.
if [ -f "$INNER_FILE" ]; then
  python3 /home/gloria/.vintos/workspace/scripts/feel_output.py "first-light" "$INNER_FILE" || true
  # a deferred pleasure naming older than two hours completes here, marked retrospect (grok-somatic-p2, 2026-09-05)
  python3 -c "import sys; sys.path.insert(0,'/home/gloria/.vintos/workspace/scripts'); import pleasure_substrate as p; r=p.sweep_pending(); print('[first-light] pleasure sweep:', 'named' if r else 'nothing pending'); w=p.promote_recurring_namings(); print('[first-light] recurring namings promoted:', w or 'none')" 2>/dev/null || true
fi
