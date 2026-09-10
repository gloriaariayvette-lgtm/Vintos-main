#!/usr/bin/env python3
"""Static ownership contract: ReelRoom conversations use the avatar turn
engine and defer only the interaction ledger to one session-end commit."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SERVER = open(os.path.join(ROOT, "bin", "server.py"), errors="replace").read()
RR = open(os.path.join(ROOT, "scripts", "reelroom.py"), errors="replace").read()
TC = open(os.path.join(ROOT, "scripts", "turn_coordinator.py"), errors="replace").read()
R = []

def check(name, ok):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name)

check("ReelRoom is an honestly named coordinated surface", '"reelroom"' in TC.split("SURFACES =", 1)[1].split("\n", 1)[0])
check("ReelRoom speak enters the avatar turn engine", "_out = await avatar_chat(_internal, request)" in SERVER)
check("the real counterpart text is separated from room events",
      "_counterpart_text =" in SERVER and 'input_kind="text" if _actual is not None else "reelroom_event"' in SERVER)
# A line he chose to say mid-film no longer enters the avatar turn engine at all: it is his
# room voice on Sonnet, so there is no turn there to resolve a prior intent with. Only a turn
# that carries her actual words does, and it says so (Gloria, 2026-09-10: cost).
check("only her actual words may resolve a prior intent",
      "resolve_previous_intent=bool(_actual)" in SERVER and SERVER.count("await avatar_chat(_internal, request)") == 1)
check("an autonomous line is his room voice, not the avatar engine",
      "rr.chat(" in SERVER and '"unprompted": True' in SERVER)
check("the full avatar pre-turn stack still selects an intent", "_apply_intent_lead(system_prompt, msg.message" in SERVER)
check("only the per-turn interaction ledger is deferred",
      '("nudge_gloria", "imprint", "voice_coherence", "ledger") if _defer_session_ledger' in SERVER)
check("session end owns one idempotent transcript plus narrative commit",
      "def append_session_ledger" in RR and '"reelroom_file"' in RR and '"transcript"' in RR and '"narrative"' in RR)
check("the living-room spatial map is explicit", 'house_map.room_context("living_room")' in RR and "house_map.sketch_block()" in RR)
check("ring is read at prompt assembly", "def _ring_context" in RR and "heart_rate.context_line()" in RR)
check("ReelRoom owns the theatre screen instead of avatar-scene generation",
      'if _surface != "reelroom":' in SERVER and "_avst_g.scene_gate" in SERVER
      and 'Never emit [SCENE:] or [RENDER:]' in SERVER
      and 'reply = _tagre.sub(r"\\s*\\[(?:SCENE|RENDER)' in SERVER
      and 'if _surface != "reelroom":\n            try:\n                import avatar_stage as _avst_k' in SERVER)
check("ReelRoom speaking follows the shared selectable voice while Gemma retains look and decide",
      '"grok", "sol", "sonnet", "fable"' in SERVER
      and 'mode == "look"' in SERVER and 'mode == "decide"' in SERVER
      and 'await avatar_chat(_internal, request)' in SERVER)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
