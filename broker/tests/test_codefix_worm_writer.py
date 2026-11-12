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
    def __init__(self, lock_rc=0, serve_out="started 4242\nhealthy\n", kill_rc=0, ssh_down=False,
                 lstart="Thu Nov  5 09:05:03 2026\n"):
        self.lock_rc, self.serve_out, self.kill_rc, self.ssh_down = lock_rc, serve_out, kill_rc, ssh_down
        self.lstart = lstart
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
        if remote.startswith("ps -o lstart= -p "):
            return types.SimpleNamespace(returncode=0 if self.lstart else 1, stdout=self.lstart or "", stderr="")
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
    check("with the process's own start time, normalised", record().get("lstart") == "Thu Nov 5 09:05:03 2026",
          record())
check("it is stopped by that PID, and only while it is still the process it started and still the writer",
      st.kills() == ["set -- $(ps -o lstart= -p 4242); [ \"$*\" = 'Thu Nov 5 09:05:03 2026' ] && "
                     "ps -o command= -p 4242 | grep -qF -- '%s' && kill 4242" % W.WRITER_MATCH], st.kills())

# the stop command itself, run by a real shell against a fake ps: only the same process, only the writer, is killed
BIN = os.path.join(HOME, "fakebin"); os.makedirs(BIN, exist_ok=True)
with open(os.path.join(BIN, "ps"), "w") as f:
    f.write('#!/bin/sh\ncase "$2" in lstart=) echo "$FAKE_LSTART";; command=) echo "$FAKE_CMD";; esac\n')
os.chmod(os.path.join(BIN, "ps"), 0o755)
STOP_CMD = st.kills()[0]
def shell_kills(lstart, cmd):
    env = dict(os.environ, PATH=BIN + os.pathsep + os.environ.get("PATH", ""), FAKE_LSTART=lstart, FAKE_CMD=cmd)
    out = subprocess.run(["bash", "-c", "kill() { echo KILLED \"$@\"; }; " + STOP_CMD], capture_output=True,
                         text=True, env=env).stdout
    return "KILLED 4242" in out
WCMD = "/opt/homebrew/bin/llama-server -m x.gguf --alias " + W.WRITER_MATCH + " -c 393216"
check("real shell: the writer it started (same start time, padded or not) is killed",
      shell_kills("Thu Nov  5 09:05:03 2026", WCMD) and shell_kills("Thu Nov 5 09:05:03 2026", WCMD))
check("real shell: a reused PID (another start time) is never killed, even if it is a writer",
      not shell_kills("Thu Nov 12 01:00:00 2026", WCMD))
check("real shell: the same start time but not the writer (AEON's :8840, anything else) is never killed",
      not shell_kills("Thu Nov  5 09:05:03 2026", "/opt/homebrew/bin/llama-server --host 127.0.0.1 --port 8840")
      and not shell_kills("", ""))
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
W._atomic(W.WRITER_RECORD, {"pid": 3131, "lstart": "Wed Nov 11 23:00:00 2026", "by": "codefix_worm.py"})
st = Studio(serve_out="started 3232\nhealthy\n")
with W.StudioWriter(run=st):
    pass
check("a writer left by an earlier call is stopped first, then the new one after",
      [k.split()[-1] for k in st.kills()] == ["3131", "3232"], st.kills())
check("the left one only if it is still the process that call started (its recorded start time)",
      "[ \"$*\" = 'Wed Nov 11 23:00:00 2026' ]" in st.kills()[0], st.kills())

for stale in ({"pid": 3131, "by": "codefix_worm.py"}, {"pid": True, "lstart": "Wed Nov 11 23:00:00 2026"},{"pid": 3131, "lstart": "x'; kill -9 1; '"}, [3131]):
    W._atomic(W.WRITER_RECORD, stale)
    st = Studio(serve_out="already running 999\n")
    with W.StudioWriter(run=st):
        pass
    check("a record that cannot prove its process (%r) kills nothing" % (stale,), not st.kills(), st.kills())

# the stop cannot reach the Studio: the PID stays recorded for the next call
st = Studio()
w = W.StudioWriter(run=st); w.__enter__(); st.ssh_down = True; w.__exit__(None, None, None)
check("a stop that cannot reach the Studio keeps the PID recorded", record().get("pid") == 4242
      and "stop_failed" in record(), record())
st2 = Studio(serve_out="started 6000\nhealthy\n")
with W.StudioWriter(run=st2):
    pass
check("and the next call stops it, by its start time", "kill 4242" in st2.kills()[0]
      and "'Thu Nov 5 09:05:03 2026'" in st2.kills()[0], st2.kills())

st = Studio(lstart=None)
with W.StudioWriter(run=st):
    pass
check("a start time that cannot be read: the call still stops its own writer by its command line",
      st.kills() == ["ps -o command= -p 4242 | grep -qF -- '%s' && kill 4242" % W.WRITER_MATCH], st.kills())

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

# credential shapes (synthetic, built in pieces): none reaches the thread, from the patch, the summary or a reason
SHAPES = {
    "openai": ("sk-proj-" + "A1b2C3d4E5f6G7h8I9j0" * 2, "A1b2C3d4E5f6"),
    "anthropic": ("sk-ant-api03-" + "Zz9Yy8Xx7Ww6" * 3, "Zz9Yy8Xx7Ww6"),
    "slack bot": ("xoxb-" + "123456789012-1234567890123-AbCdEfGhIjKlMnOp", "AbCdEfGhIjKlMn"),
    "slack app": ("xapp-" + "1-A0123456-1234567890123-abcdef0123456789", "abcdef0123456789"),
    "bearer": ("Authorization: Bearer " + "abcDEF123ghiJKL456", "abcDEF123ghiJKL456"),
    "ghp": ("ghp_" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "QrStUvWxYz0123"),
    "github_pat": ("github_pat_" + "11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz", "abcdefghijklmnopqrst"),
    "gho": ("gho_" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "QrStUvWxYz0123"),
    "hf": ("hf_" + "AbCdEfGhIjKlMnOpQrStUvWxYz01234567", "QrStUvWxYz0123"),
    "google": ("AIza" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q", "A1b2C3d4E5f6G7"),
    "jwt": ("eyJ" + "hbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.SflKxwRJSMeKKF2QT4fw", "SflKxwRJSMeKKF2QT4"),
    "assigned": ("aws_secret_access_key = '" + "wJalrXUtnFEMI/K7MDENG/bPxRfiCY" + "'", "bPxRfiCY"),
    "password": ("PASSWORD = \"" + "hunter2-correct-horse" + "\"", "hunter2"),
    "url": ("https://user:" + "s3cretpw" + "@example.com/x", "s3cretpw"),
    "private key": ("-----BEGIN " + "OPENSSH PRIVATE KEY-----\n+b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAE\n"
                    "+c2VjcmV0a2V5Ym9keXNlY3JldGtleWJvZHk\n+-----END " + "OPENSSH PRIVATE KEY-----", "c2VjcmV0a2V5"),
    "private key, cut": ("-----BEGIN " + "RSA PRIVATE KEY-----\n+MIIEowIBAAKCAQEA0Z3VS5JJcds3xfn", "0Z3VS5JJcds3xfn"),
}
for name, (secret, tell) in SHAPES.items():
    patch = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n+" + secret + "\n"
    texts = (W.handoff_text({"ref": "F-x", "status": "fixed", "rounds": 1, "id": "CF-1", "summary": "uses " + secret},
                            patch),
             W.handoff_text({"ref": "F-x", "status": "rejected", "reason": "RuntimeError: " + secret}))
    check("a %s credential never reaches the thread" % name, all(tell not in t for t in texts), texts)
code = "+    self.token = token\n+    password = getpass()\n+def check_api_key(key):\n"
check("code that only names a secret keeps its shape", W._redact(code) == code, W._redact(code))

# a caller's timeout: SIGTERM becomes SystemExit, which still unwinds through the writer and stops its PID
st = Studio(); W.WRITER = lambda: W.StudioWriter(run=st)
def killed_mid_call(req): raise SystemExit(143)
try:
    W.hand(item(), runner=killed_mid_call); exited = False
except SystemExit:
    exited = True
check("a call ended by SystemExit (SIGTERM) still stops the writer it started",
      exited and st.kills() and "kill 4242" in st.kills()[-1] and record().get("pid") is None, (st.cmds, record()))
import signal
seen = {}
real_hand, W.hand = W.hand, lambda it: seen.update(term=signal.getsignal(signal.SIGTERM),
                                                   hup=signal.getsignal(signal.SIGHUP)) or {"status": "rejected"}
old = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGHUP)
try:
    W.main(["hand", os.path.join(HOME, "no-such-item.json")])
finally:
    W.hand = real_hand; signal.signal(signal.SIGTERM, old[0]); signal.signal(signal.SIGHUP, old[1])
check("`hand` turns SIGTERM and SIGHUP into an exit that unwinds",
      callable(seen.get("term")) and seen["term"] not in (signal.SIG_DFL, signal.SIG_IGN) and callable(seen.get("hup")),
      seen)

check("the sweep's own posts are unchanged: no thread_ts unless asked",
      (lambda got: "thread_ts" not in got)(
          (FS.post("C0TEST", "x", opener=lambda req, timeout=None: (SLACK.append(json.loads(req.data.decode())), _Resp("1"))[1]),
           SLACK[-1])[1]))
check("the fault loop's instructions name the worm's thread replies",
      "[code-fix worm]" in open(os.path.join(REPO, "docs", "fault-loop.md")).read())
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
