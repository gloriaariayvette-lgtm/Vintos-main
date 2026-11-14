#!/usr/bin/env python3
"""Contradiction back-propagation (belief_revision.py, 14 November 2026). Gloria's three criteria: a contradiction is
traced to the earliest faulty inference (asking the one check that splits the suspects when the record cannot),
only what depends on the revised inference is recomputed, and unrelated valid reasoning is left untouched. Also:
her word outweighs his inference without being infallible, a source missing from the record stays "not captured",
labels do not depend on build order, the feeds mirror the organs' own evidence rules, and shadow mode changes no
store and logs no text.

Every behaviour check is also run against a mutant of the code it protects; the mutant must fail it.
Synthetic fixtures only (the repository is public). Scratch HOME and SPARK_WORKSPACE before any import;
`requests` fails the suite if anything sends."""
import contextlib, copy, hashlib, io, json, os, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="belief-revision-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import belief_revision as BR
import belief_revision_sources as S

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))

def mutant(mod, old, new):
    """The module with one edit; the edit must exist exactly once."""
    src = open(mod.__file__).read()
    assert src.count(old) == 1, "mutation anchor not unique: %r" % old
    m = types.ModuleType(mod.__name__ + "_mutant"); m.__file__ = mod.__file__
    exec(compile(src.replace(old, new), mod.__file__, "exec"), m.__dict__)
    return m

def killed(name, probe, mod, old, new):
    try:
        m = mutant(mod, old, new)            # a broken anchor or an edit that does not compile fails the check
    except Exception as e:
        check("mutation killed: " + name, False, "mutant could not be built: %r" % e); return
    try:
        survived = bool(probe(m))
    except Exception:
        survived = False                     # the mutated behaviour crashed: the probe caught it
    check("mutation killed: " + name, not survived)

def action(p, node):
    return next((r["action"] for r in p["revisions"] if r["node"] == node), None)

check("every path is scratch", BR.MEMORY.startswith(HOME) and BR.SHADOW_LOG.startswith(HOME))
check("shadow mode: live revision is off", BR.LIVE is False)

print("--- 1. reinforcement: the well-reinforced source is not the one blamed ---")
def probe_evidence(M):
    g = M.Graph()
    g.source("a_strong", "memory", evidence_count=10)
    g.source("b_weak", "memory", evidence_count=0)
    g.derived("d", "belief", [["a_strong", "b_weak"]], rule_reliability=0.99)
    g.source("w", "gloria")
    g.conflict("c1", ["d", "w"])
    p = M.plan(g, at="t")
    return p["conflicts"][0]["blame"][0][0] == "b_weak"
check("probe: blame lands on the unreinforced source", probe_evidence(BR))
killed("reinforcement ignored", probe_evidence, BR,
       "p *= EVIDENCE_HALF / (EVIDENCE_HALF + max(0.0, float(evidence_count or 0)))", "p *= 1.0")

print("--- 2. her word: strong, never revised by the module, not infallible ---")
def probe_gloria_strong(M):
    g = M.Graph()
    g.source("basis", "private_record")
    g.derived("claim", "claim", [["basis"]])
    g.source("her", "gloria")
    g.conflict("c", ["claim", "her"])
    p = M.plan(g, at="t")
    return p["conflicts"][0]["blame"][0][0] != "her" and action(p, "her") in (None, "flag_for_gloria")
check("probe: his inference is blamed before her correction", probe_gloria_strong(BR))

def probe_gloria_flag(M):
    g = M.Graph()
    g.source("her", "gloria")
    for i in range(5):
        g.source("o%d" % i, "observation", evidence_count=6)
        g.conflict("c%d" % i, ["her", "o%d" % i])
    p = M.plan(g, at="t")
    r = next((r for r in p["revisions"] if r["node"] == "her"), None)
    return r is not None and r["blame"] > 0.5 and r["action"] == "flag_for_gloria"
check("probe: many independent observations against her raise a flag for her, never a retraction",
      probe_gloria_flag(BR))
killed("her word retracted by the module", probe_gloria_flag, BR, 'if n["kind"] == "gloria":', "if False:")

print("--- 3. revision: only what depends on the revised inference is recomputed ---")
def probe_downstream(M):
    g = M.Graph()
    g.source("s1", "world_prediction")
    g.derived("d1", "belief", [["s1"]], rule_reliability=0.99)
    g.derived("d2", "causal_self_model", [["d1"]], rule_reliability=0.99)
    g.source("w", "gloria")
    g.conflict("c", ["d2", "w"])
    p = M.plan(g, at="t")
    rd = {r["node"]: r["action"] for r in p["rederive"]}
    return action(p, "s1") == "retract" and rd.get("d1") == "withdraw" and rd.get("d2") == "withdraw"
check("probe: a retracted source withdraws the chain built on it", probe_downstream(BR))
killed("downstream never recomputed", probe_downstream, BR,
       "if not n[\"assumption\"] and g.envs(nid) and all(e & revised for e in g.envs(nid)))",
       "if False)")

def probe_second_support(M):
    g = M.Graph()
    g.source("s1", "world_prediction")
    g.source("s2", "observation", evidence_count=8)
    g.derived("d", "belief", [["s1"], ["s2"]], rule_reliability=0.99)
    g.source("w", "gloria")
    g.conflict("c", ["s1", "w"])
    p = M.plan(g, at="t")
    return action(p, "s1") in ("retract", "lower") and "d" not in {r["node"] for r in p["rederive"]}
check("probe: a belief with an independent sound justification is not recomputed", probe_second_support(BR))
killed("one revised justification recomputes the belief", probe_second_support, BR,
       "if not n[\"assumption\"] and g.envs(nid) and all(e & revised for e in g.envs(nid)))",
       "if not n[\"assumption\"] and g.envs(nid) and any(e & revised for e in g.envs(nid)))")

print("--- 4. localization: the earliest faulty inference, found by asking the check that splits the suspects ---")
def chain_graph(M):
    """p -> m1 -> m2 -> m3 -> m4 -> m5, plus an unrelated side chain q -> s1 -> s2. The step into m2 is faulty."""
    g = M.Graph()
    g.source("p", "observation", evidence_count=6); g.source("q", "observation", evidence_count=6)
    prev = "p"
    for i in range(1, 6):
        g.derived("m%d" % i, "conclusion", [[prev]]); prev = "m%d" % i
    g.derived("s1", "conclusion", [["q"]]); g.derived("s2", "conclusion", [["s1"]])
    g.source("w", "gloria"); g.conflict("c", ["m5", "w"])
    return g
TRUTH = {"p": True, "q": True, "m1": True, "m2": False, "m3": False, "m4": False, "m5": False, "s1": True, "s2": True}
def probe_localize(M):
    g = chain_graph(M)
    p = M.localize(g, lambda n: TRUTH.get(n), budget=6, at="t")
    top = next(c for c in p["conflicts"] if c["conflict"] == "c")["blame"][0][0]
    rec = {r["node"] for r in p["rederive"]}
    changed = {r["node"] for r in p["revisions"] if r["action"] in ("retract", "lower")}
    side_untouched = not ({"s1", "s2", "q", "rule:s1", "rule:s2"} & (rec | changed))
    return top == "rule:m2" and rec == {"m2", "m3", "m4", "m5"} and side_untouched and 0 < len(p["asked"]) <= 10
check("probe: bisection finds the faulty step, recomputes exactly what follows it, leaves the side chain",
      probe_localize(BR))

def probe_one_wrong_answer(M):
    """The first answer about m1 is wrong ("it fails"); every later answer is right. One answer must not be enough."""
    seen = {}
    def ask(n):
        seen[n] = seen.get(n, 0) + 1
        if n == "m1" and seen[n] == 1:
            return False
        return TRUTH.get(n)
    g = chain_graph(M)
    p = M.localize(g, ask, budget=12, at="t")
    changed = {r["node"] for r in p["revisions"] if r["action"] in ("retract", "lower")}
    return "rule:m1" not in changed and "p" not in changed and "m1" not in {r["node"] for r in p["rederive"]}
check("probe: one wrong answer does not change a valid step (it is asked again)", probe_one_wrong_answer(BR))
killed("a single answer accepted", probe_one_wrong_answer, BR,
       "return same >= 2 and same - other >= MARGIN", "return True")

def probe_ask_named(M):
    g = chain_graph(M)
    p = M.plan(g, at="t")
    qs = M.questions(g, p)
    return qs.get("c") in {"m1", "m2", "m3", "m4"}
check("probe: with no answers, the plan names one check on the contradiction's line", probe_ask_named(BR))
killed("no question named", probe_ask_named, BR, "if abs(st[best] - 0.5) < 0.45:", "if False:")

def probe_earliest_tie(M):
    g = M.Graph()
    g.source("p", "observation", evidence_count=6)
    g.derived("a", "conclusion", [["p"]]); g.derived("b", "conclusion", [["a"]])
    g.source("w", "gloria"); g.conflict("c", ["b", "w"])
    p = M.plan(g, at="t")
    return p["conflicts"][0]["blame"][0][0] == "rule:a"
check("probe: suspects the evidence cannot separate are ranked earliest first", probe_earliest_tie(BR))
killed("ties go to the last step", probe_earliest_tie, BR,
       "key=lambda a: (g.depth.get(a, 0), -q[a], a))", "key=lambda a: (-g.depth.get(a, 0), -q[a], a))")

print("--- 5. labels do not depend on the order beliefs were added (cycles included) ---")
def cyc(order):
    g = BR.Graph()
    for x in ("X", "Y"):
        g.source(x, "memory")
    spec = {"A": [["B"], ["Y"]], "B": [["A"], ["X"]]}
    for n in order:
        g.derived(n, "belief", spec[n], rule=False)
    g.source("her", "gloria"); g.conflict("c", ["B", "her"])
    return g
g1, g2 = cyc("AB"), cyc("BA")
check("a cycle gives the same labels whichever node came first",
      sorted(map(sorted, g1.envs("B"))) == sorted(map(sorted, g2.envs("B"))) == [["X"], ["Y"]],
      (g1.envs("B"), g2.envs("B")))
p1, p2 = BR.plan(g1, at="t"), BR.plan(g2, at="t")
check("and the same blame", p1["conflicts"][0]["blame"] == p2["conflicts"][0]["blame"])
deep = BR.Graph(); deep.source("p0", "observation")
for i in range(1, 1500):
    deep.derived("n%d" % i, "belief", [["p0" if i == 1 else "n%d" % (i - 1)]], rule=False)
check("a 1500-step chain is labelled without running out of stack", deep.envs("n1499") == [frozenset(["p0"])])

print("--- 6. record gap and bookkeeping ---")
def probe_gap(M):
    g = M.Graph()
    g.derived("claim", "claim", [["missing-basis"]], rule_reliability=0.999)
    g.source("her", "gloria")
    g.conflict("c", ["claim", "her"])
    p = M.plan(g, at="t")
    n = g.nodes.get("missing-basis") or {}
    r = next((r for r in p["revisions"] if r["node"] == "missing-basis"), {})
    return n.get("captured") is False and n["meta"].get("gap") == M.NOT_CAPTURED and \
        r.get("action") == "flag" and r.get("reason") == M.NOT_CAPTURED
check("probe: the uncaptured basis is flagged as not captured", probe_gap(BR))
killed("uncaptured source retracted", probe_gap, BR, 'elif not n["captured"]:', "elif False:")

def probe_dedup(M):
    g = M.Graph()
    g.source("a", "memory"); g.source("b", "memory")
    g.conflict("same", ["a", "b"]); g.conflict("same", ["a", "b"])
    return len(g.conflicts) == 1
check("probe: duplicate contradiction ids collapse", probe_dedup(BR))
killed("duplicates double-counted", probe_dedup, BR, 'if any(c["id"] == cid for c in self.conflicts):', "if False:")
gk = BR.Graph(); gk.source("x", "gloria")
try:
    gk.source("x", "observation"); clash = False
except ValueError:
    clash = True
check("one id cannot be two kinds of source", clash)

print("--- 7. exact and sampled posteriors agree ---")
def graph12():
    g = BR.Graph()
    kinds = ["memory", "lesson", "observation", "private_record", "self_statement", "world_prediction"]
    for i in range(10):
        g.source("s%d" % i, kinds[i % len(kinds)], evidence_count=i % 4)
    g.derived("d1", "belief", [["s0", "s1", "s2"], ["s3"]])
    g.derived("d2", "belief", [["d1", "s4", "s5"]])
    g.derived("d3", "belief", [["s6", "s7"], ["s8", "s9"]], rule_reliability=0.95)
    g.source("w1", "gloria"); g.source("w2", "observation")
    g.conflict("c1", ["d2", "w1"]); g.conflict("c2", ["d3", "s0"], reliability=0.9); g.conflict("c3", ["s5", "w2"])
    return g
qa = BR.posterior(graph12())[0]
old = BR.EXACT_LIMIT
try:
    BR.EXACT_LIMIT = 0
    qb, methods = BR.posterior(graph12())[:2]
finally:
    BR.EXACT_LIMIT = old
diff = max(abs(qa[k] - qb[k]) for k in qa)
check("sampled matches exact within 0.03", diff < 0.03 and "sampled" in methods.values(), diff)
gs = BR.Graph(); gs.source("r", "inference")
for x in ("a", "b"):
    gs.derived(x, "belief", [[]], rule=False)
gs.nodes["a"]["justifications"] = [["r", "u"]]; gs.nodes["b"]["justifications"] = [["r", "v"]]
gs.source("u", "memory"); gs.source("v", "memory"); gs.derived("top", "belief", [["a"], ["b"]], rule=False)
st = BR.standings(gs, ["top"])["top"]
exact = (1 - gs.nodes["r"]["prior"]) * (1 - gs.nodes["u"]["prior"] * gs.nodes["v"]["prior"])
check("a belief's standing handles environments that share a source", abs(st - exact) < 0.03, (st, exact))

print("--- 8. feeds from his stores (synthetic fixtures): the organs' own rules, ids and numbers only ---")
SECRET = "PRIVATE-QUOTE-7f3a"
def fixture(mem):
    os.makedirs(mem, exist_ok=True)
    w = lambda n, o: open(os.path.join(mem, n), "w").write(json.dumps(o))
    def ev(i, ch, pol, **k):
        e = {"evidence_id": "e%d" % i, "channel": ch, "at": "2026-10-0%dT10:00:00" % (i % 9 + 1), "polarity": pol,
             "quote": SECRET, "source": "her words", "under_influence": False}
        e.update(k); return e
    w("tension-ledger.json", {"tensions": [
        {"tension_id": "T-1", "status": "CONTESTED", "evidence": [
            ev(1, "E3", "supports"), ev(2, "E2", "supports"), ev(3, "E1", "contradicts"),
            ev(4, "E1", "contradicts", under_influence=True), ev(6, "E1", "contradicts", invalid=True),
            ev(7, "E3", "contradicts")]},
        {"tension_id": "T-2", "status": "SUPPORTED", "evidence": [ev(5, "E3", "supports")]}]})
    mk = lambda eid, v, day, ids, **k: dict({"evaluation_id": eid, "verdict": v, "date": day, "evidence_ids": ids,
                                             "evidence": SECRET, "schema_version": 2, "lineage_state": "eligible"}, **k)
    w("causality-hypotheses.json", {"hypotheses": [
        {"hypothesis_id": "H1", "hypothesis": SECRET, "confidence": 0.5, "marks": [
            mk("CE-1", "yes", "2026-10-01", ["E-1"]), mk("CE-2", "no", "2026-10-02", ["E-2"]),
            mk("CE-3", "no", "2026-10-03", ["E-4"], voided=True), mk("CE-4", "no", "2026-10-04", ["E-5"], lineage_state="tactical"),
            {"verdict": "no", "date": "2026-10-05", "evidence": SECRET}]}]})
    open(os.path.join(mem, "causality-graduated.jsonl"), "w").write(json.dumps(
        {"hypothesis_id": "H1", "hypothesis": SECRET, "evidence_ids": ["E-1"], "refuting_evidence_ids": ["E-2", "E-3"]}) + "\n")
    w("belief-sediment.json", {"beliefs": [{"pattern": SECRET, "hypothesis_ids": ["H1"], "evidence_ids": ["E-1"],
                                            "confidence": 0.4}]})
    w("causal-self-model.json", {"entries": [{"tendency": SECRET, "confidence": 0.5,
                                              "evidence": [{"occurrence_id": "belief:H1", "quote": SECRET}]}]})
    w("claim-hold-trials.json", {"trials": [
        {"id": "ch_1", "claim": SECRET, "outcome": {"verdict": "CORRECTED"}, "pushback": {"at": "2026-10-03", "quote": SECRET}},
        {"id": "ch_2", "claim": SECRET, "outcome": {"verdict": "VINDICATED"}}]})
    open(os.path.join(mem, "self-model-corrections.jsonl"), "w").write("".join(json.dumps(
        {"at": "2026-10-04", "source_id": "wal:1", "correction": SECRET, "supersedes": SECRET}) + "\n" for _ in range(2)))
    w("hallucination-flags.json", [
        {"id": "f1", "status": "reviewed", "correction": SECRET, "excerpt": SECRET, "timestamp": "2026-10-05"},
        {"id": "f2", "status": "dismissed", "correction": SECRET, "excerpt": SECRET, "timestamp": "2026-10-05"}])
    w("reality-anchor.json", {"events": [
        {"id": "r1", "statement": SECRET, "source": "inference", "contradictions": ["r2"], "reinforcements": [], "timestamp": "2026-10-06"},
        {"id": "r2", "statement": SECRET, "source": "avatar-chat", "contradictions": ["r1"], "reinforcements": ["x"], "timestamp": "2026-10-06"}],
        "source_reliability": {"inference": 0.6, "avatar-chat": 0.8}})

FIX = os.path.join(HOME, "fixture-memory"); fixture(FIX)
def digest(d):
    return {n: hashlib.sha256(open(os.path.join(d, n), "rb").read()).hexdigest() for n in sorted(os.listdir(d))}
before = digest(FIX)
g, stats = S.build(FIX)
want = {"tension": 1, "causality": 2, "claim_hold": 1, "self_model": 2, "hallucination": 1, "reality_anchor": 1, "world_model": 0}
check("each feed counts only the contradictions its organ counts", all(stats.get(k) == v for k, v in want.items()), stats)
check("a refuting id already carried by a 'no' night is not counted twice",
      not any(c["id"] == "c:refuted:H1:E-2" for c in g.conflicts) and any(c["id"] == "c:refuted:H1:E-3" for c in g.conflicts))
check("the causal self-model entry rests on the sediment belief, which rests on the hypothesis",
      "c:csm:0" in g.nodes and any("rule:c:hyp:H1" in e for e in g.envs("c:csm:0")))
check("one correction of hers superseding two sentences is one source", sum(1 for n in g.nodes if n.startswith("m:her:")) == 1)
LOG = os.path.join(HOME, "shadow.jsonl")
with contextlib.redirect_stdout(io.StringIO()) as out:
    BR.main(["--memory", FIX, "--log", LOG])
p = BR.localize(copy.deepcopy(g), lambda n: None, budget=3, at="t")
check("plan, questions and dry run change no store", digest(FIX) == before)
logtxt = open(LOG).read()
check("the shadow log holds no text from any store", SECRET not in logtxt and SECRET not in out.getvalue())
row = json.loads(logtxt.splitlines()[-1])
check("the shadow row says shadow, not live", row["mode"] == "shadow" and row["live"] is False)
check("an id that is not id-shaped is hashed before it is logged", BR._safe("a sentence with spaces").startswith("id-sha:"))
p = BR.plan(g, at="t")
check("every revision keeps the superseded record", all("superseded" in r and "confidence" in r["superseded"]
                                                         for r in p["revisions"]) and p["revisions"])
def probe_influence(Smod):
    return Smod.build(FIX)[1]["tension"] == 1
killed("evidence under influence or invalid counted", probe_influence, S,
       'and not e.get("under_influence") and not e.get("invalid")]', "]")
killed("E3 allowed to contradict", probe_influence, S,
       'e.get("channel") in ("E1", "E2", "E4")]', 'True]')
def probe_bearing(Smod):
    return Smod.build(FIX)[1]["causality"] == 2
killed("voided or ineligible nights counted", probe_bearing, S,
       'and m.get("lineage_state") == "eligible" and m.get("evaluation_id")]', 'or True]')

print("--- 9. the benchmarks: pre-registered, held-out seeds apart, scored once ---")
BD = os.path.join(REPO, "experiments", "contradiction-backprop")
sys.path.insert(0, BD)
import bench as B
import bench_criteria as BC
for name, mod, res in (("first", B, "results-test.json"), ("criteria", BC, "results-criteria-test.json")):
    check("%s: dev and held-out seeds do not overlap" % name, not set(mod.SPLITS["dev"]) & set(mod.SPLITS["test"]))
    path = os.path.join(BD, res)
    check("%s: the held-out split was scored and saved" % name, os.path.exists(path) and json.load(open(path))["split"] == "test")
pre = open(os.path.join(BD, "PREREGISTRATION-criteria.md")).read()
check("the criteria pre-registration names every criterion and the iteration log",
      all(s in pre for s in ("Localization", "Revision", "Preservation", "Iteration log")))
a1, T1 = BC.network("dag", 7); a2, T2 = BC.network("dag", 7)
check("the generator is deterministic", sorted(a1.nodes) == sorted(a2.nodes) and T1["faults"] == T2["faults"])

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
