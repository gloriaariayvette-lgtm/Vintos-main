#!/usr/bin/env python3
"""The emotion daemon is one file again (18 October). The copy serving him on Aegis had nudge, set_state, read and
the live state file but no version; the repository's had version and none of those, so every client's handshake
read "protocol None". Here handle() is driven with a stub engine: no model, no torch, no socket, scratch HOME."""
import json, os, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="emo-daemon-"); os.environ["HOME"] = HOME
os.environ["EMOCLAW_CONFIG"] = os.path.join(HOME, "none.yaml")
sys.modules["emotion_model.inference"] = types.SimpleNamespace(EmotionEngine=object)   # torch-free
sys.path.insert(0, os.path.join(REPO, "skills", "emoclaw", "engine"))
from emotion_model import daemon as D
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

SAVED = []
sys.modules["emotion_model.state"] = types.SimpleNamespace(save_state=lambda st, p: SAVED.append(list(st.emotion_vector)))
D.DAEMON_SOURCE = os.path.join(HOME, "ws", "emotion_model", "daemon.py")   # telemetry lands in scratch
os.makedirs(os.path.join(HOME, "ws", "memory"))
class State:
    def __init__(self): self.emotion_vector = [0.5] * 11; self.message_count = 3; self.last_updated = "x"
    def get_decayed_emotion(self, now): return list(self.emotion_vector)
class Engine:
    def __init__(self): self.state = State(); self.seen = []
    def process_message(self, message_text, **k): self.seen.append(message_text); return "BLOCK " + message_text
E = Engine()
v = D.handle(E, {"command": "version"})
check("version answers with protocol 1 and every command it takes", v["protocol_version"] == 1
      and set(v["commands"]) >= {"ping", "state", "version", "status", "nudge", "set_state", "read"}, v)
check("status is the same answer", D.handle(E, {"command": "status"})["protocol_version"] == 1)
check("ping carries the protocol", D.handle(E, {"command": "ping"})["protocol_version"] == 1)
n = D.handle(E, {"command": "nudge", "dimension": "Warmth", "amount": 0.05})
check("nudge moves one dimension and is saved", n["success"] and n["new"] > n["old"] and SAVED, n)
check("an oversized nudge is refused", D.handle(E, {"command": "nudge", "dimension": "Warmth", "amount": 0.5})["success"] is False)
check("set_state clamps and saves", D.handle(E, {"command": "set_state", "emotion_vector": [2] * 11})["emotion_vector"] == [0.95] * 11)
check("read with no text says so, without touching state", D.handle(E, {"command": "read"}) == {"error": "empty"})
before = list(E.state.emotion_vector)
check("an unknown command never runs inference", "unknown command" in D.handle(E, {"command": "bogus", "text": "hi"})["error"]
      and not E.seen and E.state.emotion_vector == before)
check("no command and no text is an error, not a crash", D.handle(E, {}) == {"error": "text required"})
out = D.handle(E, {"text": "hello"})
check("ordinary text still runs inference and writes the live state file", out == {"state_block": "BLOCK hello"}
      and os.path.exists(os.path.join(HOME, "ws", "memory", "emotional-state.txt")))
src = open(D.__file__).read()
check("an error reply is framed with a newline like every other", 'error_msg.encode("utf-8") + b"\\n"' in src)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
