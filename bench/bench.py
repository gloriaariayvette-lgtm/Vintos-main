#!/usr/bin/env python3
"""bench.py — the work bench. Her agents, their tasks, and who does what.

This is NOT the agent room. The room in `agent-room/` is Vintos's: three lenses
arguing as him. Nothing here reads it, writes it, or shares a store with it. This is
tooling for the agents that build him — Claude Code, Codex, Grok Build, Gemma — so
they stop passing work through Gloria by hand.

THE LAW, AND IT IS ONE SENTENCE

    No task is worked until she has approved it.

A task is proposed, and there it stays. `claim()` refuses anything that is not
approved. An agent cannot approve its own work, cannot approve another agent's work,
and cannot approve by writing a state — approval is a separate act with her name on
it. The one exception is hers to grant and hers alone: a kind of task she has listed
in an agent's own config as pre-approved. She writes that list; no agent may.

EVERY AGENT KEEPS ITS OWN LEDGER

    bench/ledgers/<agent>.jsonl

Append-only. Nothing is ever rewritten — state is replayed from the events, so the
record of what happened cannot be edited into what should have happened. An event
that concerns two agents (a hand-off) is appended to both ledgers with the same task
id, so each agent's ledger is a complete account of its own work and neither has to
read the other's to know what it owes.

AND ITS OWN INSTRUCTIONS

    bench/agents/<agent>.json

What the agent is, what it may do, and — the part that saves money — a `delegate`
map: which kinds of work it should hand to a cheaper agent instead of doing itself.
A grep, a verdict, a regenerated report do not need an expensive model. The map is
per agent, because what is cheap work for one is the whole job for another.

    python3 bench.py propose --by claude --kind grep --what "..." [--for gemma]
    python3 bench.py pending                       what is waiting on her
    python3 bench.py approve T-xxxx                her yes
    python3 bench.py deny T-xxxx "reason"          her no
    python3 bench.py claim T-xxxx --by gemma       refused unless approved
    python3 bench.py done T-xxxx --by gemma --result "..."
    python3 bench.py fail T-xxxx --by gemma --why "..."
    python3 bench.py handoff T-xxxx --to grok --why "..."
    python3 bench.py mine --by codex               that agent's open work
    python3 bench.py show T-xxxx                   the whole history of one task
    python3 bench.py agents                        who exists and what they delegate
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("BENCH_ROOT") or HERE
LEDGERS = os.path.join(ROOT, "ledgers")
AGENTS = os.path.join(ROOT, "agents")

# proposed -> approved -> claimed -> done | failed
#          -> denied                      (hers)
# handed_off closes a task and opens a fresh one for someone else, linked by parent.
OPEN = ("proposed", "approved", "claimed")
TERMINAL = ("done", "failed", "denied", "handed_off")
EVENTS = ("proposed", "approved", "denied", "claimed", "done", "failed", "handed_off")

HERS = "gloria"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ledger(agent):
    return os.path.join(LEDGERS, "%s.jsonl" % _safe(agent))


def _safe(name):
    n = "".join(c for c in str(name or "").strip().lower() if c.isalnum() or c in "-_")
    return n or "unknown"


def agent_config(agent):
    """What she has told this agent about itself. A missing config is not an error —
    an agent with no instructions simply delegates nothing and pre-approves nothing."""
    try:
        with open(os.path.join(AGENTS, "%s.json" % _safe(agent))) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def agents():
    out = {}
    try:
        for f in sorted(os.listdir(AGENTS)):
            if f.endswith(".json"):
                out[f[:-5]] = agent_config(f[:-5])
    except Exception:
        pass
    return out


def _append(agent, row):
    """One event, to one agent's ledger. Append-only and fsynced: a ledger that loses
    its last line loses the fact that work was approved."""
    os.makedirs(LEDGERS, exist_ok=True)
    path = _ledger(agent)
    with open(path, "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return path


def _write(row, *who):
    """An event is appended to the ledger of every agent it concerns, once each, so no
    agent has to read another's ledger to know what it owes or is owed."""
    seen = []
    for a in who:
        a = _safe(a)
        if a and a != "unknown" and a not in seen:
            seen.append(a)
            _append(a, row)
    return seen


def events(agent=None, task=None):
    """Every event, oldest first. Reading is a replay; nothing here mutates."""
    out = []
    names = [_safe(agent)] if agent else None
    try:
        files = ["%s.jsonl" % n for n in names] if names else sorted(os.listdir(LEDGERS))
    except Exception:
        return out
    for f in files:
        if not f.endswith(".jsonl"):
            continue
        try:
            for line in open(os.path.join(LEDGERS, f)):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if task and r.get("task") != task:
                    continue
                out.append(r)
        except Exception:
            continue
    # one event may live in two ledgers; the pair (task, at, event) identifies it
    seen, uniq = set(), []
    for r in sorted(out, key=lambda r: (r.get("at", ""), r.get("task", ""))):
        k = (r.get("task"), r.get("at"), r.get("event"), r.get("by"))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


def task(task_id):
    """One task, replayed from its events. The last event that moved it is its state."""
    rows = events(task=task_id)
    if not rows:
        return None
    t = {"task": task_id, "state": None, "history": rows}
    for r in rows:
        e = r.get("event")
        if e == "proposed":
            t.update(state="proposed", by=r.get("by"), owner=r.get("for") or r.get("by"),
                     kind=r.get("kind"), what=r.get("what"), repo=r.get("repo"),
                     why=r.get("why"), parent=r.get("parent"), proposed_at=r.get("at"))
        elif e in EVENTS:
            t["state"] = e
            if e == "approved":
                t["approved_by"] = r.get("by")
                t["auto"] = bool(r.get("auto"))
            if e == "claimed":
                t["owner"] = r.get("by")
            if e == "handed_off":
                t["handed_to"] = r.get("for")
                t["child"] = r.get("child")
            if e in ("done", "failed", "denied"):
                t["outcome"] = r.get("result") or r.get("why") or ""
    return t


def _new_id():
    return "T-" + uuid.uuid4().hex[:8]


def pre_approved(agent, kind):
    """A kind of work she has said this agent may start without asking. It lives in
    HER config file for that agent; nothing in this module can add to it, and an agent
    editing its own config to widen it would be editing a file she owns."""
    cfg = agent_config(agent)
    allowed = cfg.get("auto_approve") or []
    return isinstance(allowed, list) and str(kind or "") in allowed


def route(by, kind):
    """Who should do this, according to the proposing agent's own instructions. Returns
    the delegate for that kind of work, or None to mean 'keep it'."""
    cfg = agent_config(by)
    table = cfg.get("delegate") or {}
    if not isinstance(table, dict):
        return None
    target = table.get(str(kind or "")) or table.get("*")
    return _safe(target) if target else None


def propose(by, what, kind="", for_agent=None, repo="", why="", parent=None):
    """An agent asks for work to exist. It does not start. Returns (task, why-refused).

    If the proposer's instructions delegate this kind of work, the task is addressed to
    that agent automatically — that is the whole point of the delegate map — but it is
    still only proposed. Nobody works until she says so."""
    by = _safe(by)
    if by in ("", "unknown"):
        return None, "a task must name the agent proposing it"
    if not str(what or "").strip():
        return None, "a task must say what it is"
    owner = _safe(for_agent) if for_agent else (route(by, kind) or by)
    tid = _new_id()
    row = {"at": _now(), "task": tid, "event": "proposed", "by": by, "for": owner,
           "kind": str(kind or "")[:40], "what": str(what)[:2000], "repo": str(repo or "")[:80],
           "why": str(why or "")[:600]}
    if parent:
        row["parent"] = parent
    _write(row, by, owner)
    if pre_approved(owner, kind):
        approve(tid, by=HERS, auto=True)
    return task(tid), ""


def approve(task_id, by=HERS, auto=False):
    """Hers. An agent calling this with its own name is refused — approval is not a
    state an agent may write, it is a separate act with her name on it."""
    t = task(task_id)
    if t is None:
        return None, "no task %r" % task_id
    if t["state"] != "proposed":
        return None, "task is %s, not proposed" % t["state"]
    who = _safe(by)
    if who != HERS:
        return None, ("only %s approves; %r cannot approve its own work or anyone else's"
                      % (HERS, who))
    if auto and not pre_approved(t.get("owner"), t.get("kind")):
        return None, "not a kind %s may start unasked" % t.get("owner")
    row = {"at": _now(), "task": task_id, "event": "approved", "by": HERS,
           "for": t.get("owner"), "auto": bool(auto)}
    _write(row, t.get("by"), t.get("owner"))
    return task(task_id), ""


def deny(task_id, why="", by=HERS):
    t = task(task_id)
    if t is None:
        return None, "no task %r" % task_id
    if t["state"] in TERMINAL:
        return None, "task is already %s" % t["state"]
    if _safe(by) != HERS:
        return None, "only %s denies" % HERS
    row = {"at": _now(), "task": task_id, "event": "denied", "by": HERS,
           "for": t.get("owner"), "why": str(why or "")[:600]}
    _write(row, t.get("by"), t.get("owner"))
    return task(task_id), ""


def claim(task_id, by):
    """An agent starts work. THE gate: refused unless she has approved it."""
    t = task(task_id)
    if t is None:
        return None, "no task %r" % task_id
    who = _safe(by)
    if t["state"] == "proposed":
        return None, "not approved yet — %s has not said yes to this one" % HERS
    if t["state"] != "approved":
        return None, "task is %s, not approved" % t["state"]
    if t.get("owner") and who != t["owner"]:
        return None, "this one is addressed to %s, not %s" % (t["owner"], who)
    row = {"at": _now(), "task": task_id, "event": "claimed", "by": who, "for": who}
    _write(row, who, t.get("by"))
    return task(task_id), ""


def done(task_id, by, result=""):
    return _finish(task_id, by, "done", result=result)


def fail(task_id, by, why=""):
    return _finish(task_id, by, "failed", why=why)


def _finish(task_id, by, event, result="", why=""):
    t = task(task_id)
    if t is None:
        return None, "no task %r" % task_id
    if t["state"] != "claimed":
        return None, "task is %s; only claimed work finishes" % t["state"]
    who = _safe(by)
    if who != t.get("owner"):
        return None, "%s is holding this, not %s" % (t.get("owner"), who)
    row = {"at": _now(), "task": task_id, "event": event, "by": who, "for": who,
           "result": str(result or "")[:4000], "why": str(why or "")[:600]}
    _write(row, who, t.get("by"))
    return task(task_id), ""


def handoff(task_id, to, by=None, why=""):
    """Give the work to someone else. The old task closes and a NEW one opens for them
    — proposed, not approved, because a hand-off is not a way around her yes."""
    t = task(task_id)
    if t is None:
        return None, "no task %r" % task_id
    if t["state"] in TERMINAL:
        return None, "task is already %s" % t["state"]
    target = _safe(to)
    if target in ("", "unknown"):
        return None, "a hand-off must name who is taking it"
    if target == t.get("owner"):
        return None, "%s already holds this one" % target
    child, cwhy = propose(by=_safe(by or t.get("owner")), what=t.get("what", ""),
                          kind=t.get("kind", ""), for_agent=target, repo=t.get("repo", ""),
                          why=str(why or "")[:600] or ("handed on from " + task_id),
                          parent=task_id)
    if child is None:
        return None, "could not open the new task: " + cwhy
    row = {"at": _now(), "task": task_id, "event": "handed_off",
           "by": _safe(by or t.get("owner")), "for": target,
           "child": child["task"], "why": str(why or "")[:600]}
    _write(row, t.get("owner"), t.get("by"), target)
    return child, ""


def pending():
    """Everything waiting on her, oldest first. This is the list she works from."""
    return [t for t in _all() if t and t["state"] == "proposed"]


def mine(agent, states=OPEN):
    a = _safe(agent)
    return [t for t in _all() if t and t.get("owner") == a and t["state"] in states]


def _all():
    ids, out = [], []
    for r in events():
        if r.get("task") not in ids:
            ids.append(r.get("task"))
    for i in ids:
        out.append(task(i))
    return out


def _line(t):
    return "%-11s %-9s %-8s %-10s %s" % (t["task"], t["state"], t.get("kind", "") or "-",
                                         t.get("owner", "") or "-",
                                         (t.get("what", "") or "")[:60])


def main():
    a = sys.argv[1:]
    cmd = a[0] if a else "pending"

    def opt(name, default=None):
        return a[a.index(name) + 1] if name in a else default

    if cmd == "propose":
        t, why = propose(by=opt("--by", ""), what=opt("--what", ""), kind=opt("--kind", ""),
                         for_agent=opt("--for"), repo=opt("--repo", ""), why=opt("--why", ""))
        print(_line(t) if t else "refused: " + why)
        if t and t["state"] == "proposed":
            print("       waiting on %s: bench.py approve %s" % (HERS, t["task"]))
    elif cmd == "pending":
        rows = pending()
        print("\n".join(_line(t) for t in rows) if rows else "nothing waiting on %s" % HERS)
    elif cmd == "approve":
        t, why = approve(a[1], by=opt("--by", HERS))
        print(_line(t) if t else "refused: " + why)
    elif cmd == "deny":
        t, why = deny(a[1], " ".join(x for x in a[2:] if not x.startswith("--")))
        print(_line(t) if t else "refused: " + why)
    elif cmd == "claim":
        t, why = claim(a[1], by=opt("--by", ""))
        print(_line(t) if t else "refused: " + why)
    elif cmd == "done":
        t, why = done(a[1], by=opt("--by", ""), result=opt("--result", ""))
        print(_line(t) if t else "refused: " + why)
    elif cmd == "fail":
        t, why = fail(a[1], by=opt("--by", ""), why=opt("--why", ""))
        print(_line(t) if t else "refused: " + why)
    elif cmd == "handoff":
        t, why = handoff(a[1], to=opt("--to", ""), by=opt("--by"), why=opt("--why", ""))
        print(_line(t) if t else "refused: " + why)
    elif cmd == "mine":
        rows = mine(opt("--by", ""))
        print("\n".join(_line(t) for t in rows) if rows else "nothing open")
    elif cmd == "show":
        t = task(a[1])
        print(json.dumps(t, indent=2) if t else "no such task")
    elif cmd == "agents":
        for name, cfg in sorted(agents().items()):
            print("%-8s %s" % (name, cfg.get("what", "")))
            d = cfg.get("delegate") or {}
            if d:
                print("         delegates: " + ", ".join("%s -> %s" % kv for kv in sorted(d.items())))
            if cfg.get("auto_approve"):
                print("         may start unasked: " + ", ".join(cfg["auto_approve"]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
