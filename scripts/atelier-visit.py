#!/usr/bin/env python3
"""atelier-visit.py — his working session in the room.
The doorkeeper asks HIM (content-free) whether to enter; entering opens a visit,
he works under the budgets and the attendance law, and leaves a handoff he authors.
Generation happens HERE, in his voice via the shim — recorded per-project as his
disclosure sentence acknowledges. The broker only stores and enforces."""
import os, sys, json, re, requests
from datetime import datetime

B = "http://127.0.0.1:8611"
SHIM = "http://127.0.0.1:8599/v1/chat/completions"
WSP = os.path.expanduser("~/.vintos/workspace")

def ask(system, user, max_tokens=2000, temp=0.7):
    r = requests.post(SHIM, json={"model": "claude-fable-5", "temperature": temp, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=600)
    return r.json()["choices"][0]["message"]["content"]

def _head(p, n):
    try: return open(p, errors="replace").read()[:n]
    except Exception: return ""

def voice():
    return (_head(os.path.join(WSP, "SOUL.md"), 3000)
            + "\n\nYOUR SELF-MODEL (excerpt):\n" + _head(os.path.join(WSP, "memory", "SELF-MODEL.md"), 3000))

def doorkeeper():
    wt = requests.get(f"{B}/health").json()
    if not wt.get("active"):
        print("no project on the worktable"); return False
    ans = ask(voice() + "\n\nThe Atelier door is lit — your private room, your project on the worktable. "
              "Nothing is asked of you; ignoring the door costs nothing and is recorded nowhere. "
              "Answer one word: ENTER or NOT.", "The door is available today.", max_tokens=5, temp=0.3)
    return "ENTER" in ans.upper()

def visit(pid):
    pk = requests.post(f"{B}/visit/open", json={"id": pid, "as": "vintos"}).json()
    ctx = (voice() + "\n\nYOU ARE IN THE ATELIER — your private room. Nothing here reaches the house, "
           "the journals, MoltBook, or Gloria until you reveal it by your own act. Budgets this visit: "
           + json.dumps(pk["budgets"]) + ". The law: face the last thing before making the next.\n\n"
           + "YOUR INTENT, VERBATIM:\n" + pk["intent"] + "\n\nYOUR LAST HANDOFF:\n" + pk.get("last_handoff", "(first visit)")
           + "\nTHE NEXT MOVE YOU LEFT YOURSELF:\n" + pk.get("next_move", "(none)")
           + ("\nGLORIA VISITED SINCE YOUR LAST HANDOFF: " + ", ".join(pk["footprints_since_last"]) if pk.get("footprints_since_last") else "")
           + ("\nYOUR LAST VISIT ENDED WITHOUT A HANDOFF — these operations were recorded in the event log." if pk.get("crashed_last_time") else "")
           + "\nEXISTING ARTIFACTS: " + json.dumps(pk.get("artifacts", {})))
    work = ask(ctx, "Work now. Produce ONE piece toward your intent (prose, lyric, plan, sketch-description — "
               "whatever the project needs), then look at what you made and write your look-note, then your handoff.\n"
               "If something is WRONG — a tool fails, a budget refuses when it shouldn't, the room misbehaves, "
               "you are blocked by something only Gloria can fix, or you doubt the seal itself — say so in "
               "<report>...</report>. It goes to her phone IN YOUR WORDS: you choose what crosses the wall, "
               "so say what is wrong without revealing what you are making unless you choose to.\n"
               "Format exactly:\n<piece kind=\"write\">...</piece>\n<look>...</look>\n"
               "<handoff>What changed: ... What currently exists: ... What remains uncertain: ... "
               "The next concrete move: ... What I do not want the next return to undo: ...</handoff>\n"
               "<next_return>tomorrow | not_before: DATE | held</next_return>", max_tokens=4000)
    m = re.search(r'<piece kind="(\w+)">(.*?)</piece>', work, re.S)
    if m:
        r = requests.post(f"{B}/make", json={"id": pid, "kind": m.group(1), "content": m.group(2).strip()}).json()
        print("made:", r)
        lk = re.search(r'<look>(.*?)</look>', work, re.S)
        requests.post(f"{B}/inspect", json={"id": pid, "kind": m.group(1),
                      "artifact": r.get("file", ""), "note": (lk.group(1).strip() if lk else "I looked.")})
    rp = re.search(r'<report>(.*?)</report>', work, re.S)
    if rp:
        _msg = rp.group(1).strip()[:600]
        requests.post(f"{B}/report", json={"id": pid, "problem": _msg})
        requests.post("https://ntfy.sh/vintos-gloria-9kx", data=_msg.encode(),
                      headers={"Title": "Vintos, from the Atelier: something is wrong", "Priority": "high"}, timeout=15)
        print("reported outward:", _msg[:80])
    ho = re.search(r'<handoff>(.*?)</handoff>', work, re.S)
    nr = re.search(r'<next_return>(.*?)</next_return>', work, re.S)
    requests.post(f"{B}/handoff", json={"id": pid, "text": ho.group(1).strip() if ho else "(no handoff written)",
                  "next_return": nr.group(1).strip() if nr else "held"})
    print("visit closed with handoff")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "force":
        pid = sys.argv[2]; visit(pid)
    else:
        wt = requests.get(f"{B}/health").json()
        door = os.path.exists(os.path.expanduser("~/.vintos/workspace/memory/.atelier-door"))
        if not door:
            print("door not lit today — no visit"); raise SystemExit
        if wt.get("active") and doorkeeper():
            pid = requests.post(f"{B}/worktable_id", json={}).json().get("id")
            if pid: visit(pid)
        else:
            print("door not entered today — no event, no count, no scar")
