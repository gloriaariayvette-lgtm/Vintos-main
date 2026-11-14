#!/usr/bin/env python3
"""Synthetic benchmark for contradiction back-propagation (see PREREGISTRATION.md, written before any run).

    python3 bench.py --split dev  --out /tmp/dev.json      # code check only; no constant is tuned on it
    python3 bench.py --split test --out results-test.json  # scored once: refuses if the file exists
"""
import argparse, copy, json, math, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import belief_revision as BR

SCENARIOS = ("single", "multi", "noisy", "chain")
SPLITS = {"dev": range(0, 100), "test": range(1000, 1150)}
SOURCE_KINDS = [("memory", 3), ("observation", 3), ("private_record", 3), ("self_statement", 2),
                ("causal_self_model", 2), ("lesson", 2), ("world_prediction", 2), ("soul", 1), ("gloria", 1)]


def _poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def _wchoice(rng, items, weights):
    t = rng.random() * sum(weights)
    for it, w in zip(items, weights):
        t -= w
        if t <= 0:
            return it
    return items[-1]


def network(scenario, seed):
    """One belief network with planted faults. Returns (graph, truth)."""
    rng = random.Random("%s:%d" % (scenario, seed))
    jitter = {k: rng.uniform(0.5, 1.5) for k in BR.PRIOR_FAULT}
    noisy = scenario == "noisy"
    det = 0.9 if noisy else BR.DEFAULT_DETECTOR
    g = BR.Graph()
    meta = {}                                    # assumption id -> {age, conf}
    kinds = {}
    srcs = []
    for i in range(rng.randint(6, 12)):
        k = _wchoice(rng, [k for k, _ in SOURCE_KINDS], [w for _, w in SOURCE_KINDS])
        srcs.append("s%d" % i)
        kinds["s%d" % i] = k
    # layers of inference
    depth = rng.randint(3, 5) if scenario == "chain" else rng.randint(1, 2)
    layers, derived, just = [srcs], [], {}
    for L in range(1, depth + 1):
        width = rng.randint(1, 2) if scenario == "chain" else rng.randint(2, 4)
        layer = []
        for w in range(width):
            d = "d%d_%d" % (L, w)
            pool = [x for lay in layers for x in lay]
            js = []
            for _ in range(2 if rng.random() < 0.25 else 1):
                ants = {rng.choice(layers[-1])}
                for _ in range(rng.randint(0, 2)):
                    ants.add(rng.choice(pool))
                js.append(sorted(ants))
            just[d] = js
            layer.append(d)
            derived.append(d)
        layers.append(layer)
    rules = ["rule:" + d for d in derived]
    # planted faults
    nf = {"single": 1, "multi": rng.randint(2, 3), "noisy": rng.randint(1, 2), "chain": rng.randint(1, 2)}[scenario]
    faults = set()
    while len(faults) < nf:
        if scenario == "chain" and rng.random() < 0.35:
            faults.add(rng.choice(rules))
        else:
            cand = [s for s in srcs if s not in faults]
            faults.add(_wchoice(rng, cand, [BR.PRIOR_FAULT[kinds[s]] * jitter[kinds[s]] for s in cand]))
    # source metadata: informative but noisy
    for s in srcs:
        bad = s in faults
        meta[s] = {"age": rng.uniform(0, 240), "conf": rng.uniform(0.35, 0.9) if bad else rng.uniform(0.45, 0.95),
                   "n": _poisson(rng, 1.5 if bad else 3.0)}
        g.source(s, kinds[s], confidence=round(meta[s]["conf"], 3), evidence_count=meta[s]["n"],
                 age_days=meta[s]["age"])
    for d in derived:
        ants = sorted({a for j in just[d] for a in j})
        age = min(meta[a]["age"] for a in ants) * rng.uniform(0.3, 1.0)
        conf = sum(meta[a]["conf"] for a in ants) / len(ants)
        meta[d] = meta["rule:" + d] = {"age": age, "conf": conf, "n": 0}
        g.derived(d, "inference_result", just[d], confidence=round(conf, 3))
        g.nodes["rule:" + d]["meta"]["age"] = age
    # truth
    truth = {}
    for s in srcs:
        truth[s] = s not in faults
    for d in derived:
        truth[d] = ("rule:" + d) not in faults and any(all(truth[a] for a in j) for j in just[d])
    for r in rules:
        truth[r] = r not in faults
    nodes = srcs + derived
    false_nodes = [n for n in nodes if not truth[n]]
    true_nodes = [n for n in nodes if truth[n]]
    n_w = [0]

    def witness(target, faulty=False):
        w = "w%d" % n_w[0]
        n_w[0] += 1
        k = "gloria" if rng.random() < 0.5 else "observation"
        meta[w] = {"age": rng.uniform(0, 10), "conf": 0.9, "n": 0}
        g.source(w, k, confidence=0.9, evidence_count=0, age_days=meta[w]["age"])
        truth[w] = not faulty
        if faulty:
            faults.add(w)
        g.conflict("c:%s:%s" % (target, w), [target, w], reliability=det, kind="witness")

    for n in false_nodes:
        if rng.random() < (0.5 if n in just else 0.35):
            witness(n)
    if not g.conflicts and false_nodes:
        witness(max(false_nodes, key=lambda n: (n in just, n)))
    fd = [n for n in false_nodes if n in just]
    td = [n for n in true_nodes if n in just]
    if fd and td and rng.random() < 0.3:
        a, b = rng.choice(fd), rng.choice(td)
        g.conflict("c:%s:%s" % (a, b), [a, b], reliability=det, kind="pair")
    if noisy:
        extras = [x for x in ("wrong_witness", "false_alarm", "confirm") if rng.random() < 0.5] or [rng.choice(
            ("wrong_witness", "false_alarm", "confirm"))]
        if "wrong_witness" in extras and true_nodes:
            witness(rng.choice(true_nodes), faulty=True)
        if "false_alarm" in extras and len(true_nodes) >= 2:
            a, b = rng.sample(true_nodes, 2)
            g.conflict("fa:%s:%s" % (a, b), [a, b], reliability=0.9, kind="false_alarm")
        if "confirm" in extras:
            for n in rng.sample(true_nodes, min(len(true_nodes), rng.randint(1, 3))):
                g.confirm(n, accuracy=0.85)
            if false_nodes and rng.random() < 0.15:
                g.confirm(rng.choice(false_nodes), accuracy=0.85)
    return g, {"faults": set(faults), "truth": truth, "meta": meta, "derived": derived}


# -- methods ------------------------------------------------------------------------------------------
def _candidates(g):
    out = {}
    for c in g.conflicts:
        ng = g.nogoods(c)
        out[c["id"]] = sorted(set().union(*ng)) if ng else []
    return out


def _withdrawn(g, derived, revised):
    return {d for d in derived if g.envs(d) and all(e & revised for e in g.envs(d))}


def _revised(p):
    """Retracted or lowered; her words count when the module would have lowered them but left them to her."""
    return {r["node"] for r in p["revisions"] if r["action"] in ("retract", "lower")
            or (r["action"] == "flag_for_gloria" and (r["blame"] >= BR.LOWER_AT or r["explains"]))}


def tms(g, T):
    p = BR.plan(g, at="bench")
    top = {c["conflict"]: (c["blame"][0][0] if c["blame"] else None) for c in p["conflicts"]}
    rev = _revised(p)
    wd = {r["node"] for r in p["rederive"] if r["action"] == "withdraw"}
    lowered = {r["node"] for r in p["rederive"] if r["action"] == "lower"}
    # second pass: revised sources known wrong
    g2 = copy.deepcopy(g)
    for a in rev:
        g2.nodes[a]["prior"] = 0.95
    g2._envs = None
    p2 = BR.plan(g2, at="bench")
    rev2 = _revised(p2)
    return {"top": top, "revised": rev, "withdrawn": wd, "lowered": lowered, "stable": not (rev2 - rev)}


def baseline(g, T, how):
    cands = _candidates(g)
    top, rev = {}, set()
    for cid, cs in cands.items():
        if not cs:
            continue
        if how == "uniform":
            rev.update(cs)
            top[cid] = ("uniform", cs)
            continue
        if how == "recent":
            pick = min(cs, key=lambda a: (T["meta"].get(a, {}).get("age", 0.0), a))
        else:
            pick = min(cs, key=lambda a: (T["meta"].get(a, {}).get("conf", 0.5), a))
        top[cid] = pick
        rev.add(pick)
    return {"top": top, "revised": rev, "withdrawn": _withdrawn(g, T["derived"], rev), "stable": True}


METHODS = {"tms_bayes": tms, "most_recent": lambda g, T: baseline(g, T, "recent"),
           "lowest_confidence": lambda g, T: baseline(g, T, "lowconf"),
           "uniform": lambda g, T: baseline(g, T, "uniform")}


def score_network(g, T, out):
    F = T["faults"]
    cands = _candidates(g)
    allc = set().union(*cands.values()) if cands else set()
    det = F & allc
    s = {"top_hit": 0.0, "top_n": 0, "tp": len(out["revised"] & det), "rev": len(out["revised"] & allc),
         "det": len(det), "true_c": len(allc - F), "true_c_rev": len((allc - F) & out["revised"])}
    for cid, cs in cands.items():
        if not (set(cs) & F):
            continue
        s["top_n"] += 1
        t = out["top"].get(cid)
        if isinstance(t, tuple):
            s["top_hit"] += len(set(t[1]) & F) / float(len(t[1]))
        elif t in F:
            s["top_hit"] += 1
    at_risk = [d for d in T["derived"] if T["truth"][d] and g.envs(d) and set().union(*g.envs(d)) & allc]
    s["true_d"] = len(at_risk)
    s["true_d_wd"] = sum(1 for d in at_risk if d in out["withdrawn"])
    # secondary, not barred: false beliefs downstream of a candidate that were withdrawn or lowered
    false_d = [d for d in T["derived"] if not T["truth"][d] and g.envs(d) and set().union(*g.envs(d)) & allc]
    s["false_d"] = len(false_d)
    s["false_d_hit"] = sum(1 for d in false_d if d in out["withdrawn"] or d in out.get("lowered", set()))
    nog = {c["id"]: g.nogoods(c) for c in g.conflicts}
    need = [cid for cid, cs in cands.items() if set(cs) & F]
    res = all(nog[cid] and all(e & out["revised"] for e in nog[cid]) for cid in need)
    s["converged"] = int(res and out["stable"])
    return s


def run(split):
    agg = {}
    for sc in SCENARIOS:
        for seed in SPLITS[split]:
            g, T = network(sc, seed)
            for m, fn in METHODS.items():
                out = fn(g, T)
                s = score_network(g, T, out)
                for key in (sc, "all"):
                    a = agg.setdefault(m, {}).setdefault(key, {})
                    for k, v in s.items():
                        a[k] = a.get(k, 0) + v
                    a["networks"] = a.get("networks", 0) + 1
    res = {}
    for m, by in agg.items():
        res[m] = {}
        for key, a in by.items():
            res[m][key] = {
                "top1": round(a["top_hit"] / a["top_n"], 4) if a["top_n"] else None,
                "precision": round(a["tp"] / a["rev"], 4) if a["rev"] else None,
                "recall": round(a["tp"] / a["det"], 4) if a["det"] else None,
                "collateral_sources": round(a["true_c_rev"] / a["true_c"], 4) if a["true_c"] else None,
                "collateral_beliefs": round(a["true_d_wd"] / a["true_d"], 4) if a["true_d"] else None,
                "convergence": round(a["converged"] / a["networks"], 4),
                "downstream_false_caught": round(a["false_d_hit"] / a["false_d"], 4) if a["false_d"] else None,
                "networks": a["networks"], "contradictions_with_fault": a["top_n"], "detectable_faults": a["det"]}
    return res


BARS = {"top1": 0.75, "top1_noisy": 0.60, "margin": 0.10, "precision": 0.75, "recall": 0.70,
        "collateral_sources": 0.10, "collateral_beliefs": 0.10, "convergence": 0.90}


def verdict(res):
    t = res["tms_bayes"]["all"]
    best_base = max(res[m]["all"]["top1"] for m in res if m != "tms_bayes")
    v = {"top1": t["top1"] >= BARS["top1"], "top1_noisy": res["tms_bayes"]["noisy"]["top1"] >= BARS["top1_noisy"],
         "margin": t["top1"] - best_base >= BARS["margin"], "precision": t["precision"] >= BARS["precision"],
         "recall": t["recall"] >= BARS["recall"],
         "collateral_sources": t["collateral_sources"] <= BARS["collateral_sources"],
         "collateral_beliefs": t["collateral_beliefs"] <= BARS["collateral_beliefs"],
         "convergence": t["convergence"] >= BARS["convergence"]}
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=sorted(SPLITS), required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.split == "test" and os.path.exists(a.out):
        sys.exit("the test split is scored once; %s already exists" % a.out)
    res = run(a.split)
    doc = {"split": a.split, "results": res, "bars": BARS, "pass": verdict(res)}
    with open(a.out, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    for m in res:
        r = res[m]["all"]
        print("%-18s top1=%s P=%s R=%s coll_src=%s coll_bel=%s conv=%s" % (
            m, r["top1"], r["precision"], r["recall"], r["collateral_sources"], r["collateral_beliefs"],
            r["convergence"]))
    print("pass:", doc["pass"])


if __name__ == "__main__":
    main()
