#!/usr/bin/env python3
"""Take out the avatar-chat turns her Watch made (Gloria, 2026-10-05: "Chat connected the hearts and scribbles from
the watch directly to avatar chat. I need to delete and fix this.").

From 00a0594 until 0b751e8 was deployed, /api/watch/reply forwarded each heart, scribble or dictation into
/api/avatar/chat as if she had typed it there. Each became a full turn: her "♥︎" and his answer in the avatar chat,
a row in his conversation ledger (which his Slack context reads), the facts his WAL drew from it, and an imprint.
The route no longer does that (watch_routes.py; test_watch_presence guards it). This removes what it left.

A turn is the Watch's when her words in it are exactly a reply in watch-replies.jsonl, and it was taken within five
minutes of that reply arriving. Her Watch inbox itself is kept: that is where wrist words belong.

    python3 watch_cleanup.py            what would be removed, and nothing else
    python3 watch_cleanup.py --apply    remove it; every file changed is copied to a backup first

Not undone, because they are not stored per turn: the small emotion nudges those messages gave at the time, and
any prediction graded on them. Both fade on their own.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
REPLIES = os.path.join(MEM, "watch-replies.jsonl")
AVATAR = os.path.join(MEM, "avatar-overlay-chat.json")
LEDGER = os.path.join(MEM, "interaction-ledger.json")
WAL_LOG = os.path.join(MEM, "wal-log.json")
WAL_MD = os.path.join(MEM, "wal.md")
IMPRINTS = os.path.join(MEM, "imprints.json")
BEFORE_S, AFTER_S = 15, 300          # a forwarded turn is taken within seconds of the reply; allow five minutes
LEDGER_AFTER_S = 900                 # the ledger writer waits on the imprint first (up to 45 s), then runs


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _epoch(value):
    """Seconds since the epoch from a number, an aware ISO time, or a naive local one (the ledger's)."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _same(a, b):
    """Her words, compared without the variation selector a heart may carry, or surrounding space."""
    clean = lambda t: re.sub(r"[︎️\s]+", " ", str(t or "")).strip()
    return clean(a) == clean(b) and clean(a) != ""


def replies(path=REPLIES):
    out = []
    try:
        for line in open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            at = _epoch(r.get("received_at"))
            if at and str(r.get("text") or "").strip():
                out.append((str(r["text"]), at))
    except OSError:
        pass
    return out


def _from_watch(text, at, wrist, before=BEFORE_S, after=AFTER_S):
    return any(_same(text, t) and t_at - before <= at <= t_at + after for t, t_at in wrist)


def _near(at, wrist, before=60, after=LEDGER_AFTER_S):
    return at is not None and any(t_at - before <= at <= t_at + after for _, t_at in wrist)


def plan():
    """What would go: {store: [...]} with enough of each to see it is right."""
    wrist = replies()
    found = {"avatar": [], "ledger": [], "wal": [], "wal_md": [], "imprints": [], "turn_ids": set(), "facts": set()}
    if not wrist:
        return found
    chat = _load(AVATAR, [])
    for i, e in enumerate(chat):
        if (isinstance(e, dict) and e.get("role") == "user" and _from_watch(e.get("content"), _epoch(e.get("ts")) or 0, wrist)):
            found["avatar"].append(i)
            if i + 1 < len(chat) and isinstance(chat[i + 1], dict) and chat[i + 1].get("role") == "assistant":
                found["avatar"].append(i + 1)
    for i, row in enumerate(_load(LEDGER, [])):
        if isinstance(row, dict) and _from_watch(row.get("gloria"), _epoch(row.get("timestamp")) or 0, wrist,
                                                 after=LEDGER_AFTER_S):
            found["ledger"].append(i)
            if row.get("turn_id"):
                found["turn_ids"].add(str(row["turn_id"]))
            found["facts"].update(str(f) for f in (row.get("wal_facts") or []) if str(f).strip())
    for i, e in enumerate((_load(WAL_LOG, {}) or {}).get("entries", [])):
        prov = e.get("provenance") or {}
        # by its turn id; or, written without one, by the ledger's own list of its facts and its time. A fact the
        # turn only repeated belongs to an older turn and is kept.
        if str(prov.get("turn_id") or "") in found["turn_ids"] or (
                not prov.get("turn_id") and str(e.get("content", ""))[:400] in found["facts"]
                and _near(_epoch(e.get("timestamp")), wrist)):
            found["wal"].append(i)
            found["facts"].add(str(e.get("content", ""))[:400])
    try:
        md = open(WAL_MD, encoding="utf-8").read().splitlines()
    except OSError:
        md = []
    for i, line in enumerate(md):
        m = re.match(r"^- \[(\d{4}-\d\d-\d\d \d\d:\d\d)\] \*\*\w+\*\*: (.*)$", line)
        if m and m.group(2)[:400] in found["facts"] and _near(_epoch(m.group(1).replace(" ", "T")), wrist):
            found["wal_md"].append(i)
    imp = _load(IMPRINTS, [])
    rows = imp.get("imprints", []) if isinstance(imp, dict) else imp
    for i, r in enumerate(rows if isinstance(rows, list) else []):
        if isinstance(r, dict) and _from_watch(r.get("gloria_said"), _epoch(r.get("timestamp")) or 0, wrist,
                                               after=LEDGER_AFTER_S):
            found["imprints"].append(i)
    return found


def _backup(paths):
    dest = os.path.join(MEM, "backups", "watch-cleanup-" + time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(dest, exist_ok=True)
    for p in paths:
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(dest, os.path.basename(p)))
    return dest


def _write_json(path, value):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def apply(found):
    """Remove what plan() found. Returns the backup folder."""
    changed = [p for p, k in ((AVATAR, "avatar"), (LEDGER, "ledger"), (WAL_LOG, "wal"), (WAL_MD, "wal_md"),
                              (IMPRINTS, "imprints")) if found[k]]
    if not changed:
        return None
    dest = _backup(changed)
    if found["avatar"]:
        chat = _load(AVATAR, [])
        _write_json(AVATAR, [e for i, e in enumerate(chat) if i not in set(found["avatar"])])
    if found["ledger"]:
        rows = _load(LEDGER, [])
        _write_json(LEDGER, [r for i, r in enumerate(rows) if i not in set(found["ledger"])])
    if found["wal"]:
        log = _load(WAL_LOG, {})
        log["entries"] = [e for i, e in enumerate(log.get("entries", [])) if i not in set(found["wal"])]
        _write_json(WAL_LOG, log)
    if found["wal_md"]:
        md = open(WAL_MD, encoding="utf-8").read().splitlines()
        with open(WAL_MD + ".tmp", "w", encoding="utf-8") as f:
            f.write("".join(l + "\n" for i, l in enumerate(md) if i not in set(found["wal_md"])))
        os.replace(WAL_MD + ".tmp", WAL_MD)
    if found["imprints"]:
        imp = _load(IMPRINTS, [])
        if isinstance(imp, dict):
            imp["imprints"] = [r for i, r in enumerate(imp.get("imprints", [])) if i not in set(found["imprints"])]
        else:
            imp = [r for i, r in enumerate(imp) if i not in set(found["imprints"])]
        _write_json(IMPRINTS, imp)
    return dest


def report(found):
    chat, ledger = _load(AVATAR, []), _load(LEDGER, [])
    lines = ["Watch turns found:"]
    for i in found["avatar"]:
        e = chat[i]
        lines.append("  avatar chat  %s %s: %s" % (
            datetime.fromtimestamp(_epoch(e.get("ts")) or 0).strftime("%b %d %H:%M"),
            "her" if e.get("role") == "user" else "his", str(e.get("content", ""))[:90].replace("\n", " ")))
    for i in found["ledger"]:
        lines.append("  ledger       %s her: %s" % (str(ledger[i].get("timestamp", ""))[:16], str(ledger[i].get("gloria", ""))[:60]))
    lines.append("  facts drawn from them: %d in wal-log, %d lines in wal.md; imprints: %d" % (
        len(found["wal"]), len(found["wal_md"]), len(found["imprints"])))
    if not any(found[k] for k in ("avatar", "ledger", "wal", "wal_md", "imprints")):
        lines = ["No Watch turns found in avatar chat, his ledger, his facts or his imprints."]
    return "\n".join(lines)


if __name__ == "__main__":
    f = plan()
    print(report(f))
    if "--apply" in sys.argv:
        dest = apply(f)
        print(("Removed. Backup of every file changed: %s" % dest) if dest else "Nothing to remove.")
    elif any(f[k] for k in ("avatar", "ledger", "wal", "wal_md", "imprints")):
        print("\nNothing changed yet. To remove these: python3 %s --apply" % os.path.abspath(__file__))
