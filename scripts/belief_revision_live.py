#!/usr/bin/env python3
"""belief_revision_live.py - contradiction back-propagation, applied to his stores. OFF unless Gloria turns it on.

Gloria, 14 November 2026, option (b). belief_revision finds which sources a contradiction traces back to and what
rests on them; belief_revision_answer answers its check questions from his records and the local checker (AEON on
Aegis). This module is the only one that writes, and only when vintos.env says

    BELIEF_REVISION=live

Anything else (or nothing) is off: `run` then does nothing at all (`run --dry-run` still asks the local checker
and writes nothing). What live mode may do:

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
    A record revised once is never revised again by this module, and one she reverted stays reverted.

The repair chooser (Gloria, 14 November 2026: "keep my words unchanged, preserve a reversible history while in
testing (1 week...), and the normal regression gate"). With BELIEF_REVISION_SOLVER=exact (environment, then
vintos.env) the sources to revise are the exact minimum-energy repair (belief_revision_verify.choose) over what may be
revised - her words bound out of it, only ever flagged - instead of belief_revision's own plan; the checks and their
answers are the same. It is a TRIAL: the first live run that sees the switch starts it, and it lasts TRIAL_DAYS days
(belief-revision-solver-trial.json); from the expiry date on, every run uses the old chooser again and says so in
its run log, unless BELIEF_REVISION_SOLVER_UNTIL=YYYY-MM-DD sets a later end. During the trial every run logs, as
counts and ids only, what the solver chose beside what the old chooser would have done; every solver revision is an
ordinary logged, marked, revertible revision ("chooser": "exact" on its row). Every live limit above holds for it.
If the solver cannot prove a minimum, that run uses the old chooser and logs why.

    python3 belief_revision_live.py run [--memory DIR] [--dry-run] [--checks N]
    python3 belief_revision_live.py list                    # revisions in force
    python3 belief_revision_live.py flags                   # what waits for her
    python3 belief_revision_live.py trial                   # the solver trial: state, start, expiry
    python3 belief_revision_live.py revert --all            # undo every revision (newest first)
    python3 belief_revision_live.py revert --solver         # undo every revision the solver chose
    python3 belief_revision_live.py revert REV-... [REV-...]
"""
import argparse, copy, hashlib, json, os, secrets, sys
from datetime import datetime, timedelta, timezone

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
TRIAL_NAME = "belief-revision-solver-trial.json"
TRIAL_DAYS = 7                # the exact-solver trial lasts a week from its first live run (Gloria, 14 November 2026)
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


def _setting(name):
    v = os.environ.get(name)
    if v is None:
        try:
            import env_file
            v = env_file.value(name, "")
        except Exception:
            v = ""
    return str(v or "").strip()


def _day(s):
    try:
        return datetime.strptime(str(s).strip()[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def solver_trial(mem, at, dry=False):
    """Which chooser this run uses, and the trial's state (ids and dates only). The exact solver only while
    BELIEF_REVISION_SOLVER=exact and the trial has not expired: the first live run that sees the switch writes the
    start and the expiry (start + TRIAL_DAYS); BELIEF_REVISION_SOLVER_UNTIL=YYYY-MM-DD, when set, is the expiry
    instead (her extension). A dry run never starts the clock."""
    if _setting("BELIEF_REVISION_SOLVER").lower() != "exact":
        return False, {"state": "off", "chooser": "old"}
    path = os.path.join(mem, TRIAL_NAME)
    today = _day(at) or datetime.now(timezone.utc).date()
    trial = store_guard.load_json(path, {}) or {}
    started = _day(trial.get("started"))
    if started is None:
        started = today
        trial = {"started": started.isoformat(), "expires": (started + timedelta(days=TRIAL_DAYS)).isoformat(),
                 "days": TRIAL_DAYS}
        if not dry:
            store_guard.write_json(path, trial, reader="belief_revision_live")
    expires = _day(trial.get("expires")) or started + timedelta(days=TRIAL_DAYS)
    info = {"started": started.isoformat(), "expires": expires.isoformat()}
    until = _setting("BELIEF_REVISION_SOLVER_UNTIL")
    if until:
        if _day(until):
            expires = _day(until)
            info.update(expires=expires.isoformat(), extended_by="BELIEF_REVISION_SOLVER_UNTIL")
        else:
            info["until_unreadable"] = True                     # a typo never extends the trial
    if today >= expires:
        info.update(state="expired", chooser="old", fell_back="trial expired on %s; the old chooser is used"
                    % expires.isoformat())
        if not dry and trial.get("fell_back_on") is None:
            trial["fell_back_on"] = today.isoformat()
            store_guard.write_json(path, trial, reader="belief_revision_live")
        return False, info
    info.update(state="active", chooser="exact")
    return True, info


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
        self.expect = None                  # when set, the field must still hold this value (compare-and-set)


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


def target(node, action, factor, mem, plan=None):
    """(Target, None) for a node this module may revise, or (None, why it is only flagged).
    plan: the graph node's meta as the plan saw it ({"fp", "confidence"}): a sediment belief is found by the
    fingerprint taken when the graph was built, and a confidence is only changed while it is still what the plan
    saw (review 2: a decay pass may move or change the list while the checks are being asked)."""
    t, why = _target(node, action, factor, mem, plan or {})
    if t is not None and plan and node.startswith(("c:belief:", "c:hyp:")) and "confidence" in plan:
        t.expect = plan["confidence"]
    return t, why


def _target(node, action, factor, mem, plan):
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
                        if t.get("status") == "CONFIRMED":
                            return None              # nothing under a tension she confirmed is changed (review 3)
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
        if not plan.get("fp"):
            return None, "no fingerprint from the plan: not revised"
        return Target(node, "belief-sediment.json", "confidence", _by_index("beliefs", i, "pattern", plan["fp"]),
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
        if t.expect is not None and cur != t.expect:
            out["why"] = "changed since the plan (%s is %r, the plan saw %r)" % (t.field, cur, t.expect)
            return None
        new = t.new_value(cur)
        if new is None or new == cur:
            out["why"] = "nothing to change (%s is %r)" % (t.field, cur)
            return None
        # stamped with the run's own time, so the daily limit counts the day the run belongs to (a test that runs
        # "the next night" on a later wall-clock day used to find the first night's rows dated today)
        out["row"] = dict(meta, rev=rev, at=meta.get("at") or _now(), node=t.node, store=t.store, field=t.field, was=cur, now=new,
                          superseded=copy.deepcopy(rec))
        if dry:
            return None
        # the log row first, still under the store's lock: a crash after it leaves a row whose change never landed
        # (revert then says "changed since"), never a change no row can find (review 7)
        _append(os.path.join(mem, LOG_NAME), out["row"])
        rec[t.field] = new
        rec["belief_revision"] = {"rev": rev, "field": t.field, "was": cur, "at": out["row"]["at"]}
        return data

    out["in_force"] = set(in_force(mem))
    store_guard.locked_update(path, mutate, default={}, reader="belief_revision_live")
    if "row" not in out:
        return None, out.get("why")
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
    pushed = bool(row and row.get("pushed"))       # kept for her but not pushed: told again on a later day
    for f in new:
        f["told"] = pushed
        f["told_at"] = _now() if pushed else ""
    return row


# -- one run ---------------------------------------------------------------------------------------------------------
def run(mem=None, dry=False, checks=CHECKS, transport=None, send=None, at=None):
    mem = mem or MEMORY
    if mode() != "live" and not dry:
        return {"ran": False, "reason": "BELIEF_REVISION is not live"}
    import belief_revision_sources as S
    import belief_revision_answer as A
    at = at or _now()
    # the run's own time sets the records' ages (their prior drift), so a run - and a test - means the same thing
    # whatever day it is executed on
    try:
        now = datetime.fromisoformat(at.replace("Z", "+00:00"))
        now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        now = None
    g, stats = S.build(mem, now=now)
    answerer = A.Answerer(A.StoreRecords(mem, g), transport=transport)
    p = BR.localize(g, answerer, budget=checks, at=at)
    old_wants = _wants(g, p)
    use_exact, trial = solver_trial(mem, at, dry=dry)
    if use_exact:
        try:
            import belief_revision_verify as V
            sp, status = V.choose(g, p)
        except Exception as e:                       # the solver failing never costs the night its old repair
            sp, status = None, "error:" + type(e).__name__
        trial["status"] = status
        if sp is None:
            trial.update(chooser="old", fell_back="no proved minimum (%s); the old chooser is used" % status)
        else:
            p = sp
    held = set(p.get("held") or [])
    # what each revision means for his stores: a step through the belief it produced; strongest action per record
    wants = _wants(g, p)
    if trial["state"] != "off":
        trial.update(_compare(wants, old_wants), energy=p.get("energy"), energy_old=p.get("energy_old"))

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
    plan_rows, applied, deferred = [], [], []
    stopped = False
    # the whole apply phase holds the revision log's lock: two runs at once cannot both spend the day's limit, and
    # the switch is read again here, so turning it off while the checks were being asked takes effect (review 6)
    with store_guard.transaction(os.path.join(mem, LOG_NAME)):
        if not dry and mode() != "live":
            stopped, wants = True, {}
        room = max(0, max_per_day() - applied_today(mem, at[:10]))
        rows = _read_jsonl(os.path.join(mem, LOG_NAME))
        revised_nodes = {r["node"] for r in rows if r.get("node")}   # in force, or reverted (her no stands, review 5)
        for node, w in sorted(wants.items(), key=lambda kv: (-(kv[1]["blame"] or 0), kv[0])):
            gn = g.nodes.get(node) or {}
            if gn.get("kind") == "gloria":
                # her words are never revised, whichever chooser named them: flagged for her (a second guard
                # behind the solver's own bound and target()'s record rules)
                _flag(flags, node, "gloria", "the evidence goes against her word; never revised", w["blame"], at)
                flagged["gloria"] += 1
                continue
            t, why = target(node, w["action"], w["factor"], mem,
                            plan=dict(gn.get("meta") or {}, **({"confidence": gn["confidence"]}
                                                              if gn.get("confidence") is not None else {})))
            if t is None:
                k = "self_model" if node.startswith(SELF_MODEL_PREFIXES) else "record"
                _flag(flags, node, k, why, w["blame"], at)
                flagged[k] += 1
                continue
            if node in revised_nodes:
                continue                                         # revised once already (or reverted): never again
            if not dry and len(applied) >= room:
                deferred.append(node)
                continue
            meta = {"at": at, "action": w["action"], "blame": w["blame"], "why": w["why"], "mode": "dry-run" if dry else "live",
                    "chooser": p.get("chooser", "old"), "old_would": (old_wants.get(node) or {}).get("action"),
                    "answers": [{"node": a["node"], "answer": a["answer"], "by": (a.get("provenance") or {}).get("by")}
                                for a in p.get("answers") or []][:24]}
            row, why = apply(t, mem, meta, dry=dry)
            if row:
                (plan_rows if dry else applied).append({k: row[k] for k in ("rev", "node", "store", "field", "was", "now")})
    if stopped:
        return {"ran": False, "reason": "BELIEF_REVISION was turned off during the run; nothing applied"}
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
    if trial["state"] != "off":
        summary["solver_trial"] = trial
    if not dry:
        _append(os.path.join(mem, RUNS_NAME), {k: (v if k not in ("applied",) else [
            {kk: x[kk] for kk in ("rev", "node", "store", "field")} for x in v]) for k, v in summary.items()})
    return summary


def _wants(g, p):
    """What a plan means for his stores: a step through the belief it produced; the strongest action per record."""
    wants = {}

    def want(node, action, factor, blame, why):
        cur = wants.get(node)
        rank = {"withdraw": 2, "retract": 2, "lower": 1}
        if cur is None or rank[action] > rank[cur["action"]] or (rank[action] == rank[cur["action"]]
                                                                 and factor < cur["factor"]):
            wants[node] = {"action": action, "factor": factor, "blame": blame, "why": why}

    for r in p["revisions"]:
        if r["action"] not in ("retract", "lower") or r["kind"] == "gloria":
            continue
        base = r["node"][5:] if r["node"].startswith("rule:") else r["node"]
        want(base, r["action"], round(1.0 - r["blame"], 4), r["blame"], "blamed for %s" % ", ".join(r["conflicts"][:3]))
    for d in p["rederive"]:
        f = (d["standing_after"] / d["standing_before"]) if d["standing_before"] else 0.0
        want(d["node"], d["action"], round(min(1.0, f), 4), None, "rests on a revised source")
    return wants


def _compare(chosen, old):
    """The chosen plan beside the old chooser's, as counts and ids (an id that is not id-shaped is hashed)."""
    a = {BR._safe(n): w["action"] for n, w in chosen.items()}
    b = {BR._safe(n): w["action"] for n, w in old.items()}
    return {"chosen": dict(sorted(a.items())), "old_would": dict(sorted(b.items())),
            "same": sum(1 for n in a if n in b), "same_action": sum(1 for n in a if b.get(n) == a[n]),
            "only_chosen": len(set(a) - set(b)), "only_old": len(set(b) - set(a))}


def trial_state(mem):
    t = store_guard.load_json(os.path.join(mem, TRIAL_NAME), {}) or {}
    return dict(t, switch=_setting("BELIEF_REVISION_SOLVER") or "(unset)",
                until=_setting("BELIEF_REVISION_SOLVER_UNTIL") or None)


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
    for name in ("list", "flags", "trial"):
        s = sub.add_parser(name)
        s.add_argument("--memory", default=None)
    v = sub.add_parser("revert")
    v.add_argument("revs", nargs="*")
    v.add_argument("--all", action="store_true")
    v.add_argument("--solver", action="store_true", help="every revision in force that the exact solver chose")
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
    elif a.cmd == "trial":
        out = trial_state(mem)
    else:
        if not a.all and not a.revs and not a.solver:
            ap.error("revert: name REV ids, or --all, or --solver")
        if a.all:
            revs = None
        elif a.solver:
            revs = {r for r, x in in_force(mem).items() if x.get("chooser") == "exact"} | set(a.revs)
        else:
            revs = set(a.revs)
        out = revert(mem, revs, force=a.force) if revs is None or revs else []
    print(json.dumps(out, indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
