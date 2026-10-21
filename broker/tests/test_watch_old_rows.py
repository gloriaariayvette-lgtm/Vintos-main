#!/usr/bin/env python3
"""One reading older than 48 hours does not refuse the new readings sent with it (21 October: the Watch app now sends
its anchored heart-rate history, and the backend refused a whole batch for one row outside its window).

Scratch workspace; nothing is sent; sockets are refused."""
import json, os, socket, sys, tempfile
from datetime import datetime, timezone
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="watch-old-rows-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import watch_presence as W
mem = os.path.join(HOME, "mem"); os.makedirs(mem)
W.LATEST, W.HISTORY, W.LIVE = (os.path.join(mem, n) for n in ("watch-presence.json", "history.jsonl", "watch-live.json"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:300],)))
check("its stores are scratch", all(p.startswith(HOME) for p in (W.LATEST, W.HISTORY, W.LIVE)))
T = 1_800_000_000.0
at = lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat()
hr = lambda ts, v: {"kind": "heart_rate", "value": v, "unit": "count/min", "observed_at": at(ts)}

ok, out = W.record({"samples": [hr(T - 3 * 86400, 61), hr(T - 600, 72), hr(T - 60, 75)]}, now=T)
check("the old row is passed over and the new ones are kept", ok and out["stored"] == 2 and out["skipped_stale"] == 1, out)
rows = [json.loads(l) for l in open(W.HISTORY)]
check("only the new readings are in his history", [r["value"] for r in rows] == [72.0, 75.0], rows)
check("the newest is his latest", json.load(open(W.LATEST))["latest"]["heart_rate"]["value"] == 75.0)
ok, out = W.record({"samples": [hr(T - 5 * 86400, 60)]}, now=T)
check("a batch of only old rows is accepted with nothing stored, so the Watch moves its anchor on",
      ok and out["stored"] == 0 and out["skipped_stale"] == 1, out)
ok, out = W.record({"samples": [hr(T - 60, 72), {"kind": "heart_rate", "value": 999, "observed_at": at(T)}]}, now=T)
check("bad data still refuses the batch", not ok and "plausible" in out, out)
ok, out = W.record({"samples": [hr(T - 5 * i, 70) for i in range(W.MAX_ROWS)]}, now=T)
check("an anchored catch-up of hundreds of readings is taken", ok and out["stored"] == W.MAX_ROWS, out)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
