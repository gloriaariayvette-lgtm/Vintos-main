#!/usr/bin/env python3
"""The repair problem shared by every method: a network of sources (assumptions), inference steps, beliefs,
contradictions and checks, read off a belief_revision.Graph, and the energy of a repair.

A REPAIR is a set of assumptions (sources or inference steps) declared wrong. Given a repair, every belief is
recomputed by forward chaining (the least fixpoint, so a cycle cannot hold itself up), and the repair's ENERGY is

    E(R) = sum over retracted assumptions of log((1-p)/p)          (p = its prior chance of being wrong)
         + sum over contradictions left standing of -log(1-r)       (r = how reliable the contradiction report is)
         + sum over passed checks whose belief now fails of log(acc/(1-acc))

which is minus the log of belief_revision's own joint probability (up to a constant), so the minimum-energy repair
is the most probable explanation of all the evidence. A repair is CONSISTENT when no contradiction is left standing.

The exact solver is an integer program solved by HiGHS (scipy.optimize.milp, already installed): exact branch and
bound, with a proof of optimality. Equal-energy repairs are broken toward the earlier assumption (Gloria's
criterion 1), by a tie-break term far smaller than any real weight difference.
"""
import math, time
import numpy as np

TIE = 1e-6          # per depth step: the earlier of two equal repairs wins


class Problem:
    def __init__(self, g):
        g._compute()
        self.g = g
        self.assumptions = sorted(a for a, n in g.nodes.items() if n["assumption"])
        self.derived = sorted(a for a, n in g.nodes.items() if not n["assumption"])
        self.prior = {a: g.nodes[a]["prior"] for a in self.assumptions}
        self.w = {a: math.log((1 - p) / p) for a, p in self.prior.items()}
        self.just = {v: [list(j) for j in g.nodes[v]["justifications"]] for v in self.derived}
        self.conflicts = [(c["id"], list(c["nodes"]), -math.log(max(1e-9, 1 - c["reliability"]))) for c in g.conflicts]
        self.confirms = [(c["node"], math.log(c["accuracy"] / (1 - c["accuracy"]))) for c in g.confirmations]
        self.depth = {a: g.depth.get(a, 0) for a in self.assumptions + self.derived}
        self.cyclic = self._has_cycle()

    def _has_cycle(self):
        state = {}
        for root in self.derived:
            if root in state:
                continue
            stack = [(root, iter({a for j in self.just[root] for a in j if a in self.just}))]
            state[root] = 1
            while stack:
                v, it = stack[-1]
                nxt = next(it, None)
                if nxt is None:
                    state[v] = 2
                    stack.pop()
                elif state.get(nxt) == 1:
                    return True
                elif nxt not in state:
                    state[nxt] = 1
                    stack.append((nxt, iter({a for j in self.just[nxt] for a in j if a in self.just})))
        return False

    # -- a repair's consequences ---------------------------------------------------------------------
    def holds(self, R):
        """Which nodes hold once the assumptions in R are retracted: the least fixpoint of the justifications."""
        h = {a: a not in R for a in self.assumptions}
        for v in self.derived:
            h[v] = False
        changed = True
        while changed:
            changed = False
            for v in self.derived:
                if not h[v] and any(all(h[a] for a in j) for j in self.just[v]):
                    h[v] = True
                    changed = True
        return h

    def energy(self, R, h=None):
        h = h or self.holds(R)
        e = sum(self.w[a] for a in R)
        e += sum(W for _, ns, W in self.conflicts if all(h[n] for n in ns))
        e += sum(U for n, U in self.confirms if not h[n])
        return e

    def standing(self, R, h=None):
        h = h or self.holds(R)
        return [cid for cid, ns, _ in self.conflicts if all(h[n] for n in ns)]

    def verify(self, R):
        """What the exact checker says about a proposed repair: its energy, the contradictions it leaves standing,
        the checks it breaks."""
        h = self.holds(R)
        return {"energy": self.energy(R, h), "standing": self.standing(R, h),
                "broken_checks": [n for n, _ in self.confirms if not h[n]], "holds": h}

    def suspects(self, cid):
        c = next(c for c in self.g.conflicts if c["id"] == cid)
        ng = self.g.nogoods(c)
        return set().union(*ng) if ng else set()


# -- the exact solver -----------------------------------------------------------------------------------
def solve_exact(P, allowed=None, exclude=(), time_limit=60.0, hard=False):
    """The minimum-energy repair, exactly (HiGHS branch and bound). `allowed` restricts which assumptions may be
    retracted (the others are held); `exclude` is a list of repairs to cut off (to enumerate the next optimum).
    hard=True: no contradiction may be left standing (the minimal CONSISTENT repair; a contradiction can still be
    resolved by retracting the witness who reported it, at that witness's cost).
    Returns (repair, energy, info)."""
    from scipy.optimize import milp, LinearConstraint, Bounds
    from scipy.sparse import lil_matrix
    t0 = time.perf_counter()
    idx = {}
    cost, lo, hi, integ = [], [], [], []

    def var(name, c=0.0, l=0.0, u=1.0, integer=True):
        idx[name] = len(cost)
        cost.append(c); lo.append(l); hi.append(u); integ.append(1 if integer else 0)
        return idx[name]

    allowed = set(P.assumptions) if allowed is None else set(allowed)
    for a in P.assumptions:
        var(("f", a), P.w[a] + TIE * (1 + P.depth.get(a, 0)), 0.0, 1.0 if a in allowed else 0.0)
    for v in P.derived:
        var(("h", v))
        for k, _ in enumerate(P.just[v]):
            var(("y", v, k))
            if P.cyclic:
                var(("s", v, k))
        if P.cyclic:
            var(("r", v), 0.0, 0.0, float(len(P.derived) + 1), integer=False)
    for i, (_, _, W) in enumerate(P.conflicts):
        var(("viol", i), W, 0.0, 0.0 if hard else 1.0)
    for i, (_, U) in enumerate(P.confirms):
        var(("fail", i), U)

    rows = []          # (coeffs dict, lb, ub)

    def hold(n):
        """(coeffs, const) for the 0/1 expression 'n holds'."""
        if n in P.just:
            return {idx[("h", n)]: 1.0}, 0.0
        return {idx[("f", n)]: -1.0}, 1.0

    def add(terms, const, lb=-np.inf, ub=np.inf):
        """sum(coef*var) + const in [lb, ub], terms a list of (coeffs, scale)."""
        d = {}
        for coeffs, s in terms:
            for k, v in coeffs.items():
                d[k] = d.get(k, 0.0) + s * v
        rows.append((d, lb - const, ub - const))

    M = float(len(P.derived) + 2)
    for v in P.derived:
        hv = {idx[("h", v)]: 1.0}
        ys = []
        for k, j in enumerate(P.just[v]):
            y = {idx[("y", v, k)]: 1.0}
            ys.append(y)
            consts = 0.0
            parts = []
            for a in j:
                c, k0 = hold(a)
                parts.append(c); consts += k0
                add([(y, 1.0), (c, -1.0)], -k0, ub=0.0)                 # y <= hold(a)
            # y >= sum hold(a) - (|j|-1)
            add([(y, 1.0)] + [(c, -1.0) for c in parts], -consts + (len(j) - 1), lb=0.0)
            add([(hv, 1.0), (y, -1.0)], 0.0, lb=0.0)                       # h >= y
            if P.cyclic:
                s = {idx[("s", v, k)]: 1.0}
                add([(s, 1.0), (y, -1.0)], 0.0, ub=0.0)                    # s <= y
                for a in j:
                    if a in P.just:                                        # r_v >= r_a + 1 when s is the support
                        add([({idx[("r", v)]: 1.0}, 1.0), ({idx[("r", a)]: 1.0}, -1.0), (s, -M)], 0.0, lb=1.0 - M)
        support = [{idx[("s", v, k)]: 1.0} for k in range(len(P.just[v]))] if P.cyclic else ys
        add([(hv, 1.0)] + [(s, -1.0) for s in support], 0.0, ub=0.0)        # h <= sum support
    for i, (_, ns, _) in enumerate(P.conflicts):
        parts, consts = [], 0.0
        for n in ns:
            c, k0 = hold(n)
            parts.append(c); consts += k0
        add([({idx[("viol", i)]: 1.0}, 1.0)] + [(c, -1.0) for c in parts], -consts + (len(ns) - 1), lb=0.0)
    for i, (n, _) in enumerate(P.confirms):
        c, k0 = hold(n)
        add([({idx[("fail", i)]: 1.0}, 1.0), (c, 1.0)], k0, lb=1.0)       # fail >= 1 - hold(n)
    for R in exclude:                                                      # no-good cut: differ from R somewhere
        d = {}
        const = 0.0
        for a in P.assumptions:
            if a in R:
                d[idx[("f", a)]] = -1.0; const += 1.0
            else:
                d[idx[("f", a)]] = 1.0
        rows.append((d, 1.0 - const, np.inf))
    A = lil_matrix((max(1, len(rows)), len(cost)))
    lbs, ubs = [], []
    for r, (d, lb, ub) in enumerate(rows):
        for k, v in d.items():
            A[r, k] = v
        lbs.append(lb); ubs.append(ub)
    if not rows:
        lbs, ubs = [-np.inf], [np.inf]
    res = milp(c=np.array(cost), constraints=[LinearConstraint(A.tocsr(), np.array(lbs), np.array(ubs))],
               bounds=Bounds(np.array(lo), np.array(hi)), integrality=np.array(integ),
               options={"time_limit": time_limit, "disp": False})
    info = {"status": int(res.status), "message": str(res.message), "seconds": time.perf_counter() - t0,
            "vars": len(cost), "rows": len(rows)}
    if res.x is None:
        return None, math.inf, info
    R = {a for a in P.assumptions if res.x[idx[("f", a)]] > 0.5}
    info["optimal"] = res.status == 0
    return R, P.energy(R), info


def all_optima(P, E_star, tol=1e-6, limit=8):
    """Every repair within `tol` of the optimum (up to `limit`), by re-solving with no-good cuts."""
    found = []
    while len(found) < limit:
        R, E, info = solve_exact(P, exclude=found)
        if R is None or E > E_star + tol:
            break
        found.append(R)
    return found


def prune(P, R):
    """Local polish: drop any retraction whose return lowers the energy, cheapest-to-keep first."""
    R = set(R)
    E = P.energy(R)
    improved = True
    while improved:
        improved = False
        for a in sorted(R, key=lambda a: (P.w[a], a), reverse=True):
            E2 = P.energy(R - {a})
            if E2 < E - 1e-9:
                R.discard(a); E = E2; improved = True
    return R


def local_search(P, R, rounds=20):
    """Discrete polish with swaps: drop a retraction, add a suspect, or swap one retraction for one suspect,
    whenever the energy falls (ties go to the earlier assumption). Suspects are the members of the contradictions'
    conflict sets, plus everything already retracted."""
    sus = set()
    for cid, _, _ in P.conflicts:
        sus |= P.suspects(cid)
    R = set(R)
    key = lambda S: (round(P.energy(S), 9), sum(P.depth.get(a, 0) for a in S))
    best = key(R)
    for _ in range(rounds):
        moves = [R - {a} for a in R] + [R | {b} for b in sus - R] + \
                [(R - {a}) | {b} for a in R for b in sus - R]
        cand = min(moves, key=key, default=None)
        if cand is None or key(cand) >= best:
            break
        R, best = cand, key(cand)
    return R


def solve_stable(P):
    """Iteration 3: the minimum-energy repair, keeping only the retractions that survive leaving out any ONE check
    answer (belief_revision's own rule - no single answer changes his mind - applied to the exact search). Every
    check answer is dropped in turn, the optimum is re-solved, and a retraction is kept only if every re-solve keeps
    it too. Returns (repair, seconds, re-solves)."""
    import copy as _copy
    t0 = time.perf_counter()
    R, E, info = solve_exact(P)
    keys = [("conflict", i) for i, c in enumerate(P.g.conflicts) if c.get("kind") == "check"] + \
           [("confirm", i) for i, c in enumerate(P.g.confirmations) if c.get("check")]
    core = set(R)
    for kind, i in keys:
        if not core:
            break
        Q = _copy.copy(P)
        if kind == "conflict":
            Q.conflicts = [c for k, c in enumerate(P.conflicts) if k != i]
        else:
            Q.confirms = [c for k, c in enumerate(P.confirms) if k != i]
        Ri, _, _ = solve_exact(Q)
        core &= set(Ri or ())
    return core, time.perf_counter() - t0, len(keys)
