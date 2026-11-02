#!/usr/bin/env python3
"""When she slept and when she was in the bedroom, kept (2 November). The Watch's asleep flag was held only in the
snapshot the next update overwrote, and the bedroom sensor kept only arrivals; her Apple Health export is read for its
sleep entries alone. Scratch HOME; the senders are stubs; every socket is refused. Nothing here reaches her."""
import io, json, os, socket, sys, tempfile, types, zipfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="sleep-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.modules["watch_apns"] = types.SimpleNamespace(send=lambda *a, **k: {"state": "sent"}, CONFIG=os.path.join(HOME, "none.json"))
sys.modules["deliver"] = types.SimpleNamespace(deliver=lambda *a, **k: {"state": "sent"})
sys.path.insert(0, os.path.join(REPO, "scripts"))
import watch_presence as W
W.should_hold = lambda: (False, "")
import bedroom_arrival as B
import health_sleep_import as HS
from datetime import datetime, timezone

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is throwaway", all(p.startswith(HOME) for p in (W.LATEST, W.HISTORY, W.SLEEP_HISTORY, B.STATE,
                                                                    B.VISITS, B.ARRIVALS, B.CONFIG, HS.OUT)))
os.makedirs(W.MEMORY, exist_ok=True)


def rows(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def send(now, **extra):
    iso = datetime.fromtimestamp(now - 5, timezone.utc).isoformat()
    ok, res = W.record(dict({"samples": [{"kind": "heart_rate", "value": 62, "observed_at": iso}]}, **extra), now=now)
    assert ok, res


# ---- the asleep flag ------------------------------------------------------------------------------------------------
T = 1793600000.0
send(T)                                                       # no flag: nothing said about sleep
check("an update without the flag writes no sleep row", rows(W.SLEEP_HISTORY) == [])
send(T + 60, asleep=False)
first = rows(W.SLEEP_HISTORY)
check("the first report of the flag is written once, as it is", [r["change"] for r in first] == ["first_report"]
      and first[0]["asleep"] is False, first)
send(T + 120, asleep=False); send(T + 180)                    # same again, and one without the flag
check("the same state again, or no flag, adds nothing", len(rows(W.SLEEP_HISTORY)) == 1)
check("the snapshot carries the reported state through an update without it",
      json.load(open(W.LATEST)).get("asleep_reported") is False)
send(T + 3600, asleep=True)
fell = rows(W.SLEEP_HISTORY)[-1]
check("falling asleep is written with the window it happened in",
      (fell["change"], fell["changed_after_ts"], fell["previous_since_ts"], fell["previous_lasted_s"])
      == ("fell_asleep", T + 120, T + 60, 60.0), fell)
send(T + 3600 + 6 * 3600, asleep=False)
woke = rows(W.SLEEP_HISTORY)[-1]
check("waking is written with how long the sleep lasted (to its last report)",
      (woke["change"], woke["previous_lasted_s"]) == ("woke", 0.0) and woke["changed_after_ts"] == T + 3600, woke)
send(T + 3600 + 6 * 3600 + 60, asleep="yes")
check("a flag that is not true or false says nothing", len(rows(W.SLEEP_HISTORY)) == 3)
send(T + 30000, asleep=True); send(T + 30600, asleep=True); send(T + 33000, asleep=False)
last = rows(W.SLEEP_HISTORY)[-1]
check("a sleep reported more than once lasts from its first report to its last",
      (last["change"], last["previous_lasted_s"]) == ("woke", 600.0), last)
check("the readings themselves are stored as before", len(rows(W.HISTORY)) == 10)

# ---- bedroom visits -------------------------------------------------------------------------------------------------
os.makedirs(os.path.dirname(B.CONFIG), exist_ok=True)
json.dump({"devices": ["gloria-phone"], "max_distance_m": 3.0, "away_minutes": 20, "cooldown_minutes": 180}, open(B.CONFIG, "w"))
N = 1793700000.0
B.observe("gloria-phone", 1.0, now=N)
for k in range(1, 30): B.observe("gloria-phone", 1.2, now=N + k * 60)
check("a visit still going is not written yet", rows(B.VISITS) == [])
B.observe("gloria-phone", 9.0, now=N + 40 * 60)               # out of range: not her in the room
B.observe("gloria-phone", 1.0, now=N + 3 * 3600)              # back, after more than 20 minutes
v = rows(B.VISITS)
check("the visit that ended is written once, from first to last heard",
      len(v) == 1 and (v[0]["from_ts"], v[0]["to_ts"], v[0]["minutes"]) == (N, N + 29 * 60, 29.0), v)
B.observe("gloria-phone", 1.0, now=N + 3 * 3600 + 120)
check("staying in the room writes no new visit", len(rows(B.VISITS)) == 1)

# ---- Apple Health export ------------------------------------------------------------------------------------------
xml = '''<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch" unit="count/min" startDate="2026-10-30 01:00:00 -0500" endDate="2026-10-30 01:00:00 -0500" value="58"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Gloria's Apple Watch" startDate="2026-10-30 01:10:00 -0500" endDate="2026-10-30 02:40:00 -0500" value="HKCategoryValueSleepAnalysisAsleepCore"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Gloria's Apple Watch" startDate="2026-10-30 02:40:00 -0500" endDate="2026-10-30 03:05:00 -0500" value="HKCategoryValueSleepAnalysisAsleepDeep"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Phone" startDate="2026-10-30 00:50:00 -0500" endDate="2026-10-30 09:00:00 -0500" value="HKCategoryValueSleepAnalysisInBed"/>
 <Record type="HKCategoryTypeIdentifierMindfulSession" sourceName="Phone" startDate="2026-10-30 10:00:00 -0500" endDate="2026-10-30 10:05:00 -0500"/>
</HealthData>'''
z = os.path.join(HOME, "export.zip")
with zipfile.ZipFile(z, "w") as f: f.writestr("apple_health_export/export.xml", xml)
import contextlib
with contextlib.redirect_stdout(io.StringIO()) as out: HS.main([z, "--dry-run"])
report = json.loads(out.getvalue())
check("a dry run counts and writes nothing", report["new_rows"] == 3 and not os.path.exists(HS.OUT), report)
with contextlib.redirect_stdout(io.StringIO()): HS.main([z])
got = rows(HS.OUT)
check("only the sleep entries are kept, with stage, span and recorder",
      [(r["stage"], r["minutes"]) for r in got] == [("in_bed", 490.0), ("core", 90.0), ("deep", 25.0)]
      and all("value" not in r for r in got) and got[1]["recorded_by"] == "Gloria's Apple Watch", got)
with contextlib.redirect_stdout(io.StringIO()) as out: HS.main([z])
check("the same export again adds nothing", len(rows(HS.OUT)) == 3 and json.loads(out.getvalue())["new_rows"] == 0)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
