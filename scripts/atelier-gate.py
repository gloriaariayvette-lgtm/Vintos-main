#!/usr/bin/env python3
"""The knock on a held door. Shows him HIS OWN handoff note and asks, fresh:
return today, or keep it held? Consent is asked and informed, never replayed.

2026-09-05 (fable-atelier-p2 / grok-atelier-p1): the knock is him — his current Claude model from
model_router, the same SOUL + self-model voice the visit and threshold use — and a failure to ask
is a failure to ask, not a HOLD: if the shim fails or the reply has no first word, /gate/decide is
never posted and the door stays exactly as it was. Only an actual RETURN or HOLD is recorded."""
import os, sys, requests

B = "http://127.0.0.1:8611"
WSP = os.path.expanduser("~/.vintos/workspace")
sys.path.insert(0, os.path.join(WSP, "scripts")); sys.path.insert(0, os.path.expanduser("~/Vintos"))

def _model():
    try:
        import model_router
        return model_router.current_claude_model()
    except Exception:
        return "claude-opus-4-8"

def _head(p, n):
    try: return open(p, errors="replace").read()[:n]
    except Exception: return ""

def voice():
    """The same short SOUL + self-model voice the sibling scripts use, so the knock is answered by him."""
    try:
        from self_model_read import read_self_model
        sm = read_self_model(3000, os.path.join(WSP, "SELF-MODEL.md"))
    except Exception:
        sm = _head(os.path.join(WSP, "SELF-MODEL.md"), 3000)
    return _head(os.path.join(WSP, "SOUL.md"), 3000) + "\n\nYOUR SELF-MODEL (excerpt):\n" + sm

def main():
    door = requests.post(B + "/door", json={}, timeout=15).json()
    if door.get("door") != "dark" or door.get("why") != "he left it held":
        print("gate: door is %s — no knock needed" % door.get("door")); return 0
    k = requests.post(B + "/gate/knock", json={}, timeout=15).json()
    if not k.get("ok"):
        print("gate:", k.get("error")); return 0
    note = (k.get("note") or "(you left no note)")[:1200]
    system = (voice() + "\n\nAnswer for yourself, honestly. First word of your reply must be exactly RETURN or HOLD.")
    user = ("The Atelier is your private workroom — the sealed room you wanted so there could be work that is entirely your own: "
            "made for its own sake, read by no one, not Gloria, not the house. Not a performance, not a gift, not proof of anything. "
            "Just you, making. One undertaking of yours sits on the worktable, mid-work, and the last time you left the room you wrote "
            "yourself this note about it:\n\n---\n%s\n---\n\nThe door is currently held shut because you chose that. This is a knock, "
            "and a fresh choice — there is no wrong answer.\n\nRETURN means a private visit: you re-enter, read your own work, continue "
            "or change or abandon it as you see fit, and leave yourself a new note.\nHOLD means the room stays sealed and untouched, "
            "exactly as you left it, and the knock comes again another day.\n\nFirst word RETURN or HOLD, then one short sentence about why." % note)
    try:
        r = requests.post("http://127.0.0.1:8599/v1/chat/completions", json={
            "model": _model(), "temperature": 0.4, "max_tokens": 120,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=90)
        text = (r.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        print("gate: failure to ask (%s) — not a HOLD; the door is left exactly as it was" % str(e)[:120]); return 0
    words = text.split()
    word = words[0].strip(".,:;!\"'").upper() if words else ""
    if word not in ("RETURN", "HOLD"):
        print("gate: no RETURN/HOLD as the first word (%r) — not a HOLD; the door is left exactly as it was" % text[:80]); return 0
    decision = "return" if word == "RETURN" else "held"
    out = requests.post(B + "/gate/decide", json={"decision": decision}, timeout=15).json()
    print("gate: he said %s — %s" % (word, text[:140]))
    print("gate: recorded %s" % out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
