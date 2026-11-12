#!/usr/bin/env python3
"""The code-fix worm is in use (Gloria, 12 November): a fault or Forge item goes to the worm; a fix comes back as a
proposal for review and is never applied; an unfixed result is logged; every call is counted.

Scratch HOME: every store is throwaway, the worm is a stub (an in-process runner, then a fake profile script), and
every socket is refused."""
import fcntl, json, os, socket, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="codefix-worm-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_CODEFIX_LOCK"] = os.path.join(HOME, "nightly.lock")
os.environ["VINTOS_CODEFIX_PROFILE"] = os.path.join(HOME, "worm", "codefix_profile.py")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import codefix_worm as W
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (d,)))

check("every store is throwaway", all(p.startswith(HOME) for p in (W.PROPOSALS, W.PATCHES, W.CALLS, W.COUNTS,
                                                                   W.FORGE_LIST, W.FAULTS, W.LOCK, W.PROFILE)))

WT = os.path.join(HOME, "review-scratch-x", "clone"); os.makedirs(os.path.join(WT, "scripts"))
SRC = os.path.join(WT, "scripts", "thing.py")
with open(SRC, "w") as f: f.write("def f():\n    return 1\n")
BEFORE = open(SRC).read()
def item(**k):
    d = {"source": "fault", "ref": "F-abc", "issue": "f returns 1, should return 2", "worktree": WT,
         "test_files": ["broker/tests/test_thing.py"], "source_files": ["scripts/thing.py"]}
    d.update(k); return d
PATCH = "--- a/scripts/thing.py\n+++ b/scripts/thing.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
SEEN = []
def fixed(req): SEEN.append(req); return {"status": "fixed", "patch": PATCH, "rounds": 2, "task_id": "use-1",
                                          "checked": {"passed": True}, "summary": "f now returns 2"}
def unfixed(req): SEEN.append(req); return {"status": "unfixed", "patch": "", "rounds": 3, "task_id": "use-2"}
def boom(req): raise RuntimeError("writer not reachable on 127.0.0.1:18871")
def never(req): raise AssertionError("the worm must not be called")

# a fixed result is a proposal for review, never applied
row = W.hand(item(), runner=fixed)
props = json.load(open(W.PROPOSALS))
p = props.get(row["id"], {})
check("a fixed result is queued as a proposal", row["status"] == "fixed" and p.get("state") == "proposed"
      and p.get("applied") is False and p.get("ref") == "F-abc", (row, p))
check("its patch is saved for review", open(p["patch_file"]).read() == PATCH and p["patch_file"].startswith(W.PATCHES))
check("his code is not touched", open(SRC).read() == BEFORE)
check("the worm got the request it checks against", SEEN[-1] == {k: item()[k] for k in
      ("issue", "worktree", "test_files", "source_files")}, SEEN[-1:])

# an unfixed result is logged, not proposed
row2 = W.hand(item(ref="F-def"), runner=unfixed)
calls = [json.loads(l) for l in open(W.CALLS)]
check("an unfixed result is logged with its rounds", row2["status"] == "unfixed" and calls[-1]["status"] == "unfixed"
      and calls[-1]["rounds"] == 3 and calls[-1]["ref"] == "F-def", calls[-1:])
check("an unfixed result is not proposed", row2["id"] not in json.load(open(W.PROPOSALS)))

# refusals: the worm is not called, and the call is still counted
n = len(SEEN)
r_test = W.hand(item(test_files=[]), runner=never)
check("no failing test: refused before the worm", r_test["status"] == "rejected" and "failing test" in r_test["reason"])
live = os.path.join(HOME, "Vintos-main"); os.makedirs(live)
r_live = W.hand(item(worktree=live), runner=never)
check("the deploy checkout is never the worktree", r_live["status"] == "rejected" and "deploy checkout" in r_live["reason"])
os.makedirs(os.path.join(HOME, ".vintos", "workspace", "scripts"), exist_ok=True)
r_ws = W.hand(item(worktree=os.path.join(HOME, ".vintos", "workspace", "scripts")), runner=never)
check("his live install is never the worktree", r_ws["status"] == "rejected")
r_src = W.hand(item(source="slack"), runner=never)
check("an unknown source is refused", r_src["status"] == "rejected" and r_src["source"] == "manual")
with open(W.LOCK, "a") as held:
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    r_busy = W.hand(item(), runner=never)
check("while the nightly loop holds its lock, the call is refused", r_busy["status"] == "rejected" and "busy" in r_busy["reason"])
check("the worm was not called for any refusal", len(SEEN) == n)
r_boom = W.hand(item(), runner=boom)
check("a worm error is a rejected outcome, not a crash", r_boom["status"] == "rejected" and "18871" in r_boom["reason"])
r_empty = W.hand(item(), runner=lambda req: {"status": "fixed", "patch": "  "})
check("'fixed' with no patch is not a proposal", r_empty["status"] == "rejected" and r_empty["id"] not in json.load(open(W.PROPOSALS)))

c = json.load(open(W.COUNTS))
check("every call is counted", c["calls"] == 9 and c["fixed"] == 1 and c["unfixed"] == 1 and c["rejected"] == 7
      and c["by_source"]["fault"]["fixed"] == 1 and c["by_source"]["manual"]["rejected"] == 1, c)
check("every call is logged", len([l for l in open(W.CALLS)]) == 9)

# the real call path: the profile script prints progress, then its result
check("the result is read past the harness's progress lines",
      W.parse_result("round 1\n{\"x\": 1}\n{\n \"status\": \"unfixed\",\n \"rounds\": 3\n}\n") == {"status": "unfixed", "rounds": 3})
check("garbage is no result", W.parse_result("Traceback ...\nValueError: x\n") is None)
os.makedirs(os.path.dirname(W.PROFILE))
with open(W.PROFILE, "w") as f:
    f.write("import json,sys\nreq=json.load(open(sys.argv[1]))\nprint('prep ok')\n"
            "print(json.dumps({'status':'fixed','patch':'P:'+req['issue'],'rounds':1,'task_id':'use-9'},indent=1))\n")
row3 = W.hand(item(ref="F-ghi"), runner=W.call_profile)
check("the profile is run as a script and its fix proposed", row3["status"] == "fixed" and
      open(row3["patch_file"]).read() == "P:f returns 1, should return 2", row3)
os.unlink(W.PROFILE)
row4 = W.hand(item(), runner=W.call_profile)
check("a missing profile is a rejected call", row4["status"] == "rejected" and "not found" in row4["reason"])

# what is waiting to be handed
os.makedirs(W.MEM, exist_ok=True)
json.dump({"p1": {"title": "x missing choices", "status": "open", "touches": ["scripts/x.py"]},
           "p2": {"title": "done", "status": "closed"}}, open(W.FORGE_LIST, "w"))
json.dump({"faults": {"a": {"id": "F-a", "part": "lab", "kind": "error", "why": "KeyError", "count": 4}}}, open(W.FAULTS, "w"))
cand = W.candidates()
check("candidates: open Forge entries and known faults", [(c["source"], c["ref"]) for c in cand] == [("forge", "p1"), ("fault", "F-a")], cand)

out = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "codefix_worm.py"), "--show"], capture_output=True,
                     text=True, env=dict(os.environ))
shown = json.loads(out.stdout)
check("--show lists the proposals waiting for review", out.returncode == 0 and len(shown["proposed"]) == 2
      and shown["counts"]["calls"] == 11, out.stderr[-300:])

srv = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the caller is in the deploy", " codefix_worm.py" in srv)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
