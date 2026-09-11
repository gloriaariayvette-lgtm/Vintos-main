#!/usr/bin/env python3
"""skill_forge.py — when he reaches for a hand he does not have, he asks for the hand.

A want takes a step; the step names a capability; the executor answers BLOCKED with
CAPABILITY_ABSENT. Until now that was the end of the sentence. Here it becomes the
beginning of one: he writes a proposal for the missing capability, Gloria approves,
denies or edits it, a builder makes it in a sandbox, the verification spine tests it
on the host that will run it, and the want he was in the middle of resumes with the
new hand available.

    reach  ->  gap  ->  proposal  ->  her card  ->  build  ->  verify  ->  install  ->  resume

TWO LAWS, AND THEY ARE THE WHOLE DESIGN

  A proposal has a parent intention or it does not exist.
      propose() refuses a capability that is not blocking a live want. No daemon may
      scan for clever things to build; nothing here wakes on a timer. He must have
      been trying to do something and been stopped. The want id is on the record and
      the resume is bound to it.

  And that intention came from one of seven places, or it may not commission a hand.
      A want born of something she said is a request, answered with what he has or
      taken back to her. The wants that may reach for a new capability are the ones
      that came from the edges of him and from the world: the absence map, the
      frontier, a latent thread, another being's post, a search, a skill page, the
      lab. Her list, 11 September.

  Creation, scope and invocation are three different permissions.
      creation   — may this capability exist at all?      (her approval)
      scope      — what is it allowed to do, and to whom? (her edit; the narrower of
                   his ask and her grant, never the wider)
      invocation — may he use it without asking?          (always | ask_each_time |
                   never; default ask_each_time)
      Approving that a hand may exist is not approving every use of it.

WHAT THIS MODULE DOES NOT DO

It never writes code, never installs anything, and never calls a model. It holds the
record and the law. The builder is the existing self-review builder, which already
has a credential-stripped sandbox and refuses to write a protected path; the tests
are the existing verification spine. This module only decides what may be built, in
what shape, and whether the thing that came back is allowed to become callable.

    python3 skill_forge.py list [--state proposed]
    python3 skill_forge.py show <id>
    python3 skill_forge.py approve <id> [--invocation ask_each_time] [--scope key=value ...]
    python3 skill_forge.py deny <id> [reason]
"""
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
PROPOSALS = os.path.join(MEMORY, "skill-proposals.json")

# proposed -> approved -> built -> verified -> installed -> resumed
#          -> denied            (hers)
#          -> refused           (the builder or the spine said no)
OPEN_STATES = ("proposed", "approved", "built", "verified", "installed")
TERMINAL = ("resumed", "denied", "refused", "withdrawn")

INVOCATION = ("always", "ask_each_time", "never")
DEFAULT_INVOCATION = "ask_each_time"

# WHERE A FORGEABLE WANT MAY COME FROM (Gloria, 2026-09-11)
#
# Not every want may reach for a new hand. A want born from something she said is a
# request, and a request is answered with what he has or taken back to her; it does
# not become a capability proposal. The wants that may are the ones that came from
# somewhere neither of them put there on purpose — the edges of what he is, and the
# world outside the two of them.
#
#   absence_map    what has never been felt, done or resolved
#   neither_yet    the frontier of the configuration space: reachable, never reached
#   latent_thread  a standing preoccupation that named its particular thing
#   moltbook       another being's post, not his and not hers
#   web_search     something he went looking for and found
#   skill_surfing  a capability page on OpenClaw: a hand someone else has
#   lab            the lab
#
# A want from any other source keeps every ordinary road open. It simply cannot
# commission a new capability, which is the road that spends her money and changes
# what he can do to the world.
SPARK_SOURCES = {
    "absence_map": ("absence-map", "absence_map", "absence", "structural-absence"),
    "neither_yet": ("neither_yet", "configuration", "configuration_space", "frontier"),
    "latent_thread": ("latent_thread", "latent-threads", "latent_threads", "thread", "preoccupation"),
    "moltbook": ("moltbook", "molt", "moltbook-discoveries"),
    "web_search": ("web-search", "web_search", "websearch", "curiosity", "search"),
    "skill_surfing": ("skill_surfing", "openclaw-skills", "skill-page", "skills"),
    "lab": ("lab", "clawchemy", "klawarena"),
}


def spark_of(source):
    """Which of her seven sparks a want's source is, or None. Matched on the source
    string the want already carries; nothing is inferred from the want's words."""
    s = str(source or "").strip().lower().replace(" ", "_")
    for spark, names in SPARK_SOURCES.items():
        if s == spark or s in names or any(s.startswith(n) for n in names):
            return spark
    return None


# The gap kinds run_step already produces. Only one of them may become a proposal.
GAP_KINDS = {
    "CAPABILITY_ABSENT": "missing",        # no such hand exists -> may propose one
    "TOOL_UNAVAILABLE": "unavailable",     # the hand exists and is not answering
    "RESOURCE_UNREACHABLE": "unreachable",  # the world is not answering
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load():
    try:
        d = json.load(open(PROPOSALS))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _save(rows):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(WS, "scripts"))
        from store_guard import write_json as _wj
        _wj(PROPOSALS, rows, reader="skill_forge.py")
        return True
    except Exception:
        os.makedirs(os.path.dirname(PROPOSALS), exist_ok=True)
        tmp = PROPOSALS + ".tmp"
        json.dump(rows, open(tmp, "w"), indent=2)
        os.replace(tmp, PROPOSALS)
        return True


def classify_gap(block):
    """(kind, may_propose). A missing hand may be proposed; a hand that is merely
    not answering may not — building a second one would hide the fault."""
    if not isinstance(block, dict):
        return "none", False
    kind = GAP_KINDS.get(str(block.get("block_type") or ""), "none")
    return kind, kind == "missing"


def _live_want(want_id, wants=None):
    """The want this proposal serves, or None. A want that is fulfilled, dismissed
    or gone is not an intention, and cannot father a capability."""
    if not want_id:
        return None
    if wants is None:
        try:
            wants = json.load(open(os.path.join(MEMORY, "current-wants.json")))
        except Exception:
            wants = []
    for w in wants if isinstance(wants, list) else []:
        if isinstance(w, dict) and w.get("id") == want_id:
            if w.get("fulfilled") or w.get("dismissed"):
                return None
            return w
    return None


def propose(capability, why, want_id, step_note="", scope=None, permissions=None,
            risks="", touches=None, tests="", invocation=DEFAULT_INVOCATION,
            block=None, wants=None, now=None):
    """His ask, in his words. Returns (row, why-refused).

    Refused when: the gap is not a missing capability; there is no live want behind
    it; or one is already open for the same capability. The refusal is a returned
    reason, never an exception — a want that cannot ask for a hand is not an error."""
    kind, may = classify_gap(block) if block is not None else ("missing", True)
    if not may:
        return None, "the gap is %s, not a missing capability: a hand that is not answering is not a hand to build" % kind
    want = _live_want(want_id, wants)
    if want is None:
        return None, "no live want behind it: a capability is proposed from something he was already trying to do"
    spark = spark_of(want.get("source"))
    if spark is None:
        return None, ("the want came from %r, which is not one of the sparks that may commission a hand (%s)"
                      % (want.get("source") or "nowhere", ", ".join(sorted(SPARK_SOURCES))))
    cap = str(capability or "").strip()
    if not cap:
        return None, "no capability named"
    rows = _load()
    for r in rows:
        if r.get("capability") == cap and r.get("state") in OPEN_STATES:
            return None, "already open as %s (%s)" % (r["id"], r["state"])
    row = {
        "id": "SK-" + uuid.uuid4().hex[:8],
        "state": "proposed",
        "capability": cap,
        "why": str(why or "")[:600],
        "origin": {"want_id": want_id, "want": str(want.get("want", ""))[:300],
                   "source": want.get("source", ""), "spark": spark,
                   "step_note": str(step_note or "")[:300], "at": _now()},
        # what he asks for. Her grant may narrow any of it and may never widen it.
        "asked": {"scope": dict(scope or {}), "permissions": list(permissions or []),
                  "invocation": invocation if invocation in INVOCATION else DEFAULT_INVOCATION},
        "granted": None,
        "risks": str(risks or "")[:600],
        "touches": list(touches or []),
        "tests": str(tests or "")[:600],
        "history": [{"at": _now(), "event": "proposed"}],
        "created": now or _now(),
    }
    rows.append(row)
    _save(rows)
    return row, ""


def _get(rows, pid):
    for r in rows:
        if r.get("id") == pid:
            return r
    return None


def _narrower(asked, granted):
    """Her grant, bounded by his ask. A scope key she did not touch keeps his value;
    a key she set replaces it; a permission she did not grant is not granted."""
    out = dict(asked or {})
    g = dict(granted or {})
    scope = dict((asked or {}).get("scope") or {})
    scope.update(dict(g.get("scope") or {}))
    out["scope"] = scope
    if "permissions" in g:
        asked_perms = list((asked or {}).get("permissions") or [])
        out["permissions"] = [p for p in (g.get("permissions") or []) if p in asked_perms]
    inv = g.get("invocation") or (asked or {}).get("invocation") or DEFAULT_INVOCATION
    out["invocation"] = inv if inv in INVOCATION else DEFAULT_INVOCATION
    return out


def approve(pid, granted=None, by="gloria"):
    """Her yes. The grant is the narrower of what he asked and what she gave."""
    rows = _load()
    r = _get(rows, pid)
    if r is None:
        return None, "no proposal %r" % pid
    if r["state"] != "proposed":
        return None, "proposal is %s, not proposed" % r["state"]
    r["granted"] = _narrower(r.get("asked"), granted)
    r["state"] = "approved"
    r["history"].append({"at": _now(), "event": "approved", "by": by,
                         "invocation": r["granted"]["invocation"]})
    _save(rows)
    return r, ""


def deny(pid, reason="", by="gloria"):
    rows = _load()
    r = _get(rows, pid)
    if r is None:
        return None, "no proposal %r" % pid
    if r["state"] in TERMINAL:
        return None, "proposal is already %s" % r["state"]
    r["state"] = "denied"
    r["denied_reason"] = str(reason or "")[:400]
    r["history"].append({"at": _now(), "event": "denied", "by": by, "reason": str(reason or "")[:200]})
    _save(rows)
    return r, ""


def mark(pid, state, detail="", extra=None):
    """The builder and the spine report here. installed is the only state that makes
    a capability callable, and nothing reaches it without passing verified first."""
    order = {"approved": 1, "built": 2, "verified": 3, "installed": 4, "resumed": 5}
    rows = _load()
    r = _get(rows, pid)
    if r is None:
        return None, "no proposal %r" % pid
    if state == "refused":
        r["state"] = "refused"
        r["history"].append({"at": _now(), "event": "refused", "detail": str(detail or "")[:300]})
        _save(rows)
        return r, ""
    if state not in order:
        return None, "not a state the forge moves through: %r" % state
    if order.get(r["state"], 0) != order[state] - 1:
        return None, "cannot go from %s to %s" % (r["state"], state)
    r["state"] = state
    if extra:
        r.update({k: v for k, v in extra.items() if k not in ("id", "state", "granted", "asked")})
    r["history"].append({"at": _now(), "event": state, "detail": str(detail or "")[:300]})
    _save(rows)
    return r, ""


def may_invoke(capability, asking=False):
    """(ok, why). The question the executor asks before using a forged capability.
    Anything not installed here is not a forged capability and this says nothing
    about it — the ordinary router capabilities are governed where they always were."""
    for r in _load():
        if r.get("capability") == capability and r.get("state") in ("installed", "resumed"):
            inv = (r.get("granted") or {}).get("invocation", DEFAULT_INVOCATION)
            if inv == "always":
                return True, "granted: always"
            if inv == "never":
                return False, "granted: never — hers to run, not his"
            return (bool(asking), "granted: ask_each_time — %s" % ("asked and allowed" if asking else "not asked"))
    return False, "no installed capability by that name"


def resumable(want_id=None):
    """The intentions waiting on a hand that now exists. This is what makes it
    autonomy rather than a plugin shop: the blocked want is still standing, and the
    capability landing is the event that lets it move again."""
    out = []
    for r in _load():
        if r.get("state") != "installed":
            continue
        wid = (r.get("origin") or {}).get("want_id")
        if want_id and wid != want_id:
            continue
        if _live_want(wid) is None:
            continue
        out.append({"proposal": r["id"], "capability": r["capability"], "want_id": wid,
                    "want": (r.get("origin") or {}).get("want", "")})
    return out


def card(r):
    """One proposal as the app shows it: what he wants, why, what it would touch,
    what it may do, and who may call it."""
    g = r.get("granted") or r.get("asked") or {}
    return {
        "id": r["id"], "state": r["state"], "capability": r["capability"],
        "requested_by": "vintos", "why": r.get("why", ""),
        "origin": (r.get("origin") or {}).get("want", ""),
        "permissions": list(g.get("permissions") or []),
        "scope": dict(g.get("scope") or {}),
        "invocation": g.get("invocation", DEFAULT_INVOCATION),
        "touches": list(r.get("touches") or []), "risks": r.get("risks", ""),
        "tests": r.get("tests", ""),
        "decided": r["state"] not in ("proposed",),
    }


def open_cards():
    return [card(r) for r in _load() if r.get("state") == "proposed"]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        want = None
        if "--state" in sys.argv:
            want = sys.argv[sys.argv.index("--state") + 1]
        rows = [r for r in _load() if want is None or r.get("state") == want]
        if not rows:
            print("no proposals" + (" in state %s" % want if want else ""))
            return
        for r in rows:
            g = r.get("granted") or r.get("asked") or {}
            print("%-11s %-10s %-22s %s" % (r["id"], r["state"], r["capability"],
                                            g.get("invocation", "")))
            print("            %s" % (r.get("why", "")[:96]))
    elif cmd == "show":
        r = _get(_load(), sys.argv[2])
        print(json.dumps(r or {"error": "not found"}, indent=2))
    elif cmd == "approve":
        pid = sys.argv[2]
        granted = {}
        if "--invocation" in sys.argv:
            granted["invocation"] = sys.argv[sys.argv.index("--invocation") + 1]
        scope = {}
        for a in sys.argv[3:]:
            if a.startswith("--scope"):
                continue
            if "=" in a and not a.startswith("--"):
                k, v = a.split("=", 1)
                scope[k] = v
        if scope:
            granted["scope"] = scope
        r, why = approve(pid, granted)
        print(json.dumps(card(r), indent=2) if r else "refused: " + why)
    elif cmd == "deny":
        r, why = deny(sys.argv[2], " ".join(sys.argv[3:]))
        print("denied" if r else "refused: " + why)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
