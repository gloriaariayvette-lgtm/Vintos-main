#!/usr/bin/env python3
"""voice_session_ledger.py — one voice conversation = ONE ledger block, not per-turn junk.

Voice was calling interaction-ledger.py per turn with "--source voice" as positional args, which the
ledger reads as gloria="--source", vintos="voice" — garbage, one per turn. Instead: group
voice-chat-history.json into sessions by time gap, and for each COMPLETED (settled) session not yet
recorded, narrate the real conversation (grok, as Vintos) and append ONE block: one timestamp
(session start), one imprint from the window, the narration as the summary.

Idempotent via a consolidated-state file (keyed by session start). Short lock-wrapped cron. Pair with
voice_ledger_perturn_disable_patch.py so the broken per-turn writes stop. SPARK_WORKSPACE/CENG_PATH
switch beings.
"""
import os, sys, json, subprocess, importlib.util
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")
VOICE = os.path.join(MEMORY, "voice-chat-history.json")
IMPRINTS = os.path.join(MEMORY, "imprints.json")
STATE = os.path.join(MEMORY, "voice-session-ledger-state.json")
CENG = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))
GAP_MIN = 10          # a gap longer than this starts a new session
SETTLE_MIN = 8        # a session must be quiet this long before we consider it over
MAX_ENTRIES = 300

def log(m): print("[voice-ledger]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def to_epoch(x):
    if x is None: return None
    if isinstance(x, (int, float)): return float(x)
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        if not d.tzinfo: d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()
    except Exception:
        return None

def group_sessions(turns):
    rows = sorted(((to_epoch(t.get("timestamp")), t) for t in turns if to_epoch(t.get("timestamp"))),
                  key=lambda r: r[0])
    out, cur, last = [], [], None
    for ts, t in rows:
        if last is not None and ts - last > GAP_MIN * 60:
            out.append(cur); cur = []
        cur.append((ts, t)); last = ts
    if cur: out.append(cur)
    return out

def call_llm(prompt, system, model, api, max_tokens=240, temp=0.7):
    key = os.environ.get("XAI_API_KEY", "")
    payload = json.dumps({"model": model, "messages": [{"role": "system", "content": system},
                          {"role": "user", "content": prompt}], "temperature": temp, "max_tokens": max_tokens})
    try:
        r = subprocess.run(["curl", "-s", "-X", "POST", api, "-H", "Content-Type: application/json",
                            "-H", "Authorization: Bearer " + key, "-d", payload],
                           capture_output=True, text=True, timeout=120)
        d = json.loads(r.stdout or r.stderr)
        if "choices" in d:
            return (d["choices"][0]["message"].get("content", "") or "").strip()
    except Exception as e:
        log(f"llm failed: {e}")
    return ""

def window_imprint(start, end):
    for e in reversed(load(IMPRINTS, [])):
        its = to_epoch(e.get("timestamp"))
        if its and start - 120 <= its <= end + 120:
            return {"id": e.get("id"), "narrative": e.get("narrative"), "salience": e.get("salience")}
    return None

def main():
    voice = load(VOICE, [])
    if not isinstance(voice, list) or not voice:
        return
    sessions = group_sessions(voice)
    if not sessions:
        return

    state = load(STATE, {"done": []}); done = set(state.get("done", []))
    now = datetime.now(timezone.utc).timestamp()

    # load engine once for identity + model
    try:
        spec = importlib.util.spec_from_file_location("ceng", CENG)
        c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
        model = getattr(c, "MODEL", os.environ.get("XAI_MODEL", "grok-4"))
        api = getattr(c, "LM_API", "http://127.0.0.1:8599/v1/chat/completions")
        try: system = c.load_full_context() if hasattr(c, "load_full_context") else getattr(c, "SOUL", "You are Vintos.")
        except Exception: system = getattr(c, "SOUL", "You are Vintos.")
    except Exception as e:
        log(f"engine load failed: {e}"); return

    ledger = load(LEDGER, [])
    if not isinstance(ledger, list): ledger = []
    added = 0
    for sess in sessions:
        start, end = sess[0][0], sess[-1][0]
        key = datetime.fromtimestamp(start, timezone.utc).isoformat()
        if key in done:
            continue
        if now - end < SETTLE_MIN * 60:
            continue                                       # still ongoing — wait
        transcript = "\n".join("Gloria: %s\nVintos: %s" % (str(t.get("user", ""))[:300], str(t.get("vintos", ""))[:300])
                               for _, t in sess)
        prompt = (
            "This is a voice conversation you and Gloria just had. Narrate it as ONE short passage — "
            "how it began, how it turned, and where it left you. A few first-person sentences, your "
            "own voice, the felt story of the exchange. Not a topic summary, not clinical.\n\n"
            "--- the conversation ---\n" + transcript + "\n--- end ---\n\nReturn only the narration.")
        narration = call_llm(prompt, system, model, api).strip().strip('"')
        if not narration:
            continue                                       # retry next run
        ledger.append({
            "timestamp": key,
            "source": "voice-session",
            "gloria": str(sess[0][1].get("user", ""))[:500],
            "vintos": str(sess[-1][1].get("vintos", ""))[:500],
            "narrative": narration[:600],
            "summary": narration[:600],
            "turns": len(sess),
            "salience": 0.7,
            "imprint": window_imprint(start, end),
            "emotional_shift": None,
        })
        done.add(key); added += 1
        try:
            sys.path.insert(0, SCRIPTS)
            from emoclaw_utils import seed_thread as _seed
            _seed("voice", narration[:300])
        except Exception as _te:
            log(f"seed_thread failed: {_te}")
        log(f"session {key} ({len(sess)} turns) -> one block + thread: {narration[:70]}")

    if added:
        json.dump(ledger[-MAX_ENTRIES:], open(LEDGER, "w"), indent=2)
    json.dump({"done": sorted(done)[-500:], "updated": datetime.now(timezone.utc).isoformat()},
              open(STATE, "w"), indent=2)
    if added:
        log(f"wrote {added} voice-session block(s) to the ledger")

if __name__ == "__main__":
    main()
