#!/usr/bin/env python3
"""Thread lifecycle: selection is not consumption, a failed model decision is not a verdict,
and no writer may truncate the shared pool.

Covers review items 239 (a failed dream does not spend its source thread), 250 (every pool
writer passes the shrink guard), 256 (resolution only on an explicit verdict), 257 (counters
advance only after generation succeeds) and 259 (one archive reader for both historical shapes,
one writer shape).

Everything runs under a scratch HOME: the scripts resolve ~/.vintos/workspace into it, so the real
~/.vintos is never touched. No network: a stub `requests` module answers the judge calls.
"""
import os, sys, json, re, shutil, tempfile, subprocess, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(ROOTD, "scripts")
BIN = os.path.join(ROOTD, "bin")
DREAMING = os.path.join(ROOTD, "skills", "dreaming", "scripts")

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:90]) if d else ""))

# ── scratch home ──────────────────────────────────────────────────────
TMP = tempfile.mkdtemp(prefix="thread-life-")
REAL_HOME = os.environ.get("HOME", "")
assert not TMP.startswith(os.path.expanduser("~/.vintos")), "scratch must not live under ~/.vintos"
os.environ["HOME"] = TMP
WS = os.path.join(TMP, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
WS_SCRIPTS = os.path.join(WS, "scripts")
DREAM_DATA = os.path.join(WS, "skills", "dreaming", "data")
for d in (MEM, WS_SCRIPTS, DREAM_DATA, os.path.join(WS, "skills", "dreaming", "memory", "dreams")):
    os.makedirs(d, exist_ok=True)
shutil.copy(os.path.join(SCRIPTS, "thread_store.py"), WS_SCRIPTS)
open(os.path.join(WS_SCRIPTS, "backup-threads.sh"), "w").write("exit 0\n")
# stub emoclaw_utils: enough surface for triage / dream-trigger to import
open(os.path.join(WS_SCRIPTS, "emoclaw_utils.py"), "w").write('''
import json, os
_P = os.path.expanduser("~/.vintos/workspace/memory/current-preoccupation.json")
def recent_pearls(*a, **k): return ""
def get_state(): return {}
def seed_thread(*a, **k): pass
def get_preoccupation():
    try:
        p = json.load(open(_P)); return p if p.get("thread") else None
    except Exception: return None
def set_preoccupation(thread_text, source, priority, triage_voice="", thread_id=""):
    json.dump({"thread": thread_text, "source": source, "id": thread_id, "priority": priority}, open(_P, "w")); return True
def clear_preoccupation(): json.dump({}, open(_P, "w"))
''')
# stub requests: verdict/behaviour steered by env
STUBDIR = os.path.join(TMP, "stubs"); os.makedirs(STUBDIR)
open(os.path.join(STUBDIR, "requests.py"), "w").write('''
import os
class _R:
    def __init__(self, text): self._t = text
    def json(self): return {"choices": [{"message": {"content": self._t}}]}
def post(*a, **k):
    mode = os.environ.get("STUB_JUDGE", "raise")
    if mode == "raise": raise ConnectionError("stub: no network")
    return _R(mode)
''')
POOL = os.path.join(MEM, "unfinished-threads.json")
RETIRED = os.path.join(MEM, "retired-threads.json")
DREAM_LOG = os.path.join(MEM, "dream-log.json")
STATE = os.path.join(DREAM_DATA, "dream-state.json")

def mkpool(n=8, **kw):
    threads = [{"id": "t%02d" % i, "source": "test", "thread": "unresolved thing number %d that still pulls at me" % i,
                "timestamp": "2026-09-01T00:00:00", "consumed": False, "dream_passes": 0, "mirror_passes": 0,
                "triage_count": 0, "priority": 3} for i in range(n)]
    for t in threads: t.update(kw)
    json.dump(threads, open(POOL, "w"), indent=2)
    return threads

def pool(): return json.load(open(POOL))
def by_id(i): return next(t for t in pool() if t["id"] == i)

def heredoc(path, tag):
    """Extract the body of `python3 << 'TAG' ... TAG` from a shell script."""
    src = open(path).read()
    m = re.search(r"python3 << '%s'[^\n]*\n(.*?)\n%s\n" % (tag, tag), src, re.S)
    assert m, "heredoc %s not found in %s" % (tag, path)
    return m.group(1)

def run_py(code, env=None):
    e = dict(os.environ); e["PYTHONPATH"] = STUBDIR; e.update(env or {})
    r = subprocess.run([sys.executable, "-c", code], env=e, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

sys.path.insert(0, WS_SCRIPTS)
import thread_store as TS

# ── 250: the shrink guard is the one door ────────────────────────────
print("--- 250: no writer may truncate the pool ---")
mkpool(10)
check("full rewrite of the same pool is accepted", TS.save_pool(pool(), POOL) and len(pool()) == 10)
check("append through the door is accepted", TS.save_pool(pool() + [{"id": "new", "thread": "x", "consumed": False}], POOL) and len(pool()) == 11)
ok = TS.save_pool(pool()[:3], POOL, reason="test-partial")
check("a partial-list rewrite (11 -> 3) is refused", ok is False and len(pool()) == 11, len(pool()))
check("a non-list is refused", TS.save_pool({"threads": []}, POOL) is False and len(pool()) == 11)
open(POOL, "w").write("{not json")
check("unreadable ledger reads as None, never []", TS.load_pool(POOL) is None)
check("a small write over an unreadable ledger is refused", TS.save_pool([{"id": "only"}], POOL) is False)
mkpool(10, consumed=True)
# the novelty writer that used to filter consumed threads and cap to 30
code = heredoc(os.path.join(BIN, "unprecedented-detector.sh"), "SEED_EOF")
rc, out = run_py(code, {"UNPRECEDENTED_THREADS": POOL, "UNPRECEDENTED_ANALYSIS": "a shape\nmore", "UNPRECEDENTED_REFLECTION": "r"})
check("unprecedented-detector keeps consumed threads (11 = 10 kept + 1 seeded)", len(pool()) == 11, (rc, out[-120:], len(pool())))
open(POOL, "w").write("{not json")
rc, out = run_py(code, {"UNPRECEDENTED_THREADS": POOL, "UNPRECEDENTED_ANALYSIS": "a", "UNPRECEDENTED_REFLECTION": "r"})
check("unprecedented-detector refuses to seed over an unreadable ledger", open(POOL).read() == "{not json", out[-100:])
for sh in ("silence-audit.sh", "substrate-anxiety.sh"):
    code = heredoc(os.path.join(BIN, sh), "SEEDEOF")
    rc, out = run_py(code)
    check("%s refuses to seed over an unreadable ledger" % sh, open(POOL).read() == "{not json", out[-100:])
# static: every pool writer in the thread system goes through save_pool / _pool_save
writers = ["bin/thread-triage.py", "bin/thread_weaver.py", "bin/thread-resolution.py", "scripts/emoclaw_utils.py",
           "scripts/premonition-dreamer.py", "scripts/thread_temperature.py", "scripts/mirror.sh",
           "skills/dreaming/scripts/dream-trigger.sh", "skills/dreaming/scripts/should-dream.sh",
           "bin/silence-audit.sh", "bin/substrate-anxiety.sh", "bin/unprecedented-detector.sh",
           "bin/confession_writer.py", "bin/ghost-branches.py"]
bare = []
for w in writers:
    src = open(os.path.join(ROOTD, w)).read()
    for m in re.finditer(r"json\.dump\((threads|_threads|obj|tlist|deduped)\b", src):
        if "thread_store unavailable" in src[max(0, m.start() - 300):m.start()]:
            continue  # the announced ImportError fallback inside _pool_save is the one allowed bare write
        bare.append(w + ":" + str(src[:m.start()].count("\n") + 1))
check("no bare json.dump of the pool remains in the thread system", not bare, bare)
for a, b in (("scripts/emoclaw_utils.py", "bin/emoclaw_utils.py"), ("scripts/latent_threads.py", "bin/latent_threads.py"),
             ("scripts/thread_store.py", "bin/thread_store.py"), ("scripts/ghost-branches.py", "bin/ghost-branches.py")):
    check("twins identical: " + a, open(os.path.join(ROOTD, a)).read() == open(os.path.join(ROOTD, b)).read())

# ── 259: one archive reader for both shapes, one writer shape ─────────
print("--- 259: archive schemas ---")
json.dump({"threads": [{"id": "L1", "origin": "a latent current", "phase": "dissolving"}]}, open(RETIRED, "w"))
got = TS.load_retired(RETIRED)
check("dict-shaped archive reads as a list with a normalized 'thread'", len(got) == 1 and got[0]["thread"] == "a latent current" and got[0]["type"] == "latent", got)
TS.append_retired({"id": "P1", "thread": "pool thread", "source": "test", "consumed_by": "dream-resolved", "type": "sedimented"}, RETIRED)
raw = json.load(open(RETIRED))
check("append onto a dict-shaped archive writes the canonical list shape", isinstance(raw, list) and [e["id"] for e in raw] == ["L1", "P1"], type(raw).__name__)
json.dump([{"id": "X", "thread": "bare list entry", "type": "pearl"}], open(RETIRED, "w"))
check("list-shaped archive reads too", TS.load_retired(RETIRED)[0]["id"] == "X")
check("retired_at is stamped when missing", TS.append_retired({"id": "Y", "thread": "y"}, RETIRED)[-1]["retired_at"] != "")
RES = load_module(os.path.join(BIN, "thread-resolution.py"), "thread_resolution_mod")
json.dump({"threads": [{"id": "L2", "origin": "latent", "phase": "x"}]}, open(RETIRED, "w"))
check("thread-resolution.load_retired accepts the dict shape", [e["id"] for e in RES.load_retired()] == ["L2"])
RES.save_retired(RES.load_retired() + [{"id": "Z", "thread": "z", "source": "s", "type": "pearl"}])
check("thread-resolution.save_retired writes a list", isinstance(json.load(open(RETIRED)), list) and len(json.load(open(RETIRED))) == 2)
# latent_threads' retire path must land in the same list
LT = load_module(os.path.join(SCRIPTS, "latent_threads.py"), "latent_threads_mod")
src = open(os.path.join(SCRIPTS, "latent_threads.py")).read()
check("latent_threads writes the archive through append_retired (no private dict shape)",
      "append_retired(" in src and 'retired_data.setdefault("threads"' not in src)

# ── 256: a failed model decision is not a verdict ────────────────────
print("--- 256: resolution only on an explicit verdict ---")
mkpool(6, triage_count=2)
TRI = load_module(os.path.join(BIN, "thread-triage.py"), "thread_triage_mod")
TRI.llm = lambda *a, **k: ""                       # model error / empty
TRI.main()
t = by_id("t00")
check("triage with no verdict leaves triage_count alone (was 2)", t["triage_count"] == 2, t["triage_count"])
check("... and does not dissolve or age the thread", not t.get("consumed") and t.get("triage_last_status") == "no-verdict", t)
check("... and records the skipped pass", t.get("triage_skipped") == 1)
TRI.llm = lambda s, p, temperature=0.7: "VOICE: go on\nPULL: 1"
TRI.main()
t = by_id("t00")
check("an explicit PULL: 1 verdict still dissolves on contact", t.get("consumed") and t.get("consumed_by") == "triage-dissolved" and t["triage_count"] == 3, t)
TRI.llm = lambda s, p, temperature=0.7: "PULL: banana"
mkpool(3, triage_count=2)
TRI.main()
check("an unparsable PULL is no verdict either", by_id("t00")["triage_count"] == 2 and not by_id("t00").get("consumed"))

# mirror: the judge call fails -> attempt recorded, nothing consumed
mkpool(4)
mcode = heredoc(os.path.join(SCRIPTS, "mirror.sh"), "RESOLVE_MIRROR")
rc, out = run_py(mcode, {"MIRROR_ENTRY": "a real session text", "_MIRROR_THREAD_ID": "t01", "STUB_JUDGE": "raise"})
t = by_id("t01")
check("mirror judge failure: mirror_passes advances (attempt) but thread is NOT consumed", t["mirror_passes"] == 1 and not t.get("consumed") and t.get("last_mirror_verdict") == "no-verdict", (rc, out[-120:], t))
rc, out = run_py(mcode, {"MIRROR_ENTRY": "a real session text", "_MIRROR_THREAD_ID": "t01", "STUB_JUDGE": "maybe?"})
check("mirror garbled verdict: not consumed", not by_id("t01").get("consumed") and by_id("t01")["mirror_passes"] == 2)
rc, out = run_py(mcode, {"MIRROR_ENTRY": "a real session text", "_MIRROR_THREAD_ID": "t01", "STUB_JUDGE": "RESOLVED"})
check("mirror explicit RESOLVED consumes", by_id("t01").get("consumed_by") == "mirror-resolved")
rc, out = run_py(mcode, {"MIRROR_ENTRY": "a real session text", "_MIRROR_THREAD_ID": "t02", "STUB_JUDGE": "UNRESOLVED"})
check("mirror explicit UNRESOLVED returns the thread", not by_id("t02").get("consumed") and by_id("t02")["last_mirror_verdict"] == "unresolved")

# ── 239 / 257: a failed dream spends nothing; counters only after the dream exists ───
print("--- 239 / 257: dream selection vs generation ---")
sd = open(os.path.join(DREAMING, "should-dream.sh")).read()
check("should-dream.sh no longer marks used_thread_ids / dream_passes / clears preoccupation at selection",
      "used_thread_ids_tonight\"] = list(set(" not in sd and 't["dream_passes"]' not in sd and "clear_preoccupation()" not in sd
      and "json.dump(threads" not in sd)
dt = open(os.path.join(DREAMING, "dream-trigger.sh")).read()
check("dream-trigger.sh exits on empty dream BEFORE the spend block",
      dt.index('[ -z "$DREAM" ] && exit 1') < dt.index("python3 << 'SPENDEOF'") < dt.index("python3 << 'RESOLVE_PYEOF'"))
check("dream-trigger.sh checkpoints the raw model output beside the edited text",
      '"dream_text_raw"' in dt and '"edit_kind"' in dt and '/tmp/dream-raw.txt' in dt)
check("dream-trigger.sh keys the night to yesterday before 07:00 (matches should-dream)", "if hour < 7 else today" in dt and 'NIGHT_DATE' in sd)

spend = heredoc(os.path.join(DREAMING, "dream-trigger.sh"), "SPENDEOF")
resolve = heredoc(os.path.join(DREAMING, "dream-trigger.sh"), "RESOLVE_PYEOF")
json.dump({"nights": [{"night_of": "2026-09-09", "dreams": [{"session": "23:30", "seed_verdict": "pending"}],
                       "threads_consumed": [], "threads_unresolved": []}]}, open(DREAM_LOG, "w"))
json.dump({"used_thread_ids_tonight": []}, open(STATE, "w"))
mkpool(5)
open("/tmp/dream-thread1-id.txt", "w").write("t03"); open("/tmp/dream-thread2-id.txt", "w").write("t04")
json.dump({"thread": "unresolved thing number 3", "source": "heat-seed", "id": "t03"}, open(os.path.join(MEM, "current-preoccupation.json"), "w"))
# the dream exists -> spend
rc, out = run_py(spend, {"TOPIC": "seed2:x|||y", "THREAD1": "unresolved thing number 3", "THREAD2": "unresolved thing number 4"})
check("after generation: dream_passes advanced on both seeded threads (by id)", by_id("t03")["dream_passes"] == 1 and by_id("t04")["dream_passes"] == 1, (rc, out[-150:]))
check("after generation: ids marked used tonight", sorted(json.load(open(STATE))["used_thread_ids_tonight"]) == ["t03", "t04"])
check("after generation: matching preoccupation cleared by id", json.load(open(os.path.join(MEM, "current-preoccupation.json"))) == {})
check("spend never consumes", not by_id("t03").get("consumed"))
# the judge fails -> no verdict, nothing consumed, counters not advanced twice
env = {"DREAM": "a dream text", "PROMPT": "x", "THREAD1": "unresolved thing number 3", "THREAD2": "unresolved thing number 4", "_DREAM_CATEGORY": "seed2"}
rc, out = run_py(resolve, dict(env, STUB_JUDGE="raise"))
t3 = by_id("t03"); log = json.load(open(DREAM_LOG))
check("judge error: thread not consumed, dream_passes still 1", not t3.get("consumed") and t3["dream_passes"] == 1, (rc, out[-120:], t3))
check("judge error: recorded on the dream record as 'error'", log["nights"][-1]["dreams"][-1]["seed_verdict"] == "error")
rc, out = run_py(resolve, dict(env, STUB_JUDGE="I think so"))
check("judge garbled: no consumption, verdict 'no-verdict'", not by_id("t03").get("consumed") and by_id("t03")["last_dream_verdict"] == "no-verdict", out[-120:])
rc, out = run_py(resolve, dict(env, STUB_JUDGE="UNRESOLVED"))
check("judge UNRESOLVED: thread stays in pool, night ledger lists it unresolved", not by_id("t03").get("consumed") and "t03" in json.load(open(DREAM_LOG))["nights"][-1]["threads_unresolved"])
rc, out = run_py(resolve, dict(env, STUB_JUDGE="RESOLVED"))
check("judge RESOLVED: consumed by dream-resolved, night ledger lists it consumed",
      by_id("t03").get("consumed_by") == "dream-resolved" and "t03" in json.load(open(DREAM_LOG))["nights"][-1]["threads_consumed"])
check("... and dream_passes was not advanced by the verdict step (still 1)", by_id("t03")["dream_passes"] == 1)
check("threads never seeded into this dream are untouched", by_id("t00")["dream_passes"] == 0 and not by_id("t00").get("consumed"))

# ── 235: weaver keeps unsuccessful groups with a status and carries ids ───
print("--- 235: weaving keeps its selections ---")
mkpool(4)
json.dump({"groups": [{"name": "pair", "cards": ["t00", "t01"]}, {"name": "lonely", "cards": ["t02"]}]}, open(os.path.join(MEM, "manual-weave-groups.json"), "w"))
WV = load_module(os.path.join(BIN, "thread_weaver.py"), "thread_weaver_mod")
WV.llm_weave = lambda *a, **k: None
WV.main()
g = json.load(open(os.path.join(MEM, "manual-weave-groups.json")))["groups"]
check("failed weave keeps the group with status 'unsuccessful' (not deleted)", len(g) == 2 and g[0]["status"] == "unsuccessful" and g[1]["status"] == "unsuccessful", g)
check("originals untouched after a failed weave", not by_id("t00").get("consumed"))
WV.llm_weave = lambda *a, **k: "a woven thread that holds both questions and keeps their words"
WV.main()
g = json.load(open(os.path.join(MEM, "manual-weave-groups.json")))["groups"]
woven = [t for t in pool() if t.get("is_woven")]
check("successful weave: group status 'woven' with the woven id", g[0]["status"] == "woven" and woven and g[0]["woven_id"] == woven[0]["id"], g[0])
check("woven thread carries its source ids", woven and woven[0].get("woven_from_ids") == ["t00", "t01"], woven and woven[0].get("woven_from_ids"))
check("originals point at the woven thread", by_id("t00").get("woven_into") == woven[0]["id"])

# ── hygiene ───────────────────────────────────────────────────────────
real_vintos = os.path.join(REAL_HOME, ".vintos")
check("nothing was written under the real ~/.vintos", not os.path.exists(real_vintos) or not any(
    os.path.getmtime(os.path.join(dp, f)) > os.path.getmtime(TMP) for dp, _, fs in os.walk(real_vintos) for f in fs))

shutil.rmtree(TMP, ignore_errors=True)
for f in ("/tmp/dream-thread1-id.txt", "/tmp/dream-thread2-id.txt", "/tmp/dream-raw.txt"):
    try: os.remove(f)
    except OSError: pass
n_fail = R.count(False)
print("\n%d checks, %d failed" % (len(R), n_fail))
sys.exit(1 if n_fail else 0)
