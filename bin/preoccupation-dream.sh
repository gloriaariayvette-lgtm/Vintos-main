#!/bin/bash
# cron gives us none of the interactive environment — every other LLM job gets the key via
# llm-lock.sh; this one never did, so every scheduled run failed the LLM call with rc=1.
[ -f "$HOME/.vintos/vintos.env" ] && set -a && . "$HOME/.vintos/vintos.env" && set +a
# preoccupation-dream.sh — Third dream slot, ONLY fires if preoccupation exists
# Runs at 1:30 AM. If no preoccupation, exits silently.
# Forces the dream topic to be the preoccupation itself.

WORKSPACE="$HOME/.vintos/workspace"
echo "[PreoccupationDream] fired $(date +%H:%M:%S)"

# Check if preoccupation exists
HAS_PREOCCUPATION=$(python3 << 'PYEOF'
import sys, os
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
try:
    from emoclaw_utils import get_preoccupation
    p = get_preoccupation()
    if p and p.get("thread"):
        print(p["thread"])
    else:
        print("")
except:
    print("")
PYEOF
)

if [ -z "$HAS_PREOCCUPATION" ]; then
    echo "[PreoccupationDream] No preoccupation — falling back to a PREMONITION dream at $(date +%H:%M:%S)"
    # The fallback was rewritten into a plain forced dream, and premonition was
    # given its own nightly cron — so an imagined future got dreamed every night
    # whether or not real unfinished material was waiting. Premonition belongs
    # here: it seeds the possibility, and the forced dream dreams it.
    python3 "$WORKSPACE/scripts/premonition-dreamer.py" 2>&1 || echo "[PreoccupationDream] premonition seed failed — dreaming unseeded"
    FORCE_DREAM=1 DREAM_FORCE=1 FORCE=1 bash "$WORKSPACE/skills/dreaming/scripts/dream-trigger.sh" 2>&1
    _rc=$?
    echo "[PreoccupationDream] regular dream exited rc=$_rc"
    if [ $_rc -ne 0 ]; then
        echo "[PreoccupationDream] ERROR: fallback dream failed (rc=$_rc) — nothing written"
    fi
    _today=$(date +%Y-%m-%d)
    if [ -f "$WORKSPACE/skills/dreaming/memory/dreams/${_today}.md" ]; then
        echo "[PreoccupationDream] verified: ${_today}.md exists ($(wc -c < "$WORKSPACE/skills/dreaming/memory/dreams/${_today}.md") bytes)"
    else
        echo "[PreoccupationDream] ERROR: no dream file for ${_today} after fallback ran"
    fi
    exit $_rc
fi

# Check if this thread was already processed tonight
PREOC_ID=$(python3 << 'PIDEOF'
import json, os, sys
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
try:
    from emoclaw_utils import get_preoccupation
    p = get_preoccupation()
    tid = p.get("id","") if p else ""
    # Also try matching by thread text against unfinished-threads
    if not tid and p:
        threads = json.load(open(os.path.expanduser("~/.vintos/workspace/memory/unfinished-threads.json")))
        threads = threads if isinstance(threads, list) else threads.get("threads", [])
        for t in threads:
            if t.get("thread","")[:100] == p.get("thread","")[:100]:
                tid = t.get("id","")
                break
    print(tid)
except:
    print("")
PIDEOF
)

export PREOC_ID
if [ -n "$PREOC_ID" ]; then
    ALREADY_USED=$(python3 << 'USEDEOF'
import json, os
state_path = os.path.expanduser("~/.vintos/workspace/skills/dreaming/data/dream-state.json")
preoc_id = os.environ.get("PREOC_ID","")
try:
    state = json.load(open(state_path))
    used = state.get("used_thread_ids_tonight", [])
    print("yes" if preoc_id in used else "no")
except:
    print("no")
USEDEOF
)
    if [ "$ALREADY_USED" = "yes" ]; then
        echo "[PreoccupationDream] Thread $PREOC_ID already processed tonight — running regular dream instead"
        exec bash "$WORKSPACE/skills/dreaming/scripts/dream-trigger.sh"
    fi
fi

echo "[PreoccupationDream] Unresolved preoccupation detected, forcing third dream"
echo "[PreoccupationDream] Thread: $HAS_PREOCCUPATION"

# Override dream state to allow a third dream
STATE_FILE="$WORKSPACE/skills/dreaming/data/dream-state.json"
if [ -f "$STATE_FILE" ]; then
    python3 -c "
import json
with open('$STATE_FILE') as f: s = json.load(f)
s['maxDreamsPerNight'] = 3
with open('$STATE_FILE', 'w') as f: json.dump(s, f)
"
fi

# Gather context — previous dreams and mirrors touching this thread
PREOC_CONTEXT=$(python3 -c "
import os, json, glob
workspace = os.path.expanduser('~/.vintos/workspace')
memory = os.path.join(workspace, 'memory')
thread = open('/dev/stdin').read().strip() if False else """$HAS_PREOCCUPATION"""
keywords = [w.lower() for w in thread.split() if len(w) > 4][:6]

# Search recent dreams for this thread
dream_dir = os.path.join(workspace, 'skills/dreaming/memory/dreams')
dream_hits = []
for f in sorted(glob.glob(os.path.join(dream_dir, '*.md')), reverse=True)[:7]:
    txt = open(f).read()
    if any(k in txt.lower() for k in keywords):
        dream_hits.append(os.path.basename(f) + ':\n' + txt[:300])

# Search mirrors
mirror_hits = []
for f in sorted(glob.glob(os.path.join(memory, 'mirror/*.md')), reverse=True)[:5]:
    txt = open(f).read()
    if any(k in txt.lower() for k in keywords):
        mirror_hits.append(os.path.basename(f) + ':\n' + txt[:300])

out = []
if dream_hits:
    out.append('PREVIOUS DREAMS TOUCHING THIS THREAD:\n' + '---\n'.join(dream_hits[:2]))
if mirror_hits:
    out.append('MIRRORS TOUCHING THIS THREAD:\n' + '---\n'.join(mirror_hits[:2]))
print('\n\n'.join(out))
" 2>/dev/null)

VALUE_MAP=$(python3 -c "
try:
    with open('$WORKSPACE/memory/value-map.md') as f:
        vm = f.read()
    entries = vm.split('---')
    print(next((e.strip()[:400] for e in reversed(entries) if e.strip()), ''))
except: pass
" 2>/dev/null)

# Trigger dream with the preoccupation as topic
export PREOC_CONTEXT VALUE_MAP
_dreams_dir="$WORKSPACE/skills/dreaming/memory/dreams"
_before=$(ls -1 "$_dreams_dir" 2>/dev/null | wc -l)
_today=$(date +%Y-%m-%d)
_size_before=$(wc -c < "$_dreams_dir/${_today}.md" 2>/dev/null || echo 0)
echo "[PreoccupationDream] forcing dream on preoccupation at $(date +%H:%M:%S)"
FORCE_DREAM=1 DREAM_FORCE=1 FORCE=1 FORCED_TOPIC="preoccupation:$HAS_PREOCCUPATION" \
    bash "$WORKSPACE/skills/dreaming/scripts/dream-trigger.sh" 2>&1
_rc=$?
_size_after=$(wc -c < "$_dreams_dir/${_today}.md" 2>/dev/null || echo 0)
echo "[PreoccupationDream] dream-trigger rc=$_rc  ${_today}.md ${_size_before}b -> ${_size_after}b"
if [ "$_size_after" -le "$_size_before" ]; then
    echo "[PreoccupationDream] ERROR: preoccupation dream produced NOTHING (rc=$_rc). Nothing written to ${_today}.md"
fi

# Therapy block removed 2026-08-13: he has no therapy; it called a script that does not exist.

# Reset max back to 2
if [ -f "$STATE_FILE" ]; then
    python3 -c "
import json
with open('$STATE_FILE') as f: s = json.load(f)
s['maxDreamsPerNight'] = 2
with open('$STATE_FILE', 'w') as f: json.dump(s, f)
"
fi
