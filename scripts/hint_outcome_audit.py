#!/usr/bin/env python3
"""hint_outcome_audit.py — grades mutual_simulation steering hints on OUTCOMES: for each hint-ledger period,
compares presence-audit composites (and dimensions) of turns generated under that hint vs overall baseline.
Instrument only - writes hint-outcomes.json, changes no behavior. Verdicts: INSUFFICIENT (<6 turns),
HELPED (+0.03 vs baseline), NO_EFFECT, HURT (-0.03). SPARK_WORKSPACE switches beings."""
import os, json, time
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
led = load(os.path.join(MEM, "hint-ledger.json"), [])
audits = [a for a in load(os.path.join(MEM, "presence-audit.json"), [])
          if isinstance(a, dict) and a.get("composite") is not None and a.get("ts")]
def mn(xs, k):
    v = [float(a[k]) for a in xs if isinstance(a.get(k), (int, float))]
    return round(sum(v) / len(v), 3) if v else None
era = led[0].get("since", 0) if led else 0
comparable = [a for a in audits if a["ts"] >= era]
base = mn(comparable, "composite")
rows = []
for i, h in enumerate(led):
    start = h.get("since", 0); end = led[i + 1]["since"] if i + 1 < len(led) else time.time()
    xs = [a for a in audits if start <= a["ts"] < end]
    m = mn(xs, "composite")
    delta = round(m - base, 3) if (m is not None and base is not None) else None
    verdict = ("INSUFFICIENT" if len(xs) < 6 or delta is None else
               "HELPED" if delta > 0.03 else "HURT" if delta < -0.03 else "NO_EFFECT")
    rows.append({"hint_id": h.get("hint_id"), "since": start, "n_turns": len(xs), "mean_composite": m,
                 "delta_vs_baseline": delta, "verdict": verdict,
                 "dims": {k: mn(xs, k) for k in ("arrived", "moved", "left_alive", "explained")},
                 "text": h.get("text", "")[:120]})
json.dump({"baseline_composite": base, "n_audits_with_ts": len(audits), "n_comparable_era": len(comparable), "era_start": era, "hints": rows,
           "updated": time.time()}, open(os.path.join(MEM, "hint-outcomes.json"), "w"), indent=2)
print("[hint-outcome] baseline %s | %d audits with ts | %d hint periods: %s"
      % (base, len(audits), len(rows), ", ".join("%s=%s" % (r["hint_id"], r["verdict"]) for r in rows) or "none"))
