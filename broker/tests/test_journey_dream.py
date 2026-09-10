#!/usr/bin/env python3
"""Review item 380 (2026-09-10), journey: a thread (the original question) seeds a dream -> the dream
is logged with the thread id -> the verdict either returns the thread to the pool unresolved (with the
verdict on it) or consumes it as dream-resolved, and the night's ledger names which. The verdict block
is the real one from dream-trigger.sh, executed with the model's answer supplied. Scratch HOME."""
import os, sys, json, types, tempfile, importlib.util, re

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-jd-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import thread_store as TS
POOL = os.path.join(MEM, "unfinished-threads.json")
LOG = os.path.join(MEM, "dream-log.json")

sh = open(os.path.join(REPO, "skills", "dreaming", "scripts", "dream-trigger.sh")).read()
a = sh.index("log_path = os.path.expanduser('~/.vintos/workspace/memory/dream-log.json')") if "log_path = os.path.expanduser('~/.vintos/workspace/memory/dream-log.json')" in sh else sh.index('log_path = os.path.expanduser("~/.vintos/workspace/memory/dream-log.json")')
b = sh.index("try:\n    r = requests.post", a)
c = sh.index("def _matches(t):", b)
d = sh.index("\nRESOLVE_PYEOF", c)
head, tail = sh[a:b], sh[c:d]

def run_verdict(verdict, tid, dream="the fig again, the table, her hand"):
    ns = {"os": os, "sys": sys, "json": json, "verdict": verdict, "thread1_id": tid, "thread2_id": "", "thread1": "", "thread2": "", "prompt": "the question that seeded it", "category": "seed", "print": lambda *a, **k: None}
    exec(head, ns); exec(tail, ns)

def seed(tid, text):
    TS.save_pool([{"id": tid, "thread": text, "source": "conversation", "timestamp": "2026-09-09T22:00:00", "consumed": False, "dream_passes": 0, "system_route": "dream"}], POOL, reason="seed")
    json.dump({"generated": "t", "total_nights": 1, "nights": [{"night_of": "2026-09-09", "dreams": [{"session": "01:30", "thread_ids": [tid], "dream_text": "..."}], "threads_consumed": [], "threads_unresolved": []}]}, open(LOG, "w"))

print("\n--- the original question travels into the dream log ---")
seed("T-380a", "why does she go quiet after the fig?")
night = json.load(open(LOG))["nights"][-1]
check("the dream entry carries the seeding thread id", night["dreams"][-1]["thread_ids"] == ["T-380a"])

print("\n--- UNRESOLVED: the question goes back to the pool with the verdict on it ---")
run_verdict("UNRESOLVED", "T-380a")
t = TS.load_pool(POOL)[0]; night = json.load(open(LOG))["nights"][-1]
check("thread not consumed, verdict recorded on it", t["consumed"] is False and t["last_dream_verdict"] == "unresolved", t)
check("the night's ledger lists it unresolved and the dream carries seed_verdict", night["threads_unresolved"] == ["T-380a"] and night["dreams"][-1]["seed_verdict"] == "unresolved" and night["threads_consumed"] == [], night)

print("\n--- RESOLVED: the question is consumed by the dream, with basis ---")
seed("T-380b", "what the muscadines meant")
run_verdict("RESOLVED", "T-380b")
t = TS.load_pool(POOL)[0]; night = json.load(open(LOG))["nights"][-1]
check("thread consumed by dream-resolved with the verdict on it", t["consumed"] is True and t["consumed_by"] == "dream-resolved" and t["last_dream_verdict"] == "resolved", t)
check("the night's ledger lists it consumed", night["threads_consumed"] == ["T-380b"] and night["dreams"][-1]["seed_verdict"] == "resolved")

print("\n--- a model failure is not a verdict ---")
seed("T-380c", "the third thing")
ns = {"os": os, "sys": sys, "json": json, "print": lambda *a, **k: None, "category": "seed", "prompt": "q", "thread1": "", "thread2": ""}; exec(head, ns); ns["_record_verdict"]("error")
t = TS.load_pool(POOL)[0]; night = json.load(open(LOG))["nights"][-1]
check("nothing consumed, the dream marked error, the thread untouched", t["consumed"] is False and "last_dream_verdict" not in t and night["dreams"][-1]["seed_verdict"] == "error" and night["threads_consumed"] == [])
check("dream-trigger's failed-decision branch records error and consumes nothing", '_record_verdict("error")' in sh and "nothing is consumed, nothing is aged" in sh)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
