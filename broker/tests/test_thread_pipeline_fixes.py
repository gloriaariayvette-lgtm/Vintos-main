#!/usr/bin/env python3
"""Thread pipeline fixes (6 November 2026): the mirror judges the thread it showed; the resolved-similarity gate
reads every recent retirement by its retired_at date; the pipeline protection on triage age-out and sediment
lapses after PROTECT_TRIAGES triages with no new pass; sediment archives what it retires; a two-thread dream
gets one verdict per thread and the verdict lands on the dream those threads seeded; a thread reinstated into
the pool is not counted as resolved by the gate or the weekly chapter.

Scratch HOME set before any import; no network: requests is a stub everywhere (in-process and in the
subprocesses that run the shell heredocs); the embedding is a stub; nothing is sent."""
import os, sys, json, re, shutil, tempfile, subprocess, importlib.util, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(ROOTD, "scripts")
BIN = os.path.join(ROOTD, "bin")
DREAMING = os.path.join(ROOTD, "skills", "dreaming", "scripts")

TMP = tempfile.mkdtemp(prefix="thread-fixes-")
REAL_HOME = os.environ.get("HOME", "")
os.environ["HOME"] = TMP
WS = os.path.join(TMP, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
WS_SCRIPTS = os.path.join(WS, "scripts")
for d in (MEM, WS_SCRIPTS):
    os.makedirs(d, exist_ok=True)
for f in ("thread_store.py", "store_guard.py"):
    shutil.copy(os.path.join(SCRIPTS, f), WS_SCRIPTS)
open(os.path.join(WS_SCRIPTS, "thread-resolution.py"), "w").write("# background resolver stub\n")
open(os.path.join(WS_SCRIPTS, "backup-threads.sh"), "w").write("exit 0\n")
open(os.path.join(WS_SCRIPTS, "emoclaw_utils.py"), "w").write('''
def recent_pearls(*a, **k): return ""
def get_state(): return {}
def seed_thread(*a, **k): return None
def get_preoccupation(): return None
def set_preoccupation(*a, **k): return True
''')
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
def _no_net(*a, **k): raise ConnectionError("stub: no network")
sys.modules["requests"] = types.SimpleNamespace(post=_no_net, get=_no_net)
sys.path.insert(0, WS_SCRIPTS)
import thread_store as TS

POOL = os.path.join(MEM, "unfinished-threads.json")
RETIRED = os.path.join(MEM, "retired-threads.json")
DREAM_LOG = os.path.join(MEM, "dream-log.json")

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

def th(i, text=None, **kw):
    t = {"id": i, "source": "test", "thread": text or ("a distinct open question about the %s that still pulls" % i),
         "timestamp": "2026-10-01T00:00:00", "consumed": False}
    t.update(kw); return t
def put(threads): json.dump(threads, open(POOL, "w"), indent=2)
def pool(): return json.load(open(POOL))
def by_id(i): return next(t for t in pool() if t["id"] == i)

def heredoc(path, tag):
    src = open(path).read()
    m = re.search(r"python3 << '%s'[^\n]*\n(.*?)\n%s\n" % (tag, tag), src, re.S)
    assert m, "heredoc %s not found in %s" % (tag, path)
    return m.group(1)

def run_py(code, env=None):
    e = dict(os.environ); e["PYTHONPATH"] = STUBDIR; e.update(env or {})
    code = code.replace("/tmp/dream-", TMP + "/dream-")
    r = subprocess.run([sys.executable, "-c", code], env=e, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout, r.stderr

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

# ── 1. the mirror judges the thread it showed ────────────────────────────
print("--- mirror: one choice of thread ---")
MIRROR = os.path.join(SCRIPTS, "mirror.sh")
msrc = open(MIRROR).read()
session = heredoc(MIRROR, "THREADEOF")
judge = heredoc(MIRROR, "RESOLVE_MIRROR")
check("mirror.sh has one thread picker: the judge reads the id the session block printed",
      "TIDEOF" not in msrc and "__THREAD_ID__" in msrc and '2>"$_MIRROR_TID_FILE"' in msrc)
put([th("dreamy", priority=5, dream_only=True), th("plain", priority=3), th("pride1", priority=5, source="pride-mirror")])
rc, out, err = run_py(session)
tid = re.findall(r"__THREAD_ID__:(\S+)", err)
check("the session shows the open thread the mirror may take, not the higher-priority dream_only one",
      tid == ["plain"] and "about the plain" in out and "dreamy" not in out, (tid, out, err[-200:]))
put([th("dreamy", priority=5, dream_only=True), th("plain", priority=3), th("routed", priority=1, system_route="mirror")])
rc, out, err = run_py(session)
check("a thread routed to the mirror is the one shown, and its route is cleared",
      re.findall(r"__THREAD_ID__:(\S+)", err) == ["routed"] and "about the routed" in out and "system_route" not in by_id("routed"), (out, err[-200:]))
put([th("dreamy", priority=5, dream_only=True), th("plain", priority=3, consumed=True)])
rc, out, err = run_py(judge, {"MIRROR_ENTRY": "a real session", "_MIRROR_THREAD_ID": "", "STUB_JUDGE": "RESOLVED"})
check("no thread shown: the judge falls back to nothing (the dream_only thread is not judged or consumed)",
      not by_id("dreamy").get("consumed") and not by_id("dreamy").get("mirror_passes"), (out, by_id("dreamy")))
rc, out, err = run_py(judge, {"MIRROR_ENTRY": "a real session", "_MIRROR_THREAD_ID": "plain", "STUB_JUDGE": "RESOLVED"})
check("the shown thread was consumed meanwhile: nothing else is judged in its place",
      not by_id("dreamy").get("consumed") and by_id("plain").get("consumed_by") is None, (out, pool()))
put([th("plain", priority=3)])
rc, out, err = run_py(judge, {"MIRROR_ENTRY": "a real session", "_MIRROR_THREAD_ID": "plain", "STUB_JUDGE": "RESOLVED"})
check("the shown thread is still judged on an explicit RESOLVED", by_id("plain").get("consumed_by") == "mirror-resolved", out)
check("the semantic search is handed the chosen id (THREAD_ID was never exported)",
      "MIRROR_SEMANTIC=$(THREAD_ID=\"$THREAD_ID\" python3 << 'MIRSEMEOF'" in msrc)

# ── 2. the resolved-similarity gate reads retired_at and the whole window ──
print("--- resolved-similarity gate ---")
SG = load_module(os.path.join(SCRIPTS, "similarity_gate.py"), "similarity_gate_t")
VOCAB = ["lantern", "harbor", "filler", "reopened", "sameline"]
EMBEDDED = []
def fake_embed(texts):
    EMBEDDED.extend(texts)
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]
SG._embed_many = fake_embed
now = datetime.now()
rows = [{"id": "lan", "thread": "the lantern on the harbor wall", "retired_at": (now - timedelta(days=5)).isoformat(), "type": "sedimented"}]
rows += [{"id": "old-shape", "thread": "harbor harbor harbor", "timestamp": (now - timedelta(days=6)).isoformat()}]
rows += [{"id": "f%02d" % i, "thread": "filler retirement %d" % i, "retired_at": (now - timedelta(days=2)).isoformat()} for i in range(40)]
rows += [{"id": "s%02d" % i, "thread": "sameline sameline", "retired_at": (now - timedelta(days=1)).isoformat()} for i in range(10)]
rows += [{"id": "back", "thread": "reopened reopened", "retired_at": (now - timedelta(days=1)).isoformat()}]
rows += [{"id": "ancient", "thread": "lantern lantern", "retired_at": (now - timedelta(days=60)).isoformat()}]
json.dump(rows, open(RETIRED, "w"))
put([th("back", "reopened reopened")])
hit = SG.check_thread_against_resolved("the lantern on the harbor wall")
check("a retirement dated retired_at, older than the last 25 rows but inside the window, is compared and blocks",
      hit and hit["matched"] == "the lantern on the harbor wall", hit)
check("a row with only the old timestamp field is still read", SG.check_thread_against_resolved("harbor harbor harbor"))
check("identical archive rows embed once", EMBEDDED.count("sameline sameline") == 1, EMBEDDED.count("sameline sameline"))
check("a retirement outside the window is not compared", "lantern lantern" not in EMBEDDED)
check("an archive row whose thread is open again in the pool is not a resolution",
      SG.check_thread_against_resolved("reopened reopened") is None and EMBEDDED.count("reopened reopened") == 1)   # the query only

# ── 3. pipeline protection lapses; 5. sediment archives ──────────────────
print("--- protection lapses after PROTECT_TRIAGES triages with no new pass ---")
N = TS.PROTECT_TRIAGES
t = {"dream_passes": 1}
TS.note_triage(t)
check("a thread with a pass is protected when first counted", TS.pipeline_protected(t) and t["triages_since_pass"] == 0)
for _ in range(N - 1): TS.note_triage(t)
check("... still protected after %d triages without a new pass" % (N - 1), TS.pipeline_protected(t))
TS.note_triage(t)
check("... lapses at %d" % N, not TS.pipeline_protected(t))
t["mirror_passes"] = 1; TS.note_triage(t)
check("a new pass restores it", TS.pipeline_protected(t) and t["triages_since_pass"] == 0)
check("a thread with no passes is never protected", not TS.pipeline_protected(TS.note_triage({})))

TRI = load_module(os.path.join(BIN, "thread-triage.py"), "thread_triage_t")
TRI.llm = lambda s, p, temperature=0.7: "VOICE: still here\nPULL: 2"
put([th("stuck", dream_passes=1, triage_count=15, priority=2), th("moving", dream_passes=1, triage_count=15, priority=2),
     th("fresh", triage_count=1, priority=2)])
for run in range(1, N + 2):   # the first triage sets the baseline; N more without a pass lapse it
    if run == 5:
        p = pool(); [x.update(dream_passes=2) for x in p if x["id"] == "moving"]; put(p)
    TRI.main()
    if run == N:
        check("triage: the stuck thread is still protected after %d runs" % run, not by_id("stuck").get("consumed"), by_id("stuck"))
check("triage: after %d verdict triages past its baseline with no new pass the stuck thread ages out" % N,
      by_id("stuck").get("consumed_by") == "triage-aged-out", by_id("stuck"))
check("triage: a thread that got a new pass meanwhile stays protected", not by_id("moving").get("consumed"), by_id("moving"))
check("triage: a pull-2 thread without passes still ages out at its second triage", by_id("fresh").get("consumed_by") == "triage-aged-out")

RES = load_module(os.path.join(BIN, "thread-resolution.py"), "thread_resolution_t")
json.dump([], open(RETIRED, "w"))
put([th("sedA", priority=3, triage_count=3),
     th("sedLapsed", priority=3, triage_count=9, dream_passes=1, passes_at_triage=1, triages_since_pass=N),
     th("sedKept", priority=3, triage_count=9, dream_passes=1, passes_at_triage=1, triages_since_pass=2),
     th("sedLow", priority=1, triage_count=1)])
RES.sediment_threads()
arch = {e["id"]: e for e in TS.load_retired(RETIRED)}
check("sediment archives every thread it retires", {"sedA", "sedLapsed", "sedLow"} <= set(arch) and arch["sedA"]["type"] == "sediment", sorted(arch))
check("sediment: a lapsed protection sediments, a live one is kept", by_id("sedLapsed").get("retired") and not by_id("sedKept").get("retired"))
RES.resolve_threads()
check("the next resolve purges the sedimented threads from the pool, and their archive rows remain",
      {t["id"] for t in pool()} == {"sedKept"} and {"sedA", "sedLapsed", "sedLow"} <= {e["id"] for e in TS.load_retired(RETIRED)}, [t["id"] for t in pool()])

# ── 7. a reinstated thread is open, not resolved ─────────────────────────
print("--- reinstated threads ---")
json.dump([{"id": "rein", "thread": "the reinstated question", "retired_at": now.isoformat(), "type": "pearl", "source": "x"},
           {"id": "gone", "thread": "the settled question", "retired_at": now.isoformat(), "type": "pearl", "source": "x"}], open(RETIRED, "w"))
put([th("rein", "the reinstated question")])
check("live_retired drops the row of a thread open in the pool", [r["id"] for r in TS.live_retired(TS.load_retired(RETIRED), pool())] == ["gone"])
PROMPTS = []
RES.llm = lambda s, p, temperature=0.7: (PROMPTS.append(p) or "a chapter")
RES.weekly_review()
check("the weekly chapter does not list a reinstated thread as released or resolved",
      PROMPTS and "the settled question" in PROMPTS[0] and "the reinstated question" not in PROMPTS[0], PROMPTS[:1])

# ── 4. per-thread dream verdicts, stamped on the dream they seeded ───────
print("--- dream verdicts ---")
resolve = heredoc(os.path.join(DREAMING, "dream-trigger.sh"), "RESOLVE_PYEOF")
put([th("d1"), th("d2"), th("other")])
json.dump({"nights": [{"night_of": "2026-11-05", "dreams": [
    {"session": "03:07", "hour": 3, "thread_ids": ["d1", "d2"], "seed_verdict": "pending"},
    {"session": "23:50", "hour": 23, "thread_ids": ["other"], "seed_verdict": "pending"}],
    "threads_consumed": [], "threads_unresolved": []}]}, open(DREAM_LOG, "w"))
open(TMP + "/dream-thread1-id.txt", "w").write("d1"); open(TMP + "/dream-thread2-id.txt", "w").write("d2")
env = {"DREAM": "a dream", "PROMPT": "x", "THREAD1": "first", "THREAD2": "second", "_DREAM_CATEGORY": "seed2"}
rc, out, err = run_py(resolve, dict(env, STUB_JUDGE="THREAD 1: RESOLVED\nTHREAD 2: UNRESOLVED"))
night = json.load(open(DREAM_LOG))["nights"][-1]
d_a, d_b = night["dreams"]
check("one RESOLVED in a two-thread dream consumes only that thread",
      by_id("d1").get("consumed_by") == "dream-resolved" and not by_id("d2").get("consumed") and by_id("d2")["last_dream_verdict"] == "unresolved",
      (out, err[-200:], pool()))
check("the verdict lands on the dream those threads seeded, not on the night's last entry",
      d_a["seed_verdict"] == "partial" and d_a.get("thread_verdicts") == {"d1": "resolved", "d2": "unresolved"} and d_b["seed_verdict"] == "pending", night["dreams"])
check("the night's ledgers name each thread by its own verdict", night["threads_consumed"] == ["d1"] and night["threads_unresolved"] == ["d2"], night)
check("a thread the dream was not seeded by is untouched", not by_id("other").get("consumed") and "last_dream_verdict" not in by_id("other"))
put([th("d1"), th("d2")])
rc, out, err = run_py(resolve, dict(env, STUB_JUDGE="THREAD 1: UNRESOLVED"))
check("a missing line is no verdict for that thread only", by_id("d1")["last_dream_verdict"] == "unresolved" and by_id("d2")["last_dream_verdict"] == "no-verdict"
      and not by_id("d2").get("consumed"), pool())
rc, out, err = run_py(resolve, dict(env, STUB_JUDGE="UNRESOLVED"))
check("a bare UNRESOLVED leaves both open", by_id("d1")["last_dream_verdict"] == "unresolved" and by_id("d2")["last_dream_verdict"] == "unresolved")
put([th("solo")])
open(TMP + "/dream-thread1-id.txt", "w").write("solo"); os.remove(TMP + "/dream-thread2-id.txt")
rc, out, err = run_py(resolve, {"DREAM": "a dream", "PROMPT": "the solo thread", "_DREAM_CATEGORY": "seed", "STUB_JUDGE": "RESOLVED"})
check("a one-thread dream still resolves on a bare RESOLVED", by_id("solo").get("consumed_by") == "dream-resolved", (out, err[-200:]))

# ── hygiene ──────────────────────────────────────────────────────────────
check("HOME stayed pointed at the scratch tree", os.environ.get("HOME") == TMP)
for f in (TMP + "/dream-thread1-id.txt", TMP + "/dream-thread2-id.txt"):
    try: os.remove(f)
    except OSError: pass
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
