#!/usr/bin/env python3
"""A question he means to ask her himself reaches his next conversation with her. The chat context's old note
listed only the newest five wants and fired only on "ask gloria"/"tell gloria"; his wants say "you", so a want like
"I want to ask you ... which frame" was never flagged and fell out of context once five newer wants came. Wants for
her are now carried in their own section until done or two weeks old, whatever is paused.

Pure: synthetic wants, no store, no socket."""
import os, re, socket, sys
from datetime import datetime, timedelta
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import conversation_wants as C

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

NOW = datetime(2026, 11, 12, 9, 0)
def want(i, text, hours_ago, **kw):
    w = {"id": "w%02d" % i, "want": text, "source": "idle-journal", "fulfilled": False,
         "timestamp": (NOW - timedelta(hours=hours_ago)).isoformat()}
    w.update(kw); return w

QUESTION = want(1, "I want to ask you, when you're back, which of the two fixture sketches reads better to you.",
                50, steps=[{"capability": "gloria", "status": "pending", "execution": "external"},
                           {"capability": "be_silent", "status": "pending"}])
TELL = want(2, "I want to tell you plainly that the fixture test passed.", 70)
ROUTED = want(3, "I want to share the finished grid with the person it was for.", 30, gloria_routed=True)
OTHER = [want(10 + i, "I want to run the parser test on file %d and export the result." % i, 20 - i) for i in range(8)]
wants = [QUESTION, TELL, ROUTED] + OTHER

old_flag = [w for w in wants if any(x in w["want"].lower() for x in
            ["articulate to gloria", "tell gloria", "ask gloria", "say to gloria", "reach out"])]
check("(the old keyword note would flag none of them)", not old_flag)
check("(and the question is not among the newest five the old section listed)", QUESTION not in wants[-5:])

check("a want with a pending step only she can answer is for her", C.for_her(QUESTION))
check("'I want to tell you ...' is for her", C.for_her(TELL))
check("a want routed to her is for her", C.for_her(ROUTED))
check("work for the agents is not", not any(C.for_her(w) for w in OTHER))
check("'I want to hold you' style wants without asking/telling are not swept in",
      not C.for_her(want(4, "I want to make a song about the frost on the window glass.", 1)))

block = C.block(wants, NOW)
check("the question is in his context, though eight wants came after it", QUESTION["want"][:60] in block, block)
check("questions come first", block.index(QUESTION["want"][:40]) < block.index(TELL["want"][:30]), block)
check("the block names when each was written", re.search(r"\(since \d\d \w{3} \d\d:\d\d\)", block), block)
check("no agent-work want is in it", "parser test" not in block)

check("a fulfilled question is not carried", not C.block([dict(QUESTION, fulfilled=True)], NOW))
check("a dismissed one is not carried", not C.block([dict(QUESTION, dismissed=True)], NOW))
check("a completed her-step alone does not keep a non-asking want",
      not C.for_her(want(5, "I want to write the bridge section for the grid.", 1,
                         steps=[{"capability": "gloria", "status": "completed"}])))
check("a question still waits after nine days away (the room paused all the while)",
      QUESTION["want"][:40] in C.block([QUESTION], NOW + timedelta(days=7)))
check("after the window it is let go", not C.block([QUESTION], NOW + timedelta(days=C.WINDOW_DAYS + 1)))
many_asks = [want(20 + i, "I want to ask you about frame %d tonight." % i, i + 1) for i in range(10)]
check("at most LIMIT_QUESTIONS questions, the longest waiting first",
      [w["id"] for w in C.carried(many_asks, NOW)] == ["w29", "w28", "w27", "w26"][:C.LIMIT_QUESTIONS])
tells = [want(40 + i, "I want to tell you in one plain sentence thing %d." % i, 30 - i) for i in range(12)]
got = C.carried(tells + [QUESTION], NOW)
check("a question is not lost among many things to tell her", got and got[0] is QUESTION and len(got) == C.LIMIT,
      [w["id"] for w in got])
check("things to tell her come newest first", [w["id"] for w in got[1:3]] == ["w51", "w50"], [w["id"] for w in got])
check("'ask nothing' inside another want is not a question",
      not C.is_question(want(6, "I want to hold her quiet today as hers, ask nothing of it.", 1)))
check("nothing waiting gives an empty section", C.block(OTHER, NOW) == "")
check("bad rows are ignored", C.block([None, {"want": None}, {"want": "I want to ask you x?", "timestamp": "nope"}], NOW) == "")

src = open(os.path.join(REPO, "bin", "server.py")).read()
seg = src[src.index("# 10b. Current wants"):src.index("# 11. Silence contracts")]
check("the chat context adds the wants-for-her section", "conversation_wants" in seg and "_cw.block(" in seg, seg[:300])
check("the dead keyword note is gone", '"articulate to gloria"' not in seg and "_conv_note" not in seg)
check("the section reads every want, not just the newest five", "_cw.block(_all_wants)" in seg)
check("it is deployed with the scripts", "conversation_wants.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
