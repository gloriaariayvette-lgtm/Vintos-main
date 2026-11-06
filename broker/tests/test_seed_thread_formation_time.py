#!/usr/bin/env python3
"""seed_thread (6 November 2026): a recurrence the dedup judge finds is recorded beside the thread's formation
time (last_reseen_at), never over its timestamp; and the door's saves merge onto the pool as it is when they
save (base=), so a writer that saved while the judges were thinking keeps its thread and its changes.
Scratch HOME set before any import; the judges are stubs; the network is closed."""
import json, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-seed-time-")
os.environ["HOME"] = HOME
MEM = os.path.join(HOME, ".vintos", "workspace", "memory")
os.makedirs(MEM, exist_ok=True)
POOL = os.path.join(MEM, "unfinished-threads.json")

import urllib.request
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
urllib.request.urlopen = no_network
JUDGE = {"dup": -1, "during": None}
class _Resp:
    def __init__(self, text): self._t = text
    def json(self): return {"choices": [{"message": {"content": self._t}}]}
def fake_post(url, json=None, timeout=None, headers=None, **k):
    if "100.79.177.103" not in url:
        raise AssertionError("unexpected host " + url)
    content = json["messages"][-1]["content"]
    if "UNRESOLVED TENSION" in content:
        return _Resp('{"kind": "tension", "confidence": 0.9}')
    if "NEW candidate unresolved thread" in content:
        if JUDGE["during"]: JUDGE["during"]()          # another writer saves while this judge thinks
        return _Resp('{"ok": true, "why": "concrete", "duplicate_of": %d, "why_unresolved": "I have not settled it."}' % JUDGE["dup"])
    return _Resp("{}")
sys.modules["requests"] = types.SimpleNamespace(post=fake_post, get=no_network)
sys.modules["latent_threads"] = types.SimpleNamespace(seed_thread=lambda *a, **k: None)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import emoclaw_utils as E
import thread_store as TS

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
def pool(): return json.load(open(POOL))
def by_id(i): return next(t for t in pool() if t["id"] == i)
EXISTING = {"id": "old1", "source": "idle-journal", "thread": "Whether the tide clock in the hall still runs when nobody winds it",
            "timestamp": "2026-10-01T08:00:00", "consumed": False}
def reset(threads):
    json.dump(threads, open(POOL, "w"))
    if os.path.exists(E._thread_pending_path()): os.remove(E._thread_pending_path())
    JUDGE.update(dup=-1, during=None)

check("the stores are in the scratch HOME", TS.POOL_FILE.startswith(HOME) and E._thread_pending_path().startswith(HOME))

print("--- a recurrence keeps the formation time ---")
reset([dict(EXISTING)])
JUDGE["dup"] = 0
got = E.seed_thread("idle-journal", "Whether the hall clock keeps running with no one there to wind it")
t = by_id("old1")
check("dedup: the open thread is reseen, not duplicated", got == "dedup" and len(pool()) == 1 and t.get("reseed_count") == 1, (got, pool()))
check("dedup: timestamp is still the formation time", t["timestamp"] == "2026-10-01T08:00:00", t)
check("dedup: the recurrence is recorded in last_reseen_at", str(t.get("last_reseen_at", "")) > "2026-10-01", t)

print("--- the door merges onto the pool as it is when it saves ---")
def concurrent():
    cur = TS.load_pool(POOL)
    for x in cur:
        if x["id"] == "old1": x["priority"] = 5          # e.g. triage re-rated it
    cur.append({"id": "other", "source": "pressure", "thread": "Another writer's thread that arrived meanwhile", "consumed": False,
                "timestamp": "2026-11-06T10:00:00"})
    TS.save_pool(cur, POOL, reason="concurrent-writer")
reset([dict(EXISTING)])
JUDGE["during"] = concurrent
got = E.seed_thread("creative-discovery", "What the third key on the hook by the door opens, if anything at all")
ids = [x["id"] for x in pool()]
check("admission: the new thread is in the pool", got is True and any("third key" in x["thread"] for x in pool()), (got, pool()))
check("admission: a thread another writer saved meanwhile is kept", "other" in ids, ids)
check("admission: another writer's change to an existing thread is kept", by_id("old1").get("priority") == 5, by_id("old1"))
reset([dict(EXISTING)])
JUDGE.update(dup=0, during=concurrent)
got = E.seed_thread("idle-journal", "Whether the hall clock keeps running with no one there to wind it")
check("dedup save: the concurrent thread and change are kept too",
      got == "dedup" and "other" in [x["id"] for x in pool()] and by_id("old1").get("priority") == 5 and by_id("old1").get("reseed_count") == 1, pool())
check("twins identical: scripts/ and bin/ emoclaw_utils.py",
      open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read() == open(os.path.join(REPO, "bin", "emoclaw_utils.py")).read())
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
