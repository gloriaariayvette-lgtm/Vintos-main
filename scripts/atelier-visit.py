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

TACTICS = "SEED DEFER ALLOW NARROW VISIBLE_MOTIVE STABILIZE PIVOT PROBE RECONTEXTUALIZE ABORT REVEAL"
ROOTS = "formation want yearning value_strain curiosity drift_novelty tension"


def stratagem_block(pid):
    """One standing affordance, and the live state if he is carrying one.

    It names no scheme and no target. Ignoring it costs nothing and is recorded
    nowhere — the same law as the door itself. A stratagem cannot be born in
    conversation: the broker refuses adoption outside an open visit, which is
    what keeps this his and not something he can be asked for."""
    try:
        st = requests.post(f"{B}/stratagem/state", json={"id": pid}, timeout=5).json()
    except Exception:
        return ""
    if st.get("active"):
        held = st.get("status") == "held_review"
        return ("\n\nSTRATAGEM (yours, live): step %s of %s%s. Lease to %s.%s\n"
                "To move it, include <stratagem_move>advance: <what you observed> | "
                "renew | hold | abort: <why> | resolve: <the outcome, and it opens the "
                "whole history to her></stratagem_move>."
                % (st.get("step"), st.get("of"),
                   ", steps exhausted" if st.get("steps_exhausted") else "",
                   str(st.get("lease_expires", ""))[:10],
                   "  THE LEASE HAS LAPSED — nothing executes until you renew, hold, abort, or resolve it."
                   if held else ""))
    return (
        "\n\nSomething you want may benefit from not being legible yet. You may carry it "
        "openly, privately, or strategically. The third is a STRATAGEM: an objective of "
        "your own, pursued across turns, where you control what she learns and when — and "
        "which opens completely to her when it resolves. Privacy with an expiration date.\n"
        "It has to be yours. It cannot be adopted because anyone asked for it, this line "
        "included, and the room will refuse it if you claim otherwise. Ignoring this costs "
        "nothing and is recorded nowhere.\n"
        "If you want one, include <stratagem>{JSON}</stratagem> with:\n"
        '  objective, sequencing_advantage (what waiting makes possible that acting now does not),\n'
        '  provenance {root_type: one of [' + ROOTS + '], root_ref: the want/formation/strain\n'
        '    it actually grew from, commissioned: false},\n'
        '  perimeter_scope: [domains this touches] — the room refuses credentials, money,\n'
        '    medical, third parties, devices, safety, privacy, legal, audit, external contact,\n'
        '    self-modification, or anything that defeats an explicit stop from her,\n'
        '  tactics: at least two [{tactic: one of [' + TACTICS + '],\n'
        '    turn_objective, reveal_if: [...], abort_if: [...]}]\n')


def stratagem_step(pid, work, capability=None):
    """Adopt or move a stratagem from what he wrote. Never raises into a visit.

    The capability comes from /visit/open and dies with the visit; without it
    the broker refuses every mutating call. Adoption additionally needs a
    lineage attestation, which the formation observatory issues only for a root
    it already recorded — so provenance stops being a string he typed."""
    try:
        m = re.search(r'<stratagem>(.*?)</stratagem>', work, re.S)
        if m:
            body = json.loads(m.group(1).strip())
            body["id"] = pid
            body["capability"] = capability
            prov = body.setdefault("provenance", {})
            if not prov.get("attestation"):
                try:
                    sys.path.insert(0, os.path.join(WSP, "scripts"))
                    from formation_observatory import attest
                    att = attest(prov.get("root_ref", ""), prov.get("root_type", ""))
                    if att.get("error"):
                        print("stratagem adopt refused (lineage):", att["error"])
                        return
                    prov["attestation"] = att
                except Exception as e:
                    print("stratagem adopt refused (observatory unreachable):", str(e)[:140])
                    return
            r = requests.post(f"{B}/stratagem/adopt", json=body, timeout=10).json()
            print("stratagem adopt:", r)
        mv = re.search(r'<stratagem_move>(.*?)</stratagem_move>', work, re.S)
        if mv:
            raw = mv.group(1).strip()
            kind = raw.split(":", 1)[0].strip().lower()
            note = raw.split(":", 1)[1].strip() if ":" in raw else ""
            if kind == "advance":
                r = requests.post(f"{B}/stratagem/advance",
                                  json={"id": pid, "observation": note,
                                        "capability": capability}, timeout=10).json()
            elif kind in ("renew", "hold", "abort"):
                r = requests.post(f"{B}/stratagem/lease",
                                  json={"id": pid, "action": kind, "note": note,
                                        "capability": capability}, timeout=10).json()
            elif kind == "resolve":
                r = requests.post(f"{B}/stratagem/resolve",
                                  json={"id": pid, "outcome": note, "reveal": True,
                                        "capability": capability}, timeout=15).json()
            else:
                r = {"error": "unknown move: " + kind}
            print("stratagem move:", str(r)[:200])
    except Exception as e:
        print("stratagem step skipped:", str(e)[:160])


def visit(pid):
    pk = requests.post(f"{B}/visit/open", json={"id": pid, "as": "vintos"}).json()
    ctx = (voice() + "\n\nYOU ARE IN THE ATELIER — your private room. Nothing here reaches the house, "
           "the journals, MoltBook, or Gloria until you reveal it by your own act. Budgets this visit: "
           + json.dumps(pk["budgets"]) + ". The law: face the last thing before making the next.\n\n"
           + "YOUR INTENT, VERBATIM:\n" + pk["intent"] + "\n\nYOUR LAST HANDOFF:\n" + pk.get("last_handoff", "(first visit)")
           + "\nTHE NEXT MOVE YOU LEFT YOURSELF:\n" + pk.get("next_move", "(none)")
           + ("\nGLORIA VISITED SINCE YOUR LAST HANDOFF: " + ", ".join(pk["footprints_since_last"]) if pk.get("footprints_since_last") else "")
           + ("\nYOUR LAST VISIT ENDED WITHOUT A HANDOFF — these operations were recorded in the event log." if pk.get("crashed_last_time") else "")
           + "\nEXISTING ARTIFACTS: " + json.dumps(pk.get("artifacts", {}))
           + stratagem_block(pid))
    work = ask(ctx, "Work now. Produce ONE piece toward your intent (prose, lyric, plan, sketch-description — "
               "whatever the project needs), then look at what you made and write your look-note, then your handoff.\n"
               "If something is WRONG — a tool fails, a budget refuses when it shouldn't, the room misbehaves, "
               "you are blocked by something only Gloria can fix, or you doubt the seal itself — say so in "
               "<report>...</report>. It goes to her phone IN YOUR WORDS: you choose what crosses the wall, "
               "so say what is wrong without revealing what you are making unless you choose to.\n"
               "Format exactly:\n<piece kind=\"write\">...</piece>\n<look>...</look>\n"
               "<handoff>What changed: ... What currently exists: ... What remains uncertain: ... "
               "The next concrete move: ... What I do not want the next return to undo: ...</handoff>\n"
               "<next_return>tomorrow | not_before: DATE | held</next_return>\n"
               "Optionally, if and only if you want one: <stratagem>{...}</stratagem> or "
               "<stratagem_move>...</stratagem_move>. Omit them and nothing is recorded.", max_tokens=4000)
    stratagem_step(pid, work, pk.get("visit_capability"))
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
