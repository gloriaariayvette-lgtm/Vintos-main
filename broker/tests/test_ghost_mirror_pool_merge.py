#!/usr/bin/env python3
"""Ghost and mirror no longer write over each other's thread changes (map §4.3, item 1). Both loaded the whole
pool, changed one thread and saved the whole snapshot back without base=, so a writer that saved in between was
silently undone. Both now pass base=: save_pool re-reads the pool under its lock and applies only the fields
each writer changed, per thread.

The ghost's update_thread is run from the real module; the mirror's resolution block is run from the real
mirror.sh text. A concurrent writer is simulated at the exact point between each one's load and save. Scratch
HOME; the judge is a stub; every socket is refused."""
import importlib.util, json, os, re, shutil, socket, subprocess, sys, tempfile, types
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-pool-merge-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); SCR = os.path.join(WS, "scripts")
STUBS = os.path.join(HOME, "stubs")
for d in (MEM, SCR, STUBS):
    os.makedirs(d, exist_ok=True)
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
def no_post(*a, **k): raise AssertionError("no model is called from this suite")
sys.modules["requests"] = types.SimpleNamespace(post=no_post, get=no_post)
for f in ("thread_store.py", "store_guard.py"):
    shutil.copy(os.path.join(REPO, "scripts", f), SCR)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import thread_store

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

POOL = os.path.join(MEM, "unfinished-threads.json")
check("the pool is scratch", thread_store.POOL_FILE == POOL and POOL.startswith(HOME))
def th(i, **kw):
    t = {"id": i, "source": "idle-journal", "thread": "open question " + i, "consumed": False}
    t.update(kw); return t
def put(*threads): json.dump(list(threads), open(POOL, "w"))
def get(): return {t["id"]: t for t in json.load(open(POOL))}
def mirror_writes_meanwhile():
    p = json.load(open(POOL))
    for t in p:
        if t["id"] == "a": t["mirror_passes"] = t.get("mirror_passes", 0) + 1; t["last_mirror_verdict"] = "unresolved"
    p.append(th("new-from-elsewhere"))
    _REAL_SAVE(p, POOL, reason="test-concurrent")
_REAL_SAVE = thread_store.save_pool

# ── ghost: update_thread with a writer landing between its load and its save ──
spec = importlib.util.spec_from_file_location("ghost_merge_fixture", os.path.join(REPO, "scripts", "ghost-branches.py"))
GB = importlib.util.module_from_spec(spec); spec.loader.exec_module(GB)
check("ghost's pool is scratch", GB.THREADS_FILE == POOL)
real_save = thread_store.save_pool
def save_after_interleave(*a, **k):
    mirror_writes_meanwhile()
    return real_save(*a, **k)
thread_store.save_pool = save_after_interleave
put(th("a", mirror_passes=1), th("b"))
GB.update_thread("a", consumed=False, reason="no lean held")
thread_store.save_pool = real_save
p = get()
check("ghost: its own pass is recorded", p["a"].get("ghost_passes") == 1 and len(p["a"].get("unsuccessful_passes", [])) == 1, p["a"])
check("ghost: the mirror's pass and verdict from meanwhile survive",
      p["a"].get("mirror_passes") == 2 and p["a"].get("last_mirror_verdict") == "unresolved", p["a"])
check("ghost: a thread added meanwhile survives", "new-from-elsewhere" in p, list(p))

thread_store.save_pool = save_after_interleave
put(th("a"), th("b"))
GB.update_thread("a", consumed=True, reason="ghost-primary-resolved")
thread_store.save_pool = real_save
p = get()
check("ghost: a consume lands and the concurrent mirror pass is kept",
      p["a"].get("consumed") is True and p["a"].get("consumed_by") == "ghost-primary-resolved" and p["a"].get("mirror_passes") == 1, p["a"])
check("the bin and scripts copies of ghost-branches stay one file",
      open(os.path.join(REPO, "bin", "ghost-branches.py")).read() == open(os.path.join(REPO, "scripts", "ghost-branches.py")).read())

# ── mirror: the real resolution block, with a ghost run saving while the judge is out ──
src = open(os.path.join(REPO, "scripts", "mirror.sh")).read()
m = re.search(r"python3 << 'RESOLVE_MIRROR'\n(.*?)\nRESOLVE_MIRROR\n", src, re.S)
check("the mirror's resolution block is found", m is not None)
block = os.path.join(HOME, "resolve_mirror.py"); open(block, "w").write(m.group(1) if m else "")
# The judge stub: first a concurrent ghost save (consume or pass), then the verdict.
open(os.path.join(STUBS, "requests.py"), "w").write(
    "import json, os, sys\n"
    "sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))\n"
    "def post(url, **kw):\n"
    "    import thread_store\n"
    "    p = json.load(open(thread_store.POOL_FILE))\n"
    "    for t in p:\n"
    "        if t['id'] == 'a':\n"
    "            if os.environ.get('GHOST_CONSUMES'): t['consumed'] = True; t['consumed_by'] = 'ghost-primary-resolved'\n"
    "            else: t['ghost_passes'] = t.get('ghost_passes', 0) + 1\n"
    "    p.append({'id': 'seeded-meanwhile', 'thread': 'x', 'consumed': False})\n"
    "    thread_store.save_pool(p, thread_store.POOL_FILE, reason='test-ghost')\n"
    "    v = os.environ.get('VERDICT', 'UNRESOLVED')\n"
    "    class R:\n"
    "        def json(self): return {'choices': [{'message': {'content': v}}]}\n"
    "    return R()\n"
    "def get(*a, **k): raise AssertionError('no network')\n")
def resolve(**extra):
    env = {"HOME": HOME, "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": STUBS,
           "MIRROR_ENTRY": "a session text", "_MIRROR_THREAD_ID": "a"}
    env.update(extra)
    return subprocess.run([sys.executable, block], env=env, capture_output=True, text=True, timeout=60)

put(th("a", mirror_passes=1), th("b"))
r = resolve(VERDICT="UNRESOLVED")
p = get()
check("mirror: its pass and verdict are recorded", p["a"].get("mirror_passes") == 2 and p["a"].get("last_mirror_verdict") == "unresolved",
      r.stdout + r.stderr)
check("mirror: the ghost pass saved during the judge survives", p["a"].get("ghost_passes") == 1, p["a"])
check("mirror: a thread seeded during the judge survives", "seeded-meanwhile" in p, list(p))

put(th("a"), th("b"))
r = resolve(VERDICT="UNRESOLVED", GHOST_CONSUMES="1")
p = get()
check("mirror: an UNRESOLVED verdict does not reopen a thread the ghost consumed meanwhile",
      p["a"].get("consumed") is True and p["a"].get("consumed_by") == "ghost-primary-resolved" and p["a"].get("mirror_passes") == 1,
      p["a"])

put(th("a"), th("b"))
r = resolve(VERDICT="RESOLVED")
p = get()
check("mirror: a RESOLVED verdict consumes, and the ghost pass is kept",
      p["a"].get("consumed") is True and p["a"].get("consumed_by") == "mirror-resolved" and p["a"].get("ghost_passes") == 1, p["a"])

# Two writers in separate processes at once: every increment lands.
writer = os.path.join(HOME, "writer.py")
open(writer, "w").write(
    "import json, sys, os, copy\n"
    "sys.path.insert(0, os.path.expanduser('~/.vintos/workspace/scripts'))\n"
    "import thread_store\n"
    "key = sys.argv[1]\n"
    "for _ in range(25):\n"
    "    p = thread_store.load_pool(); base = copy.deepcopy(p)\n"
    "    for t in p:\n"
    "        if t['id'] == 'a': t[key] = t.get(key, 0) + 1\n"
    "    thread_store.save_pool(p, reason='stress', base=base)\n")
put(th("a"), th("b"))
env = {"HOME": HOME, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
procs = [subprocess.Popen([sys.executable, writer, k], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
         for k in ("ghost_passes", "mirror_passes")]
for pr in procs: pr.wait(timeout=120)
p = get()
check("two concurrent writers on different fields lose nothing", p["a"].get("ghost_passes") == 25 and p["a"].get("mirror_passes") == 25,
      p["a"])

shutil.rmtree(HOME, ignore_errors=True)
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
