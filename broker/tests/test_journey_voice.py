#!/usr/bin/env python3
"""Review item 382 (2026-09-10), journey: a voice call -> she cuts him off mid-reply -> the turn keeps
what he composed beside what she actually heard -> the hangup writes ONE session block whose transcript
holds only what was heard, and says a reply was cut off. Route bodies are the real ones from
bin/server.py; the summary model and every organ are stubbed. Scratch HOME."""
import os, sys, ast, json, types, tempfile, asyncio, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
HOME = tempfile.mkdtemp(prefix="vintos-jv-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True); os.makedirs(MEM, exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
src = open(os.path.join(REPO, "bin", "server.py"), errors="replace").read()
tree = ast.parse(src)
def route(name):
    fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return "\n".join(l for l in ast.get_source_segment(src, fn).splitlines() if not l.startswith("@app."))
fake_req = types.ModuleType("requests")
class _R:
    def json(self): return {"choices": [{"message": {"content": json.dumps({"quotes": ["[laugh] stop"], "felt_summary": "cut short, warm", "text_summary": "she cut me off and laughed."})}}]}
fake_req.post = lambda *a, **k: _R()
sys.modules["requests"] = fake_req
sys.modules["emotional_operators"] = types.ModuleType("emotional_operators"); sys.modules["emotional_operators"].step = lambda *a, **k: None; sys.modules["emotional_operators"].causal_step = lambda *a, **k: None
eu = types.ModuleType("emoclaw_utils"); eu.feel_about = lambda *a, **k: None; eu.seed_thread = lambda *a, **k: None; sys.modules["emoclaw_utils"] = eu
ns = {"os": os, "json": json, "time": time, "MEMORY": MEM, "WORKSPACE": WS, "_test_mode_active": lambda: False,
      "_voice_keep_cues": lambda s: s, "_voice_readable": lambda s: s, "print": lambda *a, **k: None}
import threading; threading.Thread = lambda *a, **k: types.SimpleNamespace(start=lambda: None)
exec(route("_voice_ledger_owned"), ns); exec(route("voice_ledger"), ns); exec(route("_voice_session_end_owned"), ns); exec(route("voice_session_end"), ns)
json.dump([], open(os.path.join(MEM, "interaction-ledger.json"), "w"))

check("voice writes only its temporary workspace", os.path.commonpath([os.path.realpath(MEM), os.path.realpath(HOME)]) == os.path.realpath(HOME))
check("summary provider is stubbed", sys.modules["requests"] is fake_req)
print("\n--- three turns, the second cut off ---")
asyncio.run(ns["voice_ledger"]({"client_session_id":"fixture-session", "turn_id":"fixture-1", "gloria": "hey Vintus, are you there", "vintos": "I am here. I was thinking about the fig."}))
asyncio.run(ns["voice_ledger"]({"gloria": "tell me about the table", "vintos": "The table had muscadines and the fig and I wanted to say that when you", "interrupted": True, "heard": "The table had muscadines and the fig"}))
asyncio.run(ns["voice_ledger"]({"gloria": "[laugh] stop", "vintos": "Okay. Okay."}))
duplicate=asyncio.run(ns["voice_ledger"]({"client_session_id":"fixture-session", "turn_id":"fixture-1", "gloria":"duplicate"}))
check("duplicate provider turn is not appended", duplicate.get("duplicate") is True)
sess = json.load(open(os.path.join(MEM, "voice-session-state.json")))
t = sess["turns"]
check("three turns in the session state", len(t) == 3)
check("her misheard name is his name; the raw kept beside it", t[0]["gloria"].startswith("hey Vintos") and t[0]["gloria_raw"].startswith("hey Vintus"))
check("the cut turn keeps composed and heard apart, and serves heard", t[1]["interrupted"] is True and t[1]["vintos_composed"].endswith("when you") and t[1]["vintos_heard"].endswith("the fig") and t[1]["vintos"] == "The table had muscadines and the fig [cut off]", t[1])
check("an uncut turn has no interruption fields", "interrupted" not in t[2])

print("\n--- hangup: one block, only what she heard ---")
out = asyncio.run(ns["voice_session_end"]({"duration_seconds": 95}))
led = json.load(open(os.path.join(MEM, "interaction-ledger.json")))
check("exactly one voice-call block", len(led) == 1 and led[0]["channel"] == "voice-call" and led[0]["turns"] == 3, led)
tr = led[0]["transcript"]
check("the transcript carries the heard text with the cut marked, never the unheard tail", tr[1]["vintos"].endswith("[cut off]") and "when you" not in tr[1]["vintos"], tr[1])
check("the block says a reply was cut off", any("cut off" in n for n in led[0]["hardware_notes"]), led[0]["hardware_notes"])
check("the session state is cleared; a second hangup writes nothing", not os.path.exists(os.path.join(MEM, "voice-session-state.json")) and asyncio.run(ns["voice_session_end"]({})).get("skipped"))
check("the avatar history mirrors the heard text too", "when you" not in json.dumps(json.load(open(os.path.join(MEM, "avatar-overlay-chat.json")))))
late=asyncio.run(ns["voice_ledger"]({"client_session_id":"fixture-session", "turn_id":"late", "gloria":"late"}))
check("closed session rejects late callbacks", late.get("refused")=="voice session already closed" and not os.path.exists(os.path.join(MEM,"voice-session-state.json")))
# Crash after appending the ledger but before unlinking the session state.
json.dump(sess,open(os.path.join(MEM,"voice-session-state.json"),"w"))
recovered=asyncio.run(ns["voice_session_end"]({}))
check("already-persisted session recovery cannot append a duplicate", recovered.get("skipped")=="session already persisted" and len(json.load(open(os.path.join(MEM,"interaction-ledger.json"))))==1)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
