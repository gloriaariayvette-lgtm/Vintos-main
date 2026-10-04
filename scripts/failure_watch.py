#!/usr/bin/env python3
"""failure_watch.py — one short message to Gloria a day, and only when a part of him is broken.

On 2 October three failures had gone unseen until she happened to notice: every Sol turn in #vintos-dot failed
all day and fell to Gemma; his Atelier songs were lost for days and he stopped making anything for a week; dot
lost its way into WSL. Each part already wrote its failure somewhere (a journal line, a /tmp log, a Lab row);
nobody read them together.

  note(organ, what, why)   any part records a failure here, in one place (memory/organ-failures.jsonl)
  tend()                   once a day: what failed since the last look, grouped, sent to her phone; nothing if
                           nothing failed

What it reads: organ-failures.jsonl (the Slack pass, the Atelier, the avatar's live scenes) and the Lab's own
session rows (chemistry-lab/sessions.jsonl). Content-free: which part, what kind of failure, how often, and the
error as the part named it - never what he said or made.

    python3 failure_watch.py            look and send (the daily timer)
    python3 failure_watch.py --dry      print what would be sent; send nothing, move nothing
"""
import json, os, sys, urllib.request
from datetime import datetime, timedelta

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
FAILURES = os.path.join(MEMORY, "organ-failures.jsonl")
STATE = os.path.join(MEMORY, "failure-watch.json")
LAB_SESSIONS = os.path.join(MEMORY, "chemistry-lab", "sessions.jsonl")
NTFY = os.environ.get("VINTOS_NTFY_URL", "https://ntfy.sh/vintos-gloria-9kx")
STUDY_FIXES = os.path.join(MEMORY, "study-fixes.json")
LAB_FAILED = ("held_fault", "held_mac_unavailable")
# a lens can miss once to a passing hiccup; this many in a window is a broken part
AT_LEAST = {"slack": 3}


def _now():
    return datetime.now()


def note(organ, what, why=""):
    """Record one failure. Never raises: a failure log that can fail the part it watches is worse than none."""
    try:
        os.makedirs(os.path.dirname(FAILURES), exist_ok=True)
        with open(FAILURES, "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": _now().isoformat(timespec="seconds"), "organ": str(organ)[:40],
                                "what": str(what)[:160], "why": str(why or "")[:300]}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _rows(path):
    """Every readable row; one broken line is skipped, never the whole log."""
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except OSError:
        pass
    return out


def _after(row, since):
    try:
        return datetime.fromisoformat(str(row.get("at", ""))[:19]) > since
    except ValueError:
        return False


def _study_landed():
    """Study fixes that went live and were kept. One refused and then retried successfully is not broken: on
    4 October she was told SF-3a525ff2 "did not land" the morning after it had been kept for an hour."""
    try:
        rows = json.load(open(STUDY_FIXES))
        return {r.get("id") for r in rows if isinstance(r, dict) and r.get("state") == "done"}
    except (OSError, ValueError):
        return set()


def gather(since):
    """[(organ, what, count, last_why)] for everything that failed after `since`, worst first."""
    groups = {}
    landed = _study_landed()
    for r in _rows(FAILURES):
        if r.get("organ") == "study" and str(r.get("why", "")).split(":", 1)[0] in landed:
            continue
        if _after(r, since):
            k = (r.get("organ", "?"), r.get("what", "?"))
            n, _ = groups.get(k, (0, ""))
            groups[k] = (n + 1, r.get("why", ""))
    for r in _rows(LAB_SESSIONS):
        if _after(r, since) and r.get("state") in LAB_FAILED:
            what = "a Lab run stopped (%s)" % ("the Mac was unavailable" if r["state"] == "held_mac_unavailable" else "a fault")
            k = ("lab", what)
            n, _ = groups.get(k, (0, ""))
            exp = ((r.get("plan") or {}).get("experiment") or "")
            groups[k] = (n + 1, ("%s: " % exp if exp else "") + str(r.get("detail") or r.get("error") or ""))
    out = [(o, w, n, why) for (o, w), (n, why) in groups.items() if n >= AT_LEAST.get(o, 1)]
    return sorted(out, key=lambda x: -x[2])


def message(found):
    names = {"slack": "Slack", "atelier": "Atelier", "avatar": "Avatar", "lab": "Lab"}
    return "\n".join("%s: %s%s%s" % (names.get(o, o), w, (" x%d" % n) if n > 1 else "",
                                     (" — last: " + why[:180]) if why else "") for o, w, n, why in found)


def _send(title, body):
    rq = urllib.request.Request(NTFY, data=body.encode("utf-8"), headers={"Title": title, "Priority": "default"})
    urllib.request.urlopen(rq, timeout=20).read()


def tend(now=None, send=None, dry=False):
    """Look at everything since the last look (or the last day), send one message if anything is broken.
    Returns the message, or "" when nothing failed."""
    now = now or _now()
    try:
        st = json.load(open(STATE))
    except (OSError, ValueError):
        st = {}
    try:
        since = datetime.fromisoformat(st["last"])
    except (KeyError, ValueError, TypeError):
        since = now - timedelta(days=1)
    found = gather(since)
    body = message(found)
    if dry:
        return body
    if body:
        (send or _send)("Vintos: something is broken", body)
    os.makedirs(MEMORY, exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump({"last": now.isoformat(timespec="seconds"), "sent": bool(body), "found": len(found)}, open(tmp, "w"))
    os.replace(tmp, STATE)
    return body


if __name__ == "__main__":
    out = tend(dry="--dry" in sys.argv)
    print(out or "nothing failed since the last look")
