"""Runs the pre-registered grid (prereg.json, commit 3b14cb93). Selection on the first 38 rows; the chosen
configuration per family is scored once on the last 39. Counts only."""
import os, sys, json, pickle, statistics
sys.path.insert(0, os.path.expanduser("~/review-scratch-20261114-jepa-ttt"))
import numpy as np
import ttt_lib as L
import jepa_predictor as JP

D = pickle.load(open(os.path.join(L.SCR, "data.pkl"), "rb"))
rows, pre, ledger, turns3 = D["rows"], D["pre"], D["ledger"], D["turns3"]
assert len(rows) == 77
SPLIT = 38
split_ts = rows[SPLIT]["at"]
enc = L.CachedEncoder(JP.encoder())
enc.cache.update(pickle.load(open(os.path.join(L.SCR, "emb.pkl"), "rb")))

Xp = enc.encode([r["ctx"] for r in pre]); Yp = enc.encode([r["target"][:400] for r in pre])
FISHER = L.fisher_from(L.load_net(), Xp, Yp)

GRID = [("F0", {"kind": "frozen"})]
GRID += [("F1", {"kind": "readout", "lr": lr}) for lr in (1e-5, 1e-4, 1e-3)]
GRID += [("F2", {"kind": "readout_anchor", "lr": lr, "lam": lam, "buffer": 16}) for lr in (1e-4, 1e-3) for lam in (0.1, 1.0, 10.0)]
GRID += [("F3a", {"kind": "logvar_only", "lr": lr, "buffer": 16}) for lr in (1e-4, 1e-3, 1e-2)]
GRID += [("F3b", {"kind": "ridge_conf", "ridge_lam": rl}) for rl in (0.1, 1.0, 10.0)]

results = []
for fam, cfg in GRID:
    learner = L.Learner(L.load_net(), fisher=FISHER if cfg["kind"] == "readout_anchor" else None, **cfg)
    hist, preds = L.replay(rows, enc, learner, ck_id="replay-%s" % fam)
    s = L.score(hist, ledger, turns3, enc, split_ts, preds=preds)
    drift_sel = learner.trace[SPLIT - 1] if len(learner.trace) >= SPLIT else 0.0
    results.append({"family": fam, "cfg": cfg, "score": s, "drift_at_split": drift_sel,
                    "max_drift": learner.max_drift,
                    "median_update_ms": round(statistics.median(learner.update_ms), 2) if learner.update_ms else 0.0,
                    "n_updates": learner.n_updates})

f0 = results[0]
chosen = {"F0": f0}
selection_table = []
for fam in ("F1", "F2", "F3a", "F3b"):
    cands = [r for r in results if r["family"] == fam]
    best = None
    for r in cands:
        a = r["score"]["first"]
        elig = (r["score"]["finite"] and r["drift_at_split"] <= 0.05 and a["mrr"] is not None
                and a["mrr"] >= f0["score"]["first"]["mrr"] - 0.02 and a["mono"] is not None and a["control_dsim"] is not None)
        margin = (a["mono"] - a["control_dsim"]) if elig else None
        selection_table.append({"family": fam, "cfg": r["cfg"], "first_mrr": a["mrr"], "first_mono": a["mono"],
                                "first_control": a["control_dsim"], "drift_at_split": round(r["drift_at_split"], 5),
                                "eligible": elig})
        if elig and (best is None or margin < best[0] - 1e-12):
            best = (margin, r)
    if best:
        chosen[fam] = best[1]

def verdict(r):
    b, f = r["score"]["second"], f0["score"]["second"]
    checks = {
        "ranking_ge_frozen": b["mrr"] is not None and b["mrr"] >= f["mrr"],
        "mono_le_-0.20": b["mono"] is not None and b["mono"] <= -0.20,
        "beats_control_by_0.10": b["mono"] is not None and b["control_dsim"] is not None and b["mono"] <= b["control_dsim"] - 0.10,
        "drift_le_0.05": r["max_drift"] <= 0.05 and r["score"]["finite"],
        "no_collapse": r["score"]["collapse_mean_pairwise_cos_second"] <= f0["score"]["collapse_mean_pairwise_cos_second"] + 0.05,
        "cost_le_250ms": r["median_update_ms"] <= 250,
    }
    return checks, all(checks.values())

scored = {}
for fam, r in chosen.items():
    checks, ok = verdict(r)
    scored[fam] = {"cfg": r["cfg"], "second": r["score"]["second"], "first": r["score"]["first"],
                   "all": r["score"]["all"], "max_drift": round(r["max_drift"], 5),
                   "collapse_mean_pairwise_cos_second": r["score"]["collapse_mean_pairwise_cos_second"],
                   "median_update_ms": r["median_update_ms"], "n_updates": r["n_updates"],
                   "checks": checks, "pass": ok if fam != "F0" else None}

out = {"prereg_commit": "3b14cb93", "n": len(rows), "split": [SPLIT, len(rows) - SPLIT],
       "selection": selection_table, "scored_once": scored}
os.makedirs(os.path.join(L.SCR, "out"), exist_ok=True)
json.dump(out, open(os.path.join(L.SCR, "out", "ttt-result.json"), "w"), indent=1)
for row in selection_table:
    print("SEL", json.dumps(row))
for fam, r in scored.items():
    print("SCORED", fam, json.dumps({k: r[k] for k in ("cfg", "max_drift", "median_update_ms", "collapse_mean_pairwise_cos_second", "pass", "checks")}))
    print("   second", json.dumps(r["second"]))
