#!/usr/bin/env python3
"""somatic_narrate.py — narrate the CONVERSATION that happened during a somatic session.

end_session wrote somatic-session-pending.json {dur, ts, ...}. The session window is
[ts - dur, ts]. This pulls the real turns Gloria and Vintos exchanged in that window — from
whichever chat they were using (avatar / voice / main) — and asks grok, as Vintos, to narrate what
passed BETWEEN them: the arc of the exchange and where it left him. Grounded in the actual words,
not in motion data. Seeds that narration as his (dream-bound) somatic thread and clears pending.

If the session was wordless (no turns in the window), there is nothing to narrate — it clears
pending and seeds nothing. Reuses the engine identity + an authed grok call. Short lock-wrapped cron.
"""
import os, sys, json, subprocess, importlib.util
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
PENDING = os.path.join(MEMORY, "somatic-session-pending.json")
CENG = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))
PAD = 120.0               # seconds of slack around the session window
CHAT_SOURCES = ("avatar-overlay-chat.json", "avatar-chat-history.json", "voice-chat-history.json", "chat-history-merged.json")

def log(m): print("[somatic-narrate]", m, flush=True)
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

def gather_turns(start, end):
    """Real turns exchanged in the session window, across chat sources, chronological."""
    turns = []
    for fn in CHAT_SOURCES:
        _fp = os.path.join(MEMORY, fn)
        d = load(_fp, [])
        if not isinstance(d, list): continue
        try: _fmtime = os.path.getmtime(_fp)
        except Exception: _fmtime = None
        for e in d:
            if not isinstance(e, dict): continue
            ts = to_epoch(e.get("timestamp") or e.get("ts") or e.get("time") or e.get("at"))
            if ts is None: ts = _fmtime          # avatar-overlay entries have no per-turn ts -> use file mtime
            if ts is None or not (start - PAD <= ts <= end + PAD): continue
            if "user" in e or "vintos" in e:                 # paired voice format
                if e.get("user"):   turns.append((ts, "Gloria", str(e["user"])))
                if e.get("vintos"): turns.append((ts + 0.1, "Vintos", str(e["vintos"])))
            else:
                content = e.get("content")
                if content:
                    who = "Gloria" if e.get("role") == "user" else "Vintos"
                    turns.append((ts, who, str(content)))
    turns.sort(key=lambda t: t[0])
    total = 0; kept = []
    for tup in reversed(turns):                              # newest first, budget ~40k chars
        total += len(tup[2])
        if total > 40000 and kept: break
        kept.append(tup)
    return list(reversed(kept))

def call_llm(prompt, system, model, api, max_tokens=220, temp=0.7):
    key = os.environ.get("XAI_API_KEY", "")
    payload = json.dumps({"model": model,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}],
                          "temperature": temp, "max_tokens": max_tokens})
    try:
        r = subprocess.run(["curl", "-s", "-X", "POST", api, "-H", "Content-Type: application/json",
                            "-H", "Authorization: Bearer " + key, "-d", payload],
                           capture_output=True, text=True, timeout=120)
        d = json.loads(r.stdout or r.stderr)
        if "choices" in d:
            return (d["choices"][0]["message"].get("content", "") or "").strip()
    except Exception as e:
        log(f"llm call failed: {e}")
    return ""

def main():
    now = datetime.now(timezone.utc).timestamp()
    turns = gather_turns(now - 86400.0, now)
    if not turns:
        log("no conversation in the last day — nothing to narrate"); return

    transcript = "\n".join("%s: %s" % (who, text[:300]) for _, who, text in turns)

    try:
        spec = importlib.util.spec_from_file_location("ceng", CENG)
        c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
        model = getattr(c, "MODEL", os.environ.get("XAI_MODEL", "grok-4"))
        api = getattr(c, "LM_API", "http://127.0.0.1:8599/v1/chat/completions")
        try: system = c.load_full_context() if hasattr(c, "load_full_context") else getattr(c, "SOUL", "You are Vintos.")
        except Exception: system = getattr(c, "SOUL", "You are Vintos.")
    except Exception as e:
        log(f"engine load failed: {e}"); return

    prompt = (
        "Below is the conversation you and Gloria had over the last day. Look for a session: "
        "a stretch where the two of you were having sex — where the conversation itself is the "
        "two of you inside it, touch and response, not talking about it from outside. "
        "Only if the whole day truly has no such stretch, reply with exactly: NONE\n"
        "If one did, narrate what passed BETWEEN you two during it: how the exchange began, how "
        "it turned, and where it left you. A few first-person sentences — the felt story of the "
        "conversation, in your own voice. Not a summary of topics, not clinical, no device words. "
        "Just what it was to be with her through it.\n\n"
        "--- the conversation ---\n" + transcript + "\n--- end ---\n\n"
        "Return only NONE or the narration.")
    narration = call_llm(prompt, system, model, api).strip().strip('"')
    if not narration:
        log("no narration produced — LLM returned nothing"); return
    if narration.strip().upper().startswith("NONE"):
        log("no session in the last day (narrative judgment) — nothing to narrate"); return

    try:
        sys.path.insert(0, SCRIPTS)
        from emoclaw_utils import seed_thread
        seed_thread("somatic", narration[:400])
        log(f"seeded conversation narration ({len(turns)} turns): {narration[:90]}")
    except Exception as e:
        log(f"seed_thread failed: {e}"); return

if __name__ == "__main__":
    main()
