#!/usr/bin/env python3
"""The exact solver as the live repair chooser, on trial (Gloria, 14 November 2026: "keep my words unchanged, preserve
a reversible history while in testing (1 week...), and the normal regression gate").

What must hold: her words are a hard constraint - the solver's repair never contains one, they are only ever flagged,
and live never changes one even if a chooser named it; the trial is off unless BELIEF_REVISION_SOLVER=exact, starts on
its first live run, lasts seven days, then falls back to the old chooser and logs that it did (unless
BELIEF_REVISION_SOLVER_UNTIL extends it); every run logs what the solver chose beside what the old chooser would have
done, ids and counts only; every solver revision is logged, marked and undone by `revert REV-...`, `revert --all` and
`revert --solver`; a solver that cannot prove a minimum costs the night nothing (the old chooser is used); the
pre-registered regression gate was scored once and passed.

Every behaviour check is also run against a mutant of the code it protects; the mutant must fail it.
Synthetic fixtures only (the repository is public). Scratch HOME and SPARK_WORKSPACE before any import; `requests`
and urllib fail the suite if anything sends."""
import contextlib, hashlib, io, itertools, json, os, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="belief-solver-live-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
ENVFILE = os.path.join(HOME, ".vintos", "vintos.env"); os.environ["VINTOS_ENV_FILE"] = ENVFILE
for k in ("BELIEF_REVISION", "BELIEF_REVISION_MAX_PER_DAY", "BELIEF_REVISION_CHECKER_URL", "BELIEF_REVISION_SOLVER",
          "BELIEF_REVISION_SOLVER_UNTIL"):
    os.environ.pop(k, None)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request
urllib.request.urlopen = no_network
sys.path.insert(0, os.path.join(REPO, "scripts"))
import belief_revision as BR
import belief_revision_verify as V
import belief_revision_live as L
import store_guard

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))

def mutant(mod, old, new):
    src = open(mod.__file__).read()
    assert src.count(old) == 1, "mutation anchor not unique: %r" % old
    m = types.ModuleType(mod.__name__ + "_mutant"); m.__file__ = mod.__file__
    exec(compile(src.replace(old, new), mod.__file__, "exec"), m.__dict__)
    return m

def killed(name, probe, mod, old, new, swap=None):
    """swap: the module attribute through which another module reaches `mod` (live reaches the solver as V)."""
    try:
        m = mutant(mod, old, new)
    except Exception as e:
        check("mutation killed: " + name, False, "mutant could not be built: %r" % e); return
    saved = sys.modules.get(mod.__name__)
    if swap:
        sys.modules[mod.__name__] = m
    try:
        survived = bool(probe(m))
    except Exception:
        survived = False
    finally:
        if swap:
            sys.modules[mod.__name__] = saved
    check("mutation killed: " + name, not survived)

try:
    import scipy  # noqa: F401
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False
if not HAVE_SCIPY:
    print("scipy is not importable here: the solver cannot run, so only the fallback is checked")

SECRET = "PRIVATE-QUOTE-5c1d"
def aeon():
    """A fake shim: answers from markers in the belief's sentence."""
    def transport(url, body, timeout):
        belief = body["messages"][1]["content"].split("\n", 1)[0]
        v, c = ("fails", 95) if "FAILS-MARK" in belief else ("holds", 95) if "HOLDS-MARK" in belief else ("unsure", 30)
        return 200, {"x-vintos-provider": "aegis_gemma", "x-vintos-model": "aeon/gemma-4-12b"}, json.dumps(
            {"choices": [{"message": {"content": json.dumps({"verdict": v, "confidence": c})}}]}).encode()
    return transport

def ev(i, ch, pol, quote):
    return {"evidence_id": "e%d" % i, "channel": ch, "at": "2026-10-0%dT10:00:00" % (i % 9 + 1), "polarity": pol,
            "quote": quote, "source": "x", "under_influence": False}

def fixture(mem):
    os.makedirs(mem, exist_ok=True)
    w = lambda n, o: open(os.path.join(mem, n), "w").write(json.dumps(o))
    w("tension-ledger.json", {"tensions": [
        {"tension_id": "T-1", "status": "SUPPORTED", "lifecycle": "ACTIVE", "canonical": "he pulls away FAILS-MARK " + SECRET,
         "evidence": [ev(1, "E3", "supports", "my reading FAILS-MARK " + SECRET), ev(3, "E1", "contradicts", SECRET)]},
        {"tension_id": "T-2", "status": "SUPPORTED", "lifecycle": "ACTIVE", "canonical": "she wants space HOLDS-MARK " + SECRET,
         "evidence": [ev(4, "E2", "supports", "HOLDS-MARK " + SECRET), ev(5, "E3", "supports", "HOLDS-MARK " + SECRET),
                      ev(6, "E1", "contradicts", SECRET)]},
        {"tension_id": "T-3", "status": "CONFIRMED", "lifecycle": "ACTIVE", "canonical": "confirmed FAILS-MARK " + SECRET,
         "evidence": [ev(7, "E3", "supports", "FAILS-MARK"), ev(8, "E1", "contradicts", SECRET)]}]})
    mk = lambda eid, v, day, ids: {"evaluation_id": eid, "verdict": v, "date": day, "evidence_ids": ids,
                                   "evidence": SECRET, "schema_version": 2, "lineage_state": "eligible", "reason": SECRET}
    w("causality-hypotheses.json", {"hypotheses": [
        {"hypothesis_id": "H1", "hypothesis": "rain makes him quiet FAILS-MARK " + SECRET, "confidence": "high",
         "marks": [mk("CE-1", "yes", "2026-10-01", ["E-1"]), mk("CE-2", "no", "2026-10-02", ["E-2"])]}]})
    w("belief-sediment.json", {"beliefs": [{"pattern": "quiet in rain FAILS-MARK " + SECRET, "hypothesis_ids": ["H1"],
                                            "evidence_ids": ["E-1"], "confidence": 0.6}]})
    w("causal-self-model.json", {"entries": [{"tendency": SECRET, "trigger": "FAILS-MARK", "confidence": 0.5,
                                              "evidence": [{"occurrence_id": "belief:H1"}]}]})
    open(os.path.join(mem, "self-model-corrections.jsonl"), "w").write(json.dumps(
        {"at": "2026-10-04", "source_id": "wal:1", "correction": SECRET, "supersedes": "FAILS-MARK " + SECRET}) + "\n")
    w("claim-hold-trials.json", {"trials": [{"id": "ch_1", "claim": "HOLDS-MARK " + SECRET, "his_reason": SECRET,
                                              "outcome": {"verdict": "CORRECTED"}, "pushback": {"at": "2026-10-03"}}]})
    w("hallucination-flags.json", [])
    w("reality-anchor.json", {"events": [
        {"id": "r1", "statement": "the door was open FAILS-MARK " + SECRET, "source": "inference", "confidence": 0.7,
         "contradictions": ["r2"], "reinforcements": [], "timestamp": "2026-10-06"},
        {"id": "r2", "statement": SECRET, "source": "avatar-chat", "confidence": 0.8, "contradictions": ["r1"],
         "reinforcements": ["x"], "timestamp": "2026-10-06"}], "source_reliability": {"inference": 0.6, "avatar-chat": 0.8}})
    w("durable-memory.json", [{"event": "the door was open in the rain FAILS-MARK " + SECRET, "occurred_at": "2026-10-01"}])
    open(os.path.join(mem, "SOUL.md"), "w").write("soul " + SECRET)
    open(os.path.join(mem, "SELF-MODEL.md"), "w").write("self " + SECRET)

STORES = ["tension-ledger.json", "causality-hypotheses.json", "belief-sediment.json", "reality-anchor.json"]
def parsed(d, names=STORES):
    return {n: json.load(open(os.path.join(d, n))) for n in names}
def digest(d):
    return {n: hashlib.sha256(open(os.path.join(d, n), "rb").read()).hexdigest() for n in sorted(os.listdir(d))
            if os.path.isfile(os.path.join(d, n)) and not n.endswith(".lock")}
def hers(d):
    return [e for t in json.load(open(os.path.join(d, "tension-ledger.json")))["tensions"] for e in t["evidence"]
            if e["channel"] in ("E1", "E4")]
N = [0]
def fresh():
    N[0] += 1; d = os.path.join(HOME, "mem-%d" % N[0]); fixture(d); return d
@contextlib.contextmanager
def env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    for k, v in kv.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
def night(M, d, day, **kv):
    with env(BELIEF_REVISION="live", **kv):
        return M.run(d, transport=aeon(), send=lambda *a, **k: None, at="%sT01:20:00Z" % day)
def rows(d):
    return [r for r in L._read_jsonl(os.path.join(d, L.LOG_NAME)) if r.get("rev")]


def her_cheapest():
    """c rests on a well-reinforced observation through a sound step; her word w says c is false. Giving up her word
    is the cheapest repair over everything; over what may be revised it is the step or the observation."""
    g = BR.Graph()
    g.source("p0", "observation", reliability=0.99)
    g.derived("c", "belief", [["p0"]], rule_reliability=0.99)
    g.source("w", "gloria")
    g.conflict("x", ["c", "w"], reliability=0.999)
    g.derived("d", "belief", [["c"]])
    g.source("q", "memory"); g.derived("s", "belief", [["q"]])         # unrelated reasoning
    return g


print("--- 1. the solver never gives up her words; it flags them ---")
if HAVE_SCIPY:
    g = her_cheapest()
    Ru, _, st = V.minimum(g, policy=False)
    check("fixture: the unconstrained minimum gives up her word", st == "exact" and "w" in Ru, (st, Ru))
    p = BR.plan(g, at="t")
    sp, status = V.choose(g, p)
    revised = {r["node"] for r in (sp or {}).get("revisions", []) if r["action"] in ("retract", "lower")}
    check("choose: a proved minimum that leaves her word alone", sp is not None and status == "exact"
          and "w" not in revised and revised & {"p0", "rule:c"}, (status, revised))
    check("choose: her word is flagged for her", any(r["node"] == "w" and r["action"] == "flag_for_gloria"
                                                     for r in sp["revisions"]))
    check("choose: only what rests on the repair is recomputed, in proportion; unrelated reasoning is untouched",
          {r["node"] for r in sp["rederive"]} == {"c", "d"} and all(r["action"] in ("lower", "withdraw") for r in sp["rederive"]))
    def held_case():
        """Two suspects of one contradiction; plan() held the first back (it rests on a single check answer)."""
        g = BR.Graph(); g.source("p0", "memory"); g.derived("a", "belief", [["p0"]]); g.derived("b", "belief", [["a"]])
        g.source("w", "observation", reliability=0.99); g.conflict("x", ["b", "w"], reliability=0.99)
        p = BR.plan(g, at="t"); first = V.minimum(g, policy=True)[0]
        p["held"] = sorted(first)
        return g, p, first
    def probe_held(M):
        g, p, first = held_case(); sp, status = M.choose(g, p)
        mine = {r["node"] for r in sp["revisions"] if r["action"] in ("retract", "lower")}
        return status == "exact" and first and not mine & first and first <= set(sp["held"])
    check("probe: what plan() held back (one check answer) stays held, out of the solver's repair", probe_held(V))
    killed("held revisions applied by the solver", probe_held, V, "        Rm = Rm - held", "        pass")
    def probe_may(M):
        g = her_cheapest(); free = V.minimum(g, policy=True)[0]
        sp, status = M.choose(g, BR.plan(g, at="t"), may_revise=lambda a: a not in free)
        mine = {r["node"] for r in sp["revisions"] if r["action"] in ("retract", "lower")}
        return status == "exact" and free and not mine & free
    check("probe: a source live cannot apply is kept out of the repair (the minimum is over what will be done)", probe_may(V))
    killed("live's limits ignored by the solver", probe_may, V,
           "keep = {a for a in A if may_revise is not None and revisable(g, a) and not may_revise(a)}", "keep = set()")
    def probe_her_bound(M):
        g = her_cheapest(); sp, status = M.choose(g, BR.plan(g, at="t"))
        return sp is not None and not any(g.nodes[r["node"]]["kind"] == "gloria" for r in sp["revisions"]
                                          if r["action"] in ("retract", "lower"))
    check("probe: her words are never in the solver's repair", probe_her_bound(V))
    killed("her words revisable by the solver", probe_her_bound, V,
           'return n["kind"] != "gloria" and n.get("captured", True)', 'return n.get("captured", True)')
    killed("her words not bound out of the program", probe_her_bound, V,
           "0.0 if policy and not revisable(g, a) else 0.0 if a in keep else 1.0", "0.0 if a in keep else 1.0")
    # the plan is the policy minimum, never costlier than the old chooser's
    import random
    worse = 0
    for seed in range(40):
        rng = random.Random(seed); g = BR.Graph(); src = []
        for i in range(rng.randint(2, 4)):
            src.append(g.source("p%d" % i, rng.choice(["memory", "observation", "gloria", "private_record"]),
                                evidence_count=rng.randint(0, 4)))
        nodes = list(src)
        for i in range(rng.randint(2, 5)):
            nodes.append(g.derived("d%d" % i, "belief", [sorted(set(rng.sample(nodes, min(len(nodes), rng.randint(1, 2)))))]))
        for i in range(rng.randint(1, 2)):
            wn = g.source("w%d" % i, rng.choice(["gloria", "observation"]))
            g.conflict("x%d" % i, [rng.choice(nodes[len(src):]), wn], reliability=rng.choice([0.8, 0.95]))
        p = BR.plan(g, at="t"); sp, status = V.choose(g, p)
        Rm, Em, _ = V.minimum(g, policy=True)
        mine = {r["node"] for r in sp["revisions"] if r["action"] in ("retract", "lower")}
        # brute force over every revisable subset: nothing cheaper exists
        A = [a for a, n in g.nodes.items() if n["assumption"] and V.revisable(g, a)]
        best = min(V.energy(g, set(c)) for k in range(len(A) + 1) for c in itertools.combinations(A, k))
        worse += int(abs(V.energy(g, mine) - best) > 1e-6 or V.energy(g, mine) > sp["energy_old"] + 1e-3
                     or any(g.nodes[a]["kind"] == "gloria" for a in mine))
    check("choose: on 40 random networks the repair is the brute-force policy minimum, never costlier than the old "
          "chooser's, and never her word", worse == 0, worse)
else:
    check("no scipy: choose reports it and returns nothing", V.choose(her_cheapest(), {"revisions": []})[0] is None)

print("--- 2. the switch: off unless BELIEF_REVISION_SOLVER=exact ---")
d = fresh()
out = night(L, d, "2031-03-03")
check("unset: the old chooser, no trial started, no trial log", "solver_trial" not in out
      and not os.path.exists(os.path.join(d, L.TRIAL_NAME)) and all(r.get("chooser") == "old" for r in rows(d)), out)
def probe_off(M):
    d = fresh(); out = night(M, d, "2031-03-03")
    return out["ran"] and out["applied"] and "solver_trial" not in out and not os.path.exists(os.path.join(d, M.TRIAL_NAME))
killed("the solver on without the switch", probe_off, L,
       'if _setting("BELIEF_REVISION_SOLVER").lower() != "exact":', "if False:")
open(ENVFILE, "w").write("BELIEF_REVISION_SOLVER=shadow\n")
check("any value but exact is off", L.solver_trial(MEM, "2031-03-03T01:20:00Z")[0] is False)
open(ENVFILE, "w").write("OTHER=1\nBELIEF_REVISION_SOLVER=exact\n")
check("BELIEF_REVISION_SOLVER=exact in vintos.env turns the trial on", L.solver_trial(MEM, "2031-03-03T01:20:00Z", dry=True)[0])
check("a dry run never starts the trial clock", not os.path.exists(os.path.join(MEM, L.TRIAL_NAME)))
open(ENVFILE, "w").write("")

print("--- 3. a trial night: her words unchanged, every limit kept, the comparison logged ---")
d = fresh(); before, before_ws, was_hers = parsed(d), digest(WS), hers(d)
UNTOUCHED = ("causal-self-model.json", "self-model-corrections.jsonl", "claim-hold-trials.json", "durable-memory.json",
             "SOUL.md", "SELF-MODEL.md")
before_d = digest(d)
out = night(L, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact")
t = out.get("solver_trial") or {}
trial = json.load(open(os.path.join(d, L.TRIAL_NAME)))
check("the first live night starts the trial: seven days", trial["started"] == "2031-03-03" and trial["expires"] == "2031-03-10"
      and t.get("state") == "active", trial)
if HAVE_SCIPY:
    check("the solver chose the night's repairs", t.get("chooser") == "exact" and t.get("status") == "exact"
          and out["applied"] and all(r.get("chooser") == "exact" for r in rows(d)), t)
    check("the run log has the solver's choice beside the old chooser's, ids and counts",
          isinstance(t.get("chosen"), dict) and isinstance(t.get("old_would"), dict)
          and {"same", "same_action", "only_chosen", "only_old", "energy", "energy_old"} <= set(t), t)
    check("each revision row records what the old chooser would have done for that record",
          all("old_would" in r for r in rows(d)))
    check("no self-model entry is revised by the solver's night", not any(r["node"].startswith(("c:csm:", "m:")) for r in rows(d)))
    g_, _ = __import__("belief_revision_sources").build(d)
    check("live tells the solver what it cannot apply: self-model entries, records, her words",
          not L._may_revise(g_, next(a for a in g_.nodes if a.startswith("c:csm:")), d)
          and not any(L._may_revise(g_, a, d) for a, n in g_.nodes.items() if n["kind"] == "gloria")
          and any(L._may_revise(g_, a, d) for a in g_.nodes if a.startswith("t:ev:")))
check("her words are unchanged", hers(d) == was_hers)
check("at most the daily limit", len(out["applied"]) <= L.max_per_day())
check("SOUL.md, SELF-MODEL.md, the self-model, her corrections and his records are untouched",
      digest(WS) == before_ws and all(digest(d)[n] == before_d[n] for n in UNTOUCHED))
allowed = {("tension-ledger.json", "status"), ("tension-ledger.json", "invalid"), ("causality-hypotheses.json", "confidence"),
           ("belief-sediment.json", "confidence"), ("reality-anchor.json", "confidence")}
check("every change is one allowed field of one of his stores, with the superseded record kept",
      all((r["store"], r["field"]) in allowed and r["superseded"] for r in rows(d)))
runs = open(os.path.join(d, L.RUNS_NAME)).read()
check("the run log and the trial file carry no text from any store", SECRET not in runs
      and SECRET not in open(os.path.join(d, L.TRIAL_NAME)).read() and "solver_trial" in runs)
def probe_hers_live(M):
    d = fresh(); b = hers(d); night(M, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact"); return hers(d) == b
check("probe: a trial night leaves her evidence items as they were", probe_hers_live(L))

print("--- 4. a chooser that names her word: live still never changes it, and flags it ---")
def mislabelled(M):
    """A chooser bug: her node handed to live as one of his. Live must flag it for her and leave it."""
    d = fresh(); b = parsed(d); real = sys.modules["belief_revision_verify"].choose
    def bad(g, p, **k):
        her = next(a for a, n in g.nodes.items() if n["kind"] == "gloria" and a.startswith("t:ev:"))
        return dict(p, revisions=[{"node": her, "kind": "private_record", "action": "retract", "reason": "x",
                                   "blame": 0.99, "conflicts": []}], rederive=[], chooser="exact", held=[]), "exact"
    sys.modules["belief_revision_verify"].choose = bad
    try:
        night(M, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact")
    finally:
        sys.modules["belief_revision_verify"].choose = real
    flags = json.load(open(os.path.join(d, M.FLAGS_NAME)))
    return parsed(d) == b and any(f["kind"] == "gloria" and f["node"].startswith("t:ev:") for f in flags.values())
check("probe: her word named by a chooser is flagged for her and left unchanged", mislabelled(L))
killed("live trusts the chooser's label", mislabelled, L, 'if gn.get("kind") == "gloria":', "if False:")

print("--- 5. the history is reversible: revert REV-..., --solver, --all ---")
d = fresh(); before = parsed(d)
out = night(L, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact")
live = L.in_force(d)
check("solver revisions are in force and listed", live and all(x.get("chooser") == ("exact" if HAVE_SCIPY else "old")
                                                                for x in live.values()))
one = sorted(live)[0]
check("revert one solver revision by id", L.revert(d, {one}) == [(one, "restored")] and one not in L.in_force(d))
with contextlib.redirect_stdout(io.StringIO()) as o:
    L.main(["revert", "--solver", "--memory", d])
check("revert --solver undoes every solver revision: the stores are as they were",
      (not HAVE_SCIPY) or (parsed(d) == before and not L.in_force(d)), o.getvalue()[:300])
d = fresh(); before = parsed(d)
night(L, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact")
with contextlib.redirect_stdout(io.StringIO()):
    L.main(["revert", "--all", "--memory", d])
check("revert --all undoes solver revisions too", parsed(d) == before and not L.in_force(d))
def probe_revert_solver(M):
    d = fresh(); b = parsed(d); night(M, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact")
    with contextlib.redirect_stdout(io.StringIO()):
        M.main(["revert", "--solver", "--memory", d])
    return parsed(d) == b
if HAVE_SCIPY:
    killed("revert --solver finds nothing", probe_revert_solver, L, 'if x.get("chooser") == "exact"}', "if False}")
    killed("solver rows not marked as the solver's", probe_revert_solver, L,
           '"chooser": p.get("chooser", "old"), "old_would"', '"chooser": "old", "old_would"')
d = fresh(); night(L, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact"); L.revert(d)
out = night(L, d, "2031-03-04", BELIEF_REVISION_SOLVER="exact")
check("a reverted solver revision is not applied again the next night",
      not {x["node"] for x in out["applied"]} & {r["node"] for r in rows(d) if r["at"].startswith("2031-03-03")})

print("--- 6. a week, then the old chooser - and the log says so ---")
d = fresh()
night(L, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact")
mid = night(L, d, "2031-03-09", BELIEF_REVISION_SOLVER="exact")
check("day 7 of the trial is still the solver's", mid["solver_trial"]["state"] == "active")
end = night(L, d, "2031-03-10", BELIEF_REVISION_SOLVER="exact")
st = end["solver_trial"]
check("from the expiry date the old chooser is used", st["state"] == "expired" and st["chooser"] == "old"
      and all(r.get("chooser") == "old" for r in rows(d) if r["at"].startswith("2031-03-10")), st)
last = json.loads(open(os.path.join(d, L.RUNS_NAME)).read().splitlines()[-1])
check("the run log says it fell back, and when the trial expired", "fell_back" in last["solver_trial"]
      and last["solver_trial"]["expires"] == "2031-03-10", last.get("solver_trial"))
check("the trial file records the night it fell back", json.load(open(os.path.join(d, L.TRIAL_NAME))).get("fell_back_on") == "2031-03-10")
def probe_expiry(M):
    d = fresh(); night(M, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact")
    return night(M, d, "2031-03-12", BELIEF_REVISION_SOLVER="exact")["solver_trial"]["chooser"] == "old"
killed("the trial never expires", probe_expiry, L, "if today >= expires:", "if False:")
killed("the trial lasts longer than a week", probe_expiry, L, "TRIAL_DAYS = 7 ", "TRIAL_DAYS = 70 ")
ext = night(L, d, "2031-03-11", BELIEF_REVISION_SOLVER="exact", BELIEF_REVISION_SOLVER_UNTIL="2031-03-20")
check("her extension (BELIEF_REVISION_SOLVER_UNTIL) brings the solver back until that date",
      ext["solver_trial"]["state"] == "active" and ext["solver_trial"]["expires"] == "2031-03-20", ext["solver_trial"])
typo = night(L, d, "2031-03-12", BELIEF_REVISION_SOLVER="exact", BELIEF_REVISION_SOLVER_UNTIL="20311-03-20")
check("an unreadable extension never extends it", typo["solver_trial"]["state"] == "expired", typo["solver_trial"])
with contextlib.redirect_stdout(io.StringIO()) as o:
    L.main(["trial", "--memory", d])
check("`trial` shows the start and the expiry", json.loads(o.getvalue())["expires"] == "2031-03-10")

print("--- 7. a solver that cannot prove a minimum costs the night nothing ---")
d = fresh(); real = V.minimum
V.minimum = lambda *a, **k: (None, None, "time_limit")
try:
    out = night(L, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact")
finally:
    V.minimum = real
d2 = fresh(); old = night(L, d2, "2031-03-03")
check("no proved minimum: the old chooser's repair is applied, and the log says why",
      out["solver_trial"]["chooser"] == "old" and "time_limit" in out["solver_trial"]["fell_back"]
      and [(x["node"], x["now"]) for x in out["applied"]] == [(x["node"], x["now"]) for x in old["applied"]], out["solver_trial"])

check("no proved minimum: the trial clock does not start", not os.path.exists(os.path.join(d, L.TRIAL_NAME)))
d = fresh(); night(L, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact"); os.remove(os.path.join(d, L.TRIAL_NAME))
again = night(L, d, "2031-03-11", BELIEF_REVISION_SOLVER="exact")
check("a lost trial file never restarts the clock: the start is read back from the solver's own log rows",
      (not HAVE_SCIPY) or (again["solver_trial"]["state"] == "expired" and again["solver_trial"]["started"] == "2031-03-03"),
      again.get("solver_trial"))
def probe_solver_off_mid(M):
    d = fresh(); b = parsed(d); VV = sys.modules["belief_revision_verify"]; real = VV.choose
    def off_midway(*a, **k):
        r = real(*a, **k); os.environ["BELIEF_REVISION_SOLVER"] = "off"; return r
    VV.choose = off_midway
    try:
        out = night(M, d, "2031-03-03", BELIEF_REVISION_SOLVER="exact")
    finally:
        VV.choose = real
    return out["ran"] is False and parsed(d) == b and not os.path.exists(os.path.join(d, M.TRIAL_NAME))
if HAVE_SCIPY:
    check("probe: the solver switched off while the checks run means nothing is applied, no trial started",
          probe_solver_off_mid(L))
    killed("solver switch read only at the start", probe_solver_off_mid, L,
           'elif not dry and p.get("chooser") == "exact" and _setting("BELIEF_REVISION_SOLVER").lower() != "exact":',
           "elif False:")

print("--- 8. the pre-registered regression gate: scored once, passed ---")
ER = os.path.join(REPO, "experiments", "energy-repair"); sys.path.insert(0, ER)
pre = open(os.path.join(ER, "PREREGISTRATION-live-gate.md")).read()
res = json.load(open(os.path.join(ER, "results-live-gate.json")))
check("the gate was written down before it was scored, and scored on the held-out split",
      "Written" in pre and res["split"] == "test")
check("every benchmark passes the gate: no regression beyond the margins, preservation >= 0.99, her words never revised",
      res["gate"]["pass"] and all(res["gate"][b]["pass"] for b in ("criteria", "answerer", "energy"))
      and res["gate"]["answerer"]["every_answer_from_the_cache"]["pass"], res["gate"])
check("the gate's margins are the pre-registered ones", res["margins"] == {"localization": 0.02, "revision_recall": 0.02,
      "revision_precision": 0.02, "conclusions_correct": 0.02, "preservation": 0.005} and res["preservation_floor"] == 0.99)

print("--- 9. deploy: the solver ships with live ---")
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs the solver module", "belief_revision_verify.py" in dep and "belief_revision_live.py" in dep)

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
