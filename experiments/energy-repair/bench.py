#!/usr/bin/env python3
"""Energy-landscape belief repair against the existing contradiction back-propagation (see PREREGISTRATION.md).

    python3 bench.py --split dev  --methods br,exact,energy --out /tmp/dev.json [--scenarios a,b] [--seeds N]
    python3 bench.py --split test --out results-test.json       # once: refuses if a test result exists
"""
import argparse, json, math, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen, core
import belief_revision as BR

SPLITS = {"dev": range(0, 40), "test": range(7000, 7060)}
TEST_RESULT = os.path.join(HERE, "results-test.json")
TEST_PASSIVE = os.path.join(HERE, "results-test-passive.json")


# -- methods: each returns {"repair": set, "seconds": float, ...} ------------------------------------------
def m_br(P, T, net):
    """belief_revision as it stands: on the checked track, the plan its own bisection checks ended with (the time
    the checks took is counted); on the passive track, plan() on the recorded evidence."""
    t0 = time.perf_counter()
    p = T.get("br_plan") or BR.plan(net, at="bench")
    R = {r["node"] for r in p["revisions"] if r["action"] in ("retract", "lower")}
    top = {c["conflict"]: (c["blame"][0][0] if c["blame"] else None) for c in p["conflicts"]}
    return {"repair": R, "seconds": T.get("br_seconds", 0.0) + time.perf_counter() - t0, "top": top}


def m_exact(P, T, net):
    R, E, info = core.solve_exact(P)
    return {"repair": R, "seconds": info["seconds"], "proved_optimal": info.get("optimal", False)}


def m_exact_stable(P, T, net):
    R, secs, n = core.solve_stable(P)
    return {"repair": R, "seconds": secs}


def m_exact_hard(P, T, net):
    R, E, info = core.solve_exact(P, hard=True)
    return {"repair": R, "seconds": info["seconds"]}


def energy_candidates(P, variant, restarts, prune, search=False, **kw):
    import energy as EN
    Tn = EN.Tensors(P)
    out = []
    for r in range(restarts):
        R, soft, _ = EN.minimize(P, variant=variant, seed=r, noise=0.0 if r == 0 else 1.5, T=Tn, **kw)
        R = core.prune(P, R) if prune else R
        out.append(core.local_search(P, R) if search else R)
    return out


def pick(P, cands):
    """The exact checker as verifier: the candidate with the lowest energy (earlier on ties)."""
    best = None
    for R in cands:
        R = set(R)
        key = (round(P.energy(R), 9), sum(P.depth.get(a, 0) for a in R), sorted(R))
        if best is None or key < best[0]:
            best = (key, R)
    return best[1]


def m_energy(variant, prune=False, restarts=1, search=False, **kw):
    def run(P, T, net):
        t0 = time.perf_counter()
        R = pick(P, energy_candidates(P, variant, restarts, prune, search, **kw))
        return {"repair": R, "seconds": time.perf_counter() - t0}
    return run


GNN_PATH = os.environ.get("ENERGY_REPAIR_GNN") or os.path.join(HERE, "gnn.pt")


def gnn_candidates(P, prob, samples=12):
    import random as _r
    cands = [{a for a, p in prob.items() if p >= t} for t in (0.5, 0.3, 0.7)]
    rng = _r.Random(len(P.assumptions))
    for _ in range(samples):
        cands.append({a for a, p in prob.items() if rng.random() < p})
    # greedy cover: while a contradiction stands, retract its most likely suspect
    R = set()
    for _ in range(len(P.conflicts) + 1):
        st = P.standing(R)
        if not st:
            break
        sus = [a for a in P.suspects(st[0]) if a not in R]
        if not sus:
            break
        R.add(max(sus, key=lambda a: (prob.get(a, 0), -P.depth.get(a, 0))))
    cands.append(R)
    return [core.prune(P, c) for c in cands]


def m_gnn(P, T, net):
    import gnn
    t0 = time.perf_counter()
    prob = gnn.probs(gnn.load(GNN_PATH), P)
    return {"repair": {a for a, p in prob.items() if p >= 0.5}, "seconds": time.perf_counter() - t0}


def m_hybrid(sources):
    def run(P, T, net):
        t0 = time.perf_counter()
        cands = []
        if "gnn" in sources:
            import gnn
            cands += gnn_candidates(P, gnn.probs(gnn.load(GNN_PATH), P))
        if "energy" in sources:
            cands += energy_candidates(P, "propagated", 4, True, earliness=1e-3)
        return {"repair": pick(P, cands), "seconds": time.perf_counter() - t0, "candidates": len(cands)}
    return run


def m_gnn_topk_ilp(P, T, net):
    """The learned model narrows the search to its top suspects; the exact solver searches only those."""
    import gnn
    t0 = time.perf_counter()
    prob = gnn.probs(gnn.load(GNN_PATH), P)
    k = max(8, 2 * sum(1 for p in prob.values() if p >= 0.5) + 4)
    allowed = sorted(prob, key=lambda a: -prob[a])[:k]
    R, E, info = core.solve_exact(P, allowed=allowed)
    return {"repair": R, "seconds": time.perf_counter() - t0}


def m_llm(rounds):
    def run(P, T, net):
        import llm
        res = llm.repair(P, rounds=2)
        R, ok, sec, tok, status = res[rounds - 1]
        return {"repair": R, "seconds": sum(r[2] for r in res[:rounds]), "calls": rounds,
                "tokens": sum(r[3] for r in res[:rounds]), "unparsed": int(not ok)}
    return run


METHODS = {
    "br": m_br,
    "exact": m_exact,
    "exact_hard": m_exact_hard,
    "exact_stable": m_exact_stable,
    "energy_free": m_energy("free"),
    "energy_free_anneal": m_energy("free", anneal=4.0),
    "energy_prop": m_energy("propagated"),
    "energy_prop_polish": m_energy("propagated", prune=True, earliness=1e-3),
    "energy_prop_search": m_energy("propagated", prune=True, search=True, earliness=1e-3),
    "gnn": m_gnn,
    "hybrid_gnn": m_hybrid(("gnn",)),
    "hybrid_energy": m_hybrid(("energy",)),
    "hybrid": m_hybrid(("gnn", "energy")),
    "gnn_topk_ilp": m_gnn_topk_ilp,
    "llm_first": m_llm(1),
    "llm_selfcorrect": m_llm(2),
}


# -- scoring -----------------------------------------------------------------------------------------------
def score(P, T, out, E_star, R_star, n_optima):
    R = set(out["repair"])
    v = P.verify(R)
    h = v["holds"]
    s = {"networks": 1, "seconds": out["seconds"], "consistent": int(not v["standing"]),
         "optimal": int(v["energy"] <= E_star + 1e-6), "gap": v["energy"] - E_star,
         "same_as_optimum": int(R == R_star), "size": len(R), "bad_hit": len(R & T["bad"]), "bad_n": len(T["bad"]),
         "n_optima": n_optima}
    # 1. localization: per true contradiction against a false conclusion, the earliest real fault among its
    #    ancestors is retracted, and nothing else among that contradiction's suspects that is really sound
    loc_n = loc_hit = loc_any = 0
    for cid, ns, _ in P.conflicts:
        c = next(c for c in P.g.conflicts if c["id"] == cid)
        if c["kind"] != "witness":
            continue
        n = next((x for x in ns if x in T["truth"] and x not in T["premises"]), None)
        if not n or T["truth"][n]:
            continue
        cands = [f for f in T["faults"] if f == n or f in T["anc"](n)]
        if not cands:
            continue
        target = T["fault_ids"][min(cands, key=lambda f: (T["depth"][f], f))]
        loc_n += 1
        sus = P.suspects(cid)
        loc_any += int(target in R)
        loc_hit += int(target in R and not ((R & sus) - T["bad"]))
    s.update(loc_n=loc_n, loc_hit=loc_hit, loc_any=loc_any)
    # 2. revision: the conclusions the repair withdraws against the conclusions really false
    withdrawn = {n for n in T["order"] if not h[n]}
    false = {n for n in T["order"] if not T["truth"][n]}
    s.update(dep=len(false), rec=len(withdrawn), rec_tp=len(false & withdrawn),
             concl_n=len(T["order"]), concl_ok=sum(int(h[n] == T["truth"][n]) for n in T["order"]))
    # 3. preservation: valid nodes that do not depend on any fault stay as they were
    downstream = set()
    for f in T["faults"]:
        downstream |= T["desc"](f) | {f}
    upstream = set()
    for f in T["faults"]:
        upstream |= T["anc"](f)
    pn = pok = sn = sok = un = uok = 0
    for n in T["order"] + T["premises"]:
        if not T["truth"][n] or n in downstream:
            continue
        ok = h[n] and n not in R and ("rule:" + n) not in R
        pn += 1; pok += int(ok)
        if n in upstream:
            un += 1; uok += int(ok)
        else:
            sn += 1; sok += int(ok)
    s.update(pres_n=pn, pres_ok=pok, side_n=sn, side_ok=sok, up_n=un, up_ok=uok)
    # early assumption: a wrong premise where the exact minimal repair lies at that premise
    e_n = e_hit = 0
    for p in T.get("premise_faults", ()):
        if p in R_star:
            e_n += 1; e_hit += int(p in R)
    s.update(early_n=e_n, early_hit=e_hit)
    if "top" in out:                                   # belief_revision's own top-1 localization, as it reports it
        tn = th = 0
        for cid, ns, _ in P.conflicts:
            c = next(c for c in P.g.conflicts if c["id"] == cid)
            n = next((x for x in ns if x in T["truth"] and x not in T["premises"]), None)
            if c["kind"] != "witness" or not n or T["truth"][n]:
                continue
            cands = [f for f in T["faults"] if f == n or f in T["anc"](n)]
            if cands:
                tn += 1
                th += int(out["top"].get(cid) == T["fault_ids"][min(cands, key=lambda f: (T["depth"][f], f))])
        s.update(top_n=tn, top_hit=th)
    for k in ("calls", "tokens", "unparsed"):
        if k in out:
            s[k] = out[k]
    return s


def summarize(a):
    r = lambda x, y: round(x / y, 4) if y else None
    return {"networks": a["networks"], "consistent": r(a["consistent"], a["networks"]),
            "optimal": r(a["optimal"], a["networks"]), "mean_gap": r(a["gap"], a["networks"]),
            "same_as_optimum": r(a["same_as_optimum"], a["networks"]),
            "localization": r(a["loc_hit"], a["loc_n"]), "localization_lenient": r(a["loc_any"], a["loc_n"]),
            "revision_precision": r(a["rec_tp"], a["rec"]), "revision_recall": r(a["rec_tp"], a["dep"]),
            "conclusions_correct": r(a["concl_ok"], a["concl_n"]), "preservation": r(a["pres_ok"], a["pres_n"]),
            "preservation_side": r(a["side_ok"], a["side_n"]), "preservation_upstream": r(a["up_ok"], a["up_n"]),
            "early_premise": r(a["early_hit"], a["early_n"]), "early_n": a["early_n"],
            "true_faults_found": r(a["bad_hit"], a["bad_n"]), "repair_size": r(a["size"], a["networks"]),
            "ms_per_network": round(1000 * a["seconds"] / a["networks"], 2),
            "multiple_optima": r(a["multi"], a["networks"]),
            "contradictions": a["loc_n"],
            "br_top1": r(a.get("top_hit", 0), a.get("top_n", 0)) if "top_n" in a else None,
            "llm_calls": a.get("calls"), "llm_unparsed": a.get("unparsed")}


CACHE = os.environ.get("ENERGY_REPAIR_CACHE") or os.path.expanduser("~/.cache/energy-repair/checked")


def checked(sc, seed):
    """The network after belief_revision's own bisection checks (bench_criteria's tms_bayes: answers from the truth,
    flipped with the scenario's check noise). Every method then repairs on the SAME evidence. Cached on disk."""
    import copy, pickle, random as _r
    path = os.path.join(CACHE, "%s-%d.pkl" % (sc, seed))
    g, T = gen.network(sc, seed)
    if os.path.exists(path):
        with open(path, "rb") as f:
            g2, p, wrong, secs = pickle.load(f)
    else:
        acc = 0.85 if sc in ("noisy", "large_mixed", "ambiguous") else 0.9
        rng = _r.Random("answers:%s:%s" % (sc, seed))

        def ask(node):
            if node not in T["truth"]:
                return None
            ans = T["truth"][node]
            return ans if rng.random() < acc else (not ans)
        g2 = copy.deepcopy(g)
        t0 = time.perf_counter()
        p = BR.localize(g2, ask, budget=12, accuracy=acc, at="bench")
        wrong = {c["nodes"][1] for c in g2.conflicts if c["kind"] == "check" and T["truth"].get(c["nodes"][0], False)}
        os.makedirs(CACHE, exist_ok=True)
        with open(path + ".tmp", "wb") as f:
            secs = time.perf_counter() - t0
            pickle.dump((g2, p, wrong, secs), f)
        os.replace(path + ".tmp", path)
    T = dict(T, bad=set(T["bad"]) | wrong, br_plan=p, br_seconds=secs)
    return g2, T


def _warm(args):
    checked(*args)
    return args


def warm(pairs, workers=16):
    from multiprocessing import Pool
    with Pool(workers) as pool:
        for _ in pool.imap_unordered(_warm, pairs):
            pass


def load(sc, seed, track):
    if track == "checked":
        return checked(sc, seed)
    return gen.network(sc, seed)


def run(split, methods, scenarios, seeds=None, log=None, track="checked"):
    agg = {}
    rows = []
    rng = SPLITS[split] if seeds is None else list(SPLITS[split])[:seeds]
    if track == "checked":
        warm([(sc, s) for sc in scenarios for s in rng])
    for sc in scenarios:
        for seed in rng:
            g, T = load(sc, seed, track)
            P = core.Problem(g)
            R_star, E_star, info = core.solve_exact(P)
            opt = core.all_optima(P, E_star, limit=4)
            for m in methods:
                out = METHODS[m](P, T, g)
                s = score(P, T, out, E_star, R_star, len(opt))
                s["multi"] = int(len(opt) > 1)
                rows.append({"method": m, "scenario": sc, "seed": seed, "repair": sorted(out["repair"]),
                             "optimum": sorted(R_star), "bad": sorted(T["bad"]), "gap": round(s["gap"], 4),
                             "consistent": s["consistent"], "loc": [s["loc_hit"], s["loc_n"]]})
                fam = "large" if sc in gen.LARGE else "small"
                for key in (sc, fam, "all"):
                    a = agg.setdefault(m, {}).setdefault(key, {})
                    for k, v in s.items():
                        a[k] = a.get(k, 0) + v
            if log:
                log("%s %d done" % (sc, seed))
    return {m: {k: summarize(a) for k, a in by.items()} for m, by in agg.items()}, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=sorted(SPLITS), required=True)
    ap.add_argument("--methods", default=",".join(METHODS))
    ap.add_argument("--scenarios", default=",".join(gen.ALL))
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", default=None)
    ap.add_argument("--track", choices=["checked", "passive"], default="checked")
    a = ap.parse_args()
    if a.split == "test" and os.path.exists(a.out):           # every held-out result file is scored once
        sys.exit("the held-out split is scored once; a test result already exists")
    methods = a.methods.split(",")
    res, rows = run(a.split, methods, a.scenarios.split(","), a.seeds, track=a.track)
    with open(a.out, "w") as f:
        json.dump({"split": a.split, "track": a.track, "results": res}, f, indent=1, sort_keys=True)
    if a.rows:
        with open(a.rows, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    keys = ["all", "small", "large"] + a.scenarios.split(",")
    for m in methods:
        for k in keys:
            x = res[m].get(k)
            if not x:
                continue
            print("%-12s %-13s cons=%s opt=%s gap=%s loc=%s recP=%s recR=%s concl=%s pres=%s side=%s early=%s ms=%s" % (
                m, k, x["consistent"], x["optimal"], x["mean_gap"], x["localization"], x["revision_precision"],
                x["revision_recall"], x["conclusions_correct"], x["preservation"], x["preservation_side"],
                x["early_premise"], x["ms_per_network"]))


if __name__ == "__main__":
    main()
