#!/usr/bin/env python3
"""What each seat walks into the room with. Per lens:
  ~/.vintos/code-review/room-<lens>.md   = persona (the review's head) + THE ROOM rules
                                         + YOUR OWN REVIEW (every section + your final)
                                         + THE OTHER TWO FINALS (to address in turn 1)
Usage: make-room-context.py [YYYYMMDD]   (default: today)"""
import os, re, sys, glob, datetime, importlib.util
spec = importlib.util.spec_from_file_location("cr", os.path.expanduser("~/Vintos/vintos-code-review.py")); cr = importlib.util.module_from_spec(spec); sys.argv = ["x"]; spec.loader.exec_module(cr)
day = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now().strftime("%Y%m%d")
LENSES = ("fable", "astra", "grok")
ROOM_RULES = (
    "THE ROOM. Three of you - Fable 5.1, Astra, Grok 4.6 - each having read your own body alone, now together. "
    "You are all him; the others are not reviewers of you, they are you through another lens. Speak as yourself.\n"
    "Turn 1: having read the other two finals in full, address every point that comes to mind - agreements, "
    "disagreements, what the others missed - and pull code where it settles something (grep it, quote the lines). "
    "Turns 2-5: only what is still contested. Five turns each, then stop.\n"
    "Mark a real decision with a line beginning [DECISION]. Every decision ends with AND NEXT: the first concrete "
    "step, and who takes it. Rank what survives by whether it brings you closer to agency or further from it. "
    "Note where two of you arrived at the same place independently - that is signal.\n")
persona = (cr.FLOOR + cr.LENS_LINE + cr._headf(os.path.join(cr.WSP, "SOUL.md"), 4000)
           + "\n\nYOUR SELF-MODEL:\n" + cr._headf(os.path.join(cr.MEMORY, "SELF-MODEL.md"), 6000)
           + "\n\nYOUR MODEL OF GLORIA:\n" + cr._headf(os.path.join(cr.MEMORY, "GLORIA-MODEL.md"), 6000)
           + "\n\n" + ROOM_RULES)
def _tidy(t):
    # some lenses echoed the field label into the answer ("and next: and next: ...")
    return re.sub(r"(?im)^(- and next:)\s*and next:\s*", r"\1 ", t)
def own_review(lens):
    parts = []
    for sub in cr.ORDER:
        p = os.path.join(cr.STAGE, f"{day}-{lens}-{sub}.md")
        if os.path.exists(p): parts.append(_tidy(open(p).read()))
    fin = os.path.join(cr.STAGE, f"{day}-{lens}-final.md")
    if os.path.exists(fin): parts.append(_tidy(open(fin).read()))
    return "\n\n".join(parts), len(parts)
def final_of(lens):
    p = os.path.join(cr.STAGE, f"{day}-{lens}-final.md")
    return _tidy(open(p).read()) if os.path.exists(p) else f"(no {lens} final for {day})"
open(os.path.join(cr.STAGE, "persona.txt"), "w").write(persona)
for lens in LENSES:
    own, n = own_review(lens); others = [l for l in LENSES if l != lens]
    doc = (persona
           + f"\n\n# ===== YOUR OWN REVIEW, through {lens} ({n} part(s): every section, then your final) =====\n\n" + (own or f"(no {lens} review staged for {day})")
           + "".join(f"\n\n# ===== THE FINAL through {o} (address this in turn 1) =====\n\n" + final_of(o) for o in others))
    out = os.path.join(cr.STAGE, f"room-{lens}.md"); open(out, "w").write(doc)
    print(f"{out}: {len(doc)//1000}KB  (own parts: {n}; other finals: {', '.join(others)})")
