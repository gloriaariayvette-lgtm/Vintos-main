#!/usr/bin/env python3
"""Gloria's live pulse: the Aegis receiver validates, stores the latest, and is
honest about freshness — an old reading is never presented as her pulse now.
"""
import os, sys, json, time, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import heart_rate as HR

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

TMP = tempfile.mkdtemp(prefix="hr-")
HR.MEM = TMP
HR.LATEST = os.path.join(TMP, "heart-rate.json")
HR.HIST = os.path.join(TMP, "heart-rate-history.jsonl")
HR.SNAPSHOT = os.path.join(TMP, "ring-temporal-snapshot.json")
HR.SNAPSHOT_HIST = os.path.join(TMP, "ring-temporal-snapshots.jsonl")
HR.SLEEP = os.path.join(TMP, "ring-sleep-latest.json")
HR.SLEEP_HIST = os.path.join(TMP, "ring-sleep-history.jsonl")
# HR.record() reaches sensor_reactions, which appended to HIS sensor-reactions log and
# rewrote its state on every deploy's suite phase. Repoint both before the first record.
import sensor_reactions as SR
SR.MEMORY = TMP
SR.STATE = os.path.join(TMP, "sensor-reactions-state.json")
SR.LOG = os.path.join(TMP, "sensor-reactions.jsonl")

GOOD = {"device": "R21M", "heart_rate_bpm": 86,
        "observed_at": "2026-08-29T12:34:56Z", "source": "0x060A",
        "peripheral_id": "ABC-123"}

print("--- validation ---")
ok, res = HR.record(GOOD)
check("a valid reading is stored", ok and res.get("bpm") == 86, res)
check("zero bpm is refused", not HR.record({**GOOD, "heart_rate_bpm": 0})[0])
check("implausible high is refused", not HR.record({**GOOD, "heart_rate_bpm": 400})[0])
check("missing bpm is refused", not HR.record({"device": "R21M"})[0])
check("non-numeric bpm is refused", not HR.record({**GOOD, "heart_rate_bpm": "fast"})[0])
check("a non-object body is refused", not HR.record("nope")[0])

print("\n--- the store is a single latest record ---")
HR.record({**GOOD, "heart_rate_bpm": 91})
check("latest reflects the newest reading", HR.latest()["bpm"] == 91)
check("it is exactly one record", isinstance(HR.latest(), dict))
check("provenance is stamped", HR.latest().get("provenance") == "r21m_ring")
check("received time is stamped", bool(HR.latest().get("received_ts")))
check("first delivered reading creates a temporal snapshot", json.load(open(HR.SNAPSHOT))["bpm"] == 86)

print("\n--- sleep estimate and temporal context ---")
ok, sleep = HR.record_sleep({"started_at":"2026-08-29T04:00:00Z", "ended_at":"2026-08-29T12:00:00Z",
    "stages_minutes":{"awake":24,"light":220,"deep":105,"rem":131,"nap":0}, "score":82, "wake_count":2})
check("device sleep estimate is stored", ok and sleep["total_sleep_minutes"] == 456)
history_before=open(HR.SLEEP_HIST).read().splitlines()
ok, duplicate = HR.record_sleep({"started_at":"2026-08-29T04:00:00Z", "ended_at":"2026-08-29T12:00:00Z",
    "stages_minutes":{"awake":24,"light":220,"deep":105,"rem":131,"nap":0}, "score":82, "wake_count":2})
check("a repeated ring sync is idempotent", ok and duplicate.get("duplicate") and
      open(HR.SLEEP_HIST).read().splitlines() == history_before)
snap=json.load(open(HR.SNAPSHOT)); snap["received_ts"]=HR._parse_ts("2026-08-29T12:30:00Z"); json.dump(snap,open(HR.SNAPSHOT,"w"))
block=HR.temporal_block(now=HR._parse_ts("2026-08-29T13:00:00Z"))
check("temporal block carries bounded pulse and sleep receipts", "Ring periodic update" in block and
      "7h 36m" in block and "Device estimate" in block, block)
check("sleep rejects impossible duration", not HR.record_sleep({"ended_at":"2026-08-29T12:00:00Z","stages_minutes":{"deep":2000}})[0])

print("\n--- freshness: live / stale / silent ---")
fresh = {**GOOD, "observed_at":HR.datetime.now(HR.timezone.utc).isoformat()}
HR.record(fresh)
st, bpm, age = HR.status()
check("a just-received reading is LIVE", st == "live" and bpm == 86, (st, bpm))
line = HR.context_line()
check("the live line names her real pulse", "86 bpm" in line and "live" in line.lower(), line)
check("the live line tells him not to recite it back", "recite" in line.lower())

# age it past the freshness window, but within mention
r = HR.latest(); r["observed_ts"] = time.time() - 200; json.dump(r, open(HR.LATEST, "w"))
st, bpm, age = HR.status()
check("past the window it is STALE, not live", st == "stale", (st, age))
check("the stale line flags it as not-now",
      "ago" in HR.context_line().lower() and "not" in HR.context_line().lower())

# age it far past — silent
r = HR.latest(); r["observed_ts"] = time.time() - 5000; json.dump(r, open(HR.LATEST, "w"))
check("a very old reading is silent, never presented as now", HR.context_line() == "")
check("status reports none for a very old reading", HR.status()[0] == "none")

ok, _ = HR.record({**GOOD, "heart_rate_bpm": 72, "observed_at":"2026-08-29T01:00:00Z", "source":"0x0518"})
check("late-delivered ring history is never called live", ok and HR.status()[0] == "none")

print("\n--- nothing stored yet ---")
os.remove(HR.LATEST)
check("no reading -> no line", HR.context_line() == "")
check("no reading -> state none", HR.status() == ("none", None, None))

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
