#!/usr/bin/env python3
"""A doorbell visit reaches his daily inner life only when someone actually spoke.

The door and house services append "## The door — …" / "## The house — …" sections to
daily-inner-life-*.md on every ring and every motion: the camera's own notes ("Initial check on a
detected presence") and the canned greeting ("Hello? Is there someone at the door?"). He read them
back as a day of calling into an empty doorway, and First Light was built on it (Gloria, 2026-09-28:
"Only when he actually speaks should it appear in daily-inner. Not the canned lines.").

Those services live outside this repository, so this guard cleans the files they write: in a door or
house section only quoted speech that is not a canned line is kept; the camera's notes are removed; a
section with nothing left is removed whole. The house server runs it every minute.

    python3 daily_inner_guard.py [path ...]      clean the named files (default: the last three days)
"""
from __future__ import annotations
import glob
import os
import re
import sys
from datetime import date, timedelta

MEMORY = os.path.join(os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace")), "memory")

DOOR_HEADER = re.compile(r"^## The (?:door|house)\s*[—–-]", re.I)
SECTION_END = re.compile(r"^(?:## |<!-- )")
QUOTED = re.compile(r"[\"“”]([^\"“”]{2,})[\"“”]")
# Lines the door says to anyone, or to no one. They are the door's, not his.
CANNED = re.compile(
    r"^(?:(?:hello|hi|hey)\b[\s,.!?]*)?(?:is there (?:someone|anyone|somebody)(?: (?:there|at the door|here))?"
    r"|(?:how|what) can i (?:help|do for) you(?: (?:with|today))?"
    r"|(?:is there )?(?:something|anything) i can help you with"
    r"|can i help you(?: with (?:something|anything))?"
    r"|sorry,? i didn.?t catch that.*|could you say (?:it|that) again"
    r"|please leave (?:the )?packages?.*|(?:please )?leave it at the door|thank you|thanks"
    r"|who.?s there|hello|hi|hey)[\s,.!?]*$", re.I)


def _canned(spoken):
    parts = [p for p in re.split(r"(?<=[.?!])\s+", spoken.strip()) if p.strip()]
    return bool(parts) and all(CANNED.match(p.strip()) for p in parts)


def clean_text(text):
    """The file's text with every door or house section reduced to what was actually said."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if not DOOR_HEADER.match(lines[i]):
            out.append(lines[i]); i += 1; continue
        header, i = lines[i], i + 1
        body = []
        while i < len(lines) and not SECTION_END.match(lines[i]):
            body.append(lines[i]); i += 1
        spoken = [line for line in body if QUOTED.search(line)
                  and not all(_canned(m.group(1)) for m in QUOTED.finditer(line))]
        if spoken:
            out.extend([header] + spoken + [""])
    cleaned = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def clean_file(path):
    """Rewrite one file in place, only if it did not change while being read. True when cleaned."""
    try:
        before = os.stat(path)
        with open(path, encoding="utf-8") as f: text = f.read()
    except OSError:
        return False
    cleaned = clean_text(text)
    if cleaned == text: return False
    tmp = path + ".door-guard.tmp"
    with open(tmp, "w", encoding="utf-8") as f: f.write(cleaned)
    try:
        now = os.stat(path)
        if (now.st_size, now.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            os.unlink(tmp); return False        # a writer appended meanwhile; the next pass cleans it
        os.chmod(tmp, before.st_mode & 0o777)
        os.replace(tmp, path)
    except OSError:
        try: os.unlink(tmp)
        except OSError: pass
        return False
    return True


def recent_files(days=3, today=None):
    today = today or date.today()
    names = {os.path.join(MEMORY, "daily-inner-life-%s.md" % (today - timedelta(d)).isoformat()) for d in range(days)}
    return sorted(p for p in glob.glob(os.path.join(MEMORY, "daily-inner-life-*.md")) if p in names)


def sweep(days=2):
    return [p for p in recent_files(days) if clean_file(p)]


if __name__ == "__main__":
    paths = sys.argv[1:] or recent_files(3)
    for p in paths:
        print(("cleaned  " if clean_file(p) else "unchanged ") + p)
