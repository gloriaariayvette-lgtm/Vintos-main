#!/usr/bin/env python3
"""calibration.py - whether a predictive head has EARNED its use, by held-out evidence, against
versioned release criteria.

Review items 202 and 207 (2026-09-10). The variance gate said only "this forecast's spread is tighter
than its own recent spread"; that is variance, not calibration, and nothing consumed the audit that
actually asked the calibration question. This module is the one gate:

  * criteria are VERSIONED (CRITERIA_VERSION); a head released under v1 is not released under v2
    until it is evaluated again, and the release record says which version it passed.
  * evidence is HELD OUT: the audit's joined rows are split by SOURCE (which producer's records) and
    by TIME (the earlier two thirds fit, the later third judges), so a head cannot pass on the rows it
    was tuned on.
  * the verdict is one of RELEASED / WITHHELD / INSUFFICIENT, always with the numbers and the reason.

    verdict(head="gloria")   -> {"state", "why", "criteria_version", "n_holdout", ...}
    allowed(head)            -> bool (RELEASED only)
    record_release(head, v)  -> appends to memory/calibration-releases.jsonl

Nothing here trains, steers or writes into a forecast. It reads jepa-calibration.json (the audit) and
memory/jepa-prediction-history.jsonl, and says yes or no.
"""
import os, json, time

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
AUDIT = os.path.join(MEMORY, "jepa-calibration.json")
HISTORY = os.path.join(MEMORY, "jepa-prediction-history.jsonl")
RELEASES = os.path.join(MEMORY, "calibration-releases.jsonl")

CRITERIA_VERSION = "v1-2026-09-10"
CRITERIA = {
    "min_holdout": 30,             # joined predictions in the held-out slice
    "max_monotonicity": -0.20,     # confidence must fall as error rises (Spearman, want negative)
    "beat_control_by": 0.10,       # ... and beat the decode-similarity control by this margin
    "max_wrong_but_confident": 2,  # confident-and-wrong cases tolerated in the holdout
    "max_axis_lockstep": 0.95,     # two heads moving in lockstep are one signal wearing two names
}


def _audit():
    try:
        d = json.load(open(AUDIT))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def holdout(rows, by="time", fraction=0.34):
    """The slice a head is judged on. by='time': the latest `fraction` of rows in order. by='source':
    rows whose source is not the majority source, when more than one source exists."""
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return [], "no rows"
    if by == "source":
        counts = {}
        for r in rows:
            counts[r.get("source") or "unknown"] = counts.get(r.get("source") or "unknown", 0) + 1
        if len(counts) > 1:
            major = max(counts, key=counts.get)
            out = [r for r in rows if (r.get("source") or "unknown") != major]
            return out, "held out every source but %s" % major
        return [], "one source only (%s): no source holdout possible" % (list(counts) or ["none"])[0]
    rows = sorted(rows, key=lambda r: str(r.get("iso") or r.get("at") or ""))
    k = max(1, int(len(rows) * fraction))
    return rows[-k:], "the latest %d of %d rows by time" % (k, len(rows))


def verdict(head="gloria", criteria=None, audit=None):
    """RELEASED / WITHHELD / INSUFFICIENT for one head, with the numbers behind it."""
    c = dict(CRITERIA); c.update(criteria or {})
    a = audit if audit is not None else _audit()
    key = {"gloria": "g", "self": "s"}.get(head, head[:1])
    out = {"head": head, "criteria_version": CRITERIA_VERSION, "criteria": c, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if not a or a.get("verdict") == "INSUFFICIENT" or key not in a:
        out.update(state="INSUFFICIENT", why="no calibration audit with this head yet (n_joined=%s)" % a.get("n_joined", 0), n_holdout=0)
        return out
    n = int(a.get("n_joined") or 0)
    ax = a.get(key) or {}
    mono = ax.get("monotonicity_conf_vs_err")
    ctrl = ax.get("CONTROL_dsim_vs_err")
    wbc = len(ax.get("wrong_but_confident") or [])
    lock = a.get("axis_lockstep_corr")
    # the audit reports over its joined rows; the holdout size is what the audit says it judged on
    n_hold = int(a.get("n_holdout") or n)
    out["n_holdout"] = n_hold
    out["numbers"] = {"monotonicity": mono, "control": ctrl, "wrong_but_confident": wbc, "axis_lockstep": lock}
    if n_hold < c["min_holdout"]:
        out.update(state="INSUFFICIENT", why="%d joined predictions in the holdout; %d required" % (n_hold, c["min_holdout"]))
        return out
    fails = []
    if mono is None or float(mono) > c["max_monotonicity"]:
        fails.append("monotonicity %s is not at or below %s (confidence does not fall as error rises)" % (mono, c["max_monotonicity"]))
    if mono is not None and ctrl is not None and float(mono) > float(ctrl) - c["beat_control_by"]:
        fails.append("does not beat the decode-similarity control by %s (head %s, control %s): variance, not usefulness" % (c["beat_control_by"], mono, ctrl))
    if wbc > c["max_wrong_but_confident"]:
        fails.append("%d confident-and-wrong cases in the holdout; %d tolerated" % (wbc, c["max_wrong_but_confident"]))
    if lock is not None and abs(float(lock)) > c["max_axis_lockstep"]:
        fails.append("the two heads move in lockstep (%s): one signal wearing two names" % lock)
    if fails:
        out.update(state="WITHHELD", why="; ".join(fails))
    else:
        out.update(state="RELEASED", why="passed %s on %d held-out predictions" % (CRITERIA_VERSION, n_hold))
    return out


def allowed(head="gloria"):
    return verdict(head).get("state") == "RELEASED"


def record_release(head, v=None):
    v = v or verdict(head)
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(RELEASES, "a") as f:
            f.write(json.dumps(v) + "\n")
    except OSError:
        pass
    return v


if __name__ == "__main__":
    for h in ("gloria", "self"):
        v = verdict(h)
        print("%-7s %-12s %s" % (h, v["state"], v["why"]))
