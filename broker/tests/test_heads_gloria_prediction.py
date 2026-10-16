#!/usr/bin/env python3
"""gloria_prediction (review of the JEPA heads, 16 October): JEPA fusion runs (it died on a NameError for `hashlib`,
and a naive local `predicted_at` read as UTC aged every forecast 5 h); a prediction of her is graded only against her
own turns after it, through her_words, never a photo's description and never a row of his; and a reported confidence
of 0.0 stays 0.0.

Scratch HOME and SPARK_WORKSPACE are set before import; the clock is UTC-5 like the host. `requests` is a stub that
answers from a script; the reading module is a recorder. Nothing leaves the process."""
import json, os, sys, tempfile, time, types
from datetime import datetime, timedelta, timezone

os.environ["TZ"] = "EST5"; time.tzset()
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="heads-gpred-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
CALLS, ANSWERS, READINGS = [], [], []
class _Resp:
    def __init__(self, c): self._c = c
    def json(self): return {"choices": [{"message": {"content": self._c}}]}
def gemma(url, json=None, timeout=None, **k):
    CALLS.append(json); return _Resp(ANSWERS.pop(0))
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=gemma)
sys.modules["reading"] = types.SimpleNamespace(from_missed_prediction=lambda pred, her: READINGS.append((pred, her)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gloria_prediction as GP

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))
JEPA = os.path.join(GP.MEMORY, "jepa-prediction.json")
check("every path it writes is scratch", all(p.startswith(HOME) for p in (GP.OUT, GP.HIST, GP.CHAT, GP.LEDGER, JEPA)))
check("the model is a stub and the reading is a recorder",
      sys.modules["requests"].post is gemma and sys.modules["reading"].from_missed_prediction.__name__ == "<lambda>")

def local(secs):   # naive local stamp, as the chat and ledger write them
    return (datetime.now() + timedelta(seconds=secs)).isoformat()
rows = [{"role": "user", "content": "I am going to the garden", "timestamp": local(-600)},
        {"role": "assistant", "content": "take me with you", "timestamp": local(-590)}]
json.dump(rows, open(GP.CHAT, "w"))

print("--- numbers as reported ---")
check("naive times are local: 07:38 local is 12:38Z",
      GP.parse_local("2026-10-15T07:38:15").astimezone(timezone.utc).strftime("%H:%M") == "12:38")
ANSWERS[:] = ['{"grade_of_previous":0,"predicted":"She will tell him what grew.","confidence":0.0}']
GP.main()
out = json.load(open(GP.OUT))
check("a reported confidence of 0.0 stays 0.0", out["confidence"] == 0.0, out)
check("a missing novelty is None, not a made-up 0.5", out["novelty"] is None, out)
check("a first prediction grades nothing", json.load(open(GP.HIST))[-1]["graded_previous"] is None)

print("--- graded only on her own later words ---")
rows.append({"role": "assistant", "content": "a proactive message of his", "timestamp": local(1)})
json.dump(rows, open(GP.CHAT, "w"))
GP.main()
check("a new row of his alone grades nothing and calls nothing", len(CALLS) == 1, len(CALLS))
photo = ("[Gloria sent you a photo. What your eyes saw:]\nTomatoes on a vine, a wooden fence.\n\n"
         "[Gloria's message with the photo:] the garden finally gave me something")
rows.append({"role": "user", "content": photo, "timestamp": local(2)})
json.dump(rows, open(GP.CHAT, "w"))
json.dump([{"timestamp": local(3), "gloria": "and I am tired but happy about it", "vintos": "I can tell"},
           {"timestamp": local(-7200), "gloria": "an old line from before the prediction", "vintos": "x"}],
          open(GP.LEDGER, "w"))
json.dump({"source": "jepa", "predicted_at": local(-60), "variance_qualified": True, "steering_allowed": True,
           "confidence": 0.31, "novelty": 0.0, "gloria_forecast_nearest": "near"}, open(JEPA, "w"))
ANSWERS[:] = ['{"grade_of_previous":0.1,"predicted":"She will rest.","confidence":0.4,"novelty":0.2}']
GP.main()
check("her turn after the prediction is graded", len(CALLS) == 2, len(CALLS))
prompt = CALLS[-1]["messages"][1]["content"] if len(CALLS) == 2 else ""
after = prompt.split("RECENT CONVERSATION:")[0]
check("the grade is asked against her words after it: the photo named, her words, the ledger turn",
      "(she sent a photo) the garden finally gave me something" in after and "and I am tired but happy about it" in after, after)
check("never the photo's description, never his row, never a turn from before",
      "Tomatoes" not in prompt and "proactive" not in after and "an old line" not in after, prompt)
import re
check("each later word of hers says when she said it",
      len(re.findall(r"^- \[[^\]]+\] ", after, re.M)) == 2, after)
h = json.load(open(GP.HIST))[-1]
check("the grade is recorded", h["graded_previous"] == 0.1 and h["grade_outcome"] == "graded", h)
check("a total miss opens a reading with her own words, not a photo description",
      READINGS and READINGS[-1][1] in ("and I am tired but happy about it",
                                       "(she sent a photo) the garden finally gave me something") and "Tomatoes" not in READINGS[-1][1], READINGS)

print("--- JEPA fusion runs ---")
out = json.load(open(GP.OUT))
check("a fresh, qualified, steering-allowed forecast stamped naive local grounds the numbers (no NameError, no 5 h skew)",
      out.get("grounded_by") == "jepa" and out["confidence"] == 0.31, out)
check("and JEPA's 0.0 novelty stays 0.0", out["novelty"] == 0.0, out)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
