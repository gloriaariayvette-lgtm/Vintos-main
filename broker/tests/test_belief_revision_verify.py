#!/usr/bin/env python3
"""The exact check on belief_revision's plans (belief_revision_verify.py, energy-repair experiment, 14 November 2026):
a plan that leaves a contradiction standing or breaks a passed check is reported, the minimal repair is found
exactly (and a loop cannot hold itself up), and nothing is changed. Every behaviour check is also run against a
mutant of the code it protects; the mutant must fail it. Synthetic fixtures only (the repository is public)."""
import contextlib, io, json, os, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="belief-verify-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
os.makedirs(os.path.join(WS, "memory"))
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import belief_revision as BR
import belief_revision_verify as V

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))

def mutant(mod, old, new):
    src = open(mod.__file__).read()
    assert src.count(old) == 1, "mutation anchor not unique: %r" % old
    m = types.ModuleType(mod.__name__ + "_mutant"); m.__file__ = mod.__file__
    exec(compile(src.replace(old, new), mod.__file__, "exec"), m.__dict__)
    return m

def killed(name, probe, mod, old, new):
    try:
        m = mutant(mod, old, new)
    except Exception as e:
        check("mutation killed: " + name, False, "mutant could not be built: %r" % e); return
    try:
        survived = bool(probe(m))
    except Exception:
        survived = False
    check("mutation killed: " + name, not survived)

try:
    import scipy  # noqa: F401
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False


def chain():
    """p0 -> a -> b -> c, c contradicted by her; a passed a check."""
    g = BR.Graph()
    g.source("p0", "observation", evidence_count=3)
    g.derived("a", "belief", [["p0"]])
    g.derived("b", "belief", [["a"]])
    g.derived("c", "belief", [["b"]])
    g.source("w", "gloria")
    g.conflict("c1", ["c", "w"])
    g.confirm("a", accuracy=0.9)
    return g


print("--- 1. a plan that leaves a contradiction standing is reported ---")
def probe_standing(M):
    g = chain()
    return M.verify(g, {"revisions": []}, exact=False)["standing"] == ["c1"]
check("no revision: the contradiction stands", probe_standing(V))
killed("standing ignores the contradiction", probe_standing, V,
       'if all(h.get(n, True) for n in c["nodes"])', 'if False')

print("--- 2. a revision that breaks a passed check is reported ---")
def probe_broken(M):
    g = chain()
    v = M.verify(g, {"revisions": [{"node": "p0", "action": "retract"}]}, exact=False)
    return v["standing"] == [] and v["broken_checks"] == ["a"]
check("retracting the premise resolves the contradiction but breaks the passed check on a", probe_broken(V))
killed("broken checks not recomputed", probe_broken, V,
       '"broken_checks": sorted({c["node"] for c in g.confirmations if not h.get(c["node"], True)})',
       '"broken_checks": []')

print("--- 3. a flag is not a revision ---")
def probe_flag(M):
    g = chain()
    return M.verify(g, {"revisions": [{"node": "rule:c", "action": "flag"}]}, exact=False)["standing"] == ["c1"]
check("a flagged step does not count as revised", probe_flag(V))
killed("flags counted as revisions", probe_flag, V, 'if r.get("action") in ("retract", "lower")}', '}')

print("--- 4. a loop cannot hold itself up ---")
def probe_loop(M):
    g = BR.Graph()
    g.source("p", "memory")
    g.derived("x", "belief", [["p"], ["y"]])
    g.derived("y", "belief", [["x"]])
    h = M.holds(g, {"p"})
    return h["x"] is False and h["y"] is False and M.holds(g, set())["y"] is True
check("x and y, supporting each other, fall when their only outside source goes", probe_loop(V))
killed("fixpoint seeded true", probe_loop, V, 'h.update({v: False for v in D})', 'h.update({v: True for v in D})')

if HAVE_SCIPY:
    print("--- 5. the exact minimum ---")
    def probe_min(M):
        g = chain()
        Rm, Em, _ = M.minimum(g)
        # retracting the last step (1.39) beats retracting her words (2.94) and beats rule:a / p0, which break a's check
        return Rm == {"rule:c"} or Rm == {"rule:b"}
    check("the cheapest repair keeps the checked belief and her words", probe_min(V))
    def probe_earliest(M):
        g = chain()
        return M.minimum(g)[0] == {"rule:b"}
    check("equal repairs go to the earlier step", probe_earliest(V))
    killed("tie-break toward the later step", probe_earliest, V, "w[a] + TIE * (1 + depth.get(a, 0))",
           "w[a] - TIE * (1 + depth.get(a, 0))")
    def probe_loop_min(M):
        # p is contradicted by her; y passed a check and rests on p only through the loop x <-> y. Retracting p
        # would break y's check (a loop cannot hold itself up), so the cheaper repair is to give up her word here.
        g = BR.Graph()
        g.source("p", "memory")
        g.derived("x", "belief", [["p"], ["y"]], rule=False)
        g.derived("y", "belief", [["x"]], rule=False)
        g.source("w", "gloria")
        g.conflict("c1", ["p", "w"])
        g.confirm("y", accuracy=0.9)
        Rm, Em, _ = M.minimum(g)
        return Rm == {"w"} and abs(M.energy(g, Rm) - Em) < 1e-9
    check("the solver knows a loop cannot keep a checked belief once its outside source goes", probe_loop_min(V))
    killed("loop support without ranks", probe_loop_min, V, "    cyc = _cyclic(D, J)", "    cyc = False")
    def probe_gap(M):
        g = chain()
        v = M.verify(g, {"revisions": [{"node": "w", "action": "retract"}]})
        return v["solver"] == "exact" and v["minimal"] is False and v["gap"] > 1.0
    check("retracting her words to end the contradiction is reported as far from minimal", probe_gap(V))
    def probe_policy(M):
        # the unconstrained minimum gives up her word; belief_revision never may, so the policy minimum must not
        g = BR.Graph()
        g.source("p", "memory")
        g.derived("x", "belief", [["p"], ["y"]], rule=False)
        g.derived("y", "belief", [["x"]], rule=False)
        g.source("w", "gloria")
        g.conflict("c1", ["p", "w"])
        g.confirm("y", accuracy=0.9)
        R0, _, _ = M.minimum(g)
        R1, _, s1 = M.minimum(g, policy=True)
        return R0 == {"w"} and "w" not in R1 and s1 == "exact"
    check("the policy minimum never revises her words", probe_policy(V))
    killed("policy ignored", probe_policy, V, "0.0 if policy and not revisable(g, a) else 0.0 if a in keep else 1.0", "0.0 if a in keep else 1.0")
    import itertools, random
    def probe_brute(M):
        """Seeded random small graphs, cyclic and not: the solver's minimum equals exhaustive search."""
        rng = random.Random(7)
        for t in range(40):
            g = BR.Graph()
            src = ["s%d" % i for i in range(rng.randint(2, 4))]
            for a in src:
                g.source(a, rng.choice(["memory", "observation", "lesson"]), evidence_count=rng.randint(0, 4))
            der = ["d%d" % i for i in range(rng.randint(1, 4))]
            for i, v in enumerate(der):
                pool = src + der[:i] + (der[i + 1:] if rng.random() < 0.4 else [])
                js = [rng.sample(pool, rng.randint(1, 2)) for _ in range(rng.randint(1, 2))]
                g.derived(v, "belief", js, rule=rng.random() < 0.5)
            for k in range(rng.randint(1, 2)):
                g.source("w%d" % k, "observation")
                g.conflict("c%d" % k, [rng.choice(der), "w%d" % k])
            if rng.random() < 0.6:
                g.confirm(rng.choice(der), accuracy=0.9)
            A = sorted(a for a, n in g.nodes.items() if n["assumption"])
            best = min(M.energy(g, set(c)) for r in range(len(A) + 1) for c in itertools.combinations(A, r))
            Rm, Em, st = M.minimum(g)
            if st != "exact" or abs(Em - best) > 1e-6:
                return False
        return True
    check("the minimum equals exhaustive search on 40 random small graphs", probe_brute(V))
    killed("a justification need not force its belief", probe_brute, V,
           "row([(hv, 1.0), (y, -1.0)], 0.0, lb=0.0)", "pass")
    killed("a justification may hold with a member missing", probe_brute, V,
           "row([(y, 1.0)] + [(c, -1.0) for c in parts], -consts + len(j) - 1, lb=0.0)", "pass")
    killed("a broken check costs nothing", probe_brute, V,
           "row([({idx[(\"fail\", i)]: 1.0}, 1.0), (c, 1.0)], k0, lb=1.0, ub=1.0)", "pass")
else:
    print("--- 5. scipy not importable: the exact part reports 'unavailable' ---")
    check("no solver: says so", V.verify(chain(), {"revisions": []})["solver"] == "unavailable")

print("--- 6. the dry run logs numbers only and changes nothing ---")
g = chain()
before = json.dumps({"n": sorted(g.nodes), "c": g.conflicts, "k": g.confirmations}, sort_keys=True, default=str)
V.verify(g, BR.plan(g, at="t"))
after = json.dumps({"n": sorted(g.nodes), "c": g.conflicts, "k": g.confirmations}, sort_keys=True, default=str)
check("verify does not change the graph", before == after)
FIX = os.path.join(HOME, "mem"); os.makedirs(FIX)
LOG = os.path.join(HOME, "shadow.jsonl")
with contextlib.redirect_stdout(io.StringIO()) as out:
    BR.main(["--memory", FIX, "--log", LOG, "--verify"])
row = json.loads(open(LOG).read().splitlines()[-1])
SOLVER = {"exact", "time_limit", "unavailable", "error", "not run", None}
check("the shadow row carries the verify counts, numbers only",
      {"standing", "broken_checks", "energy", "solver", "solver_policy"} <= set(row.get("verify", {}))
      and all(x is None or isinstance(x, (int, float, bool)) or (k.startswith("solver") and x in SOLVER)
              for k, x in row["verify"].items()), row.get("verify"))
import belief_revision_sources as S
real_build = S.build
def fake_build(mem):
    g = BR.Graph(); g.source("secret-memory-id with words", "memory"); g.derived("d", "belief", [["secret-memory-id with words"]])
    g.source("w", "observation"); g.conflict("c1", ["d", "w"])
    return g, {"fixture": 1}
S.build = fake_build
try:
    with contextlib.redirect_stdout(io.StringIO()):
        BR.main(["--memory", FIX, "--log", LOG, "--verify"])
finally:
    S.build = real_build
row = json.loads(open(LOG).read().splitlines()[-1])
check("with a real contradiction the verify row is still numbers only, and no id reaches it",
      row["verify"]["solver"] in SOLVER and "secret-memory-id" not in json.dumps(row["verify"])
      and all(x is None or isinstance(x, (int, float, bool)) or k.startswith("solver") for k, x in row["verify"].items()),
      row["verify"])
def boom(*a, **k): raise ZeroDivisionError("x")
import belief_revision_verify as V2
real_verify = V2.verify; V2.verify = boom
try:
    with contextlib.redirect_stdout(io.StringIO()):
        BR.main(["--memory", FIX, "--log", LOG, "--verify"])
finally:
    V2.verify = real_verify
row = json.loads(open(LOG).read().splitlines()[-1])
check("a check that fails still leaves the dry run its row", row["verify"] == {"solver": "error", "error": "ZeroDivisionError"})
with contextlib.redirect_stdout(io.StringIO()):
    BR.main(["--memory", FIX, "--log", LOG])
check("a plain dry run has no verify field", "verify" not in json.loads(open(LOG).read().splitlines()[-1]))

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
