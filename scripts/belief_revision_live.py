#!/usr/bin/env python3
"""belief_revision_live.py - contradiction back-propagation, applied to his stores. OFF unless Gloria turns it on.

Gloria, 14 November 2026, option (b). belief_revision finds which sources a contradiction traces back to and what
rests on them; belief_revision_answer answers its check questions from his records and the local checker (AEON on
Aegis). This module is the only one that writes, and only when vintos.env says

    BELIEF_REVISION=live

Anything else (or nothing) is off: `run` then does nothing at all. What live mode may do:

  * Revise only HIS beliefs, inferences and readings, each through one field its readers already honour:
      a tension he inferred      tension-ledger.json   status -> CONTRADICTED (withdraw) / SUPPORTED -> HYPOTHESIS (lower)
      his private reading (E3)   tension-ledger.json   that evidence item's "invalid" -> true
      a causal hypothesis        causality-hypotheses  confidence one level down (lower) / "low" (withdraw)
      a sediment belief          belief-sediment.json  confidence lowered (never below 0.06, so no pass deletes it)
      an inference he recorded   reality-anchor.json   confidence lowered (events whose source is "inference" only)
    An inference STEP is revised through the belief it produced.
  * Never revise her words. A source of hers that the evidence goes against is flagged to her (one note a day at
    most, through gloria_asks, carrying counts only - no text leaves Aegis) and listed in belief-revision-flags.json.
  * Never touch SOUL.md or SELF-MODEL.md, and never revise a self-model entry (causal-self-model, self-model
    sentences): those are flagged, like hers. A tension she CONFIRMED is never changed either.
  * Records of what happened (his messages as sent, nightly evidence, journal text, claims already corrected) are not
    beliefs: flagged, never rewritten.
  * A revision that rests on a single check answer is held (belief_revision.localize), not applied.
  * At most MAX_PER_DAY store changes a day (BELIEF_REVISION_MAX_PER_DAY); the rest wait, most blamed first.
  * Every change is a compare-and-set under the store's lock (store_guard.transaction), logged with the whole
    superseded record in belief-revisions.jsonl, and marked on the record ("belief_revision": rev id, field, was).
    A record already revised and not reverted is not revised again.

    python3 belief_revision_live.py run [--memory DIR] [--dry-run] [--checks N]
    python3 belief_revision_live.py list                    # revisions in force
    python3 belief_revision_live.py flags                   # what waits for her
    python3 belief_revision_live.py revert --all            # undo every revision (newest first)
    python3 belief_revision_live.py revert REV-... [REV-...]
"""
import argparse, copy, hashlib, json, os, secrets, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import belief_revision as BR
import store_guard

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
LOG_NAME = "belief-revisions.jsonl"
FLAGS_NAME = "belief-revision-flags.json"
RUNS_NAME = "belief-revision-runs.jsonl"
MAX_PER_DAY = 5
CHECKS = 24                   # check questions per run (localize budget)
FLOOR = 0.06                  # a lowered numeric confidence never drops to where a decay pass deletes the record
LEVELS = ["low", "medium", "high"]
TENSION_LOWER = {"SUPPORTED": "HYPOTHESIS", "CONTESTED": "HYPOTHESIS"}
TENSION_WITHDRAWABLE = ("HYPOTHESIS", "SUPPORTED", "CONTESTED")
SELF_MODEL_PREFIXES = ("c:csm:", "m:sentence:", "m:writer")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mode():
    """'live' only when BELIEF_REVISION=live (the environment, then vintos.env). Anything else is 'off'."""
    v = os.environ.get("BELIEF_REVISION")
    if v is None:
        try:
            import env_file
            v = env_file.value("BELIEF_REVISION", "")
        except Exception:
            v = ""
    return "live" if str(v).strip().lower() == "live" else "off"


def max_per_day():
    try:
        return max(0, int(os.environ.get("BELIEF_REVISION_MAX_PER_DAY") or MAX_PER_DAY))
    except ValueError:
        return MAX_PER_DAY


def _fp(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _read_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def _append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with store_guard.transaction(path):
        with open(path, "a") as f:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")


# -- where a node lives in his stores --------------------------------------------------------------------------------
class Target:
    """One field of one record in one store: how to find it, and what a revision may set it to."""

    def __init__(self, node, store, field, locate, new_value, why=""):
        self.node, self.store, self.field, self.locate, self.new_value, self.why = node, store, field, locate, new_value, why


def _list(data, key):
    return data.get(key) if isinstance(data, dict) and isinstance(data.get(key), list) else None


def _by(key, idkey, ident):
    def locate(data):
        for r in _list(data, key) or []:
            if isinstance(r, dict) and str(r.get(idkey)) == ident:
                return r
        return None
    return locate


def _by_index(key, i, fp_field, fp):
    def locate(data):
        rows = _list(data, key) or []
        if 0 <= i < len(rows) and isinstance(rows[i], dict) and _fp(rows[i].get(fp_field)) == fp:
            return rows[i]
        for r in rows:                              # the list moved: find the same record by its fingerprint
            if isinstance(r, dict) and _fp(r.get(fp_field)) == fp:
                return r
        return None
    return locate


def _numeric(factor):
    def new(cur):
        try:
            cur = float(cur)
        except (TypeError, ValueError):
            return None
        return round(max(FLOOR, cur * factor), 4) if cur > FLOOR else None
    return new


def _level(withdraw):
    def new(cur):
        c = str(cur or "").lower()
        if c not in LEVELS:
            return None
        return "low" if withdraw else LEVELS[max(0, LEVELS.index(c) - 1)]
    return new


def target(node, action, factor, mem):
    """(Target, None) for a node this module may revise, or (None, why it is only flagged)."""
    if node.startswith(SELF_MODEL_PREFIXES):
        return None, "self-model entry: flagged, never revised"
    withdraw = action in ("retract", "withdraw")
    if node.startswith("t:tension:"):
        tid = node[10:]

        def new(cur):
            if withdraw:
                return "CONTRADICTED" if cur in TENSION_WITHDRAWABLE else None
            return TENSION_LOWER.get(cur)
        return Target(node, "tension-ledger.json", "status", _by("tensions", "tension_id", tid), new), None
    if node.startswith("t:ev:"):
        eid = node[5:]

        def locate(data):
            for t in _list(data, "tensions") or []:
                for e in (t.get("evidence") or []) if isinstance(t, dict) else []:
                    if isinstance(e, dict) and str(e.get("evidence_id")) == eid:
                        return e if e.get("channel") == "E3" else None    # only his private reading
            return None
        return Target(node, "tension-ledger.json", "invalid", locate, lambda cur: True if cur is not True else None,
                      "his private reading"), None
    if node.startswith("c:hyp:"):
        return Target(node, "causality-hypotheses.json", "confidence", _by("hypotheses", "hypothesis_id", node[6:]),
                      _level(withdraw)), None
    if node.startswith("c:belief:"):
        try:
            i = int(node[9:])
        except ValueError:
            return None, "unreadable id"
        rows = _list(store_guard.load_json(os.path.join(mem, "belief-sediment.json"), {}), "beliefs") or []
        if not (0 <= i < len(rows)) or not isinstance(rows[i], dict):
            return None, "record not found"
        return Target(node, "belief-sediment.json", "confidence",
                      _by_index("beliefs", i, "pattern", _fp(rows[i].get("pattern"))),
                      _numeric(FLOOR if withdraw else factor)), None
    if node.startswith("r:"):
        eid = node[2:]

        def locate(data):
            r = _by("events", "id", eid)(data)
            return r if r is not None and r.get("source") == "inference" else None
        return Target(node, "reality-anchor.json", "confidence", locate, _numeric(FLOOR if withdraw else factor)), None
    return None, "a record of what happened, not a belief of his: flagged, never rewritten"


# -- applying, under the store's lock ----------------------------------------------------------------------------------
def in_force(mem):
    """Applied revisions not reverted, by rev id."""
    rows = _read_jsonl(os.path.join(mem, LOG_NAME))
    reverted = {r["revert"] for r in rows if r.get("revert") and r.get("result") == "restored"}
    return {r["rev"]: r for r in rows if r.get("rev") and not r.get("revert") and r["rev"] not in reverted}


def applied_today(mem, today=None):
    today = today or _now()[:10]
    return sum(1 for r in _read_jsonl(os.path.join(mem, LOG_NAME)) if r.get("rev") and not r.get("revert")
               and str(r.get("at", ""))[:10] == today)


def apply(t, mem, meta, dry=False):
    """Compare-and-set one field under the store's lock. Returns the log row, or None with why."""
    path = os.path.join(mem, t.store)
    rev = "REV-" + secrets.token_hex(4)
    out = {}

    def mutate(data):
        rec = t.locate(data)
        if rec is None:
            out["why"] = "record not found (or not his to revise)"
            return None
        mark = rec.get("belief_revision")
        if isinstance(mark, dict) and mark.get("rev") in out["in_force"]:
            out["why"] = "already revised (%s)" % mark.get("rev")
            return None
        cur = rec.get(t.field)
        new = t.new_value(cur)
        if new is None or new == cur:
            out["why"] = "nothing to change (%s is %r)" % (t.field, cur)
            return None
        out["row"] = dict(meta, rev=rev, at=_now(), node=t.node, store=t.store, field=t.field, was=cur, now=new,
                          superseded=copy.deepcopy(rec))
        if dry:
            return None
        rec[t.field] = new
        rec["belief_revision"] = {"rev": rev, "field": t.field, "was": cur, "at": out["row"]["at"]}
        return data

    out["in_force"] = set(in_force(mem))
    store_guard.locked_update(path, mutate, default={}, reader="belief_revision_live")
    if "row" not in out:
        return None, out.get("why")
    if not dry:
        _append(os.path.join(mem, LOG_NAME), out["row"])
    return out["row"], None


def _relocate(row, mem):
    """Find the record a logged revision changed. A sediment belief is found by the superseded record's own
    fingerprint, never by its old position (the list may have moved since)."""
    if row["node"].startswith("c:belief:"):
        fp = _fp((row.get("superseded") or {}).get("pattern"))
        return lambda data: next((r for r in _list(data, "beliefs") or [] if isinstance(r, dict)
                                  and _fp(r.get("pattern")) == fp), None)
    t, _why = target(row["node"], "lower", 1.0, mem)
    return t.locate if t else (lambda data: None)


def revert(mem, revs=None, force=False):
    """Undo revisions, newest first: the field goes back to what it was, if nobody has changed it since (or force).
    revs=None reverts every revision in force. Returns [(rev, result)]."""
    live = in_force(mem)
    todo = [r for r in sorted(live.values(), key=lambda r: r["at"], reverse=True) if revs is None or r["rev"] in revs]
    results = []
    for row in todo:
        path = os.path.join(mem, row["store"])
        res = {}
        locate = _relocate(row, mem)

        def mutate(data):
            rec = locate(data)
            if rec is None:
                res["r"] = "record gone; superseded copy kept in %s" % LOG_NAME
                return None
            if rec.get(row["field"]) != row["now"] and not force:
                res["r"] = "changed since (%s is now %r); not restored - use --force" % (row["field"], rec.get(row["field"]))
                return None
            rec[row["field"]] = row["was"]
            if row["was"] is None and row["field"] not in row["superseded"]:
                rec.pop(row["field"], None)
            mark = rec.get("belief_revision")
            if isinstance(mark, dict) and mark.get("rev") == row["rev"]:
                rec.pop("belief_revision", None)
            res["r"] = "restored"
            return data

        store_guard.locked_update(path, mutate, default={}, reader="belief_revision_live")
        _append(os.path.join(mem, LOG_NAME), {"revert": row["rev"], "at": _now(), "node": row["node"],
                                               "store": row["store"], "result": res["r"]})
        results.append((row["rev"], res["r"]))
    unknown = sorted(set(revs or ()) - set(live))
    results += [(r, "not in force (unknown or already reverted)") for r in unknown]
    return results


# -- flags: her words, self-model entries, records, held revisions -----------------------------------------------------
def _flag(flags, node, kind, why, blame, at):
    f = flags.setdefault(node, {"node": node, "kind": kind, "first_at": at, "told": False})
    f.update(why=why, blame=blame, last_at=at)
    return f


def tell_her(flags, mem, send=None, today=None):
    """One note a day at most, only when something new waits for her: counts only, never text (the push goes through
    ntfy). The list itself stays on Aegis."""
    today = today or _now()[:10]
    new = [f for f in flags.values() if not f.get("told") and f["kind"] in ("gloria", "self_model")]
    if not new or any(str(f.get("told_at", ""))[:10] == today for f in flags.values()):
        return None
    hers = sum(1 for f in new if f["kind"] == "gloria")
    selfm = len(new) - hers
    parts = []
    if hers:
        parts.append("%d of your recorded words now stand against his other evidence" % hers)
    if selfm:
        parts.append("%d of his self-model entries look wrong to it" % selfm)
    note = ("Belief revision (%s): %s. Nothing of yours, and no self-model entry, was changed - they wait for you: "
            "python3 belief_revision_live.py flags" % (today, "; ".join(parts)))
    try:
        import gloria_asks
        row, _line = gloria_asks.tell(note, by="belief_revision", where="belief revision", send=send)
    except Exception:
        row = None
    for f in new:
        f["told"] = bool(row)
        f["told_at"] = _now() if row else ""
    return row


# -- one run ---------------------------------------------------------------------------------------------------------
def run(mem=None, dry=False, checks=CHECKS, transport=None, send=None, at=None):
    mem = mem or MEMORY
    if mode() != "live" and not dry:
        return {"ran": False, "reason": "BELIEF_REVISION is not live"}
    import belief_revision_sources as S
    import belief_revision_answer as A
    at = at or _now()
    g, stats = S.build(mem)
    answerer = A.Answerer(A.StoreRecords(mem, g), transport=transport)
    p = BR.localize(g, answerer, budget=checks, at=at)
    held = set(p.get("held") or [])
    # what each revision means for his stores: a step through the belief it produced; strongest action per record
    wants = {}

    def want(node, action, factor, blame, why):
        cur = wants.get(node)
        rank = {"withdraw": 2, "retract": 2, "lower": 1}
        if cur is None or rank[action] > rank[cur["action"]] or (rank[action] == rank[cur["action"]]
                                                                 and factor < cur["factor"]):
            wants[node] = {"action": action, "factor": factor, "blame": blame, "why": why}

    flags = store_guard.load_json(os.path.join(mem, FLAGS_NAME), {}) or {}
    flagged = {"gloria": 0, "self_model": 0, "record": 0, "held": 0, "not_captured": 0}
    for r in p["revisions"]:
        node, kind = r["node"], r["kind"]
        if r["action"] == "flag_for_gloria" or kind == "gloria":
            _flag(flags, node, "gloria", "the evidence goes against her word; never revised", r["blame"], at)
            flagged["gloria"] += 1
            continue
        if r["action"] not in ("retract", "lower"):
            if r["reason"] == BR.NOT_CAPTURED:
                flagged["not_captured"] += 1
            if (node[5:] if node.startswith("rule:") else node).startswith(SELF_MODEL_PREFIXES):
                _flag(flags, node, "self_model", "self-model entry the evidence questions: flagged, never revised",
                      r["blame"], at)
                flagged["self_model"] += 1
            elif node in held:
                _flag(flags, node, "held", "rests on a single check answer; question left open", r["blame"], at)
                flagged["held"] += 1
            continue
        base = node[5:] if node.startswith("rule:") else node
        want(base, r["action"], round(1.0 - r["blame"], 4), r["blame"], "blamed for %s" % ", ".join(r["conflicts"][:3]))
    for d in p["rederive"]:
        f = (d["standing_after"] / d["standing_before"]) if d["standing_before"] else 0.0
        want(d["node"], d["action"], round(min(1.0, f), 4), None, "rests on a revised source")
    plan_rows, applied, deferred = [], [], []
    room = max(0, max_per_day() - applied_today(mem, at[:10]))
    revised_nodes = {r["node"] for r in in_force(mem).values()}
    for node, w in sorted(wants.items(), key=lambda kv: (-(kv[1]["blame"] or 0), kv[0])):
        t, why = target(node, w["action"], w["factor"], mem)
        if t is None:
            k = "self_model" if node.startswith(SELF_MODEL_PREFIXES) else "record"
            _flag(flags, node, k, why, w["blame"], at)
            flagged[k] += 1
            continue
        if node in revised_nodes:
            continue                                             # revised before and still in force: once is enough
        if not dry and len(applied) >= room:
            deferred.append(node)
            continue
        meta = {"action": w["action"], "blame": w["blame"], "why": w["why"], "mode": "dry-run" if dry else "live",
                "answers": [{"node": a["node"], "answer": a["answer"], "by": (a.get("provenance") or {}).get("by")}
                            for a in p.get("answers") or []][:24]}
        row, why = apply(t, mem, meta, dry=dry)
        if row:
            (plan_rows if dry else applied).append({k: row[k] for k in ("rev", "node", "store", "field", "was", "now")})
    if not dry:
        store_guard.write_json(os.path.join(mem, FLAGS_NAME), flags, reader="belief_revision_live")
        told = tell_her(flags, mem, send=send, today=at[:10])
        if told is not None:
            store_guard.write_json(os.path.join(mem, FLAGS_NAME), flags, reader="belief_revision_live")
    summary = {"ran": True, "mode": "dry-run" if dry else "live", "at": at, "sources": {k: v for k, v in stats.items()
                                                                                       if k != "world_model_note"},
               "checks": len(p.get("asked") or []),
               "answered_by": _count((a.get("provenance") or {}).get("by") for a in p.get("answers") or []),
               "unknown": sum(1 for a in p.get("answers") or [] if a["answer"] is None),
               "held": len(held), "applied": applied if not dry else [], "would_apply": plan_rows,
               "deferred_daily_limit": len(deferred), "flagged": flagged}
    if not dry:
        _append(os.path.join(mem, RUNS_NAME), {k: (v if k not in ("applied",) else [
            {kk: x[kk] for kk in ("rev", "node", "store", "field")} for x in v]) for k, v in summary.items()})
    return summary


def _count(items):
    out = {}
    for i in items:
        out[str(i)] = out.get(str(i), 0) + 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--memory", default=None)
    r.add_argument("--dry-run", action="store_true", help="show what would change; write nothing (still asks checks)")
    r.add_argument("--checks", type=int, default=CHECKS)
    for name in ("list", "flags"):
        s = sub.add_parser(name)
        s.add_argument("--memory", default=None)
    v = sub.add_parser("revert")
    v.add_argument("revs", nargs="*")
    v.add_argument("--all", action="store_true")
    v.add_argument("--force", action="store_true", help="restore even if the field changed since")
    v.add_argument("--memory", default=None)
    a = ap.parse_args(argv)
    mem = a.memory or MEMORY
    if a.cmd == "run":
        out = run(mem, dry=a.dry_run, checks=a.checks)
    elif a.cmd == "list":
        out = [{k: x[k] for k in ("rev", "at", "node", "store", "field", "was", "now")} for x in in_force(mem).values()]
    elif a.cmd == "flags":
        out = store_guard.load_json(os.path.join(mem, FLAGS_NAME), {})
    else:
        if not a.all and not a.revs:
            ap.error("revert: name REV ids, or --all")
        out = revert(mem, None if a.all else set(a.revs), force=a.force)
    print(json.dumps(out, indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
