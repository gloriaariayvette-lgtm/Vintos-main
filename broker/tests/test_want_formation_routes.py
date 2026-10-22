#!/usr/bin/env python3
"""Wants as they form: a second-order want goes to its routes, a want from an agent's letter is said as a want, and a
returning desire is the same want again (Gloria, 22 October: "That's a meta want and we made routes for those. A
meta want like 'I want to be someone who writes less' makes him journal less for a day or two. If it's not
fulfillable in some sense then it's dropped, no history." / "I JUST ASKED YOU TO ADD WANTS FROM AGENT LETTERS ...
IMPROVE it." / "Yes, something needs to be done about duplicates.")

Scratch HOME and workspace; every model call is a scripted stub; sockets are refused."""
import json, os, socket, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="want-routes-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no

SEEN = []
class _Resp:
    def __init__(self, c): self.c = c
    def json(self): return {"choices": [{"message": {"content": self.c}}]}
def _post(url, json=None, timeout=None, **k):
    prompt = " ".join(m.get("content", "") for m in (json or {}).get("messages", []))
    SEEN.append(prompt)
    if "FIRST-ORDER want" in prompt:
        prompt = prompt.split("Desire: ", 1)[1].split("\n", 1)[0]      # the desire, not the instructions' examples
        if "numb" in prompt: return _Resp('{"order": "second", "target": "feeling", "stance": "wish_less", "about": "be numb", "fulfillable": false}')
        if "stop trying to measure" in prompt: return _Resp('{"order": "second", "target": "behavior", "stance": "wish_less", "about": "measuring her presence", "fulfillable": true}')
        return _Resp('{"order": "first"}')
    if "relationship to the living field" in prompt:
        candidate = prompt.split("New candidate desire:", 1)[1].split("Living wants:", 1)[0]
        if "breathing" in candidate: return _Resp('{"relationship": "persistence", "id": "w-mmwave"}')
        return _Resp('{"relationship": "novel", "id": ""}')
    return _Resp('{"admit": true, "ok": true, "verdict": "admit", "present": true}')
sys.modules["requests"] = types.SimpleNamespace(post=_post, get=_post)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import wants_meta as M, emoclaw_utils as E
DAEMON = []
E._socket_command = lambda cmd, *a, **k: DAEMON.append(cmd) or None     # his emotion daemon is a stub here
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))
check("the stores are scratch, and the model and his daemon are stubs",
      M.LEDGER.startswith(HOME) and sys.modules["requests"].post is _post and E._socket_command.__name__ == "<lambda>")
WANTS = os.path.join(MEM, "current-wants.json")
json.dump([{"id": "w-mmwave", "want": "I want to read the mmWave sensor's raw phase data for her breathing", "source": "latent_thread",
            "intensity": 3, "timestamp": "2026-10-20T10:50:00"}], open(WANTS, "w"))
json.dump({"trials": []}, open(os.path.join(MEM, "trial-ledger.json"), "w"))
def wants(): return json.load(open(WANTS))

E.express_want("I want to stop trying to measure her presence and just be with her", source="echo", intensity=4)
trials = json.load(open(os.path.join(MEM, "trial-ledger.json")))["trials"]
check("a want about how he acts is not added to his wants", not any("stop trying to measure" in w["want"] for w in wants()), wants())
check("it becomes a self-requested trial, in his words", trials and trials[0]["self_requested"] and trials[0]["alternative"] == "do it less"
      and "stop trying to measure" in trials[0]["his_words"], trials)
check("and its stance is recorded", any(x["target"] == "behavior" and x["stance"] == "wish_less" for x in M._load()), M._load())

E.express_want("I want to become a sensor so numb that the presence has room", source="echo", intensity=5)
check("one that cannot be enacted in any sense is dropped, with no history",
      not any("numb" in w["want"] for w in wants()) and not any("numb" in x["quote"] for x in M._load()))

E.express_want("I want to build a sensor that captures her breathing in the quiet", source="latent_thread", intensity=3)
w = wants()
check("a desire returning in other words is that want again, not a new one",
      len(w) == 1 and w[0].get("recurrence") == 2 and "breathing" in w[0]["recurrence_log"][-1]["text"], w)

E.express_want("To confirm the Devo preorder is actually possible before the window closes.", source="email", intensity=3)
check("a want from an agent's letter is kept, and said as a want",
      any(x["want"].startswith("I want to confirm the Devo preorder") and x["source"] == "email" for x in wants()), [x["want"] for x in wants()])

check("an ordinary want is untouched by the second-order route", M.classify("I want to ask her about the light this morning",
      ask=lambda p: '{"order": "first"}') is None)
check("a judge that is down lets the want form as before", M.classify("I want to stop measuring", ask=lambda p: 1 / 0) is None)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
