#!/usr/bin/env python3
"""The regression gate for the exact solver as the LIVE repair chooser (see PREREGISTRATION-live-gate.md, written
before this was scored on any held-out seed).

On each pre-registered benchmark, the same network, after the same check questions and the same answers, is repaired
twice: by belief_revision's own plan ("old", what live does today) and by belief_revision_verify.choose ("exact",
what live does with BELIEF_REVISION_SOLVER=exact). Both are scored with the benchmark's own scorer.

  criteria   experiments/contradiction-backprop/bench_criteria.py   answers from the truth, flipped (10-15%)
  answerer   experiments/contradiction-backprop/bench_answerer.py   records, then AEON - from the checker cache only
             (nothing is sent: a prompt not in the cache is answered "unknown", for both choosers alike, and counted)
  energy     experiments/energy-repair/bench.py, checked track        the cached post-check networks

    python3 gate_live.py --split dev  --out /tmp/gate-dev.json
    python3 gate_live.py --split test --out results-live-gate.json     # once: refuses a second scoring
"""
import argparse, copy, hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CB = os.path.join(REPO, "experiments", "contradiction-backprop")
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, CB)
sys.path.insert(0, HERE)
import belief_revision as BR
import belief_revision_verify as V
import belief_revision_answer as A
import bench_criteria as BC
import bench_answerer as BA

TEST_RESULT = os.path.join(HERE, "results-live-gate.json")
SPLITS = {"criteria": {"dev": range(0, 120), "test": range(5000, 5150)},
          "answerer": {"dev": range(0, 60), "test": range(9000, 9075)},
          "energy": {"dev": range(0, 40), "test": range(7000, 7060)}}
# Gloria's three criteria, and how far "beyond noise" is (PREREGISTRATION-live-gate.md)
MARGIN = {"localization": 0.02, "revision_recall": 0.02, "revision_precision": 0.02, "conclusions_correct": 0.02,
          "preservation": 0.005}
PRESERVATION_FLOOR = 0.99


def _hers(g, plan):
    return sum(1 for r in plan["revisions"] if r["action"] in ("retract", "lower") and g.nodes[r["node"]]["kind"] == "gloria")


def _pair(g2, p):
    t0 = time.perf_counter()
    sp, status = V.choose(g2, p)
    return sp, status, time.perf_counter() - t0


MISSES = [0]


def cache_only(url, body, timeout):
    key = hashlib.sha256(json.dumps([url, body], sort_keys=True).encode()).hexdigest()
    hit = BA._load_cache().get(key)
    if hit:
        return hit["status"], hit["headers"], hit["raw"].encode()
    MISSES[0] += 1
    return 503, {}, b""                                   # never sent: unknown, for both choosers alike


def criteria_one(sc, seed):
    g, T = BC.network(sc, seed)
    acc = 0.85 if sc == "noisy" else 0.9
    import random
    rng = random.Random("answers:%s" % seed)

    def ask(node):
        if node not in T["truth"]:
            return None
        ans = T["truth"][node]
        return ans if rng.random() < acc else (not ans)
    g2 = copy.deepcopy(g)
    p = BR.localize(g2, ask, budget=12, accuracy=acc, at="bench")
    return g, g2, T, p


def answerer_one(sc, seed):
    g, T = BC.network(sc, seed)
    w = BA.World(g, T)
    g2 = copy.deepcopy(g)
    p = BR.localize(g2, A.Answerer(w, transport=cache_only), budget=12, at="bench")
    return g, g2, T, p


def _cb_job(job):
    kind, sc, seed = job
    MISSES[0] = 0
    g, g2, T, p = (criteria_one if kind == "criteria" else answerer_one)(sc, seed)
    sp, status, secs = _pair(g2, p)
    fell = sp is None
    sp = p if fell else sp
    scores = {m: BC.score(g, T, BC._from_plan(plan)) for m, plan in (("old", p), ("exact", sp))}
    return sc, scores, {"fallback": int(fell), "her_old": _hers(g2, p), "her_exact": _hers(g2, sp), "secs": secs,
                        "differ": int(BC._from_plan(p)["changed"] != BC._from_plan(sp)["changed"]), "misses": MISSES[0]}


def run_cb(kind, split, workers=12):
    from multiprocessing import Pool
    agg = {"old": {}, "exact": {}}
    extra = {"networks": 0, "fallback": 0, "her_words_revised": {"old": 0, "exact": 0}, "differ": 0, "solver_seconds": 0.0,
             "checker_cache_misses": 0}
    jobs = [(kind, sc, seed) for sc in BC.SCENARIOS for seed in SPLITS[kind][split]]
    with Pool(workers) as pool:
        results = list(pool.imap(_cb_job, jobs, chunksize=2))
    for sc, scores, x in results:
        extra["networks"] += 1
        extra["fallback"] += x["fallback"]
        extra["solver_seconds"] = round(extra["solver_seconds"] + x["secs"], 3)
        extra["her_words_revised"]["old"] += x["her_old"]
        extra["her_words_revised"]["exact"] += x["her_exact"]
        extra["differ"] += x["differ"]
        extra["checker_cache_misses"] += x["misses"]
        for m, s in scores.items():
            for key in (sc, "all"):
                a = agg[m].setdefault(key, {})
                for k, v in s.items():
                    a[k] = a.get(k, 0) + v
    return {m: {key: _rates(a) for key, a in by.items()} for m, by in agg.items()}, extra


def _rates(a):
    r = lambda x, y: round(x / y, 4) if y else None
    return {"localization": r(a["loc_hit"], a["loc_n"]), "revision_precision": r(a["rec_tp"], a["rec"]),
            "revision_recall": r(a["rec_tp"], a["dep"]), "conclusions_correct": r(a["concl_ok"], a["concl_n"]),
            "preservation": r(a["pres_ok"], a["pres_n"]), "preservation_side": r(a["side_ok"], a["side_n"]),
            "preservation_upstream": r(a["up_ok"], a["up_n"]), "contradictions": a["loc_n"]}


def run_energy(split):
    import importlib.util, core, gen
    spec = importlib.util.spec_from_file_location("energy_bench", os.path.join(HERE, "bench.py"))
    EB = importlib.util.module_from_spec(spec)
    sys.modules["energy_bench"] = EB                  # its warm() pool pickles functions by module name
    spec.loader.exec_module(EB)                      # this directory's bench.py, not contradiction-backprop's
    agg = {"old": {}, "exact": {}}
    extra = {"networks": 0, "fallback": 0, "her_words_revised": {"old": 0, "exact": 0}, "differ": 0, "solver_seconds": 0.0}
    pairs = [(sc, s) for sc in gen.ALL for s in SPLITS["energy"][split]]
    EB.warm(pairs)
    for sc, seed in pairs:
        g2, T = EB.checked(sc, seed)
        P = core.Problem(g2)
        R_star, E_star, _ = core.solve_exact(P)
        opt = core.all_optima(P, E_star, limit=4)
        p = T["br_plan"]
        sp, status, secs = _pair(g2, p)
        extra["networks"] += 1
        extra["solver_seconds"] += secs
        if sp is None:
            extra["fallback"] += 1
            sp = p
        extra["her_words_revised"]["old"] += _hers(g2, p)
        extra["her_words_revised"]["exact"] += _hers(g2, sp)
        for m, plan in (("old", p), ("exact", sp)):
            R = {r["node"] for r in plan["revisions"] if r["action"] in ("retract", "lower")}
            top = {c["conflict"]: (c["blame"][0][0] if c["blame"] else None) for c in plan["conflicts"]}
            s = EB.score(P, T, {"repair": R, "seconds": 0.0, "top": top}, E_star, R_star, len(opt))
            s["multi"] = int(len(opt) > 1)
            fam = "large" if sc in gen.LARGE else "small"
            for key in (sc, fam, "all"):
                a = agg[m].setdefault(key, {})
                for k, v in s.items():
                    a[k] = a.get(k, 0) + v
        extra["differ"] += int({r["node"] for r in p["revisions"] if r["action"] in ("retract", "lower")}
                               != {r["node"] for r in sp["revisions"] if r["action"] in ("retract", "lower")})
    res = {m: {key: EB.summarize(a) for key, a in by.items()} for m, by in agg.items()}
    return res, extra


def verdict(res):
    """Per benchmark: the exact chooser does not fall below the old one by more than the margin on any of Gloria's
    three criteria; preservation stays >= 0.99; her words are never revised."""
    out = {}
    for bench, (r, extra) in res.items():
        old, new = r["old"]["all"], r["exact"]["all"]
        v = {}
        for k, m in MARGIN.items():
            v[k] = {"old": old[k], "exact": new[k], "delta": round(new[k] - old[k], 4), "pass": new[k] >= old[k] - m}
        v["preservation_floor"] = {"exact": new["preservation"], "pass": new["preservation"] >= PRESERVATION_FLOOR}
        v["her_words_never_revised"] = {"exact": extra["her_words_revised"]["exact"],
                                        "pass": extra["her_words_revised"]["exact"] == 0}
        v["pass"] = all(x["pass"] for x in v.values() if isinstance(x, dict))
        out[bench] = v
    out["pass"] = all(v["pass"] for v in out.values() if isinstance(v, dict))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--benches", default="criteria,answerer,energy")
    a = ap.parse_args()
    if a.split == "test" and (os.path.exists(a.out) or os.path.exists(TEST_RESULT)):
        sys.exit("the held-out split is scored once; a gate result already exists")
    res = {}
    for b in a.benches.split(","):
        t0 = time.time()
        res[b] = run_energy(a.split) if b == "energy" else run_cb(b, a.split)
        res[b][1]["wall_seconds"] = round(time.time() - t0, 1)
        print(b, json.dumps(res[b][1], sort_keys=True), flush=True)
    doc = {"split": a.split, "margins": MARGIN, "preservation_floor": PRESERVATION_FLOOR,
           "results": {b: {"scores": r, "extra": e} for b, (r, e) in res.items()}, "gate": verdict(res)}
    with open(a.out, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    for b, v in doc["gate"].items():
        if isinstance(v, dict):
            print(b, "PASS" if v["pass"] else "FAIL", {k: (x.get("old"), x.get("exact"), x["pass"]) for k, x in v.items()
                                                        if isinstance(x, dict)})
    print("gate:", "PASS" if doc["gate"]["pass"] else "FAIL")


if __name__ == "__main__":
    main()
