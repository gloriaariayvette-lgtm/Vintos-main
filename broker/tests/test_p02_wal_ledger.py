#!/usr/bin/env python3
"""P02-01 effective writer turn id, P04-01 backfill parity across both WAL files, P02-02 ledger append vs
backfill under one lock, P02-03 malformed extraction is a writer failure, P04-05 a replayed turn is not
recurrence. Scratch memory dir, stubbed model, no network."""
import os, sys, json, ast, time, threading, tempfile, importlib.util as iu
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(ROOT, "scripts"); BIN = os.path.join(ROOT, "bin"); sys.path.insert(0, SCRIPTS)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:110]) if d else ""))
def load(name, path):
    sp = iu.spec_from_file_location(name, path); m = iu.module_from_spec(sp); sp.loader.exec_module(m); return m
def fresh_mem():
    d = os.path.join(tempfile.mkdtemp(), "memory"); os.makedirs(d); return d
def point(mod, mem):
    mod.MEMORY = mem; mod.WAL_FILE = os.path.join(mem, "wal.md"); mod.WAL_LOG = os.path.join(mem, "wal-log.json")

# ---------------- P02-01: _post_turn resolves one effective turn id
src = open(os.path.join(BIN, "server.py")).read()
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_post_turn")
code = ast.get_source_segment(src, fn)
mem = fresh_mem(); os.makedirs(os.path.join(mem, "..", "scripts"), exist_ok=True)
launched = []
class FakePopen:
    def __init__(self, argv, **kw): launched.append(kw.get("env", {}).get("VINTOS_TURN_ID"))
import subprocess as _sp; _orig = _sp.Popen; _sp.Popen = FakePopen
ns = {"os": os, "WORKSPACE": os.path.dirname(mem), "MEMORY": mem, "_test_mode_active": lambda: False, "print": print}
exec(code, ns)
# scripts exist check inside _bg: create empty script files so the writers "launch"
for f in ("self-prediction.py", "wal-extract.py", "imprint.py", "interaction-ledger.py", "voice-coherence.py"):
    open(os.path.join(os.path.dirname(mem), "scripts", f), "w").write("")
ns["_post_turn"]("test", "hello there", "reply", skip=("nudge_gloria","compare","direction","curiosity","predict","adopt","marks"),
                 writer_env={"VINTOS_TURN_ID": "T42"}, test_mode=False)
_sp.Popen = _orig
rec = [json.loads(l) for l in open(os.path.join(mem, "post-turn-record.jsonl"))][-1]
check("P02-01 every launched child carries T42", launched and all(t == "T42" for t in launched), launched)
check("P02-01 the post-turn record carries T42", rec.get("turn_id") == "T42", rec)

# ---------------- P04-01: both WAL files backfill by turn id
def run_backfill(path, mem, tid, facts):
    W = load("wal_" + os.path.basename(path).replace("-", "_").replace(".py", ""), path); point(W, mem)
    W.extract = lambda u, v, e=None: json.dumps([{"type": "fact", "content": f, "importance": 0.8} for f in facts])
    W._prov = lambda e=None: {"turn_id": tid, "output_provenance": "counterpart_verbatim", "may_witness": True}
    W.writer_event = lambda *a, **k: None
    sys.argv = ["wal", "Gloria said something long enough to matter here", "Vintos replied with something long enough to matter here too"]
    os.environ["VINTOS_TURN_ID"] = tid
    W.main(); return W
for path in (os.path.join(BIN, "wal-extract.py"), os.path.join(BIN, "wal_extract.py")):
    mem = fresh_mem(); led = os.path.join(mem, "interaction-ledger.json")
    now = time.time()
    json.dump([{"turn_id": "A", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 20)), "wal_facts": []},
               {"turn_id": "B", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 2)), "wal_facts": []}], open(led, "w"))
    run_backfill(path, mem, "A", ["the harbour photo was from the ferry"])
    rows = {r["turn_id"]: r for r in json.load(open(led))}
    check("P04-01 %s: only A gains the facts, B untouched" % os.path.basename(path),
          rows["A"]["wal_facts"] and not rows["B"]["wal_facts"], {k: v["wal_facts"] for k, v in rows.items()})

# ---------------- P02-02: the ledger append waits for a held lock (forced overlap), and so does backfill
L = load("interaction_ledger_t", os.path.join(SCRIPTS, "interaction-ledger.py"))
mem = fresh_mem(); L.MEMORY = mem; L.LEDGER_FILE = os.path.join(mem, "interaction-ledger.json"); L.WAL_LOG = os.path.join(mem, "wal-log.json")
L.IMPRINT_FILE = os.path.join(mem, "imprints.json"); L.BLUSH_FILE = os.path.join(mem, "blush.md")
json.dump([{"turn_id": "A", "timestamp": "2026-09-05T10:00:00", "wal_facts": []}], open(L.LEDGER_FILE, "w"))
_t = [time.time()]
L.time.time = lambda: (_t.__setitem__(0, _t[0] + 40) or _t[0])      # the 30s WAL wait ends at once
L.time.sleep = lambda *_: None
L.writer_event = lambda *a, **k: None; L._prov = lambda e=None: {"turn_id": "B", "output_provenance": "unknown", "may_witness": False}
import fcntl
lk = open(L.LEDGER_FILE + ".lock", "a+"); fcntl.flock(lk, fcntl.LOCK_EX)
sys.argv = ["ledger", "Gloria said B, the second turn, long enough", "Vintos answered B at some length as well"]
os.environ["VINTOS_TURN_ID"] = "B"   # the ledger reads the turn id from the environment
done = threading.Event()
def append():
    try: L.main()
    except SystemExit: pass
    finally: done.set()
th = threading.Thread(target=append, daemon=True); th.start(); time.sleep(0.6)
before = json.load(open(L.LEDGER_FILE))
check("P02-02 ledger append waits while the lock is held", len(before) == 1 and not done.is_set())
fcntl.flock(lk, fcntl.LOCK_UN); lk.close(); done.wait(20)
after = json.load(open(L.LEDGER_FILE))
check("P02-02 after release the append lands", len(after) == 2 and after[-1].get("turn_id") == "B", [r.get("turn_id") for r in after])
# backfill for A while a lock is held: waits, then lands without losing B
lk = open(L.LEDGER_FILE + ".lock", "a+"); fcntl.flock(lk, fcntl.LOCK_EX)
done2 = threading.Event()
def backfill():
    try: run_backfill(os.path.join(BIN, "wal-extract.py"), mem, "A", ["a fact for A"])
    finally: done2.set()
th2 = threading.Thread(target=backfill, daemon=True); th2.start(); time.sleep(0.6)
check("P02-02 backfill waits while the lock is held", not done2.is_set())
fcntl.flock(lk, fcntl.LOCK_UN); lk.close(); done2.wait(20)
final = json.load(open(L.LEDGER_FILE))
check("P02-02 both survive: A has its facts, B intact", len(final) == 2 and final[0]["wal_facts"] and final[1].get("turn_id") == "B", [(r.get("turn_id"), r.get("wal_facts")) for r in final])

# ---------------- P02-03: malformed extraction -> started, failed, nothing written; NONE -> no failed
for path in (os.path.join(BIN, "wal-extract.py"), os.path.join(BIN, "wal_extract.py")):
    mem = fresh_mem(); W = load("wal_m_" + os.path.basename(path).replace("-", "_").replace(".py", ""), path); point(W, mem)
    events = []
    W.writer_event = lambda name, state, prov=None, exc=None: events.append(state)
    W._prov = lambda e=None: {"turn_id": "M", "output_provenance": "counterpart_verbatim", "may_witness": True}
    W.extract = lambda u, v, e=None: "{ this is not json"
    sys.argv = ["wal", "Gloria said something long enough to matter here", "Vintos replied with something long enough to matter here too"]
    try: W.main()
    except Exception: pass
    check("P02-03 %s: malformed -> started, failed; never completed" % os.path.basename(path), events == ["started", "failed"], events)
    check("P02-03 %s: nothing written" % os.path.basename(path), not os.path.exists(W.WAL_FILE) and not os.path.exists(W.WAL_LOG))
    events.clear(); W.extract = lambda u, v, e=None: "NONE"; W.main()
    check("P02-03 %s: NONE is not a failure" % os.path.basename(path), events == ["started", "completed"], events)

# ---------------- P04-05: replaying turn T adds nothing; distinct turn U recurs once
mem = fresh_mem()
W = run_backfill(os.path.join(BIN, "wal-extract.py"), mem, "T", ["she keeps the harbour photo on the fridge"])
one = json.load(open(W.WAL_LOG))["entries"]; ts1 = one[0]["timestamp"]
sys.argv = sys.argv; W.main()   # same turn T again
two = json.load(open(W.WAL_LOG))["entries"]
md = open(W.WAL_FILE).read().count("harbour photo")
check("P04-05 replay of T: one fact, recurrence 0, timestamp unchanged, one markdown line",
      len(two) == 1 and two[0]["recurrence"] == 0 and two[0]["timestamp"] == ts1 and md == 1, (len(two), two[0]["recurrence"], md))
W._prov = lambda e=None: {"turn_id": "U", "output_provenance": "counterpart_verbatim", "may_witness": True}; os.environ["VINTOS_TURN_ID"] = "U"; W.main()
three = json.load(open(W.WAL_LOG))["entries"]
check("P04-05 distinct turn U recurs once", len(three) == 1 and three[0]["recurrence"] == 1 and three[0]["source_turns"] == ["T", "U"], three[0].get("source_turns"))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
