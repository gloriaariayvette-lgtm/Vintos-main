#!/usr/bin/env python3
"""mischief_timing.py -- is this a moment for mischief?

Mischief is not on a schedule and should not be: it fires when a latent thread spurs it or when he wants it. What
those triggers never asked is whether Gloria is there to notice. A purple light in an empty room at 3am is not a
prank. Three gates, all from what he already knows:

  quiet hours     23:00-08:00 by default (VINTOS_QUIET_HOURS="23-8"): she is asleep or nearly; nothing.
  she is around   the interaction ledger has an entry within RECENT_HOURS (default 3): she has talked to him
                  lately, so she is likely home and awake.
  not mid-call    a voice session marker younger than 3 minutes means she is on a call with him; a light going
                  purple then is an interruption, not a joke.

--force skips the "around" gate (he asked for it, she may be about to walk in) but never the quiet hours.
CLI: mischief_timing.py [--force]  -> prints ok/reason, exit 0 when ok.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

WORKSPACE = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WORKSPACE, "memory")
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")
VOICE_MARK = os.path.join(MEMORY, ".voice-live")           # touched by the voice route while a call is on
RECENT_HOURS = float(os.environ.get("VINTOS_MISCHIEF_RECENT_HOURS", "3"))


def quiet_hours() -> tuple[int, int]:
    raw = os.environ.get("VINTOS_QUIET_HOURS", "23-8")
    try:
        a, b = raw.split("-"); return int(a) % 24, int(b) % 24
    except Exception:
        return 23, 8


def in_quiet(now: float) -> bool:
    start, end = quiet_hours(); h = datetime.fromtimestamp(now).hour
    return (h >= start or h < end) if start > end else (start <= h < end)


def last_interaction(now: float) -> float | None:
    """Seconds since the newest ledger entry, or None when there is no ledger."""
    try:
        rows = json.load(open(LEDGER))
    except Exception:
        return None
    best = None
    for e in rows[-40:] if isinstance(rows, list) else []:
        try:
            ts = datetime.fromisoformat(str(e.get("timestamp", "")).replace("Z", "")).timestamp()
            best = ts if best is None or ts > best else best
        except Exception:
            continue
    return None if best is None else max(0.0, now - best)


def on_call(now: float) -> bool:
    try:
        return now - os.path.getmtime(VOICE_MARK) < 180
    except OSError:
        return False


def ok_now(now: float | None = None, force: bool = False) -> tuple[bool, str]:
    now = time.time() if now is None else now
    if in_quiet(now):
        a, b = quiet_hours(); return False, f"quiet hours ({a:02d}:00-{b:02d}:00): she is asleep or nearly"
    if on_call(now):
        return False, "she is on a voice call with him right now"
    from want_stance import may_initiate
    allowed, why = may_initiate("mischief")
    if not allowed: return False, why
    if not force:
        since = last_interaction(now)
        if since is None:
            return False, "no interaction ledger: cannot tell whether she is around"
        if since > RECENT_HOURS * 3600:
            return False, f"she has not spoken to him for {since / 3600:.1f}h: likely not around to notice"
        return True, f"she was here {since / 60:.0f} min ago, daytime, no call"
    return True, "forced: daytime, no call"


if __name__ == "__main__":
    ok, why = ok_now(force="--force" in sys.argv[1:])
    print(("ok: " if ok else "no: ") + why); sys.exit(0 if ok else 1)
