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
check("SAVE updates the same working file and keeps the prior version in .history",
      again == out["saved"][0] and open(again).read() == "x = 1\n"
      and any("def tend" in open(os.path.join(W.CODE_HISTORY, h)).read() for h in os.listdir(W.CODE_HISTORY)))
check("a name cannot leave the code folder", os.path.dirname(W.save_code("../../etc/evil.sh", "x")) == W.CODE)
check("stray characters around a filename are dropped, never turned into a trailing underscore (udp_probe.py_)",
      os.path.basename(W.save_code("udp_probe.py_", "x")) == "udp_probe.py"
      and os.path.basename(W.save_code("`udp_probe.py`", "x")) == "udp_probe.py"
      and os.path.basename(W.save_code("udp_probe.py<|", "x")) == "udp_probe.py"
      and os.path.basename(W.save_code("  udp probe.py ", "x")) == "udp_probe.py")
check("RUN cleans the name the same way, so a trailing-underscore name still finds the saved file",
      not W.run_code(dict(cfg, repo="/x"), "udp_probe.py_").startswith("no such saved file"))
check("its memory is this thread only: the first message it sees is its own instructions, then her words",
      seen[0][0]["role"] == "system" and seen[0][1]["content"] == "Where is tend? Write a fix." and len(seen[0]) == 2)
seen.clear(); W.turn("t2", "hello", cfg, model_call=lambda c, m: (seen.append(m), "hi")[1])
check("a new thread starts empty", len(seen[0]) == 2 and "Where is tend" not in json.dumps(seen[0]))
check("reading outside his code is refused", W.read(cfg, "../../etc/passwd").startswith("not readable here")
      and W.read(cfg, "/etc/passwd").startswith("not readable here"))
codex = os.path.join(TMP, "Codex", "2026-10-23", "worktree"); os.makedirs(codex)
open(os.path.join(codex, "plan.md"), "w").write("runtime selection\n")
cfg2 = dict(cfg, also_read=os.path.join(TMP, "Codex"))
out = W.run_tools("Let me look.\n\n`LIST %s`\n- GREP runtime in %s\n1. **READ %s/plan.md**" % (codex, codex, codex), cfg2)
check("a tool line in backticks, a bullet or bold still runs, on a folder she made readable",
      "plan.md" in out and "plan.md:1: runtime selection" in out and "1\truntime selection" in out, out)
out = W.run_tools("LIST [%s]\nREAD <%s/plan.md>\nLIST [/]" % (codex, codex), cfg2)
check("brackets copied from the usage line are not part of the path (25 October)",
      "plan.md" in out and "1\truntime selection" in out and "not readable here: /" in out, out)
check("a missing folder says where it can look", "it can look in:" in W.listing(cfg2, "no-such"))
out = W.run_tools("<|tool_call>call:LIST [%s/]END" % codex, cfg2)
check("Gemma's own tool-call form runs (25 October: <|tool_call>call:LIST [...]END did nothing)", "plan.md" in out, out)
out = W.run_tools('<|tool_call>call:read{path:<|"|>%s/plan.md<|"|>}<tool_call|>' % codex, cfg2)
check("... and its call:name{key:value} form too", "1\truntime selection" in out, out)
msg = {"content": "", "tool_calls": [{"function": {"name": "list", "arguments": json.dumps({"folder": codex})}},
                                     {"function": {"name": "save", "arguments": json.dumps({"filename": "a.py", "code": "x = 1"})}}]}
lines = W._as_lines(msg)
check("native tool_calls from LM Studio become the same lines", ("LIST " + codex) in lines and "SAVE a.py" in lines
      and "plan.md" in W.run_tools(lines, cfg2), lines)
check("a word like 'List' in prose is not a tool", W.run_tools("**List** the directory first.\nThen Read it.", cfg2) == "")
import subprocess
subprocess.run(["git", "init", "-q", code]); subprocess.run(["git", "-C", code, "add", "."])
subprocess.run(["git", "-C", code, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "first tend"])
check("read-only git runs: log", "first tend" in W.git(cfg, "log --oneline"))
check("git that writes is refused", W.git(cfg, "commit -m x").startswith("only read-only git")
      and "not allowed" in W.git(cfg, "log --output=/tmp/x")
      and W.git(cfg, "in /etc log").startswith("not readable here"))
# the read-only boundary on `branch` (Chat, 24 October): no create, delete, rename, move, copy, force, upstream
import subprocess as _sp
real = _sp.run; _sp.run = real_run if 'real_run' in dir() else _sp.run
def _refs(): return sorted(l.strip().lstrip("* ").split()[0] for l in real(["git","-C",code,"branch","-a"],capture_output=True,text=True).stdout.splitlines() if l.strip())
real(["git","-C",code,"branch","keep-me"],capture_output=True)
before = _refs()
for bad in ("branch -D keep-me", "branch -d keep-me", "branch -m keep-me renamed", "branch -M keep-me renamed",
            "branch newbranch", "branch -c keep-me copy", "branch -f keep-me HEAD", "branch --delete keep-me",
            "branch keep-me origin/main", "branch -u origin/main"):
    r = W.git(cfg, bad)
    check("refused and nothing changed: GIT %s" % bad, "list-only" in r or "will not create" in r, r)
check("the branches are exactly as before any refused branch command", _refs() == before, (_refs(), before))
check("listing branches still works", "keep-me" in W.git(cfg, "branch") and "keep-me" in W.git(cfg, "branch -a")
      and "keep-me" in W.git(cfg, "branch --merged"))
check("ordinary read commands still work", "first tend" in W.git(cfg, "log --oneline")
      and "def tend" in W.git(cfg, "show HEAD:scripts/alarm.py") and W.git(cfg, "status").strip() != ""
      and "alarm.py" in W.git(cfg, "ls-tree --name-only HEAD scripts/"))
check("FETCH takes only web addresses", W.fetch("file:///etc/passwd").startswith("refused"))
check("the thread is kept on disk with what was looked up", len(json.load(open(W.thread_path("t1")))["messages"]) >= 4)
# progress is written as the turn runs, and the flag clears when it is done
saw = []
def slow_model(c, m):
    saw.append(len(json.load(open(W.thread_path("t4")))["messages"]))   # her message is already on disk before the model answers
    return "done"
W.turn("t4", "hi there", cfg, model_call=slow_model)
done = json.load(open(W.thread_path("t4")))
check("her message is saved before the model is asked, and 'working' clears when the turn ends",
      saw == [1] and done.get("working") is False and done["messages"][-1]["content"] == "done")
big = [{"role": "system", "content": "s"}] + [{"role": "user", "content": "x" * 1000}] * 50
check("a long thread is fitted to the model's room, newest kept", len(W.fitted(big, 5000)) < 10)
check("on the Mac itself it is open; through Tailscale only with her login; a tagged machine is refused",
      W.allowed({"Host": "127.0.0.1:8765"}) and not W.allowed({"Host": "mac.tail1234.ts.net"})
      and W.allowed({"Host": "mac.tail1234.ts.net", "X-Forwarded-For": "100.1.2.3", "Tailscale-User-Login": "her@example.com"})
      and not W.allowed({"Host": "mac.tail1234.ts.net", "X-Forwarded-For": "100.1.2.3"})
      and not W.allowed({"Host": "127.0.0.1:8765", "X-Forwarded-For": "100.1.2.3"}))
seen.clear()
W.fetch = lambda url, limit=20000: "PAGE TEXT of " + url
W.turn("t3", "Read this: https://example.test/notes.html please", cfg, model_call=lambda c, m: (seen.append(m), "ok")[1])
check("a link she gives is read for the model before it answers, without it having to ask",
      "PAGE TEXT of https://example.test/notes.html" in seen[0][-1]["content"], seen[0][-1:])
subprocess.run(["git", "-C", code, "remote", "add", "origin", "https://github.com/gloria/Vintos-main.git"])
subprocess.run(["git", "-C", code, "update-ref", "refs/remotes/origin/main", "HEAD"])
W.subprocess = subprocess
real_run = subprocess.run
def no_fetch(cmd, *a, **k):   # nothing is fetched from GitHub in a test: the branch is already "on origin"
    if "fetch" in cmd: return subprocess.CompletedProcess(cmd, 0, "", "")
    if "ls-remote" in cmd: return subprocess.CompletedProcess(cmd, 0, "abc\trefs/heads/main\nabd\trefs/heads/codex/x\n", "")
    return real_run(cmd, *a, **k)
subprocess.run = no_fetch
page = W.fetch_link(cfg, "https://github.com/gloria/Vintos-main/blob/main/scripts/alarm.py")
tree = W.fetch_link(cfg, "https://github.com/gloria/Vintos-main/tree/main/scripts")
root = W.fetch_link(cfg, "https://github.com/gloria/Vintos-main")
subprocess.run = real_run
check("a folder link lists that folder of the branch, and says how to go further",
      "scripts/alarm.py" in tree and "GIT show origin/main:<path>" in tree, tree)
check("the repository link itself shows its branches and top level", "main" in root and "scripts/" in root, root)
check("a GitHub link into his own repository is read from his checkout, not the web",
      page.startswith("his repository, branch main, scripts/alarm.py") and "def tend(now):" in page, page[:200])
calls = []
def api(path):
    calls.append(path)
    if path == "/repos/someone/tool": return {"default_branch": "main"}
    if path.startswith("/repos/someone/tool/branches"): return [{"name": "main"}, {"name": "feat/x"}]
    if path == "/repos/someone/tool/contents/?ref=main":
        return [{"name": "src", "type": "dir", "path": "src"}, {"name": "README.md", "type": "file", "path": "README.md"}]
    if path == "/repos/someone/tool/contents/src/app.py?ref=feat%2Fx":
        import base64; return {"encoding": "base64", "content": base64.b64encode(b"def run():\n    pass\n").decode()}
    raise AssertionError(path)
W._api, W._gh_token = api, lambda: ""
o_root = W.fetch_link(cfg, "https://github.com/someone/tool")
o_file = W.fetch_link(cfg, "https://github.com/someone/tool/blob/feat/x/src/app.py")
check("another repository is read through GitHub, not copied to the Mac: its branches, top level, and links to go on",
      "Branches: main, feat/x" in o_root and "https://github.com/someone/tool/tree/main/src" in o_root
      and "FETCH any link above" in o_root and not os.path.exists(os.path.join(W.HOME, "repos")), o_root)
check("a file on a branch whose name holds a slash is read", "someone/tool, branch feat/x, src/app.py" in o_file
      and "def run():" in o_file, o_file)
# --- RUN: it tests and fixes its own code, contained ---
W.RUNS = os.path.join(W.HOME, "runs"); os.makedirs(W.RUNS, exist_ok=True)
bad = W.save_code("try.py", "import sys\nprint('hello')\nsys.exit(3)\n")
check("a fresh working file is written in the code folder", os.path.basename(bad) == "try.py" and os.path.dirname(bad) == W.CODE)
r1 = W.run_code(cfg, "try.py")
check("RUN runs the saved file and returns its output and non-zero exit", "hello" in r1 and "exit 3" in r1 and "it failed" in r1, r1)
W.save_code("try.py", "print('fixed')\n")
check("SAVE again keeps the earlier draft in .history and updates the file",
      os.path.isdir(W.CODE_HISTORY) and open(bad).read() == "print('fixed')\n"
      and any("import sys" in open(os.path.join(W.CODE_HISTORY, h)).read() for h in os.listdir(W.CODE_HISTORY)))
check("RUN the fix: clean exit", "exit 0" in W.run_code(cfg, "try.py") and "it failed" not in W.run_code(cfg, "try.py"))
check("RUN refuses a file that was not saved", W.run_code(cfg, "ghost.py").startswith("no such saved file"))
check("RUN only runs the languages it names", W.save_code("x.bin", "data") and W.run_code(cfg, "x.bin").startswith("I only run"))
loop = W.run_code(cfg, W.save_code("spin.py", "while True:\n    pass\n") and "spin.py")
check("an endless run is stopped by the time limit, not left hanging", "longer than" in loop, loop)
check("by default a run may use the network (so its code can find the Acer), and does not say offline",
      "offline" not in W.run_code(dict(cfg), W.save_code("ok.py", "print('ok')\n") and "ok.py"))
check("offline in Settings takes the network away for the run", "(offline)" in W.run_code(dict(cfg, offline_runs=True), "ok.py"))
default_prof = W.SANDBOX % {"code": "/c", "scratch": "/s", "tmp": "/t", "net": ""}
offline_prof = W.SANDBOX % {"code": "/c", "scratch": "/s", "tmp": "/t", "net": "(deny network*)"}
check("writes are always confined to the code and run folders (on her Mac via sandbox-exec)",
      '(deny file-write*)' in default_prof and '(subpath "/c")' in default_prof and '(subpath "/s")' in default_prof)
check("the default profile allows the network; only offline denies it",
      "deny network" not in default_prof and "(deny network*)" in offline_prof)

# --- HOSTS: find devices on her network (and she can run tools herself) ---
check("HOSTS is wired as a tool the model can call", any(f["function"]["name"] == "hosts" for f in W.TOOLS)
      and "HOSTS" in W.VERBS.values() and "HOSTS" in W.SYSTEM)
check("the device finder uses TCP+ARP, never ping (so a Windows PC that ignores ping still shows)",
      "arp" in W.discover_hosts.__doc__.lower() and "ping" in W.discover_hosts.__doc__.lower())
W._local_ipv4 = lambda: "192.168.1.50"
W._gateway = lambda: "192.168.1.1"
W._rdns = lambda ip: ""
W._arp_table = lambda: {"192.168.1.9": "ac:de:48:11:22:33", "192.168.1.1": "00:11:22:aa:bb:cc", "192.168.1.50": "aa:bb:cc:dd:ee:ff"}
W._poke = lambda ip, port, timeout=0: ip == "192.168.1.9" and port in (445, 3389)   # the Acer: smb + rdp, no ping needed
rep = W.discover_hosts(dict(cfg), "")
check("HOSTS lists the network and the Acer shows by its MAC and its open services, with the router and this Mac marked",
      "192.168.1.9" in rep and "ac:de:48:11:22:33" in rep and "445/smb" in rep and "3389/rdp" in rep
      and "← router" in rep and "← this Mac" in rep and "ipconfig /all" in rep, rep)
check("HOSTS on one address reports only it", "192.168.1.9" in W.discover_hosts(dict(cfg), "192.168.1.9")
      and "192.168.1.1" not in W.discover_hosts(dict(cfg), "192.168.1.9"))
check("Gloria can type a command herself: the verb alone, or with one argument",
      W.direct_tool("HOSTS") == "HOSTS" and W.direct_tool("hosts 10.0.0.5") == "HOSTS 10.0.0.5"
      and W.direct_tool("HOSTS ports=8080") == "HOSTS ports=8080" and W.direct_tool("list code/") == "LIST code/")
check("a sentence that starts with a verb is left for the model, not run as a command",
      W.direct_tool("run the tests again") is None and W.direct_tool("read the handoff doc") is None
      and W.direct_tool("what is on my network?") is None)
hist = []
W.turn("t5", "HOSTS 192.168.1.9", dict(cfg), model_call=lambda c, m: (hist.append(m), "should not be called")[1])
tdat = json.load(open(W.thread_path("t5")))
check("typing HOSTS runs it directly and does not call the model",
      hist == [] and "192.168.1.9" in tdat["messages"][-1]["content"] and tdat["messages"][-1].get("tool"))

# --- a new thread cannot see another thread's findings, and bad threads can be deleted ---
W.turn("bad1", "the Acer is at 10.0.0.9 and runs macOS (WRONG, from Gemma)", dict(cfg), model_call=lambda c, m: "noted")
seen2 = []
W.turn("fresh", "hello again", dict(cfg), model_call=lambda c, m: (seen2.append(m), "hi")[1])
check("a new thread's context holds only its own messages, never another thread's content",
      "10.0.0.9" not in json.dumps(seen2[0]) and "WRONG, from Gemma" not in json.dumps(seen2[0])
      and [mm["content"] for mm in seen2[0][1:]] == ["hello again"])
check("the bad thread is on disk until deleted", os.path.exists(W.thread_path("bad1")))
import importlib
def post(path, payload):
    class H(W.Handler):
        def __init__(self): self.headers = {"Host": "127.0.0.1:%d" % W.PORT, "Content-Length": str(len(payload))}; self._body=payload; self.out={}
        def rfile_read(self): return self._body
        def _send(self, code, body, kind="application/json"): self.out = body
    h = H(); import io; h.rfile = io.BytesIO(payload.encode()); h.path = path; h.do_POST(); return h.out
check("deleting a thread removes its file for good", post("/api/delete", json.dumps({"thread": "bad1"}))["deleted"] == 1
      and not os.path.exists(W.thread_path("bad1")))
W.turn("b2", "x", dict(cfg), model_call=lambda c, m: "y"); W.turn("b3", "x", dict(cfg), model_call=lambda c, m: "y")
check("delete-all clears every thread", post("/api/delete", json.dumps({"thread": "*"}))["deleted"] >= 2
      and (not os.path.isdir(W.THREADS) or os.listdir(W.THREADS) == []))
outside = os.path.join(W.HOME, "keep.txt"); open(outside, "w").write("safe")
check("delete cannot escape the threads folder", post("/api/delete", json.dumps({"thread": "../keep.txt"}))["deleted"] == 0
      and post("/api/delete", json.dumps({"thread": "../../../etc/hosts"}))["deleted"] == 0 and open(outside).read() == "safe")

# --- WiFi: open vs refused vs firewalled, so "nothing there" and "firewall dropping" are told apart ---
W._arp_table = lambda: {"192.168.1.110": "f0:68:e3:83:5b:75"}
W._rdns = lambda ip: ""
import errno as _e
def status(ip, port, timeout=0):
    return {80: "open", 22: "closed", 445: "filtered", 3389: "filtered"}.get(port, "closed")
W._poke_status = status
rep = W.discover_hosts(dict(cfg), "192.168.1.110")
check("one-host probe separates open, refused, and firewalled ports",
      "OPEN" in rep and "80/http" in rep and "actively refused" in rep and "firewall is swallowing" in rep, rep)
def allfilt(ip, port, timeout=0): return "filtered"
W._poke_status = allfilt
rep2 = W.discover_hosts(dict(cfg), "192.168.1.110")
check("a device that answers ARP but drops every port is reported as firewalled, not empty",
      "firewall is dropping connections" in rep2 and "nothing is listening" not in rep2, rep2)
def allclosed(ip, port, timeout=0): return "closed"
W._poke_status = allclosed
check("a device that refuses every port is reported as genuinely running no service",
      "genuinely running no TCP service" in W.discover_hosts(dict(cfg), "192.168.1.110"))

# --- Bluetooth investigator: reads the Mac's radio + devices, offline-stubbed ---
import subprocess as _sp
_real = _sp.run
def fake_sysprofiler(cmd, *a, **k):
    if cmd[:2] == ["system_profiler", "SPBluetoothDataType"]:
        return type("P", (), {"stdout": "Bluetooth:\n  State: On\n  Devices (Paired):\n    Acer-Laptop:\n      Address: F0:68:E3:83:5B:75\n      Connected: No\n      RSSI: -61\n"})()
    return _real(cmd, *a, **k)
_sp.run = fake_sysprofiler
W._bt_le_scan = lambda seconds=6: "live scan needs pyobjc (not on this Mac's Python); showing paired/known devices only"
bt = W.discover_bluetooth(dict(cfg), "")
_sp.run = _real
check("BT reports the Mac's radio and paired devices (the Acer shows with its address)",
      "Bluetooth on this Mac" in bt and "F0:68:E3:83:5B:75" in bt and "Acer-Laptop" in bt and "pairing mode" in bt, bt[:200])
check("BT and the one-host probe are callable by the model and by Gloria directly",
      any(f["function"]["name"] == "bt" for f in W.TOOLS) and W.direct_tool("BT") == "BT"
      and W.direct_tool("bluetooth") == "BT" and "BT" in W.SYSTEM)

check("nothing reached the network", NET == [], NET[:3])
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
