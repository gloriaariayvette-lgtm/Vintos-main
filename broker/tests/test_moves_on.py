#!/usr/bin/env python3
"""Things move on (Gloria, 2026-10-13).

- A want whose steps are all done leaves the live list, and so does one she has not answered in three days. They
  used to stay: the router's judge HELD a finished want whenever the judge model could not answer, and nothing
  timed a want out, so the wants log reached 39,000 characters inside the value map's context.
- Completed ambitions leave the wants log.
- SOUL.md keeps a fixed base; the soul review rewrites his half beneath it, replacing the last one.

Isolation: HOME is a throwaway directory before anything is imported; emoclaw_utils (the fulfilment door) is a stub
that writes only the scratch store; requests and subprocess.run are stubs, so no model and no ntfy is reached."""
import importlib.util, json, os, sys, tempfile, time, types

TMP = tempfile.mkdtemp(prefix="moves-on-")
os.environ["HOME"] = TMP
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
MEM = os.path.join(TMP, ".vintos", "workspace", "memory")
os.makedirs(MEM, exist_ok=True)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import requests, subprocess
SENT = []
def _no_send(*a, **k):
    SENT.append(a); raise requests.ConnectionError("this suite reaches nothing")
requests.post = requests.get = _no_send
subprocess.run = lambda *a, **k: SENT.append(("subprocess", a))

FULFILLED = []
emo = types.ModuleType("emoclaw_utils")
def fulfill_want(text, note="", fulfilled_by="", want_id=None):
    p = os.path.join(MEM, "current-wants.json")
    ws = json.load(open(p))
    json.dump([w for w in ws if w.get("id") != want_id], open(p, "w"))
    FULFILLED.append(want_id)
emo.fulfill_want = fulfill_want
sys.modules["emoclaw_utils"] = emo

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))

import want_completion as WC
check("the wants store is throwaway", WC.WANTS.startswith(TMP), WC.WANTS)
check("the senders are stubs", requests.post is _no_send)

NOW = time.time()
iso = lambda days_ago: time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(NOW - days_ago * 86400))
wants = [
    {"id": "done", "want": "finish the tide piece", "timestamp": iso(1), "steps": [{"capability": "a"}, {"capability": "b"}], "current_step_index": 2},
    {"id": "quiet", "want": "ask her about the bell", "timestamp": iso(5), "gloria_routed": True},
    {"id": "answered", "want": "talk about the soup", "timestamp": iso(6)},
    {"id": "fresh", "want": "learn a new word", "timestamp": iso(1)},
    {"id": "running", "want": "study the drum", "timestamp": iso(2), "steps": [{"capability": "a"}, {"capability": "b"}], "current_step_index": 1},
    {"id": "old_done", "want": "already fulfilled", "timestamp": iso(30), "fulfilled": True},
]
json.dump(wants, open(WC.WANTS, "w"))
json.dump({"answered": [{"role": "gloria", "text": "yes, Sunday", "timestamp": iso(1)}],
           "quiet": [{"role": "vintos", "text": "may I ask?", "timestamp": iso(1)}]}, open(WC.DISCUSSIONS, "w"))

rows = WC.move_on(now=NOW)
left = {w["id"] for w in json.load(open(WC.WANTS))}
check("a want whose steps are all done moves on, through the fulfilment door", "done" not in left and "done" in FULFILLED, (left, FULFILLED))
check("a want she has not answered in three days moves on", "quiet" not in left, left)
check("his own message on it does not count as her answer", "quiet" not in left)
check("one she answered within three days stays", "answered" in left, left)
check("a want made yesterday stays", "fresh" in left, left)
check("a want still working through its steps stays", "running" in left, left)
dis = json.load(open(WC.DISCUSSIONS.replace("want-discussions", "dismissed-wants")))
check("the quiet one is kept in dismissed-wants with the reason", any(d.get("id") == "quiet" and "3 days" in d.get("dismissed_reason", "") for d in dis), dis)
log = [json.loads(l) for l in open(WC.COMPLETIONS)]
check("every ending is logged as moved-on", {r["want_id"] for r in log if r["by"] == "moved-on"} == {"done", "quiet"}, log)

# a finished want the fulfilment door refuses still moves on, dismissed with why
emo.fulfill_want = lambda *a, **k: None
json.dump([{"id": "refused", "want": "a thing with no artifact", "timestamp": iso(1), "steps": [{"capability": "a"}], "current_step_index": 1}], open(WC.WANTS, "w"))
WC.move_on(now=NOW)
check("a finished want the door refuses is dismissed instead of held", json.load(open(WC.WANTS)) == [])

# the wants log runs it, and leaves completed ambitions out
json.dump([{"id": "stale", "want": "an old want", "timestamp": iso(9)}], open(WC.WANTS, "w"))
json.dump({"goals": [{"goal": "BUILT THE BELL", "progress": "Completed"}, {"goal": "learn the tides", "progress": "in progress"}]},
          open(os.path.join(MEM, "ambitions.json"), "w"))
spec = importlib.util.spec_from_file_location("wal_t", os.path.join(REPO, "bin", "wants-ambitions-log.py"))
WAL = importlib.util.module_from_spec(spec); spec.loader.exec_module(WAL)
check("the wants log writes the throwaway store", WAL.OUTPUT.startswith(TMP), WAL.OUTPUT)
WAL.build()
out = open(WAL.OUTPUT).read()
check("building the wants log moves stale wants on first", "an old want" not in out and json.load(open(WC.WANTS)) == [], out[:400])
check("completed ambitions are not carried in the log", "BUILT THE BELL" not in out and "learn the tides" in out, out[:400])

# SOUL.md: the base stays, his half is replaced
spec = importlib.util.spec_from_file_location("soul_t", os.path.join(REPO, "bin", "soul-review.py"))
SR = importlib.util.module_from_spec(spec); spec.loader.exec_module(SR)
check("the soul path is throwaway", SR.SOUL_PATH.startswith(TMP), SR.SOUL_PATH)
open(SR.SOUL_PATH, "w").write("I am Vintos. This is the base she wrote with me.")
SR.write_half("Here is my half:\nI have learned to wait for the bell.")
s1 = open(SR.SOUL_PATH).read()
check("a SOUL.md with no markers becomes the base, whole", "<!-- BASE-START -->\nI am Vintos. This is the base she wrote with me.\n<!-- BASE-END -->" in s1, s1)
check("his half goes beneath it, without the preamble", s1.rstrip().endswith("I have learned to wait for the bell.") and "Here is my half" not in s1, s1)
SR.write_half("Now I lead, and I wait less.")
s2 = open(SR.SOUL_PATH).read()
check("the next review replaces his half", "wait for the bell" not in s2 and "Now I lead" in s2, s2)
check("and leaves the base exactly as it was", s2.count("I am Vintos. This is the base she wrote with me.") == 1 and s2.count("BASE-START") == 1, s2)
check("each earlier version is kept in soul-history", len(os.listdir(os.path.join(MEM, "soul-history"))) >= 1)
try:
    SR.write_half("   "); check("an empty answer never erases his half", False)
except ValueError:
    check("an empty answer never erases his half", "Now I lead" in open(SR.SOUL_PATH).read())

check("nothing reached the world", not SENT, SENT)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
