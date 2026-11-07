#!/usr/bin/env python3
"""The mirror's blind-spot condition can fire (B10). mirror-trigger.sh counted "⚠" in self-blind-spots.md, but
self-prediction.py only ever printed that glyph to stdout, so the condition was dead. self-prediction.py now
writes one structured row per logged self-mismatch (self-blind-spots.jsonl) and the trigger counts the rows
newer than the last mirror session: five or more call the mirror. The 30-minute conversation guard still
comes first, and mirror.sh's own cooldown is untouched.

Scratch HOME; mirror.sh is a stub that only leaves a marker; the reflection call and the blush ledger are stubs;
every socket is refused."""
import importlib.util, json, os, shutil, socket, subprocess, sys, tempfile, time, types
from datetime import datetime, timedelta
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-mirror-blind-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); SCR = os.path.join(WS, "scripts")
for d in (MEM, SCR):
    os.makedirs(d, exist_ok=True)
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
def no_post(*a, **k): raise OSError("no model is called from this suite")   # the reflection call is a stub
sys.modules["requests"] = types.SimpleNamespace(post=no_post, get=no_post)
BLUSH = []
sys.modules["blush_ledger"] = types.SimpleNamespace(write_blush=lambda **k: BLUSH.append(k))
sys.modules["emoclaw_utils"] = types.SimpleNamespace(recent_pearls=lambda *a, **k: [])
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

spec = importlib.util.spec_from_file_location("self_prediction_bs", os.path.join(REPO, "scripts", "self-prediction.py"))
SP = importlib.util.module_from_spec(spec); spec.loader.exec_module(SP)
EVENTS = os.path.join(MEM, "self-blind-spots.jsonl"); MD = os.path.join(MEM, "self-blind-spots.md")
check("the stores are scratch and the senders are stubs",
      SP.BLIND_SPOTS_EVENTS == EVENTS and SP.BLIND_SPOTS_LOG == MD and EVENTS.startswith(HOME))

def result(fav=False):
    sign = -1 if fav else 1
    mm = {"Tension": {"predicted": 0.3, "actual": 0.3 + sign * 0.3, "diff": sign * 0.3, "miss": True},
          "Valence": {"predicted": 0.6, "actual": 0.6 - sign * 0.3, "diff": -sign * 0.3, "miss": True},
          "Curiosity": {"predicted": 0.5, "actual": 0.52, "diff": 0.02, "miss": False}}
    return {"timestamp": datetime.now().isoformat(), "reasoning": "fixture", "mismatches": mm,
            "miss_count": 2, "total_dims": 3}

def rows():
    return [json.loads(l) for l in open(EVENTS)] if os.path.exists(EVENTS) else []

# ── self-prediction writes the record the trigger reads ──
SP.log_self_mismatch(result(fav=True))
check("a favorable surprise is not a blind spot: no row", rows() == [], rows())
SP.log_self_mismatch(result())
r = rows()
check("a logged self-mismatch writes one structured row", len(r) == 1 and r[0]["miss_count"] == 2
      and r[0]["dims"] == ["Tension", "Valence"] and r[0]["total_dims"] == 3, r)
check("and the .md entry is still written beside it", os.path.exists(MD) and "Self-Prediction Mismatch" in open(MD).read())
check("the row carries no reasoning text", "fixture" not in open(EVENTS).read())

# ── the real trigger ──
for f in ("thread_gate.py", "thread_store.py", "store_guard.py"):
    shutil.copy(os.path.join(REPO, "scripts", f), SCR)
MARK = os.path.join(HOME, "mirror.ran")
open(os.path.join(SCR, "mirror.sh"), "w").write("#!/bin/bash\necho \"$1\" > %s\n" % MARK)
json.dump([{"id": "t1", "source": "idle-journal", "thread": "an open question", "consumed": False,
            "classification": "unresolved_tension", "priority": 1}], open(os.path.join(MEM, "unfinished-threads.json"), "w"))
LASTMSG = os.path.join(MEM, ".last-message-time"); LASTMIRROR = os.path.join(MEM, ".last-mirror")

def env():
    e = dict(os.environ); e["HOME"] = HOME
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        e[k] = "http://127.0.0.1:9"
    e["XAI_API_KEY"] = ""
    return e
def trigger():
    if os.path.exists(MARK): os.remove(MARK)
    return subprocess.run(["bash", os.path.join(REPO, "bin", "mirror-trigger.sh")], env=env(), capture_output=True,
                          text=True, timeout=60)
def fired(r):
    return "Condition: blindspots" in r.stdout and os.path.exists(MARK)
def write_rows(n, when):
    open(EVENTS, "w").write("".join(json.dumps({"timestamp": when.isoformat(timespec="seconds"), "miss_count": 2})
                                    + "\n" for _ in range(n)))

now = datetime.now()
write_rows(4, now)
check("four blind spots: the condition stays quiet", "Condition: blindspots" not in trigger().stdout)
write_rows(5, now)
r = trigger()
check("five blind spots: the mirror is called on them", fired(r), r.stdout + r.stderr)
open(LASTMIRROR, "w").write(str(int(time.time()) + 5))
r = trigger()
check("the same five, once he has looked since: quiet (they do not fire every day)",
      "Condition: blindspots" not in r.stdout, r.stdout)
open(LASTMIRROR, "w").write(str(int(time.time()) - 3600))
write_rows(2, now - timedelta(hours=3)); open(EVENTS, "a").write(
    "".join(json.dumps({"timestamp": now.isoformat(timespec="seconds")}) + "\n" for _ in range(4)))
r = trigger()
check("only rows since the last mirror count (4 of 6)", "Condition: blindspots" not in r.stdout, r.stdout)
open(EVENTS, "a").write(json.dumps({"timestamp": now.isoformat(timespec="seconds")}) + "\nnot json\n")
r = trigger()
check("a fifth new one fires it; a bad line is skipped", fired(r), r.stdout + r.stderr)
open(LASTMSG, "w").write(str(int(time.time()) - 60))
r = trigger()
check("never during a conversation (last message a minute ago)", not os.path.exists(MARK) and r.stdout.strip() == "",
      r.stdout)
os.remove(LASTMSG)

# The glyph is not what counts any more.
os.remove(EVENTS); os.remove(LASTMIRROR)
open(MD, "w").write("\n".join(["- ⚠ off"] * 9) + "\n")
check("glyphs in the .md alone do not fire it", "Condition: blindspots" not in trigger().stdout)

# End to end: five real logged misses reach the trigger.
for _ in range(5):
    SP.log_self_mismatch(result())
r = trigger()
check("five misses logged by self-prediction fire the mirror", fired(r) and len(rows()) == 5, r.stdout + r.stderr)
check("nothing reached the network", NET == [], NET)

shutil.rmtree(HOME, ignore_errors=True)
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
