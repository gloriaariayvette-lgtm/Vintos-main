#!/usr/bin/env python3
"""Self-model review (16 October): the reality anchor decays once, on read, not again on every write; running
the file no longer writes "Gloria said she misses Vintos" into her store; her chat words are filed as hers and
a photo is named, never described. Belief sediment decays by elapsed time, not per drift tick, and its readers
read the fields the store has.

Isolation: HOME and SPARK_WORKSPACE point at a scratch directory before anything is imported; the stores this
suite writes are asserted to sit inside it; requests is a stub (the contradiction check reaches nothing); the
__main__ run is a subprocess under the same scratch HOME; no socket connects.
"""
import json, os, socket, subprocess, sys, tempfile, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="selfmodel-anchor-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "bin"))

NET = []
def _no_net(self, *a, **k):
    NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

SENT = []
_req = types.ModuleType("requests")
def _post(*a, **k):
    SENT.append(a); raise OSError("stub: nothing is sent")
_req.post = _post; _req.get = _post
sys.modules["requests"] = _req

import reality_anchor as RA
import belief_sediment as BS

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("isolation: the anchor store is in the scratch workspace", RA.ANCHOR_FILE.startswith(HOME), RA.ANCHOR_FILE)
check("isolation: the sediment store is in the scratch workspace", BS.SEDIMENT_FILE.startswith(HOME), BS.SEDIMENT_FILE)
check("isolation: requests is a stub", RA.requests is _req)

# --- decay once, on read -------------------------------------------------------------------------------------
ten_days = (datetime.now() - timedelta(days=10)).isoformat()
json.dump({"events": [{"id": "old1", "statement": "the kettle in the kitchen is copper", "is_real": True,
                       "confidence": 0.8, "timestamp": ten_days, "source": "journal", "context": "journal",
                       "contradictions": [], "reinforcements": [], "contexts_seen": ["journal"]}],
           "known_pool": [], "imagined_pool": [], "source_reliability": {}, "prediction_outcomes": []},
          open(RA.ANCHOR_FILE, "w"))
RA.record_event("journal", "I wrote about the river walk this morning", is_real=False)
RA.record_event("journal", "a second unrelated note about tomorrow's plans", is_real=False)
stored = next(e for e in RA.load_anchor()["events"] if e["id"] == "old1")
check("two writes leave another event's stored confidence unchanged", stored["confidence"] == 0.8, stored["confidence"])
eff = RA.effective_confidence(stored)
check("its confidence as of now is decayed once for its age", abs(eff - round(0.8 / (1 + RA.DECAY_RATE * 10), 3)) < 0.002, eff)
act = {e["id"]: e for e in RA.get_active_beliefs(threshold=0.0, limit=50)}
check("the belief reader serves the decayed value and keeps the stored one beside it",
      abs(act["old1"]["confidence"] - eff) < 0.002 and act["old1"]["base_confidence"] == 0.8)

# --- her words, as hers -------------------------------------------------------------------------------------
e = RA.record_event("chat", "I missed you today, the bus was late again", is_real=True, confidence=1.0)
check("a chat-route event with no perpetrator is hers", e["perpetrator"] == "gloria", e.get("perpetrator"))
e2 = RA.record_event("avatar-chat", "hello from the avatar app", is_real=True, confidence=1.0)
check("the avatar route's chat is hers too", e2["perpetrator"] == "gloria")
e3 = RA.record_event("journal", "I sat with the quiet", is_real=False)
check("a journal event stays his", e3["perpetrator"] == "vintos")
photo = "[Gloria sent you a photo. What your eyes saw:]\nA woman in a red coat on a pier, gulls overhead"
e4 = RA.record_event("chat", photo[:200], is_real=True, confidence=1.0)
pool = RA.load_anchor()["known_pool"]
check("a photo is named, never described, in the grounded pool", e4 and e4["statement"].startswith("(she sent a photo)")
      and not any("What your eyes saw" in k["content"] or "red coat" in k["content"] for k in pool), [k["content"] for k in pool])

# --- the __main__ self-test ---------------------------------------------------------------------------------
before = open(RA.ANCHOR_FILE).read()
env = dict(os.environ, HOME=HOME, SPARK_WORKSPACE=WS)
p = subprocess.run([sys.executable, os.path.join(REPO, "bin", "reality_anchor.py")], env=env, capture_output=True,
                   text=True, timeout=60)
after = open(RA.ANCHOR_FILE).read()
check("running the file writes nothing to the store", p.returncode == 0 and before == after, p.stderr[-300:])
check("and never records 'Gloria said she misses Vintos'", "misses Vintos" not in after
      and "record_event(" not in open(os.path.join(REPO, "bin", "reality_anchor.py")).read().split('if __name__ == "__main__":', 1)[1])

# --- belief sediment: time, not ticks -----------------------------------------------------------------------
t0 = datetime(2026, 10, 1, 12, 0, 0)
json.dump({"beliefs": [{"pattern": "she answers late at night when she is tired", "confidence": 0.4,
                        "evidence_count": 1, "decay_rate": 0.005, "last_decayed_at": t0.isoformat()}],
           "promotions": {}}, open(BS.SEDIMENT_FILE, "w"))
for i in range(96):                                       # a day of 15-minute ticks
    BS.decay_beliefs(now=t0 + timedelta(minutes=15 * (i + 1)))
c1 = BS.load_sediment()["beliefs"][0]["confidence"]
check("a day of drift ticks takes one day's decay, not 96 steps", abs(c1 - 0.395) < 0.001, c1)
BS.decay_beliefs(now=t0 + timedelta(days=7))
c7 = BS.load_sediment()["beliefs"][0]["confidence"]
check("a 0.4 belief is still above 0.3 after a week unreinforced", c7 > 0.3 and abs(c7 - 0.365) < 0.002, c7)
BS.decay_beliefs(now=t0 + timedelta(days=7))
check("decaying twice at the same moment changes nothing", BS.load_sediment()["beliefs"][0]["confidence"] == c7)
json.dump({"beliefs": [{"pattern": "an unstamped legacy belief", "confidence": 0.3, "evidence_count": 1}], "promotions": {}},
          open(BS.SEDIMENT_FILE, "w"))
BS.decay_beliefs()
b = BS.load_sediment()["beliefs"][0]
check("a legacy belief is stamped without a catch-up step", b["confidence"] == 0.3 and b.get("last_decayed_at"))
BS.promote_hypothesis("when she sends a song she wants me to listen closely", hypothesis_id=None)
nb = [x for x in BS.load_sediment()["beliefs"] if x["pattern"].startswith("when she sends")][0]
check("a new belief carries its decay stamp", nb.get("last_decayed_at"))

for twin in ("scripts/belief-sediment.py", "scripts/belief_sediment.py"):
    check("twin %s is identical" % twin, open(os.path.join(REPO, twin)).read() == open(os.path.join(REPO, "bin", "belief-sediment.py")).read())

sr = open(os.path.join(REPO, "bin", "soul-review.py")).read()
smu = open(os.path.join(REPO, "bin", "self-model-update.sh")).read()
check("soul-review reads the store's pattern field", 'b["text"]' not in sr and 'b.get("pattern")' in sr)
check("self-model-update reads pattern and confidence", "b.get('pattern')" in smu and "b.get('confidence'" in smu)

check("nothing left the machine", not NET and not SENT, (NET, SENT))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
