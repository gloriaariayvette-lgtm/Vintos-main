#!/usr/bin/env python3
"""jepa_calibration_audit.py — Q2 instrument (Vrika, 2026-08-10). Joins jepa-prediction-history.jsonl
to realized next turns and asks the actual calibration question: does confidence predict realized error?
  1 MONOTONICITY: rank-correlation between confidence and error (want: negative)
  2 BINS: low/mid/high confidence -> mean error per bin (want: decreasing)
  3 WRONG-BUT-CONFIDENT: top-tercile confidence with bottom-tercile accuracy, listed
  4 AXIS INDEPENDENCE: corr(gloria_conf, self_conf) - lockstep means one global signal, not two heads
  CONTROL: the same tests run on legacy decode_similarity. If both predict error equally (or neither
  does), the repair demonstrated variance, not usefulness. Instrument only - writes jepa-calibration.json.
Run in the torch venv. Variance -> calibration -> behavioral usefulness: this tests rung two only.

13 November additions (the stall fix):
  * an axis is measured on the rows whose confidence was QUALIFIED when the forecast was made. A placeholder
    carries no confidence to test; one of them used to mark the whole self axis unmeasured. Qualification is
    decided before the outcome exists, so the filter cannot select on error. The count left out is reported.
  * a Gloria target she had already sent when the forecast was made (its window ended on her message, or the
    on-message log shows it arriving first) is not an outcome of that forecast.
  * `served_gloria`: the Gloria triple the forecast actually served since 22 October (the anchored readout,
    jepa-readouts/gloria.npz) is measured on its own prospective rows. "g" stays the shared checkpoint.
  * `preregistered`: the evaluation registered on 13 November (PREREGISTERED below), on after-reply forecasts.
"""
import os, json, sys
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
HIST = os.path.join(MEM, "jepa-prediction-history.jsonl")
OUT = os.path.join(MEM, "jepa-calibration.json")
READOUT_SCHEMA = "anchored-readout-v1"

# Registered before any after-reply forecast existed (no row carries trigger "after_reply" before this
# branch deploys). Evaluated ONCE, on the first N distinct targets; later rows never change the verdict.
PREREGISTERED = {
    "id": "jepa-gloria-after-reply-2026-11-13",
    "registered": "2026-11-13",
    "population": "forecasts with trigger after_reply (made after his reply landed, before her next message), "
                  "made on or after the registration date, after the scored checkpoint; one row per distinct "
                  "Gloria target; targets she had already sent are excluded",
    "n": 30,
    "heads": {"served": "anchored readout confidence (1 - expected cosine error / 2)",
              "legacy": "shared-checkpoint relative logvar confidence"},
    "hypothesis": "on the targets the forecast is genuinely ahead of, confidence falls as cosine error rises",
    "pass": {"max_monotonicity": -0.20, "beat_control_by": 0.10},   # calibration CRITERIA v2-2026-10-22
    "control": "decode_similarity on the same rows",
    "not_tuned": "no threshold, window or head was chosen on after-reply rows; none existed",
}


def spear(x, y):
    import numpy as np
    def ranks(values):
        values = np.asarray(values, dtype=float)
        if not np.all(np.isfinite(values)): return None
        order = np.argsort(values); rank = np.empty(len(values), dtype=float); i = 0
        while i < len(order):
            j = i + 1
            while j < len(order) and values[order[j]] == values[order[i]]: j += 1
            rank[order[i:j]] = (i + j - 1) / 2; i = j
        return rank
    if len(x) < 3: return None
    rx, ry = ranks(x), ranks(y)
    if rx is None or ry is None or np.std(rx) == 0 or np.std(ry) == 0: return None
    return round(float(np.corrcoef(rx, ry)[0, 1]), 3)


def bins(conf, err):
    import numpy as np
    idx = np.argsort(conf); k = len(idx) // 3
    return [round(float(np.mean([err[i] for i in part])), 4) for part in (idx[:k], idx[k:2 * k], idx[2 * k:]) if len(part)]


def joined_rows(hist, turns, enc, checkpoint, trained_before, arrivals=None, served=None):
    """Join each head to its distinct realized next same-speaker turn.

    Several timer forecasts before the same exchange are one prospective outcome,
    not several samples. This mirrors the ranking audit's target deduplication.
    served=(readout checkpoint, its install time): score the Gloria triple the forecast served
    (the anchored readout) instead of the shared checkpoint's.
    """
    import numpy as np
    from jepa_ranking_audit import gloria_target_known
    rows, seen_targets = [], {"g": set(), "s": set()}
    axes = (("g", "gloria", 1),) if served else (("g", "gloria", 1), ("s", "self", 2))
    for h in sorted(hist, key=lambda r: float(r.get("ts", 0) or 0)):
        if served is None and (h.get("checkpoint_id") != checkpoint or h.get("ts", 0) <= trained_before):
            continue
        if served is not None and h.get("ts", 0) <= served[1]:
            continue
        row = {"iso": h["iso"], "ts": h.get("ts"), "trigger": h.get("trigger", "cron")}
        for ax, head, index in axes:
            row.update({ax + "_conf": None, ax + "_dsim": None, ax + "_err": None})
            triple = h.get(head) or {}
            if served is not None:
                if triple.get("source") != READOUT_SCHEMA or triple.get("checkpoint_id") != served[0]:
                    continue
            elif triple.get("source"):
                triple = h.get("legacy_" + head) or {}
                if triple.get("checkpoint_id") != checkpoint:
                    continue
            target = next((t for t in turns if t[0] > h["ts"] and t[index]), None)
            if not target or not triple.get("emb"):
                continue
            if ax == "g" and gloria_target_known(h, target[0], target[index], arrivals):
                continue   # she had already sent it: not an outcome this forecast was ahead of
            key = (target[0], target[index])
            if key in seen_targets[ax]:
                continue
            seen_targets[ax].add(key)
            act = enc.encode([target[index][:400]], show_progress_bar=False)[0]
            p_, a_ = np.asarray(triple["emb"], dtype="float32"), np.asarray(act, dtype="float32")
            error = 1.0 - float(p_ @ a_ / (np.linalg.norm(p_) * np.linalg.norm(a_) + 1e-9))
            row.update({ax + "_conf": None if triple.get("confidence_placeholder") else triple.get("confidence"),
                        ax + "_dsim": triple.get("decode_similarity"), ax + "_err": round(error, 4)})
        if row["g_err"] is not None or row.get("s_err") is not None:
            rows.append(row)
    return rows


def axis_stats(rows, ax, holdout):
    """One axis, judged on the latest third of its QUALIFIED rows (confidence present when forecast)."""
    import numpy as np
    axis_rows = [r for r in rows if r.get(ax + "_err") is not None]
    measured = [r for r in axis_rows if r[ax + "_conf"] is not None and r[ax + "_dsim"] is not None]
    left_out = len(axis_rows) - len(measured)
    if not measured:
        return {"n_holdout": 0, "n_joined": len(axis_rows), "n_unqualified_left_out": left_out,
                "unmeasured": "no joined row carries a qualified confidence"}
    axis_hold, axis_why = holdout(measured, by="time")
    conf = [r[ax + "_conf"] for r in axis_hold]; dsim = [r[ax + "_dsim"] for r in axis_hold]; e = [r[ax + "_err"] for r in axis_hold]
    wb = [r["iso"][:16] for r in axis_hold if r[ax + "_conf"] >= np.percentile(conf, 67) and r[ax + "_err"] >= np.percentile(e, 67)]
    return {"n_holdout": len(axis_hold), "n_joined": len(axis_rows), "n_measured": len(measured),
            "n_unqualified_left_out": left_out, "holdout": axis_why,
            "monotonicity_conf_vs_err": spear(conf, e), "bins_low_mid_high_err": bins(conf, e),
            "CONTROL_dsim_vs_err": spear(dsim, e), "wrong_but_confident": wb[:5]}


def preregistered(legacy_rows, served_rows, reg=PREREGISTERED):
    """The registered evaluation: the first reg['n'] after-reply targets, scored once."""
    out = {"registration": reg}
    for name, rs in (("served", served_rows), ("legacy", legacy_rows)):
        elig = sorted((r for r in rs if r.get("trigger") == "after_reply" and r.get("g_err") is not None
                       and r.get("g_conf") is not None and r.get("g_dsim") is not None
                       and str(r.get("iso", ""))[:10] >= reg["registered"]),
                      key=lambda r: float(r.get("ts") or 0))
        if len(elig) < reg["n"]:
            out[name] = {"state": "COLLECTING", "n": len(elig), "needed": reg["n"]}
            continue
        first = elig[:reg["n"]]
        conf = [r["g_conf"] for r in first]; err = [r["g_err"] for r in first]; dsim = [r["g_dsim"] for r in first]
        mono, ctrl = spear(conf, err), spear(dsim, err)
        ok = (mono is not None and ctrl is not None and mono <= reg["pass"]["max_monotonicity"]
              and mono <= ctrl - reg["pass"]["beat_control_by"])
        out[name] = {"state": "PASS" if ok else "FAIL", "n": len(first), "monotonicity_conf_vs_err": mono,
                     "CONTROL_dsim_vs_err": ctrl, "bins_low_mid_high_err": bins(conf, err),
                     "first_iso": first[0]["iso"][:16], "last_iso": first[-1]["iso"][:16]}
    return out


def _served_identity():
    import hashlib
    path = os.path.join(MEM, "jepa-readouts", "gloria.npz")
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest(), os.path.getmtime(path)
    except Exception:
        return None


def main():
    import numpy as np
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
    from jepa_predictor import encoder
    try:
        hist = [json.loads(l) for l in open(HIST)]
    except Exception:
        print("[jepa-audit] no history yet"); return
    from jepa_ranking_audit import realized_ledger, load_arrivals
    led = realized_ledger()
    arrivals = load_arrivals(os.path.join(MEM, "jepa-self-forecasts.jsonl"))
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
    rows = joined_rows(hist, turns, enc, checkpoint, trained_before, arrivals=arrivals)
    served = _served_identity()
    served_rows = joined_rows(hist, turns, enc, None, None, arrivals=arrivals, served=served) if served else []
    n = len(rows)
    if n < 8:
        print("[jepa-audit] only %d distinct joined outcomes - honest answer: TOO EARLY (release needs >=30 held out)" % n)
        json.dump({"n_joined": n, "verdict": "INSUFFICIENT", "checkpoint": checkpoint,
                   "holdout_protocol": "prospective-checkpoint-v1"}, open(OUT, "w"), indent=2); return
    # review 207: the verdict is computed on a HELD-OUT slice (the latest third by time), never on the
    # rows the head's own thresholds were shaped by. The full-sample numbers stay beside them.
    hold, hold_why = _cal.holdout(rows, by="time")
    if _cal.checkpoint_fingerprint() != checkpoint: return
    res = {"n_joined": n, "n_holdout": len(hold), "holdout": hold_why,
           "criteria_version": getattr(_cal, "CRITERIA_VERSION", "unknown"),
           "checkpoint": checkpoint, "holdout_protocol": "prospective-checkpoint-v1",
           "by_trigger": {t: sum(1 for r in rows if r["trigger"] == t) for t in sorted({r["trigger"] for r in rows})}}
    for ax in ("g", "s"):
        res[ax] = axis_stats(rows, ax, _cal.holdout)
    _measured = [r for r in hold if r["g_conf"] is not None and r["s_conf"] is not None]
    res["axis_lockstep_corr"] = spear([r["g_conf"] for r in _measured], [r["s_conf"] for r in _measured]) if len(_measured) > 2 else None
    res["full_sample"] = {ax: {"monotonicity_conf_vs_err": spear([r[ax + "_conf"] for r in rows if r[ax + "_conf"] is not None],
                                                                 [r[ax + "_err"] for r in rows if r[ax + "_conf"] is not None])} for ax in ("g", "s")}
    if served:
        res["served_gloria"] = dict(axis_stats(served_rows, "g", _cal.holdout), checkpoint=served[0], source=READOUT_SCHEMA,
                                    note="the Gloria triple predict() served; reported, not a release input")
    res["preregistered"] = preregistered(rows, served_rows)
    res["reading"] = ("conf beats control if monotonicity is more negative than CONTROL; equal-or-neither = variance without usefulness. "
                      "lockstep near 1.0 = one global signal wearing two names.")
    json.dump(res, open(OUT, "w"), indent=2)
    sg = res.get("served_gloria") or {}
    print("[jepa-audit] n=%d | gloria mono %s (control %s) | self mono %s (control %s) | lockstep %s | served gloria mono %s (control %s, n=%s)"
          % (n, res["g"].get("monotonicity_conf_vs_err", "unmeasured"), res["g"].get("CONTROL_dsim_vs_err"),
             res["s"].get("monotonicity_conf_vs_err", "unmeasured"), res["s"].get("CONTROL_dsim_vs_err"), res["axis_lockstep_corr"],
             sg.get("monotonicity_conf_vs_err", "unmeasured"), sg.get("CONTROL_dsim_vs_err"), sg.get("n_holdout", 0)))
if __name__ == "__main__":
    main()
