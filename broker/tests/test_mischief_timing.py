#!/usr/bin/env python3
"""Mischief timing: quiet hours block even a forced act; a voice call blocks; no recent interaction blocks unless
forced; a recent daytime interaction with no call is a go. Scratch workspace only."""
import os, sys, json, tempfile, time
from datetime import datetime
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(); os.makedirs(os.path.join(TMP, "memory")); os.environ["SPARK_WORKSPACE"] = TMP; os.environ["VINTOS_QUIET_HOURS"] = "23-8"
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import mischief_timing as MT
assert MT.LEDGER.startswith(TMP)
R = []
def check(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -- {d}"))
def at(h, m=0): return datetime.now().replace(hour=h, minute=m, second=0, microsecond=0).timestamp()
def ledger(age_s, now): json.dump([{"turn_id": "x", "timestamp": datetime.fromtimestamp(now - age_s).isoformat()}], open(MT.LEDGER, "w"))

now = at(15)
check("no ledger: cannot tell she is around -> no", MT.ok_now(now)[0] is False and "ledger" in MT.ok_now(now)[1])
ledger(20 * 60, now)
check("she spoke 20 min ago, 3pm, no call -> go", MT.ok_now(now)[0] is True, MT.ok_now(now))
ledger(5 * 3600, now)
check("silent for 5h -> no, but forced -> go", MT.ok_now(now)[0] is False and MT.ok_now(now, force=True)[0] is True, (MT.ok_now(now), MT.ok_now(now, force=True)))
check("quiet hours block even a forced act", MT.ok_now(at(2), force=True)[0] is False and MT.ok_now(at(23, 30), force=True)[0] is False and "quiet" in MT.ok_now(at(2))[1])
check("08:00 is the edge: quiet ends", MT.ok_now(at(8), force=True)[0] is True)
ledger(60, now); open(MT.VOICE_MARK, "w").close()
# The test's clock is fixed at 15:00; anchor the marker to that same clock.
# Otherwise a run before 08:00 makes the freshly-created real-time file look
# many synthetic hours old and tests wall-clock disagreement, not call gating.
os.utime(MT.VOICE_MARK, (now, now))
check("a voice call under way -> no", MT.ok_now(now)[0] is False and "call" in MT.ok_now(now)[1])
os.utime(MT.VOICE_MARK, (now - 600, now - 600))
check("a call that ended 10 min ago no longer blocks", MT.ok_now(now)[0] is True)
import shutil; shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
