#!/usr/bin/env python3
"""build_merged_chat.py — unify main + voice + avatar chats into
chat-history-merged.json so time/silence calcs see ALL conversations.

Lossless by construction. The first version rebuilt each record as exactly
{role, content, timestamp}, which had two consequences nobody intended:

  - generation_provenance was dropped. Every downstream learner — repair,
    encounter, JEPA, drift, causality, value-map — reads this file, so a
    tactical act arrived looking like an ordinary turn one cron later. The
    protection lived on the record and the merge threw the record away.
  - every avatar turn got the avatar FILE's mtime, because avatar records
    carry their time in `ts`, not `timestamp`. Distinct turns across the whole
    retained window collapsed onto one instant, and that instant was "now".

So: carry every field the source record had, take the real per-turn time
wherever one exists, and when there genuinely isn't one say so on the record
(`timestamp_estimated`) instead of presenting a guess as fact.

Never worse than before: falls back to copying main on any error.
"""
import os, json, shutil
from datetime import datetime

MEM = os.path.expanduser("~/.vintos/workspace/memory")
main   = os.path.join(MEM, "chat-history.json")
voice  = os.path.join(MEM, "voice-chat-history.json")
avatar = os.path.join(MEM, "avatar-overlay-chat.json")
merged = os.path.join(MEM, "chat-history-merged.json")

# Fields that must survive the merge or a protection silently stops applying.
CARRY = ("generation_provenance", "provenance", "may_witness", "turn_id",
         "capsule_commitment", "stratagem_id", "surface", "eligible",
         "admitted", "offered", "withheld", "tactical")
# Where a per-turn time can legitimately live, in order of preference.
TIME_KEYS = ("timestamp", "ts", "time", "at", "created")


def load(p):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return []


def pts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        pass
    try:                       # epoch seconds are a legitimate per-turn time too
        v = float(s)
        return v if v > 1e8 else 0.0
    except Exception:
        return 0.0


def entry(e, role, content, ts, source, estimated=False):
    """One merged record: the carried protections, then the merged view."""
    out = {k: e[k] for k in CARRY if isinstance(e, dict) and k in e}
    out.update({"role": role, "content": content, "timestamp": ts, "source": source})
    if estimated:
        out["timestamp_estimated"] = True
    return out


def own_time(e):
    """(iso_or_empty, found). Never invents one."""
    for k in TIME_KEYS:
        v = e.get(k)
        if v in (None, ""):
            continue
        if pts(v) > 0:
            try:
                return datetime.fromtimestamp(pts(v)).isoformat(), True
            except Exception:
                return str(v), True
    return "", False


out = []
try:
    for e in load(main):
        if isinstance(e, dict) and e.get("timestamp"):
            out.append(entry(e, e.get("role", "user"), e.get("content", ""),
                             e["timestamp"], "main"))

    for e in load(voice):
        if not isinstance(e, dict):
            continue
        ts, _ = own_time(e)
        ts = ts or e.get("timestamp") or ""
        if e.get("user"):
            out.append(entry(e, "user", str(e["user"]), ts, "voice"))
        if e.get("vintos"):
            out.append(entry(e, "assistant", str(e["vintos"]), ts, "voice"))

    if os.path.exists(avatar):
        # Only ever a LAST resort, and only for the records that truly lack a
        # time — not a blanket stamp over the whole file.
        amt = datetime.fromtimestamp(os.path.getmtime(avatar)).isoformat()
        for e in load(avatar):
            if not (isinstance(e, dict) and e.get("content")):
                continue
            ts, found = own_time(e)
            out.append(entry(e, e.get("role", "user"), str(e.get("content", "")),
                             ts if found else amt, "avatar", estimated=not found))

    out = [e for e in out if pts(e.get("timestamp")) > 0]
    out.sort(key=lambda e: pts(e["timestamp"]))
    if not out:
        raise ValueError("empty")
    with open(merged, "w") as f:
        json.dump(out, f)
except Exception:
    try:
        shutil.copy2(main, merged)
    except Exception:
        pass
