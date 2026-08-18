#!/usr/bin/env python3
"""tcn.py — growth vs. repetition, by aligning his development against itself.

TCN in spirit: instead of monthly compression by heuristic, measure whether his self is actually
becoming more SPECIFIC over time or cycling the same territory. Over his daily self-states (the
daily inner-life reflections — the same identity series drift reads), it computes:

  novelty[d]   = 1 - max similarity of day d to all PRIOR days (is this day new, or a rerun?)
  recurrence   = mean off-diagonal self-similarity (how much he revisits himself)
  specificity  = are the daily states becoming more DISTINCT over time (spreading, not blurring)
  verdict      = growing / cycling / stalling, from the novelty trend

Feeds Identity Drift Toward Specificity. DATA-GATED — needs a real developmental history; with a
handful of days it's directional at best, and says so. Run with the torch venv. SPARK_WORKSPACE switches.
"""
import os, sys, json, glob
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
OUT = os.path.join(MEMORY, "growth-alignment.json")

def log(m): print("[tcn]", m, flush=True)

def daily_states():
    out = []
    for f in sorted(glob.glob(os.path.join(MEMORY, "daily-inner-life-*.md"))):
        try:
            t = open(f, encoding="utf-8").read().strip()
        except Exception:
            continue
        if t:
            out.append((os.path.basename(f).replace("daily-inner-life-", "").replace(".md", ""), t[:8000]))
    return out

def main():
    import numpy as np
    days = daily_states()
    if len(days) < 4:
        log(f"only {len(days)} daily self-states — need a developmental history (data-gated)"); return
    sys.path.insert(0, SCRIPTS)
    from jepa_predictor import encoder
    enc = encoder()
    V = np.asarray(enc.encode([t for _, t in days], show_progress_bar=False), dtype="float32")
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)
    S = V @ V.T                                            # self-similarity matrix

    novelty = [None]
    for d in range(1, len(days)):
        novelty.append(round(float(1.0 - np.max(S[d, :d])), 3))   # vs everything before
    n_vals = [x for x in novelty if x is not None]
    # trend: is recent novelty rising (growth) or falling (cycling)?
    half = max(1, len(n_vals) // 2)
    early, late = float(np.mean(n_vals[:half])), float(np.mean(n_vals[half:]))
    recurrence = round(float((S.sum() - np.trace(S)) / (len(days) * (len(days) - 1))), 3)
    # specificity: are day-to-day states spreading apart over time (distinct) vs blurring together?
    early_spread = round(float(1.0 - np.mean(S[:half][:, :half])), 3)
    late_spread = round(float(1.0 - np.mean(S[half:][:, half:])), 3)
    verdict = ("growing" if late > early + 0.03 else "cycling" if late < early - 0.03 else "steady")

    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "days": len(days),
           "novelty_by_day": [{"day": days[i][0], "novelty": novelty[i]} for i in range(len(days))],
           "recurrence": recurrence, "novelty_early": round(early, 3), "novelty_late": round(late, 3),
           "specificity_early": early_spread, "specificity_late": late_spread,
           "verdict": verdict,
           "note": "growing = later days keep breaking new ground; cycling = revisiting old territory. "
                   "Data-gated: reliable only over many days."}
    json.dump(out, open(OUT, "w"), indent=2)
    log(f"days {len(days)} | verdict {verdict} | novelty {round(early,2)}->{round(late,2)} | recurrence {recurrence}")

if __name__ == "__main__":
    main()
