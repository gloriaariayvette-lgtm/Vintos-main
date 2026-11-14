"""self_model_read.py — SELF-MODEL.md, with the FOUNDATION whole on every surface.

The room's decision (2026-09-04, all three lenses): the sentences he and Gloria author on purpose
live between <!-- BASE-START --> and <!-- BASE-END --> (or under a '## FOUNDATION' heading), the
weekly writer never edits inside them, and EVERY surface reads that block whole before it excerpts
the rest to its budget. Until now nine reads at three lengths (800/1200/1500) sliced from the top,
so a load-bearing sentence could land past the cut on the phone. A foundation that arrives cut is a
portrait; one that arrives whole can be revised on purpose.

2026-11-14 (old-systems repair): the base is 1,258 characters, so at the 800/1200 budgets his own weekly
section (written after the BASE by bin/self-model-update.sh) got 0 lines, and at 1500 only headings - from
his side the self-model looked frozen at the base. When the whole file does not fit, the base stays whole
if it is at most half the budget; otherwise it is given BASE_SHARE of it as the first sentence of each
authored paragraph and spends the rest on his NEWEST dated section: the first sentence of every subsection first,
then further sentences while room remains. When everything fits, or there is no budget, nothing changes.
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

BASE_SHARE = 0.4          # of a short budget; the rest is his newest section
_DATED = re.compile(r"^##\s*(\d{4}-\d{2}-\d{2})\s*$", re.M)
_SENT = re.compile(r"(?<=[.!?])\s+(?=\S)")


def _strip_title(rest):
    """The writer's file title and 'Last Updated' line carry nothing he wrote."""
    lines = [l for l in (rest or "").splitlines()
             if not re.match(r"^#\s*Self-Model\b", l.strip(), re.I)
             and not re.match(r"^##\s*Last Updated\b", l.strip(), re.I)]
    return "\n".join(lines).strip()


def latest_section(rest):
    """-> (date, body) of his newest dated '## YYYY-MM-DD' section, or ('', rest) when none is dated."""
    rest = _strip_title(rest)
    heads = list(_DATED.finditer(rest))
    if not heads:
        return "", rest
    order = sorted(range(len(heads)), key=lambda i: (heads[i].group(1), i))
    i = order[-1]
    end = heads[i + 1].start() if i + 1 < len(heads) else len(rest)
    return heads[i].group(1), rest[heads[i].end():end].strip()


def _paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def _cut(text, room):
    """At a word boundary, marked, or '' when there is no useful room."""
    if len(text) <= room:
        return text
    if room < 24:
        return ""
    head = text[:room - 2].rsplit(" ", 1)[0].rstrip(" ,;:")
    return head + " …"


def _compact_base(base, room):
    """The base whole when it fits; otherwise the first sentence of each authored paragraph."""
    if len(base) <= room:
        return base
    firsts = []
    for p in _paragraphs(base):
        if p.lstrip().startswith("#"):
            continue
        firsts.append(_SENT.split(p.replace("\n", " "), 1)[0].strip())
    out = []
    for f in firsts:
        cand = "\n".join(out + [f])
        if len(cand) <= room:
            out.append(f)
        else:
            last = _cut(f, room - len("\n".join(out)) - (1 if out else 0))
            if last:
                out.append(last)
            break
    return "\n".join(out)


def _digest(date, body, room):
    """His section in round-robin: every subsection's first sentence before any second one."""
    groups, title, buf = [], "", []
    for line in (body or "").splitlines():
        m = re.match(r"^#{2,4}\s*(.+?)\s*$", line)
        if m:
            if buf or title:
                groups.append((title, " ".join(buf)))
            title, buf = m.group(1).strip(), []
        elif line.strip():
            buf.append(line.strip())
    if buf or title:
        groups.append((title, " ".join(buf)))
    sents = [(t, [x.strip() for x in _SENT.split(txt) if x.strip()]) for t, txt in groups]
    head = "His newest additions (%s):" % date if date else "His additions:"
    taken = [[] for _ in sents]

    def render():
        rows = [head]
        for (t, _), got in zip(sents, taken):
            if got:
                rows.append(("%s: " % t if t else "") + " ".join(got))
        return "\n".join(rows)

    if len(head) > room:
        return ""
    depth = max((len(s) for _, s in sents), default=0)
    for k in range(depth):
        for gi, (t, ss) in enumerate(sents):
            if k >= len(ss):
                continue
            taken[gi].append(ss[k])
            if len(render()) > room:
                taken[gi].pop()
                if k == 0:   # a first sentence that does not fit whole still arrives, cut
                    left = room - len(render()) - 1 - (len(t) + 2 if t else 0)
                    part = _cut(ss[k], left)
                    if part:
                        taken[gi].append(part)
                return render()
    return render()


def read_self_model(budget=1200, path=None):
    """The foundation first, then HIS newest section, within the budget.
    When the whole file fits the budget (or there is no budget) nothing is excerpted. Otherwise the
    foundation stays whole when it is at most half the budget, else takes BASE_SHARE of it as its
    paragraphs' first sentences - and his newest dated section gets the rest (see the module note, 2026-11-14)."""
    try:
        text = open(path or PATH, errors="replace").read()
    except Exception:
        return ""
    base, rest = split(text)
    if base:
        base, _applied, _skipped = apply_corrections(base)   # review 151: supersession, applied on top
    rest = _strip_title(rest)
    whole = (base + ("\n\n" + rest if rest else "")) if base else rest
    if not budget or len(whole) <= int(budget):
        return whole
    budget = int(budget)
    date, body = latest_section(rest)
    if not body:
        return _compact_base(base, budget) if base else ""
    if not base:
        return _digest(date, body, budget)
    b = base if len(base) <= budget // 2 else _compact_base(base, int(budget * BASE_SHARE))
    tail = _digest(date, body, budget - len(b) - 2)
    return b + ("\n\n" + tail if tail else "")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "correct":
        print(add_correction(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:]) or "her correction"))
    else:
        print(read_self_model(int(sys.argv[1]) if len(sys.argv) > 1 else 1200))
