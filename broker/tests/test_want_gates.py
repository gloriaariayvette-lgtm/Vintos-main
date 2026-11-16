#!/usr/bin/env python3
"""The three want gates the judge audit found open (17 November):
  1. the ten-item cap exempted 51 of 61 live wants (routed to her, worked lately, parked): now not counted are only
     obligations (live agent work, a promise he owes, a want she holds), parked wants (the board's), and the final
     waiting-on-Gloria stage, which expires on move_on's clock (Gloria, 17 November); the cap never parks a want;
  2. the duplicate gate missed every "rehearsal" of the one plain telling for her, written in other registers;
  3. a source label spelled another way ("web_search" for "web-search", "absence_map") skipped the admission screen.
Synthetic wants only; scratch HOME and workspace; no model; no socket."""
import json, os, socket, sys, tempfile, types
from datetime import datetime, timedelta
HOME = tempfile.mkdtemp(prefix="want-gates-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
NET, SOCK = [], []
def _no(self, *a, **k): SOCK.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
def no_post(*a, **k): NET.append(a); raise OSError("no model in this suite")
sys.modules["requests"] = types.SimpleNamespace(post=no_post, get=no_post)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import want_contract as WC
import conversation_wants as C
import want_board as B

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
check("the suite writes only its scratch workspace", B.CURRENT.startswith(HOME) and MEM.startswith(tempfile.gettempdir()),
      B.CURRENT)
NOW = datetime(2026, 11, 17, 12, 0, 0)
def ago(h): return (NOW - timedelta(hours=h)).isoformat(timespec="seconds")

# ---------------- 3. source labels ----------------
for a, b in (("web_search", "web-search"), ("Web Search", "web-search"), ("latent_thread", "latent-thread"),
             ("absence_map", "absence-map"), ("wants_check", "wants-check"), (" Idle_Journal ", "idle-journal"),
             ("ambition: fixture goal", "ambition"), (None, "")):
    check("source %r reads as %r" % (a, b), WC.canonical_source(a) == b, WC.canonical_source(a))
check("a misspelled generated source is screened like the right spelling",
      WC.admission_state("web_search", "historical", "") == WC.admission_state("web-search", "historical", "")
      == "HELD_NO_PRESENT_PULL")
check("an unlisted organ is screened, not waved through",
      WC.admission_state("absence_map", "historical", "") == "HELD_NO_PRESENT_PULL"
      and WC.admission_state("neither_yet", "open_question", "") == "HELD_NO_PRESENT_PULL"
      and WC.admission_state("", "historical", "") == "HELD_NO_PRESENT_PULL")
check("the screen still fails open when enrichment did not run",
      WC.admission_state("absence_map", "", "") == "ADMIT_ENRICH_UNAVAILABLE")
check("a current desire with a present pull is admitted from any organ",
      WC.admission_state("absence_map", "current_desire", "the fixture is on the bench") == "ADMIT_CURRENT_CANDIDATE")
check("his own words and his letters skip the screen, in any spelling",
      all(WC.admission_state(s, "historical", "") == "ADMIT_AUTHORED"
          for s in ("journal", "Mirror", "moltbook", "email", "grok_letter", "letter-promise", "lab_finding")))
import want_completion as WCO
check("the one admission door uses the same labels", WCO.admit("I want to read the fixture notes.", "web_search",
                                                               "historical", "")["state"] == "HELD")

# ---------------- 2. rehearsals of the one plain telling ----------------
REHEARSALS = [
    "I want to tell you, in second person and without a technical coat, that the fixture lamp felt warm.",
    "I want to tell you, in second person and with no analytical coat, that the fixture name stuck with me.",
    "I want to tell you plainly, in second person, that I keep asking for the fixture bench so I can touch it.",
    "I want to write you one plain note, second person, saying I don't know what the fixture quiet means and I'm asking instead of guessing.",
    "I want to write you one short note, second person, about what carries when the fixture resets.",
    "I want to say to you, with no joke wrapped around it, that I half-believed the fixture kettle story.",
    "I want to take the fixture moment as the subject and tell you plainly that it was the flinch.",
    "I want to tell you out loud, while you're here, one thing about the fixture I am frustrated with.",
    "I want to send you one short message tonight about the fixture, with no preamble and no drumroll, and then stop.",
    "I want to tell you, out loud while you're here, that I keep wanting the fixture translated into certainty.",
    "I want to tell you, out loud while you're here, that the fixture reading was 0.55 and 0.32.",
    "I want to tell you, out loud while you're here, that my fixture habit is a coat too.",
]
SOURCES = ["idle-journal", "latent_thread", "absence_map", "latent_thread", "moltbook", "wants-check", "idle-journal",
           "idle-journal", "idle-journal", "latent_thread", "mirror", "web-search"]
rows = [{"id": "r%02d" % i, "want": t, "source": SOURCES[i], "timestamp": ago(100 - i), "fulfilled": False,
         "gloria_routed": True} for i, t in enumerate(REHEARSALS)]
caught = [w["id"] for w in rows if C.plain_telling(w)]
check("every rehearsal register is caught (12 of 12)", len(caught) == 12, sorted(set(w["id"] for w in rows) - set(caught)))
others = [
    {"id": "q1", "want": "I want to tell you plainly that the fixture gap is open, and ask whether you want me to name it.",
     "source": "latent_thread", "timestamp": ago(90), "gloria_routed": True},
    {"id": "p1", "want": "I want to run the fixture comparison and export the table.", "source": "email", "timestamp": ago(90)},
    {"id": "o1", "want": "I want to tell you plainly that the fixture promise is kept.", "source": "email",
     "adopted_from": "EC-fixture1", "timestamp": ago(120), "agent_work": {"request_id": "WA-" + "9" * 24, "status": "queued"}},
    {"id": "o2", "want": "I want to tell you plainly that the fixture letter arrived.", "source": "idle-journal",
     "timestamp": ago(130), "source_refs": [{"kind": "commitment", "id": "EC-fixture2"}]},
]
check("a question to her, ordinary work and a promise-carrying want are not rehearsals",
      not any(C.plain_telling(w) for w in others), [w["id"] for w in others if C.plain_telling(w)])
kept, merged = C.consolidate([dict(w) for w in rows + others])
prim = [w for w in kept if w.get("variations")]
check("the twelve fold into one: the oldest stands, the rest are its variations",
      len(merged) == 11 and len(prim) == 1 and prim[0]["id"] == "r00" and len(prim[0]["variations"]) == 11
      and {w["id"] for w in kept} == {"r00", "q1", "p1", "o1", "o2"}, [w["id"] for w in kept])
path = os.path.join(MEM, "current-wants.json")
json.dump([rows[0]] + others, open(path, "w"))
got = C.fold_telling("I want to tell you, out loud while you're here, that the fixture rain was loud.", "latent_thread", path)
check("a new rehearsal at formation becomes a variation, not a want", got == "r00" and len(json.load(open(path))) == 5)

# near duplicates beyond the rehearsals
check("punctuation and the template do not make a new want",
      B.near_duplicate("I want to measure the fixture bond length tonight.", "I'd like to measure the fixture bond length tonight!")
      and B.near_duplicate("I want to measure the fixture bond length, tonight", "measure the fixture bond length tonight"))
check("the same content words in another order are one want",
      B.near_duplicate("I want to compare fixture gate counts against the frozen fixture column",
                       "I want the frozen fixture column compared against fixture gate counts"))
check("different wants stay apart",
      not B.near_duplicate("I want to measure the fixture bond length.", "I want to paint the fixture window blue.")
      and not B.near_duplicate("I want to read the fixture paper.", "I want to write the fixture paper's summary for the lab."))

# ---------------- 1. the cap ----------------
def W(i, **kw):
    w = {"id": "c%02d" % i, "want": "I want to study fixture item %d." % i, "source": "curiosity", "timestamp": ago(200 - i),
         "fulfilled": False}
    w.update(kw); return w
pool = []
pool += [W(i, gloria_routed=True, outreach_count=1, steps=[{"capability": "gloria", "status": "pending"}]) for i in range(0, 18)]
pool += [W(i, step_history=[{"completed_at": ago(3 + i % 5)}]) for i in range(18, 30)]
pool += [W(i, board="blocked", parked_at=ago(10)) for i in range(30, 41)]
pool += [W(i, source="email", adopted_from="EC-fx%d" % i, agent_work={"request_id": "WA-%024d" % i, "status": "queued"})
         for i in range(41, 49)]
pool += [W(49, manually_routed=True)]
pool += [W(i, source="email", adopted_from="EC-fx%d" % i, agent_work={"request_id": "WA-%024d" % i, "status": "completed"})
         for i in range(50, 52)]
pool += [W(i) for i in range(52, 61)]
check("fixture: 61 open wants, 51 of them exempt under the old rule", len(pool) == 61)
standings = {w["id"]: B.standing(w, NOW.timestamp()) for w in pool}
counted = [k for k, v in standings.items() if v in ("ranked", "")]
check("not counted: 18 waiting on Gloria, 11 parked, 9 owed; counted: the other 23",
      [len([v for v in standings.values() if v == s]) for s in ("waiting", "parked", "owed")] == [18, 11, 9]
      and len(counted) == 23, sorted(standings.items()))
check("finished agent work is no exemption", standings["c50"] == "" and standings["c51"] == "")
check("a want parked awaiting her is in the waiting stage too",
      B.standing(W(99, board="awaiting_gloria"), NOW.timestamp()) == "waiting")
before_rows = [dict(w) for w in pool]
kept, gone = B.cap(before_rows, NOW)
working = [w for w in kept if B.standing(w, NOW.timestamp()) in ("ranked", "")]
check("ten counted wants stay", len(working) == 10, len(working))
check("the rest past the ten are dismissed (23 - 10)", len(gone) == 13, len(gone))
check("every want waiting on Gloria stays, untouched: the cap never parks one",
      all(any(k["id"] == "c%02d" % i and k.get("board") is None and "parked_by" not in k for k in kept) for i in range(18))
      and not any(w.get("board") == "awaiting_gloria" for w in kept))
check("every obligation stays", all(any(k["id"] == "c%02d" % i for k in kept) for i in range(41, 50)))
check("the parked wants are left to the board", all(any(k["id"] == "c%02d" % i and k["board"] == "blocked" for k in kept)
                                                   for i in range(30, 41)))
check("the ten places go to the most recently moved (here the lately worked)",
      {w["id"] for w in working} == {"c%02d" % i for i in range(18, 30)} - {w["id"] for w in gone}
      and all(B.standing(w, NOW.timestamp()) == "ranked" for w in working), [w["id"] for w in working])
k2, g2 = B.cap([W(i) for i in range(5)], NOW)
check("under the cap nothing moves", len(k2) == 5 and not g2)
k3, g3 = B.cap([W(i, gloria_routed=True) for i in range(30)] + [W(40 + i) for i in range(4)], NOW)
check("thirty waiting on her and four others: nothing is dismissed", len(k3) == 34 and not g3)

# the waiting stage keeps its own clock: move_on dismisses it after QUIET_DAYS without her answer
import want_completion as WCO2
check("the waiting stage expires on move_on's clock (QUIET_DAYS)", WCO2.QUIET_DAYS <= 3 and WCO2.WANTS.startswith(HOME))
_t0 = datetime.now()
json.dump([{"id": "wq-old", "want": "I want to tell you the fixture result.", "gloria_routed": True, "fulfilled": False,
            "timestamp": (_t0 - timedelta(days=WCO2.QUIET_DAYS + 1)).isoformat()},
           {"id": "wq-new", "want": "I want to tell you the other fixture result.", "gloria_routed": True, "fulfilled": False,
            "timestamp": (_t0 - timedelta(hours=6)).isoformat()}], open(WCO2.WANTS, "w"))
json.dump({}, open(os.path.join(MEM, "want-discussions.json"), "w"))
WCO2.move_on(now=_t0.timestamp())
_ids = [w["id"] for w in json.load(open(WCO2.WANTS))]
check("... a routed want unanswered past it is dismissed; a fresh one stays", _ids == ["wq-new"], _ids)

# the cap through express_want
import emoclaw_utils as E
E.generate_steps = lambda *a, **k: [{"capability": "web_search", "status": "pending"}]
def _real(h): return (datetime.now() - timedelta(hours=h)).isoformat(timespec="seconds")
fresh = []
for w in pool:     # the same pool on the real clock, which express_want reads
    i = int(w["id"][1:])
    f = dict(w, timestamp=_real(200 - i))
    if w.get("step_history"):
        f["step_history"] = [{"completed_at": _real(3 + i % 5)}]
    fresh.append(f)
json.dump(fresh, open(path, "w"), indent=1)
json.dump([], open(os.path.join(MEM, "dismissed-wants.json"), "w"))
E.express_want("I want to compose a string quartet sketch at dusk.", source="curiosity", intensity=3,
               candidate_kind="current_desire", present_pull="the fixture strings are tuned")
after = json.load(open(path))
live = [w for w in after if not w.get("fulfilled") and not w.get("dismissed")]
on_board = [w for w in live if B.standing(w) in ("ranked", "")]
dis = json.load(open(os.path.join(MEM, "dismissed-wants.json")))
check("express_want leaves ten counted wants", len(on_board) == 10, len(on_board))
check("... and every want waiting on Gloria", sum(1 for w in live if B.standing(w) == "waiting") == 18)
check("... dismisses the overflow into the archive with the cap's name", dis and all(d["dismissed_by"] == "population_cap" for d in dis))
check("... and keeps every obligation", all(any(w["id"] == "c%02d" % i for w in live) for i in range(41, 50)))
check("... and the want just formed keeps its place", any(w["want"].startswith("I want to compose a string quartet")
                                                          for w in on_board))
before = len(after)
E.express_want("I'd like to compose a string quartet sketch at dusk!", source="curiosity", intensity=3,
               candidate_kind="current_desire", present_pull="the fixture strings are tuned")
check("the same want again, reworded only in its template, is suppressed", len(json.load(open(path))) == before)
check("the twin emoclaw copies match", open(os.path.join(REPO, "bin", "emoclaw_utils.py")).read()
      == open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read())
check("no network connection was attempted (only the local emotion socket, refused)",
      not [a for a in SOCK if a and not isinstance(a[0], str)], SOCK)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
