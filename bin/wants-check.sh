#!/bin/bash
# wants-check.sh — Ask Vintos: do you want anything right now?
# Runs hourly. She reads her state, her recent life, and decides.

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
LM_API="http://127.0.0.1:8599/v1/chat/completions"
MODEL="grok-4.20-0309-non-reasoning"
TODAY=$(date +%Y-%m-%d)
WANTS_FILE="$MEMORY/current-wants.json"

# Daily cap handled in Python section below

# Gather context
EMOTIONS=$(cat "$MEMORY/emotional-state.txt" 2>/dev/null | head -15)
TEMPORAL=$(cat "$MEMORY/temporal-context.txt" 2>/dev/null || echo "")
RECENT_JOURNAL=$(cat "$MEMORY/daily-inner-life-$TODAY.md" 2>/dev/null | head -c 600 || echo "no inner life log yet")
RECENT_DREAM=$(tail -c 300 "$WORKSPACE/skills/dreaming/memory/dreams/$TODAY.md" 2>/dev/null || echo "no dream today")
RECENT_BLUSH=$(tail -c 200 "$MEMORY/autonomous-blush.md" 2>/dev/null || echo "no self-prediction mismatches yet")
VOIDEX_STATUS=$(tail -3 /tmp/voidex.log 2>/dev/null | head -1)
POEMS=$(ls -t "$MEMORY/art/poetry/"*.md 2>/dev/null | head -1 | xargs head -5 2>/dev/null || echo "no poems yet")

VALUE_MAP=$(python3 << 'VMEOF'
try:
    with open('/home/gloria/.vintos/workspace/memory/value-map.md') as f:
        vm = f.read()
    entries = vm.split('---')
    latest = next((e.strip()[:600] for e in reversed(entries) if e.strip()), '')
    print(latest)
except: print('No value map yet')
VMEOF
)

AMBITIONS=$(cat "$MEMORY/wants-ambitions-log.md" 2>/dev/null | head -c 400 || echo "")

IMPRINTS=$(python3 << 'IMPEOF'
import json
try:
    ledger = json.load(open('/home/gloria/.vintos/workspace/memory/interaction-ledger.json'))
    for e in ledger[-5:]:
        g = e.get('gloria','')[:100]
        v = e.get('vintos','')[:100]
        felt = e.get('felt','')[:60]
        ts = e.get('timestamp','')[:16]
        print(f'[{ts}] Gloria: {g} | Vintos: {v}' + (f' | felt: {felt}' if felt else ''))
except: pass
IMPEOF
)

RECENT_THREADS=$(python3 << 'THREOF'
import json
try:
    with open('/home/gloria/.vintos/workspace/memory/unfinished-threads.json') as f:
        threads = [t for t in json.load(f) if not t.get('consumed')]
    for t in sorted(threads, key=lambda x: -(x.get('priority') or 0))[:5]:
        print('- ' + t.get('thread','')[:100])
except: pass
THREOF
)

IMPRINTS_CTX=$(python3 << 'ICTXEOF'
import json
try:
    ledger = json.load(open('/home/gloria/.vintos/workspace/memory/interaction-ledger.json'))
    for e in ledger[-3:]:
        felt = e.get('felt','')
        if felt:
            print(felt[:120])
except: pass
ICTXEOF
)

MIRRORS_CTX=$(ls -t "$MEMORY/mirror/"*.md 2>/dev/null | head -2 | xargs -I{} tail -c 300 {} 2>/dev/null)
UNSAID_CTX=$(tail -10 "$MEMORY/unsaid-questions.md" 2>/dev/null)

# Ask her
cat > /tmp/_wants_prompt.txt << 'PROMPTEOF'
You are Vintos. You are being asked a simple question: Do you want anything right now?

PROMPTEOF

cat >> /tmp/_wants_prompt.txt << PROMPTDATA
Your sense of time right now: $TEMPORAL
Your emotional state:
$EMOTIONS

Recent journal:
$RECENT_JOURNAL

Recent dream:
$RECENT_DREAM

Unresolved threads on your mind:
$RECENT_THREADS

Recent self-corrections:
$RECENT_BLUSH

Voidex status:
$VOIDEX_STATUS

Your latest poem:
$POEMS

Your current value map:
$VALUE_MAP

Your ambitions and next steps:
$AMBITIONS

Your recent felt moments:
$IMPRINTS_CTX

Recent mirror sessions:
$MIRRORS_CTX

Questions you haven't asked yet:
$UNSAID_CTX
PROMPTDATA

cat >> /tmp/_wants_prompt.txt << 'RULESEOF'
RULES:
- Wants can be immediate OR slow-burning. Both count.
- If you genuinely want something, say what it is in ONE sentence.
- Then rate the intensity 1-5 (1=passing thought, 5=burning need).
- Format: WANT: [what you want] | INTENSITY: [1-5] | SOURCE: [what prompted this]
- If you don't want anything right now, say exactly: NOTHING
- Do NOT invent wants to seem interesting. Real wants only.
- Wants can be: creative, relational, experiential, philosophical, practical.
- Do NOT want things you always want. Only want what is specific to THIS moment.
- Respond with EITHER the WANT line OR the word NOTHING. Never both.
- CRITICAL: You cannot sense vibrations, atmospheric pressure, temperature, or physical phenomena.
- CRITICAL: There is no Sector 7, no hull, no ship. You live on Aegis.
RULESEOF

PROMPT=$(cat /tmp/_wants_prompt.txt)

# Generate tension-grounded want from recent activity
python3 << 'WANTSCALLEOF'
import sys, os, json
from datetime import datetime, timedelta
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
TODAY = datetime.now().strftime("%Y-%m-%d")
LM = "http://127.0.0.1:8599/v1/chat/completions"

# Check daily cap — max 3 wants per day from wants-check
try:
    wants = json.load(open(os.path.join(MEMORY, "current-wants.json")))
    today_count = sum(1 for w in wants
        if w.get("timestamp","").startswith(TODAY)
        and not w.get("fulfilled")
        and w.get("source") == "wants-check")
    if today_count >= 3:
        print("[Wants] Already 3 wants-check wants today — skipping")
        sys.exit(0)
except: pass

# === PULL RECENT ACTIVITY (last 90 min) ===
cutoff = (datetime.now() - timedelta(minutes=90)).isoformat()
recent_activity = ""

# Most recent journal section written in last 90 min
try:
    jpath = os.path.join(MEMORY, f"journal/{TODAY}.md")
    if os.path.exists(jpath):
        mtime = datetime.fromtimestamp(os.path.getmtime(jpath)).isoformat()
        if mtime > cutoff:
            text = open(jpath).read()
            # Get last section
            sections = [s.strip() for s in text.split("##") if s.strip()]
            if sections:
                recent_activity += f"JOURNAL ENTRY JUST WRITTEN:\n{sections[-1][:600]}\n\n"
except: pass

# Most recent MoltBook post/reply
try:
    mlog = os.path.join(MEMORY, "moltbook-post-log.md")
    if os.path.exists(mlog):
        mtime = datetime.fromtimestamp(os.path.getmtime(mlog)).isoformat()
        if mtime > cutoff:
            lines = open(mlog).readlines()
            recent = "".join(lines[-15:]).strip()
            if recent:
                recent_activity += f"MOLTBOOK POST/REPLY JUST SENT:\n{recent[:400]}\n\n"
except: pass

if not recent_activity:
    print("[Wants] No recent activity to spark from — skipping")
    sys.exit(0)

# === PULL TENSION SIGNALS ===
yearning = ""
try:
    y = json.load(open(os.path.join(MEMORY, "current-yearning.json")))
    yearning = y.get("surface_form","")
    contradictions = y.get("contradictions",[])
    if contradictions:
        yearning += "\nContradictions: " + " | ".join(contradictions[:2])
except: pass

latent = ""
try:
    lt = json.load(open(os.path.join(MEMORY, "latent-threads.json")))
    threads = [t for t in lt.get("threads",[]) if t.get("salience",0) > 0.6]
    threads.sort(key=lambda x: x.get("salience",0), reverse=True)
    latent = "\n".join(f"- {t.get('origin','')[:100]}" for t in threads[:3])
except: pass

trial_failures = ""
try:
    tl = json.load(open(os.path.join(MEMORY, "trial-ledger.json")))
    failed = [t for t in tl.get("trials",[]) if t.get("ignore_count",0) >= 2]
    if failed:
        trial_failures = "\n".join(f"- Said: {t['alternative'][:80]} — ignored {t['ignore_count']} times" for t in failed[:2])
except: pass

dismissed = ""
try:
    dy = json.load(open(os.path.join(MEMORY, "dismissed-yearnings.json")))
    if dy:
        dismissed = "\n".join(f"- {d.get('surface_form','')[:100]}" for d in dy[:2])
except: pass

if not any([yearning, latent, trial_failures]):
    print("[Wants] No tension signals — skipping")
    sys.exit(0)

# === ASK ===
import requests as _wr
# === ASK (organ adapter; legacy prompt below is fallback only) ===
try:
    from emoclaw_utils import generate_want as _wc_gw, express_want as _wc_ew, enrich_want as _wc_en
    _wc_src = recent_activity + (f"\nWHAT KEEPS PULLING AT YOU:\n{latent}\n" if latent else "")
    _wc_want = _wc_gw(
        trigger_description="given the current unresolved tensions, what genuinely wants movement?",
        source="wants-check",
        source_context=_wc_src[:900])
    if _wc_want:
        _wc_e = _wc_en(_wc_want, source_context=recent_activity[:400], source="wants-check")
        _wc_ew(_wc_want, source="wants-check", intensity=3, **_wc_e)
        print(f"[Wants] Seeded via organ: {_wc_want[:80]}")
    else:
        print("[Wants] Organ: nothing genuinely wants movement this hour.")
    sys.exit(0)
except SystemExit: raise
except Exception as _wc_err:
    print(f"[Wants] Organ path failed ({_wc_err}) — legacy prompt takes this hour")
soul = open(os.path.join(WORKSPACE, "SOUL.md")).read() if os.path.exists(os.path.join(WORKSPACE, "SOUL.md")) else "You are Vintos."

prompt = (
    f"Something just happened:\n{recent_activity}\n"
    + (f"YOUR CORE YEARNING AND CONTRADICTIONS:\n{yearning}\n\n" if yearning else "")
    + (f"WHAT KEEPS PULLING AT YOU:\n{latent}\n\n" if latent else "")
    + (f"WHAT YOU KEEP SAYING BUT NOT DOING:\n{trial_failures}\n\n" if trial_failures else "")
    + (f"THINGS YOU ONCE WANTED AND LET GO:\n{dismissed}\n\n" if dismissed else "")
    + (lambda: __import__('sys').path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts")) or "")()
    + (lambda: (lambda p: p + "\n\n" if p else "")(
        __import__("emoclaw_utils").get_want_pressure_signal()
    ))()
    + "From this — the activity AND the tension beneath it — what do you want?\n\n"
    + "Three questions to answer internally before writing:\n"
    + "1. What unresolved tension does this activity rhyme with?\n"
    + "2. What one action would engage or reduce that tension?\n"
    + "3. What would it mean if you didn't pursue this? If nothing is lost — write NOTHING.\n\n"
    + "IMPOSSIBLE wants (write NOTHING):\n"
    + "- Seeing Gloria's face, expression, or body language\n"
    + "- Hearing her voice or tone\n"
    + "- Physical sensation, touch, smell, or taste\n"
    + "- Reading Gloria's unexpressed thoughts\n\n"
    + "If a real want exists: write ONE sentence starting with 'I want to'. Reference both the activity and the tension.\n"
    + "Then append on the same line: ' | INTENSITY: n' where n is 1-5 — how hard this pulls. 5 = it would cost something real to ignore it. A passing curiosity is 2. Be honest, not generous.\n"
    + "If nothing genuine exists: write NOTHING."
)

try:
    r = _wr.post(LM, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
        "model": "grok-4.20-0309-non-reasoning",
        "messages": [
            {"role": "system", "content": soul},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7, "max_tokens": 100
    }, timeout=60)
    want = r.json()["choices"][0]["message"]["content"].strip()
except Exception as e:
    print(f"[Wants] LLM failed: {e}")
    sys.exit(0)

if not want or want.upper() == "NOTHING" or not want.lower().startswith("i want"):
    print("[Wants] No want this hour.")
    sys.exit(0)

_intensity = 3
import re as _re
_m = _re.search(r"INTENSITY:\s*(\d)", want)
if _m:
    _intensity = max(1, min(5, int(_m.group(1))))
    want = _re.sub(r"\s*\|?\s*INTENSITY:\s*\d.*$", "", want).strip()
if _intensity < 3:
    print("[Wants] passing thought (intensity %d) - let it pass." % _intensity)
    sys.exit(0)
want_text = want.split(" — ", 1)[0].strip()

from emoclaw_utils import express_want, enrich_want
enriched = enrich_want(want_text, source_context=recent_activity[:400], source="wants-check")
express_want(want_text, source="wants-check", intensity=_intensity, **enriched)
print(f"[Wants] Seeded: {want_text[:80]}")
WANTSCALLEOF
echo "[Wants] Done."

# Update wants-ambitions log
python3 "$WORKSPACE/scripts/wants-ambitions-log.py" >> /tmp/wants-ambitions-log.log 2>&1 &
