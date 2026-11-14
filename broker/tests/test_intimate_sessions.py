#!/usr/bin/env python3
"""One file per session with her (13 November): the idle-gap boundary, the bridge's stuck "absent" readings not kept,
the disk caps, two processes sharing one session, the old day files split by the same rule, and nothing in the house
reading any of it back. Synthetic rows only; scratch HOME; every socket is refused."""
import json, os, re, socket, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="intimate-sessions-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ.pop("VINTOS_TEST_MODE", None)
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import intimate_stream as S

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
def files():
    return sorted(n for n in os.listdir(S.SESS_DIR) if n.endswith(".jsonl")) if os.path.isdir(S.SESS_DIR) else []
def rows(name):
    return [json.loads(l) for l in open(os.path.join(S.SESS_DIR, name))]
def reset():
    for n in os.listdir(S.SESS_DIR) if os.path.isdir(S.SESS_DIR) else []:
        os.remove(os.path.join(S.SESS_DIR, n))
    S._mem.update(state=None, total=None, total_at=0.0, capped=set())
    S._last_obs.update(t=0.0, state=None)

check("every row is throwaway", S.SESS_DIR.startswith(HOME))
T0 = 1_700_000_000.0          # a fixed synthetic clock

# ---- the boundary rule ----------------------------------------------------------------------------------------------
st, sid = S.step(None, T0, False)
check("a reading of nothing opens nothing", st is None and sid is None)
st, a = S.step(None, T0, True)
st, b = S.step(st, T0 + S.GAP_S - 1, True)
check("signs less than the gap apart stay one session", a == b == S.sid_for(T0) and st["last"] == T0 + S.GAP_S - 1)
st2, c = S.step(st, st["last"] + S.GAP_S + 1, True)
check("a longer pause opens the next session, named for its start", c != a and c == S.sid_for(st["last"] + S.GAP_S + 1))
st3, d = S.step(st, st["last"] + 60, False)
check("a row that cannot open a session joins the open one without extending it", d == a and st3["last"] == st["last"])
check("the gap is longer than every window the code uses inside a session",
      S.GAP_S > 15 * 60 and S.GAP_S > 6 * 60 and S.GAP_S > 4 * 60 and S.GAP_S > 180)
check("what opens: touch, her press, his edge, a level they drove, a naming; not absence, decay or a late end",
      S.opens("frames", {}) and S.opens("observation", {"state": "stroking"}) and S.opens("gcs_press", {})
      and S.opens("choice", {}) and S.opens("collapse_level", {"why": "update"}) and S.opens("felt", {})
      and not S.opens("observation", {"state": "absent"}) and not S.opens("collapse_level", {"why": "decay"})
      and not S.opens("session_end", {}))

# ---- live recording: one file per session ---------------------------------------------------------------------------
reset()
S.record("gcs_press", t=T0, level=2)
S.frames([(T0 + 600, 40, 10, 0), (T0 + 600.1, 45, 12, 1)])
S.observation({"state": "stroking", "speed": 12, "flips": 1, "pressure": 0.1}, T0 + 601)
S.record("choice", t=T0 + 900, choice="edge")
S.record("felt", t=T0 + 920, word="w", pleasure=True)
check("a press, then touch ten minutes later, his edge and his naming are one session", files() == [S.sid_for(T0) + ".jsonl"]
      and [r["kind"] for r in rows(files()[0])] == ["gcs_press", "frames", "observation", "choice", "felt"], files())
check("every row carries its session", {r["sid"] for r in rows(files()[0])} == {S.sid_for(T0)})
check("the session file is private", oct(os.stat(os.path.join(S.SESS_DIR, files()[0])).st_mode & 0o777) == "0o600")
check("so is the directory", oct(os.stat(S.SESS_DIR).st_mode & 0o777) == "0o700")

# the bridge's flag stuck up for days: an "absent" reading every second
for i in range(1, 4000):
    S.observation({"state": "absent", "speed": 0}, T0 + 920 + i)
n_absent = sum(1 for r in rows(files()[0]) if r.get("state") == "absent")
check("absent readings are kept only while the session is still open (30 minutes), then not at all",
      0 < n_absent <= S.GAP_S + 1 and files() == [S.sid_for(T0) + ".jsonl"], n_absent)
S.record("collapse_level", t=T0 + 20000, level=0, was=2, why="decay")
S.record("session_end", t=T0 + 20001, dur_s=19000)
un = [f for f in files() if f.startswith("unattached-")]
check("a decay or a late session end with no session open is kept apart, not as a new session",
      len(un) == 1 and [r["kind"] for r in rows(un[0])] == ["collapse_level", "session_end"]
      and len([f for f in files() if not f.startswith("unattached-")]) == 1, files())
S.frames([(T0 + 30000, 50, 20, 0)])
check("touch hours later is a new session", len([f for f in files() if not f.startswith("unattached-")]) == 2
      and S.sid_for(T0 + 30000) + ".jsonl" in files(), files())

# ---- two processes, one session -------------------------------------------------------------------------------------
reset()
now = time.time()
S.frames([(now, 30, 10, 0)])
code = ("import sys; sys.path.insert(0, %r); import intimate_stream as S; "
        "print(S.record('gcs_press', t=%r, level=2))" % (os.path.join(REPO, "scripts"), now + 5))
out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(os.environ), timeout=60)
check("the server's press lands in the bridge's open session", out.stdout.strip() == "True" and files()
      == [S.sid_for(now) + ".jsonl"] and [r["kind"] for r in rows(files()[0])] == ["frames", "gcs_press"],
      (out.stdout, out.stderr, files()))

# ---- the lock is never waited on ------------------------------------------------------------------------------------
import fcntl
hold = os.open(S._LOCK, os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(hold, fcntl.LOCK_EX)
child = ("import sys, time; sys.path.insert(0, %r); import intimate_stream as S; t = time.time(); "
         "ok = S.record('choice', t=%r, choice='letgo'); print(ok, round(time.time() - t, 3))"
         % (os.path.join(REPO, "scripts"), now + 6))
out = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, env=dict(os.environ), timeout=60)
fcntl.flock(hold, fcntl.LOCK_UN); os.close(hold)
parts = out.stdout.split()
check("with the lock held elsewhere a row is still written, at once", parts and parts[0] == "True"
      and float(parts[1]) < 0.5, (out.stdout, out.stderr))

# ---- caps -----------------------------------------------------------------------------------------------------------
reset()
_cap = S.SESSION_CAP_BYTES; S.SESSION_CAP_BYTES = 2000
for i in range(100):
    S.frames([(T0 + i, 40, 10, 0)])
S.record("choice", t=T0 + 101, choice="edge")
r = rows(files()[0])
check("a session at its cap stops taking frames", os.path.getsize(os.path.join(S.SESS_DIR, files()[0])) < 2000 + 400
      and sum(1 for x in r if x["kind"] == "frames") < 100)
check("and says so once", sum(1 for x in r if x["kind"] == "capped") == 1
      and [x for x in r if x["kind"] == "capped"][0]["cap"] == "session")
check("events are still kept past the cap", r[-1]["kind"] == "choice")
S.SESSION_CAP_BYTES = _cap
reset()
_tot = S.TOTAL_CAP_BYTES; S.TOTAL_CAP_BYTES = 1500
for i in range(100):
    S.frames([(T0 + i, 40, 10, 0)])
r = rows(files()[0])
check("the whole directory has a cap too", sum(1 for x in r if x["kind"] == "frames") < 100
      and [x["cap"] for x in r if x["kind"] == "capped"] == ["total"])
S.TOTAL_CAP_BYTES = _tot
check("nothing in the recorder deletes or truncates", not re.search(r"os\.(remove|unlink|truncate|rmdir)|shutil|O_TRUNC",
      open(S.__file__).read()))

# ---- backfill of the old day files ----------------------------------------------------------------------------------
reset()
os.makedirs(S.DIR, exist_ok=True)
day = os.path.join(S.DIR, "day-a.jsonl")
legacy = [{"t": T0, "kind": "gcs_press", "source": "her_act"},
          {"t": T0 + 60, "kind": "frames", "source": "measured", "f": [[T0 + 60, 1, 2, 0]]}]
legacy += [{"t": T0 + 60 + i, "kind": "observation", "source": "measured", "state": "absent"} for i in range(1, 5000)]
legacy += [{"t": T0 + 90000, "kind": "felt", "source": "his_reading", "word": "w"}]
open(day, "w").write("".join(json.dumps(x) + "\n" for x in legacy))
before = open(day).read()
dry = S.backfill(write=False)
check("backfill counts without writing", dry["sessions"] and not files() and dry["absent_readings_not_kept"] > 0, dry)
done = S.backfill(write=True)
check("backfill splits the day files by the same rule", sorted(done["written"])
      == sorted([S.sid_for(T0) + ".jsonl", S.sid_for(T0 + 90000) + ".jsonl"]), done)
check("and never touches the day files", open(day).read() == before)
again = S.backfill(write=True)
check("and never overwrites a session file", not again["written"] and len(again["skipped"]) == 2, again)

# ---- record only: nothing reads it back -----------------------------------------------------------------------------
readers = []
for root in ("scripts", "bin"):
    for n in os.listdir(os.path.join(REPO, root)):
        if not n.endswith(".py") or n == "intimate_stream.py":
            continue
        src = open(os.path.join(REPO, root, n), errors="ignore").read()
        if "intimate-sessions" in src or "intimate-stream" in src:
            readers.append(root + "/" + n)
        for m in re.finditer(r"(?:_ist|_g_ist|_fc_ist|_gc_ist|intimate_stream)\.(\w+)", src):
            if m.group(1) not in ("record", "frames", "observation", "py"):   # "intimate_stream.py" in a comment
                readers.append("%s/%s uses %s" % (root, n, m.group(1)))
check("no organ reads the sessions: they only call record, frames and observation", not readers, readers)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
