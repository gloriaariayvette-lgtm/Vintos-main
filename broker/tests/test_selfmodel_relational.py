#!/usr/bin/env python3
"""Self-model review (16 October): world_model and reciprocal_modification update only when there is a new
exchange since their last run; reciprocal_modification reads the merged chat through evidence_view; both, and
premonition-dreamer, read her words through her_words (a photo is named, never described); a held interaction
hint keeps its own patterns with the text the ledger graded, and its tenure counts replies by when they were
said; `moment-index.py seed` never writes into the live archive.

Isolation: HOME and SPARK_WORKSPACE point at a scratch directory before anything is imported; every store this
suite writes is asserted to sit inside it; requests is a stub that answers locally and records every call; the
seed run is a subprocess under the same scratch HOME; no socket connects.
"""
import importlib.util, json, os, socket, subprocess, sys, tempfile, time, types
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="selfmodel-rel-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.join(REPO, "bin"))
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

CALLS = []
REPLY = {"content": "{}"}
class _Resp:
    def __init__(self, content): self._c = content
    def json(self): return {"choices": [{"message": {"content": self._c}}]}
_req = types.ModuleType("requests")
def _post(url, json=None, **k):
    CALLS.append(json); return _Resp(REPLY["content"])
_req.post = _post; _req.get = _post
sys.modules["requests"] = _req

import world_model as WM
import reciprocal_modification as RM
import mutual_simulation as MS

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("isolation: every store is in the scratch workspace", all(p.startswith(HOME) for p in
      (WM.CHAT, WM.OUT, RM.CHAT, RM.OUT, RM.LOG, RM.SELF_REVIEW_RECEIPTS, MS.OUT, MS.LEDGER, MS.AUDIT)))
check("isolation: requests is a local stub", RM.requests is _req and sys.modules["requests"] is _req)

now = datetime.now(timezone.utc)
PHOTO = ("[Gloria sent you a photo. What your eyes saw:]\nA woman in a red coat on a pier, gulls overhead\n\n"
         "[Gloria's message with the photo:] look where I am")
chat = [
    {"role": "user", "content": "good morning, I'm in the kitchen", "timestamp": (now - timedelta(minutes=9)).isoformat()},
    {"role": "assistant", "content": "morning. the kettle's on?", "timestamp": (now - timedelta(minutes=8)).isoformat()},
    {"role": "user", "content": PHOTO, "timestamp": (now - timedelta(minutes=5)).isoformat()},
    {"role": "assistant", "content": "TACTICAL LINE under a stratagem", "timestamp": (now - timedelta(minutes=4)).isoformat(),
     "generation_provenance": {"may_witness": False, "output_provenance": "stratagem_influenced"}},
    {"role": "assistant", "content": "the pier suits you", "timestamp": (now - timedelta(minutes=3)).isoformat()},
]
json.dump(chat, open(WM.CHAT, "w"))

# --- world model -------------------------------------------------------------------------------------------
REPLY["content"] = json.dumps({"scene": "a pier by the sea", "objects": ["gulls", "red coat"], "attention": "the view"})
CALLS.clear(); WM.main()
sent = CALLS[0]["messages"][1]["content"] if CALLS else ""
check("world model reads her words: the photo is named, not described", "(she sent a photo) look where I am" in sent
      and "What your eyes saw" not in sent and "red coat on a pier" not in sent, sent)
st1 = json.load(open(WM.OUT))
CALLS.clear(); WM.main()
check("with no new exchange it neither extracts nor rewrites the scene", CALLS == [] and json.load(open(WM.OUT)) == st1)
chat.append({"role": "user", "content": "the wind is cold here", "timestamp": now.isoformat()})
json.dump(chat, open(WM.CHAT, "w"))
CALLS.clear(); WM.main()
check("a new exchange updates the scene", len(CALLS) == 1 and json.load(open(WM.OUT))["source_key"] != st1["source_key"])

# --- reciprocal modification --------------------------------------------------------------------------------
REPLY["content"] = json.dumps({"current_state": {"warmth": 0.7}, "trajectory": "closer", "shift": "we leaned in"})
CALLS.clear(); RM.main()
prompt = CALLS[0]["messages"][1]["content"] if CALLS else ""
check("reciprocal reads through evidence_view: a tactical turn does not reach it", prompt and "TACTICAL LINE" not in prompt, prompt[-400:])
check("reciprocal reads her words: the photo is named, not described", "(she sent a photo) look where I am" in prompt
      and "What your eyes saw" not in prompt, prompt[-400:])
check("each line carries when it was said", "] Gloria: the wind is cold here" in prompt)
h1 = json.load(open(RM.LOG))
CALLS.clear(); RM.main(); RM.main()
check("with no new exchange no shift is logged and the model is not asked", CALLS == [] and json.load(open(RM.LOG)) == h1 and len(h1) == 1)
chat.append({"role": "assistant", "content": "come home and warm up", "timestamp": now.isoformat()})
json.dump(chat, open(RM.CHAT, "w"))
CALLS.clear(); RM.main()
check("a new exchange logs one new shift", len(CALLS) == 1 and len(json.load(open(RM.LOG))) == 2)

# --- premonition-dreamer ------------------------------------------------------------------------------------
spec = importlib.util.spec_from_file_location("premonition_dreamer_t", os.path.join(REPO, "scripts", "premonition-dreamer.py"))
PD = importlib.util.module_from_spec(spec); spec.loader.exec_module(PD)
check("isolation: premonition reads the scratch memory", PD.MEMORY.startswith(HOME) and PD.THREADS.startswith(HOME))
json.dump(chat[:3], open(os.path.join(MEM, "chat-history-merged.json"), "w"))
pres = PD.gather_present()
check("premonition reads her words: the photo is named, not described", "Gloria: (she sent a photo) look where I am" in pres
      and "What your eyes saw" not in pres and "red coat" not in pres, pres)

# --- mutual simulation --------------------------------------------------------------------------------------
REPLY["content"] = json.dumps({"works": ["asking about her day"], "flat": ["long monologues"]})
long_ago = (now - timedelta(days=3)).isoformat()
audits = []
for i in range(12):
    comp = 0.8 if i % 2 == 0 else 0.5
    audits.append({"id": "a%d" % i, "composite": comp, "arrived": 0.5, "moved": 0.5, "left_alive": 0.5, "explained": 0.2,
                   "note": "note %d" % i, "timestamp": long_ago, "ts": time.time()})   # said 3 days ago, scored now
json.dump(audits, open(MS.AUDIT, "w"))
prev = {"what_works": ["old works line"], "works_eligible": True, "what_falls_flat": [], "flat_eligible": False,
        "edge_note": "PREV EDGE", "patterns": [{"text": "old works line", "status": "observed", "bucket": "works", "n_evidence": 5}]}
prev_text = MS._hint_text(prev)
prev["hint_id"] = "prevhint"
json.dump(prev, open(MS.OUT, "w"))
json.dump([{"hint_id": "prevhint", "text": prev_text, "since": time.time() - 3600}], open(MS.LEDGER, "w"))
MS.main()
out = json.load(open(MS.OUT))
check("tenure counts replies by when they were said: re-scored old replies do not end a hint", out["hint_id"] == "prevhint", out.get("hint_id"))
check("the held hint keeps its own patterns with its text", out["patterns"] == prev["patterns"]
      and MS._hint_text(out) == prev_text and MS.get_interaction_hint() == prev_text)

legacy = {"what_works": ["unproven works line"], "edge_note": "LEGACY EDGE", "hint_id": "legacy"}
json.dump(legacy, open(MS.OUT, "w"))
json.dump([{"hint_id": "legacy", "text": "[INTERACTION MODEL - seems to land lately: unproven works line. growing edge: LEGACY EDGE.]",
            "since": time.time() - 3600}], open(MS.LEDGER, "w"))
MS.main()
out = json.load(open(MS.OUT))
check("a held hint that no longer serves its ledger text is replaced, so the ledger grades what is served",
      out["hint_id"] != "legacy" and json.load(open(MS.LEDGER))[-1]["hint_id"] == out["hint_id"]
      and json.load(open(MS.LEDGER))[-1]["text"] == MS._hint_text(out), out.get("hint_id"))

# --- moment-index seed ----------------------------------------------------------------------------------------
live = os.path.join(MEM, "moment-archive.json")
json.dump({"moments": {}}, open(live, "w"))
env = dict(os.environ, HOME=HOME, SPARK_WORKSPACE=WS)
p = subprocess.run([sys.executable, os.path.join(REPO, "bin", "moment-index.py"), "seed"], env=env, capture_output=True,
                   text=True, timeout=60)
check("`moment-index.py seed` leaves the live archive untouched", p.returncode == 0 and json.load(open(live)) == {"moments": {}}
      and not os.path.exists(os.path.join(MEM, "moment-index.json")) and "scratch archive" in p.stdout, (p.stdout, p.stderr[-300:]))

check("nothing left the machine (every model call answered by the local stub)", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
