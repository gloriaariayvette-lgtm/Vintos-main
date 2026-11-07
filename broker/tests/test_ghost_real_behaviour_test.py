#!/usr/bin/env python3
"""New Ghost Branch hypotheses are tested on his real behaviour, and existing ones can be restated the same way
(Gloria, 7 November; wording review the same day). A ghost row's `test` used to watch for a lean "producing
movement" when a thread type recurs, which only another ghost run can show. Now it asks whether, in real
conversation, he takes the lean and stays with the subject, judged from his own words only, with two kinds of
no (fell back / closed after the lean) that reach the ledger as different outcomes. Only conversation lines may
decide it. The wording is versioned (real_behaviour_v2) so a restate reaches rows on an older wording, and a
restated row counts only marks from its restate date (older marks are kept). Tenure (32 days) and graduation
thresholds are unchanged. scripts/ghost_test_restate.py is a dry run by default that prints only counts and ids;
--apply writes after a backup. Gloria decides whether it runs.

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
for name in ("ghost-branches.py", "causality-engine.py"):
    check("the bin and scripts copies of %s stay one file" % name,
          open(os.path.join(REPO, "bin", name)).read() == open(os.path.join(REPO, "scripts", name)).read())

# ── a new row ──
lean = next(a for a in GB.DEFAULT_AXES if a["id"] == "more_brazen")
row = GB.seed_causality_hypothesis({"thread": "fixture thread"}, lean, "fixture output", "relational_tension",
                                   primary_pattern="recursive_abstraction")
t = (row or {}).get("test", "")
check("a new ghost row is seeded", row is not None and row.get("source") == "ghost_branch")
check("its test is about real conversation, not ghost runs, inner notes or feeling readings",
      "real conversation with Gloria only" in t and "ghost runs, rehearsals, his inner notes and feeling readings do not count" in t
      and "cite only lines of the conversation itself" in t, t)
check("it names the moment, the likely pull and the lean with what the lean looks like",
      'a moment of the "relational-tension" kind' in t and "recursive abstraction is the likely pull for him" in t
      and 'the "more brazen" lean (he says the thing plainly instead of hedging it)' in t, t)
check("it judges only his own words, never how Gloria felt",
      "Judge only his own words; do not guess how Gloria felt" in t and "go better" not in t and "worse" not in t, t)
check("no wording that claims a habit, a later time or a cause",
      all(w not in t for w in ("usually", "after a", "better for it")), t)
check("two kinds of no, and outside endings and can't-tell are unconfirmed",
      "NO, fell back" in t and '(no_kind "fell_back")' in t and '(no_kind "closed_after_lean")' in t
      and "ended for reasons outside it" in t and "too short to tell" in t and "he took a different lean" in t, t)
check("taking the lean while nothing else changed is a yes, not a gap", "even if nothing else changed" in t, t)
check("the row says how its test is framed (versioned)", row.get("test_basis") == "real_behaviour_v2" == GB.TEST_BASIS)
check("the hypothesis wording is unchanged",
      row.get("hypothesis") == "more brazen reduces recursive_abstraction avoidance in relational-tension threads", row.get("hypothesis"))

# ── render edge cases ──
r1 = GB.real_behaviour_test("more brazen", "**humor_deflection**.,", "", "more_brazen")
check("an empty thread type does not render as 'a this kind of moment'", "this kind of" not in r1 and "a moment like that" in r1, r1)
check("a markdown-wrapped model label is cleaned", "humor deflection is the likely pull" in r1 and "**" not in r1 and ".," not in r1, r1)
r2 = GB.real_behaviour_test("higher curiosity", "unknown_pattern", "unclassified", "higher_curiosity")
check("sentinels read as missing, not as words", "unknown pattern" not in r2 and "unclassified" not in r2
      and "an avoidance move is the likely pull" in r2, r2)
r3 = GB.real_behaviour_test("less oriented toward Gloria's reception", "x", "attachment_conflict", "reduced_gloria_orientation")
check("no a/an article error before a vowel", "a attachment" not in r3 and 'a moment of the "attachment-conflict" kind' in r3, r3)
check("a label with an apostrophe reads cleanly in double quotes", '"less oriented toward Gloria\'s reception" lean' in r3, r3)
r4 = GB.real_behaviour_test("custom lean", "x", "y", "custom_axis")
check("a custom axis with no gloss falls back to its label", 'the "custom lean" lean, and' in r4, r4)
GB.call_llm = lambda *a, **k: "**Humor_Deflection**.,"
check("detect_primary_pattern cleans the model's label", GB.detect_primary_pattern("x") == "humor_deflection")
LONG = "very_long_pattern_name_that_keeps_going_beyond_forty_characters"
GB.call_llm = lambda *a, **k: LONG
cut = GB.detect_primary_pattern("x")
check("a long label is cut at a word boundary", len(cut) <= 40 and not cut.endswith("_")
      and all(w in LONG.split("_") for w in cut.split("_")), cut)

spec = importlib.util.spec_from_file_location("causality_ghost_tests", os.path.join(REPO, "scripts", "causality-engine.py"))
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
check("tenure and graduation thresholds are unchanged",
      C.GHOST_BRANCH_TENURE_DAYS == 32 and C.ORDINARY_TENURE_DAYS == 7 and C.MIN_NIGHTLY_EVALUATIONS == 7
      and C.MIN_SUPPORTING_OCCASIONS == 2)

# ── the nightly ledger: two kinds of no, marks tagged, counted from the restate ──
def ghost_row(**kw):
    h = {"id": "ghost_n1", "hypothesis_id": "CH-n1", "source": "ghost_branch", "test_basis": "real_behaviour_v2",
         "formed_date": "2026-10-01", "marks": []}
    h.update(kw); return h
def ev(c, source="interactions"):
    return {"id": "E-" + c * 20, "fingerprint": "F-" + c, "source": source, "text": "a line"}
h = ghost_row()
C._record_nightly(h, "2026-11-08", "no", items=[ev("a")], no_kind="closed_after_lean")
C._record_nightly(h, "2026-11-09", "no", items=[ev("b")], no_kind="fell_back")
C._record_nightly(h, "2026-11-10", "no", items=[ev("c")])
outs = [m["outcome"] for m in h["marks"]]
check("a no after taking the lean is not recorded as defaulted",
      outs == ["closed_after_lean", "defaulted", "no_unspecified"] and h["marks"][0]["no_kind"] == "closed_after_lean", outs)
check("marks are tagged with the test basis they were judged under",
      all(m.get("test_basis") == "real_behaviour_v2" for m in h["marks"]))
legacy = {"id": "c1", "hypothesis_id": "CH-c1", "source": "causality_engine", "formed_date": "2026-10-01", "marks": []}
C._record_nightly(legacy, "2026-11-08", "no", items=[ev("a")])
check("other hypotheses keep defaulted for a no", legacy["marks"][0]["outcome"] == "defaulted"
      and legacy["marks"][0]["test_basis"] == "original", legacy["marks"])
check("every kind of no still counts against the legacy net",
      C._mark_net({"marks": [{"outcome": o} for o in ("closed_after_lean", "defaulted", "no_unspecified")]}) == -3)
r = ghost_row(test_restated_at="2026-11-09T10:00:00", marks=[
    {"schema_version": C.CAUSALITY_SCHEMA, "date": "2026-11-01", "verdict": "yes", "evidence_ids": ["E-x"], "lineage_state": "eligible"},
    {"schema_version": C.CAUSALITY_SCHEMA, "date": "2026-11-09", "verdict": "no", "evidence_ids": ["E-y"], "lineage_state": "eligible"}])
gr = C.graduation_readiness(r, today="2026-11-10")
check("a restated row counts only marks from the restate date, and keeps the older ones",
      gr["yes"] == 0 and gr["no"] == 1 and gr["nightly_evaluations"] == 1 and len(r["marks"]) == 2, gr)

# the nightly judge: only conversation lines decide a real-behaviour test
inner = dict(ev("d", "inner"), day="2026-11-11"); talk = dict(ev("e"), day="2026-11-11")
C._build_evidence_catalog = lambda ctx, day: [inner, talk]
prompts = []
def fake_ask(prompt, **k):
    prompts.append(prompt)
    return json.dumps([
        {"n": 1, "verdict": "yes", "evidence_ids": [inner["id"]], "evidence": "only an inner note was cited for this one"},
        {"n": 2, "verdict": "no", "no_kind": "closed_after_lean", "evidence_ids": [talk["id"]],
         "evidence": "a real conversation line was cited for this one"}])
C.ask_llm = fake_ask
db = {"hypotheses": [ghost_row(id="ghost_j1", hypothesis_id="CH-j1"), ghost_row(id="ghost_j2", hypothesis_id="CH-j2")]}
C.test_existing_hypotheses(db, {}, today="2026-11-11", context={})
m1, m2 = db["hypotheses"][0]["marks"][-1], db["hypotheses"][1]["marks"][-1]
check("a yes cited only from his inner notes is unconfirmed", m1["verdict"] == "unconfirmed"
      and m1["reason"] == "conversation_evidence_missing", m1)
check("the judge's no_kind reaches the ledger", m2["verdict"] == "no" and m2["outcome"] == "closed_after_lean", m2)
check("the judge is told about the kinds of no", prompts and "no_kind" in prompts[0])

# ── the migration over existing rows ──
SECRET = "PRIVATE-HYPOTHESIS-TEXT"
def old(i, **kw):
    h = {"id": "ghost_old%d" % i, "source": "ghost_branch", "thread_type": "relational", "successful_lean": "higher_curiosity",
         "failed_primary_pattern": "humor_deflection", "hypothesis": "higher curiosity " + SECRET + " %d" % i,
         "test": SECRET + " old test %d" % i, "formed_date": "2026-10-20", "marks": [{"date": "2026-10-21"}],
         "graduated": False, "hypothesis_id": "CH-old%d" % i}
    h.update(kw); return h
db = {"hypotheses": [old(1), old(2), old(3, successful_lean="no_such_lean"), old(4, graduated=True),
                     old(5, test_basis="real_behaviour", test_before_restate=SECRET + " first test 5"),
                     old(6, status="graduated"), old(7, status="retired"),
                     old(8, hypothesis="a relabelled lean " + SECRET),
                     old(9, test_basis="real_behaviour_v2"),
                     {"id": "other1", "source": "causality_engine", "hypothesis": SECRET, "test": SECRET}]}
json.dump(db, open(STORE, "w"))
before = open(STORE).read()
def run(*args):
    return subprocess.run([sys.executable, os.path.join(REPO, "scripts", "ghost_test_restate.py"), *args],
                          env=dict(os.environ, HOME=HOME), capture_output=True, text=True, timeout=60)
r = run("--aply")
check("an unknown argument is refused, nothing done", r.returncode == 2 and open(STORE).read() == before, r.stdout)
r = run()
check("dry run: counts and ids", r.returncode == 0 and "ghost_branch rows: 9 | to restate: 3 | skipped: 6" in r.stdout
      and "ghost_old1" in r.stdout and "ghost_old5" in r.stdout and "DRY RUN" in r.stdout, r.stdout + r.stderr)
check("dry run: graduated, retired and relabelled rows are skipped with their reasons",
      "skipped (graduated): 2" in r.stdout and "skipped (retired): 1" in r.stdout and "skipped (label_mismatch): 1" in r.stdout
      and "skipped (already_current): 1" in r.stdout and "skipped (lean_unknown): 1" in r.stdout, r.stdout)
check("dry run: never prints hypothesis or test text", SECRET not in r.stdout + r.stderr and "humor" not in r.stdout)
check("dry run: writes nothing", open(STORE).read() == before
      and not [f for f in os.listdir(MEM) if ".bak-ghost-restate-" in f])

r = run("--apply")
after = json.load(open(STORE))["hypotheses"]
by = {h["id"]: h for h in after}
want = GB.real_behaviour_test("higher curiosity", "humor_deflection", "relational", "higher_curiosity")
check("apply: eligible rows, and a row on the older real-behaviour wording, are restated the way new rows are written",
      all(by[i]["test"] == want and by[i]["test_basis"] == "real_behaviour_v2" and by[i].get("test_restated_at")
          for i in ("ghost_old1", "ghost_old2", "ghost_old5")), r.stdout + r.stderr)
check("apply: the first replaced test is kept, nothing else on the row moves",
      by["ghost_old1"]["test_before_restate"] == SECRET + " old test 1" and by["ghost_old5"]["test_before_restate"] == SECRET + " first test 5"
      and by["ghost_old1"]["hypothesis"] == "higher curiosity " + SECRET + " 1"
      and by["ghost_old1"]["hypothesis_id"] == "CH-old1" and by["ghost_old1"]["marks"] == [{"date": "2026-10-21"}])
check("apply: skipped and non-ghost rows are untouched",
      all(by["ghost_old%d" % i]["test"] == SECRET + " old test %d" % i for i in (3, 4, 6, 7, 8, 9))
      and by["other1"]["test"] == SECRET)
check("apply: a backup was written first and no text was printed",
      len([f for f in os.listdir(MEM) if ".bak-ghost-restate-" in f]) == 1 and SECRET not in r.stdout + r.stderr, r.stdout)
r = run()
check("a second dry run finds nothing left to restate", "to restate: 0" in r.stdout, r.stdout)

shutil.rmtree(HOME, ignore_errors=True)
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
