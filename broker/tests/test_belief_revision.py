#!/usr/bin/env python3
"""Contradiction back-propagation (belief_revision.py, 14 November 2026): blame lands on the right sources,
her word outweighs his inference without being infallible, what was built on a revised source is re-derived,
a source missing from the record stays "not captured", and shadow mode changes no store and logs no text.

Every behaviour check is also run against a mutant of the code it protects; the mutant must fail it.
Synthetic fixtures only (the repository is public). Scratch HOME and SPARK_WORKSPACE before any import;
`requests` fails the suite if anything sends."""
import hashlib, json, os, sys, tempfile, types

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
        survived = bool(probe(mutant(mod, old, new)))
    except Exception:
        survived = False
    check("mutation killed: " + name, not survived)

def action(p, node):
    return next((r["action"] for r in p["revisions"] if r["node"] == node), None)

check("every path is scratch", BR.MEMORY.startswith(HOME) and BR.SHADOW_LOG.startswith(HOME))
check("shadow mode: live revision is off", BR.LIVE is False)
check("no store writer exists in the module", not any(hasattr(BR, n) for n in ("apply", "commit", "write_store")))

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
    top = p["conflicts"][0]["blame"][0][0]
    return top != "her" and action(p, "her") in (None, "flag_for_gloria")
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

print("--- 3. what was built on a revised source is re-derived ---")
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
killed("downstream never withdrawn", probe_downstream, BR,
       "cut_off = all(e & revised for e in es)", "cut_off = False")

def probe_second_support(M):
    g = M.Graph()
    g.source("s1", "world_prediction")
    g.source("s2", "observation", evidence_count=8)
    g.derived("d", "belief", [["s1"], ["s2"]], rule_reliability=0.99)
    g.source("w", "gloria")
    g.conflict("c", ["s1", "w"])
    p = M.plan(g, at="t")
    return action(p, "s1") in ("retract", "lower") and "d" not in {r["node"] for r in p["rederive"]}
check("probe: a belief with an independent sound justification stands", probe_second_support(BR))
killed("one revised justification takes down the belief", probe_second_support, BR,
       "cut_off = all(e & revised for e in es)", "cut_off = any(e & revised for e in es)")

print("--- 4. several suspects: the most probable explanation still resolves it ---")
def probe_explanation(M):
    g = M.Graph()
    g.source("s1", "lesson")
    g.source("s2", "lesson")
    g.derived("d", "belief", [["s1", "s2"]], rule_reliability=0.99)
    g.source("w", "gloria")
    g.conflict("c", ["d", "w"])
    p = M.plan(g, at="t")
    lowered = [r for r in p["revisions"] if r["node"] in ("s1", "s2") and r["action"] == "lower"]
    return len(lowered) >= 1 and all(r["blame"] < 0.5 for r in lowered) and "c" in M.resolved(g, p)
check("probe: an ambiguous contradiction is resolved by lowering in proportion", probe_explanation(BR))
killed("explanation ignored", probe_explanation, BR, "elif a in diagnosis:", "elif False:")

print("--- 5. record gap: a source not in the record is not captured, never retracted ---")
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

print("--- 6. one contradiction recorded twice is one observation ---")
def probe_dedup(M):
    g = M.Graph()
    g.source("a", "memory"); g.source("b", "memory")
    g.conflict("same", ["a", "b"]); g.conflict("same", ["a", "b"])
    return len(g.conflicts) == 1
check("probe: duplicate contradiction ids collapse", probe_dedup(BR))
killed("duplicates double-counted", probe_dedup, BR, 'if any(c["id"] == cid for c in self.conflicts):', "if False:")

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
    qb, methods, _, _ = BR.posterior(graph12())
finally:
    BR.EXACT_LIMIT = old
diff = max(abs(qa[k] - qb[k]) for k in qa)
check("sampled matches exact within 0.03", diff < 0.03 and "sampled" in methods.values(), diff)

print("--- 8. feeds from his stores (synthetic fixtures): ids and numbers only, no store changed ---")
SECRET = "PRIVATE-QUOTE-7f3a"
def fixture(mem):
    os.makedirs(mem, exist_ok=True)
    w = lambda n, o: open(os.path.join(mem, n), "w").write(json.dumps(o))
    ev = lambda i, ch, pol, infl=False: {"evidence_id": "e%d" % i, "channel": ch, "at": "2026-10-0%dT10:00:00" % (i % 9 + 1),
                                         "polarity": pol, "quote": SECRET, "source": "her words", "under_influence": infl}
    w("tension-ledger.json", {"tensions": [
        {"tension_id": "T-1", "status": "CONTESTED", "evidence": [ev(1, "E3", "supports"), ev(2, "E2", "supports"),
                                                                    ev(3, "E1", "contradicts"), ev(4, "E1", "contradicts", True)]},
        {"tension_id": "T-2", "status": "SUPPORTED", "evidence": [ev(5, "E3", "supports")]}]})
    w("causality-hypotheses.json", {"hypotheses": [
        {"hypothesis_id": "H1", "hypothesis": SECRET, "confidence": 0.5, "marks": [
            {"evaluation_id": "CE-1", "verdict": "yes", "date": "2026-10-01", "evidence_ids": ["E-1"], "evidence": SECRET},
            {"evaluation_id": "CE-2", "verdict": "no", "date": "2026-10-02", "evidence_ids": ["E-2"], "evidence": SECRET}]}]})
    open(os.path.join(mem, "causality-graduated.jsonl"), "w").write(json.dumps(
        {"hypothesis_id": "H1", "hypothesis": SECRET, "evidence_ids": ["E-1"], "refuting_evidence_ids": ["E-3"]}) + "\n")
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
check("each feed counts its contradictions", all(stats.get(k) == v for k, v in want.items()), stats)
check("the causal self-model entry rests on the sediment belief, which rests on the hypothesis",
      "csm:0" in g.nodes and any("rule:hyp:H1" in e for e in g.envs("csm:0")))
check("one correction of hers superseding two sentences is one source", sum(1 for n in g.nodes if n.startswith("her:wal")) == 1)
LOG = os.path.join(HOME, "shadow.jsonl")
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()) as out:
    BR.main(["--memory", FIX, "--log", LOG])
check("dry run changes no store", digest(FIX) == before)
logtxt = open(LOG).read()
check("the shadow log holds no text from any store", SECRET not in logtxt and SECRET not in out.getvalue())
row = json.loads(logtxt.splitlines()[-1])
check("the shadow row says shadow, not live", row["mode"] == "shadow" and row["live"] is False)
p = BR.plan(g, at="t")
check("every revision keeps the superseded record", all("superseded" in r and "confidence" in r["superseded"]
                                                         for r in p["revisions"]) and p["revisions"])
def probe_influence(Smod):
    gg, st = Smod.build(FIX)
    return st["tension"] == 1
killed("evidence under influence counted", probe_influence, S,
       'if isinstance(e, dict) and not e.get("under_influence")]', 'if isinstance(e, dict)]')

print("--- 9. the benchmark: pre-registered, test seeds apart, scored once ---")
BD = os.path.join(REPO, "experiments", "contradiction-backprop")
sys.path.insert(0, BD)
import bench as B
pre = open(os.path.join(BD, "PREREGISTRATION.md")).read()
check("the pre-registration names every bar", all(s in pre for s in ("Blame top-1", "Precision", "Recall",
                                                                     "Collateral", "Convergence")))
check("dev and test seeds do not overlap", not set(B.SPLITS["dev"]) & set(B.SPLITS["test"]))
g1, T1 = B.network("chain", 7); g2, T2 = B.network("chain", 7)
check("the generator is deterministic", sorted(g1.nodes) == sorted(g2.nodes) and T1["faults"] == T2["faults"])
res = os.path.join(BD, "results-test.json")
check("the test split was scored and saved", os.path.exists(res) and json.load(open(res))["split"] == "test")

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
