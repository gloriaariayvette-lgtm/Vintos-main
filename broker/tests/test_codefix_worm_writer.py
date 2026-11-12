#!/usr/bin/env python3
"""The code-fix worm's writer is started only for a call and stopped by the PID it started (Gloria, 12 November: no
always-on writer), and the worm's result goes back on the fault item the fault-fix Claude already works: the fault's
own thread in #fault-fix.

Scratch HOME: every store is throwaway; ssh and serve_writer2.sh are a fake `run` that records each command and
answers as the Studio would; Slack is a fake opener; every socket is refused."""
import fcntl, json, os, socket, subprocess, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="codefix-writer-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_CODEFIX_LOCK"] = os.path.join(HOME, "nightly.lock")
os.environ["VINTOS_CODEFIX_PROFILE"] = os.path.join(HOME, "worm", "loop", "codefix_profile.py")
os.environ["VINTOS_CODEFIX_STUDIO_SCRIPTS"] = os.path.join(HOME, "worm", "cc_studio")
os.environ["VINTOS_SLACK_TOKEN_FILE"] = os.path.join(HOME, "slack-token")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import codefix_worm as W
import fault_sweep as FS
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (d,)))

check("every store is throwaway", all(p.startswith(HOME) for p in (W.WRITER_RECORD, W.STUDIO_SCRIPTS, W.LOCK,
      W.PROPOSALS, W.CALLS, W.FAULTS, FS.CONFIG, FS.STATE, FS.TOKEN_FILE)))
SLACK = []
def no_slack(req, timeout=None): raise AssertionError("Slack is reached only through the fake opener")
FS.urllib.request.urlopen = no_slack


class Studio:
    """A fake `run`: answers ssh and serve_writer2.sh as the Studio would, records every command."""
    def __init__(self, lock_rc=0, serve_out="started 4242\nhealthy\n", kill_rc=0, ssh_down=False):
        self.lock_rc, self.serve_out, self.kill_rc, self.ssh_down = lock_rc, serve_out, kill_rc, ssh_down
        self.cmds = []

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        if cmd[0] == "bash":
            return types.SimpleNamespace(returncode=0, stdout=self.serve_out, stderr="")
        if cmd[0] != "ssh":
            raise AssertionError("unexpected command %r" % (cmd,))
        if self.ssh_down:
            return types.SimpleNamespace(returncode=255, stdout="", stderr="timed out")
        remote = cmd[-1]
        if remote.startswith("lockf"):
            return types.SimpleNamespace(returncode=self.lock_rc, stdout="", stderr="")
        if " kill " in remote:
            return types.SimpleNamespace(returncode=self.kill_rc, stdout="", stderr="")
        raise AssertionError("unexpected remote %r" % remote)

    def served(self): return [c for c in self.cmds if c[0] == "bash"]
    def kills(self): return [c[-1] for c in self.cmds if c[0] == "ssh" and " kill " in c[-1]]


def record(): return json.load(open(W.WRITER_RECORD)) if os.path.exists(W.WRITER_RECORD) else {}

# --- the writer for one call ----------------------------------------------------------------------------------------
st = Studio()
with W.StudioWriter(run=st) as w:
    check("the writer is started by serve_writer2.sh from the worm's own scripts",
          st.served() and st.served()[0][1] == os.path.join(W.STUDIO_SCRIPTS, "serve_writer2.sh"), st.cmds)
    check("only after the Studio's train.lock was found free",
          st.cmds[0][0] == "ssh" and st.cmds[0][-1].startswith("lockf -s -t 0 ~/physics-lab/train.lock"), st.cmds)
    check("its PID is recorded while it serves", record().get("pid") == 4242 and w.pid == 4242, record())
check("it is stopped by that PID, and only while it is still the writer",
      st.kills() == ["ps -o command= -p 4242 | grep -qF -- '%s' && kill 4242" % W.WRITER_MATCH], st.kills())
check("the record says it stopped", record().get("pid") is None and record().get("last_pid") == 4242, record())
check("never a pattern kill", not any("pkill" in " ".join(c) or "killall" in " ".join(c) for c in st.cmds))

st = Studio(lock_rc=75)
try:
    with W.StudioWriter(run=st): raised = None
except W.WriterUnavailable as e:
    raised = str(e)
check("a held train.lock is a refusal: nothing is started, nothing waits",
      raised and "train.lock" in raised and not st.served() and not st.kills(), (raised, st.cmds))

st = Studio(ssh_down=True)
try:
    with W.StudioWriter(run=st): raised = None
except W.WriterUnavailable as e:
    raised = str(e)
check("an unreachable Studio is a refusal", raised and "not reachable" in raised and not st.served(), raised)

st = Studio(serve_out="already running 999\n")
with W.StudioWriter(run=st) as w:
    pass
check("a writer this side did not start is used and left running", not st.kills() and w.pid is None, st.cmds)

st = Studio(serve_out="started 5151\n")
try:
    with W.StudioWriter(run=st): raised = None
except W.WriterUnavailable as e:
    raised = str(e)
check("a writer that never answers its health check is stopped again by its PID",
      raised and "health" in raised and st.kills() and "kill 5151" in st.kills()[0], (raised, st.cmds))

st = Studio(serve_out="port 8871 busy\n")
try:
    with W.StudioWriter(run=st): raised = None
except W.WriterUnavailable as e:
    raised = str(e)
check("a busy port is a refusal, nothing killed", raised and "8871 busy" in raised and not st.kills(), raised)

# a call that died before stopping its writer: the next call stops that PID first
W._atomic(W.WRITER_RECORD, {"pid": 3131, "by": "codefix_worm.py"})
st = Studio(serve_out="started 3232\nhealthy\n")
with W.StudioWriter(run=st):
    pass
check("a writer left by an earlier call is stopped first, then the new one after",
      [k.split()[-1] for k in st.kills()] == ["3131", "3232"], st.kills())

# the stop cannot reach the Studio: the PID stays recorded for the next call
st = Studio()
w = W.StudioWriter(run=st); w.__enter__(); st.ssh_down = True; w.__exit__(None, None, None)
check("a stop that cannot reach the Studio keeps the PID recorded", record().get("pid") == 4242
      and "stop_failed" in record(), record())
st2 = Studio(serve_out="started 6000\nhealthy\n")
with W.StudioWriter(run=st2):
    pass
check("and the next call stops it", "kill 4242" in st2.kills()[0], st2.kills())

# --- hand(): the writer inside the call, the result on the fault's thread ---------------------------------------------
def git(*a, cwd=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, check=True, capture_output=True, env=env)
WT = os.path.realpath(os.path.join(HOME, "review-scratch-x", "clone")); os.makedirs(WT)
git("init", "-q", WT)
def item(**k):
    d = {"source": "fault", "ref": "F-abc", "issue": "f returns 1, should return 2", "worktree": WT,
         "test_files": ["broker/tests/test_thing.py"], "source_files": ["scripts/thing.py"]}
    d.update(k); return d
PATCH = ("--- a/scripts/thing.py\n+++ b/scripts/thing.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
         "+KEY = 'xoxb-1234-abcd'\n")
CALLED = []
def fixed(req): CALLED.append(req); return {"status": "fixed", "patch": PATCH, "rounds": 2, "task_id": "use-1",
                                            "checked": {"passed": True}, "summary": "f now returns 2"}
def unfixed(req): CALLED.append(req); return {"status": "unfixed", "patch": "", "rounds": 3}
def boom(req): CALLED.append(req); raise RuntimeError("writer not reachable on 127.0.0.1:18871")

os.makedirs(W.MEM, exist_ok=True)
json.dump({"channel": "C0TEST"}, open(FS.CONFIG, "w"))
json.dump({"faults": {"abc": {"id": "F-abc", "posted": "1794481871.515529"}, "new": {"id": "F-new", "posted": None}}},
          open(FS.STATE, "w"))
open(FS.TOKEN_FILE, "w").write("xoxb-test-token")
class _Resp:
    def __init__(self, ts): self.ts = ts
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def read(self): return json.dumps({"ok": True, "ts": self.ts}).encode()
def slack(req, timeout=None):
    SLACK.append(json.loads(req.data.decode())); return _Resp("1794500000.%06d" % len(SLACK))
FS.urllib.request.urlopen = slack

st = Studio(); W.WRITER = lambda: W.StudioWriter(run=st)
row = W.hand(item(), runner=fixed)
check("a fault with a checked fix: the writer was started for it and stopped after",
      row["status"] == "fixed" and len(st.served()) == 1 and "kill 4242" in st.kills()[-1], (row, st.cmds))
msg = SLACK[-1] if SLACK else {}
check("the result is a reply in the fault's own thread in #fault-fix",
      msg.get("channel") == "C0TEST" and msg.get("thread_ts") == "1794481871.515529", msg)
check("it says the worm's checked patch is attached and the tests pass",
      msg.get("text", "").startswith("[code-fix worm] *F-abc* - worm's checked patch attached, tests pass")
      and "+    return 2" in msg.get("text", "") and row["id"] + ".patch" in msg.get("text", ""), msg.get("text"))
check("the fault-fix Claude is told to review and apply it, nothing was applied",
      "Not applied anywhere" in msg.get("text", "") and "apply it in your clone" in msg.get("text", ""))
check("a credential in the patch never reaches Slack", "xoxb-1234" not in msg.get("text", "")
      and "[redacted]" in msg.get("text", ""), msg.get("text"))
props = json.load(open(W.PROPOSALS))
check("the proposal behind the thread records where it was posted",
      props[row["id"]]["handoff"]["thread"] == "1794481871.515529" and props[row["id"]]["applied"] is False,
      props[row["id"]])
check("the saved patch is whole (redaction is only for Slack)", open(row["patch_file"]).read() == PATCH)

row = W.hand(item(), runner=unfixed)
check("a fault the worm could not fix: its thread hears so",
      row["status"] == "unfixed" and SLACK[-1]["text"].startswith("[code-fix worm] *F-abc* - worm couldn't fix it")
      and SLACK[-1]["thread_ts"] == "1794481871.515529", SLACK[-1])
check("and the writer was stopped", "kill 4242" in st.kills()[-1])

n_kills = len(st.kills())
row = W.hand(item(), runner=boom)
check("a worm that fails mid-call still has its writer stopped", row["status"] == "rejected"
      and len(st.kills()) == n_kills + 1, st.cmds[-3:])
check("and its thread hears why", "worm ran and gave no result" in SLACK[-1]["text"] and "18871" in SLACK[-1]["text"])

row = W.hand(item(ref="F-new"), runner=unfixed)
check("a fault not yet posted gets its own message naming it, not a thread reply",
      "thread_ts" not in SLACK[-1] and "*F-new*" in SLACK[-1]["text"], SLACK[-1])

# no post when the worm was not run
n_slack, n_called = len(SLACK), len(CALLED)
st.lock_rc = 75
row = W.hand(item(), runner=fixed)
check("the Studio training: refused, the worm not run, no writer started",
      row["status"] == "rejected" and "train.lock" in row["reason"] and len(CALLED) == n_called, row)
st.lock_rc = 0
with open(W.LOCK, "a") as held:
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    n_cmds = len(st.cmds)
    row = W.hand(item(), runner=fixed)
check("the nightly loop's lock held: refused before the Studio is even asked",
      row["status"] == "rejected" and "busy" in row["reason"] and len(st.cmds) == n_cmds, row)
row = W.hand(item(test_files=[]), runner=fixed)
check("an item with no failing test: refused, no writer", row["status"] == "rejected" and len(st.cmds) == n_cmds)
check("none of these refusals was posted", len(SLACK) == n_slack, SLACK[n_slack:])

row = W.hand(item(source="forge", ref="P-1"), runner=fixed)
check("a Forge item is not posted in #fault-fix (its proposal waits in the file)",
      row["status"] == "fixed" and len(SLACK) == n_slack and "handoff" not in row, row)

# Slack refusing is recorded, the proposal still stands
def refused(req, timeout=None):
    class _R(_Resp):
        def read(self): return json.dumps({"ok": False, "error": "not_in_channel"}).encode()
    return _R("")
FS.urllib.request.urlopen = refused
row = W.hand(item(), runner=fixed)
check("Slack refusing the reply: recorded on the call, the proposal still made",
      row["status"] == "fixed" and "not_in_channel" in row["handoff"]["error"]
      and row["id"] in json.load(open(W.PROPOSALS)), row)

# a long patch is cut in Slack, never in its file
FS.urllib.request.urlopen = slack
long_patch = PATCH + "".join("+line %d\n" % i for i in range(2000))
row = W.hand(item(), runner=lambda req: {"status": "fixed", "patch": long_patch, "rounds": 1})
check("a long patch is cut in the thread and named by its file",
      len(SLACK[-1]["text"]) < W.SLACK_PATCH_CHARS + 1500 and "cut here" in SLACK[-1]["text"]
      and open(row["patch_file"]).read() == long_patch, len(SLACK[-1]["text"]))

check("the sweep's own posts are unchanged: no thread_ts unless asked",
      (lambda got: "thread_ts" not in got)(
          (FS.post("C0TEST", "x", opener=lambda req, timeout=None: (SLACK.append(json.loads(req.data.decode())), _Resp("1"))[1]),
           SLACK[-1])[1]))
check("the fault loop's instructions name the worm's thread replies",
      "[code-fix worm]" in open(os.path.join(REPO, "docs", "fault-loop.md")).read())
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
