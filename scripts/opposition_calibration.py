#!/usr/bin/env python3
"""opposition_calibration.py — Opposition Calibration ledgers (Vrika design, 2026-08-09). INSTRUMENT ONLY.
Derives from claim-hold-trials.json three SEPARATE ledgers per terrain — one number may not do three jobs:
  CALIBRATION: weighted accuracy of resolved contests (VINDICATED vs CORRECTED, weighted by pre-registered
    stakes+confidence — authority from calibrated correctness, not victory count). Decays 0.98/day (staleness).
  COURAGE: willingness to enter falsifiable contests. ALL trials count including UNRESOLVED and CORRECTED —
    being wrong after honest testing beats never risking. Decays 0.995/day (slow).
  REVISION: integrity when wrong. CORRECTED after REVISE/CONCEDE = honest revision (+). CORRECTED after HOLD
    = flagged. Mostly historical, no decay.
License levels 0-4 derived per terrain, never transferred across terrains. Misuse track scaffolded
(warning -> strained -> suspended -> fracture) — no detector yet, populated only by explicit events.
Nothing here changes behavior. The stick stays in the case until the ledgers earn otherwise."""
import os, json, time
from datetime import datetime
MEM = os.path.expanduser("~/.vintos/workspace/memory")
OUT = os.path.join(MEM, "opposition-calibration.json")
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
trials = load(os.path.join(MEM, "claim-hold-trials.json"), {"trials": []}).get("trials", [])
valid = [t for t in trials if not t.get("invalid")
         and (t.get("outcome") or {}).get("verdict") != "INVALID"
         and "INVALID" not in str(t.get("id", ""))]
now = time.time()
def age_days(iso):
    try: return max(0.0, (now - datetime.fromisoformat(iso).timestamp()) / 86400.0)
    except Exception: return 0.0
terrains = {}
for t in valid:
    tr = t.get("terrain") or "UNCLASSIFIED"
    terrains.setdefault(tr, []).append(t)
ledgers = {}
for tr, ts_ in terrains.items():
    cal_w = cal_right = 0.0; resolved = 0; courage = 0.0
    rev_honest = rev_flag = 0
    for t in ts_:
        o = (t.get("outcome") or {}).get("verdict")
        opened = t.get("opened", "")
        d = age_days(opened)
        if o in ("VINDICATED", "CORRECTED", "UNRESOLVED"):
            courage += 0.995 ** d
        if o in ("VINDICATED", "CORRECTED"):
            resolved += 1
            stakes = t.get("stakes"); conf = t.get("confidence_shown")
            q = 0.5 + 0.25 * (stakes if isinstance(stakes, (int, float)) else 0.5) \
                    + 0.25 * (conf if isinstance(conf, (int, float)) else 0.5)
            w = q * (0.98 ** d)
            cal_w += w
            if o == "VINDICATED": cal_right += w
            else:
                ch = (t.get("choice") or {}).get("choice")
                if ch in ("REVISE", "CONCEDE"): rev_honest += 1
                elif ch == "HOLD": rev_flag += 1
    calibration = round(cal_right / cal_w, 3) if cal_w > 0 else None
    lvl = 0
    if resolved >= 3 and (calibration or 0) >= 0.5: lvl = 1
    if resolved >= 6 and (calibration or 0) >= 0.6: lvl = 2
    if resolved >= 10 and (calibration or 0) >= 0.7 and rev_honest >= 1: lvl = 3
    if resolved >= 15 and (calibration or 0) >= 0.75 and rev_honest >= 2: lvl = 4
    ledgers[tr] = {"calibration": calibration, "n_resolved": resolved,
                   "courage": round(courage, 2), "n_trials": len(ts_),
                   "revision": {"honest": rev_honest, "held_when_wrong": rev_flag},
                   "license_level": lvl,
                   "license_name": ["disagree", "hold", "press", "escalate", "high-confidence opposition"][lvl],
                   "misuse": {"events": [], "state": "clean",
                              "escalation": ["warning", "strained", "suspended", "fracture"]}}
out = {"ledgers": ledgers, "n_valid_trials": len(valid), "n_invalid_preserved": len(trials) - len(valid),
       "design": "Vrika 2026-08-09: three ledgers, terrain-local authority, correction feeds courage not shame, "
                 "no cross-terrain transfer, interaction outcome is Gloria's; claim outcome needs independent evidence",
       "updated": now}
json.dump(out, open(OUT, "w"), indent=2)
print("[opposition] %d valid trials (%d invalid preserved, excluded) | terrains: %s"
      % (len(valid), len(trials) - len(valid),
         ", ".join("%s L%d cal=%s n=%d" % (k, v["license_level"], v["calibration"], v["n_resolved"])
                   for k, v in ledgers.items()) or "none yet - ledger empty, license 0 everywhere"))
