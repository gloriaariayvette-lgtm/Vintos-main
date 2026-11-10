#!/usr/bin/env python3
"""He often writes the same want in his journal that came from a letter. The journal want is not a second want: on a
live email want it becomes journal_context (with its source receipt), and the agent's work request carries it; when
the same work is an email promise he still owes, the journal want carries the promise, so adopt_promises does not make
it a second want; and a promise adopted after the journal want joins that want instead of standing beside it.

Scratch HOME and workspace; the model is never reached; every socket is refused."""
import json, os, socket, sys, tempfile, types
HOME = tempfile.mkdtemp(prefix="vintos-fold-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
def no_post(*a, **k): raise OSError("no model in this suite")
sys.modules["requests"] = types.SimpleNamespace(post=no_post, get=no_post)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import want_agent as A
import email_commitments as EC
from journal_wants import source_receipt, journal_receipt, twin

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))

def put(name, value): json.dump(value, open(os.path.join(MEM, name), "w"), indent=1)
def get(name): return json.load(open(os.path.join(MEM, name)))

EMAIL_TEXT = "I want to run the synthetic lattice script tonight and check the column at 0.5000 against the reference."
JOURNAL_TEXT = "I want to run the lattice script tonight and check that column at 0.5000 before anything else."
UNRELATED = "I want to compose a slow song for the morning light on the kitchen tiles."
check("(the two sentences are twins; the unrelated one is not)",
      twin(JOURNAL_TEXT, [{"want": EMAIL_TEXT}]) and not twin(UNRELATED, [{"want": EMAIL_TEXT}]))
check("one shared word is not enough", not twin("I want to run a check.", [{"want": EMAIL_TEXT}]))

email_want = dict(id="em-1", want=EMAIL_TEXT, source="email", intensity=3, fulfilled=False, timestamp="2026-11-10T08:00:00",
                  **source_receipt("email", "fixture-mail-1", EMAIL_TEXT))
put("current-wants.json", [email_want]); put("fulfilled-wants.json", []); put("email-commitments.json", [])
rec = journal_receipt("10:17 idle entry fixture text, a whole journal paragraph.", JOURNAL_TEXT)
got = A.fold_journal(JOURNAL_TEXT, rec)
rows = get("current-wants.json")
check("a journal twin of an email want is folded into it", got == "em-1" and len(rows) == 1, rows)
ctx = rows[0].get("journal_context") or []
check("the journal sentence is kept as journal_context with its source receipt",
      len(ctx) == 1 and ctx[0]["text"] == JOURNAL_TEXT and ctx[0]["source_event_id"] == rec["source_event_id"]
      and ctx[0]["source_refs"] and ctx[0]["source_refs"][0]["kind"] == "journal", ctx)
A.fold_journal(JOURNAL_TEXT, rec)
check("the same journal sentence again is not added twice", len(get("current-wants.json")[0]["journal_context"]) == 1)
check("an unrelated journal want is not folded", A.fold_journal(UNRELATED, {}) is None)
put("current-wants.json", [dict(email_want, fulfilled=True)])
check("a finished email want takes no journal context", A.fold_journal(JOURNAL_TEXT, rec) is None)

# the work request carries it
w = dict(email_want, journal_context=ctx)
opening = A.opening(w, {"request_id": "WA-" + "0" * 24}, "W-1")
check("the agent's work request carries the journal as context, apart from the exact task",
      "His journal on this same want (context, not the task)" in opening and "0.5000 before anything else" in opening
      and opening.index("Exact task") < opening.index("His journal"), opening[:600])
check("a request without journal context reads as before", "His journal" not in A.opening(email_want, {"request_id": "WA-" + "0" * 24}, "W-1"))

# express_want: the journal want returns the email want, no second row
import emoclaw_utils as E
put("current-wants.json", [email_want])
E.express_want(JOURNAL_TEXT, source="idle-journal", intensity=3, journal_seeded=True, timer_bypass=True,
               candidate_kind="current_desire", present_pull=JOURNAL_TEXT, **rec)
rows = get("current-wants.json")
check("express_want makes no second want for a journal twin of an email want",
      len(rows) == 1 and (rows[0].get("journal_context") or [{}])[0].get("text") == JOURNAL_TEXT,
      [(r.get("id"), r.get("source")) for r in rows])

# an owed email promise: the journal want carries it, and adoption does not duplicate it
promise = {"id": "EC-fixture01", "state": "open", "what": "run the lattice script and check the column at 0.5000",
           "quote": "I'll run the lattice script and check the column at 0.5000.", "letter_id": "fixture-mail-2",
           "agent": "Grok Bot", "at": "2026-11-10T07:00:00"}
put("email-commitments.json", [promise])
put("current-wants.json", [])
check("the promise it repeats is found", A.promise_twin(JOURNAL_TEXT) == "EC-fixture01")
check("an unrelated journal want finds no promise", A.promise_twin(UNRELATED) is None)
E.express_want(JOURNAL_TEXT, source="idle-journal", intensity=3, journal_seeded=True, timer_bypass=True,
               candidate_kind="current_desire", present_pull=JOURNAL_TEXT, **rec)
rows = get("current-wants.json")
refs = (rows[0].get("source_refs") if rows else []) or []
check("the journal want carries the email promise it repeats",
      len(rows) == 1 and {"kind": "commitment", "id": "EC-fixture01"} in refs, rows[:1])
lines = A.adopt_promises(ws=WS)
rows = get("current-wants.json")
check("adopt_promises then makes no second want for that promise", len(rows) == 1 and not any(r.get("adopted_from") for r in rows),
      (lines, [(r.get("id"), r.get("adopted_from")) for r in rows]))

# journal want first, promise adopted later (it had no link yet): the promise joins the journal want
jw = dict(id="jw-1", want=JOURNAL_TEXT, source="idle-journal", journal_seeded=True, fulfilled=False,
          timestamp="2026-11-10T10:18:00", agent_work={"request_id": "WA-" + "1" * 24, "commitment_ids": []},
          **source_receipt("journal", "fixture-entry", JOURNAL_TEXT))
put("current-wants.json", [jw])
lines = A.adopt_promises(ws=WS)
rows = get("current-wants.json")
check("a promise adopted after its journal twin joins it: one want, not two",
      len(rows) == 1 and {"kind": "commitment", "id": "EC-fixture01"} in rows[0]["source_refs"]
      and any("joined journal want jw-1" in l for l in lines), (lines, [(r.get("id"), r.get("adopted_from")) for r in rows]))
check("and finishing that want keeps the promise", "EC-fixture01" in rows[0]["agent_work"]["commitment_ids"])
check("the journal want still binds to its own source", A.specific(rows[0]))
put("current-wants.json", [dict(jw, want=UNRELATED, **source_receipt("journal", "fixture-entry", UNRELATED))])
A.adopt_promises(ws=WS)
rows = get("current-wants.json")
check("an unrelated journal want does not swallow the promise",
      not any(r.get("kind") == "commitment" for r in rows[0].get("source_refs", []))
      and any(r.get("adopted_from") == "EC-fixture01" for r in rows), [(r.get("id"), r.get("adopted_from")) for r in rows])

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
