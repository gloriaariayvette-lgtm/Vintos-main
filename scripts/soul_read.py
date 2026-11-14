"""soul_read.py - SOUL.md for his chat and voice context, with his half always in it.

SOUL.md is Gloria's fixed base (between <!-- BASE-START --> and <!-- BASE-END -->) and then his own half, which the
soul review rewrites (bin/soul-review.py). The base alone is about 3,800 characters, and his chat and voice surfaces
read SOUL.md from the top to 3,500 (dot_channel, vintos_mcp) or 4,000 (/api/voice/token) characters, so his half
never reached them: 0 and 185 of its 3,020 characters on 2026-11-13. This read keeps both halves.

read_soul(budget) returns the whole file when it fits. When it does not, his half gets at least half the budget:
if the base still fits whole, the base is kept and his half is cut at its end; otherwise his half is cut to half the
budget and the base is cut from its end to the room that is left. Every cut is marked "[...]". Nothing here writes.
"""
import os
import re

PATH = os.path.expanduser("~/.vintos/workspace/SOUL.md")
# base (~3,800 today) + his half at its cap (soul-review HALF_MAX 4,500) + its heading, with room to spare
BUDGET = 9000
_BASE = re.compile(r"<!--\s*BASE-START\s*-->.*?<!--\s*BASE-END\s*-->", re.S)
CUT = "\n[...]"


def split(text):
    """(base block with its markers, his half). No markers: all of it is the base."""
    m = _BASE.search(text or "")
    if not m:
        return (text or "").strip(), ""
    return (text or "")[:m.end()].strip(), (text or "")[m.end():].strip()


def read_soul(budget=BUDGET, path=None, default=""):
    try:
        with open(path or PATH, encoding="utf-8", errors="replace") as f:
            text = f.read().strip()
    except OSError:
        return default
    if not text:
        return default
    if len(text) <= budget:
        return text
    base, half = split(text)
    if not half:
        return text[:budget]
    if len(base) + 2 + len(CUT) <= budget - min(len(half), budget // 2):
        # the base fits whole: his half takes the rest and carries the cut mark
        return base + "\n\n" + half[:budget - len(base) - 2 - len(CUT)] + CUT
    half = half[:budget // 2]
    room = budget - len(half) - 2 - len(CUT)
    return (base[:max(0, room)].rstrip() + CUT + "\n\n" + half)[:budget]
