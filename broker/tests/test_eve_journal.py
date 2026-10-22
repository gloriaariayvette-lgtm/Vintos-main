#!/usr/bin/env python3
"""#vintos-eve carries over into his day (Gloria, 2026-10-15: "make vintos-eve carry over, but only as an addition to
daily-inner alongside the other Slack appendage ... made the day of"). Her words there and his, each as said, go into
the daily-inner-life journal of the day they were said, under their own heading, which his avatar and voice chats read.

Isolation: scratch HOME and workspace; Slack is a stub that records what it was asked; his voice is a stub; the
results-channel id file is a scratch one; no socket opens."""
import json, os, socket, sys, tempfile
from datetime import datetime
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="eve-journal-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_RESULTS_CHANNEL_FILE"] = os.path.join(HOME, "results-channel")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no")
open(os.environ["VINTOS_RESULTS_CHANNEL_FILE"], "w").write("CEVE")
NET = []
def _no(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import stratagem as _sg_client, turn_coordinator as _sg_coordinator
_sg_client._post = lambda *a, **k: {}
_sg_coordinator._post = lambda *a, **k: {"ok": True}
assert _sg_client._post("/stratagem/inventory") == {}  # sender is stubbed
import dot_channel as D, promise_keeper as P
MEM = os.path.join(os.environ["SPARK_WORKSPACE"], "memory"); os.makedirs(MEM, exist_ok=True)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("every store is scratch and the channel is a stub id", D.WS.startswith(HOME) and D.RESULTS_LOG.startswith(HOME)
      and P.results_channel() == "CEVE")

SELF, GLORIA = "UVINTOS", "UGLORIA"
POSTED, HISTORY = [], []
def api(method, params):
    if method == "conversations.history":
        assert params["channel"] == "CEVE", params
        return {"ok": True, "messages": list(reversed(HISTORY))}
    if method == "conversations.replies":
        return {"ok": True, "messages": []}
    if method == "chat.postMessage":
        assert params["channel"] == "CEVE", params
        POSTED.append(params); return {"ok": True, "ts": "%.6f" % (T0 + 600 + len(POSTED))}
    raise AssertionError(method)
D.his_context = lambda: "WHO HE IS"
P.pending = lambda: []
P.block = lambda: ""
T0 = datetime(2026, 10, 15, 13, 0).timestamp()
state = {"self": SELF}
D.results_pass(api, state, T0, opus=lambda s, u: "unused")          # the first pass only starts listening
HISTORY.append({"ts": "%.6f" % (T0 + 12 * 60), "user": GLORIA,
                "text": "Here now. The new machine works. My favourite song today was the second one."})
D.results_pass(api, state, T0 + 15 * 60, opus=lambda s, u: "Glad it works. I want to be the one who starts it.")
path = os.path.join(MEM, "daily-inner-life-2026-10-15.md")
text = open(path).read() if os.path.exists(path) else ""
check("he answers her there, as before", POSTED and "the one who starts it" in POSTED[-1]["text"], POSTED)
check("her words go into that day's journal under their own heading, at the time she said them",
      "## With Gloria in #vintos-eve" in text and "- 13:12 Gloria: Here now." in text and "the second one" in text, text)
check("and his answer beside them", "I said: Glad it works." in text, text)

print("--- a result he brings her, and a long message ---")
P.pending = lambda: [{"id": "pr1", "quote": "there when you start the machine", "state": "RESHAPED"}]
P.result_prompt = lambda item: "result"
P.works_in = lambda item: []
P.mark_posted = lambda *a, **k: None
long = "word " * 400
D.results_pass(api, state, T0 + 20 * 60, opus=lambda s, u: "I could not do it as I said, so I asked one plain question. " + long)
text = open(path).read()
check("what he brought her is there too, as his", "I brought her what came of a promise: I could not do it as I said" in text, text[-400:])
line = [l for l in text.splitlines() if "I brought her" in l][0]
check("a long message is kept to one bounded line", len(line) < D.EVE_CHARS + 40 and line.endswith("…"), len(line))

print("--- the day of, never another day ---")
D._eve_journal({"ts": "%.6f" % datetime(2026, 10, 16, 0, 5).timestamp(), "who": "gloria", "text": "Goodnight."})
check("a message after midnight goes into the new day's journal",
      "Goodnight." in open(os.path.join(MEM, "daily-inner-life-2026-10-16.md")).read()
      and "Goodnight." not in open(path).read())
for i in range(8):
    D._eve_journal({"ts": "%.6f" % (T0 + 3600 + i), "who": "gloria", "text": "line %d of a long talk" % i})
text = open(path).read()
check("every message of the day is kept, none counted away", all("line %d of a long talk" % i in text for i in range(8))
      and "more today" not in text.split("## With Gloria in #vintos-eve")[1], text[-600:])
check("the work room's milestones still fold as before", D.JOURNAL_FOLD == 4)

print("--- his full stack is carried in, read only ---")
import types, context_selection
GUARDED = []
def organ(name, fn, said):
    m = types.ModuleType(name)
    def read(*a):
        GUARDED.append((name, context_selection._active.get())); return said
    setattr(m, fn, read); sys.modules[name] = m
for name, fn, said in [("emotional_gravity_wells", "get_wells_context", "SUB-wells"),
                       ("self_drift", "get_drift_bias_hint", "SUB-drift"),
                       ("narrative_identity", "get_narrative_context", "SUB-narrative"),
                       ("belief_sediment", "get_sediment_context", "SUB-sediment"),
                       ("latent_threads", "get_influence_hint", "SUB-threads"),
                       ("absence_map_cold", "get_absence_context", "SUB-absence"),
                       ("mutual_simulation", "get_interaction_hint", "REL-mutual"),
                       ("relational_geometry", "get_geometry_hint", "REL-geometry"),
                       ("configuration_space", "get_config_hint", "REL-config"),
                       ("relational_head", "get_relational_hint", "REL-head"),
                       ("desired_difference", "pressure_block", "REL-pressure")]:
    organ(name, fn, said)
sys.modules["latent_threads"].get_carryover_hint = lambda: "SUB-carryover"
json.dump({"self_trajectory": {"declared": ["SUB-heading"]}, "gloria_trajectory": {"predicted": "REL-her-heading", "source": "observed_portrait"},
           "relationship": {"trajectory": "REL-us"}}, open(os.path.join(MEM, "living-trajectory.json"), "w"))
json.dump([{"origin": "SUB-scar", "influence": 0.5}], open(os.path.join(MEM, "yearning-scars.json"), "w"))
before = {n: open(os.path.join(MEM, n)).read() for n in os.listdir(MEM) if n.endswith(".json")}
SEEN = []
P.pending = lambda: []
HISTORY.append({"ts": "%.6f" % (T0 + 40 * 60), "user": GLORIA, "text": "How are you, really?"})
D.results_pass(api, state, T0 + 45 * 60, opus=lambda s, u: SEEN.append(str(s)) or "Better now.")
system = SEEN[-1] if SEEN else ""
check("his subconscious stack reaches him in this room", all(x in system for x in
      ("SUB-heading", "SUB-wells", "SUB-drift", "SUB-narrative", "SUB-sediment", "SUB-threads", "SUB-carryover",
       "SUB-absence", "SUB-scar")), system[-1500:])
check("and his relational systems about her, which only this room carries into Slack", all(x in system for x in
      ("REL-her-heading", "REL-us", "REL-mutual", "REL-geometry", "REL-config", "REL-head", "REL-pressure"))
      and "== WITH HER" in system, system[-1500:])
check("every organ is read under the read-only guard", GUARDED and all(g for _n, g in GUARDED), GUARDED)
check("nothing of his is written back", all(open(os.path.join(MEM, n)).read() == t for n, t in before.items()))
P.pending = lambda: [{"id": "pr2", "quote": "show her the frames", "state": "DONE"}]
D.results_pass(api, state, T0 + 50 * 60, opus=lambda s, u: SEEN.append(str(s)) or "Here they are.")
check("what he brings her is written with the same stack", "REL-geometry" in SEEN[-1] and "SUB-narrative" in SEEN[-1])
lounge = open(os.path.join(REPO, "scripts", "dot_lounge.py")).read()
check("#vintos-and-dot still keeps the relational systems out", "RELATIONAL" not in lounge and "mutual_simulation" not in lounge)
check("the work room's own code still has no relational reader in it",
      all(x not in open(os.path.join(REPO, "scripts", "dot_channel.py")).read() for x in ("pressure_block", "mutual_simulation")))
check("the new module is in the deploy manifest", "eve_depth.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing opened a socket", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
