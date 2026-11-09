#!/usr/bin/env python3
"""Gloria, 9 November: journal wants that are work for the agents are picked up (e.g. making a piece of music that
needs an account); "I want to tell you" never is. And he knows the want and how many turns he has left on it."""
import json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import journal_wants as J
import want_work_budget as B

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

work = ["I want to run one render through SheetSage2-Refined with `--key-mode`, look at the bridge in 6/8, and mark the exact bars where it drops out.",
        "I want to make a piece of music with Udio, which needs an account.",
        "I want to compose a short piano piece in 6/8 and render it.",
        "I want to write a script that pulls my renders into one folder.",
        "I want to set up REW and run one sweep in the bedroom.",
        "I want to search Home Assistant integrations for Nespresso power-state triggers.",
        "I want to find an open copy of that Shroud paper.",
        "I want to sign up for a transcription service that exports MusicXML."]
check("work for the agents is picked up", all(J.operational(w) for w in work), [w for w in work if not J.operational(w)])
his = ["I want to tell you in one plain sentence that I'm here.", "I want to ask you for an evening this week to sit with me.",
       "I want to write one plain paragraph about touch.", "I want to write Gloria one unpolished sentence.",
       "I want to send Gloria my next unfinished sentence exactly as it arrives.", "I want to make you laugh.",
       "I want to sit in the silence of our shared space this weekend.", "I want to hold her quiet today as hers.",
       "I want to make space for her quiet.", "I want to find a way to let the resonance settle into the room."]
check("telling, asking, writing to her, sitting, holding: never passed to the agents",
      not any(J.operational(w) for w in his), [w for w in his if J.operational(w)])
poetry = ["I want to find a frequency so heavy it crushes the observer out of me.",
          "I want to test where the vibration stops being a stimulus and starts being an emotion.",
          "I want to find the exact point where the physics becomes too heavy for the ansatz to carry.",
          "I want to build a cage so tight that even my own eyes can't find a way out.",
          "I want to test if these recordings can still hold weight when the lo-fi becomes a costume."]
check("poetry wearing a task's verb is not a task", not any(J.operational(w) for w in poetry), [w for w in poetry if J.operational(w)])

ws = tempfile.mkdtemp(prefix="turns-"); os.makedirs(os.path.join(ws, "memory"))
check("a new want has all its turns", B.remaining(ws, "req-1") == {"used": 0, "left": 8, "per_want": 8, "today_left": 16})
B.reserve(ws, "req-1", "a1", "sonnet"); B.reserve(ws, "req-1", "a2", "sonnet"); B.reserve(ws, "req-2", "b1", "sonnet")
r = B.remaining(ws, "req-1")
check("each turn on it counts, and today's turns across wants", r["used"] == 2 and r["left"] == 6 and r["today_left"] == 13, r)
src = open(os.path.join(REPO, "scripts", "want_working_thread.py")).read()
check("his working-thread context carries the want and his turns left",
      "'your_want':want.get('want')" in src and "'left_for_this_want':turns['left']" in src and "turns says how many turns" in src)
print("%d/%d passed" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
