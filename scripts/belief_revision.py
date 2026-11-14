#!/usr/bin/env python3
"""belief_revision.py - when two things he holds contradict, find WHICH sources made the wrong one, and by how much.

Gloria, 14 November 2026: "a way for him to back-propagate after logical contradictions with real accuracy."

Until now a contradiction lowers or flags the one record it touches (tension_promotion, belief_sediment.contradict,
reality_anchor) or matches text by word overlap (correction_propagate). Nothing walks back to the memories, evidence
items and inference steps the wrong belief was built from. This module does, truth-maintenance style:

  1. Every belief keeps its JUSTIFICATIONS: the sources it rests on, and the inference step that joined them.
     A source is an assumption: a memory, an evidence item, her words, a causal self-model entry, a SOUL or
     self-model statement, a lesson, a world-model prediction - or the inference step itself, because true
     premises can still be joined wrongly. A justification naming a source that is not in the record makes an
     assumption marked "not captured"; nothing is invented to fill it.
  2. A contradiction is a set of nodes that cannot all hold. Expanding each node to the sets of assumptions it
     rests on (its environments) gives the minimal CONFLICT SETS: in each one at least one assumption is wrong.
  3. Blame is a posterior, not a guess. Each assumption has a prior chance of being wrong from its kind, how many
     times it has been independently reinforced, and its age. The contradictions are noisy observations (a
     detector can raise a false alarm). The posterior chance that each assumption is wrong is computed exactly
     for small conflict components and by seeded likelihood weighting for large ones.
  4. Revision is proportionate: retract (kept as a superseded record, never deleted), lower, flag, or nothing.
     Her corrections are strong evidence (prior 0.05) but not infallible; one of hers is never retracted by this
     module - when the weight of evidence goes against her it is flagged for her instead.
  5. Everything built on a revised source is re-derived: its new standing is how likely it is that at least one
     of its environments is still all-sound.

SHADOW MODE ONLY. This module has no code that writes his stores. `shadow()` appends what it WOULD revise, as ids,
kinds and numbers - never text - to memory/belief-revision-shadow.jsonl. Turning on live revision is Gloria's decision.

    python3 belief_revision.py --memory DIR [--log PATH | --no-log]    # dry run over the stores in DIR
"""
import hashlib, itertools, json, math, os, random, sys, time
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
SHADOW_LOG = os.path.join(MEMORY, "belief-revision-shadow.jsonl")
LIVE = False          # shadow mode: nothing in this module changes a store. Live revision is Gloria's decision.
NOT_CAPTURED = "not captured"

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
EXACT_LIMIT = 14              # components up to this many assumptions are enumerated exactly
SAMPLES = 20000               # likelihood-weighting draws for larger components (seeded, so reproducible)
MAX_ENVS = 64                 # environments kept per node (most probable first)
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
    for e in sorted(set(envs), key=len):
        if not any(o <= e for o in out):
            out.append(e)
    return out


class Graph:
    """Beliefs, the sources they rest on, and the contradictions between them."""

    def __init__(self):
        self.nodes = {}            # id -> {kind, assumption, confidence, prior, captured, justifications, meta}
        self.conflicts = []        # {id, nodes, reliability, kind}
        self.confirmations = []    # {node, accuracy}
        self._envs = None

    # -- building -------------------------------------------------------------------------------------
    def source(self, nid, kind, confidence=None, evidence_count=0, age_days=0.0, reliability=None,
               captured=True, **meta):
        self.nodes[nid] = {"kind": kind, "assumption": True, "confidence": confidence, "captured": bool(captured),
                           "prior": prior_fault(kind, evidence_count, age_days, reliability),
                           "justifications": [], "meta": meta}
        self._envs = None
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
        self._envs = None
        return nid

    def conflict(self, cid, node_ids, reliability=DEFAULT_DETECTOR, kind=""):
        if any(c["id"] == cid for c in self.conflicts):
            return                                       # the same contradiction recorded twice is one observation
        self.conflicts.append({"id": cid, "nodes": list(node_ids), "reliability": float(reliability), "kind": kind})
        self._envs = None

    def confirm(self, nid, accuracy=0.9):
        self.confirmations.append({"node": nid, "accuracy": float(accuracy)})
        self._envs = None

    def _fill_gaps(self):
        """A justification that names a source not in the record gets an assumption marked not captured."""
        for nid in list(self.nodes):
            for j in self.nodes[nid]["justifications"]:
                for a in j:
                    if a not in self.nodes:
                        self.source(a, "unknown", captured=False, gap=NOT_CAPTURED)
        for c in self.conflicts:
            for a in c["nodes"]:
                if a not in self.nodes:
                    self.source(a, "unknown", captured=False, gap=NOT_CAPTURED)
        for c in self.confirmations:
            if c["node"] not in self.nodes:
                self.source(c["node"], "unknown", captured=False, gap=NOT_CAPTURED)

    # -- environments (ATMS labels) -------------------------------------------------------------------
    def _all_good(self, env):
        return math.prod(1.0 - self.nodes[a]["prior"] for a in env)

    def _cap(self, envs):
        envs = _minimize(envs)
        if len(envs) > MAX_ENVS:
            envs = sorted(envs, key=lambda e: (-self._all_good(e), sorted(e)))[:MAX_ENVS]
        return envs

    def envs(self, nid, _stack=()):
        """The minimal sets of assumptions this node rests on."""
        if self._envs is None:
            self._fill_gaps()
            self._envs = {}
        if nid in self._envs:
            return self._envs[nid]
        n = self.nodes[nid]
        if n["assumption"]:
            out = [frozenset([nid])]
        else:
            out = []
            for j in n["justifications"]:
                if any(a in _stack for a in j):
                    continue                                    # a circular justification supports nothing
                parts = [self.envs(a, _stack + (nid,)) for a in j]
                if any(not p for p in parts):
                    continue
                combo = [frozenset()]
                for p in parts:
                    combo = self._cap([c | e for c in combo for e in p])
                out.extend(combo)
            out = self._cap(out)
        self._envs[nid] = out
        return out

    def nogoods(self, conflict):
        """Minimal conflict sets: at least one assumption in each is wrong if the contradiction is real."""
        combo = [frozenset()]
        for m in conflict["nodes"]:
            combo = self._cap([c | e for c in combo for e in self.envs(m)])
        return _minimize(combo)


# -- posterior -----------------------------------------------------------------------------------------
def _seed(names):
    return int(hashlib.sha256("|".join(sorted(names)).encode()).hexdigest()[:12], 16)


def _component_posterior(g, names, constraints):
    """Posterior chance each assumption in one connected component is wrong.
    constraints: ("conflict", [masks], eps) | ("confirm", [env masks], accuracy)."""
    n = len(names)
    priors = [g.nodes[a]["prior"] for a in names]

    def lik(s):
        L = 1.0
        for c in constraints:
            if c[0] == "conflict":
                if not all(s & m for m in c[1]):
                    L *= c[2]                      # every nogood must be hit; otherwise the alarm was false
            else:
                holds = any(not (s & m) for m in c[1])
                L *= c[2] if holds else (1.0 - c[2])
        return L

    def joint(s):
        return math.prod(priors[i] if s >> i & 1 else 1.0 - priors[i] for i in range(n)) * lik(s)

    q = [0.0] * n
    Z = 0.0
    best, best_v = 0, -1.0
    if n <= EXACT_LIMIT:
        w = [1.0]
        for p in priors:                           # bit i set = assumption i is wrong
            w = [x * (1.0 - p) for x in w] + [x * p for x in w]
        # the doubling above puts assumption i at bit i (assumption 0 doubled first -> lowest bit)
        for s, ws in enumerate(w):
            if ws == 0.0:
                continue
            v = ws * lik(s)
            Z += v
            if v > best_v:
                best, best_v = s, v
            if v:
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
            Z += v
            for i in range(n):
                if s >> i & 1:
                    q[i] += v
            if v > 0 and (best_v < 0 or joint(s) > best_v):
                best, best_v = s, joint(s)
        # the best draw, then drop any fault whose removal makes the explanation more probable
        changed = True
        while changed:
            changed = False
            for i in range(n):
                if best >> i & 1 and joint(best & ~(1 << i)) > best_v:
                    best &= ~(1 << i)
                    best_v = joint(best)
                    changed = True
        method = "sampled"
    post = {a: (q[i] / Z if Z else priors[i]) for i, a in enumerate(names)}
    diagnosis = {a for i, a in enumerate(names) if best >> i & 1}
    return post, method, diagnosis


def posterior(g):
    """{assumption: posterior chance it is wrong}, the method used per component, and each conflict's nogoods."""
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
    q, methods, diagnosis = {}, {}, set()
    for members in comps.values():
        names = sorted(members)
        idx = {a: i for i, a in enumerate(names)}
        mask = lambda env: sum(1 << idx[a] for a in env)
        cons = []
        for c in g.conflicts:
            ng = nog[c["id"]]
            if ng and next(iter(ng[0])) in idx:
                cons.append(("conflict", [mask(e) for e in ng], 1.0 - c["reliability"]))
        for c, es in conf_envs:
            if es and next(iter(es[0])) in idx:
                cons.append(("confirm", [mask(e) for e in es], c["accuracy"]))
        res, method, diag = _component_posterior(g, names, cons)
        q.update(res)
        diagnosis |= diag
        for a in names:
            methods[a] = method
    for a, n in g.nodes.items():
        if n["assumption"] and a not in q:
            q[a] = n["prior"]
    return q, methods, nog, diagnosis


def belief(g, nid, fault):
    """Chance a node holds: at least one of its environments all sound (noisy-OR over environments)."""
    es = g.envs(nid)
    if not es:
        return 0.0
    miss = 1.0
    for e in es:
        miss *= 1.0 - math.prod(1.0 - fault[a] for a in e)
    return 1.0 - miss


# -- revision plan -------------------------------------------------------------------------------------
def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan(g, at=None):
    """What a contradiction-driven revision WOULD do. Changes nothing."""
    at = at or _now()
    q, methods, nog, diagnosis = posterior(g)
    prior = {a: n["prior"] for a, n in g.nodes.items() if n["assumption"]}
    blamed_in = {}
    per_conflict = []
    for c in g.conflicts:
        members = sorted(set().union(*nog[c["id"]]) if nog[c["id"]] else [])
        for a in members:
            blamed_in.setdefault(a, []).append(c["id"])
        ranked = sorted(members, key=lambda a: (-q[a], a))
        per_conflict.append({"conflict": c["id"], "kind": c["kind"], "conflict_sets": len(nog[c["id"]]),
                             "candidates": len(members),
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
        elif a in diagnosis:
            # one contradiction with several suspects rarely singles one out; the most probable explanation
            # of ALL the contradictions still names who to lower - in proportion to their blame
            action, reason = "lower", "most probable explanation"
        elif qa >= FLAG_AT and qa >= 2 * pa:
            action = "flag"
        else:
            continue
        if n["kind"] == "gloria":
            action, reason = "flag_for_gloria", "her word is never revised by this module; she decides"
        elif not n["captured"]:
            action, reason = "flag", NOT_CAPTURED
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
    rederive = []
    for nid, n in sorted(g.nodes.items()):
        es = g.envs(nid)
        if n["assumption"] or not es:
            continue
        rests_on = sorted(set().union(*es) & revised)
        if not rests_on:
            continue                                   # only what was built on a revised source is re-derived
        before, after = belief(g, nid, prior), belief(g, nid, q)
        cut_off = all(e & revised for e in es)        # no justification left standing on unrevised sources
        if cut_off and after < 0.5 * before:
            act = "withdraw"                           # the logic and the odds both say it no longer holds
        elif cut_off or (before > 0 and after < 0.75 * before):
            act = "lower"
        else:
            continue
        rederive.append({"node": nid, "kind": n["kind"], "action": act, "standing_before": round(before, 4),
                         "standing_after": round(after, 4), "rests_on_revised": rests_on})
    return {"at": at, "mode": "shadow", "live": LIVE, "conflicts": per_conflict, "revisions": revisions,
            "rederive": rederive, "fault": q}


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
            "not_captured": sum(1 for r in p["revisions"] if r["reason"] == NOT_CAPTURED)}


def shadow(p, path=None, extra=None):
    """Append what it WOULD revise: ids, kinds and numbers only. No text from any store."""
    path = path or SHADOW_LOG
    row = {"at": p["at"], "mode": "shadow", "live": False, "counts": counts(p),
           "revisions": [{k: r[k] for k in ("node", "kind", "action", "blame", "prior", "confidence_was",
                                            "confidence_would_be", "conflicts")} for r in p["revisions"]],
           "rederive": p["rederive"], "conflicts": p["conflicts"]}
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
    ap.add_argument("--memory", default=MEMORY, help="directory holding his stores (use a copy)")
    ap.add_argument("--log", default=None, help="shadow log path (default memory/belief-revision-shadow.jsonl)")
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
