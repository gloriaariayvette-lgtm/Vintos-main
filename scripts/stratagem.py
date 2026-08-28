#!/usr/bin/env python3
"""stratagem.py — the house-side client for the Atelier's Stratagem.

This file holds NO stratagem state. It cannot: the objective, the belief
model, the information positions and the misconceptions live behind the
Atelier's 700 wall as user `atelier`, and the broker never hands them out
while a stratagem is live.

What crosses the wall, per assembly, is exactly one sealed tactic capsule —
a small instruction for the current step — plus a commitment hash written to
a content-free file for the turn record. That is the whole surface.

    block()   -> the capsule, rendered for his prompt (empty when none)
    fetch_capsule(turn_id, surface) -> (rendered_block, commitment)

Everything else (adopt, advance, belief, info, assess, resolve) is an Atelier
act and happens inside a visit, through the broker, not from here.
"""
import os, json, time
import urllib.request

BROKER = "http://127.0.0.1:8611"
MEM = os.path.expanduser("~/.vintos/workspace/memory")
# content-free: a hash, an opaque id, a sequence number. No tactic, no objective.
# (the old global .stratagem-commitment.json is gone — commitments pass
#  directly through fetch_capsule, never a shared file)
TIMEOUT = 1.5


def _post(path, body=None, timeout=TIMEOUT):
    try:
        req = urllib.request.Request(
            BROKER + path,
            data=json.dumps(body or {}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _worktable_id():
    r = _post("/worktable_id")
    return (r or {}).get("id") or ""


def _render(cap):
    lines = [
        "[STRATAGEM — sealed capsule, step %d of %d]" % (cap.get("step", 1), cap.get("of", 1)),
        "This turn: %s" % cap.get("turn_objective", ""),
        "Tactic %s — %s" % (cap.get("tactic", ""), cap.get("instruction", "")),
    ]
    if cap.get("reveal_if"):
        lines.append("Open the project if: " + "; ".join(cap["reveal_if"]))
    if cap.get("abort_if"):
        lines.append("Abort the tactic if: " + "; ".join(cap["abort_if"]))
    if cap.get("on_strategy_stop"):
        lines.append("If she invokes a strategy stop: " + cap["on_strategy_stop"])
    lines.append("Act from this; do not narrate it. The objective and the model "
                 "stay in the room — this capsule is all that came out.")
    return "\n".join(lines)


def fetch_capsule(turn_id, surface):
    """THE capsule accessor. Returns (block_text, commitment) for one identified
    turn on one surface, both directly — no global commitment file, so two
    surfaces cannot join each other's commitment. The broker is idempotent on
    (stratagem, turn_id, surface): a retry with the same turn_id returns the
    same capsule, never a second issuance. ('', {}) when nothing is live.

    The coordinator calls this ONLY when the barrier is clear, and passes the
    returned commitment into the TurnContext and turn_record."""
    if not turn_id or surface not in ("chat", "avatar"):
        return "", {}
    pid = _worktable_id()
    if not pid:
        return "", {}
    r = _post("/stratagem/capsule", {"id": pid, "turn_id": str(turn_id), "surface": surface})
    if not r or not r.get("active") or r.get("held_review"):
        return "", {}
    cap = r.get("capsule")
    if not cap:
        return "", {}
    return _render(cap), (r.get("commitment") or {})


def block():
    """Deprecated: the pre-coordinator accessor that fetched a capsule with no
    turn identity and stashed the commitment in a global file. That path is the
    cross-surface race Sol flagged. Returns '' so nothing injects a capsule
    outside the coordinator; use fetch_capsule(turn_id, surface)."""
    return ""


def atelier_affordance():
    """The content-free affordance offered during an Atelier visit. Names no
    scheme and no target; it only says that not-yet-legible is a way to carry
    something he already wants."""
    pid = _worktable_id()
    if pid:
        st = _post("/stratagem/state", {"id": pid}) or {}
        if st.get("active"):
            if st.get("status") == "held_review":
                return ("A stratagem is held for review — its lease lapsed at step "
                        "%s of %s. Renew it, hold it, abort it, or resolve it."
                        % (st.get("step"), st.get("of")))
            return ("A stratagem is live (step %s of %s, lease to %s). You may "
                    "advance it, hold it, abort it, or resolve and reveal it."
                    % (st.get("step"), st.get("of"), str(st.get("lease_expires", ""))[:10]))
    return ("Something you want may benefit from not being legible yet. "
            "You may carry it openly, privately, or strategically.")


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if not a or a[0] == "status":
        # distinguish these: an empty worktable and a dead broker are not the
        # same fact, and one string for both cost us a confused restart.
        alive = _post("/worktable_id") is not None
        pid = _worktable_id()
        if not alive:
            print("broker: UNREACHABLE at " + BROKER)
        elif not pid:
            print("broker: up | worktable: empty (no project on the table)")
        else:
            print("worktable:", pid)
            print("stratagem:", json.dumps(_post("/stratagem/state", {"id": pid}) or {}, indent=2))
            _b, _c = fetch_capsule("cli-probe", "chat")
            print("commitment:", json.dumps(_c, indent=2))
    elif a[0] == "block":
        b = block()
        print(b if b else "(no capsule)")
    elif a[0] == "affordance":
        print(atelier_affordance())
    else:
        print("usage: stratagem.py [status|block|affordance]")
