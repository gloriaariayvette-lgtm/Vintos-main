#!/usr/bin/env python3
"""belief_revision.py - when two things he holds contradict, find WHICH sources made the wrong one, and by how much.

Gloria, 14 November 2026: "a way for him to back-propagate after logical contradictions with real accuracy."
Her three criteria: LOCALIZE to the earliest unsupported inference, not the last step; REVISE that inference and
recompute only the conclusions that depend on it; PRESERVE unrelated valid reasoning untouched.

Until now a contradiction lowers or flags the one record it touches (tension_promotion, belief_sediment.contradict,
reality_anchor) or matches text by word overlap (correction_propagate). Nothing walks back to the memories, evidence
items and inference steps the wrong belief was built from. This module does, truth-maintenance style:

  1. Every belief keeps its JUSTIFICATIONS: the sources it rests on, and the inference step that joined them.
     A source is an assumption: a memory, an evidence item, her words, a causal self-model entry, a SOUL or
     self-model statement, a lesson, a world-model prediction - or the inference step itself, because true
     premises can still be joined wrongly. A justification naming a source that is not in the record makes an
     assumption marked "not captured"; nothing is invented to fill it.
  2. A contradiction is a set of nodes that cannot all hold. Expanding each node to the sets of assumptions it
     rests on (its environments, computed as an order-independent fixpoint) gives the minimal CONFLICT SETS: in
     each one at least one assumption is wrong. A check that a belief holds is evidence too.
  3. Blame is a posterior, not a guess. Each assumption has a prior chance of being wrong from its kind, how many
     times it has been independently reinforced, and its age. Contradictions and checks are noisy observations.
     The posterior is exact for small components and seeded likelihood weighting for large ones.
  4. Localization: the most probable explanation of all the evidence names the faulty sources; where the evidence
     cannot tell two suspects apart, the EARLIER one (closer to the sources) is blamed, because everything after
     it is recomputed anyway, while blaming the later one would leave the real fault standing.
  5. Revision is proportionate: retract (kept as a superseded record, never deleted), lower, flag, or nothing.
     Her corrections are strong evidence (prior 0.05) but not infallible; one of hers is never revised by this
     module - when the weight of evidence goes against her it is flagged for her instead.
  6. Only what depends on a revised source is recomputed: a belief every one of whose justifications passes through
     a revised source. A belief with an independent sound justification, and everything unrelated, is untouched.

This module has no code that writes his stores. `shadow()` appends what it WOULD revise, as ids, kinds and numbers -
never text - to a shadow log. Check questions are answered by belief_revision_answer (his records, then the local
checker; Gloria's option (b), 14 November 2026), and the only writer is belief_revision_live, which does nothing
unless BELIEF_REVISION=live is in vintos.env.

    python3 belief_revision.py --memory DIR [--log PATH | --no-log]    # dry run over the stores in DIR (a copy)
"""
import bisect, hashlib, json, math, os, random, re, sys
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
SHADOW_LOG = os.path.join(MEMORY, "belief-revision-shadow.jsonl")
LIVE = False          # shadow mode: nothing in this module changes a store. Live revision is Gloria's decision.
NOT_CAPTURED = "not captured"
SAFE_ID = re.compile(r"^[\w:.\-/]{1,96}$")

# Prior chance that a record of this kind is wrong, before any contradiction is seen.
PRIOR_FAULT = {
    "gloria": 0.05,             # her corrections and her own words: strong evidence, not infallible
    "observation": 0.10,        # a record of what happened: his message as sent, a measurement, a nightly mark
    "memory": 0.15,
    "lesson": 0.20,
    "soul": 0.20,
    "inference": 0.20,          # an inference step: premises can be right and the step still wrong
    "self_statement": 0.25,
    "private_record": 0.25,     # his own private reading of an event
    "unknown": 0.25,            # provenance not captured
    "causal_self_model": 0.30,
    "world_prediction": 0.35,
}
EVIDENCE_HALF = 4.0           # independent reinforcements that halve the prior chance of being wrong
AGE_DRIFT_DAYS, AGE_DRIFT = 180.0, 0.25   # an unreinforced record drifts: up to +25% prior after 180 days
RETRACT_AT, LOWER_AT, FLAG_AT = 0.80, 0.50, 0.30
TIE = 0.02                    # blame within this of the top cannot be told apart: the earliest is blamed
LOWER_BY_EXPLANATION = True   # lower the most probable explanation's members even before they are localized
OPINIONS = 3                  # separate checks at most on the one answer a revision hinges on
MARGIN = 1                    # agreeing answers must outnumber disagreeing ones by this much (and be at least two)
LOCALIZED_AT = 0.90         # below this the culprit is not yet localized, and a check is worth asking
EXACT_LIMIT = 14              # components up to this many assumptions are enumerated exactly
SAMPLES = 20000               # likelihood-weighting draws for larger components (seeded, so reproducible)
DRAWS = 2000                  # posterior draws used to recompute a belief's standing
MAX_ENVS = 64                 # environments kept per node (most probable first); truncation is reported
DEFAULT_DETECTOR = 0.95       # chance a reported contradiction is real


def prior_fault(kind, evidence_count=0, age_days=0.0, reliability=None):
    """The chance this source is wrong before the contradiction: kind, reinforcement, age."""
    if reliability is not None:
        p = 1.0 - float(reliability)
    else:
        p = PRIOR_FAULT.get(kind, PRIOR_FAULT["unknown"])
        p *= EVIDENCE_HALF / (EVIDENCE_HALF + max(0.0, float(evidence_count or 0)))
        p *= 1.0 + AGE_DRIFT * min(max(0.0, float(age_days or 0)) / AGE_DRIFT_DAYS, 1.0)
    return min(max(p, 0.005), 0.95)


def _minimize(envs):
    """Drop every environment that contains another (a superset is never a minimal reason)."""
    out = []
    for e in sorted(set(envs), key=lambda e: (len(e), sorted(e))):
        if not any(o <= e for o in out):
            out.append(e)
    return out


class Graph:
    """Beliefs, the sources they rest on, and the contradictions between them."""

    def __init__(self):
        self.nodes = {}            # id -> {kind, assumption, confidence, prior, captured, justifications, meta}
        self.conflicts = []        # {id, nodes, reliability, kind}
        self.confirmations = []    # {node, accuracy}
        self._labels = None
        self.truncated = set()     # nodes / conflicts whose environment list was capped

    # -- building -------------------------------------------------------------------------------------
    def source(self, nid, kind, confidence=None, evidence_count=0, age_days=0.0, reliability=None,
               captured=True, **meta):
        old = self.nodes.get(nid)
        if old is not None and (not old["assumption"] or old["kind"] != kind):
            raise ValueError("node %s already held as %s" % (nid, old["kind"]))
        if old is not None:
            return nid                                   # the same source met twice is one source
        self.nodes[nid] = {"kind": kind, "assumption": True, "confidence": confidence, "captured": bool(captured),
                           "prior": prior_fault(kind, evidence_count, age_days, reliability),
                           "justifications": [], "meta": meta}
        self._labels = None
        return nid

    def derived(self, nid, kind, justifications, confidence=None, rule=True, rule_kind="inference",
                rule_reliability=None, **meta):
        """A belief that holds if ANY justification holds; a justification holds if ALL its antecedents do
        and (with rule=True) the inference step that joined them was sound."""
        just = [list(j) for j in (justifications or [])]
        if rule:
            rid = "rule:" + nid
            self.source(rid, rule_kind, reliability=rule_reliability)
            just = [j + [rid] for j in just] or [[rid]]
        self.nodes[nid] = {"kind": kind, "assumption": False, "confidence": confidence, "captured": True,
                           "prior": None, "justifications": just, "meta": meta}
        self._labels = None
        return nid

    def conflict(self, cid, node_ids, reliability=DEFAULT_DETECTOR, kind=""):
        if any(c["id"] == cid for c in self.conflicts):
            return                                       # the same contradiction recorded twice is one observation
        self.conflicts.append({"id": cid, "nodes": list(node_ids), "reliability": float(reliability), "kind": kind})
        self._labels = None

    def confirm(self, nid, accuracy=0.9):
        self.confirmations.append({"node": nid, "accuracy": float(accuracy)})
        self._labels = None

    def _fill_gaps(self):
        """A justification that names a source not in the record gets an assumption marked not captured."""
        named = [a for n in list(self.nodes.values()) for j in n["justifications"] for a in j]
        named += [a for c in self.conflicts for a in c["nodes"]] + [c["node"] for c in self.confirmations]
        for a in named:
            if a not in self.nodes:
                self.source(a, "unknown", captured=False, gap=NOT_CAPTURED)

    # -- environments (ATMS labels), an order-independent fixpoint ------------------------------------------
    def _all_good(self, env):
        return math.prod(1.0 - self.nodes[a]["prior"] for a in env)

    def _cap(self, envs, owner):
        envs = _minimize(envs)
        if len(envs) > MAX_ENVS:
            self.truncated.add(owner)
            envs = sorted(envs, key=lambda e: (-self._all_good(e), sorted(e)))[:MAX_ENVS]
        return envs

    def _compute(self):
        self._fill_gaps()
        self.truncated = set()
        lab = {nid: [frozenset([nid])] for nid, n in self.nodes.items() if n["assumption"]}
        derived = sorted(nid for nid, n in self.nodes.items() if not n["assumption"])
        for nid in derived:
            lab[nid] = []
        # Jacobi iteration: each round recomputes every derived label from the previous round's labels, so the
        # result does not depend on the order nodes were added; a cycle supports only what reaches it from outside
        for _ in range(len(derived) + 1):
            new = {}
            for nid in derived:
                out = []
                for j in self.nodes[nid]["justifications"]:
                    parts = [lab[a] for a in j]
                    if any(not p for p in parts):
                        continue
                    combo = [frozenset()]
                    for p in parts:
                        combo = self._cap([c | e for c in combo for e in p], nid)
                    out.extend(combo)
                new[nid] = self._cap(out, nid)
            if all(new[n] == lab[n] for n in derived):
                break
            lab.update(new)
        self._labels = lab
        # depth: how many inference steps from the sources (an assumption sits at the depth of what it built)
        depth = {nid: 0 for nid in lab}
        for _ in range(len(derived) + 1):
            changed = False
            for nid in derived:
                ds = [max([depth[a] for a in j if a in depth and not self.nodes[a]["assumption"]] or [0])
                      for j in self.nodes[nid]["justifications"]]
                d = 1 + (min(ds) if ds else 0)
                if d != depth[nid] and d <= len(derived) + 1:
                    depth[nid], changed = d, True
            if not changed:
                break
        for nid in derived:
            if ("rule:" + nid) in depth:
                depth["rule:" + nid] = depth[nid]
        self.depth = depth

    def envs(self, nid):
        """The minimal sets of assumptions this node rests on."""
        if self._labels is None:
            self._compute()
        return self._labels[nid]

    def nogoods(self, conflict):
        """Minimal conflict sets: at least one assumption in each is wrong if the contradiction is real."""
        combo = [frozenset()]
        for m in conflict["nodes"]:
            combo = self._cap([c | e for c in combo for e in self.envs(m)], conflict["id"])
        return _minimize(combo)


# -- posterior -----------------------------------------------------------------------------------------
def _seed(names):
    return int(hashlib.sha256("|".join(sorted(names)).encode()).hexdigest()[:12], 16)


def _component_posterior(g, names, constraints):
    """Posterior chance each assumption in one connected component is wrong, the most probable explanation, and
    a weighted sample of fault states for recomputing beliefs.
    constraints: ("conflict", [masks], eps) | ("confirm", [env masks], accuracy)."""
    n = len(names)
    priors = [g.nodes[a]["prior"] for a in names]
    depth = [g.depth.get(a, 0) for a in names]

    def lik(s):
        L = 1.0
        for c in constraints:
            if c[0] == "conflict":
                if not all(s & m for m in c[1]):
                    L *= c[2]                      # every conflict set must hold a fault; otherwise a false alarm
            else:
                holds = any(not (s & m) for m in c[1])
                L *= c[2] if holds else (1.0 - c[2])
        return L

    def joint(s):
        return math.prod(priors[i] if s >> i & 1 else 1.0 - priors[i] for i in range(n)) * lik(s)

    def earliness(s):
        return tuple(sorted(depth[i] for i in range(n) if s >> i & 1))

    def better(s, v, best, best_v):
        if v > best_v * (1 + 1e-9):
            return True
        return v >= best_v * (1 - 1e-9) and earliness(s) < earliness(best)   # a tie goes to the earlier fault

    q = [0.0] * n
    Z = 0.0
    best, best_v = 0, -1.0
    states, weights = [], []
    if n <= EXACT_LIMIT:
        w = [1.0]
        for p in priors:                           # bit i set = assumption i is wrong
            w = [x * (1.0 - p) for x in w] + [x * p for x in w]
        for s, ws in enumerate(w):
            v = ws * lik(s)
            if v <= 0:
                continue
            Z += v
            states.append(s); weights.append(v)
            if best_v < 0 or better(s, v, best, best_v):
                best, best_v = s, v
            for i in range(n):
                if s >> i & 1:
                    q[i] += v
        method = "exact"
    else:
        rng = random.Random(_seed(names))
        for _ in range(SAMPLES):
            s = 0
            for i, p in enumerate(priors):
                if rng.random() < p:
                    s |= 1 << i
            v = lik(s)
            if v <= 0:
                continue
            Z += v
            states.append(s); weights.append(v)
            for i in range(n):
                if s >> i & 1:
                    q[i] += v
            jv = joint(s)
            if best_v < 0 or better(s, jv, best, best_v):
                best, best_v = s, jv
        changed = True                             # refine the best draw: drop faults that make it less probable
        while changed:
            changed = False
            for i in range(n):
                if best >> i & 1:
                    t = best & ~(1 << i)
                    if better(t, joint(t), best, best_v):
                        best, best_v, changed = t, joint(t), True
        method = "sampled"
    post = {a: (q[i] / Z if Z else priors[i]) for i, a in enumerate(names)}
    diagnosis = {a for i, a in enumerate(names) if best >> i & 1}
    cum, t = [], 0.0
    for v in weights:
        t += v
        cum.append(t)
    return post, method, diagnosis, (names, states, cum)


def posterior(g):
    """{assumption: posterior chance it is wrong}, the method per assumption, each conflict's conflict sets,
    the most probable explanation, and the per-component samplers."""
    for nid in list(g.nodes):
        g.envs(nid)
    nog = {c["id"]: g.nogoods(c) for c in g.conflicts}
    conf_envs = [(c, g.envs(c["node"])) for c in g.confirmations]
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(items):
        items = list(items)
        for a in items:
            find(a)
        for a in items[1:]:
            parent[find(a)] = find(items[0])

    for c in g.conflicts:
        union(set().union(*nog[c["id"]]) if nog[c["id"]] else [])
    for c, es in conf_envs:
        union(set().union(*es) if es else [])
    comps = {}
    for a in parent:
        comps.setdefault(find(a), []).append(a)
    q, methods, diagnosis, samplers = {}, {}, set(), []
    for members in comps.values():
        names = sorted(members)
        idx = {a: i for i, a in enumerate(names)}
        mask = lambda env: sum(1 << idx[a] for a in env)
        first = lambda envs: next((a for e in envs for a in e), None)
        cons = []
        for c in g.conflicts:
            ng = nog[c["id"]]
            if ng and first(ng) in idx:
                cons.append(("conflict", [mask(e) for e in ng], 1.0 - c["reliability"]))
        for c, es in conf_envs:
            if es and first(es) in idx:
                cons.append(("confirm", [mask(e) for e in es], c["accuracy"]))
        res, method, diag, sampler = _component_posterior(g, names, cons)
        q.update(res)
        diagnosis |= diag
        samplers.append(sampler)
        for a in names:
            methods[a] = method
    for a, n in g.nodes.items():
        if n["assumption"] and a not in q:
            q[a] = n["prior"]
    return q, methods, nog, diagnosis, samplers


def standings(g, nids, samplers=None, seed="standing"):
    """Chance each node holds - some environment all sound - from joint draws (posterior when samplers are given,
    otherwise the priors). Environments that share a source are handled exactly, not as if independent."""
    rng = random.Random(seed)
    need = sorted({a for nid in nids for e in g.envs(nid) for a in e})
    in_comp = set()
    comps = []
    for names, states, cum in samplers or []:
        if cum and set(names) & set(need):
            comps.append((names, states, cum))
            in_comp.update(names)
    free = [(a, g.nodes[a]["prior"]) for a in need if a not in in_comp]
    held = {nid: 0 for nid in nids}
    for _ in range(DRAWS):
        bad = set()
        for names, states, cum in comps:
            s = states[min(bisect.bisect_left(cum, rng.random() * cum[-1]), len(states) - 1)]
            bad.update(a for i, a in enumerate(names) if s >> i & 1)
        for a, p in free:
            if rng.random() < p:
                bad.add(a)
        for nid in nids:
            if any(not (e & bad) for e in g.envs(nid)):
                held[nid] += 1
    return {nid: held[nid] / float(DRAWS) for nid in nids}


# -- revision plan -------------------------------------------------------------------------------------
def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rank(g, members, q):
    """Most blamed first; suspects the evidence cannot tell apart (within TIE) go earliest first."""
    if not members:
        return []
    top = max(q[a] for a in members)
    tied = sorted((a for a in members if q[a] >= top - TIE), key=lambda a: (g.depth.get(a, 0), -q[a], a))
    rest = sorted((a for a in members if q[a] < top - TIE), key=lambda a: (-q[a], a))
    return tied + rest


def plan(g, at=None, hold=()):
    """What a contradiction-driven revision WOULD do. Changes nothing. Sources in `hold` are flagged, not revised."""
    at = at or _now()
    q, methods, nog, diagnosis, samplers = posterior(g)
    prior = {a: n["prior"] for a, n in g.nodes.items() if n["assumption"]}
    blamed_in = {}
    per_conflict = []
    for c in g.conflicts:
        members = sorted(set().union(*nog[c["id"]]) if nog[c["id"]] else [])
        for a in members:
            blamed_in.setdefault(a, []).append(c["id"])
        ranked = rank(g, members, q)
        per_conflict.append({"conflict": c["id"], "kind": c["kind"], "conflict_sets": len(nog[c["id"]]),
                             "candidates": len(members), "truncated": c["id"] in g.truncated,
                             "blame": [[a, round(q[a], 4)] for a in ranked[:5]]})
    revisions = []
    for a in sorted(blamed_in):
        n = g.nodes[a]
        qa, pa = q[a], prior[a]
        reason = "blame"
        if qa >= RETRACT_AT:
            action = "retract"
        elif qa >= LOWER_AT:
            action = "lower"
        elif a in diagnosis and LOWER_BY_EXPLANATION:
            # one contradiction with several suspects rarely singles one out; the most probable explanation
            # of ALL the evidence still names who to lower - in proportion to their blame
            action, reason = "lower", "most probable explanation"
        elif qa >= FLAG_AT and qa >= 2 * pa:
            action = "flag"
        else:
            continue
        if n["kind"] == "gloria":
            action, reason = "flag_for_gloria", "her word is never revised by this module; she decides"
        elif not n["captured"]:
            action, reason = "flag", NOT_CAPTURED
        elif a in hold and action in ("retract", "lower"):
            action, reason = "flag", "rests on a single answer"
        was = n["confidence"]
        would = was
        if was is not None and action == "lower":
            would = round(float(was) * (1.0 - qa), 4)
        elif was is not None and action == "retract":
            would = 0.0
        revisions.append({
            "node": a, "kind": n["kind"], "action": action, "reason": reason,
            "blame": round(qa, 4), "prior": round(pa, 4), "method": methods.get(a, "prior"),
            "explains": a in diagnosis,
            "confidence_was": was, "confidence_would_be": would, "conflicts": blamed_in[a],
            # the record is superseded, never deleted - the gloria_regrade pattern
            "superseded": {"confidence": was, "standing": "held",
                           "replaced_by": {"by": "belief_revision", "mode": "shadow", "at": at,
                                           "conflicts": blamed_in[a]}},
        })
    revised = {r["node"] for r in revisions if r["action"] in ("retract", "lower")}
    # recompute ONLY what depends on a revised source: every justification passes through one
    dependent = sorted(nid for nid, n in g.nodes.items()
                       if not n["assumption"] and g.envs(nid) and all(e & revised for e in g.envs(nid)))
    before = standings(g, dependent, None, seed="before")
    after = standings(g, dependent, samplers, seed="after")
    rederive = []
    for nid in dependent:
        act = "withdraw" if after[nid] < 0.5 * before[nid] or after[nid] < 0.05 else "lower"
        rederive.append({"node": nid, "kind": g.nodes[nid]["kind"], "action": act,
                         "standing_before": round(before[nid], 4), "standing_after": round(after[nid], 4),
                         "rests_on_revised": sorted(set().union(*g.envs(nid)) & revised)})
    return {"at": at, "mode": "shadow", "live": LIVE, "conflicts": per_conflict, "revisions": revisions,
            "rederive": rederive, "fault": q}


def ancestors(g, nid):
    """Every belief this one was derived from, directly or not (assumptions excluded)."""
    out, stack = set(), [nid]
    while stack:
        n = g.nodes.get(stack.pop())
        for j in (n or {}).get("justifications", []):
            for a in j:
                if a not in out and a in g.nodes and not g.nodes[a]["assumption"]:
                    out.add(a)
                    stack.append(a)
    return out


def ambiguous(c):
    """The evidence has not singled out a culprit: nothing is near-certain, or the top suspects tie."""
    b = c["blame"]
    return bool(b) and (b[0][1] < LOCALIZED_AT or (len(b) > 1 and b[1][1] >= b[0][1] - TIE))


def line_of(g, nid):
    """What a check could test on this belief's line of derivation: the belief, the beliefs it came from, and the
    recorded sources under them - never an inference step itself (a step is judged through its conclusion), and
    never her words (she is not asked to vouch for what she said)."""
    out = set()
    if nid in g.nodes and not g.nodes[nid]["assumption"]:
        out = {nid} | ancestors(g, nid)
        for d in list(out):
            for j in g.nodes[d]["justifications"]:
                out.update(a for a in j if g.nodes[a]["assumption"] and not a.startswith("rule:")
                           and g.nodes[a]["kind"] != "gloria" and g.nodes[a]["captured"])
    return out


def questions(g, p, checked=()):
    """For each contradiction the evidence cannot yet localize, the one check that would best split the suspects:
    the belief on its line of derivation whose standing is closest to even (a bisection, like git bisect).
    Shadow mode only names the question; who answers it - his records, or her - is Gloria's decision."""
    _, _, _, _, samplers = posterior(g)
    asks = {}
    pool = {}
    for c in p["conflicts"]:
        if not ambiguous(c):
            continue
        conflict = next(x for x in g.conflicts if x["id"] == c["conflict"])
        line = set()
        for m in conflict["nodes"]:
            line |= line_of(g, m)
        line -= set(checked)
        if line:
            pool[c["conflict"]] = sorted(line)
    need = sorted(set().union(*pool.values())) if pool else []
    st = standings(g, need, samplers, seed="questions") if need else {}
    for cid, line in pool.items():
        best = min(line, key=lambda n: (abs(st[n] - 0.5), g.depth.get(n, 0), n))
        if abs(st[best] - 0.5) < 0.45:                   # a check whose answer is already known tells nothing
            asks[cid] = best
    return asks


def descendants(g, nid):
    """Every belief built, directly or not, on this node."""
    kids = {}
    for d, n in g.nodes.items():
        for j in n["justifications"]:
            for a in j:
                kids.setdefault(a, set()).add(d)
    out, stack = set(), [nid]
    while stack:
        for c in kids.get(stack.pop(), ()):
            if c not in out:
                out.add(c)
                stack.append(c)
    return out


def corroboration(g, suspect, checked, rivals=()):
    """A check that tells whether `suspect` really is wrong: the nearest unchecked belief that rests on it in every
    justification (if the suspect is wrong it fails too) and on none of the rival suspects (else it would fail for
    their sake and prove nothing), else a second opinion on the belief it produced."""
    base = suspect[5:] if suspect.startswith("rule:") else suspect
    if base not in g.nodes:
        return None
    pool = ({base} if not g.nodes[base]["assumption"] else set()) | descendants(g, base)
    rivals = set(rivals) - {suspect}
    pool = [n for n in pool if n not in checked and g.envs(n) and all(suspect in e for e in g.envs(n))
            and not any(e & rivals for e in g.envs(n))]
    if pool:
        return min(pool, key=lambda n: (g.depth.get(n, 0), n))
    if not g.nodes[base]["assumption"] or (g.nodes[base]["kind"] != "gloria" and g.nodes[base]["captured"]):
        return base if checked.count(base) < 2 else None
    return None


def localize(g, ask, budget=12, per_conflict=3, accuracy=0.9, at=None):
    """Plan, then ask checks where the evidence cannot yet localize (at most `per_conflict` for any one
    contradiction, `budget` in all), adding each answer as evidence: True (it holds) is a passing check, False a
    contradiction from the check, None (cannot tell) adds nothing. Returns the final plan and the checks asked."""
    asked = []
    answers = []
    spent = {}
    verified = {}
    p = plan(g, at=at)
    while len(asked) < budget:
        checked = [n for n, _ in asked]
        qs = {cid: n for cid, n in questions(g, p, checked=checked).items() if spent.get(cid, 0) < per_conflict}
        if qs:
            cid = sorted(qs)[0]
            spent[cid] = spent.get(cid, 0) + 1
            node = qs[cid]
        else:
            # corroborate before revising: one answer is never enough to change a source - ask one more check of
            # something the revision predicts (a conclusion built on the suspect), or a second opinion
            node = None
            for r in p["revisions"]:
                if r["action"] not in ("retract", "lower") or verified.get(r["node"], 0) >= OPINIONS:
                    continue
                hinge = fragile(g, r["node"])
                if verified.get(r["node"]) and settled(asked, hinge):
                    continue                             # already corroborated and it holds up
                verified[r["node"]] = verified.get(r["node"], 0) + 1
                if hinge and not settled(asked, hinge) and checked.count(hinge[0]) < OPINIONS:
                    node = hinge[0]                      # the answer it hinges on gets another opinion;
                    break                                # two that disagree get a third
                rivals = {a for c in p["conflicts"] if c["conflict"] in r["conflicts"] for a, b in c["blame"]
                          if b >= FLAG_AT}
                node = corroboration(g, r["node"], checked, rivals)
                if node:
                    break
            if not node:
                break
        ans, acc, prov = _answer(ask(node), accuracy)
        asked.append((node, ans))
        answers.append({"node": node, "answer": ans, "accuracy": acc, "provenance": prov})
        if ans is True:
            g.confirm(node, accuracy=acc)
            g.confirmations[-1]["check"] = True
        elif ans is False:
            k = sum(1 for n, _ in asked if n == node)        # a second opinion is a second, separate check
            w = g.source("check:%s:%d" % (node, k), "observation", reliability=acc)
            g.conflict("check:%s:%d" % (node, k), [node, w], kind="check")
        p = plan(g, at=at)
    # no single check answer may change a source on its own: a revision that would not survive dropping any one
    # answer is held back as a flag, its question still open
    hold = {r["node"] for r in p["revisions"] if r["action"] in ("retract", "lower")
            and not settled(asked, fragile(g, r["node"]))}
    if hold:
        p = plan(g, at=at, hold=hold)
    p["asked"] = [[n, a] for n, a in asked]
    p["answers"] = answers
    p["held"] = sorted(hold)
    return p


def _answer(raw, accuracy):
    """An answer as (True | False | None, the accuracy to weigh it with, its provenance). `ask` may return a bare
    True / False / None (weighed with `accuracy`), or {"answer", "accuracy", "provenance"} from an answerer that
    knows how reliable each answer is (belief_revision_answer: a record, or the checker's measured accuracy)."""
    prov = None
    if isinstance(raw, dict):
        a, prov = raw.get("answer"), raw.get("provenance")
        try:
            acc = float(raw.get("accuracy") or accuracy)
        except (TypeError, ValueError):
            acc = accuracy
    else:
        a, acc = raw, accuracy
    if a is not True and a is not False:
        return None, float(accuracy), prov
    return a, min(max(float(acc), 0.5), 0.995), prov


def fragile(g, node):
    """The belief whose single check answer this source's revision hinges on (dropping that one answer would bring
    its blame below LOWER_AT), or None when no single answer carries it."""
    import copy as _copy
    keys = [("conflict", c["id"], c["nodes"][0]) for c in g.conflicts if c["kind"] == "check"] + \
           [("confirm", i, c["node"]) for i, c in enumerate(g.confirmations) if c.get("check")]
    for kind, key, about in keys:
        g2 = _copy.copy(g)
        g2.conflicts = [c for c in g.conflicts if not (kind == "conflict" and c["id"] == key)]
        g2.confirmations = [c for i, c in enumerate(g.confirmations) if not (kind == "confirm" and i == key)]
        if posterior(g2)[0].get(node, 0.0) < LOWER_AT:
            return about, kind == "confirm"
    return None


def settled(asked, hinge):
    """A hinge answer is settled when at least two separate answers on that belief agree and outnumber the rest."""
    if not hinge:
        return True
    about, value = hinge
    same = sum(1 for n, a in asked if n == about and a is value)
    other = sum(1 for n, a in asked if n == about and a is (not value))
    return same >= 2 and same - other >= MARGIN


def resolved(g, p):
    """Conflict ids whose every conflict set holds a retracted or lowered source."""
    nog = {c["id"]: g.nogoods(c) for c in g.conflicts}
    out = {r["node"] for r in p["revisions"] if r["action"] in ("retract", "lower")}
    return {cid for cid, ng in nog.items() if ng and all(e & out for e in ng)}


def counts(p):
    by = {}
    for r in p["revisions"]:
        by.setdefault(r["kind"], {}).setdefault(r["action"], 0)
        by[r["kind"]][r["action"]] += 1
    rd = {}
    for r in p["rederive"]:
        rd.setdefault(r["kind"], {}).setdefault(r["action"], 0)
        rd[r["kind"]][r["action"]] += 1
    return {"conflicts": len(p["conflicts"]), "revisions": by, "rederive": rd,
            "not_captured": sum(1 for r in p["revisions"] if r["reason"] == NOT_CAPTURED),
            "truncated": sum(1 for c in p["conflicts"] if c["truncated"])}


def _safe(x):
    return x if SAFE_ID.match(str(x)) else "id-sha:" + hashlib.sha256(str(x).encode()).hexdigest()[:16]


def shadow(p, path, extra=None):
    """Append what it WOULD revise: ids, kinds and numbers only. Any id that is not id-shaped is hashed."""
    row = {"at": p["at"], "mode": "shadow", "live": False, "counts": counts(p),
           "revisions": [dict({k: r[k] for k in ("kind", "action", "blame", "prior", "confidence_was",
                                                  "confidence_would_be")},
                              node=_safe(r["node"]), conflicts=[_safe(c) for c in r["conflicts"]])
                         for r in p["revisions"]],
           "rederive": [dict({k: r[k] for k in ("kind", "action", "standing_before", "standing_after")},
                             node=_safe(r["node"]), rests_on_revised=[_safe(a) for a in r["rests_on_revised"]])
                        for r in p["rederive"]],
           "conflicts": [dict({k: c[k] for k in ("kind", "conflict_sets", "candidates", "truncated")},
                              conflict=_safe(c["conflict"]), blame=[[_safe(a), b] for a, b in c["blame"]])
                         for c in p["conflicts"]]}
    if extra:
        row.update(extra)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--memory", required=True, help="directory holding his stores (use a copy)")
    ap.add_argument("--log", default=None, help="shadow log path (default: belief-revision-shadow.jsonl in --memory)")
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import belief_revision_sources as S
    g, stats = S.build(a.memory)
    p = plan(g)
    out = {"sources": stats, "plan": counts(p), "resolved": len(resolved(g, p))}
    if not a.no_log:
        out["log"] = shadow(p, a.log or os.path.join(a.memory, "belief-revision-shadow.jsonl"),
                            extra={"sources": stats})
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
