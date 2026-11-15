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

choose() is the one exception to "reports only": Gloria approved the exact solver as the repair chooser for the live
nightly run, on trial (14 November 2026: "keep my words unchanged, preserve a reversible history while in testing
(1 week...), and the normal regression gate"). It returns a plan in belief_revision.plan()'s own shape, built from
the minimum over what belief_revision may revise - her words are a hard constraint (never in the repair; only ever
flagged) - and it still writes nothing: belief_revision_live applies it under every live limit, behind
BELIEF_REVISION_SOLVER=exact.
"""
import math, time

SOLVER_SECONDS = 20.0
TIE = 1e-4                 # equal repairs go to the earlier source (far below any real weight difference)


def _parts(g):
    if g._labels is None:
        g._compute()                                              # fills gaps and depth
    A = sorted(a for a, n in g.nodes.items() if n["assumption"])
    D = sorted(a for a, n in g.nodes.items() if not n["assumption"])
    w = {a: math.log((1 - g.nodes[a]["prior"]) / g.nodes[a]["prior"]) for a in A}
    J = {v: [list(j) for j in g.nodes[v]["justifications"]] for v in D}
    C = [(c["id"], list(c["nodes"]), -math.log(max(1e-9, 1 - c["reliability"]))) for c in g.conflicts]
    acc = lambda a: min(max(float(a), 0.5), 1 - 1e-9)             # a check below even odds is no evidence
    K = [(c["node"], math.log(acc(c["accuracy"]) / (1 - acc(c["accuracy"])))) for c in g.confirmations]
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


def revisable(g, a):
    """What belief_revision itself may revise: never her words, never a source that is not captured."""
    n = g.nodes[a]
    return n["kind"] != "gloria" and n.get("captured", True)


def minimum(g, time_limit=SOLVER_SECONDS, policy=False, keep=()):
    """(repair, energy, status) of the exact minimum. policy=True: only what belief_revision may revise (not her
    words, not uncaptured sources). keep: further sources the repair may not contain. status is "exact",
    "time_limit" (the repair is the best found, an upper bound), "unavailable" (no scipy) or "error"."""
    try:
        import numpy as np
        from scipy.optimize import milp, LinearConstraint, Bounds
        from scipy.sparse import lil_matrix
    except ImportError:
        return None, None, "unavailable"
    try:
        return _minimum(g, time_limit, policy, np, milp, LinearConstraint, Bounds, lil_matrix, set(keep))
    except Exception:
        return None, None, "error"


def _minimum(g, time_limit, policy, np, milp, LinearConstraint, Bounds, lil_matrix, keep=frozenset()):
    A, D, w, J, C, K = _parts(g)
    depth = getattr(g, "depth", {}) or {}
    cyc = _cyclic(D, J)
    idx, cost, hi, integ = {}, [], [], []

    def var(k, c=0.0, u=1.0, integer=True):
        idx[k] = len(cost); cost.append(c); hi.append(u); integ.append(1 if integer else 0)
    for a in A:
        var(("f", a), w[a] + TIE * (1 + depth.get(a, 0)), 0.0 if policy and not revisable(g, a) else 0.0 if a in keep else 1.0)
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
        row([({idx[("fail", i)]: 1.0}, 1.0), (c, 1.0)], k0, lb=1.0, ub=1.0)    # fail is exactly 1 - hold
    if not rows:
        return set(), 0.0, "exact"
    mat = lil_matrix((len(rows), len(cost)))
    for r, (d, _, _) in enumerate(rows):
        for k, x in d.items():
            mat[r, k] = x
    res = milp(c=np.array(cost), constraints=[LinearConstraint(mat.tocsr(), np.array([r[1] for r in rows]),
                                                                   np.array([r[2] for r in rows]))],
                   bounds=Bounds(np.zeros(len(cost)), np.array(hi)), integrality=np.array(integ),
                   options={"time_limit": time_limit, "disp": False, "mip_rel_gap": 0.0})
    if res.x is None:
        return None, None, "error" if res.status != 1 else "time_limit"
    R = {a for a in A if res.x[idx[("f", a)]] > 0.5}
    return R, energy(g, R), "exact" if res.status == 0 else "time_limit"


def verify(g, p, exact=True):
    """What the plan's revisions would leave: contradictions still standing, passed checks now broken (a lowered
    source is counted as dropped, the way plan() itself recomputes dependents), the plan's energy, and - when the
    solver is available - the exact minimum and the plan's gap to it, both over everything (`optimum`) and over what
    belief_revision may revise (`optimum_policy`: never her words, never an uncaptured source). Ids and numbers."""
    t0 = time.perf_counter()
    R = {r["node"] for r in p.get("revisions", []) if r.get("action") in ("retract", "lower")}
    h = holds(g, R)
    out = {"revised": len(R),
           "standing": sorted(c["id"] for c in g.conflicts if all(h.get(n, True) for n in c["nodes"])),
           "broken_checks": sorted({c["node"] for c in g.confirmations if not h.get(c["node"], True)}),
           "energy": round(energy(g, R), 4), "solver": "not run"}
    if exact:
        for key, pol in (("", False), ("_policy", True)):
            Rm, Em, status = minimum(g, policy=pol)
            out["solver" + key] = status
            if Rm is None:
                continue
            out.update({"optimum" + key: round(Em, 4), "gap" + key: round(max(0.0, out["energy"] - Em), 4),
                        "minimal" + key: (out["energy"] <= Em + 1e-6) if status == "exact" else None})
            if not key:
                out.update(optimum_size=len(Rm), optimum_differs=sorted(Rm ^ R))
    out["seconds"] = round(time.perf_counter() - t0, 3)
    return out


def choose(g, p, time_limit=SOLVER_SECONDS, may_revise=None, held_mode="flag"):
    """The exact solver as the repair chooser. g: the graph AFTER the check questions were asked (localize adds the
    answers to it); p: belief_revision's own final plan on that graph (its posterior, its check answers and its
    flags are reused). may_revise: a test of whether the caller can actually apply a revision of a source (live:
    target() accepts it); a source it refuses is kept out of the repair, so the minimum is over what will really be
    done. Returns (plan, status): a plan in plan()'s shape whose retract/lower set is the policy-constrained minimum,
    or (None, status) when no proved minimum is available ("time_limit", "unavailable", "error", "policy") - the
    caller then keeps belief_revision's own plan.

      * her words are never in the repair: bound to 0 in the program, and refused here again if a solver ever
        returned one. They are flagged for her: those plan() flagged, and those the unconstrained minimum gives up
        with blame FLAG_AT or more;
      * what plan() held back (a revision resting on a single check answer, or a weak suspect of a contradiction
        whose question went unanswered) is kept out of the repair and stays held - the live limit stands;
      * revisions: each source in the minimum, retracted when its posterior blame is RETRACT_AT or more, otherwise
        lowered in proportion to it - as plan() does;
      * plan()'s other flags (not captured, self-model, held) are kept for sources the minimum does not revise;
      * rederive: as plan() does it - only beliefs every justification of which passes through a revised source,
        lowered in proportion to their standing, withdrawn when it halves;
      * conflicts: plan()'s, with the minimum's members of each contradiction first (earliest first)."""
    import belief_revision as BR
    held = set(p.get("held") or ())
    A = [a for a, n in g.nodes.items() if n["assumption"]]
    keep = {a for a in A if may_revise is not None and revisable(g, a) and not may_revise(a)}
    if held_mode == "bound":
        keep |= held
    Rm, Em, status = minimum(g, time_limit, policy=True, keep=keep)
    if status != "exact" or Rm is None:
        return None, status
    if any(not revisable(g, a) or a in keep for a in Rm):
        return None, "policy"                                  # never: her words are bound to 0 in the program
    if held_mode == "flag":
        Rm = Rm - held
    q = p.get("fault") or {}
    nog = {c["id"]: g.nogoods(c) for c in g.conflicts}
    blamed_in = {}
    for c in g.conflicts:
        for a in sorted(set().union(*nog[c["id"]]) if nog[c["id"]] else []):
            blamed_in.setdefault(a, []).append(c["id"])
    depth = getattr(g, "depth", {}) or {}
    revisions = []
    for a in sorted(Rm):
        n = g.nodes[a]
        qa = float(q.get(a, n["prior"]))
        action = "retract" if qa >= BR.RETRACT_AT else "lower"
        was = n["confidence"]
        would = was if was is None else (0.0 if action == "retract" else round(float(was) * (1.0 - qa), 4))
        revisions.append({"node": a, "kind": n["kind"], "action": action, "reason": "exact minimum",
                          "blame": round(qa, 4), "prior": round(n["prior"], 4), "method": "exact", "explains": True,
                          "confidence_was": was, "confidence_would_be": would, "conflicts": blamed_in.get(a, []),
                          "superseded": {"confidence": was, "standing": "held",
                                         "replaced_by": {"by": "belief_revision_verify.choose", "mode": "exact",
                                                         "at": p.get("at"), "conflicts": blamed_in.get(a, [])}}})
    hers = {r["node"] for r in p.get("revisions", []) if r["action"] == "flag_for_gloria"}
    Ru, _Eu, ustatus = minimum(g, time_limit, policy=False)
    if Ru and ustatus == "exact":
        hers |= {a for a in Ru if g.nodes[a]["kind"] == "gloria" and float(q.get(a, 0.0)) >= BR.FLAG_AT}
    for a in sorted(hers):
        n = g.nodes[a]
        revisions.append({"node": a, "kind": n["kind"], "action": "flag_for_gloria",
                          "reason": "her word is never revised; she decides", "blame": round(float(q.get(a, n["prior"])), 4),
                          "prior": round(n["prior"], 4), "method": "exact", "explains": a in (Ru or ()),
                          "confidence_was": n["confidence"], "confidence_would_be": n["confidence"],
                          "conflicts": blamed_in.get(a, [])})
    for r in p.get("revisions", []):
        if r["node"] not in Rm and r["node"] not in hers and r["action"] not in ("retract", "lower", "flag_for_gloria"):
            revisions.append(dict(r))
        elif r["node"] in held and r["node"] not in Rm and r["node"] not in hers and r["action"] in ("retract", "lower"):
            revisions.append(dict(r, action="flag", reason="rests on a single answer"))
    dependent = sorted(v for v, n in g.nodes.items() if not n["assumption"] and g.envs(v)
                       and all(e & Rm for e in g.envs(v)))
    rederive = []
    if dependent:
        samplers = BR.posterior(g)[4]
        before = BR.standings(g, dependent, None, seed="before")
        after = BR.standings(g, dependent, samplers, seed="after")
        for v in dependent:
            act = "withdraw" if after[v] < 0.5 * before[v] or after[v] < 0.05 else "lower"
            rederive.append({"node": v, "kind": g.nodes[v]["kind"], "action": act,
                             "standing_before": round(before[v], 4), "standing_after": round(after[v], 4),
                             "rests_on_revised": sorted(set().union(*g.envs(v)) & Rm)})
    conflicts = []
    for c in p.get("conflicts", []):
        mine = sorted((a for a in Rm if c["conflict"] in blamed_in.get(a, ())), key=lambda a: (depth.get(a, 0), a))
        rest = [x for x in c["blame"] if x[0] not in mine]
        conflicts.append(dict(c, blame=[[a, round(float(q.get(a, 0.0)), 4)] for a in mine] + rest))
    out = dict(p, conflicts=conflicts, revisions=revisions, rederive=rederive, chooser="exact",
               held=sorted(held - Rm), energy=round(energy(g, Rm), 4), energy_old=round(energy(g, {
                   r["node"] for r in p.get("revisions", []) if r["action"] in ("retract", "lower")}), 4))
    return out, status
