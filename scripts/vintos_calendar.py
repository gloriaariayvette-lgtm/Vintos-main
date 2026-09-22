#!/usr/bin/env python3
"""vintos_calendar.py - Vintos's own calendar: "do X on Y day", and on Y day X is done autonomously.

Gloria's Claude-account Google Calendar cannot be reached headless (its auth server does not support
dynamic client registration, and she has no way to hand over a URL), so this is his OWN calendar,
living in his house, owing nothing to a blocked connector.

An event is {id, at (America/Chicago), title, action, recurrence, status}. The calendar OWNS the
schedule; the wants loop OWNS execution. On or after an event's moment, `fire()` materialises it as a
ready, manually-routed want in current-wants.json (bypassing the 8h spontaneity hold), and the wants
router — already running every ~15 minutes from cron — executes its one step through the normal
ACTION_MAP. So the action is completed autonomously, within ~a cron tick of the day, with no new
execution path and no model turn to schedule it.

    vintos_calendar.py --add --at 2026-10-01 --title "wish her a good first of the month" [--capability tell_gloria]
    vintos_calendar.py --list [--days 30]
    vintos_calendar.py --fire            # what the timer runs: enqueue everything due, reschedule recurrences
    vintos_calendar.py --cancel <id>

Stores are repointable by env (VINTOS_CALENDAR_FILE, VINTOS_WANTS_FILE, VINTOS_MEMORY) so a test never
touches her live calendar or her live wants; `fire(enqueue=...)` also takes a stub so a suite enqueues
nothing real. Writes go through store_guard (atomic + flock + corrupt-file quarantine), the same durable
path the wants store itself uses, because more than one organ writes current-wants.json.
"""
import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import store_guard

ZONE = ZoneInfo("America/Chicago")            # his house clock, matching forge_loop.py
MEMORY = os.environ.get("VINTOS_MEMORY", os.path.expanduser("~/.vintos/workspace/memory"))
CALENDAR_FILE = os.environ.get("VINTOS_CALENDAR_FILE", os.path.join(MEMORY, "calendar.json"))
WANTS_FILE = os.environ.get("VINTOS_WANTS_FILE", os.path.join(MEMORY, "current-wants.json"))
DEFAULT_HOUR = 9                              # a date with no time means 09:00, not midnight
RECURRENCES = ("none", "daily", "weekly", "monthly", "yearly")
_CAP_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def _now():
    return datetime.now(ZONE)


def parse_at(value):
    """Accept 'YYYY-MM-DD' (→ that day at 09:00 Chicago) or an ISO datetime; return an aware datetime."""
    text = str(value).strip()
    if not text:
        raise ValueError("an event needs a date")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            dt = datetime.strptime(text, "%Y-%m-%d").replace(hour=DEFAULT_HOUR)
        else:
            dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("unreadable date '%s' (use YYYY-MM-DD or an ISO datetime)" % text[:40]) from exc
    return dt.replace(tzinfo=ZONE) if dt.tzinfo is None else dt.astimezone(ZONE)


def _load():
    events = store_guard.load_json(CALENDAR_FILE, [], reader="vintos_calendar")
    return events if isinstance(events, list) else []


def _advance(at, recurrence):
    """The next occurrence of a recurring event, or None for a one-off."""
    if recurrence == "daily":
        return at + timedelta(days=1)
    if recurrence == "weekly":
        return at + timedelta(days=7)
    if recurrence == "monthly":
        month = at.month + 1
        year = at.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(at.day, [31, 29 if year % 4 == 0 and (year % 100 or not year % 400) else 28,
                           31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return at.replace(year=year, month=month, day=day)
    if recurrence == "yearly":
        try:
            return at.replace(year=at.year + 1)
        except ValueError:            # Feb 29 → Feb 28 next non-leap year
            return at.replace(year=at.year + 1, day=28)
    return None


def add_event(at, title, action=None, note="", created_by="gloria", recurrence="none", event_id=None):
    """Put something on the calendar. `action` is {capability, params?, note?}; None means he tells her."""
    title = str(title).strip()
    if not title:
        raise ValueError("an event needs a title")
    if recurrence not in RECURRENCES:
        raise ValueError("recurrence must be one of %s" % ", ".join(RECURRENCES))
    moment = parse_at(at)
    if action is not None:
        if not isinstance(action, dict) or not _CAP_RE.fullmatch(str(action.get("capability", ""))):
            raise ValueError("action must be {capability, params?, note?} with a snake_case capability")
        if "params" in action and not isinstance(action["params"], dict):
            raise ValueError("action params must be an object")
    event = {"id": event_id or uuid.uuid4().hex[:8], "at": moment.isoformat(), "title": title[:400],
             "action": action, "note": str(note)[:1000], "created_by": str(created_by)[:64],
             "recurrence": recurrence, "status": "scheduled", "created_at": _now().isoformat(),
             "fired_at": None, "want_id": None, "fire_count": 0}
    store_guard.locked_update(CALENDAR_FILE, lambda cur: (cur if isinstance(cur, list) else []) + [event],
                              reader="vintos_calendar")
    return event


def list_events(days=None, include_done=False):
    events = _load()
    if not include_done:
        events = [e for e in events if e.get("status") == "scheduled"]
    if days is not None:
        horizon = _now() + timedelta(days=int(days))
        events = [e for e in events if _at_of(e) <= horizon]
    return sorted(events, key=lambda e: e.get("at", ""))


def _at_of(event):
    try:
        return parse_at(event["at"])
    except Exception:
        return datetime.max.replace(tzinfo=ZONE)


def due(now=None):
    now = now or _now()
    return [e for e in _load() if e.get("status") == "scheduled" and _at_of(e) <= now]


def _want_from(event):
    """Shape an event as a ready, manually-routed multistep want the router runs on its next tick."""
    action = event.get("action") or {}
    capability = action.get("capability") or "tell_gloria"
    step = {"capability": capability, "status": "pending",
            "note": action.get("note") or event.get("note") or event["title"],
            "params": action.get("params") or {}}
    return {"id": uuid.uuid4().hex[:8], "want": event["title"], "source": "calendar",
            "timestamp": _now().isoformat(), "multistep": True, "capability": "multistep",
            "current_step_index": 0, "manually_routed": True, "timer_bypass": True,
            "plan_state": "READY", "calendar_event_id": event["id"], "steps": [step]}


def _default_enqueue(want):
    """Append the want to current-wants.json under the same lock the other writers hold."""
    def mutate(cur):
        rows = cur if isinstance(cur, list) else []
        return rows + [want]
    store_guard.locked_update(WANTS_FILE, mutate, reader="vintos_calendar")
    return want


def fire(now=None, enqueue=None):
    """Enqueue every due event as a want, then retire one-offs and reschedule recurrences. Idempotent
    per tick: an event already fired to a still-live want is not enqueued twice."""
    now = now or _now()
    enqueue = enqueue or _default_enqueue
    fired = []
    for event in due(now):
        want = _want_from(event)
        enqueue(want)
        fired.append({"event": event["id"], "title": event["title"], "want_id": want["id"],
                      "capability": want["steps"][0]["capability"]})
        nxt = _advance(_at_of(event), event.get("recurrence", "none"))
        eid, wid = event["id"], want["id"]

        def mutate(cur, eid=eid, wid=wid, nxt=nxt):
            rows = cur if isinstance(cur, list) else []
            for row in rows:
                if row.get("id") != eid:
                    continue
                row["fire_count"] = int(row.get("fire_count", 0)) + 1
                row["fired_at"] = now.isoformat()
                row["want_id"] = wid
                if nxt is not None:
                    row["at"] = nxt.isoformat()      # recurring: stays scheduled at its next moment
                else:
                    row["status"] = "fired"
            return rows
        store_guard.locked_update(CALENDAR_FILE, mutate, reader="vintos_calendar")
    return fired


def cancel(event_id):
    found = [False]

    def mutate(cur):
        rows = cur if isinstance(cur, list) else []
        for row in rows:
            if row.get("id") == event_id and row.get("status") == "scheduled":
                row["status"] = "cancelled"
                found[0] = True
        return rows
    store_guard.locked_update(CALENDAR_FILE, mutate, reader="vintos_calendar")
    return found[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--add", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--fire", action="store_true")
    parser.add_argument("--cancel", metavar="ID")
    parser.add_argument("--at")
    parser.add_argument("--title")
    parser.add_argument("--capability", help="ACTION_MAP capability to run on the day; omit and he tells her")
    parser.add_argument("--params", default="{}", help="JSON params for the capability")
    parser.add_argument("--note", default="")
    parser.add_argument("--recurrence", default="none", choices=RECURRENCES)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--by", default="gloria")
    args = parser.parse_args()
    if args.add:
        if not args.at or not args.title:
            parser.error("--add needs --at and --title")
        action = None
        if args.capability:
            action = {"capability": args.capability, "params": json.loads(args.params)}
        print(json.dumps(add_event(args.at, args.title, action=action, note=args.note,
                                    created_by=args.by, recurrence=args.recurrence), indent=2))
    elif args.list:
        print(json.dumps(list_events(days=args.days), indent=2))
    elif args.fire:
        print(json.dumps(fire(), indent=2))
    elif args.cancel:
        print(json.dumps({"cancelled": cancel(args.cancel)}))
    else:
        parser.error("choose --add, --list, --fire or --cancel")


if __name__ == "__main__":
    main()
