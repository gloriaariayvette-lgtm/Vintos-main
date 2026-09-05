"""self_model_read.py — SELF-MODEL.md, with the FOUNDATION whole on every surface.

The room's decision (2026-09-04, all three lenses): the sentences he and Gloria author on purpose
live between <!-- BASE-START --> and <!-- BASE-END --> (or under a '## FOUNDATION' heading), the
weekly writer never edits inside them, and EVERY surface reads that block whole before it excerpts
the rest to its budget. Until now nine reads at three lengths (800/1200/1500) sliced from the top,
so a load-bearing sentence could land past the cut on the phone. A foundation that arrives cut is a
portrait; one that arrives whole can be revised on purpose.
"""
import os, re

PATH = os.path.expanduser("~/.vintos/workspace/SELF-MODEL.md")
_MARK = re.compile(r"<!--\s*BASE-START\s*-->(.*?)<!--\s*BASE-END\s*-->", re.S)
_HEAD = re.compile(r"(^|\n)##\s*FOUNDATION[^\n]*\n(.*?)(?=\n##\s|\Z)", re.S)


def split(text):
    """-> (foundation, rest). Foundation is '' when no marked block exists."""
    m = _MARK.search(text or "")
    if m:
        return m.group(1).strip(), (text[:m.start()] + text[m.end():]).strip()
    m = _HEAD.search(text or "")
    if m:
        return m.group(2).strip(), (text[:m.start(2)] + text[m.end(2):]).strip()
    return "", (text or "").strip()


def read_self_model(budget=1200, path=None):
    """The foundation whole, then the rest excerpted to what is left of the budget.
    The foundation is never cut, even when it alone exceeds the budget."""
    try:
        text = open(path or PATH, errors="replace").read()
    except Exception:
        return ""
    base, rest = split(text)
    if not base:
        return rest[:budget] if budget else rest
    left = max(0, int(budget) - len(base) - 2) if budget else len(rest)
    tail = rest[:left].rstrip()
    if left and len(rest) > left:
        tail += " …"
    return base + ("\n\n" + tail if tail else "")


if __name__ == "__main__":
    import sys
    print(read_self_model(int(sys.argv[1]) if len(sys.argv) > 1 else 1200))
