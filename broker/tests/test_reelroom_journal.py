#!/usr/bin/env python3
"""2026-09-10, Gloria: "The last thing in the conversation ledger should have been from the ReelRoom."
It was not: the night reached the ledger only if the app asked for the summary and the model answered.
Now every spoken turn lands in a scratch journal under memory/reelroom/ (never the ledger), and the night
becomes ONE ledger object - like a call - whether the summary comes, fails, or never arrives. Scratch HOME."""
import os, sys, json, types, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-reel-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
rc = types.ModuleType("robot_core"); rc.WORKSPACE = WS; rc.MEMORY = MEM
rc._gemma = lambda *a, **k: ""; rc._sonnet = lambda *a, **k: "my memory of tonight"; rc._read = lambda *a, **k: ""
rc.GEMMA = "g"; rc.SONNET = "s"; sys.modules["robot_core"] = rc
for name in ("requests", "numpy", "house_map", "heart_rate"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)
spec = importlib.util.spec_from_file_location("reelroom", os.path.join(REPO, "scripts", "reelroom.py"))
rr = importlib.util.module_from_spec(spec); spec.loader.exec_module(rr)
LEDGER = os.path.join(MEM, "interaction-ledger.json")
json.dump([{"timestamp": "2026-09-08T23:45:01", "source": "avatar", "channel": "avatar", "gloria": "before"}], open(LEDGER, "w"))
def ledger(): return json.load(open(LEDGER))

print("\n--- the journal is scratch, not the ledger ---")
t0 = 1_800_000_000.0
rr.journal("what did you think of that", "the room went cold with her", history=[], film_title="Vertigo", film_year="1958", elapsed_min=12, now=t0)
rr.journal("", "I chose to say this", history=[], film_title="Vertigo", elapsed_min=40, now=t0 + 60)
j = rr._load_journal()
check("two turns journaled, the event turn without a user line", len(j["chat_history"]) == 3 and j["chat_history"][0]["role"] == "user", j.get("chat_history"))
check("elapsed keeps the furthest point", j["elapsed_seconds"] == 2400)
check("the ledger is untouched by turns", len(ledger()) == 1)
check("the journal lives under memory/reelroom/", rr.JOURNAL.startswith(os.path.join(MEM, "reelroom")))

print("\n--- summary never came: the night still becomes one ledger object ---")
c = rr.commit_journal("test: app closed", now=t0 + 7200)
check("committed with its file and turn count", c["committed"] and c["file"].endswith("_vertigo.md") and c["turns"] == 3, c)
L = ledger()
check("exactly one ReelRoom entry, whole transcript, dated from the night's start", len(L) == 2 and L[-1]["channel"] == "reelroom" and L[-1]["turns"] == 2 and L[-1]["timestamp"].startswith("2027-01-15"), L[-1])
check("the ReelRoom entry is last", L[-1]["source"] == "reelroom-session")
check("listed in reelroom-sessions.json as journal-committed", json.load(open(rr.SESSIONS))[-1]["committed_by"] == "journal")
check("the journal is cleared", not os.path.exists(rr.JOURNAL))
check("a second commit is a no-op", rr.commit_journal()["committed"] is False)

print("\n--- a new film after silence commits the old night first ---")
rr.journal("hi", "hello", film_title="Rear Window", elapsed_min=1, now=t0 + 10_000)
rr.journal("ok", "yes", film_title="Rear Window", elapsed_min=2, now=t0 + 10_000 + 4 * 3600)
check("the stale journal became its own session; the fresh turn started a new one", len(ledger()) == 3 and len(rr._load_journal()["chat_history"]) == 2, (len(ledger()), rr._load_journal().get("chat_history")))

print("\n--- summary: the model failing does not lose the night ---")
def boom(*a, **k): raise RuntimeError("provider down")
p = rr.journal_payload()
out = rr.summary(p, caller=boom, now=t0 + 30_000)
check("summary() returns a file with an empty memory instead of raising", out["file"] and out["summary"] == "", out)
wrote = rr.append_session_ledger(p, out["summary"], out["file"])
check("the ledger takes the transcript without a narrative", wrote and ledger()[-1]["transcript"] and ledger()[-1]["narrative"] == "")
check("idempotent by file", rr.append_session_ledger(p, "", out["file"]) is False)

print("\n--- the server routes ---")
S = open(os.path.join(REPO, "bin", "server.py"), errors="replace").read()
check("the chat route journals each spoken turn (scratch, not ledger)", "rr.journal(msg if _actual is not None else" in S)
check("the summary route takes the fuller transcript and clears the journal", "rr.journal_payload()" in S and "os.remove(rr.JOURNAL)" in S)
check("a failed summary still commits the night from the journal", 'rr.commit_journal("summary failed' in S)
check("the scrub backfill commits a live journal first", "_rr.commit_journal(\"ledger-scrub backfill\")" in open(os.path.join(REPO, "bin", "ledger-scrub.py")).read())
check("per-turn ledger writes stay deferred on the ReelRoom surface", '"ledger") if _defer_session_ledger' in S)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
