#!/usr/bin/env python3
"""Networks for the energy-repair experiment. Synthetic only (the repository is public).

The four scenarios of the contradiction back-propagation benchmark come from bench_criteria.network() unchanged.
The rest come from one parameterized generator built the same way (premises, a main structure with planted faults,
side branches, independent side chains, contradictions from her or an observation, passed checks):

  Chat's cases (small, same size as the original benchmark)
    early_premise  a recorded source (not hers) is wrong and several conclusions on different lines show it;
                   the cheapest repair is usually to retract that one early premise rather than several late steps
    ambiguous      evidence that pulls both ways: weak contradiction reports (0.75), a check that wrongly passed a
                   false conclusion, a wrong witness against a true one
    multi_repair   two lines of the same make meet in a contradiction: two repairs cost the same

  Generalization (LARGER and differently built; never used to train anything)
    deep           chains of 10-20 steps, dags of 8-12 layers
    wide           layers 4-7 wide, justifications joining 2-4 antecedents, many alternative justifications
    cycles         a dag plus back-edges: later conclusions offered as alternative justifications of earlier
                   ones (mutual support loops), which cannot hold themselves up
    large_mixed    deep and wide together, two or three faults (steps or premises), noisy evidence

Every network comes with the truth: which assumptions are really wrong (T["bad"]), every node's real standing, and
for each planted fault its id ("rule:x" for a step, the premise id for a premise).
"""
import math, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "experiments", "contradiction-backprop"))
import belief_revision as BR
import bench_criteria as BC

BASE = ("chain", "dag", "noisy", "two_faults")
CHAT = ("early_premise", "ambiguous", "multi_repair")
LARGE = ("deep", "wide", "cycles", "large_mixed")
SMALL = BASE + CHAT
ALL = SMALL + LARGE
NONHER = ("observation", "memory", "lesson", "private_record")

CFG = {
    "early_premise": dict(layers=(3, 5), width=(2, 3), fanin=2, alt_p=0.15, faults=0, premise_faults=1, min_hits=3),
    "ambiguous": dict(layers=(3, 5), width=(2, 3), fanin=2, alt_p=0.2, faults=1, det=0.75, acc=0.8,
                      false_pass=0.8, wrong_witness=0.8),
    "multi_repair": dict(layers=(2, 4), width=(2, 3), fanin=2, alt_p=0.0, faults=1, twin=True),
    "deep": dict(layers=(10, 16), width=(2, 3), fanin=2, alt_p=0.2, faults=1, chain_p=0.4, chain=(12, 25)),
    "wide": dict(layers=(4, 6), width=(5, 8), fanin=4, alt_p=0.45, faults=1),
    "cycles": dict(layers=(5, 9), width=(3, 4), fanin=2, alt_p=0.2, faults=1, cycle_p=0.35),
    "large_mixed": dict(layers=(8, 12), width=(3, 6), fanin=3, alt_p=0.3, faults=2, premise_faults=1, det=0.9,
                        acc=0.85, false_pass=0.3, wrong_witness=0.5, premises=(6, 10)),
}


def network(scenario, seed):
    if scenario in BASE:
        g, T = BC.network(scenario, seed)
        bad = set(T["fault_steps"])
        T = dict(T, bad=bad | set(T["wrong_witnesses"]), fault_ids={f: "rule:" + f for f in T["faults"]})
        return g, T
    return _network(scenario, seed, CFG[scenario])


def _network(scenario, seed, c):
    rng = random.Random("energy:%s:%d" % (scenario, seed))
    g = BR.Graph()
    just, parents, main = {}, {}, []
    premises = []
    for i in range(rng.randint(*c.get("premises", (3, 6)))):
        p = "p%d" % i
        premises.append(p)
        kind = rng.choice(NONHER) if (c.get("twin") or c.get("min_hits")) else rng.choice(BC.PREMISE_KINDS)
        g.source(p, kind, evidence_count=BC._poisson(rng, 3.0), age_days=rng.uniform(0, 200))

    def add(nid, js):
        just[nid] = js
        parents[nid] = sorted({a for j in js for a in j})

    if c.get("chain") and rng.random() < c.get("chain_p", 0):
        prev = premises[0]
        for i in range(1, rng.randint(*c["chain"]) + 1):
            j = [prev] + ([rng.choice(premises)] if rng.random() < 0.3 else [])
            add("m%d" % i, [sorted(set(j))])
            main.append("m%d" % i)
            prev = "m%d" % i
        layers = [premises[:]] + [[m] for m in main]
    else:
        layers = [premises[:]]
        for L in range(1, rng.randint(*c["layers"]) + 1):
            layer = []
            for w in range(rng.randint(*c["width"])):
                nid = "m%d_%d" % (L, w)
                pool_prev, pool_all = layers[-1], [x for lay in layers for x in lay]
                k = rng.randint(1, c["fanin"])
                ants = {rng.choice(pool_prev)} | {rng.choice(pool_all) for _ in range(k - 1)}
                js = [sorted(ants)]
                if rng.random() < c["alt_p"]:
                    alt = sorted({rng.choice(pool_all) for _ in range(rng.randint(1, max(1, c["fanin"] - 1)))})
                    if alt not in js:
                        js.append(alt)
                add(nid, js)
                layer.append(nid)
                main.append(nid)
            layers.append(layer)
    if c.get("twin"):
        # two lines of the same make, from two premises of the same kind and standing, meeting in a contradiction
        kind = rng.choice(NONHER)
        ev, age = BC._poisson(rng, 3.0), rng.uniform(0, 200)
        for t in ("ta", "tb"):
            g.source(t + "0", kind, evidence_count=ev, age_days=age)
            premises.append(t + "0")
            prev = t + "0"
            for i in range(1, c.get("twin_len", rng.randint(1, 3)) + 1):
                add("%s%d" % (t, i), [[prev]])
                main.append("%s%d" % (t, i))
                prev = "%s%d" % (t, i)
            c = dict(c, twin_len=i)
    k = 0
    for _ in range(rng.randint(1, 3)):
        prev = rng.choice(main + premises)
        for _ in range(rng.randint(1, 3)):
            nid = "b%d" % k; k += 1
            add(nid, [[prev]])
            prev = nid
    for ci in range(rng.randint(1, 2)):
        p = "q%d" % ci
        g.source(p, rng.choice(BC.PREMISE_KINDS), evidence_count=BC._poisson(rng, 3.0), age_days=rng.uniform(0, 200))
        premises.append(p)
        prev = p
        for _ in range(rng.randint(2, 3)):
            nid = "s%d" % k; k += 1
            add(nid, [[prev]])
            prev = nid
    order = list(main) + sorted((n for n in just if n not in main), key=lambda n: int(n[1:]))
    # depth when everything is sound (the stage at which a node is first derived)
    depth = {p: 0 for p in premises}
    pending = list(order)
    while pending:
        rest = []
        for nid in pending:
            ds = [max(depth[a] for a in j) for j in just[nid] if all(a in depth for a in j)]
            if ds:
                depth[nid] = 1 + min(ds)
            else:
                rest.append(nid)
        if len(rest) == len(pending):
            raise RuntimeError("underivable node")
        pending = rest
    if c.get("cycle_p"):
        # back-edges: a later main conclusion offered as an alternative justification of an earlier one
        for nid in main:
            later = [m for m in main if depth[m] > depth[nid] + 1]
            if later and rng.random() < c["cycle_p"]:
                alt = [rng.choice(later)]
                if alt not in just[nid]:
                    add(nid, just[nid] + [alt])
    for nid in order:
        g.derived(nid, "conclusion", just[nid])
    children = {}
    for nid in order:
        for a in parents[nid]:
            children.setdefault(a, set()).add(nid)

    def closure(x, edges):
        out, stack = set(), [x]
        while stack:
            for y in edges.get(stack.pop(), ()):
                if y not in out:
                    out.add(y); stack.append(y)
        return out
    desc = lambda x: closure(x, children)
    anc = lambda x: closure(x, parents)

    # planted faults: inference steps on the main structure, and/or a recorded premise (never hers)
    faults = []
    by_depth = {}
    for m in main:
        if not m.startswith("t"):
            by_depth.setdefault(depth[m], []).append(m)
    for _ in range(c.get("faults", 1)):
        for _try in range(20):
            d0 = rng.choice(sorted(by_depth))
            f = rng.choice(by_depth[d0])
            if all(f not in desc(x) and x not in desc(f) and f != x for x in faults):
                faults.append(f)
                break
    if c.get("twin"):
        faults = [rng.choice(["ta1", "tb1"])]                 # one of the two twin lines is really wrong
    premise_faults = []
    for _ in range(c.get("premise_faults", 0)):
        used = [p for p in premises if p.startswith("p") and g.nodes[p]["kind"] != "gloria"
                and len([d for d in desc(p) if d in main]) >= 2 and p not in premise_faults]
        if used:
            premise_faults.append(max(used, key=lambda p: (len(desc(p)), p)) if c.get("min_hits") else rng.choice(used))
    fault_ids = {f: "rule:" + f for f in faults}
    fault_ids.update({p: p for p in premise_faults})
    bad = set(fault_ids.values())
    truth = {p: p not in bad for p in premises}
    for nid in order:
        truth[nid] = False
    changed = True
    while changed:
        changed = False
        for nid in order:
            if not truth[nid] and ("rule:" + nid) not in bad and any(all(truth[a] for a in j) for j in just[nid]):
                truth[nid] = changed = True
    false_nodes = [n for n in order if not truth[n]]
    true_derived = [n for n in order if truth[n]]
    witnesses, wrong = [], set()
    det = c.get("det", BR.DEFAULT_DETECTOR)

    def contradict(target, faulty=False):
        w = "w%d" % len(witnesses)
        witnesses.append(w)
        g.source(w, "gloria" if rng.random() < 0.5 else "observation", age_days=rng.uniform(0, 5))
        if faulty:
            wrong.add(w)
        g.conflict("c:%s:%s" % (target, w), [target, w], reliability=det, kind="wrong_witness" if faulty else "witness")

    if c.get("twin"):
        # the two twin conclusions contradict each other directly: one must go, and the record cannot say which
        a, b = "ta%d" % c["twin_len"], "tb%d" % c["twin_len"]
        g.conflict("c:%s:%s" % (a, b), [a, b], reliability=det, kind="witness")
    else:
        for n in false_nodes:
            if rng.random() < 0.4:
                contradict(n)
        for f in list(fault_ids):
            mine = [n for n in false_nodes if n == f or n in desc(f)]
            hit = {n for cc in g.conflicts for n in cc["nodes"]}
            if mine and not hit & set(mine):
                contradict(max(mine, key=lambda n: (depth[n], n)))
        if c.get("min_hits"):
            # the wrong premise shows itself on several different lines
            for f in premise_faults:
                mine = [n for n in false_nodes if n in desc(f)]
                hit = {n for cc in g.conflicts for n in cc["nodes"]}
                for n in rng.sample(mine, len(mine)):
                    if len(hit & set(mine)) >= c["min_hits"]:
                        break
                    if n not in hit:
                        contradict(n); hit.add(n)
    acc = c.get("acc", 0.9)
    for n in true_derived:
        leaf = not children.get(n)
        if rng.random() < (0.6 if leaf and not n.startswith("m") else 0.3):
            g.confirm(n, accuracy=acc)
    if c.get("false_pass") and false_nodes and rng.random() < c["false_pass"]:
        g.confirm(rng.choice(false_nodes), accuracy=acc)          # a check that wrongly passed
    if c.get("wrong_witness") and true_derived and rng.random() < c["wrong_witness"]:
        contradict(rng.choice(true_derived), faulty=True)          # a wrong witness
    bad |= wrong
    T = {"scenario": scenario, "seed": seed, "faults": set(fault_ids), "fault_ids": fault_ids, "bad": bad,
         "fault_steps": {v for v in fault_ids.values() if v.startswith("rule:")}, "premise_faults": set(premise_faults),
         "truth": truth, "order": order, "premises": premises, "depth": depth, "witnesses": witnesses,
         "wrong_witnesses": wrong, "anc": anc, "desc": desc}
    return g, T


def size(g):
    return {"nodes": len(g.nodes), "conflicts": len(g.conflicts), "confirms": len(g.confirmations)}


if __name__ == "__main__":
    import statistics as st
    for sc in ALL:
        ns = [network(sc, s) for s in range(20)]
        print("%-13s nodes=%5.1f conflicts=%4.1f bad=%3.1f" % (
            sc, st.mean(len(g.nodes) for g, _ in ns), st.mean(len(g.conflicts) for g, _ in ns),
            st.mean(len(T["bad"]) for _, T in ns)))
