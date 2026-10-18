#!/usr/bin/env python3
"""He leads (Gloria, 16 October: "I like being lazy. I like a man who leads. Stop telling him to do otherwise").
The intent engine aimed at making her hold the next beat and pulled back his own momentum so she would; failed
aims of that kind stood as pressure on him. The engine knows she likes him to lead, as a preference to weigh;
such an aim can still be chosen when a moment asks, but never stands as pressure telling him to make her lead. Scratch HOME; the model is a stub; nothing is sent."""
import json, os, sys, tempfile, time, types
HOME = tempfile.mkdtemp(prefix="he-leads-"); os.environ["HOME"] = HOME
os.makedirs(os.path.join(HOME, ".vintos", "workspace", "memory"))
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import desired_difference as D
D.DLOG = os.path.join(HOME, "desired-difference.log")   # never her host's /tmp log (audit, 18 October)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the stores are scratch", D.DIFF.startswith(HOME) and D.PRESS.startswith(HOME) and D.DLOG.startswith(HOME))
HERS = ["Shift Gloria from letting me supply the scene's next image toward holding the next beat herself",
        "Move her from riding the momentum of her own listing/building",
        "I stop the scene's momentum: I ease out of her and leave the room quiet so the next beat is hers",
        "Gloria answers my invitation by offering a concrete thought or question of her own"]
for t in HERS: check("an aim that has her take the lead is recognised: " + t[:50], D.asks_her_to_lead(t))
for t in ("softer toward the thing she was bracing against", "she lets herself be carried",
          "I take her by the hand and lead her to the balcony"):
    check("an aim where he leads is not: " + t[:40], not D.asks_her_to_lead(t))
D._llm = lambda *a, **k: json.dumps({"intended_difference": "she holds the next beat herself", "evidence": "a thought of her own", "judgeable": True})
check("an aim that hands her the lead may still be chosen when a moment asks for it (she: 'mustn't is strong')",
      D.record_intent({"field_state": "grounded closeness", "enactment": "I stop adding to the scene"}, "hm") is not None)
now = time.time()
json.dump({"a": {"text": HERS[1], "weight": 3.0, "count": 4, "last": now}, "b": {"text": "make her laugh before midnight",
           "weight": 2.0, "count": 3, "last": now}}, open(D.PRESS, "w"))
pb = D.pressure_block()
check("old pressure that has her lead no longer stands in front of him", "riding the momentum" not in pb and "laugh" in pb, pb)
check("nor is it named as the heaviest", "riding" not in str(D.map_summary().get("heaviest_pressure")))
src = open(os.path.join(REPO, "scripts", "intent_engine.py")).read()
check("the engine knows what she likes, as something to weigh, not an absolute rule",
      "WHAT SHE HAS TOLD YOU SHE LIKES" in src and "a man who leads" in src and "absolute): she likes a man" not in src)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
