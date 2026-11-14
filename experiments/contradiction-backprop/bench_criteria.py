#!/usr/bin/env python3
"""Gloria's three criteria, measured on synthetic inference chains and DAGs (see PREREGISTRATION-criteria.md).

  1. Localization - the contradiction is traced to the earliest faulty inference, not the last step.
  2. Revision     - only the conclusions that depend on it are recomputed, and the final conclusions are right.
  3. Preservation - independent valid reasoning is left unchanged (target: all of it).

    python3 bench_criteria.py --split dev  --out /tmp/dev.json
    python3 bench_criteria.py --split test --out results-criteria-test.json   # once: refuses if any test result exists
"""
import argparse, copy, json, math, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import belief_revision as BR

SCENARIOS = ("chain", "dag", "noisy", "two_faults")
SPLITS = {"dev": range(0, 120), "test": range(5000, 5150)}
TEST_RESULT = os.path.join(HERE, "results-criteria-test.json")
PREMISE_KINDS = ("observation", "memory", "gloria", "lesson", "private_record")


def _poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def network(scenario, seed):
    """A network of valid premises, a main chain or DAG with planted faulty inference step(s) at varying depth,
    side branches off it, independent side chains, and the contradictions and checks a faulty step produces."""
    rng = random.Random("criteria:%s:%d" % (scenario, seed))
    g = BR.Graph()
    just, parents, main, side_roots = {}, {}, [], []
    premises = []
    for i in range(rng.randint(3, 6)):
        p = "p%d" % i
        premises.append(p)
        g.source(p, rng.choice(PREMISE_KINDS), evidence_count=_poisson(rng, 3.0), age_days=rng.uniform(0, 200))

    def add(nid, js):
        just[nid] = js
        parents[nid] = sorted({a for j in js for a in j})

    if scenario == "chain":
        prev = premises[0]
        for i in range(1, rng.randint(3, 7) + 1):
            j = [prev] + ([rng.choice(premises)] if rng.random() < 0.3 else [])
            add("m%d" % i, [sorted(set(j))])
            main.append("m%d" % i)
            prev = "m%d" % i
    else:
        layers = [premises[:]]
        for L in range(1, rng.randint(3, 6) + 1):
            layer = []
            for w in range(rng.randint(2, 3)):
                nid = "m%d_%d" % (L, w)
                pool_prev, pool_all = layers[-1], [x for lay in layers for x in lay]
                js = [sorted({rng.choice(pool_prev)} | ({rng.choice(pool_all)} if rng.random() < 0.4 else set()))]
                if rng.random() < 0.2:
                    alt = sorted({rng.choice(pool_all)})
                    if alt != js[0]:
                        js.append(alt)
                add(nid, js)
                layer.append(nid)
                main.append(nid)
            layers.append(layer)
    # side branches hanging off the main structure, and independent side chains from their own premises
    k = 0
    for _ in range(rng.randint(1, 3)):
        prev = rng.choice(main + premises)
        for _ in range(rng.randint(1, 3)):
            nid = "b%d" % k; k += 1
            add(nid, [[prev]])
            prev = nid
    for c in range(rng.randint(1, 2)):
        p = "q%d" % c
        g.source(p, rng.choice(PREMISE_KINDS), evidence_count=_poisson(rng, 3.0), age_days=rng.uniform(0, 200))
        premises.append(p)
        prev = p
        for _ in range(rng.randint(2, 3)):
            nid = "s%d" % k; k += 1
            add(nid, [[prev]])
            prev = nid
    order = [n for n in main] + sorted((n for n in just if n not in main), key=lambda n: int(n[1:]))
    for nid in order:
        g.derived(nid, "conclusion", just[nid])
    # planted faulty inference step(s)
    depth = {p: 0 for p in premises}
    for nid in order:
        depth[nid] = 1 + min(max(depth[a] for a in j) for j in just[nid])
    children = {}
    for nid in order:
        for a in parents[nid]:
            children.setdefault(a, set()).add(nid)

    def desc(x):
        out, stack = set(), [x]
        while stack:
            for c in children.get(stack.pop(), ()):
                if c not in out:
                    out.add(c); stack.append(c)
        return out

    def anc(x):
        out, stack = set(), [x]
        while stack:
            for a in parents.get(stack.pop(), ()):
                if a not in out:
                    out.add(a); stack.append(a)
        return out

    by_depth = {}
    for m in main:
        by_depth.setdefault(depth[m], []).append(m)
    d0 = rng.choice(sorted(by_depth))
    faults = [rng.choice(by_depth[d0])]
    if scenario == "two_faults":
        cand = [m for m in main if m not in desc(faults[0]) and m not in anc(faults[0]) and m != faults[0]]
        if cand:
            faults.append(rng.choice(cand))
    fault_steps = {"rule:" + f for f in faults}
    truth = {p: True for p in premises}
    for nid in order:
        truth[nid] = ("rule:" + nid) not in fault_steps and any(all(truth[a] for a in j) for j in just[nid])
    false_nodes = [n for n in order if not truth[n]]
    true_derived = [n for n in order if truth[n]]
    witnesses, wrong = [], set()
    det = 0.9 if scenario == "noisy" else BR.DEFAULT_DETECTOR

    def contradict(target, faulty=False):
        w = "w%d" % len(witnesses)
        witnesses.append(w)
        g.source(w, "gloria" if rng.random() < 0.5 else "observation", age_days=rng.uniform(0, 5))
        if faulty:
            wrong.add(w)
        g.conflict("c:%s:%s" % (target, w), [target, w], reliability=det, kind="wrong_witness" if faulty else "witness")

    for n in false_nodes:
        if rng.random() < 0.4:
            contradict(n)
    for f in faults:                                                     # every fault shows itself at least once
        mine = [n for n in false_nodes if n == f or n in desc(f)]
        hit = {n for c in g.conflicts for n in c["nodes"]}
        if mine and not hit & set(mine):
            contradict(max(mine, key=lambda n: (depth[n], n)))
    # checks: valid conclusions get used and work out; side-branch leaves are checked most
    acc = 0.85 if scenario == "noisy" else 0.9
    for n in true_derived:
        leaf = not children.get(n)
        if rng.random() < (0.6 if leaf and not n.startswith("m") else 0.3):
            g.confirm(n, accuracy=acc)
    if scenario == "noisy":
        if false_nodes and rng.random() < 0.3:
            g.confirm(rng.choice(false_nodes), accuracy=acc)                 # a check that wrongly passed
        if true_derived and rng.random() < 0.5:
            contradict(rng.choice(true_derived), faulty=True)                # a wrong witness
    T = {"scenario": scenario, "seed": seed, "faults": set(faults), "fault_steps": fault_steps, "truth": truth, "order": order, "premises": premises,
         "depth": depth, "witnesses": witnesses, "wrong_witnesses": wrong, "anc": anc, "desc": desc}
    return g, T


# -- methods -------------------------------------------------------------------------------------------
def _contradicted(c, T):
    return next((n for n in c["nodes"] if n in T["truth"] and n not in T["premises"]), None)


def tms(g, T):
    p = BR.plan(g, at="bench")
    top = {c["conflict"]: (c["blame"][0][0] if c["blame"] else None) for c in p["conflicts"]}
    changed = {r["node"] for r in p["revisions"] if r["action"] in ("retract", "lower")}
    recomputed = {r["node"] for r in p["rederive"]}
    withdrawn = {r["node"] for r in p["rederive"] if r["action"] == "withdraw"}
    return {"top": top, "changed": changed, "recomputed": recomputed, "withdrawn": withdrawn}


def _from_plan(p):
    return {"top": {c["conflict"]: (c["blame"][0][0] if c["blame"] else None) for c in p["conflicts"]},
            "changed": {r["node"] for r in p["revisions"] if r["action"] in ("retract", "lower")},
            "recomputed": {r["node"] for r in p["rederive"]},
            "withdrawn": {r["node"] for r in p["rederive"] if r["action"] == "withdraw"}}


def tms_checks(g, T, budget=12):
    """The module asking checks where the evidence cannot localize; answers come from the truth, flipped with
    the scenario's check noise."""
    acc = 0.85 if T.get("scenario") == "noisy" else 0.9
    rng = random.Random("answers:%s" % T.get("seed"))
    def ask(node):
        if node not in T["truth"]:
            return None
        ans = T["truth"][node]
        return ans if rng.random() < acc else (not ans)
    g2 = copy.deepcopy(g)
    p = BR.localize(g2, ask, budget=budget, accuracy=acc, at="bench")
    out = _from_plan(p)
    out["asked"] = len(p["asked"])
    return out


def last_step(g, T):
    """Blame the step that produced the contradicted belief; recompute what depends on it."""
    top, changed = {}, set()
    for c in g.conflicts:
        n = _contradicted(c, T)
        if n:
            top[c["id"]] = "rule:" + n
            changed.add("rule:" + n)
    rec = {d for d in T["order"] if g.envs(d) and all(e & changed for e in g.envs(d))}
    return {"top": top, "changed": changed, "recomputed": rec, "withdrawn": rec}


METHODS = {"tms_bayes": tms_checks, "tms_passive": tms, "last_step": last_step}


def score(g, T, out):
    s = {k: 0 for k in ("loc_n", "loc_hit", "dep", "rec", "rec_tp", "concl_n", "concl_ok", "pres_n", "pres_ok",
                        "side_n", "side_ok", "up_n", "up_ok")}
    for c in g.conflicts:
        n = _contradicted(c, T)
        if not n or c["kind"] != "witness":
            continue
        steps = [f for f in T["faults"] if f == n or f in T["anc"](n)]
        if not steps:
            continue
        target = "rule:" + min(steps, key=lambda f: (T["depth"][f], f))       # the earliest faulty inference
        s["loc_n"] += 1
        s["loc_hit"] += int(out["top"].get(c["id"]) == target)
    dependent = {n for n in T["order"] if not T["truth"][n]}
    s["dep"], s["rec"] = len(dependent), len(out["recomputed"])
    s["rec_tp"] = len(dependent & out["recomputed"])
    for n in T["order"]:
        held = n not in out["withdrawn"]
        s["concl_n"] += 1
        s["concl_ok"] += int(held == T["truth"][n])
    downstream = set().union(*(T["desc"](f) | {f} for f in T["faults"]))
    upstream = set().union(*(T["anc"](f) for f in T["faults"]))
    for n in T["order"] + T["premises"]:
        if not T["truth"][n] or n in downstream:
            continue
        unchanged = n not in out["recomputed"] and n not in out["changed"] and ("rule:" + n) not in out["changed"]
        s["pres_n"] += 1; s["pres_ok"] += int(unchanged)
        key = "up" if n in upstream else "side"
        s[key + "_n"] += 1; s[key + "_ok"] += int(unchanged)
    return s


def run(split):
    agg = {}
    for sc in SCENARIOS:
        for seed in SPLITS[split]:
            g, T = network(sc, seed)
            for m, fn in METHODS.items():
                out = fn(g, T)
                s = score(g, T, out)
                s["asked"] = out.get("asked", 0)
                for key in (sc, "all"):
                    a = agg.setdefault(m, {}).setdefault(key, {})
                    for k, v in s.items():
                        a[k] = a.get(k, 0) + v
                    a["networks"] = a.get("networks", 0) + 1
    r = lambda x, y: round(x / y, 4) if y else None
    return {m: {key: {"localization": r(a["loc_hit"], a["loc_n"]), "revision_precision": r(a["rec_tp"], a["rec"]),
                      "revision_recall": r(a["rec_tp"], a["dep"]), "conclusions_correct": r(a["concl_ok"], a["concl_n"]),
                      "preservation": r(a["pres_ok"], a["pres_n"]), "preservation_side": r(a["side_ok"], a["side_n"]),
                      "preservation_upstream": r(a["up_ok"], a["up_n"]), "contradictions": a["loc_n"],
                      "checks_per_network": r(a["asked"], a["networks"]),
                      "networks": a["networks"]} for key, a in by.items()} for m, by in agg.items()}


BARS = {"localization": 0.80, "localization_margin": 0.20, "revision_precision": 0.90, "revision_recall": 0.90,
        "conclusions_correct": 0.95, "preservation": 0.98, "preservation_side": 1.0}


def verdict(res):
    t, b = res["tms_bayes"]["all"], res["last_step"]["all"]
    return {"localization": t["localization"] >= BARS["localization"],
            "localization_margin": t["localization"] - b["localization"] >= BARS["localization_margin"],
            "revision_precision": t["revision_precision"] >= BARS["revision_precision"],
            "revision_recall": t["revision_recall"] >= BARS["revision_recall"],
            "conclusions_correct": t["conclusions_correct"] >= BARS["conclusions_correct"],
            "preservation": t["preservation"] >= BARS["preservation"],
            "preservation_side": t["preservation_side"] >= BARS["preservation_side"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=sorted(SPLITS), required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.split == "test" and (os.path.exists(a.out) or os.path.exists(TEST_RESULT)):
        sys.exit("the held-out split is scored once; a test result already exists")
    res = run(a.split)
    doc = {"split": a.split, "results": res, "bars": BARS, "pass": verdict(res)}
    with open(a.out, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    for m in res:
        for key in ("all",) + SCENARIOS:
            x = res[m][key]
            print("%-11s %-10s loc=%s recP=%s recR=%s concl=%s pres=%s side=%s up=%s n=%s checks=%s" % (
                m, key, x["localization"], x["revision_precision"], x["revision_recall"], x["conclusions_correct"],
                x["preservation"], x["preservation_side"], x["preservation_upstream"], x["contradictions"],
                x["checks_per_network"]))
    print("pass:", doc["pass"])


if __name__ == "__main__":
    main()
