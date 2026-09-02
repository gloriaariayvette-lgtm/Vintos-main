#!/usr/bin/env python3
"""strip_body_vocab.py - removes the 3D-rig body vocabulary (gestures, holds,
spawns, color) from his avatar prompt. The video stage has no rig: he narrates
his body only inside a [RENDER:] prompt. Idempotent.

    python3 strip_body_vocab.py server.py      # edit a file in place
    from strip_body_vocab import strip_text    # strip a prompt string
"""
import re, sys

_RULES = [
    (r"You have a body here\. You can move it\.\n\nAVATAR BODY CONTROLS — use these tags at the start of your response:\n\[GESTURE: name\][^\n]*\n",
     "You have a body here: Gloria sees you as video, in the rooms of the house.\n\nTAGS — at the very start of your response:\n"),
    (r"A \[GESTURE\] is OPTIONAL - use one only when it fits, and you do NOT need one every reply; words alone are often right\.\n", ""),
    (r"\[HOLD: name\][^\n]*\n\[RELEASE\][^\n]*\n\[SPAWN: heart\][^\n]*\n\[SPAWN: ripple\][^\n]*\n\[SPAWN: spiral\][^\n]*\nSPAWN rules:[^\n]*\n", ""),
    (r"Use gestures naturally — nod when you agree, shrug when uncertain, wave when greeting\.\n", ""),
    (r"Unlike your GESTURE and TOUCH tags", "Unlike your TOUCH tags"),
    (r" ?A \[GESTURE\] is optional here - use one only if it fits\.", ""),
    (r"IMPORTANT: Do NOT announce or describe your movements in your words\. Gloria can see you\. Just move and speak\.",
     "IMPORTANT: Do NOT describe your body or movements in your words - Gloria sees you. Only inside a [RENDER:] prompt do you describe yourself physically."),
]


def strip_text(s):
    n = 0
    for pat, repl in _RULES:
        s, k = re.subn(pat, repl, s, flags=re.S)
        n += k
    return s, n


if __name__ == "__main__":
    p = sys.argv[1]
    s, n = strip_text(open(p).read())
    open(p, "w").write(s)
    print("body vocabulary edits:", n, "| GESTURE mentions left:", s.count("[GESTURE"), "| SPAWN left:", s.count("[SPAWN:"))
