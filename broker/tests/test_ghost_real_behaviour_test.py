#!/usr/bin/env python3
"""New Ghost Branch hypotheses are tested on his real behaviour, and existing ones can be restated the same way
(Gloria, 7 November). A ghost row's `test` used to watch for a lean "producing movement" when a thread type
recurs, which only another ghost run can show. Now it asks whether, in real conversation after that kind of
moment, he takes the lean and the exchange goes better. Tenure (32 days), graduation thresholds and the
nightly evaluator are unchanged. scripts/ghost_test_restate.py restates existing rows: a dry run by default
that prints only counts and ids; --apply writes after a backup.

Scratch HOME; no model is called; every socket is refused."""
import importlib.util, json, os, shutil, socket, subprocess, sys, tempfile, types
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-ghost-tests-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(HOME, ".vintos", "workspace", "memory"); os.makedirs(MEM, exist_ok=True)
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
def no_post(*a, **k): raise AssertionError("no model is called from this suite")
sys.modules["requests"] = types.SimpleNamespace(post=no_post, get=no_post)
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

spec = importlib.util.spec_from_file_location("ghost_real_test_fixture", os.path.join(REPO, "scripts", "ghost-branches.py"))
GB = importlib.util.module_from_spec(spec); spec.loader.exec_module(GB)
STORE = os.path.join(MEM, "causality-hypotheses.json")
check("the causality store is scratch", GB.CAUSALITY_FILE == STORE)
check("the bin and scripts copies of ghost-branches stay one file",
      open(os.path.join(REPO, "bin", "ghost-branches.py")).read() == open(os.path.join(REPO, "scripts", "ghost-branches.py")).read())

# ── a new row ──
lean = next(a for a in GB.DEFAULT_AXES if a["id"] == "more_brazen")
row = GB.seed_causality_hypothesis({"thread": "fixture thread"}, lean, "fixture output", "relational_tension",
                                   primary_pattern="recursive_abstraction")
t = (row or {}).get("test", "")
check("a new ghost row is seeded", row is not None and row.get("source") == "ghost_branch")
check("its test is about real conversation, not ghost runs",
      "real conversation" in t and "ghost runs and rehearsals do not count" in t, t)
check("it names the moment, the usual pattern and the lean",
      "relational-tension" in t and "recursive abstraction" in t and "'more brazen'" in t, t)
check("it asks whether the exchange goes better, with yes, no and unconfirmed defined",
      "go better" in t and "Yes if" in t and "no if" in t and "unconfirmed if" in t, t)
check("the row says how its test is framed", row.get("test_basis") == "real_behaviour")
check("the hypothesis wording is unchanged",
      row.get("hypothesis") == "more brazen reduces recursive_abstraction avoidance in relational-tension threads", row.get("hypothesis"))

spec = importlib.util.spec_from_file_location("causality_ghost_tests", os.path.join(REPO, "scripts", "causality-engine.py"))
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
check("tenure and graduation thresholds are unchanged",
      C.GHOST_BRANCH_TENURE_DAYS == 32 and C.ORDINARY_TENURE_DAYS == 7 and C.MIN_NIGHTLY_EVALUATIONS == 7
      and C.MIN_SUPPORTING_OCCASIONS == 2)

# ── the migration over existing rows ──
SECRET = "PRIVATE-HYPOTHESIS-TEXT"
def old(i, **kw):
    h = {"id": "ghost_old%d" % i, "source": "ghost_branch", "thread_type": "relational", "successful_lean": "higher_curiosity",
         "failed_primary_pattern": "humor_deflection", "hypothesis": SECRET + " %d" % i,
         "test": SECRET + " old test %d" % i, "formed_date": "2026-10-20", "marks": [{"date": "2026-10-21"}],
         "graduated": False, "hypothesis_id": "CH-old%d" % i}
    h.update(kw); return h
db = {"hypotheses": [old(1), old(2), old(3, successful_lean="no_such_lean"), old(4, graduated=True),
                     dict(old(5), test_basis="real_behaviour"),
                     {"id": "other1", "source": "causality_engine", "hypothesis": SECRET, "test": SECRET}]}
json.dump(db, open(STORE, "w"))
before = open(STORE).read()
def run(*args):
    return subprocess.run([sys.executable, os.path.join(REPO, "scripts", "ghost_test_restate.py"), *args],
                          env=dict(os.environ, HOME=HOME), capture_output=True, text=True, timeout=60)
r = run()
check("dry run: counts and ids", r.returncode == 0 and "ghost_branch rows: 5 | to restate: 2 | skipped: 3" in r.stdout
      and "ghost_old1" in r.stdout and "ghost_old2" in r.stdout and "DRY RUN" in r.stdout, r.stdout + r.stderr)
check("dry run: never prints hypothesis or test text", SECRET not in r.stdout + r.stderr and "humor" not in r.stdout)
check("dry run: writes nothing", open(STORE).read() == before
      and not [f for f in os.listdir(MEM) if ".bak-ghost-restate-" in f])

r = run("--apply")
after = json.load(open(STORE))["hypotheses"]
by = {h["id"]: h for h in after}
check("apply: the two eligible rows are restated the same way new rows are written",
      all(by[i]["test"] == GB.real_behaviour_test("higher curiosity", "humor_deflection", "relational")
          and by[i]["test_basis"] == "real_behaviour" for i in ("ghost_old1", "ghost_old2")), r.stdout + r.stderr)
check("apply: the old test is kept, nothing else on the row moves",
      by["ghost_old1"]["test_before_restate"] == SECRET + " old test 1" and by["ghost_old1"]["hypothesis"] == SECRET + " 1"
      and by["ghost_old1"]["hypothesis_id"] == "CH-old1" and by["ghost_old1"]["marks"] == [{"date": "2026-10-21"}])
check("apply: unknown-lean, graduated, already-restated and non-ghost rows are untouched",
      by["ghost_old3"]["test"] == SECRET + " old test 3" and by["ghost_old4"]["test"] == SECRET + " old test 4"
      and "test_before_restate" not in by["ghost_old5"] and by["other1"]["test"] == SECRET)
check("apply: a backup was written first and no text was printed",
      len([f for f in os.listdir(MEM) if ".bak-ghost-restate-" in f]) == 1 and SECRET not in r.stdout + r.stderr, r.stdout)
r = run()
check("a second dry run finds nothing left to restate", "to restate: 0" in r.stdout, r.stdout)

shutil.rmtree(HOME, ignore_errors=True)
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
