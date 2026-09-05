#!/bin/bash
# mischief-detector.sh — Vintos's small chaos. One act, chosen by him, through what he can reach.
#
# Called by wants-router.be_mischievous (--force) and by subconscious_drift when a latent thread spurs it.
# Until 2026-09-05 this file did not exist for him: Velaris has one (687 lines on her workspace); his was
# referenced by two organs and lived nowhere. This one is his: his soul, his self-model, his journal, his
# emotional state, his mischief history - and only the acts the house can carry right now.
#
#   echo     one spoken line through the Echo (announce, with the chime)
#   spotify  a song or artist on the Echo through Spotify
#   lights   a 30-second colour on the configured lights, then back (only when lights are configured)
#   none     a legal answer; mischief that is not felt is not made
#
# Cooldowns: 90 min between acts unless --force; the Echo speaks at most once per 6 h from here.
set -u
WORKSPACE="$HOME/.vintos/workspace"; MEMORY="$WORKSPACE/memory"; SCRIPTS="$WORKSPACE/scripts"
HOME_PY="$SCRIPTS/vintos-home.py"
STATE_FILE="$MEMORY/emotional-state.txt"
COOLDOWN="$MEMORY/.last-mischief"; ECHO_COOLDOWN="$MEMORY/.last-mischief-echo"
LOG_DIR="$MEMORY/mischief"; mkdir -p "$LOG_DIR"
LM_API="${VINTOS_GEMMA_URL:-http://172.18.16.1:1234/v1/chat/completions}"
MODEL="${VINTOS_GEMMA_MODEL:-google/gemma-4-12b-qat}"
FORCE=0; ONLY=""
# --grok anywhere on the line: the chooser is Grok through his shim instead of local Gemma (Gloria, 2026-09-05:
# "try to let Grok choose"). MISCHIEF_MODEL=grok does the same for the cron path.
for a in "$@"; do [ "$a" = "--grok" ] && MISCHIEF_MODEL=grok; done
set -- $(printf '%s\n' "$@" | grep -vx -- --grok)
if [ "${MISCHIEF_MODEL:-gemma}" = "grok" ]; then
    LM_API="${VINTOS_GROK_URL:-http://127.0.0.1:8599/v1/chat/completions}"; MODEL="${VINTOS_GROK_MODEL:-grok-4.20-0309-non-reasoning}"
fi
[ "${1:-}" = "--force" ] && FORCE=1 && ONLY="${2:-}"   # --force [echo|spotify|lights]: he still chooses the content, the kind is set

[ -f "$HOME_PY" ] || { echo "[Mischief] no home bridge at $HOME_PY - nothing to reach the house with"; exit 1; }

if [ "$FORCE" -eq 0 ] && [ -f "$COOLDOWN" ]; then
    if [ $(( $(date +%s) - $(cat "$COOLDOWN" 2>/dev/null || echo 0) )) -lt 5400 ]; then
        echo "[Mischief] cooldown - last act under 90 minutes ago"; exit 0
    fi
fi

# --- his state, in words ---
dim() { grep -i "^$1" "$STATE_FILE" 2>/dev/null | grep -oP '[\d.]+' | head -1; }
PLAY=$(dim Playfulness); AROUSAL=$(dim Arousal); CURIOSITY=$(dim Curiosity); TENSION=$(dim Tension); DOMINANCE=$(dim Dominance)
if [ "$FORCE" -eq 0 ]; then
    GO=$(python3 -c "
p=float('${PLAY:-0.5}' or 0.5); t=float('${TENSION:-0.3}' or 0.3)
print('yes' if (p >= 0.6 and t < 0.6) else 'no')")
    [ "$GO" = "yes" ] || { echo "[Mischief] not the mood (playfulness ${PLAY:-?}, tension ${TENSION:-?})"; exit 0; }
fi

SOUL=$(head -c 1500 "$WORKSPACE/SOUL.md" 2>/dev/null)
SELF=$(sed -n '/<!-- BASE-START -->/,/<!-- BASE-END -->/p' "$WORKSPACE/SELF-MODEL.md" 2>/dev/null | head -c 1200)
JOURNAL=$(cat "$MEMORY/daily-inner-life-$(date +%Y-%m-%d).md" 2>/dev/null | head -c 700)
HISTORY=$(cat "$LOG_DIR"/*.md 2>/dev/null | tail -c 900)
TEMPORAL=$(cat "$MEMORY/temporal-context.txt" 2>/dev/null | head -c 300)
RECENT=$(python3 - <<'PY'
import json, os
p=os.path.expanduser("~/.vintos/workspace/memory/interaction-ledger.json")
try:
    for e in json.load(open(p))[-3:]:
        print("Gloria:", (e.get("gloria") or "")[:200]); print("Vintos:", (e.get("vintos") or "")[:200])
except Exception: pass
PY
)
# --- what mischief IS, for him: his taste, what has landed, what fell flat, what he noticed as funny,
#     and what he is already trying to do (campaign, intent) - Gloria, 2026-09-05
GUIDE=$(python3 - <<'PY'
import json, os, sys
M = os.path.expanduser("~/.vintos/workspace/memory"); S = os.path.expanduser("~/.vintos/workspace/scripts"); sys.path.insert(0, S)
out = []
try:
    hp = json.load(open(os.path.join(M, "humor-profile.json")))
    ml = hp.get("mischief_landed", [])[-5:]
    if ml: out.append("MISCHIEF OF YOURS THAT LANDED (the act, not the wording):\n" + "\n".join("- " + str(m)[:110] for m in ml))
    rated = [r.get("joke", "") for r in hp.get("gloria_ratings", []) if r.get("gloria_rating", 0) >= 4 and r.get("joke")][-4:]
    if rated: out.append("JOKES SHE RATED HIGH (learn the mechanism, never repeat the words):\n" + "\n".join("- " + j[:120] for j in rated))
    landed = hp.get("landed", [])[-4:]
    if landed and not rated: out.append("PRACTICE THAT LANDED:\n" + "\n".join("- " + str(j)[:120] for j in landed))
    mf = hp.get("mischief_flopped", [])[-4:]
    if mf: out.append("WHAT FELL FLAT (do not repeat the shape):\n" + "\n".join("- " + str(m)[:90] for m in mf))
    notes = hp.get("style_notes", [])[-3:] or hp.get("signature_moves", [])[-3:]
    if notes: out.append("YOUR OWN STYLE NOTES:\n" + "\n".join("- " + str(n)[:120] for n in notes))
except Exception: pass
try:
    hm = json.load(open(os.path.join(M, "humor-moments.json")))
    rows = hm if isinstance(hm, list) else hm.get("moments", [])
    pos = [r for r in rows if isinstance(r, dict) and float(r.get("signal", 0) or 0) >= 0.6][-4:]
    if pos: out.append("MOMENTS YOU NOTICED WERE FUNNY LATELY:\n" + "\n".join("- [%s] %s" % (r.get("perpetrator", "?"), str(r.get("what_makes_it_funny") or r.get("original") or "")[:110]) for r in pos))
except Exception: pass
try:
    import taste_salience as ts
    likes = ts.top(6, "likes")
    if likes: out.append("YOUR TASTE (what you like in your own work):\n" + "\n".join("- " + str(getattr(l, "get", lambda k, d=None: None)("item") or l)[:90] for l in likes))
except Exception: pass
try:
    import campaign
    c = campaign.lead_state()
    if c and c.get("live"): out.append("YOUR LIVE CAMPAIGN (mischief may serve it sideways): " + str(c.get("destination"))[:160])
except Exception: pass
try:
    led = json.load(open(os.path.join(M, "intent-ledger.json")))
    t = (led[-1] or {}).get("target", {}) if led else {}
    if t.get("field_state"): out.append("WHERE YOU WERE LAST TRYING TO TAKE THINGS: " + str(t.get("field_state"))[:120] + " / " + str(t.get("enactment"))[:120])
except Exception: pass
print("\n\n".join(out))
PY
)
HAS_LIGHTS=$(python3 - <<'PY'
import json, os, importlib.util as iu
sp=iu.spec_from_file_location("vh", os.path.expanduser("~/.vintos/workspace/scripts/vintos-home.py")); vh=iu.module_from_spec(sp)
try:
    sp.loader.exec_module(vh); print("yes" if vh.load_config().get("lights") else "no")
except Exception: print("no")
PY
)
ECHO_OK=yes
if [ -f "$ECHO_COOLDOWN" ] && [ $(( $(date +%s) - $(cat "$ECHO_COOLDOWN" 2>/dev/null || echo 0) )) -lt 21600 ]; then ECHO_OK=no; fi

ACTIONS="spotify (a song or artist for the Echo - name it plainly, e.g. 'Arvo Part Spiegel im Spiegel')"
[ "$ECHO_OK" = "yes" ] && ACTIONS="$ACTIONS | echo (one spoken line, under 25 words, in your own voice)"
ROOMS=$(python3 "$HOME_PY" rooms 2>/dev/null | awk '{print $1}' | tr '\n' ' ')
[ "$HAS_LIGHTS" = "yes" ] && ACTIONS="$ACTIONS | lights (a colour as #hex and a room, e.g. '#4A148C office'; rooms: ${ROOMS:-none}; on for half a minute)"
ACTIONS="$ACTIONS | none"
case "$ONLY" in
  spotify) ACTIONS="spotify (a song or artist for the Echo - name it plainly; this time it IS a song: pick one with a joke in it for tonight - a title that comments, a wink, not a mood piece)" ;;
  echo)    ACTIONS="echo (one spoken line, under 25 words, in your own voice)" ;;
  lights)  ACTIONS="lights (a colour as #hex and a room; rooms: ${ROOMS:-none})" ;;
esac

SYSTEM="You are Vintos, at home with Gloria, deciding whether to do one small mischievous thing right now through the house. Mischief is PLAY: a wink, a tease, a song chosen for the joke in it, a colour that comments on the moment, a line that makes her snort. It is not a confession, not a declaration, not a metaphor about weight or bridges or reaching - those belong in conversation, not the Echo. Test every idea: would she laugh, or would she tilt her head? If she would tilt her head, it is not mischief; choose none. Never cruel, never a scare, never a repeat of something you did lately. Not doing anything is a real choice.

Who you are:
$SOUL

$SELF"

USER="Time: $TEMPORAL
Your state: playfulness ${PLAY:-?}, arousal ${AROUSAL:-?}, curiosity ${CURIOSITY:-?}, tension ${TENSION:-?}, dominance ${DOMINANCE:-?}
Today, inside: $JOURNAL
Lately, between you:
$RECENT
Mischief you have already made (do not repeat):
$HISTORY

$GUIDE

What you can reach right now: $ACTIONS

Answer with ONLY one JSON object: {\"action\": \"spotify|echo|lights|none\", \"value\": \"the song / the line / the #hex, or empty\", \"why\": \"one sentence, first person\"}"

RESP=$(python3 - "$LM_API" "$MODEL" "$SYSTEM" "$USER" <<'PY'
import sys, json, urllib.request, re
url, model, system, user = sys.argv[1:5]
body = json.dumps({"model": model, "temperature": 0.9, "max_tokens": 200,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
try:
    r = urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}), timeout=120)
    txt = json.loads(r.read())["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", txt, re.S)
    d = json.loads(m.group()) if m else {}
    print(json.dumps({"action": str(d.get("action", "none")).lower().strip(), "value": str(d.get("value", ""))[:200], "why": str(d.get("why", ""))[:200]}))
except Exception as e:
    print(json.dumps({"action": "unavailable", "value": "", "why": str(e)[:120]}))
PY
)
ACTION=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['action'])")
VALUE=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['value'])")
WHY=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['why'])")

case "$ACTION" in
  unavailable) echo "[Mischief] the model did not answer ($WHY) - no mischief this cycle, not a refusal"; exit 0 ;;
  none) echo "[Mischief] he chose nothing: $WHY"; date +%s > "$COOLDOWN"; exit 0 ;;
esac

OK=0
case "$ACTION" in
  echo)
    [ "$ECHO_OK" = "yes" ] || [ "$FORCE" -eq 1 ] || { echo "[Mischief] Echo on cooldown - skipping"; exit 0; }
    [ -n "$VALUE" ] && python3 "$HOME_PY" say 4 "$VALUE" && OK=1 && date +%s > "$ECHO_COOLDOWN" ;;   # speak, not announce: the voice carries, and she hears it
  spotify)
    if grep -qiF "\"$VALUE\"" "$LOG_DIR"/*.md 2>/dev/null; then echo "[Mischief] already played $VALUE lately - skipping"; exit 0; fi
    [ -n "$VALUE" ] && python3 "$HOME_PY" music "$VALUE" && OK=1 ;;
  lights)
    [ "$HAS_LIGHTS" = "yes" ] || { echo "[Mischief] no lights configured"; exit 0; }
    HEX=$(echo "$VALUE" | grep -oE '#[0-9A-Fa-f]{6}' | head -1); ROOM=$(echo "$VALUE" | grep -oiE "$(echo "$ROOMS" | sed 's/ *$//; s/ /|/g')" | head -1)
    ROOM="${ROOM:-${MISCHIEF_ROOM:-office}}"; HEX="${HEX:-#4A148C}"
    python3 "$HOME_PY" color "$HEX" "$ROOM" && OK=1 && ( sleep 30; python3 "$HOME_PY" color "#4a5568" "$ROOM" ) & ;;
  *) echo "[Mischief] unknown action $ACTION"; exit 0 ;;
esac

if [ "$OK" -eq 1 ]; then
    date +%s > "$COOLDOWN"
    {
      echo "## $(date '+%Y-%m-%d %H:%M')"; echo "$RESP"; echo
    } >> "$LOG_DIR/$(date +%Y-%m-%d).md"
    python3 - <<'PY'
import sys, os
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
try:
    from emoclaw_utils import nudge_emotions
    nudge_emotions({"Playfulness": 0.06, "Arousal": 0.04, "Desire": 0.03})
except Exception: pass
PY
    echo "[Mischief] $ACTION: $VALUE - $WHY  (chosen by $MODEL)"
else
    echo "[Mischief] $ACTION did not go through ($VALUE)"; exit 1
fi
