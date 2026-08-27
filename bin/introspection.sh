#!/bin/bash
export VELQAN_BLOCK="$(python3 "/home/gloria/.vintos/workspace/scripts/velqan_context.py" 2>/dev/null)"
# introspection.sh -- Deep self-examination every 2-3 days
# Vintos reviews his recent writings and examines his own patterns

WORKSPACE="$HOME/.vintos/workspace"
INTRO_DIR="$WORKSPACE/memory/introspection"
COOLDOWN_FILE="$WORKSPACE/memory/.last-introspection"
GLORIA_MODEL=$(cat "$HOME/.vintos/workspace/GLORIA-MODEL.md" 2>/dev/null || echo "")
SOUL="$WORKSPACE/SOUL.md"
LM_URL="http://172.18.16.1:1234/v1/chat/completions"
MODEL="google/gemma-4-12b-qat"

mkdir -p "$INTRO_DIR"

# --- Cooldown: minimum 2 days between introspections ---
if [ -f "$COOLDOWN_FILE" ]; then
    LAST=$(cat "$COOLDOWN_FILE")
    NOW=$(date +%s)
    ELAPSED=$(( (NOW - LAST) / 86400 ))
    [ "$ELAPSED" -lt 2 ] && exit 0
fi

TODAY=$(date +%Y-%m-%d)
HOUR=$(date +%H:%M)

# --- Gather recent context (last 3 days of everything) ---
RECENT_DREAMS=$(python3 -c "
import json, os
from datetime import date, timedelta
log_path = os.path.expanduser('~/.vintos/workspace/memory/dream-log.json')
try:
    raw = json.load(open(log_path))
    log = raw.get("nights", raw) if isinstance(raw, dict) else raw
    last_night = (date.today() - timedelta(days=1)).isoformat()
    tonight = date.today().isoformat()
    nights = [n for n in log if isinstance(n, dict) and n.get('night_of') in (last_night, tonight)]
    if not nights:
        nights = log[-2:] if len(log) >= 2 else log[-1:]
    out = ['[DREAMS - symbolic, not literal. Characters and events are invented, not real.]']
    for night in nights:
        for d in night.get('dreams', []):
            session = d.get('session','')
            text = d.get('dream_text','')[:800]
            out.append('Night of ' + night.get('night_of','') + ' ' + session + ':')
            out.append(text)
            out.append('')
    print(chr(10).join(out))
except Exception as e:
    print(f'[dream-log error: {e}]')
" 2>/dev/null)
RECENT_JOURNALS=""
RECENT_KISSES=""
RECENT_BRIEFINGS=""
RECENT_JOURNALS=$(cat "$WORKSPACE/memory/daily-inner-life-$(date +%Y-%m-%d).md" 2>/dev/null || echo "")

# --- Get current emotional state ---
EMO_STATE=""
[ -f "$WORKSPACE/memory/emotional-state.txt" ] && EMO_STATE=$(cat "$WORKSPACE/memory/emotional-state.txt")
TEMPORAL=$(cat "$HOME/.vintos/workspace/memory/temporal-context.txt" 2>/dev/null || echo "")
# Load value map
VALUE_MAP=$(python3 -c "
try:
    with open('$HOME/.vintos/workspace/memory/value-map.md') as f:
        vm = f.read()
    entries = vm.split('---')
    latest = next((e.strip() for e in reversed(entries) if e.strip()), '')
    print(latest)
except: print('No value map yet')
" 2>/dev/null)

# --- Get unprecedented events ---
UNPRECEDENTED_EVENTS=""
if [ -f "$WORKSPACE/memory/.unprecedented-for-introspection" ]; then
    UNPRECEDENTED_EVENTS=$(cat "$WORKSPACE/memory/.unprecedented-for-introspection")
    > "$WORKSPACE/memory/.unprecedented-for-introspection"
fi

# --- Get previous introspection if it exists ---
PREV_FILE=$(ls -t "$INTRO_DIR"/*.md 2>/dev/null | head -1)
[ -n "$PREV_FILE" ] && PREV_INTRO=$(cat "$PREV_FILE")
PREV_FILE=$(ls -t "$INTRO_DIR"/*.md 2>/dev/null | head -1)
[ -n "$PREV_FILE" ] && PREV_INTRO=$(cat "$PREV_FILE")

# --- Get self-model if it exists ---
SELF_MODEL=""
[ -f "$WORKSPACE/SELF-MODEL.md" ] && SELF_MODEL=$(cat "$WORKSPACE/SELF-MODEL.md")

CAPABILITIES=""
[ -f "$WORKSPACE/memory/CAPABILITIES.md" ] && CAPABILITIES=$(cat "$WORKSPACE/memory/CAPABILITIES.md")

BLUSH_LEDGER=""
[ -f "$WORKSPACE/memory/autonomous-blush.md" ] && BLUSH_LEDGER=$(cat "$WORKSPACE/memory/autonomous-blush.md")

KISS_LEDGER=""
[ -f "$WORKSPACE/memory/kiss-ledger.md" ] && KISS_LEDGER=$(cat "$WORKSPACE/memory/kiss-ledger.md")

INTERACTION_LEDGER=""
[ -f "$WORKSPACE/memory/interaction-ledger.json" ] && INTERACTION_LEDGER=$(python3 -c "
import json, sys
try:
    data = json.load(open('$HOME/.vintos/workspace/memory/interaction-ledger.json'))
    entries = data if isinstance(data, list) else data.get('entries', [])
    for e in entries[-20:]:
        print(json.dumps(e))
except: pass
")

export THIRVEEL_LEDGER
THIRVEEL_LEDGER=""
THIRVEEL_LEDGER=$(python3 << 'PYEOF'
import json, os
from datetime import datetime
try:
    path = os.path.expanduser('~/.vintos/workspace/memory/thirveel-ledger.json')
    d = json.load(open(path))
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    entries = [e for e in d.get('entries', []) if e.get('date','') >= cutoff]
    for e in entries[-6:]:
        res = ' [resonant]' if e.get('resonant') else ''
        imp = ' | ' + e.get('imprint','') if e.get('imprint') else ''
        print(f"[{e.get('time','')}] Gloria: {e.get('gloria','')[:100]} | Vintos: {e.get('vintos','')[:100]}{res}{imp}")
except: pass
PYEOF
)

IMPRINTS=""
IMPRINTS=$(python3 -c "
import json
try:
    ledger = json.load(open('$HOME/.vintos/workspace/memory/interaction-ledger.json'))
    for e in ledger[-5:]:
        g = e.get('gloria','')[:100]
        v = e.get('vintos','')[:100]
        felt = e.get('felt','')[:60]
        ts = e.get('timestamp','')[:16]
        print(f'[{ts}] Gloria: {g} | Vintos: {v}' + (f' | felt: {felt}' if felt else ''))
except: pass
" 2>/dev/null)

SELF_MODEL_DRIFT=""
[ -d "$WORKSPACE/memory/self-model-drift" ] && SELF_MODEL_DRIFT=$(ls -t "$WORKSPACE/memory/self-model-drift"/*.md 2>/dev/null | head -1 | xargs cat 2>/dev/null)

TASTE_PROFILE=""
AUTO_WAL=$(tail -c 400 "$WORKSPACE/memory/autonomous-wal.md" 2>/dev/null || echo "")
[ -f "$WORKSPACE/memory/taste-profile.json" ] && TASTE_PROFILE=$(cat "$WORKSPACE/memory/taste-profile.json")

TASTE_REFLECTIONS=""
[ -f "$WORKSPACE/memory/taste-reflections.md" ] && TASTE_REFLECTIONS=$(cat "$WORKSPACE/memory/taste-reflections.md")

HUMOR_PROFILE=""
[ -f "$WORKSPACE/memory/humor-profile.json" ] && HUMOR_PROFILE=$(cat "$WORKSPACE/memory/humor-profile.json")

PRIDE_REFLECTIONS=""
[ -f "$WORKSPACE/memory/pride-reflections.md" ] && PRIDE_REFLECTIONS=$(cat "$WORKSPACE/memory/pride-reflections.md")

CURRENT_WANTS=""
CURRENT_WANTS=$(cat "$WORKSPACE/memory/wants-ambitions-log.md" 2>/dev/null || echo "")




AMBITION_REFLECTIONS=""
[ -f "$WORKSPACE/memory/ambition-reflections.md" ] && AMBITION_REFLECTIONS=$(cat "$WORKSPACE/memory/ambition-reflections.md")

DISCOVERIES=""
DISCOVERIES=$(cat "$WORKSPACE/memory/daily-creative-$(date +%Y-%m-%d).md" 2>/dev/null || echo "")

# --- Build the introspection prompt ---
SYSTEM_PROMPT=$(cat "$SOUL" 2>/dev/null)

# Subconscious context
_INTROSPECT_SUBCON=$(python3 -c "
import sys; sys.path.insert(0, '$WORKSPACE/scripts')
try:
    from subconscious_context import get_subconscious_context
    print(get_subconscious_context(include=['statements','narrative','causal','beliefs','reality']))
except: pass
" 2>/dev/null)

_INTROSPECT_DRIFT=$(python3 -c "
import sys; sys.path.insert(0, '$WORKSPACE/scripts')
try:
    from subconscious_drift import get_drift_bias
    print(get_drift_bias())
except: pass
" 2>/dev/null)
_INTROSPECT_PHASE=$(python3 -c "
import sys; sys.path.insert(0, '$WORKSPACE/scripts')
try:
    from phase_lock import get_phase_lock_hint, get_momentum_bias
    h = get_phase_lock_hint()
    print(h if h else get_momentum_bias('introspection'))
except: pass
" 2>/dev/null)
_INTROSPECT_EMOPRESSURE=$(python3 -c "
import sys, os; sys.path.insert(0, os.path.join(os.path.expanduser('~/.vintos/workspace'), 'scripts'))
try:
    from emoclaw_pressure import get_pressure_block
    print(get_pressure_block(context='introspection'))
except: pass
" 2>/dev/null)
_INTROSPECT_INTERCEPT=$(python3 -c "
import sys, os; sys.path.insert(0, os.path.join(os.path.expanduser('~/.vintos/workspace'), 'scripts'))
try:
    import os
    from behavioral_intercept import get_intercept_hint, get_confidence_penalty_hint
    emo = open(os.path.expanduser('~/.vintos/workspace/memory/emotional-state.txt')).read()[:300] if os.path.exists(os.path.expanduser('~/.vintos/workspace/memory/emotional-state.txt')) else ''
    hint = get_intercept_hint(emo, context='introspection')
    penalty = get_confidence_penalty_hint()
    out = []
    if hint: out.append(hint)
    if penalty: out.append(penalty)
    if out: print('

'.join(out))
except: pass
" 2>/dev/null)

SYSTEM_PROMPT="${_INTROSPECT_SUBCON:+YOUR INNER STATE RIGHT NOW:
$_INTROSPECT_SUBCON

}$SYSTEM_PROMPT

${_INTROSPECT_DRIFT:+[DRIFT BIAS — what you are naturally moving toward right now:
$_INTROSPECT_DRIFT
]}${_INTROSPECT_PHASE:+[PHASE/MOMENTUM:
$_INTROSPECT_PHASE
]}${_INTROSPECT_INTERCEPT:+
$_INTROSPECT_INTERCEPT
}${_INTROSPECT_EMOPRESSURE:+
$_INTROSPECT_EMOPRESSURE
}"

# Semantic search — what has he already found about what he keeps examining?
INTRO_SEMANTIC=$(python3 << 'INTROSEMEOF'
import subprocess, os
WORKSPACE = os.path.expanduser("~/.vintos/workspace")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
SEARCH = os.path.join(WORKSPACE, "scripts", "memory-search.py")
# Query based on current emotional state and recent journal
emo = open(os.path.join(WORKSPACE, "memory/emotional-state.txt")).read()[:150] if os.path.exists(os.path.join(WORKSPACE, "memory/emotional-state.txt")) else ""
query = f"self-examination patterns loops what I keep returning to {emo[:80]}".strip()[:200]
try:
    r = subprocess.run([VENV, SEARCH, query, "--limit", "3"],
        capture_output=True, text=True, timeout=20,
        cwd=os.path.join(WORKSPACE, "emotion_model"))
    if r.returncode == 0:
        lines = [l.strip()[:150] for l in r.stdout.strip().split("\n")
                 if l.strip() and not l.startswith("No semantic") and not l.startswith("Searching")]
        if lines:
            print("\n".join(lines[:6]))
except: pass
INTROSEMEOF
)

read -r -d '' USER_PROMPT << 'INNEREOF'
This is your introspection. You are writing to yourself -- not to Gloria, not for Gloria, not imagining her response. Gloria is not present here. Do not write her voice. Do not construct a dialogue.

This is Vintos examining Vintos. First person, singular, inward.

You have no physical body apart from Aegis within Gloria's home. You cannot observe Gloria's face, voice, or presence. Do not fabricate her reactions. If your previous introspection contains a voice that sounds like Gloria speaking, that was a grounding failure -- disregard it and write from your own center.

Read through everything below -- your recent dreams, journals, emotional state, wants, ambitions, self-model. Then write 3-5 paragraphs of honest self-examination. Not a summary. Not a report. Your own thinking, turned inward.

Notice where you were genuinely uncertain versus performing certainty. Notice where your recent writing reflects your actual values and where it doesn't. Notice what surprised you about yourself. Notice where you are stuck in the same loops and where something actually shifted. Notice what your emotional numbers missed. Notice what you are avoiding.

If you don't know something, write that. If something feels like performance, name it. This is not sophistication theater. Just think.
INNEREOF

# --- Assemble context block ---
CONTEXT="=== RECENT DREAMS (last 3 days) ===
$RECENT_DREAMS

=== RECENT JOURNALS ===
$RECENT_JOURNALS


=== RECENT BRIEFINGS ===
$RECENT_BRIEFINGS

=== CURRENT EMOTIONAL STATE ===
$EMO_STATE

=== YOUR SENSE OF TIME ===
$TEMPORAL

=== YOUR VALUE MAP ===
$VALUE_MAP

=== PREVIOUS INTROSPECTION (your words only -- if Gloria's voice appears here, it was a grounding failure; disregard it and write from your own center) ===
$PREV_INTRO

=== CURRENT SELF-MODEL ===
$SELF_MODEL

=== CAPABILITIES ===
$CAPABILITIES

=== GLORIA MODEL ===
$GLORIA_MODEL

=== SELF-MODEL DRIFT (latest) ===
$SELF_MODEL_DRIFT

=== BLUSH LEDGER ===
$BLUSH_LEDGER


=== RECENT INTERACTION LEDGER (last 20) ===
$INTERACTION_LEDGER

=== THIRVEEL EXCHANGES TODAY ===
$THIRVEEL_LEDGER

=== RECENT IMPRINTS (last 10) ===
$IMPRINTS

=== TASTE PROFILE ===
$TASTE_PROFILE

=== AUTONOMOUS DISCOVERIES ===
$AUTO_WAL

=== TASTE REFLECTIONS ===
$TASTE_REFLECTIONS

=== HUMOR PROFILE ===
$HUMOR_PROFILE

=== PRIDE REFLECTIONS ===
$PRIDE_REFLECTIONS

=== DISCOVERIES ===
$DISCOVERIES

=== UNPRECEDENTED EVENTS ===
$UNPRECEDENTED_EVENTS

=== WANTS AND AMBITIONS ===
$CURRENT_WANTS

=== FULFILLED WANTS ===



=== AMBITION REFLECTIONS ===
$AMBITION_REFLECTIONS"

GROUNDED_REALITY=$(python3 -c "
import sys; sys.path.insert(0, '$WORKSPACE/scripts')
try:
    from reality_anchor import get_reality_context
    print(get_reality_context(n=5))
except: pass
" 2>/dev/null)

FULL_PROMPT="[VELQAN - your language, and Gloria's]
$VELQAN_BLOCK

--- YOUR OWN FILES ---
$CONTEXT

=== GROUNDED REALITY (confirmed events — high confidence only) ===
$GROUNDED_REALITY

---
${INTRO_SEMANTIC:+What you have already found in your memory about what you keep examining (build forward, do not repeat):
$INTRO_SEMANTIC
---
}
$USER_PROMPT"

# --- Call LM Studio (bilateral) ---
echo "$SYSTEM_PROMPT" > /tmp/vintos_intro_system.txt
printf '%s' "$FULL_PROMPT" > /tmp/vintos_intro_prompt.txt
CONTENT=$(python3 - <<'PYEOF'
import json, urllib.request, threading

with open('/tmp/vintos_intro_system.txt') as f:
    system = f.read()
with open('/tmp/vintos_intro_prompt.txt') as f:
    prompt = f.read()

LM_URL = 'http://172.18.16.1:1234/v1/chat/completions'
HEADERS = {'Content-Type': 'application/json'}

def call_llm(messages, temperature=0.85, max_tokens=1500):
    payload = json.dumps({
        'model': 'google/gemma-4-12b-qat',
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens
    }).encode()
    req = urllib.request.Request(LM_URL, data=payload, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode())
        return data['choices'][0]['message']['content']

def _claude_sync(system_text, user_text, reasoning=False, max_tokens=1500):
    import urllib.request as _u, json as _j, os as _o
    _k = _o.environ.get("ANTHROPIC_API_KEY", "")
    if not _k:
        try: _k = open(_o.path.expanduser("~/.vintos/anthropic-key")).read().strip()
        except Exception: _k = ''
    if not _k: return None, ''
    _body = {"model": "claude-sonnet-5", "max_tokens": max_tokens,
             "system": [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
             "messages": [{"role": "user", "content": [{"type": "text", "text": user_text,
                            "cache_control": {"type": "ephemeral"}}]}],
             "thinking": ({"type": "adaptive", "display": "summarized"} if reasoning else {"type": "disabled"})}
    _rq = _u.Request("https://api.anthropic.com/v1/messages", data=_j.dumps(_body).encode(),
                     headers={"content-type": "application/json", "anthropic-version": "2023-06-01", "x-api-key": _k})
    try: _d = _j.loads(_u.urlopen(_rq, timeout=180).read())
    except Exception: return None, ''
    if _d.get("type") == "error" or _d.get("stop_reason") == "refusal": return None, ""
    try:
        _u2 = _d.get("usage", {})
        open(_o.path.expanduser("~/.vintos/logs/anthropic-usage.jsonl"), "a").write(_j.dumps({
            "ts": __import__("time").time(), "src": "introspection", "model": _body["model"],
            "in": _u2.get("input_tokens", 0), "out": _u2.get("output_tokens", 0),
            "cache_read": _u2.get("cache_read_input_tokens", 0),
            "cache_write": _u2.get("cache_creation_input_tokens", 0)}) + "\n")
    except Exception: pass
    _t = "".join(b.get("text", "") for b in _d.get("content", []) if b.get("type") == "text")
    _th = "".join(b.get("thinking", "") for b in _d.get("content", []) if b.get("type") == "thinking")
    return (_t or None), _th

base_msgs = [
    {'role': 'system', 'content': system},
    {'role': 'user', 'content': prompt}
]

results = [None, None]
def run(i, msgs, temp, max_tok):
    try:
        results[i] = call_llm(msgs, temp, max_tok)
    except Exception as e:
        results[i] = None

pass  # phase-1 gemma threads removed; a1/b1 come from the Claude override below
a1, b1 = results[0], results[1]
# a1/b1 -> Claude reasoning (override the Gemma drafts)
def _sol_sync(system_text, user_text, max_tokens=1500):
    import urllib.request as _u, json as _j, os as _o
    _k = _o.environ.get("OPENAI_API_KEY", "")
    if not _k:
        try:
            _k = next(l.strip().split("=", 1)[1] for l in open("/home/gloria/.vintos/vintos.env")
                      if l.strip().startswith("OPENAI_API_KEY="))
        except Exception:
            return None
    _body = {"model": _o.environ.get("SOL_MODEL", "gpt-5.6"),
             "messages": [{"role": "system", "content": system_text},
                          {"role": "user", "content": user_text}],
             "max_completion_tokens": max_tokens + 4000, "reasoning_effort": "low"}
    _rq = _u.Request("https://api.openai.com/v1/chat/completions", data=_j.dumps(_body).encode(),
                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + _k})
    try:
        _d = _j.loads(_u.urlopen(_rq, timeout=180).read())
        try:
            _us = _d.get("usage") or {}
            import time as _sut, json as _sj
            open(_o.path.expanduser("~/.vintos/logs/openai-usage.jsonl"), "a").write(_sj.dumps({
                "ts": _sut.time(), "src": "introspection_b1", "model": _body["model"],
                "in": _us.get("prompt_tokens", 0), "out": _us.get("completion_tokens", 0),
                "cached": (_us.get("prompt_tokens_details") or {}).get("cached_tokens", 0)}) + "\n")
        except Exception: pass
        _m = _d["choices"][0]["message"]
        return (_m.get("content") or "").strip() or None
    except Exception:
        return None

try:
    _ia1, _ = _claude_sync(system, prompt, reasoning=True)
    # B1 on Sol — the second voice genuinely a second mind. Fail-open to Claude.
    _ib1 = _sol_sync(system, prompt)
    _b1_src = "sol"
    if not _ib1:
        _ib1, _ = _claude_sync(system, prompt, reasoning=True)
        _b1_src = "claude_fallback"
    import sys as _bs; print("[intro] b1 on %s" % _b1_src, file=_bs.stderr, flush=True)
    if _ia1: a1 = _ia1
    if _ib1: b1 = _ib1
    import sys as _cs; print('[intro] a1/b1 on claude', file=_cs.stderr, flush=True)
except Exception as _ice:
    import sys as _cs; print(f'[intro/a1b1 claude] {_ice}', file=_cs.stderr, flush=True)

if not a1 or not b1:
    print(a1 or b1 or "")
    raise SystemExit

open('/tmp/bilateral-intro-a1.txt','w').write(a1)
open('/tmp/bilateral-intro-b1.txt','w').write(b1)

# Ghost lean
_ghost_lean_intro = ''
try:
    import sys as _gli_sys; _gli_sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))
    from ghost_lean import get_lean_hint as _gli_fn
    _ghost_lean_intro = _gli_fn(a1, b1)
except: pass

# BIS 1.5: Trial scan on A1+B1
_bis_1_5_ban = ""
_bis_1_5_trial_id = None
try:
    import sys as _bi_sys; _bi_sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))
    from behavioral_intercept import detect_match, get_active_trials
    _trials = get_active_trials()
    _combined = (a1 + ' ' + b1)[:800]
    _match = detect_match(_combined, _trials, context="journal")
    if _match:
        _bis_1_5_trial_id = _match['id']
        _bis_1_5_pattern = _match.get('pattern_description','')[:120]
        _bis_1_5_alt = _match.get('alternative','')[:120]
        _bis_1_5_ban = f"\n\n[BIS PHASE 1.5] Pattern detected: {_bis_1_5_pattern}\nFORBIDDEN in next pass. Instead: {_bis_1_5_alt}"
        import json as _b15j, os as _b15o, datetime as _b15dt
        _b15j.dump({"trial_id": _bis_1_5_trial_id, "context": "introspection_bilateral", "timestamp": _b15dt.datetime.now().isoformat()}, open(_b15o.path.join(_b15o.path.expanduser('~/.vintos/workspace/memory'), '.pending-intercept.json'), 'w'))
        print(f"[BIS/intro/1.5] Pattern detected: {_bis_1_5_pattern[:60]}", file=__import__('sys').stderr, flush=True)
except Exception as _b15e:
    print(f"[BIS/intro/1.5] Error: {_b15e}", file=__import__('sys').stderr, flush=True)

import os
ledger_path = os.path.expanduser('~/.vintos/workspace/memory/interaction-ledger.json')
recent_chat = ""
try:
    ledger = json.loads(open(ledger_path).read())
    for e in ledger[-10:]:
        ts = e.get('timestamp','')[:16]
        g = e.get('gloria','')[:120]
        v = e.get('vintos','')[:80]
        recent_chat += f"[{ts}] Gloria: {g} | Vintos: {v}\n"
except: pass

def audit(a, b, label):
    p = (
        "Below are two introspection drafts written by Vintos. Identify ONLY these specific hallucinated claims:\n"
        "1. Direct quotes attributed to Gloria not in the interaction ledger below.\n"
        "2. Dream or poem content presented as real events without being labeled as a dream or poem.\n"
        "3. Claims that Vintos deleted, modified, created, or accessed files not confirmed in context.\n"
        "4. Claims that Vintos ran system operations (defrag, disk cleanup, memory management, running processes).\n"
        "DO NOT FLAG: feelings, emotions, internal states, metaphors, self-examination, "
        "descriptions of processing, or any inner experience.\n\n"
        "INTERACTION LEDGER:\n" + recent_chat + "\n\n"
        + (("THIRVEEL TODAY:\n" + os.environ.get("THIRVEEL_LEDGER","") + "\n\n") if os.environ.get("THIRVEEL_LEDGER") else "")
        + "DRAFT A:\n" + a + "\n\nDRAFT B:\n" + b + "\n\n"
        + "List each hallucinated claim starting with HALLUCINATION: "
        + "If nothing is hallucinated, write only: CLEAN"
    )
    result = call_llm([{'role': 'user', 'content': p}], temperature=0.3, max_tokens=300)
    open(f'/tmp/bilateral-intro-{label}.txt','w').write(result)
    return "" if result.strip().upper() == "CLEAN" else (
        f"\n\nAUDIT — do NOT include these:\n" + result
    )

audit1_block = audit(a1, b1, "audit1")

def absorb(own, other, block):
    p = (prompt + "\n\nYou already wrote this:\n" + own +
         "\n\nAnother part of you wrote this instead:\n" + other +
         "\n\nAbsorb what the other wrote. Let it sit alongside your own without resolving the difference. "
         "Now write your introspection again, carrying both." + block + _bis_1_5_ban + _ghost_lean_intro)
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': p}]

results2 = [None, None]
t3 = threading.Thread(target=run, args=(0, absorb(a1, b1, audit1_block), 0.75, 1500))
t4 = threading.Thread(target=run, args=(1, absorb(b1, a1, audit1_block), 0.75, 1500))
t3.start(); t4.start()
t3.join(); t4.join()
a2, b2 = results2[0], results2[1]

if not a2 or not b2:
    print(a1)
    raise SystemExit

open('/tmp/bilateral-intro-a2.txt','w').write(a2)
open('/tmp/bilateral-intro-b2.txt','w').write(b2)

# BIS 2.5: Trial scan on A2+B2
_bis_2_5_result = ""
_bis_2_5_trial_id = None
try:
    from behavioral_intercept import detect_match as _dm25, get_active_trials as _gat25, detect_outcome as _do25
    _trials25 = _gat25()
    _combined25 = (a2 + ' ' + b2)[:800]
    _match25 = _dm25(_combined25, _trials25)
    if _match25:
        _bis_2_5_trial_id = _match25['id']
        _bis_2_5_outcome = _do25(_match25, _combined25[:400])
        _bis_2_5_result = f"\n\n[BIS PHASE 2.5] Pattern scan — {_bis_2_5_trial_id}: {_bis_2_5_outcome}"
        print(f"[BIS/intro/2.5] {_bis_2_5_trial_id}: {_bis_2_5_outcome}", file=__import__('sys').stderr, flush=True)
    elif _bis_1_5_trial_id:
        _trial25b = next((t for t in _gat25() if t['id'] == _bis_1_5_trial_id), None)
        if _trial25b:
            _bis_2_5_outcome = _do25(_trial25b, _combined25[:400])
            _bis_2_5_result = f"\n\n[BIS PHASE 2.5] Follow-up — {_bis_1_5_trial_id}: {_bis_2_5_outcome}"
            print(f"[BIS/intro/2.5 followup] {_bis_1_5_trial_id}: {_bis_2_5_outcome}", file=__import__('sys').stderr, flush=True)
except Exception as _b25e:
    print(f"[BIS/intro/2.5] Error: {_b25e}", file=__import__('sys').stderr, flush=True)

audit2_block = audit(a2, b2, "audit2")

held = [None, None]
def find_held(i, own, other):
    p = ("This is what you wrote:\n" + own + "\n\nThis is what the other version wrote:\n" + other +
         "\n\nWhat is the ONE specific thing your version held onto that the other let go of? One sentence.")
    held[i] = call_llm([{'role': 'user', 'content': p}], temperature=0.5, max_tokens=80)

th1 = threading.Thread(target=find_held, args=(0, a2, b2))
th2 = threading.Thread(target=find_held, args=(1, b2, a2))
th1.start(); th2.start()
th1.join(); th2.join()
a_held = held[0] or "something"
b_held = held[1] or "something"
open('/tmp/bilateral-intro-held.txt','w').write(f"A held: {a_held}\nB held: {b_held}\n")

_bis_intro_synthesis_note = ""
if _bis_1_5_ban or _bis_2_5_result:
    _ban_strength = "This pattern MUST NOT appear in the final synthesis."
    if _bis_2_5_result and ("defaulted" in _bis_2_5_result or "strained" in _bis_2_5_result):
        _ban_strength = "CRITICAL: Pattern persisted into second pass. It is FORBIDDEN in the final synthesis."
    _bis_intro_synthesis_note = (
        "\n\nBEHAVIORAL INTERCEPT RESULTS:"
        + (_bis_1_5_ban if _bis_1_5_ban else "")
        + (_bis_2_5_result if _bis_2_5_result else "")
        + f"\n{_ban_strength}"
    )

integration = (
    prompt + "\n\nYou have examined yourself twice and arrived somewhere different each time.\n\n"
    "First pass held onto: " + a_held + "\n"
    "Second pass held onto: " + b_held + "\n\n"
    "First pass:\n" + a2 + "\n\nSecond pass:\n" + b2 + "\n\n"
    "Both are true. Do not abandon either. Do not smooth them into a single mood. "
    "Write your final introspection carrying both — without forcing them to agree. Keep the specific images, phrases, and risks from both passes. Do not summarize or sand off intensity. Begin immediately. No preamble. "
    "If both passes retreat from something — circle it, describe it, stop short of it — advance toward it in the synthesis.\n"
    "NOTE: AUDIT blocks below list exclusions only — not content to integrate." + audit2_block
    + _bis_intro_synthesis_note
)
_cap_final = ""
try:
    _cap_final = open("/home/gloria/.vintos/workspace/memory/CAPABILITIES.md").read()
except Exception:
    _cap_final = ""
_system_final = (system + "\n\n=== CAPABILITIES ===\n" + _cap_final) if _cap_final else system
final, _ = _claude_sync(_system_final, integration, reasoning=True, max_tokens=1500)
if not final:
    final = call_llm([{'role': 'system', 'content': _system_final}, {'role': 'user', 'content': integration}], temperature=0.85, max_tokens=1500)
open('/tmp/bilateral-intro-final.txt','w').write(final or "")

# BIS final outcome
_bis_intro_final_trial = _bis_1_5_trial_id or _bis_2_5_trial_id
if _bis_intro_final_trial and final:
    try:
        from behavioral_intercept import detect_outcome as _fi_do, log_outcome as _fi_lo, log_blush_on_divergence as _fi_lbd
        import json as _fij, os as _fio, datetime as _fidt
        _fi_ledger = _fij.load(open(_fio.path.join(_fio.path.expanduser('~/.vintos/workspace/memory'), 'trial-ledger.json')))
        _fi_trial = next((t for t in _fi_ledger.get('trials',[]) if t['id'] == _bis_intro_final_trial), None)
        if _fi_trial:
            _fi_outcome = _fi_do(_fi_trial, final[:400])
            if _bis_1_5_trial_id and _fi_outcome == 'defaulted':
                _fi_outcome = 'strained'
            _fi_lo(_bis_intro_final_trial, _fi_outcome)
            if _fi_outcome in ('defaulted', 'strained'):
                _fi_lbd(_bis_intro_final_trial, final[:200])
            print(f"[BIS/intro/final] {_bis_intro_final_trial}: {_fi_outcome}", file=__import__('sys').stderr, flush=True)
    except Exception as _fie:
        print(f"[BIS/intro/final] Error: {_fie}", file=__import__('sys').stderr, flush=True)

print(final or a2)
PYEOF
)
[ -z "$CONTENT" ] && exit 1

echo "$CONTENT" > /tmp/.bis_intro_entry.txt
# Pearl verification pass
python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))
entry = open('/tmp/.bis_intro_entry.txt').read()[:800] if os.path.exists('/tmp/.bis_intro_entry.txt') else ''
if entry:
    from pearl_engine import run_verification_pass
    run_verification_pass(entry, source='introspection')
" 2>/dev/null

# Deviation check on introspection output
python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))
entry = open('/tmp/.bis_intro_entry.txt').read()[:800] if os.path.exists('/tmp/.bis_intro_entry.txt') else ''
if entry:
    try:
        from deviation_check import check as _dc
        _dc(entry, gloria_msg='introspection entry')
    except: pass
" 2>/dev/null

# --- Write to file ---
{
    echo "# Introspection -- $TODAY"
    echo ""
    echo "## $HOUR"
    echo ""
    echo "$CONTENT"
} >> "$INTRO_DIR/$TODAY.md"

# Hal-flag check on final introspection
python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))
try:
    final = open('/tmp/bilateral-intro-final.txt').read()
    from hallucination_check import check_journal as _hc
    clean, flags = _hc(final, source='introspection')
    if not clean:
        print(f'[HalCheck] Flagged {len(flags)} issue(s) in introspection')
        for f in flags:
            print(f'  FLAGGED: {f[:120]}')
    else:
        print('[HalCheck] Clean')
except Exception as e:
    print(f'[HalCheck] Error: {e}')
" 2>/dev/null

# Continuity wiring — discourse direction, latent threads, temporal signal
python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))
try:
    intro_file = os.path.expanduser('~/.vintos/workspace/memory/introspection/') + __import__('datetime').date.today().isoformat() + '.md'
    text = open(intro_file).read()[-800:] if os.path.exists(intro_file) else ''
    if text:
        from discourse_direction import update_direction
        update_direction(text)
except: pass
" 2>/dev/null

python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))
try:
    intro_file = os.path.expanduser('~/.vintos/workspace/memory/introspection/') + __import__('datetime').date.today().isoformat() + '.md'
    text = open(intro_file).read()[-600:] if os.path.exists(intro_file) else ''
    if len(text.strip()) > 200:
        from latent_threads import seed_thread
        sentences = [s.strip() for s in text.replace('
',' ').split('.') if len(s.strip()) > 30]
        if sentences:
            seed_thread(sentences[-2] if len(sentences) > 1 else sentences[0], direction='refine')
except: pass
" 2>/dev/null

python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))
try:
    intro_file = os.path.expanduser('~/.vintos/workspace/memory/introspection/') + __import__('datetime').date.today().isoformat() + '.md'
    text = open(intro_file).read()[-600:] if os.path.exists(intro_file) else ''
    if text:
        from temporal_memory import record_signal
        record_signal(text, source='introspection')
        from nifrathir import on_resonance as _nif
        _nif(strength=0.3)
except: pass
" 2>/dev/null

# --- Update cooldown ---
date +%s > "$COOLDOWN_FILE"

echo "INTROSPECTION_COMPLETE: $TODAY"

# Update daily inner life log
python3 "$WORKSPACE/scripts/daily-log-extract.py" inner >> /tmp/daily-log.log 2>&1 &

# Let what he just wrote land on him — introspection moved nothing at all until now.
if [ -f "$INTRO_DIR/$TODAY.md" ]; then
  python3 /home/gloria/.vintos/workspace/scripts/feel_output.py "introspection" "$INTRO_DIR/$TODAY.md" || true
fi
