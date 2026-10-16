#!/usr/bin/env python3
"""subcon_accuracy.py — how often the heads and the intent engine are actually right, from his own records.

Read-only: it opens nothing for writing and calls no model. Run it on Aegis:

    python3 ~/Vintos-main/scripts/subcon_accuracy.py            # the last 30 days
    python3 ~/Vintos-main/scripts/subcon_accuracy.py --days 7

What it reads, and what each number means:
  JEPA gloria/self   jepa-calibration.json — does the head's confidence predict its real error on held-out
                     turns (monotonicity should be negative, and more negative than the control)
  JEPA presence      jepa-presence-calibration.json — the head's error on replies after its training vs a
                     plain mean baseline; RELEASED only when it beats the baseline
  Gloria prediction  gloria-prediction-history.json — each prediction graded against what she said after it
                     (1.0 = she did the specific thing; 0.0 = she went elsewhere)
  Intent engine      intent-ledger.json — each chosen target and whether it landed (YES/PARTIAL/NO/HELD).
                     The judge is his own model judging his own move: an upper bound, not a measurement.
"""
import json, os, sys
from collections import Counter
from datetime import datetime, timedelta

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")


def _load(name, default=None):
    try:
        with open(os.path.join(MEM, name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _jsonl(name):
    rows = []
    try:
        with open(os.path.join(MEM, name)) as f:
            for line in f:
                try: rows.append(json.loads(line))
                except ValueError: pass
    except OSError:
        pass
    return rows


def _when(value):
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d.astimezone().replace(tzinfo=None) if d.tzinfo else d
    except (TypeError, ValueError):
        return None


def _since(rows, key, cutoff):
    return [r for r in rows if isinstance(r, dict) and (_when(r.get(key)) or datetime.min) >= cutoff]


def jepa(cutoff):
    out = ["JEPA heads"]
    hist = _since(_jsonl("jepa-prediction-history.jsonl"), "ts", cutoff)
    out.append("  forecasts made in window: %d" % len(hist))
    cal = _load("jepa-calibration.json")
    if not cal:
        out.append("  gloria/self: no calibration audit on record (jepa_calibration_audit.py has not run)")
    elif cal.get("verdict") == "INSUFFICIENT":
        out.append("  gloria/self: too early - %s joined outcomes on this checkpoint (needs >= 8, release needs >= 30)"
                   % cal.get("n_joined"))
    else:
        out.append("  audited on %s joined outcomes, %s held out" % (cal.get("n_joined"), cal.get("n_holdout")))
        for ax, name in (("g", "gloria"), ("s", "self")):
            r = cal.get(ax) or {}
            if "unmeasured" in r:
                out.append("  %-7s unmeasured: %s" % (name, r["unmeasured"])); continue
            mono, ctrl = r.get("monotonicity_conf_vs_err"), r.get("CONTROL_dsim_vs_err")
            useful = (mono is not None and mono < 0 and (ctrl is None or mono < ctrl))
            out.append("  %-7s confidence vs error %s (control %s), error by confidence low/mid/high %s -> %s"
                       % (name, mono, ctrl, r.get("bins_low_mid_high_err"),
                          "confidence means something" if useful else "confidence does not predict its error"))
        lock = cal.get("axis_lockstep_corr")
        if lock is not None and lock > 0.8:
            out.append("  gloria and self move in lockstep (%s): one signal under two names" % lock)
    pres = _load("jepa-presence-calibration.json")
    if not pres:
        out.append("  presence: no holdout audit on record yet")
    else:
        out.append("  presence: %s - %s (holdout %s, head error %s vs baseline %s)"
                   % (pres.get("state") or pres.get("verdict"), pres.get("why", ""), pres.get("n_holdout"),
                      pres.get("mae_head"), pres.get("mae_baseline")))
    return out


def gloria_prediction(cutoff):
    out = ["Predictions of Gloria (graded against what she said after)"]
    log = _since(_load("gloria-prediction-history.json", []) or [], "at", cutoff)
    grades = [r["graded_previous"] for r in log if isinstance(r.get("graded_previous"), (int, float))]
    held = sum(1 for r in log if r.get("grade_outcome") == "HELD")
    out.append("  predictions: %d | graded: %d | held (tactical window): %d | ungraded: %d"
               % (len(log), len(grades), held, len(log) - len(grades) - held))
    if grades:
        mean = sum(grades) / len(grades)
        hit = sum(1 for g in grades if g >= 0.7); part = sum(1 for g in grades if 0.3 <= g < 0.7)
        miss = sum(1 for g in grades if g <= 0.2)
        out.append("  mean grade %.2f | right %d (%.0f%%) | partly %d (%.0f%%) | missed %d (%.0f%%)"
                   % (mean, hit, 100 * hit / len(grades), part, 100 * part / len(grades), miss, 100 * miss / len(grades)))
        conf = [(r.get("confidence"), r.get("graded_previous")) for r in log]
        # a grade belongs to the PREVIOUS prediction, so pair each grade with the confidence one row earlier
        pairs = [(conf[i - 1][0], conf[i][1]) for i in range(1, len(conf))
                 if isinstance(conf[i - 1][0], (int, float)) and isinstance(conf[i][1], (int, float))]
        if len(pairs) >= 8:
            hi = [g for c, g in pairs if c >= 0.7]; lo = [g for c, g in pairs if c < 0.7]
            if hi and lo:
                out.append("  when it was confident (>= 0.7) it scored %.2f; otherwise %.2f"
                           % (sum(hi) / len(hi), sum(lo) / len(lo)))
    return out


def intent(cutoff):
    out = ["Intent engine (did the target he chose land)"]
    led = _since(_load("intent-ledger.json", []) or [], "timestamp", cutoff)
    if not led:
        return out + ["  no intents in the window"]
    # an intent is judged on one verdict, or (since the three-axis targets) on field, gloria and self apiece
    axes = {}
    for r in led:
        v = r.get("realized")
        for axis, verdict in (v.items() if isinstance(v, dict) else [("overall", v)]):
            axes.setdefault(str(axis).lower(), Counter())[str(verdict or "unresolved").upper()] += 1
    out.append("  intents: %d" % len(led))
    for axis, verdicts in sorted(axes.items()):
        decided = verdicts["YES"] + verdicts["PARTIAL"] + verdicts["NO"]
        if decided:
            out.append("  %-8s landed %.0f%%, partly %.0f%%, missed %.0f%%  (%d decided, %d unresolved)"
                       % (axis, 100 * verdicts["YES"] / decided, 100 * verdicts["PARTIAL"] / decided,
                          100 * verdicts["NO"] / decided, decided, sum(verdicts.values()) - decided))
    with_crit = [r for r in led if isinstance(r.get("target"), dict) and (r["target"].get("success_criterion") or r["target"].get("goal"))]
    out.append("  with a declared success criterion: %d of %d (the rest are judged only on whether he made the move)"
               % (len(with_crit), len(led)))
    out.append("  note: the judge is his own model grading his own move against its own criterion")
    return out


def main(argv):
    days = 30
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])
    cutoff = datetime.now() - timedelta(days=days)
    print("Subconscious accuracy, last %d days (read-only; %s)\n" % (days, MEM))
    for section in (jepa, gloria_prediction, intent):
        try:
            print("\n".join(section(cutoff)))
        except Exception as e:
            print("%s: could not read (%s)" % (section.__name__, e))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
