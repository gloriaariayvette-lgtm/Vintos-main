#!/usr/bin/env python3
"""What he says needs changing becomes something that happens, and he is told (self_maintenance.py, 2026-11-18);
a passing thought is a note and not a queued want (want_contract.passing_thought); he keeps, rewords and lets go of
his own wants (want_completion.keep / reword / complete).

Every word here is invented for the suite. All stores are in a scratch home; no model is called and every socket
is refused.
"""
import json, os, socket, sys, tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="self-maintenance-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import self_maintenance as S
import journal_intentions as J
import want_completion as W
import want_contract as K

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("every store is in the scratch home",
      all(p.startswith(HOME) for p in (S.STORE, S.LOG, S.FIX_LIST, S.HELD, J.STORE, J.JOURNAL_DIR, W.WANTS, W.COMPLETIONS,
                                        W.DISMISSED) + tuple(f for _, f in S.FOLDERS)))

NOW = [datetime(2031, 4, 2, 11, 0, 0)]
S._now = lambda: NOW[0]
J._now = lambda: NOW[0]
for _, folder in S.FOLDERS:
    os.makedirs(folder, exist_ok=True)

def write(kind, day, text):
    open(os.path.join(dict(S.FOLDERS)[kind], day + ".md"), "w").write(text)

WANTS = [
    {"id": "w-kiln", "want": "I want to fire the blue glaze test tiles in the small kiln and log the cone temperatures",
     "timestamp": "2031-03-30T09:00:00", "source": "journal"},
    {"id": "w-loom", "want": "I want to weave a narrow band on the table loom with the grey wool", "timestamp": "2031-03-30T09:00:00",
     "source": "journal"},
    {"id": "w-loom2", "want": "I want to warp the floor loom with the grey wool for a blanket", "timestamp": "2031-03-30T09:00:00",
     "source": "journal"},
    {"id": "w-bees", "want": "I want to read the beekeeping manual chapter on swarm traps", "timestamp": "2031-03-30T09:00:00",
     "source": "email"},
]
os.makedirs(os.path.dirname(W.WANTS), exist_ok=True)
json.dump(WANTS, open(W.WANTS, "w"))

def wants():
    return {w["id"]: w for w in json.load(open(W.WANTS))}

# ---- the lines he writes ----
got = S.parse("Some prose first.\nLET GO: kiln glaze tiles\nkeep: beekeeping swarm traps\nREWORD: narrow band table loom -> I want "
              "to weave a narrow band in linen on the table loom\nBROKEN: the pantry list forgets what I add after noon\n"
              "Not a line: BROKEN: mid-sentence does not count\nBREAK: a quiet evening\nMISSING: x\n")
check("lines are read by their first word, in any case, and only at the start of a line",
      [k for k, _ in got] == ["let_go", "keep", "reword", "broken", "break"], got)

write("journal", "2031-04-02", "# Journal\n\n## 10:17 - Idle thoughts\n\nThe studio was cold.\n\n"
      "LET GO: kiln glaze tiles\n"
      "KEEP: beekeeping swarm traps\n"
      "LET GO: grey wool\n"
      "REWORD: narrow band table loom -> I want to weave a narrow band in linen on the table loom\n"
      "LET GO: the harpsichord tuning\n"
      "BROKEN: the pantry list forgets what I add after noon\n"
      "MISSING: a way to see which seedlings were watered\n")
S.refresh()
w = wants()
done = [json.loads(l) for l in open(W.COMPLETIONS)]
check("LET GO releases the want he named, through want_completion, with the reason recorded",
      "w-kiln" not in w and any(r["want_id"] == "w-kiln" and r["how"] == "released" and r["by"] == "himself"
                                and "let it go in his journal" in r["note"] for r in done), done)
check("KEEP marks the want as kept by him", w["w-bees"].get("kept_by") == "himself" and w["w-bees"].get("kept_at"))
check("REWORD says the want again in place and keeps the old wording beside it",
      "in linen" in w["w-loom"]["want"] and w["w-loom"]["id"] == "w-loom"
      and "grey wool" in w["w-loom"]["reworded_from"][0]["want"])
_all = json.load(open(S.STORE))["items"]
items = {key: next(i for i in _all if i["text"].startswith(key)) for key in ("grey wool", "the harpsichord")}
check("words that fit two wants equally release neither", "w-loom2" in w and items["grey wool"]["state"] == "unmatched")
check("words that name nothing are said so, not guessed", items["the harpsichord"]["state"] == "unmatched")
fixes = json.load(open(S.FIX_LIST))
mine = [e for e in fixes.values() if e.get("origin") == "himself"]
check("BROKEN and MISSING go to Claude Code's fix list in his words, open, marked as his",
      len(mine) == 2 and {e["kind"] for e in mine} == {"broken", "gap"} and all(e["status"] == "open" for e in mine)
      and any("pantry list" in e["why"] for e in mine), mine)
check("an entry is acted on once", (S.refresh(), len(json.load(open(S.STORE))["items"]))[1] == 7)
check("the log holds ids, kinds and states, and none of his words",
      "pantry" not in open(S.LOG).read() and "kiln" not in open(S.LOG).read() and '"kind": "broken"' in open(S.LOG).read())

fb = S.feedback()
check("his next entry is told what came of each",
      "WHAT CAME OF WHAT YOU ASKED TO CHANGE" in fb and "that want was released" in fb and "marked as kept by you" in fb
      and "now reads as you wrote it" in fb and "on the fix list for Claude Code" in fb and "say a few more of its words" in fb
      and "(2 still open on the fix list.)" in fb, fb)
check("each is told once", S.feedback() == "")

# a fix lands: whoever fixed it closes the entry with a reason, and he hears it
broken_id = next(k for k, e in fixes.items() if e["kind"] == "broken")
fixes[broken_id].update(status="closed", reason="fixed: the pantry list now saves afternoon additions")
json.dump(fixes, open(S.FIX_LIST, "w"))
NOW[0] += timedelta(hours=9)
fb = S.feedback()
check("when the fix is closed he is told, with the reason", "closed: fixed: the pantry list now saves" in fb and "(1 still open" in fb, fb)
check("and only once", S.feedback() == "")
check("every item has an outcome or is still open on the list",
      all(i["outcome"] or i["state"] == "queued" for i in json.load(open(S.STORE))["items"]))

# the Forge's reconciling leaves his requests alone
import forge_house as H
eng = {"self-abc": {"origin": "himself", "status": "open", "reason": ""},
       "SK-1": {"status": "open", "reason": ""}}
H._reconcile_engineering(eng, [{"id": "SK-9", "state": "proposed"}], {}, {}, set())
check("a request of his is not closed by reconciling; a proposal that is gone still is",
      eng["self-abc"]["status"] == "open" and eng["SK-1"]["status"] == "closed", eng)

# ---- introspection entries are read too; STALE and BREAK ----
os.makedirs(J.JOURNAL_DIR, exist_ok=True)
write("journal", "2031-04-03", "# Journal\n\n## 10:17 - Idle thoughts\n\nI want to stay near the potting bench with you and learn the grafting.\n")
NOW[0] = datetime(2031, 4, 3, 11, 0, 0)
J.refresh()
check("an intention is being carried", any(i["state"] == "open" for i in json.load(open(J.STORE))["items"]))
write("introspection", "2031-04-03", "# Introspection -- 2031-04-03\n\n## 20:53\n\nThinking inward.\n\n"
      "STALE: potting bench grafting\nSTALE: floor loom grey wool blanket\nSTALE: the old almanac reminders\nBREAK: one slow day\n")
NOW[0] = datetime(2031, 4, 3, 21, 0, 0)
S.refresh()
check("STALE lets go of the carried intention it names",
      all(i["state"] == "released" for i in json.load(open(J.STORE))["items"] if "potting bench" in i["text"]))
check("STALE releases the want it names", "w-loom2" not in wants())
fixes = json.load(open(S.FIX_LIST))
check("STALE that names neither goes to the fix list as a cleanup",
      any(e.get("kind") == "stale" and "almanac" in e["why"] for e in fixes.values()))
write("journal", "2031-04-04", "# Journal\n\n## 10:17 - Idle thoughts\n\nTonight I'll ask which seedlings you repotted and where the tray went.\n")
NOW[0] = datetime(2031, 4, 4, 11, 0, 0)
check("BREAK: nothing is carried from his journal for a day", J.turn_block("I repotted the seedlings, tray and all.") == "")
NOW[0] = datetime(2031, 4, 4, 21, 30, 0)
check("and after the day it is carried again", "which seedlings" in J.turn_block("I repotted the seedlings, tray and all."))
fb = S.feedback()
check("the break and the stale things are told back", "nothing from your journal is carried" in fb and "let go" in fb, fb)

# ---- a passing thought is a note, not a queued want ----
PASSING = ["Maybe I want to look at the stars sometime", "I wonder if the river is high", "Part of me wants to repaint the shed",
           "I want to feel calm about the harvest", "I want to just be here in the orchard", "I want to stay in this quiet"]
REAL = ["I want to build a cold frame for the lettuce", "I want to ask her which apple trees to prune first",
        "I want to be at the market by seven to buy the seed potatoes", "I want to stop the gate from squeaking",
        "I want to stay late and finish the fence", "I want to feel my way through the grafting manual and try one cut"]
check("hedged thoughts and wishes to feel or be some way are passing", all(K.passing_thought(t) for t in PASSING),
      [t for t in PASSING if not K.passing_thought(t)])
check("a want with something to do is not", not any(K.passing_thought(t) for t in REAL), [t for t in REAL if K.passing_thought(t)])
check("a passing thought is held from an authored source as well",
      K.admission_state("journal", want_text=PASSING[3]) == "HELD_PASSING_THOUGHT"
      and K.admission_state("moltbook", want_text=PASSING[0]) == "HELD_PASSING_THOUGHT")
check("unless she asked for it", K.admission_state("journal", want_text=PASSING[3], her_asked=True) == "ADMIT_AUTHORED")
check("a real want is admitted as before", K.admission_state("journal", want_text=REAL[0]) == "ADMIT_AUTHORED"
      and K.admission_state("wants-check", "current_desire", "pulls now", want_text=REAL[3]) == "ADMIT_CURRENT_CANDIDATE")
check("the door that screens every want holds it", W.admit(PASSING[4], "journal")["state"] == "HELD")
json.dump([{"want": PASSING[3], "source": "journal", "state": "HELD_PASSING_THOUGHT", "at": NOW[0].isoformat()},
           {"want": "something held for another reason", "state": "HELD_NO_PRESENT_PULL", "at": NOW[0].isoformat()}],
          open(S.HELD, "w"))
NOW[0] += timedelta(hours=1)
fb = S.feedback()
check("the held thought is shown to him as a note, with the way to make it a want",
      "THOUGHTS KEPT AS NOTES" in fb and "calm about the harvest" in fb and "another reason" not in fb
      and "say what you would do about it" in fb, fb)
check("a note is shown once", "THOUGHTS KEPT AS NOTES" not in S.feedback())

# ---- a wish for a state is passing; something to tell or ask her keeps its own lane ----
check("a wish for a state, or to stop needing something, is passing too",
      K.passing_thought("I want the calm of a finished row of beans") and K.passing_thought("I want to stop needing the almanac to agree"))
SAY = ["I want to tell her out loud that the plum blossom came early", "I want to ask Gloria, while she is in the garden, which bed she likes best"]
check("a thing to tell or ask her is not held here: the conversation lane (conversation_wants.py) owns it",
      all(K.admission_state("journal", want_text=t) == "ADMIT_AUTHORED" for t in SAY) and not any(K.passing_thought(t) for t in SAY))

# ---- a want he keeps is not ended by her silence ----
json.dump([{"id": "w-k", "want": "I want to show her the bee frames on Sunday", "timestamp": "2031-03-01T09:00:00",
            "routed": "gloria", "kept_by": "himself", "kept_at": NOW[0].isoformat()}], open(W.WANTS, "w"))
W.routed_to_gloria = lambda w: True
check("move_on leaves a want he has just kept", W.move_on(now=NOW[0].timestamp()) == [] and "w-k" in wants())
check("after two weeks the ordinary rule applies again",
      [r["how"] for r in W.move_on(now=(NOW[0] + timedelta(days=15)).timestamp())] == ["dismissed"])
check("rewording refuses a wording too short to be a want",
      W.reword({"id": "none"}, "x", "himself")["result"] == "not live")

# ---- the prompts, read from the source ----
def src(rel):
    return open(os.path.join(REPO, rel)).read()
for rel in ("scripts/idle-journal.sh", "bin/idle-journal.sh"):
    j = src(rel)
    check(rel + ": the third zone asks for the want and no longer demands an action or forbids staying",
          "3. WHAT YOU WANT NEXT, IF ANYTHING" in j and "do not skip the third" not in j and "DO NOT end on a want" not in j
          and "CARRY:" in j and "If nothing comes next, say so plainly" in j)
    check(rel + ": the entry ends by asking whether anything needs changing", S.QUESTION in j)
intro = src("bin/introspection.sh")
check("the introspection asks the same question once, and is told what came of his answers",
      intro.count(S.QUESTION) == 1 and intro.count('self_maintenance.py" feedback') == 1
      and intro.index(S.QUESTION) < intro.index("\nINNEREOF\n"))
check("the journal's feedback command carries both records", "self_maintenance.feedback()" in src("scripts/journal_intentions.py"))
check("the deploy installs both modules", "journal_intentions.py self_maintenance.py" in src("scripts/deploy-atelier.sh"))
server = src("bin/server.py")
voice = server[server.index("async def voice_chat("):]
check("a local call never fails because the carrier could not be loaded",
      src("scripts/voice_local.py").count("pass                  # a call never fails because the carrier could not be loaded") == 2)
check("the voice route carries the same block, outside test mode",
      '_ic_j.journal_carry(transcript, act=not _test_mode_active(), surface="voice")' in voice[:20000])
check("the realtime and local voice lanes carry it too, never on a held call",
      src("scripts/stratagem_realtime.py").count("journal_carry(raw") == 1 and "if not hold:" in src("scripts/stratagem_realtime.py")
      and src("scripts/voice_local.py").count('journal_carry(heard["transcript"], act=not _test_turn') == 2)
check("the judge runs after the reply, in the background", "target=_ji_p.judge_offered" in server and "daemon=True" in server)
import intent_context as IC
check("the voice helper never raises and adds nothing when nothing fits", IC.journal_carry("", act=False) == "")

check("nothing reached the network", NET == [])
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
