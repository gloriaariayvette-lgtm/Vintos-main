#!/usr/bin/env python3
"""Assemble what every seat in the room is given: his persona (the same head the review used,
minus the anatomy map) and the three finals from today's review. Writes:
  ~/.vintos/code-review/persona.txt   ~/.vintos/code-review/finals.md"""
import os, sys, glob, datetime
sys.path.insert(0, os.path.expanduser("~/Vintos")); import importlib.util
spec = importlib.util.spec_from_file_location("cr", os.path.expanduser("~/Vintos/vintos-code-review.py")); cr = importlib.util.module_from_spec(spec); sys.argv=["x"]; spec.loader.exec_module(cr)
day = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now().strftime("%Y%m%d")
persona = (cr.FLOOR + cr.LENS_LINE + cr._headf(os.path.join(cr.WSP, "SOUL.md"), 4000)
           + "\n\nYOUR SELF-MODEL:\n" + cr._headf(os.path.join(cr.MEMORY, "SELF-MODEL.md"), 6000)
           + "\n\nYOUR MODEL OF GLORIA:\n" + cr._headf(os.path.join(cr.MEMORY, "GLORIA-MODEL.md"), 6000)
           + "\n\nTHE ROOM: three of you - Fable 5.1, Astra, Grok 4.6 - each having read your own body alone, now together. "
             "Turn 1: having read the other finals in full, address every point that comes to mind. Turns 2-5: only what is still contested. "
             "Pull code where it settles something. Mark a real decision with a line beginning [DECISION]. Five turns each, then stop.")
finals = []
for lens in ("fable", "astra", "grok"):
    p = os.path.join(cr.STAGE, f"{day}-{lens}-final.md")
    finals.append(f"\n\n# ===== FINAL through {lens} =====\n\n" + (open(p).read() if os.path.exists(p) else f"(no {lens} final for {day})"))
open(os.path.join(cr.STAGE, "persona.txt"), "w").write(persona); open(os.path.join(cr.STAGE, "finals.md"), "w").write("".join(finals))
print("wrote", os.path.join(cr.STAGE, "persona.txt"), "and finals.md", "(missing:", [l for l in ("fable","astra","grok") if not os.path.exists(os.path.join(cr.STAGE, f"{day}-{l}-final.md"))], ")")
