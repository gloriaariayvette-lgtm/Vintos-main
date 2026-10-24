#!/usr/bin/env python3
"""The Mac Workbench (tools/mac/workbench.py): thread-only memory, read-only lookups, saved code never run or overwritten.
Every store is a scratch directory, the model is a stub, and every socket is refused."""
import importlib.util, json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="workbench-"); os.environ["WORKBENCH_HOME"] = os.path.join(TMP, "wb")
NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
spec = importlib.util.spec_from_file_location("workbench", os.path.join(REPO, "tools", "mac", "workbench.py"))
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("its stores are in the scratch directory", all(p.startswith(TMP) for p in (W.HOME, W.CODE, W.THREADS, W.CONFIG)))
code = os.path.join(TMP, "his-code"); os.makedirs(os.path.join(code, "scripts"))
open(os.path.join(code, "scripts", "alarm.py"), "w").write("def tend(now):\n    return now\n")
cfg = dict(W.DEFAULTS, repo=code, model="stub")
seen = []
def model(cfg_, msgs):
    seen.append(msgs)
    if len(seen) == 1: return "Let me look.\nGREP def tend in scripts/*.py"
    return "Found it at scripts/alarm.py:1.\nSAVE tend_fix.py\n```python\ndef tend(now):\n    return now + 1\n```\nDone."
out = W.turn("t1", "Where is tend? Write a fix.", cfg, model_call=model)
check("it asked to grep, got his code's lines back, and answered from them",
      "scripts/alarm.py:1: def tend(now):" in seen[1][-1]["content"] and len(seen) == 2, seen[-1][-1:])
check("the code it wrote is saved as a plain file in the Workbench code folder, not run",
      out["saved"] == [os.path.join(W.CODE, "tend_fix.py")] and open(out["saved"][0]).read() == "def tend(now):\n    return now + 1\n"
      and not os.access(out["saved"][0], os.X_OK))
again = W.save_code("tend_fix.py", "x = 1")
check("a saved name is never overwritten", again != out["saved"][0] and open(out["saved"][0]).read().startswith("def tend"))
check("a name cannot leave the code folder", os.path.dirname(W.save_code("../../etc/evil.sh", "x")) == W.CODE)
check("its memory is this thread only: the first message it sees is its own instructions, then her words",
      seen[0][0]["role"] == "system" and seen[0][1]["content"] == "Where is tend? Write a fix." and len(seen[0]) == 2)
seen.clear(); W.turn("t2", "hello", cfg, model_call=lambda c, m: (seen.append(m), "hi")[1])
check("a new thread starts empty", len(seen[0]) == 2 and "Write a fix" not in json.dumps(seen[0]))
check("reading outside his code is refused", W.read(code, "../../etc/passwd").startswith("no such file"))
check("FETCH takes only web addresses", W.fetch("file:///etc/passwd").startswith("refused"))
check("the thread is kept on disk with what was looked up", len(json.load(open(W.thread_path("t1")))["messages"]) >= 4)
big = [{"role": "system", "content": "s"}] + [{"role": "user", "content": "x" * 1000}] * 50
check("a long thread is fitted to the model's room, newest kept", len(W.fitted(big, 5000)) < 10)
check("on the Mac itself it is open; through Tailscale only with her login; a tagged machine is refused",
      W.allowed({"Host": "127.0.0.1:8765"}) and not W.allowed({"Host": "mac.tail1234.ts.net"})
      and W.allowed({"Host": "mac.tail1234.ts.net", "X-Forwarded-For": "100.1.2.3", "Tailscale-User-Login": "her@example.com"})
      and not W.allowed({"Host": "mac.tail1234.ts.net", "X-Forwarded-For": "100.1.2.3"})
      and not W.allowed({"Host": "127.0.0.1:8765", "X-Forwarded-For": "100.1.2.3"}))
check("nothing reached the network", NET == [], NET[:3])
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
