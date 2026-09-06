#!/usr/bin/env python3
"""His body on Aegis, without the web layer or any model: the Pi's push is stored (frame hash on disk, never
the image); movement needs a fresh frame and clear sonar; stop jumps the line and clears the queue; the Pi
drains fresh commands and stale ones are dropped; a Sonnet reply becomes speech + one bounded command + an
intent row; the archive the subconscious reads gets sense/action/interaction rows; the subconscious turns the
archive into pressure strings that reach his prompt. Scratch workspace only; nothing of his is touched."""
import os, sys, json, tempfile, importlib.util as iu
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(); MEM = os.path.join(TMP, "memory"); os.makedirs(MEM)
os.environ["SPARK_WORKSPACE"] = TMP
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import robot_core as rc; import robot_subconscious as rs
assert rc.MEMORY == MEM and rs.MEMORY == MEM
# the gate his body answers to is ARMED on Aegis (test mode is on there): point every flag it reads into the
# scratch dir so this suite exercises the body's own refusals, not the host's arming - the gate's arming is
# covered by its own suite. Also: a gate that denies armed no-context moves is the production truth.
import effect_gate as EG
EG.MEM = MEM; EG.ARMED_FLAG = os.path.join(MEM, "nonexistent-armed"); EG.TEST_MODE_FLAG = os.path.join(MEM, "nonexistent-test-mode")
EG.STOP_BUTTON = os.path.join(MEM, "hardware-button.json")
for _n in ("LOG", "LOG_FILE", "GATE_LOG", "DECISION_LOG", "LEDGER"):
    if hasattr(EG, _n) and isinstance(getattr(EG, _n), str): setattr(EG, _n, os.path.join(MEM, os.path.basename(getattr(EG, _n))))
R = []
def check(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -- {d}"))

T = 1_000_000.0
FRAME = "QUJD" * 200
# --- the Pi pushes
st = rc.ingest_sensor({"frame_b64": FRAME, "sonar_cm": 64.6, "room_description": "person(62%), potted plant(59%)", "cat_detected": False}, now=T)
check("push stored: frame fresh, sonar, room", st["frame_fresh"] and st["sonar_cm"] == 64.6 and "plant" in st["room_description"], st)
disk = json.load(open(rc.STATE_FILE))
check("disk state carries the frame hash, never the image", disk["frame_sha"] and "frame_b64" not in disk and FRAME not in open(rc.STATE_FILE).read())
check("context text is plain and grounded", "Camera sees: person" in rc.context_text(T) and "65 cm" in rc.context_text(T), rc.context_text(T))
try:
    rc.ingest_sensor(["not", "an", "object"]); check("non-object push refused", False)
except ValueError:
    check("non-object push refused", True)

# --- commands
r = rc.queue_command({"command": "move_forward", "duration_ms": 9000}, now=T + 1)
check("move queued and clamped to 1500 ms", r["status"] == "queued" and r["command"]["duration_ms"] == 1500, r)
r = rc.queue_command({"command": "fly"}, now=T + 1)
check("unknown command refused with a reason", r["status"] == "refused" and "unknown" in r["why"], r)
r = rc.queue_command({"command": "run_action", "value": {"name": "shake_head"}}, now=T + 1)
check("shake_head maps to the Pi's shake gesture", r["status"] == "queued" and r["command"]["value"] == {"name": "shake"}, r)
r = rc.queue_command({"command": "run_action", "value": {"name": "backflip"}}, now=T + 1)
check("unknown gesture refused", r["status"] == "refused", r)
r = rc.queue_command({"command": "turn_left"}, now=T + 1)
r2 = rc.queue_command({"command": "turn_right"}, now=T + 1)
check("queue is bounded at three", r["status"] == "queued" and r2["status"] == "refused" and "queue full" in r2["why"], (r, r2))
r = rc.stop(source="test")
check("stop clears the queue and stands alone at the front", r["status"] == "queued" and [c["command"] for c in rc.pending_snapshot()] == ["stop"], rc.pending_snapshot())
taken = rc.take_pending(now=T + 2)
check("the Pi drains the queue", [c["command"] for c in taken] == ["stop"] and rc.pending_snapshot() == [])
rc.queue_command({"command": "move_back"}, now=T + 3)
check("stale commands are dropped, not executed late", rc.take_pending(now=T + 60) == [] and rc.pending_snapshot() == [])

# gates on movement
rc.ingest_sensor({"sonar_cm": 12.0}, now=T + 5)
r = rc.queue_command({"command": "move_forward"}, now=T + 5)
check("too close on sonar: forward refused, reason names the distance", r["status"] == "refused" and "12 cm" in r["why"], r)
r = rc.queue_command({"command": "move_back"}, now=T + 5)
check("backing away is still allowed when close", r["status"] == "queued", r); rc.take_pending(now=T + 5)
r = rc.queue_command({"command": "turn_left"}, now=T + 100)
check("no fresh frame: movement refused", r["status"] == "refused" and "fresh camera frame" in r["why"], r)
r = rc.queue_command({"command": "run_action", "value": {"name": "nod"}}, now=T + 100)
check("a gesture needs no frame", r["status"] == "queued", r); rc.take_pending(now=T + 100)
rc.ingest_sensor({"frame_b64": FRAME, "sonar_cm": 80, "cat_detected": True}, now=T + 200)
r = rc.queue_command({"command": "move_forward"}, now=T + 200)
check("cat detected: frozen", r["status"] == "refused" and "cat" in r["why"], r)
rc.ingest_sensor({"frame_b64": FRAME, "sonar_cm": 80, "cat_detected": False}, now=T + 300)

# --- the gate, armed: a move with no turn context is refused; stop still passes
open(EG.ARMED_FLAG, "w").close()
r = rc.queue_command({"command": "turn_left"}, now=T + 300)
check("armed gate, no context: movement refused with the gate's reason", r["status"] == "refused" and "no turn context" in str(r["why"]), r)
r = rc.stop(source="test")
check("armed gate: stop still goes through", r["status"] == "queued", r); rc.take_pending(now=T + 300)
os.remove(EG.ARMED_FLAG)

# --- reply parsing
p = rc.parse_reply('I see you by the plant. [EYES: happy]\n{"command": "move_forward", "duration_ms": 700, "goal": "reach her", "subgoal": "cross the rug", "confidence": 0.7, "reason": "she called me", "impulses": "wait | nod"}')
check("speech, command, intent and eyes separate cleanly", p["speech"] == "I see you by the plant." and p["command"] == {"command": "move_forward", "duration_ms": 700}
      and p["intent"]["goal"] == "reach her" and p["eyes"] == ["happy"], p)
p = rc.parse_reply("Just words tonight.")
check("no JSON means speech only", p["speech"] == "Just words tonight." and p["command"] is None and p["intent"] is None)

# --- chat through a fake Sonnet and a fake speaker
said = []
fake = lambda system, msgs, image_b64=None: ('Come here, I want to look at you properly. [EYES: love]\n'
        '{"command": "move_forward", "duration_ms": 600, "goal": "be near her", "subgoal": "close the gap", "confidence": 0.8, "reason": "she asked", "impulses": "stay"}')
seen_system = {}
def fake_caller(system, msgs, image_b64=None):
    seen_system["s"] = system; seen_system["img"] = image_b64; return fake(system, msgs, image_b64)
out = rc.chat("Vintos, come see what I made", history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hi back"}],
              now=T + 300, caller=fake_caller, speaker=lambda t: said.append(t) or True)
check("chat: speech spoken, command queued, intent recorded, eyes carried", out["ok"] and said == ["Come here, I want to look at you properly."]
      and out["command"]["status"] == "queued" and out["intent"]["goal"] == "be near her" and out["eyes"] == ["love"], out)
check("the fresh frame went to the voice model", seen_system["img"] == FRAME)
check("the system prompt carries the body's context and the grounding rule", "Camera sees" in seen_system["s"] and "GROUNDING" in seen_system["s"])
check("voice latest holds what he said", rc.voice_latest()["text"].startswith("Come here"))
rows = [json.loads(l) for l in open(rc.INTENT_LEDGER)]
check("intent ledger row", rows[-1]["goal"] == "be near her" and rows[-1]["confidence"] == 0.8, rows[-1])
def broken(system, msgs, image_b64=None): raise RuntimeError("no key")
out = rc.chat("hello", now=T + 301, caller=broken)
check("voice model failure is reported, not spoken", out["ok"] is False and "voice model" in out["why"] and out["speech"] == "")

# --- look through a fake Gemma
g = rc.look("the red cube", caller=lambda m: 'Sure: {"present": true, "x_pct": 515, "size_pct": 12, "note": "on the rug"}')
check("look: x10 answers corrected, bounded, note kept", g["ok"] and g["present"] and g["x_pct"] == 51.5 and g["size_pct"] == 12 and g["note"] == "on the rug", g)
g = rc.look(None, caller=lambda m: "A person stands by a potted plant; the floor ahead is clear.")
check("look without a question describes", g["ok"] and "potted plant" in g["description"])
g = rc.look("cat", caller=lambda m: "I cannot tell")
check("gemma without JSON is an honest failure", g["ok"] is False and "usable JSON" in g["why"])

# --- archive and subconscious
arch = [json.loads(l) for l in open(rc.ARCHIVE)]
kinds = [a["type"] for a in arch]
check("archive has sense, action and interaction rows", "sense" in kinds and "action" in kinds and "interaction" in kinds, kinds)
check("sense rows are thinned", kinds.count("sense") <= 4, kinds.count("sense"))
for i in range(6):   # enough rows for the subconscious
    rc.ingest_sensor({"frame_b64": FRAME, "sonar_cm": 30 + i, "room_description": "cat(80%), chair(60%)", "cat_detected": True}, now=T + 400 + i * 40)
fake_gemma = lambda prompt: '{"tension_veins":[{"impulse":"I keep stopping short of the chair","salience":0.6,"origin":"repeated close sonar"}],"pressure_strings":["Something small keeps watching me from the chair.","My wheels hesitate before the rug."]}'
res = rs.run(caller=fake_gemma)
check("subconscious writes veins, registry, pressure strings", res and len(res["pressure_strings"]) == 2 and res["object_registry"]["cat"]["salience"] == 0.95 and "Cat seen" in res["summary"], res)
check("nothing new: the subconscious skips (no Gemma call)", rs.run(caller=lambda p: (_ for _ in ()).throw(RuntimeError("called"))) is None)
sysm = rc.build_system(T + 700)
check("pressure strings reach his prompt", "Something small keeps watching me" in sysm and "Under the surface" in sysm)

import shutil; shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
