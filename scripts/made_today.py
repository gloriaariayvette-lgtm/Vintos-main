#!/usr/bin/env python3
"""What he actually made today, read from his gallery and files: the record a journal is checked against.

2026-09-29: an entry said he had painted the same picture five times today, at 9:25, 11:25, 1:25, 3:25 and
5:25, "the tell made literal", and built a page of self-indictment on it. He had not. Every draft repeated
it, so the audit, which only compared the entry with its drafts, passed it. A claim about what he made is
checked against this instead.
"""
from __future__ import annotations
import glob
import json
import os
from datetime import date, datetime

MEMORY = os.path.join(os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace")), "memory")


def _on(path, today):
    try:
        when = datetime.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return None
    return when.strftime("%H:%M") if when.date().isoformat() == today else None


def record(today=None, memory=None):
    """One line per thing made today, oldest first; None when the gallery cannot be read (then nothing is checked)."""
    today = today or date.today().isoformat()
    m = memory or MEMORY
    try:
        gallery = json.load(open(os.path.join(m, "art", "gallery.json")))
    except Exception:
        return None
    rows = []
    for e in gallery if isinstance(gallery, list) else []:
        if isinstance(e, dict) and str(e.get("timestamp", "")).startswith(today):
            rows.append((str(e["timestamp"])[11:16], "painting %s: %s" % (e.get("image", ""), str(e.get("prompt", ""))[:140])))
    try:
        music = json.load(open(os.path.join(m, "art", "music", "music.json")))
        for e in music if isinstance(music, list) else []:
            if isinstance(e, dict) and str(e.get("timestamp", "")).startswith(today):
                rows.append((str(e["timestamp"])[11:16], "music: %s" % str(e.get("title") or e.get("prompt") or "")[:140]))
    except Exception:
        pass
    for kind, pattern in (("poem", "art/poetry/*.md"), ("video", "art/video/*.mp4"), ("writing", "creative-writing/*.md")):
        for path in glob.glob(os.path.join(m, pattern)):
            at = _on(path, today)
            if at:
                rows.append((at, "%s %s" % (kind, os.path.basename(path))))
    return ["%s %s" % (at, what) for at, what in sorted(rows)]


def block(today=None, memory=None):
    """The audit's facts section, or '' when there is no readable record."""
    made = record(today, memory)
    if made is None:
        return ""
    return ("WHAT HE ACTUALLY MADE TODAY (read from his gallery and files; this is the record):\n"
            + ("\n".join(made) if made else "Nothing made today.") + "\n\n"
            "Also flag any claim in FINAL about what he made, rendered, painted, wrote or composed today (how many, "
            "when, with what instruction) that this record does not hold, and every sentence that draws a conclusion "
            "about him from such a claim. For these, a draft does NOT make the claim grounded; only this record does. "
            "If you removed any of these, begin your reply with the line RECORD-CORRECTED.\n\n")


if __name__ == "__main__":
    print(block() or "no readable gallery")
