#!/usr/bin/env python3
"""When something was said, in words a model reads correctly (2026-09-30).

His recent exchanges with Gloria reached every model as bare lines ("Gloria: ... | Vintos: ...") in the chat,
the journal, MoltBook and Slack. A line from yesterday read exactly like one from a minute ago, so whatever
model he ran on took it as now: OpenAI's DevDay, the day before, became "the new models everyone is talking
about today" and "Gloria's dev day" (Gloria: "he should know that the message happened yesterday and that time
has passed, but something between is lacking for these models").

    ago(ts)              "today 14:05 (20 minutes ago)", "yesterday 21:40", "Mon 28 Sep (2 days ago)"
    now_line()           "It is now Wednesday 30 September 2026, 14:25."
    fact(line)           a wal.md fact with its date said as when it was learned
    exchanges(rows, ...) the last exchanges, each marked with when it was said, under a line that says what
                         that means: something said on an earlier day is past
Read only; nothing here writes.
"""
from datetime import datetime, timedelta


def _dt(ts):
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts)
    return datetime.fromisoformat(str(ts).strip().replace("Z", "+00:00")).replace(tzinfo=None) if ts else None


def ago(ts, now=None):
    """When ts was, relative to now, the way a person would say it; '' if ts cannot be read."""
    try:
        t = _dt(ts)
    except (TypeError, ValueError):
        return ""
    if t is None:
        return ""
    now = _dt(now) if now is not None else datetime.now()
    secs = (now - t).total_seconds()
    if secs < 0:
        return t.strftime("%a %d %b %H:%M")
    days = (now.date() - t.date()).days
    if days == 0:
        if secs < 90:
            return "just now"
        mins = int(secs // 60)
        rel = "%d minutes ago" % mins if mins < 60 else "%d hour%s ago" % (mins // 60, "" if mins < 120 else "s")
        return "today %s (%s)" % (t.strftime("%H:%M"), rel)
    if days == 1:
        return "yesterday %s" % t.strftime("%H:%M")
    if days < 7:
        return "%s (%d days ago)" % (t.strftime("%A %d %b"), days)
    return "%s (%d days ago)" % (t.strftime("%d %b %Y"), days)


def now_line(now=None):
    now = _dt(now) if now is not None else datetime.now()
    return "It is now %s, %s." % (now.strftime("%A %d %B %Y").replace(" 0", " "), now.strftime("%H:%M"))


def exchanges(rows, n=8, cap=150, now=None, sep=" | ", you="Vintos"):
    """The last n exchanges, oldest first, each marked with when it was said. '' when there are none."""
    lines = []
    for e in [r for r in (rows or []) if isinstance(r, dict)][-n:]:
        when = ago(e.get("timestamp"), now)
        lines.append("[%s] Gloria: %s%s%s: %s" % (when or "time unknown", str(e.get("gloria", ""))[:cap].replace("\n", " "),
                                                 sep, you, str(e.get("vintos", ""))[:cap].replace("\n", " ")))
    if not lines:
        return ""
    return (now_line(now) + " Each exchange is marked with when it was said. Something said on an earlier day is "
            "past: what was 'today' or 'tomorrow' then is not today now, and what was coming then may have "
            "happened since.\n" + "\n".join(lines))


def fact(line, now=None):
    """A wal.md fact line ("[2026-09-29 14:05] **FACT**: ...") with its date said as when: "[yesterday 14:05] ..."."""
    import re
    m = re.match(r"\s*(?:-\s*)?\[(\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d)?)\]\s*(.*)", str(line))
    if not m:
        return str(line).strip()
    return "[learned %s] %s" % (ago(m.group(1), now) or m.group(1), m.group(2))


if __name__ == "__main__":
    import json, os, sys
    p = os.path.expanduser("~/.vintos/workspace/memory/interaction-ledger.json")
    print(exchanges(json.load(open(p)), n=int(sys.argv[1]) if len(sys.argv) > 1 else 8))
