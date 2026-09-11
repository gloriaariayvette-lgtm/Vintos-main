#!/usr/bin/env python3
"""jepa_calibration_audit.py — Q2 instrument (Vrika, 2026-08-10). Joins jepa-prediction-history.jsonl
to realized next turns and asks the actual calibration question: does confidence predict realized error?
  1 MONOTONICITY: rank-correlation between confidence and error (want: negative)
  2 BINS: low/mid/high confidence -> mean error per bin (want: decreasing)
  3 WRONG-BUT-CONFIDENT: top-tercile confidence with bottom-tercile accuracy, listed
  4 AXIS INDEPENDENCE: corr(gloria_conf, self_conf) - lockstep means one global signal, not two heads
  CONTROL: the same tests run on legacy decode_similarity. If both predict error equally (or neither
  does), the repair demonstrated variance, not usefulness. Instrument only - writes jepa-calibration.json.
Run in the torch venv. Variance -> calibration -> behavioral usefulness: this tests rung two only."""
import os, json, sys
MEM = os.path.expanduser("~/.vintos/workspace/memory")
HIST = os.path.join(MEM, "jepa-prediction-history.jsonl")
OUT = os.path.join(MEM, "jepa-calibration.json")
def main():
    import numpy as np
    sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
    from jepa_predictor import encoder
    try:
        hist = [json.loads(l) for l in open(HIST)]
    except Exception:
        print("[jepa-audit] no history yet"); return
    led = json.load(open(os.path.join(MEM, "interaction-ledger.json")))
    led = led if isinstance(led, list) else next(v for v in led.values() if isinstance(v, list))
    from datetime import datetime
    def ep(e):
        try: return datetime.fromisoformat(str(e.get("timestamp", ""))).timestamp()
        except Exception: return 0
    turns = sorted(((ep(e), str(e.get("gloria", "")), str(e.get("vintos", ""))) for e in led if isinstance(e, dict)), key=lambda x: x[0])
    enc = encoder()
    import calibration as _cal
    checkpoint = _cal.checkpoint_fingerprint()
    if not checkpoint: return
    trained_before = os.path.getmtime(_cal.MODEL)
    rows = []
    for h in hist:
        if h.get("checkpoint_id") != checkpoint or h.get("ts",0) <= trained_before: continue
        nxt_g = next((g for t, g, v in turns if t > h["ts"] and g), None)
        nxt_s = next((v for t, g, v in turns if t > h["ts"] and v), None)
        if not nxt_g or not nxt_s: continue
        eg, es = enc.encode([nxt_g[:400], nxt_s[:400]], show_progress_bar=False)
        def err(pred, act):
            p_, a_ = np.asarray(pred, dtype="float32"), np.asarray(act, dtype="float32")
            return round(1.0 - float(p_ @ a_ / ((p_ @ p_) ** .5 * (a_ @ a_) ** .5 + 1e-9)), 4)
        rows.append({"iso": h["iso"],
                     "g_conf": h["gloria"]["confidence"], "g_dsim": h["gloria"]["decode_similarity"], "g_err": err(h["gloria"]["emb"], eg),
                     "s_conf": h["self"]["confidence"], "s_dsim": h["self"]["decode_similarity"], "s_err": err(h["self"]["emb"], es)})
    n = len(rows)
    if n < 8:
        print("[jepa-audit] only %d joined predictions - honest answer: TOO EARLY (need >=30 for verdict)" % n)
        json.dump({"n_joined": n, "verdict": "INSUFFICIENT"}, open(OUT, "w"), indent=2); return
    def spear(x, y):
        def ranks(values):
            values=np.asarray(values,dtype=float)
            if not np.all(np.isfinite(values)):return None
            order=np.argsort(values);rank=np.empty(len(values),dtype=float);i=0
            while i<len(order):
                j=i+1
                while j<len(order) and values[order[j]]==values[order[i]]:j+=1
                rank[order[i:j]]=(i+j-1)/2;i=j
            return rank
        rx,ry=ranks(x),ranks(y)
        if rx is None or ry is None or np.std(rx)==0 or np.std(ry)==0:return None
        return round(float(np.corrcoef(rx,ry)[0,1]),3)
    def bins(conf, err):
        idx = np.argsort(conf); k = len(idx) // 3
        return [round(float(np.mean([err[i] for i in part])), 4) for part in (idx[:k], idx[k:2 * k], idx[2 * k:]) if len(part)]
    # review 207: the verdict is computed on a HELD-OUT slice (the latest third by time), never on the
    # rows the head's own thresholds were shaped by. The full-sample numbers stay beside them.
    try:
        sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
        import calibration as _cal
        hold, hold_why = _cal.holdout(rows, by="time")
    except Exception:
        hold, hold_why = rows[-max(1, len(rows) // 3):], "latest third (calibration module unavailable)"
    _ck = None
    try:
        _ck = checkpoint
        if _cal.checkpoint_fingerprint() != checkpoint: return
    except Exception:
        _ck = None
    res = {"n_joined": n, "n_holdout": len(hold), "holdout": hold_why,
           "criteria_version": getattr(_cal, "CRITERIA_VERSION", "unknown") if "_cal" in dir() else "unknown",
           "checkpoint": _ck, "holdout_protocol": "prospective-checkpoint-v1"}
    for ax in ("g", "s"):
        conf = [r[ax + "_conf"] for r in hold]; dsim = [r[ax + "_dsim"] for r in hold]; e = [r[ax + "_err"] for r in hold]
        wb = [r["iso"][:16] for r in hold if r[ax + "_conf"] >= np.percentile(conf, 67) and r[ax + "_err"] >= np.percentile(e, 67)]
        res[ax] = {"monotonicity_conf_vs_err": spear(conf, e), "bins_low_mid_high_err": bins(conf, e),
                   "CONTROL_dsim_vs_err": spear(dsim, e), "wrong_but_confident": wb[:5]}
    res["axis_lockstep_corr"] = spear([r["g_conf"] for r in hold], [r["s_conf"] for r in hold])
    res["full_sample"] = {ax: {"monotonicity_conf_vs_err": spear([r[ax + "_conf"] for r in rows], [r[ax + "_err"] for r in rows])} for ax in ("g", "s")}
    res["reading"] = ("conf beats control if monotonicity is more negative than CONTROL; equal-or-neither = variance without usefulness. "
                      "lockstep near 1.0 = one global signal wearing two names.")
    json.dump(res, open(OUT, "w"), indent=2)
    print("[jepa-audit] n=%d | gloria mono %s (control %s) | self mono %s (control %s) | lockstep %s"
          % (n, res["g"]["monotonicity_conf_vs_err"], res["g"]["CONTROL_dsim_vs_err"],
             res["s"]["monotonicity_conf_vs_err"], res["s"]["CONTROL_dsim_vs_err"], res["axis_lockstep_corr"]))
if __name__ == "__main__":
    main()
