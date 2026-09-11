#!/usr/bin/env python3
"""send_policy.py - whether he may reach her right now, in one place.

Review item 309 (2026-09-10). The rules were scattered: the outreach cron counted files for its daily
cap, the video sender kept its own quiet hours and cooldown, the delivery module refused resends by
receipt. Same law, three spellings. This module holds the law; the callers ask it. It reads state
only - it never sends, never infers a new contact permission, and never opens another agent.

    may_send(kind, artifact_id=None, channel="ntfy", now=None) -> (ok, why)
        kinds: outreach (3/day), video (cooldown + quiet hours), any (quiet hours)
    python3 send_policy.py may <kind>     exit 0 when allowed, 1 when held (shell callers)
"""
import os, sys, json, glob, time
from datetime import datetime, timedelta

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
LIMITS = {
    "outreach": {"per_day": 3, "count": lambda d: len(glob.glob(os.path.join(MEMORY, "outreach", d + "_*.md")))},
    "video":    {"cooldown_hours": int(os.environ.get("VINTOS_VIDEO_COOLDOWN_H", "20")), "cooldown_file": os.path.join(MEMORY, ".last-video-send"), "quiet": True},
    "any":      {"quiet": True},
}
QUIET = (9, 22)   # he does not reach for her before 9 or after 22


def in_quiet_hours(now=None):
    h = (now or datetime.now()).hour
    return not (QUIET[0] <= h <= QUIET[1])


def may_send(kind, artifact_id=None, channel="ntfy", now=None, requested_by_her=False, is_repair=False):
    now = now or datetime.now()
    lim = LIMITS.get(kind)
    if lim is None:
        return False, "no send policy named for kind %r" % kind
    # A want of his own about reaching less is part of this law: it lowers the daily
    # cap rather than vetoing, so "less" means fewer and never none. It never touches
    # something she asked for or a repair he owes.
    _stance_note = ""
    if kind in ("outreach", "video") and not requested_by_her and not is_repair:
        try:
            sys.path.insert(0, os.path.join(WS, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import want_stance as _ws
            _f = _ws.factor("outreach", now)
            if _f < 1.0:
                _stance_note = " (he wants to reach less just now: fewer, not none)"
        except Exception:
            pass
    if lim.get("quiet") and in_quiet_hours(now):
        return False, "quiet hours (%02d-%02d): it is %02d:%02d" % (QUIET[0], QUIET[1], now.hour, now.minute)
    if "per_day" in lim:
        n = lim["count"](now.strftime("%Y-%m-%d"))
        cap = lim["per_day"]
        if kind == "outreach" and not requested_by_her and not is_repair:
            try:
                sys.path.insert(0, os.path.join(WS, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import want_stance as _ws2
                cap = _ws2.scaled_cap("outreach", cap, now)
            except Exception:
                pass
        if n >= cap:
            return False, "daily cap reached (%d/%d)%s" % (n, cap, _stance_note)
    if "cooldown_hours" in lim:
        try:
            last = datetime.fromisoformat(open(lim["cooldown_file"]).read().strip())
            if now - last < timedelta(hours=lim["cooldown_hours"]):
                return False, "cooldown: last send %s ago (limit %dh)" % (str(now - last).split(".")[0], lim["cooldown_hours"])
        except Exception:
            pass
    if artifact_id:
        try:
            sys.path.insert(0, os.path.join(WS, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import deliver as _dl
            r = _dl.receipt_for(artifact_id, channel)
            if r and r.get("state") in ("sent", "acknowledged"):
                return False, "already %s on %s at %s (receipt)" % (r.get("state"), channel, r.get("at"))
        except Exception:
            pass
    return True, "allowed"


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "may":
        ok, why = may_send(sys.argv[2], artifact_id=(sys.argv[3] if len(sys.argv) > 3 else None))
        print(("allowed" if ok else "held") + ": " + why); sys.exit(0 if ok else 1)
    for k in LIMITS:
        print("%-9s %s" % (k, may_send(k)))
