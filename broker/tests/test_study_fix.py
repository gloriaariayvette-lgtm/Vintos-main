#!/usr/bin/env python3
"""He fixes his own code in the Study (Gloria, 2026-10-03). Exercised against a throwaway git repository standing
in for GitHub: Fable, the test suite, the deploy, Slack, ntfy and the house are stubs that record what they were
given. Scratch HOME; no socket opens; ~/Vintos-main, the real workbench and the real queue are never touched."""
import json, os, socket, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="study-fix-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_STUDY_WORKBENCH"] = os.path.join(HOME, "workbench")
os.environ["VINTOS_CHECKOUT"] = os.path.join(HOME, "Vintos-main")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import study_fix as S
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))

check("every path is a scratch one", all(p.startswith(HOME) for p in (S.QUEUE, S.WORKBENCH, S.CHECKOUT, S.LOCK)))

# a stand-in GitHub: a bare repository with the branch, and her checkout cloned from it
def git(*a, cwd=None):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"] + list(a),
                          cwd=cwd, capture_output=True, text=True, check=True).stdout
ORIGIN = os.path.join(HOME, "origin.git"); SEED = os.path.join(HOME, "seed")
git("init", "-q", "--bare", ORIGIN); git("init", "-q", SEED)
os.makedirs(os.path.join(SEED, "scripts")); os.makedirs(os.path.join(SEED, "broker", "tests"))
open(os.path.join(SEED, "scripts", "greet.py"), "w").write("def greet():\n    return 'helo'\n")
open(os.path.join(SEED, "scripts", "subconscious_drift.py"), "w").write("X = 1\n")
open(os.path.join(SEED, "broker", "tests", "test_old.py"), "w").write("assert True\n")
open(os.path.join(SEED, "CLAUDE.md"), "w").write("rules: stub anything that sends\n")
git("add", "-A", cwd=SEED); git("commit", "-q", "-m", "seed", cwd=SEED)
git("checkout", "-q", "-b", S.DEFAULT_BRANCH, cwd=SEED); git("push", "-q", ORIGIN, S.DEFAULT_BRANCH, cwd=SEED)
git("clone", "-q", "--branch", S.DEFAULT_BRANCH, ORIGIN, S.CHECKOUT)
def origin_log():
    return git("log", "--format=%s", S.DEFAULT_BRANCH, cwd=ORIGIN)

# --- asking -------------------------------------------------------------------------------------------
row, why = S.request("greet() says 'helo'; it should say 'hello'")
check("a fix he names is queued", row and row["state"] == "queued" and row["id"].startswith("SF-"), why)
check("the same fix twice is not queued twice", S.request("greet() says 'helo'; it should say 'hello'")[0] is None)
check("a fix too vague to act on is refused", S.request("fix it")[1].startswith("say what is broken"))
S.request("second fix of the day, the long description"); S.request("third fix of the day, the long description")
check("three a day", S.request("a fourth fix of the day, the long description") == (None, "today's 3 Study fixes are used; more tomorrow"))
# Gloria, 2026-10-05: "Let's reset his study fixes for the day so he can work."
check("the reset is kept in the scratch workspace", S.RESET.startswith(HOME), S.RESET)
_before = [dict(r) for r in S._load()]
check("Gloria's reset gives him today's three again", S.reset_today() == 3)
check("... so the fourth of the day is queued", S.request("a fourth fix of the day, the long description")[0] is not None)
check("... and the three already asked keep their records as they were", S._load()[:3] == _before)
json.dump({"date": "2000-01-01", "at": "2000-01-01T00:00:00"}, open(S.RESET, "w"))
check("a reset from another day gives nothing today", S.used_today() == 4)
os.remove(S.RESET)
rows = S._load(); rows[:] = rows[:1]; S._save(rows)

# --- what he may not change ---------------------------------------------------------------------------
for path, want in (("scripts/jepa_predictor.py", "his subconscious and JEPA"), ("scripts/subconscious-drift.py", "his subconscious and JEPA"),
                   ("scripts/env_file.py", "keys and secrets"), ("scripts/food_order.py", "money and payments"),
                   ("scripts/deploy-atelier.sh", "the safety gates"), ("scripts/study_fix.py", "the safety gates"),
                   ("CLAUDE.md", "the safety gates"), ("scripts/forge_loop_runtime.py", "the safety gates"),
                   ("scripts/forge_loop_ui.html", "the safety gates")):
    check("%s is protected (%s)" % (path, want), S.protected(path) == want, S.protected(path))
check(".claude/settings.json is protected, written with or without ./", S.protected(".claude/settings.json") == "keys and secrets"
      and S.protected("./.claude/settings.json") == "keys and secrets")
for path in ("scripts/relational_mismatch.py", "bin/emotional-reflection.py", "scripts/dot_channel.py", "bin/server.py"):
    check("%s is his to change (blush and reflection included)" % path, S.protected(path) == "")

S.reset_workbench()
WB = S.WORKBENCH
NEWTEST = {"path": "broker/tests/test_greet_hello.py", "content": "assert True\n"}
def refused(plan):
    try:
        S.apply_edits(plan, WB); return ""
    except ValueError as exc:
        return str(exc)
    finally:
        S.reset_workbench()
check("a protected file is refused, and says it needs Gloria",
      "his subconscious and JEPA: that needs Gloria" in refused({"edits": [{"path": "scripts/subconscious_drift.py", "old": "X = 1", "new": "X = 2"}], "new_files": [NEWTEST]}))
check("an existing test may not be changed", "an existing test" in refused(
      {"edits": [{"path": "broker/tests/test_old.py", "old": "assert True", "new": "pass"}], "new_files": [NEWTEST]}))
check("a fix without a new test is refused", "one new test" in refused({"edits": [{"path": "scripts/greet.py", "old": "helo", "new": "hello"}]}))
check("a path outside the repository is refused", "not inside the repository" in refused(
      {"edits": [{"path": "../outside.py", "old": "a", "new": "b"}], "new_files": [NEWTEST]}))
check("an old text that is not exactly once is refused", "found 0 times" in refused(
      {"edits": [{"path": "scripts/greet.py", "old": "nope", "new": "x"}], "new_files": [NEWTEST]}))

# --- one fix, start to live -----------------------------------------------------------------------------
POSTS, SENT, ASKS = [], [], []
GOOD = {"summary": "greet() now says hello.", "edits": [{"path": "scripts/greet.py", "old": "'helo'", "new": "'hello'"}],
        "new_files": [NEWTEST]}
def fable_seq(*answers):
    seq = list(answers)
    def ask(system, user):
        ASKS.append(user); return json.dumps(seq.pop(0))
    return ask
DEPLOYED = []
def deploy(run):
    DEPLOYED.append(1); return "...\n  rollback: bash /home/gloria/.vintos/backups/atelier-x/restore.sh\ndeploy OK\n"
SUITE = []
def suite_seq(*results):
    seq = list(results)
    def suite(root):
        SUITE.append(open(os.path.join(root, "scripts", "greet.py")).read()); return seq.pop(0)
    return suite

row = S._load()[0]
S.work(row, ask=fable_seq({"read": ["scripts/greet.py"], "grep": ["helo"]}, GOOD), post=POSTS.append,
       suite=suite_seq([]), deploy=deploy)
check("Fable read what it asked for before fixing", "== scripts/greet.py ==" in ASKS[1] and "return 'helo'" in ASKS[1] and "grep 'helo'" in ASKS[1])
check("Fable is given the repository's rules", "rules: stub anything that sends" in ASKS[0])
check("the whole suite ran on the fixed code", SUITE == ["def greet():\n    return 'hello'\n"], SUITE)
check("it was committed as his and pushed to the branch", origin_log().splitlines()[0].startswith("Study fix %s: greet() now says hello." % row["id"]), origin_log())
check("it was deployed the ordinary way, and is watched with its restore script",
      DEPLOYED and row["state"] == "watching" and row["restore"] == "/home/gloria/.vintos/backups/atelier-x/restore.sh", row)
check("Slack heard it start, and dot was told to keep watch, what changed, and how to undo it",
      "Study fix %s started" % row["id"] in POSTS[0] and POSTS[-1].startswith("<@") and "is live" in POSTS[-1]
      and "scripts/greet.py" in POSTS[-1] and "bash /home/gloria/.vintos/backups/atelier-x/restore.sh" in POSTS[-1]
      and "Its new test: broker/tests/test_greet_hello.py" in POSTS[-1] and "rule 12" in POSTS[-1], POSTS)

# --- the watch ------------------------------------------------------------------------------------------
RUNS = []
real_sh = S.sh
def run_rec(args, cwd=None, timeout=900, check=True):
    RUNS.append(args); return real_sh(args, cwd=cwd, timeout=timeout, check=check) if args[0] == "git" else \
        type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
S.watch(row, run=run_rec, post=POSTS.append, send=SENT.append, get=lambda u: True, now=row["live_at"] + 600)
check("while the house answers, it stays", row["state"] == "watching" and row["misses"] == 0)
S.watch(row, run=run_rec, post=POSTS.append, send=SENT.append, get=lambda u: True, now=row["live_at"] + 3601)
check("an hour live without trouble: kept", row["state"] == "done" and "it stays" in POSTS[-1])

row2, _ = S.request("greet() should greet by name when given one")
row2 = next(r for r in S._load() if r["id"] == row2["id"])
GOOD2 = {"summary": "greet() greets by name.", "edits": [{"path": "scripts/greet.py", "old": "def greet():\n    return 'hello'",
         "new": "def greet(name=''):\n    return ('hello ' + name).strip()"}], "new_files": [{"path": "broker/tests/test_greet_name.py", "content": "assert True\n"}]}
S.work(row2, ask=fable_seq(GOOD2), post=POSTS.append, suite=suite_seq([]), deploy=deploy)
S.watch(row2, run=run_rec, post=POSTS.append, send=SENT.append, get=lambda u: False, now=row2["live_at"] + 600)
check("one silent check is not enough to undo", row2["state"] == "watching" and row2["misses"] == 1)
S.watch(row2, run=run_rec, post=POSTS.append, send=SENT.append, get=lambda u: False, now=row2["live_at"] + 1200)
check("the house silent twice: undone at once with its restore script", row2["state"] == "rolled_back"
      and ["bash", "/home/gloria/.vintos/backups/atelier-x/restore.sh"] in RUNS, RUNS[-3:])
check("and reverted in git, so the next deploy does not bring it back", origin_log().splitlines()[0].startswith("Revert"), origin_log())
check("Gloria gets one line, saying nothing is needed from her", len(SENT) == 1 and "Nothing is needed from you" in SENT[0], SENT)
fails = [json.loads(l) for l in open(os.path.join(S.MEMORY, "organ-failures.jsonl"))]
check("an undone fix is kept for the morning check", any(f["organ"] == "study" for f in fails), fails)

# --- the watch checks the change itself, not only the house --------------------------------------------
def fake_run(test_rc=0, active=(), journal=""):
    def run(args, cwd=None, timeout=900, check=True):
        RUNS.append(args)
        if args[0] == "git":
            return real_sh(args, cwd=cwd, timeout=timeout, check=check)
        out, rc = "", 0
        if "run_isolated_test.py" in " ".join(args): rc = test_rc; out = "FAIL greet says hullo" if test_rc else "1/1"
        elif args[:3] == ["systemctl", "--user", "is-active"]: out = "active" if args[3] in active else "inactive"
        elif args[0] == "journalctl": out = journal
        return type("R", (), {"returncode": rc, "stdout": out, "stderr": ""})()
    return run
for label, kw, why in (("its own test failing live", {"test_rc": 1}, "its own test fails live (broker/tests/test_greet_live.py)"),
                       ("a service that was up stopping", {"active": ()}, "vintos-server.service stopped"),
                       ("an error in a file it changed", {"active": ("vintos-server.service",),
                        "journal": 'Traceback (most recent call last):\n  File "/home/gloria/.vintos/workspace/scripts/greet.py", line 2, in greet'},
                        'an error in a file it changed: File "/home/gloria/.vintos/workspace/scripts/greet.py", line 2')):
    r5, _ = S.request("greet() check number %s, the long description" % label)
    r5 = next(r for r in S._load() if r["id"] == r5["id"])
    S.work(r5, ask=fable_seq({"summary": "s", "edits": [{"path": "scripts/greet.py", "old": "return", "new": "return"}],
                              "new_files": [{"path": "broker/tests/test_greet_live.py", "content": "assert True\n"}]}),
           run=fake_run(active=("vintos-server.service",)), post=POSTS.append, suite=suite_seq([]), deploy=deploy)
    check("%s: services up at go-live are recorded" % label, r5.get("services") == ["vintos-server.service"], r5.get("services"))
    S.watch(r5, run=fake_run(**kw), post=POSTS.append, send=SENT.append, get=lambda u: True, now=r5["live_at"] + 600)
    check("%s undoes it at once, saying why" % label, r5["state"] == "rolled_back" and why in POSTS[-1], (r5["state"], POSTS[-1]))
    rows = S._load(); rows[:] = [r for r in rows if r.get("asked", "")[:10] != S._today() or r["state"] != "queued"]; S._save(rows)
    rr = S._load()
    for x in rr:
        if str(x.get("asked", ""))[:10] == S._today(): x["asked"] = "2026-01-01T00:00:00"
    S._save(rr)

# --- failing, repairing, declining ----------------------------------------------------------------------
before = origin_log()
row3, _ = S.request("greet() should say good morning before noon")
row3 = next(r for r in S._load() if r["id"] == row3["id"])
BAD = {"summary": "x", "edits": [{"path": "scripts/greet.py", "old": "'hello'", "new": "'hullo'"}],
       "new_files": [{"path": "broker/tests/test_greet_morning.py", "content": "assert False\n"}]}
S.work(row3, ask=fable_seq(BAD, BAD, BAD), post=POSTS.append, suite=suite_seq(*([[("test_greet_morning.py", "AssertionError")]] * 3)), deploy=deploy)
check("a fix that fails its tests three times does not land, and nothing is pushed",
      row3["state"] == "failed" and origin_log() == before and "did not pass its tests after 3 tries" in POSTS[-1], (row3["state"], POSTS[-1]))
check("Fable was shown what failed before each retry", "IT DID NOT PASS" in ASKS[-1] and "AssertionError" in ASKS[-1])
check("the workbench is left clean", git("status", "--porcelain", cwd=WB) == "")

rows = S._load(); rows[:] = [r for r in rows if r["state"] != "queued"]; S._save(rows)
row4, _ = S.request("change how the JEPA heads predict her mood")
row4 = next(r for r in S._load() if r["id"] == row4["id"])
S.work(row4, ask=fable_seq({"refuse": "that is his subconscious; it needs Gloria"}), post=POSTS.append, suite=suite_seq(), deploy=deploy)
check("a fix Fable declines is said, and nothing changes", row4["state"] == "refused" and "declined by Fable" in POSTS[-1] and origin_log() == before)

# --- a deploy that refuses it: reverted, said in Slack, and Gloria is told -------------------------------
rr = S._load()
for x in rr:
    if str(x.get("asked", ""))[:10] == S._today(): x["asked"] = "2026-01-01T00:00:00"
    if x["state"] == "queued": x["state"] = "withdrawn"
S._save(rr)
row6, _ = S.request("greet() should wave as well as say hello")
row6 = next(r for r in S._load() if r["id"] == row6["id"])
sent_before = len(SENT)
S.work(row6, ask=fable_seq({"summary": "wave", "edits": [{"path": "scripts/greet.py", "old": "return", "new": "return"}],
                            "new_files": [{"path": "broker/tests/test_greet_wave.py", "content": "assert True\n"}]}),
       post=POSTS.append, send=SENT.append, suite=suite_seq([]),
       deploy=lambda run: "...\nDEPLOY FAILED - files are installed, but:\n  - forge not updated (sudo wants a password)\n")
check("a fix the deploy refuses is reverted and said in Slack", row6["state"] == "failed"
      and "refused by the deploy" in POSTS[-1], (row6["state"], POSTS[-1]))
check("... and Gloria is told, with what the deploy said", len(SENT) == sent_before + 1
      and "refused by the deploy" in SENT[-1] and "sudo wants a password" in SENT[-1], SENT[sent_before:])

# --- the Slack line and the deploy ----------------------------------------------------------------------
D = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("his STUDY FIX: line goes to the Study and is shown as sent, or why not",
      "study_fix.request(fix.group(1))" in D and "Sent to the Study (%s)" in D and "Not sent to the Study (%s)" in D)
check("he is told he can fix his own code, its limits, and not to hand Gloria what he can fix",
      "STUDY FIX: what is broken, where, and what should happen" in D and "Three a day" in D
      and "Not your subconscious or JEPA, keys, money or the safety gates" in D)
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs it and its timer", "study_fix.py" in dep and 'confirm_timer --user "$FIX_UNIT_NAME"' in dep
      and "OnUnitInactiveSec=10min" in open(os.path.join(REPO, "broker", "vintos-study-fix.timer")).read())
check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
