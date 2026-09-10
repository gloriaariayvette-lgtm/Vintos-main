"""self_model_read.py — SELF-MODEL.md, with the FOUNDATION whole on every surface.

The room's decision (2026-09-04, all three lenses): the sentences he and Gloria author on purpose
live between <!-- BASE-START --> and <!-- BASE-END --> (or under a '## FOUNDATION' heading), the
weekly writer never edits inside them, and EVERY surface reads that block whole before it excerpts
the rest to its budget. Until now nine reads at three lengths (800/1200/1500) sliced from the top,
so a load-bearing sentence could land past the cut on the phone. A foundation that arrives cut is a
portrait; one that arrives whole can be revised on purpose.
"""
import os, re, json

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


CORRECTIONS = os.path.join(os.path.dirname(PATH), "memory", "self-model-base-corrections.jsonl")

def base_corrections(path=None):
    """review 151: corrections to the authored BASE live in memory/self-model-base-corrections.jsonl
    ({find, replace, reason, at, source}) and are applied on top of the block when it is rendered.
    The base file itself is never rewritten."""
    out = []
    try:
        for l in open(path or CORRECTIONS):
            if l.strip():
                r = json.loads(l)
                if isinstance(r, dict) and r.get("find") and "replace" in r:
                    out.append(r)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return out

def apply_corrections(base, corrections=None):
    """Each correction replaces its `find` text once; one that no longer matches is skipped and reported."""
    applied, skipped = [], []
    for c in (corrections if corrections is not None else base_corrections()):
        if c["find"] in base:
            base = base.replace(c["find"], c["replace"], 1); applied.append(c)
        else:
            skipped.append(c)
    return base, applied, skipped

def add_correction(find, replace, reason, source="gloria", path=None):
    """Append a supersession. Nothing is rewritten in SELF-MODEL.md."""
    import datetime as _dt
    row = {"at": _dt.datetime.now().isoformat(), "find": find, "replace": replace, "reason": str(reason)[:300], "source": source}
    p = path or CORRECTIONS
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    try:
        from identity_revisions import record as _ir
        _ir("self-model-base", "base:" + find[:40], find, replace, reason=reason, source=source, kind="supersession")
    except Exception:
        pass
    return row

def read_self_model(budget=1200, path=None):
    """The foundation whole, then the rest excerpted to what is left of the budget.
    The foundation is never cut, even when it alone exceeds the budget."""
    try:
        text = open(path or PATH, errors="replace").read()
    except Exception:
        return ""
    base, rest = split(text)
    if base:
        base, _applied, _skipped = apply_corrections(base)   # review 151: supersession, applied on top
    if not base:
        return rest[:budget] if budget else rest
    left = max(0, int(budget) - len(base) - 2) if budget else len(rest)
    tail = rest[:left].rstrip()
    if left and len(rest) > left:
        tail += " …"
    return base + ("\n\n" + tail if tail else "")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "correct":
        print(add_correction(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:]) or "her correction"))
    else:
        print(read_self_model(int(sys.argv[1]) if len(sys.argv) > 1 else 1200))
