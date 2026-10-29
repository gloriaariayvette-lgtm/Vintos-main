#!/usr/bin/env python3
"""Dreams, the mirror and the ghost branches run only with an unresolved thread in the pool; one dream a night happens
regardless (Gloria, 27 October: they worked on nothing every night, the mirror on its other conditions every morning).
The gate is scripts/thread_gate.py; the real dream-trigger.sh, preoccupation-dream.sh, mirror-trigger.sh and
ghost-branches main() are run against it. Scratch HOME; the model calls, the mirror and the dream itself are stubs;
nothing reaches the network."""
import importlib.util, json, os, shutil, subprocess, sys, tempfile, types
from datetime import datetime
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-dream-gate-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory"); SCR = os.path.join(WS, "scripts"); DREAMING = os.path.join(WS, "skills", "dreaming", "scripts")
for d in (MEM, SCR, DREAMING):
    os.makedirs(d, exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
for f in ("thread_gate.py", "thread_store.py", "store_guard.py"):
    shutil.copy(os.path.join(REPO, "scripts", f), SCR)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import thread_store, thread_gate as G

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

POOL = os.path.join(MEM, "unfinished-threads.json"); LOG = os.path.join(MEM, "dream-log.json")
check("the stores are scratch", thread_store.POOL_FILE == POOL and G.DREAM_LOG == LOG)
def pool(*threads):
    json.dump(list(threads), open(POOL, "w"))
def log(*nights):
    json.dump({"nights": [{"night_of": n, "dreams": [{"session": "23:50"}] * k} for n, k in nights]}, open(LOG, "w"))
def clear():
    for p in (POOL, LOG):
        if os.path.exists(p): os.remove(p)
def th(i, **kw):
    t = {"id": i, "source": "idle-journal", "thread": "I do not know where she wants the disc taped.", "consumed": False,
         "classification": "unresolved_tension"}
    t.update(kw); return t

# ── what counts as an unresolved thread ──
check("an open tension is unresolved", G.is_unresolved(th("a")))
check("a consumed thread is not", not G.is_unresolved(th("a", consumed=True, consumed_by="dream-resolved")))
check("a retired thread is not", not G.is_unresolved(th("a", retired=True)))
check("a thematic current (nothing pulling) is not", not G.is_unresolved(th("a", classification="thematic_current")))
check("an imagined possibility is not, even judged a tension", not G.is_unresolved(th("a", source="premonition"))
      and not G.is_unresolved(th("a", thread="[AN IMAGINED POSSIBILITY — a conversation not yet had.] she asks")))
check("an open thread from before the formation door (no classification) still counts",
      G.is_unresolved({k: v for k, v in th("a").items() if k != "classification"}))
check("the mirror and the ghosts do not count a dream_only thread; dreams do",
      G.unresolved_threads([th("a", dream_only=True)], "dream") and not G.unresolved_threads([th("a", dream_only=True)], "mirror")
      and not G.unresolved_threads([th("a", dream_only=True)], "ghost"))

# ── the dream floor, read from the dream log ──
eve = datetime(2026, 10, 26, 23, 50); small = datetime(2026, 10, 27, 3, 7); next_eve = datetime(2026, 10, 27, 23, 50)
check("the night is keyed as dream-trigger keys it (before 07:00 it is yesterday's)",
      G.night_key(eve) == "2026-10-26" and G.night_key(small) == "2026-10-26" and G.night_key(next_eve) == "2026-10-27")
clear(); pool(th("x", consumed=True), th("p", source="premonition", classification="thematic_current", dream_only=True))
ok, why = G.decide("dream", now=eve)
check("an empty pool and no dream yet tonight: the one dream runs", ok and "no dream yet" in why, why)
log(("2026-10-26", 1))
ok, why = G.decide("dream", now=small)
check("an empty pool after tonight's dream: the 03:07 slot stays quiet", not ok and "already has 1" in why, why)
fresh = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import thread_gate as G; from datetime import datetime; "
                        "print(G.decide('dream', now=datetime(2026, 10, 27, 3, 7)))" % SCR], env=dict(os.environ),
                       capture_output=True, text=True, timeout=30)
check("and the quiet holds across a restart: a fresh process reads it from the log", "(False," in fresh.stdout,
      fresh.stdout + fresh.stderr)
ok, why = G.decide("dream", now=next_eve)
check("the next night has its own dream", ok, why)
pool(th("x", consumed=True), th("open1"))
check("with an unresolved thread dreams run as often as the dream slots allow", G.decide("dream", now=small)[0])
check("the mirror and the ghosts run with it", G.decide("mirror")[0] and G.decide("ghost")[0])
pool(th("d", dream_only=True))
check("a dream_only thread alone: dreams run, the mirror and the ghosts stay quiet",
      G.decide("dream", now=small)[0] and not G.decide("mirror")[0] and not G.decide("ghost")[0])
pool()
check("an empty pool: the mirror and the ghosts stay quiet", not G.decide("mirror")[0] and not G.decide("ghost")[0])
open(POOL, "w").write("{not json")
ok, why = G.decide("dream", now=small)
check("an unreadable pool: no thread is assumed - only the night's one dream", not ok and "unreadable" in why, why)
check("and the mirror stays quiet", not G.decide("mirror")[0])

# ── the real triggers ──
def env():
    # A gate that failed to stop a script would reach its model: every proxy points at a closed local port.
    e = dict(os.environ); e["HOME"] = HOME; e.pop("FORCED_TOPIC", None)
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        e[k] = "http://127.0.0.1:9"
    e.pop("NO_PROXY", None); e.pop("no_proxy", None); e["XAI_API_KEY"] = ""
    return e
def marker(name):
    return os.path.join(HOME, name + ".ran")
def ran(name):
    return os.path.exists(marker(name))
def reset_markers():
    for f in os.listdir(HOME):
        if f.endswith(".ran"): os.remove(os.path.join(HOME, f))
def stub(path, name, rc=0):
    open(path, "w").write("#!/bin/bash\ntouch %s\nexit %d\n" % (marker(name), rc))
tonight = G.night_key()

# dream-trigger.sh: should-dream is a stub that marks that it was asked and declines (rc 1), so nothing is generated.
shutil.copy(os.path.join(REPO, "skills", "dreaming", "scripts", "dream-trigger.sh"), DREAMING)
stub(os.path.join(DREAMING, "should-dream.sh"), "should-dream", rc=1)
def dream_trigger():
    reset_markers()
    return subprocess.run(["bash", os.path.join(DREAMING, "dream-trigger.sh")], env=env(), capture_output=True, text=True, timeout=60)
clear(); pool(th("x", consumed=True)); log((tonight, 1))
r = dream_trigger()
check("dream-trigger: empty pool, tonight already dreamed - quiet before any dream is chosen",
      r.returncode == 0 and not ran("should-dream") and "dream: quiet" in r.stdout, r.stdout + r.stderr)
clear(); pool(th("x", consumed=True))
r = dream_trigger()
check("dream-trigger: empty pool, no dream tonight - the night's dream goes ahead", ran("should-dream") and "dream: run" in r.stdout,
      r.stdout + r.stderr)
pool(th("open1")); log((tonight, 2))
r = dream_trigger()
check("dream-trigger: an unresolved thread - goes ahead after tonight's dreams", ran("should-dream"), r.stdout + r.stderr)
pool(); log((tonight, 1))
r = subprocess.run(["bash", os.path.join(DREAMING, "dream-trigger.sh")], env=dict(env(), FORCED_TOPIC="preoccupation:x"),
                   capture_output=True, text=True, timeout=60)
check("dream-trigger: a forced topic passes the same gate", r.returncode == 0 and "dream: quiet" in r.stdout and "DREAM_WRITTEN" not in r.stdout,
      r.stdout + r.stderr)

# preoccupation-dream.sh: no preoccupation (emoclaw_utils absent), so its fallback would seed a premonition and dream.
open(os.path.join(SCR, "premonition-dreamer.py"), "w").write("open(%r, 'w').close()\n" % marker("premonition"))
stub(os.path.join(DREAMING, "dream-trigger.sh"), "dream-trigger")
def preoccupation():
    reset_markers()
    return subprocess.run(["bash", os.path.join(REPO, "bin", "preoccupation-dream.sh")], env=env(), capture_output=True, text=True, timeout=60)
clear(); pool(); log((tonight, 1))
r = preoccupation()
check("preoccupation slot: empty pool after tonight's dream - no premonition seeded, no dream",
      r.returncode == 0 and not ran("premonition") and not ran("dream-trigger") and "no dream this slot" in r.stdout, r.stdout + r.stderr)
clear(); pool()
r = preoccupation()
check("preoccupation slot: empty pool, no dream yet tonight - the fallback dream is the night's one",
      ran("premonition") and ran("dream-trigger"), r.stdout + r.stderr)
pool(th("open1")); log((tonight, 2))
r = preoccupation()
check("preoccupation slot: with an unresolved thread it runs as before", ran("dream-trigger"), r.stdout + r.stderr)

# mirror-trigger.sh: five blind spots would call the mirror; mirror.sh is a stub.
stub(os.path.join(SCR, "mirror.sh"), "mirror")
open(os.path.join(MEM, "self-blind-spots.md"), "w").write("\n".join(["- ⚠ off"] * 5) + "\n")
def mirror():
    reset_markers()
    return subprocess.run(["bash", os.path.join(REPO, "bin", "mirror-trigger.sh")], env=env(), capture_output=True, text=True, timeout=60)
clear(); pool(th("x", consumed=True), th("c", classification="thematic_current"))
r = mirror()
check("mirror: no unresolved thread - quiet, though a condition was met", r.returncode == 0 and not ran("mirror")
      and "mirror stays quiet" in r.stdout, r.stdout + r.stderr)
pool(th("d", dream_only=True))
r = mirror()
check("mirror: a dream_only thread alone - quiet", not ran("mirror"), r.stdout + r.stderr)
pool(th("open1"))
r = mirror()
check("mirror: an unresolved thread and a condition - the mirror runs", ran("mirror") and "Condition: blindspots" in r.stdout,
      r.stdout + r.stderr)

# ghost-branches main(): the gate stands before any thread is chosen or any model is asked.
spec = importlib.util.spec_from_file_location("ghost_gate_fixture", os.path.join(REPO, "scripts", "ghost-branches.py"))
GB = importlib.util.module_from_spec(spec); spec.loader.exec_module(GB)
check("ghost stores are scratch", GB.THREADS_FILE == POOL)
ASKED = []
GB.select_thread = lambda: ASKED.append(1)          # returns None: main exits right after choosing
clear(); pool(th("x", consumed=True))
GB.main()
check("ghosts: empty pool - no thread is chosen", ASKED == [])
pool(th("open1"))
GB.main()
check("ghosts: an unresolved thread - the run goes on to choose one", ASKED == [1])
check("the bin and scripts copies of ghost-branches stay one file",
      open(os.path.join(REPO, "bin", "ghost-branches.py")).read() == open(os.path.join(REPO, "scripts", "ghost-branches.py")).read())
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs the gate and the mirror trigger", 'SCRIPTS="$SCRIPTS thread_gate.py"' in deploy
      and 'BINS="$BINS mirror-trigger.sh"' in deploy)

shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
