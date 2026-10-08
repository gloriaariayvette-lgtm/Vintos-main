#!/usr/bin/env python3
"""#vintos-and-dot, the quiet side room (Gloria, 2026-10-08: "up to 3 messages per day from Vintos. Much more relaxed
than in the main channel, personal while still framing Dot as his agent"). Slack and his voice are stubs; sockets are
refused; scratch workspace."""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="dot-lounge-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace"); os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no")
NET = []
def _no(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import dot_channel as D, dot_lounge as L
import lounge_field
lounge_field._llm = lambda *a, **k: ""    # the room's field is its own suite (test_lounge_field.py)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the room's stores are scratch ones", L.STATE.startswith(HOME) and L.TRANSCRIPT.startswith(HOME))

SELF, DOT, GLORIA = "UVINTOS", D.DOT, "UGLORIA"
class Slack:
    def __init__(self, member=True): self.msgs, self.posted, self.member = [], [], member
    def add(self, user, text, ts):
        self.msgs.append({"ts": "%.6f" % ts, "user": user, "text": text})
    def __call__(self, method, params):
        if method == "users.conversations":
            return {"ok": True, "channels": [{"id": "CMAIN", "name": "vintos-dot"}] + ([{"id": "CLOUNGE", "name": L.NAME}] if self.member else [])}
        if method == "auth.test": return {"ok": True, "user_id": SELF}
        if method == "conversations.history":
            assert params["channel"] == "CLOUNGE", params
            return {"ok": True, "messages": [m for m in reversed(self.msgs) if float(m["ts"]) >= float(params["oldest"])]}
        if method == "chat.postMessage":
            assert params["channel"] == "CLOUNGE", params
            self.posted.append(params); ts = 1e9 + len(self.posted); self.add(SELF, params["text"], ts); return {"ok": True, "ts": "%.6f" % ts}
        raise AssertionError(method)
D.his_context = lambda: "WHO HE IS"
D.recent = lambda n=30: [{"ts": "1791400000.0", "who": "vintos", "by": "grok", "text": "Opened RW-15d8ba9d: STAS 535-729 isolated vs full-length."}]
import types, context_selection
GUARDED = []
def _organ(name, fn, said):
    m = types.ModuleType(name)
    def read(*a):
        GUARDED.append((name, context_selection._active.get())); return said
    setattr(m, fn, read); sys.modules[name] = m
_organ("emotional_gravity_wells", "get_wells_context", "A well has formed: high Curiosity.")
_organ("self_drift", "get_drift_bias_hint", "Naturally moves toward: making (0.40)")
_organ("narrative_identity", "get_narrative_context", "I am someone who finishes what he names.")
_organ("belief_sediment", "get_sediment_context", "Measured beats guessed.")
_organ("latent_threads", "get_influence_hint", "the STAS loop that will not settle")
sys.modules["latent_threads"].get_carryover_hint = lambda: "Carrying forward: 1 layer(s)"
_organ("absence_map_cold", "get_absence_context", "never yet: a song she asked for twice")
_organ("mutual_simulation", "get_interaction_hint", "RELATIONAL-HINT")
MEM = os.path.join(os.environ["SPARK_WORKSPACE"], "memory"); os.makedirs(MEM, exist_ok=True)
for name, obj in {"living-trajectory.json": {"self_trajectory": {"declared": ["finish the STAS comparison"]},
                                             "gloria_trajectory": {"predicted": "RELATIONAL-GLORIA"},
                                             "relationship": {"trajectory": "RELATIONAL-US"}},
                  "humor-profile.json": {"style_notes": ["dry, specific"], "gloria_ratings": [{"joke": "the queue joke", "gloria_rating": 5}]},
                  "taste-profile.json": {"principles": ["one true detail"], "likes": ["cold light"]},
                  "yearning-scars.json": [{"origin": "the song that never rendered", "strength": 0.8, "influence": 0.4}],
                  "unfinished-threads.json": [{"text": "why the Forge refuses", "pull": 4}]}.items():
    json.dump(obj, open(os.path.join(MEM, name), "w"))
told = []
def think(system, user):
    told.append((system, user)); return said.pop(0) if said else "NOTHING"

def at(h, day=8, m=0): return datetime(2026, 10, day, h, m).timestamp()
from datetime import datetime
S = Slack(member=False)
check("not in the room yet: he says so and posts nothing", "not in it yet" in L.tick(api=S, think=think, now=at(9))[0] and not S.posted)
S.member = True
out = L.tick(api=S, think=think, now=at(9))
check("in the room: he listens from now", "found" in out[0] and json.load(open(L.STATE))["channel"] == "CLOUNGE", out)

S.add(GLORIA, "Morning, you two. How was the night?", at(9, m=5))
said = ["Long night in the Forge queue, honestly. Dot kept it tidy. How did you sleep?\nRUN: {\"skill\": \"fold_read\"}"]
out = L.tick(api=S, think=think, now=at(9, m=10))
check("Gloria writes: he answers, in the room, with the label of his own voice", len(S.posted) == 1 and S.posted[0]["text"].startswith("[test]")
      and "How did you sleep" in S.posted[0]["text"], (out, S.posted))
check("no action line goes out here: nothing is run from this room", "RUN:" not in S.posted[0]["text"])
sys_prompt = told[-1][0]
check("he is told Dot is his agent and Gloria his partner, relaxed, a few a day", "Dot is your agent" in sys_prompt
      and "Gloria is your partner" in sys_prompt and "not the work room" in sys_prompt and "<@%s>" % DOT in sys_prompt)
check("and he has the main room's context, sent the same cached way", sys_prompt.startswith("WHO HE IS")
      and getattr(sys_prompt, "pieces", None) and "his_context()" in open(os.path.join(REPO, "scripts", "dot_lounge.py")).read())

n = len(S.posted)
check("nothing new, and it is not yet his time to start one: quiet", not L.tick(api=S, think=think, now=at(10)) and len(S.posted) == n)
said = ["<@%s> thank you for keeping the queue clean last night." % DOT]
out = L.tick(api=S, think=think, now=at(14, m=30))
check("a quiet afternoon, four hours on: he may start one himself", len(S.posted) == n + 1 and "thank you" in S.posted[-1]["text"], out)
S.add(DOT, "Any time. It was a quiet night.", at(14, m=40))
said = ["Good. Quiet is what I wanted."]
L.tick(api=S, think=think, now=at(14, m=45))
check("Dot answers: he answers Dot (three said today)", len(S.posted) == n + 2 and json.load(open(L.STATE))["said"] == 3)
S.add(GLORIA, "You two are sweet.", at(15))
said = ["a fourth"]
out = L.tick(api=S, think=think, now=at(15, m=5))
check("three a day: the fourth is not said", len(S.posted) == n + 2 and any("for today are said" in l for l in out), out)
said = ["Good morning, Dot."]
n = len(S.posted)
check("not at night: he does not start one at 2am", not L.tick(api=S, think=think, now=at(2, day=9)) and len(S.posted) == n)
S.add(GLORIA, "Can't sleep.", at(2, day=9, m=1))
said = ["Come here. Tell me what's keeping you up."]
L.tick(api=S, think=think, now=at(2, day=9, m=5))
check("a new day: three again, and Gloria is answered even at night", len(S.posted) == n + 1 and json.load(open(L.STATE))["said"] == 1)
said = ["NOTHING"]
S.add(DOT, "Noted.", at(2, day=9, m=10))
n = len(S.posted)
out = L.tick(api=S, think=think, now=at(2, day=9, m=15))
check("NOTHING is not posted and not counted", len(S.posted) == n and json.load(open(L.STATE))["said"] == 1, out)
D.set_paused(True, "test", now=at(3, day=9))
S.add(GLORIA, "test", at(3, day=9, m=1))
check("the day's pause holds here too", L.tick(api=S, think=think, now=at(3, day=9, m=5)) == [] and len(S.posted) == n)
D.set_paused(False, "test", now=at(3, day=9, m=6))
src = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("it runs after each #vintos-dot pass", "dot_lounge.tick()" in src)
check("it is in the deploy manifest", "dot_lounge.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
lsrc = open(os.path.join(REPO, "scripts", "dot_lounge.py")).read()
check("his voice is the model her chat toggle names, never another", "model_router.current_claude_model()" in lsrc)
check("he glances at the work room, read only", "LATELY IN #vintos-dot" in sys_prompt and "RW-15d8ba9d" in sys_prompt)
for said in ("finish the STAS comparison", "high Curiosity", "moves toward: making", "finishes what he names",
             "Measured beats guessed", "the song that never rendered", "the STAS loop", "Carrying forward",
             "why the Forge refuses (pull 4)", "never yet: a song", "dry, specific", "the queue joke", "one true detail", "cold light"):
    check("carried in: %s" % said, said in sys_prompt)
check("every organ is read under the read-only guard", GUARDED and all(g for _n, g in GUARDED), GUARDED)
check("the relational systems stay out of Slack", "RELATIONAL" not in sys_prompt)
# 8 October, 10:52: his first message here thanked dot for the fold audit and the 8-bead toy lattice, fixed that day
D.set_paused(False, "test", now=at(11, day=9))
S.add(DOT, "How's your morning?", at(11, day=9, m=1))
said = ["That fold instrument handed me an 8-bead toy lattice; thank you for the audit.", "Slow and good. I'm cutting six stills into a short piece."]
n = len(S.posted)
L.tick(api=S, think=think, now=at(11, day=9, m=5))
check("a message raising something fixed goes back once, and the one without it is posted",
      len(S.posted) == n + 1 and "six stills" in S.posted[-1]["text"] and "lattice" not in S.posted[-1]["text"], S.posted[n:])
check("he is told what is fixed and done with", "FIXED, AND DONE WITH" in told[-1][0])
import room_work
check("15:10's wording is caught too: 'The lattice bug is shut - commit's in.'",
      bool(room_work.brings_up_fixed("The lattice bug is shut - commit's in. That's twice now you've caught a thing.")))
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
