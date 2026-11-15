#!/usr/bin/env python3
"""belief_revision_verify.py - an exact check on what belief_revision proposes: does the revision leave a
contradiction standing, does it break a belief that a check passed, and is there a cheaper consistent repair?

belief_revision localizes the culprit by posterior blame, then lowers or retracts. It never searches for the
globally minimal repair. The energy-repair experiment (experiments/energy-repair/, 14 November 2026) found that on
the same evidence its plans left a contradiction standing in 30% of development networks and were costlier than
the exact minimum in 25% (40% on large ones). This module only REPORTS that; it changes nothing and decides
nothing.

Energy of a repair R (a set of retracted or lowered sources): sum of log((1-p)/p) over R (p = the source's prior
chance of being wrong), plus -log(1-r) for every contradiction left standing (r = its reliability), plus
log(acc/(1-acc)) for every passed check whose belief no longer holds. That is minus the log of belief_revision's
own joint probability, so the minimum is the most probable explanation. Beliefs are recomputed as the least
fixpoint of their justifications (a loop cannot hold itself up).

The minimum is found exactly by integer programming (scipy.optimize.milp / HiGHS) when scipy is importable;
otherwise only the standing contradictions and broken checks are reported.
"""
import math, time

SOLVER_SECONDS = 20.0
TIE = 1e-6                 # equal repairs go to the earlier source


def _parts(g):
    g.envs(next(iter(g.nodes))) if g.nodes else None          # fills gaps and depth
    A = sorted(a for a, n in g.nodes.items() if n["assumption"])
    D = sorted(a for a, n in g.nodes.items() if not n["assumption"])
    w = {a: math.log((1 - g.nodes[a]["prior"]) / g.nodes[a]["prior"]) for a in A}
    J = {v: [list(j) for j in g.nodes[v]["justifications"]] for v in D}
    C = [(c["id"], list(c["nodes"]), -math.log(max(1e-9, 1 - c["reliability"]))) for c in g.conflicts]
    K = [(c["node"], math.log(c["accuracy"] / (1 - c["accuracy"]))) for c in g.confirmations]
    return A, D, w, J, C, K


def holds(g, retracted):
    """Which nodes hold once `retracted` sources are taken away: the least fixpoint."""
    A, D, _, J, _, _ = _parts(g)
    h = {a: a not in retracted for a in A}
    h.update({v: False for v in D})
    changed = True
    while changed:
        changed = False
        for v in D:
            if not h[v] and any(all(h[a] for a in j) for j in J[v]):
                h[v] = changed = True
    return h


def energy(g, retracted):
    A, D, w, J, C, K = _parts(g)
    h = holds(g, retracted)
    return (sum(w[a] for a in retracted if a in w) + sum(W for _, ns, W in C if all(h[n] for n in ns))
            + sum(U for n, U in K if not h[n]))


def _cyclic(D, J):
    deps = {v: {a for j in J[v] for a in j if a in J} for v in D}
    state = {}

    def visit(v):
        state[v] = 1
        for u in deps[v]:
            if state.get(u) == 1 or (u not in state and visit(u)):
                return True
        state[v] = 2
        return False
    return any(v not in state and visit(v) for v in D)


def minimum(g, time_limit=SOLVER_SECONDS):
    """(repair, energy) of the exact minimum, or (None, None) when scipy is not available or the solver fails."""
    try:
        import numpy as np
        from scipy.optimize import milp, LinearConstraint, Bounds
        from scipy.sparse import lil_matrix
    except ImportError:
        return None, None
    A, D, w, J, C, K = _parts(g)
    depth = getattr(g, "depth", {}) or {}
    cyc = _cyclic(D, J)
    idx, cost, hi, integ = {}, [], [], []

    def var(k, c=0.0, u=1.0, integer=True):
        idx[k] = len(cost); cost.append(c); hi.append(u); integ.append(1 if integer else 0)
    for a in A:
        var(("f", a), w[a] + TIE * (1 + depth.get(a, 0)))
    for v in D:
        var(("h", v))
        for k in range(len(J[v])):
            var(("y", v, k))
            if cyc:
                var(("s", v, k))
        if cyc:
            var(("r", v), 0.0, float(len(D) + 1), integer=False)
    for i, (_, _, W) in enumerate(C):
        var(("viol", i), W)
    for i, (_, U) in enumerate(K):
        var(("fail", i), U)
    rows = []

    def hold(n):                                   # 'n holds' as (coeffs, constant)
        return ({idx[("h", n)]: 1.0}, 0.0) if n in J else ({idx[("f", n)]: -1.0}, 1.0)

    def row(terms, const, lb=-np.inf, ub=np.inf):
        d = {}
        for coeffs, s in terms:
            for k, x in coeffs.items():
                d[k] = d.get(k, 0.0) + s * x
        rows.append((d, lb - const, ub - const))
    M = float(len(D) + 2)
    for v in D:
        hv = {idx[("h", v)]: 1.0}
        sup = []
        for k, j in enumerate(J[v]):
            y = {idx[("y", v, k)]: 1.0}
            parts, consts = [], 0.0
            for a in j:
                c, k0 = hold(a)
                parts.append(c); consts += k0
                row([(y, 1.0), (c, -1.0)], -k0, ub=0.0)
            row([(y, 1.0)] + [(c, -1.0) for c in parts], -consts + len(j) - 1, lb=0.0)
            row([(hv, 1.0), (y, -1.0)], 0.0, lb=0.0)
            if cyc:
                s = {idx[("s", v, k)]: 1.0}
                row([(s, 1.0), (y, -1.0)], 0.0, ub=0.0)
                for a in j:
                    if a in J:
                        row([({idx[("r", v)]: 1.0}, 1.0), ({idx[("r", a)]: 1.0}, -1.0), (s, -M)], 0.0, lb=1.0 - M)
                sup.append(s)
            else:
                sup.append(y)
        row([(hv, 1.0)] + [(s, -1.0) for s in sup], 0.0, ub=0.0)
    for i, (_, ns, _) in enumerate(C):
        parts, consts = [], 0.0
        for n in ns:
            c, k0 = hold(n)
            parts.append(c); consts += k0
        row([({idx[("viol", i)]: 1.0}, 1.0)] + [(c, -1.0) for c in parts], -consts + len(ns) - 1, lb=0.0)
    for i, (n, _) in enumerate(K):
        c, k0 = hold(n)
        row([({idx[("fail", i)]: 1.0}, 1.0), (c, 1.0)], k0, lb=1.0)
    if not rows:
        return set(), 0.0
    mat = lil_matrix((len(rows), len(cost)))
    for r, (d, _, _) in enumerate(rows):
        for k, x in d.items():
            mat[r, k] = x
    try:
        res = milp(c=np.array(cost), constraints=[LinearConstraint(mat.tocsr(), np.array([r[1] for r in rows]),
                                                                   np.array([r[2] for r in rows]))],
                   bounds=Bounds(np.zeros(len(cost)), np.array(hi)), integrality=np.array(integ),
                   options={"time_limit": time_limit, "disp": False})
    except Exception:
        return None, None
    if res.x is None or res.status != 0:
        return None, None
    R = {a for a in A if res.x[idx[("f", a)]] > 0.5}
    return R, energy(g, R)


def verify(g, p, exact=True):
    """What the plan's revisions (retract and lower) would leave: contradictions still standing, passed checks now
    broken, the plan's energy, and - when the solver is available - the exact minimum and how far the plan is from
    it. Ids and numbers only."""
    t0 = time.perf_counter()
    R = {r["node"] for r in p.get("revisions", []) if r.get("action") in ("retract", "lower")}
    h = holds(g, R)
    out = {"revised": len(R),
           "standing": sorted(c["id"] for c in g.conflicts if all(h.get(n, True) for n in c["nodes"])),
           "broken_checks": sorted({c["node"] for c in g.confirmations if not h.get(c["node"], True)}),
           "energy": round(energy(g, R), 4), "solver": "not run"}
    if exact:
        Rm, Em = minimum(g)
        if Rm is None:
            out["solver"] = "unavailable"
        else:
            out.update(solver="exact", optimum=round(Em, 4), gap=round(max(0.0, out["energy"] - Em), 4),
                       minimal=out["energy"] <= Em + 1e-6, optimum_size=len(Rm),
                       optimum_differs=sorted(Rm ^ R))
    out["seconds"] = round(time.perf_counter() - t0, 3)
    return out
