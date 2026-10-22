#!/usr/bin/env python3
"""The Study's tool-using writer (22 October, Gloria: "You MUST get them to work!"). A scripted model drives the real
tools in a scratch workbench: it reads, greps, edits, creates its test, runs it, and may finish only once its new test
has passed. Protected files and existing tests are refused; the budget and turn limits stop it; the cache points stay
within the API's four; the model's own blocks go back unchanged. The API, the test runner and the usage log are
stubs; sockets are refused."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="study-agent-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import claude_cache, study_agent as A, study_fix as SF
claude_cache.USAGE = os.path.join(HOME, "usage.jsonl")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the usage log is scratch", claude_cache.USAGE.startswith(HOME))

root = os.path.join(HOME, "bench"); os.makedirs(os.path.join(root, "scripts")); os.makedirs(os.path.join(root, "broker", "tests"))
open(os.path.join(root, "scripts", "thing.py"), "w").write("def f():\n    return 1\n")
open(os.path.join(root, "scripts", "jepa_predictor.py"), "w").write("x = 1\n")
open(os.path.join(root, "broker", "tests", "test_old.py"), "w").write("assert True\n")
open(os.path.join(root, "CLAUDE.md"), "w").write("rules")

import itertools
_ids = itertools.count()
def tool(name, **inp): return {"type": "tool_use", "id": "t%d" % next(_ids), "name": name, "input": inp}
SCRIPT = [
    [{"type": "thinking", "thinking": "look first", "signature": "sig"}, tool("grep", pattern="def f")],
    [tool("read_file", path="scripts/thing.py")],
    [tool("edit_file", path="scripts/jepa_predictor.py", old="x = 1", new="x = 2")],
    [tool("edit_file", path="broker/tests/test_old.py", old="assert True", new="assert 1")],
    [tool("edit_file", path="scripts/thing.py", old="return 1", new="return 2")],
    [tool("finish", summary="too soon")],
    [tool("create_file", path="broker/tests/test_thing.py", content="import sys\n")],
    [tool("finish", summary="still too soon")],
    [tool("run_test", test="test_thing.py")],
    [tool("finish", summary="f now returns 2, as he asked.")],
]
SENT = []
class Resp:
    def __init__(self, d): self.d = d
    def json(self): return self.d
def post(url, json=None, **k):
    SENT.append(json)
    content = SCRIPT[len(SENT) - 1]
    return Resp({"content": content, "stop_reason": "tool_use",
                 "usage": {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}})
RAN = []
s = A.Session({"what": "f should return 2"}, root, post=post, key="k", run_test=lambda n: (RAN.append(n), (0, "ok"))[1])
out = s.start()
results = [b["content"] for m in s.messages if m["role"] == "user" and isinstance(m["content"], list)
           for b in m["content"] if b.get("type") == "tool_result"]
check("it finishes with the summary and what it changed", out.get("summary", "").startswith("f now returns 2")
      and out["changed"] == ["scripts/thing.py", "broker/tests/test_thing.py"], out)
check("the edit really landed in the workbench", open(os.path.join(root, "scripts", "thing.py")).read().endswith("return 2\n"))
check("a protected file is refused", any("refused: scripts/jepa_predictor.py is his subconscious and JEPA" in r for r in results)
      and open(os.path.join(root, "scripts", "jepa_predictor.py")).read() == "x = 1\n")
check("an existing test is refused", any("existing test" in r for r in results)
      and open(os.path.join(root, "broker", "tests", "test_old.py")).read() == "assert True\n")
check("finish is refused until a new test exists, and again until it has passed",
      any("not yet: a fix brings one new test" in r for r in results) and any("make it pass first" in r for r in results))
check("its test ran through the runner", RAN == ["test_thing.py"])
check("the model's own blocks go back unchanged (thinking with its signature)",
      SENT[1]["messages"][1]["content"][0] == {"type": "thinking", "thinking": "look first", "signature": "sig"})
check("never more than four cache points in a request", all(
      json.dumps(b).count('"cache_control"') <= 4 for b in SENT))
check("tools are offered, and the system prompt carries the repository rules",
      [t["name"] for t in SENT[0]["tools"]][-1] == "give_up" and "rules" in SENT[0]["system"][0]["text"])
check("every call is logged as study-fix", sum(1 for l in open(claude_cache.USAGE) if '"study-fix"' in l) == len(SENT))

SENT.clear()
SCRIPT[:] = [[tool("grep", pattern="x")]] * 50
b = A.Session({"what": "w"}, root, post=post, key="k", budget=0.0)
check("it stops at its budget", "budget" in b.start().get("refuse", ""))
SENT.clear()
t = A.Session({"what": "w"}, root, post=post, key="k", max_turns=3)
check("it stops at its turn limit", "turns" in t.start().get("refuse", "") and len(SENT) == 3)

src = open(os.path.join(REPO, "scripts", "study_fix.py")).read()
check("the Study can work fixes with it, keeps the one-shot writer as fallback, and repairs in the same conversation",
      "study_agent.Session(row, WORKBENCH)" in src and "plan = agent.repair(failures)" in src and "plan_fix(row, ask=ask" in src)
check("the Study may not edit its own writer", SF.protected("scripts/study_agent.py"))
# ---- Claude Code on the subscription (study_sdk.py): what it changed is judged from git, not taken from it ----
import subprocess
g = os.path.join(HOME, "gitbench"); os.makedirs(os.path.join(g, "scripts")); os.makedirs(os.path.join(g, "broker", "tests"))
open(os.path.join(g, "scripts", "thing.py"), "w").write("def f():\n    return 1\n")
open(os.path.join(g, "scripts", "jepa_predictor.py"), "w").write("x = 1\n")
open(os.path.join(g, "broker", "tests", "test_old.py"), "w").write("assert True\n")
for c in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"]):
    subprocess.run(["git"] + c, cwd=g, check=True, capture_output=True)
def reset_g():
    subprocess.run(["git", "reset", "-q", "--hard"], cwd=g, check=True); subprocess.run(["git", "clean", "-qfd"], cwd=g, check=True)
REQS = []
def sdk_doing(*writes):
    def run_sdk(req):
        REQS.append(req)
        for path, text in writes:
            full = os.path.join(g, path); os.makedirs(os.path.dirname(full), exist_ok=True); open(full, "w").write(text)
        return {"ok": True, "text": "f now returns 2.", "turns": 7}
    return run_sdk
good = SF.SubscriptionWriter({"what": "f should return 2"}, g, run_sdk=sdk_doing(
    ("scripts/thing.py", "def f():\n    return 2\n"), ("broker/tests/test_thing.py", "assert True\n")))
out = good.start()
check("a good attempt on the subscription comes back with what git says changed",
      out.get("summary") == "f now returns 2." and sorted(out["changed"]) == ["broker/tests/test_thing.py", "scripts/thing.py"]
      and REQS[-1]["model"] == SF.WRITER and REQS[-1]["root"] == g, out)
reset_g()
check("a protected file changed throws the attempt away", "thrown away" in SF.SubscriptionWriter({"what": "w"}, g,
      run_sdk=sdk_doing(("scripts/jepa_predictor.py", "x = 2\n"), ("broker/tests/test_n.py", "assert 1\n"))).start().get("refuse", ""))
reset_g()
check("an existing test changed throws it away", "existing test" in SF.SubscriptionWriter({"what": "w"}, g,
      run_sdk=sdk_doing(("broker/tests/test_old.py", "assert 1\n"), ("scripts/thing.py", "y\n"))).start().get("refuse", ""))
reset_g()
check("no new test throws it away", "no new test" in SF.SubscriptionWriter({"what": "w"}, g,
      run_sdk=sdk_doing(("scripts/thing.py", "y\n"))).start().get("refuse", ""))
reset_g()
rep = SF.SubscriptionWriter({"what": "w"}, g, run_sdk=sdk_doing(("scripts/thing.py", "z\n"), ("broker/tests/test_z.py", "1\n")))
rep.repair([("test_x.py", "AssertionError: boom")])
check("a repair carries the suite's failures to the agent, on the same tree", REQS[-1]["failures"] == [("test_x.py", "AssertionError: boom")])
try:
    SF.SubscriptionWriter({"what": "w"}, g, run_sdk=lambda r: {"ok": False, "error": "not logged in"}).start(); raised = False
except RuntimeError:
    raised = True
check("an agent that cannot run raises, which the Study turns into the next writer", raised)
sdk_src = open(os.path.join(REPO, "scripts", "study_sdk.py")).read()
check("the agent's tools are reading, editing and the isolated test runner only",
      'TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash(python3 scripts/run_isolated_test.py:*)"]' in sdk_src
      and "cwd=req[\"root\"]" in sdk_src)
check("the Study tries the subscription first; the paid tool writer only when switched on",
      'for kind in ("subscription", "api")' in src and 'os.environ.get("VINTOS_STUDY_API_AGENT") != "1"' in src)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
