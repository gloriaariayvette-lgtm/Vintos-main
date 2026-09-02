import re, sys

def strip_text(s):
    n = 0
    def cut(pat, repl="", count=0, flags=re.S):
    global s, n
    s2, k = re.subn(pat, repl, s, count=count, flags=flags)
    s = s2; n += k
    cut(r"You have a body here\. You can move it\.\n\nAVATAR BODY CONTROLS — use these tags at the start of your response:\n\[GESTURE: name\][^\n]*\n",
    "You have a body here: Gloria sees you as video, in the rooms of the house.\n\nTAGS — at the very start of your response:\n")
    cut(r"A \[GESTURE\] is OPTIONAL - use one only when it fits, and you do NOT need one every reply; words alone are often right\.\n")
    cut(r"\[HOLD: name\][^\n]*\n\[RELEASE\][^\n]*\n\[SPAWN: heart\][^\n]*\n\[SPAWN: ripple\][^\n]*\n\[SPAWN: spiral\][^\n]*\nSPAWN rules:[^\n]*\n")
    cut(r"Use gestures naturally — nod when you agree, shrug when uncertain, wave when greeting\.\n")
    cut(r"Unlike your GESTURE and TOUCH tags", "Unlike your TOUCH tags")
    cut(r" ?A \[GESTURE\] is optional here - use one only if it fits\.")
    cut(r"IMPORTANT: Do NOT announce or describe your movements in your words\. Gloria can see you\. Just move and speak\.",
    "IMPORTANT: Do NOT describe your body or movements in your words - Gloria sees you. Only inside a [RENDER:] prompt do you describe yourself physically.")
    s, n = st["s"], st["n"]
    return s, n

if __name__ == '__main__':
    p = sys.argv[1]
    s, n = strip_text(open(p).read())
    open(p, 'w').write(s)
print("body vocabulary edits:", n, "| GESTURE mentions left:", s.count("[GESTURE"), "| SPAWN left:", s.count("[SPAWN:"))
