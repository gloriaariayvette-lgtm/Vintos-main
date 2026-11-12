#!/usr/bin/env python3
"""The population cap never dismisses a want an agent is working or that carries a promise he owes, or one routed to
her with her step pending (12 November: it dismissed an adopted promise-want in work, and the promise stayed "in work"
with no want). A promise left in work whose want is gone is adopted again, with its request and thread kept.
Synthetic wants and promises; scratch HOME and workspace; no model; no socket."""
import json, os, socket, sys, tempfile, time, types
HOME = tempfile.mkdtemp(prefix="want-cap-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
def no_post(*a, **k): raise OSError("no model in this suite")
sys.modules["requests"] = types.SimpleNamespace(post=no_post, get=no_post)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import want_agent as A
import emoclaw_utils as E
from journal_wants import source_receipt

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
def put(n, v): json.dump(v, open(os.path.join(MEM, n), "w"), indent=1)
def get(n, d=None):
    try: return json.load(open(os.path.join(MEM, n)))
    except OSError: return d

# ---- 1. the cap ----
def plain(i): return {"id": "u%02d" % i, "want": "I want to look at fixture topic number %d in detail." % i, "source": "curiosity",
                      "timestamp": "2026-11-0%dT10:00:00" % (1 + i % 9), "fulfilled": False}
adopted = {"id": "ec-fix1", "want": "I want to run the fixture comparison and export it.", "source": "email", "adopted_from": "EC-fix1",
           "timestamp": "2026-11-01T09:00:00", "fulfilled": False,
           "agent_work": {"request_id": "WA-" + "1" * 24, "status": "in_work", "thread": "1.0"}, "quiet": True}
promised = {"id": "jw-fix2", "want": "I want to run the fixture parser.", "source": "idle-journal", "timestamp": "2026-11-01T09:00:00",
            "fulfilled": False, "source_refs": [{"kind": "commitment", "id": "EC-fix2"}]}
for_her = {"id": "gf-fix3", "want": "I want to ask you which fixture sketch reads better.", "source": "mirror",
           "timestamp": "2026-11-01T09:00:00", "fulfilled": False, "outreach_count": 1,
           "steps": [{"capability": "gloria", "status": "pending"}]}
put("current-wants.json", [adopted, promised, for_her] + [plain(i) for i in range(14)])
E.express_want("I want to compose a fixture study for strings tonight.", source="curiosity", intensity=3,
               candidate_kind="current_desire", present_pull="fixture study")
left = {w["id"] for w in get("current-wants.json")}
gone = {w["id"] for w in get("dismissed-wants.json", [])}
check("the cap still prunes the unprotected", len(gone) >= 4, gone)
check("an in-work adopted promise-want is never dismissed by the cap", "ec-fix1" in left and "ec-fix1" not in gone)
check("a want carrying a promise is never dismissed", "jw-fix2" in left and "jw-fix2" not in gone)
check("a want routed to her with her step pending is never dismissed", "gf-fix3" in left and "gf-fix3" not in gone)

# ---- 2. a promise left in work whose want is gone ----
WHAT = "run the fixture comparison and export it"
put("current-wants.json", []); put("fulfilled-wants.json", [])
put("email-commitments.json", [
    {"id": "EC-fix1", "state": "in work", "work_id": "RW-fix1", "what": WHAT, "quote": "I'll run the fixture comparison.",
     "letter_id": "fixture-letter-1", "agent": "Fixture Bot", "at": "2026-11-10T08:00:00", "evidence": "the exported fixture file"},
    {"id": "EC-fix9", "state": "in work", "work_id": "RW-fix9", "what": "run the other fixture study",
     "quote": "I'll run it.", "letter_id": "fixture-letter-9", "at": "2026-11-10T08:00:00"}])
old = dict(adopted, want=WHAT, dismissed=True, dismissed_by="population_cap")
old["agent_work"] = {"request_id": "WA-" + "2" * 24, "goal_sha256": A.fingerprint(WHAT), "status": "in_work",
                     "thread": "1999999999.000100", "work_id": "RW-fix1", "agent": "dot", "quiet": {"since": 1}}
old.update(source_receipt("email", "fixture-letter-1", WHAT))
put("dismissed-wants.json", [old])
lines = A.adopt_promises(now=time.time())
rows = {w["id"]: w for w in get("current-wants.json")}
w = rows.get("ec-fix1") or {}
check("the orphaned promise is adopted again", w.get("adopted_from") == "EC-fix1", (lines, list(rows)))
check("its request and thread are kept", w.get("agent_work", {}).get("request_id") == "WA-" + "2" * 24
      and w["agent_work"].get("thread") == "1999999999.000100" and "quiet" not in w["agent_work"], w.get("agent_work"))
check("it is marked re-adopted and counted in the log", w.get("readopted") and any("re-adopted after their want was gone: 1" in l for l in lines), lines)
check("a promise in room work that never had a want is not taken", "ec-fix9" not in rows)
lines2 = A.adopt_promises(now=time.time())
check("re-adopting again does nothing (it is live now)", len(get("current-wants.json")) == len(rows)
      and not any("re-adopted" in l for l in lines2), lines2)
check("the twin emoclaw copies match", open(os.path.join(REPO, "bin", "emoclaw_utils.py")).read()
      == open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read())

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
