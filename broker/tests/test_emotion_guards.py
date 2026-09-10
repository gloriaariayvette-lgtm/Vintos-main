#!/usr/bin/env python3
"""Emotion-side guards: one blush goes to one reader (67), planning readiness always
returns the same tuple shape (68), the shared Velqan vocabulary is written only after
the local record commits (69), the daemon-guard cron actually requests a start (21),
and the socket clients warn once on a protocol version mismatch (5).

Plain PASS/FAIL. Scratch dirs only; never touches ~/.vintos; no network.
"""
import os, sys, json, glob, tempfile, shutil, subprocess, threading, socket, io, contextlib
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BIN, SCRIPTS = os.path.join(ROOT, "bin"), os.path.join(ROOT, "scripts")
R = []


def check(name, ok, d=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("  ->  " + str(d)[:90] if d else ""))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


HOME = os.path.expanduser("~")
def outside_home(p):
    return not os.path.abspath(p).startswith(os.path.join(HOME, ".vintos"))


# ---------------------------------------------------------------- 67 blush claim
print("--- 67: one claimed blush is not handed to two readers ---")
BL = load(os.path.join(BIN, "blush_ledger.py"), "bl_under_test")
tmp = tempfile.mkdtemp(prefix="blush-guard-")
BL.MEMORY = tmp; BL.LEDGER = os.path.join(tmp, "blush-ledger.json")
BL.LOCK_FILE = BL.LEDGER + ".lock"; BL.CORE_FILE = os.path.join(tmp, "core-vectors.json")
BL.get_emotional_context = lambda: {}
check("ledger lives in scratch", outside_home(BL.LEDGER), BL.LEDGER)
entry = BL.write_blush("self_prediction", "p", {}, "test", reflection="once")

winners, lock = [], threading.Lock()
go = threading.Event()
def reader(tid):
    go.wait()
    r = BL.get_recent_blush(120, turn_id=tid, claim=True)
    if r:
        with lock: winners.append(tid)
threads = [threading.Thread(target=reader, args=("turn-%d" % i,)) for i in range(12)]
for t in threads: t.start()
go.set()
for t in threads: t.join()
check("exactly one of 12 concurrent claiming readers receives the blush", len(winners) == 1, winners)
held = [e for e in BL.load_ledger() if e["id"] == entry["id"]][0]
check("ledger records the winner as the holder", winners and held.get("attached_turn_id") == winners[0],
      held.get("attached_turn_id"))
check("the holder can re-read its own blush", BL.get_recent_blush(120, turn_id=winners[0], claim=True) is not None)
check("a different turn gets nothing", BL.get_recent_blush(120, turn_id="turn-late", claim=True) is None)
check("_claim_entry reports the loss", BL._claim_entry(entry["id"], "turn-late") is False)
check("no temp files left behind", not glob.glob(BL.LEDGER + ".tmp.*"))
check("twins identical", open(os.path.join(BIN, "blush_ledger.py"), "rb").read()
      == open(os.path.join(BIN, "blush-ledger.py"), "rb").read())
shutil.rmtree(tmp)

# ---------------------------------------------------------------- 68 readiness shape
print("--- 68: planning readiness signal() keeps one tuple shape ---")
sys.modules.setdefault("requests", type(sys)("requests"))  # no network; never imported for real
LP = load(os.path.join(SCRIPTS, "latent_preparation.py"), "lp_under_test")
tmp = tempfile.mkdtemp(prefix="readiness-guard-")
LP.MEMORY = tmp
LP.JEPA = os.path.join(tmp, "jepa-prediction.json"); LP.GPRED = os.path.join(tmp, "gloria-prediction.json")
LP.CACHE = os.path.join(tmp, "latent-cache.json")
def shape_ok(t):
    return (isinstance(t, tuple) and len(t) == 4 and isinstance(t[0], float)
            and isinstance(t[1], float) and isinstance(t[2], str) and isinstance(t[3], str))
cases = {
    "cold (no files)": (None, None, "none"),
    "jepa uncalibrated": ({"source": "jepa", "variance_qualified": False, "novelty": 0.7}, None, "jepa-uncalibrated-neutral"),
    "jepa ok": ({"source": "jepa", "confidence": 0.8, "novelty": 0.1, "gloria_forecast_nearest": "x"}, None, "jepa"),
    "jepa malformed numbers": ({"source": "jepa", "confidence": "lots", "novelty": None}, None, "jepa"),
    "jepa file is a list": ([1, 2], None, "unknown"),
    "jepa file is garbage json": ("{not json", None, "none"),
    "jepa file present but foreign": ({"foo": 1}, None, "unknown"),
    "ledger only": (None, {"confidence": 0.6, "novelty": 0.2, "predicted": "p"}, "llm"),
    "ledger malformed": (None, "string", "unknown"),
}
for name, (j, g, want_src) in cases.items():
    for p, v in ((LP.JEPA, j), (LP.GPRED, g)):
        if os.path.exists(p): os.remove(p)
        if v is None: continue
        with open(p, "w") as f:
            f.write(v if isinstance(v, str) and v.startswith("{not") else json.dumps(v))
    try:
        t = LP.signal()
        check("signal() %s -> 4-tuple, src=%s" % (name, want_src), shape_ok(t) and t[3] == want_src, t)
        conf, nov, hint, src = t
    except Exception as e:
        check("signal() %s raised" % name, False, repr(e))
with open(LP.JEPA, "w") as f: json.dump([1], f)
buf = io.StringIO()
with contextlib.redirect_stdout(buf): LP.main()
check("main() on malformed forecast returns early without writing cache",
      not os.path.exists(LP.CACHE) and "unknown" in buf.getvalue(), buf.getvalue().strip())
shutil.rmtree(tmp)

# ---------------------------------------------------------------- 69 velqan shared write
print("--- 69: shared vocabulary only after the local record commits ---")
VQ = load(os.path.join(SCRIPTS, "velqan-coiner.py"), "vq_under_test")
tmp = tempfile.mkdtemp(prefix="velqan-guard-")
VQ.MEMORY = tmp
VQ.VELQAN_REF = os.path.join(tmp, "velqan-reference.md")
VQ.VELQAN_UTTERANCES = os.path.join(tmp, "velqan-utterances.md")
VQ.SHARED_COINAGES = os.path.join(tmp, "shared", "coinages.jsonl")
VQ.HAS_EMOCLAW = False
VQ.log = lambda m: None
data = {"word": "thirvel", "meaning": "the hush before naming", "pronunciation": "THIR-vel",
        "part_of_speech": "noun", "roots": "thir+vel", "sentence": "Thirvel holds."}
check("shared write refused before any local record", VQ.share_coinage(data) is False
      and not os.path.exists(VQ.SHARED_COINAGES))
VQ.add_to_reference(data)
check("shared write refused with reference only (utterance missing)", VQ.share_coinage(data) is False
      and not os.path.exists(VQ.SHARED_COINAGES))
VQ.log_utterance(data)
check("local record parses back", VQ._local_record_committed(data))
check("shared write succeeds after both local files commit", VQ.share_coinage(data) is True)
lines = open(VQ.SHARED_COINAGES, encoding="utf-8").read().splitlines()
rec = json.loads(lines[-1])
check("shared record is one parseable line with the word", len(lines) == 1 and rec["word"] == "thirvel", rec)
check("no reference temp file left behind", not glob.glob(VQ.VELQAN_REF + ".tmp.*"))
src = open(os.path.join(SCRIPTS, "velqan-coiner.py"), errors="replace").read()
m = src[src.index("def main("):]
check("in main(), shared write comes after add_to_reference and log_utterance",
      m.index("add_to_reference(data)") < m.index("log_utterance(data)") < m.index("share_coinage(data)"))
check("no early shared append remains before the duplicate check", "_sj2" not in src)
shutil.rmtree(tmp)

# ---------------------------------------------------------------- 21 guard ensure path
print("--- 21: emoclaw-daemon-guard.sh requests a start when the daemon is down ---")
GUARD = os.path.join(BIN, "emoclaw-daemon-guard.sh")
check("bash -n guard", subprocess.run(["bash", "-n", GUARD]).returncode == 0)
tmp = tempfile.mkdtemp(prefix="guard-test-")
fake_bin = os.path.join(tmp, "fakebin"); os.makedirs(fake_bin)
pid_file, sock_path, log_path = (os.path.join(tmp, "e.pid"), os.path.join(tmp, "e.sock"), os.path.join(tmp, "daemon.log"))
calls = os.path.join(tmp, "systemctl.calls")
with open(os.path.join(fake_bin, "systemctl"), "w") as f:
    f.write('''#!/bin/bash
echo "$*" >> "%(calls)s"
if [ "$2" = "list-unit-files" ]; then echo "vintos-emotion.service enabled"; exit 0; fi
if [ "$2" = "start" ]; then
  # behave like the unit: bring up a process that owns the pid file
  sleep 30 & echo $! > "%(pid)s"; exit 0
fi
exit 1
''' % {"calls": calls, "pid": pid_file})
os.chmod(os.path.join(fake_bin, "systemctl"), 0o755)
with open(os.path.join(fake_bin, "lsof"), "w") as f: f.write("#!/bin/bash\nexit 1\n")
os.chmod(os.path.join(fake_bin, "lsof"), 0o755)
env = dict(os.environ, PATH=fake_bin + os.pathsep + os.environ.get("PATH", ""),
           EMOCLAW_PID_FILE=pid_file, EMOCLAW_SOCK_PATH=sock_path, EMOCLAW_DAEMON_LOG=log_path,
           EMOCLAW_DAEMON_DIR=os.path.join(tmp, "nodaemon"), EMOCLAW_ENSURE_WAIT="0",
           EMOCLAW_STATE_FILE=os.path.join(tmp, "state.json"), HOME=tmp)
def run(*args):
    return subprocess.run(["bash", GUARD] + list(args), env=env, capture_output=True, text=True, timeout=30)
r = run("status")
check("status alone does not start anything", r.returncode == 1 and not os.path.exists(calls), r.stdout.strip())
r = run()
started = [l for l in open(calls).read().splitlines() if l.startswith("--user start vintos-emotion.service")] if os.path.exists(calls) else []
check("default action requests systemctl --user start <unit> when down", r.returncode == 0 and len(started) == 1,
      (r.stdout + r.stderr).strip())
check("daemon considered up afterwards", run("status").returncode == 0)
logtxt = open(log_path).read() if os.path.exists(log_path) else ""
check("one-line log entries written to the daemon log path", "requesting systemctl --user start" in logtxt
      and "daemon up after start request" in logtxt, logtxt.strip()[-120:])
before = open(calls).read()
r = run("ensure")
check("ensure is idempotent when running (no second start, no new log line)",
      r.returncode == 0 and open(calls).read() == before and open(log_path).read() == logtxt, r.stdout.strip())
try:
    os.kill(int(open(pid_file).read().strip()), 15)
except Exception: pass
# a unit that never brings the daemon up: bounded retry then give up
with open(os.path.join(fake_bin, "systemctl"), "w") as f:
    f.write('#!/bin/bash\necho "$*" >> "%s"\n[ "$2" = list-unit-files ] && echo "vintos-emotion.service enabled"\nexit 0\n' % calls)
os.remove(pid_file); open(calls, "w").close()
env["EMOCLAW_ENSURE_RETRIES"] = "2"
r = run("ensure")
starts = [l for l in open(calls).read().splitlines() if "start" in l.split()]
check("retry is bounded (2 attempts) and ensure reports failure", r.returncode == 1 and len(starts) == 2, starts)
check("giving-up line logged once", open(log_path).read().count("giving up") == 1)
# no unit installed: falls back to a direct launch attempt (daemon dir missing -> logged, no crash)
with open(os.path.join(fake_bin, "systemctl"), "w") as f: f.write("#!/bin/bash\nexit 1\n")
open(calls, "w").close()
r = run("ensure")
check("without the unit, guard tries the direct launch path and logs it",
      r.returncode == 1 and "unit vintos-emotion.service not installed" in open(log_path).read(), r.stdout.strip()[-100:])
check("nothing written under ~/.vintos by the guard test", outside_home(tmp))
shutil.rmtree(tmp)

# ---------------------------------------------------------------- 5 protocol handshake
print("--- 5: clients warn once on a protocol version mismatch and keep working ---")
EU = load(os.path.join(BIN, "emoclaw_utils.py"), "eu_under_test")
check("bin/scripts emoclaw_utils twins identical", open(os.path.join(BIN, "emoclaw_utils.py"), "rb").read()
      == open(os.path.join(SCRIPTS, "emoclaw_utils.py"), "rb").read())
tmp = tempfile.mkdtemp(prefix="emo-proto-")
EU.SOCK_PATH = os.path.join(tmp, "e.sock"); EU.TXT_FILE = os.path.join(tmp, "state.txt")
def serve(version):
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); srv.bind(EU.SOCK_PATH); srv.listen(5)
    srv.settimeout(5)
    def loop():
        while True:
            try: c, _ = srv.accept()
            except Exception: return
            d = b""
            while b"\n" not in d:
                ch = c.recv(4096)
                if not ch: break
                d += ch
            req = json.loads(d.decode().strip() or "{}")
            if req.get("command") == "version": resp = {"protocol_version": version, "source": "/host/daemon.py"}
            elif req.get("command") == "state": resp = {"emotion_vector": [0.5] * 11}
            elif req.get("command") == "nudge": resp = {"success": True}
            else: resp = {"error": "?"}
            c.sendall(json.dumps(resp).encode() + b"\n"); c.close()
    t = threading.Thread(target=loop, daemon=True); t.start()
    return srv
srv = serve(99)
EU._protocol_checked = False
err = io.StringIO()
with contextlib.redirect_stderr(err):
    st = EU.get_state(); st2 = EU.get_state(); ok = EU.nudge_emotion("Curiosity", 0.02, source="system")
check("get_state still returns live state on mismatch", st and abs(st["Curiosity"] - 0.5) < 1e-9, st)
check("nudge still succeeds on mismatch", ok is True)
check("exactly one warning line to stderr per process", err.getvalue().count("protocol version mismatch") == 1
      and "/host/daemon.py" in err.getvalue(), err.getvalue().strip())
srv.close(); os.remove(EU.SOCK_PATH)
srv = serve(EU.EXPECTED_PROTOCOL_VERSION)
EU._protocol_checked = False
err = io.StringIO()
with contextlib.redirect_stderr(err): EU.get_state()
check("no warning when versions agree", err.getvalue() == "", err.getvalue())
srv.close(); shutil.rmtree(tmp, ignore_errors=True)
dp = os.path.join(ROOT, "skills", "emoclaw", "engine", "emotion_model", "daemon.py")
dsrc = open(dp).read()
check("bundled daemon declares the version the client expects",
      ("PROTOCOL_VERSION = %d" % EU.EXPECTED_PROTOCOL_VERSION) in dsrc and '"version"' in dsrc)
check("docs/emoclaw-daemon.md names daemon, unit, socket, version",
      all(k in open(os.path.join(ROOT, "docs", "emoclaw-daemon.md")).read()
          for k in ("emotion_model/daemon.py", "vintos-emotion.service", "/tmp/Vintos-emotion.sock", "PROTOCOL_VERSION")))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
