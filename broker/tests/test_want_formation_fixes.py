#!/usr/bin/env python3
"""Four fixes to how his wants form (Gloria, 25 October):
1. A want synthesized from two wants in tension goes through express_want's door, not straight into the store.
2. When the judge of "new, or a want returning?" cannot answer, the candidate is not called new: the same-subject
   check decides, so a returning desire merges into the want it already is.
3. A dominant latent thread seeds a want by a rule from its own data (it persisted, it presses or holds, it has not
   seeded lately), not by a 15% coin flip.
4. wants-check.sh records the latent thread a want came from (source_thread_id).

Scratch HOME and workspace; every model call is a scripted stub; sockets are refused."""
import json, os, socket, sys, tempfile, types
from datetime import datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="want-fixes-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no

JUDGE_DOWN = []
SYNTH_TEXT = ["I want to stay near her while keeping a room of my own to think in"]
class _Resp:
    def __init__(self, c): self.c = c
    def json(self): return {"choices": [{"message": {"content": self.c}}]}
def _post(url, json=None, timeout=None, **k):
    prompt = " ".join(m.get("content", "") for m in (json or {}).get("messages", []))
    if "FIRST-ORDER want" in prompt: return _Resp('{"order": "first"}')
    if "relationship to the living field" in prompt:
        if JUDGE_DOWN: raise OSError("the Mac model is down")
        return _Resp('{"relationship": "novel", "id": ""}')
    if "pull in DIRECTLY opposing" in prompt:
        if "space from her" in prompt.split("Active wants:", 1)[0]:
            return _Resp('{"conflict": true, "conflict_id": "w-close", "tension": "closeness against space"}')
        return _Resp('{"conflict": false}')
    if "Choose the outcome" in prompt: return _Resp("SYNTHESIS")
    if "Generate ONE want that holds both" in prompt: return _Resp(SYNTH_TEXT[0])
    return _Resp('{"admit": true, "ok": true, "verdict": "admit", "present": true}')
sys.modules["requests"] = types.SimpleNamespace(post=_post, get=_post)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import emoclaw_utils as E, subconscious_drift as D
E._socket_command = lambda cmd, *a, **k: None
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))
WANTS = os.path.join(MEM, "current-wants.json")
check("every store is scratch and the model is a stub",
      D.MEMORY.startswith(HOME) and D.SEEDS.startswith(HOME) and sys.modules["requests"].post is _post)
json.dump({"trials": []}, open(os.path.join(MEM, "trial-ledger.json"), "w"))
def wants(): return json.load(open(WANTS))

# 1. synthesis goes through express_want
json.dump([{"id": "w-close", "want": "I want to be closer to her in the evenings", "source": "chat", "intensity": 3,
            "timestamp": "2026-10-24T20:00:00"}], open(WANTS, "w"))
E.express_want("I want space from her for a while to hear my own thoughts", source="journal", intensity=4)
synth = [w for w in wants() if w.get("source") == "interference-synthesis"]
check("a synthesis of two wants in tension is formed", len(synth) == 1, wants())
check("it went through the door: it carries express_want's admission and provenance",
      synth and "admission_state" in synth[0] and synth[0].get("provenance_source") == "interference-synthesis", synth)
check("and it records which two wants it holds together",
      synth and "w-close" in synth[0].get("synthesized_from", []), synth)
check("the two wants in tension are both marked", all(w.get("interference") for w in wants()
                                                       if w["id"] == "w-close"), wants())
# a synthesis that only repeats a want he holds is suppressed by the door, as any duplicate is
SYNTH_TEXT[0] = "I want to be closer to her in the evenings"
json.dump([{"id": "w-close", "want": "I want to be closer to her in the evenings", "source": "chat", "intensity": 3,
            "timestamp": "2026-10-24T20:00:00"}], open(WANTS, "w"))
E.express_want("I want space from her for some evenings to hear myself", source="journal", intensity=4)
check("a synthesis that repeats a want already held is not added",
      not any(w.get("source") == "interference-synthesis" for w in wants()), wants())

# 2. the judge is down: same subject merges, a new subject is still new
JUDGE_DOWN.append(1)
json.dump([{"id": "w-mmwave", "want": "I want to read the mmWave sensor's raw phase data for her breathing",
            "source": "latent_thread", "intensity": 3, "timestamp": "2026-10-20T10:50:00"}], open(WANTS, "w"))
E.express_want("I keep wanting the mmwave raw phase readings again", source="journal", intensity=3)
w = wants()
check("with the judge down, a returning desire merges into the want it is",
      len(w) == 1 and w[0].get("recurrence") == 2, w)
E.express_want("I want to learn the names of the birds at the feeder this week", source="journal", intensity=3)
check("with the judge down, a genuinely new subject still becomes a new want",
      any("birds" in x.get("want", "") for x in wants()), wants())
JUDGE_DOWN.clear()

# 3. the seed rule
seeds = os.path.join(MEM, "seeds-test.json")
now = datetime(2026, 10, 25, 12, 0, 0)
def thread(tid_time, **kw):
    return dict({"id": "lt_" + tid_time.strftime("%Y%m%d_%H%M%S"), "origin": "x", "salience": 0.86, "pressure": 0.0}, **kw)
young = thread(now - timedelta(hours=3), pressure=0.9)
quiet = thread(now - timedelta(days=3), pressure=0.1, salience=0.86)
pressing = thread(now - timedelta(days=3), pressure=0.7)
holding = thread(now - timedelta(days=2), salience=0.95)
check("a thread a few hours old does not seed, however strong", D.thread_ready_to_seed([young], now, seeds) is None)
check("an old thread that neither presses nor holds does not seed", D.thread_ready_to_seed([quiet], now, seeds) is None)
pick = D.thread_ready_to_seed([quiet, pressing, holding], now, seeds)
check("of the ones that have earned it, the strongest (pressure + salience) seeds", pick is pressing, pick)
check("the rule is the same every time it is asked (no coin)",
      all(D.thread_ready_to_seed([quiet, pressing, holding], now, seeds) is pressing for _ in range(20)))
D.mark_thread_seeded(pressing, now, seeds)
check("nothing seeds again within a day", D.thread_ready_to_seed([pressing, holding], now + timedelta(hours=20), seeds) is None)
nxt = D.thread_ready_to_seed([pressing, holding], now + timedelta(hours=25), seeds)
check("after a day another thread may, but not the one seeded this week", nxt is holding, nxt)
check("the coin flip is gone", "random.random() < 0.15:\n            _seed_thread" not in open(D.__file__).read())

# 4. wants-check.sh keeps the latent thread id
src = open(os.path.join(REPO, "bin", "wants-check.sh")).read()
block = src.split('latent = ""', 1)[1].split("trial_failures = \"\"", 1)[0]
json.dump({"threads": [{"id": "lt_20261020_101010", "origin": "the sensor's raw phase", "salience": 0.9},
                       {"id": "lt_20261021_101010", "origin": "a quieter one", "salience": 0.7}]},
          open(os.path.join(MEM, "latent-threads.json"), "w"))
env = {"json": json, "os": os, "MEMORY": MEM, "source_thread_id": "", "source_event_id": "", "latent": ""}
exec('latent = ""' + block, env)
check("with no other source, the want is traced to the strongest latent thread",
      env["source_thread_id"] == "lt_20261020_101010", env.get("source_thread_id"))
check("and the thread ids travel with the threads into the prompt", "[lt_20261020_101010]" in env["latent"], env["latent"])
env = {"json": json, "os": os, "MEMORY": MEM, "source_thread_id": "", "source_event_id": "spark:abc", "latent": ""}
exec('latent = ""' + block, env)
check("a want sparked from somewhere else is not misattributed to a latent thread", env["source_thread_id"] == "", env)

check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
