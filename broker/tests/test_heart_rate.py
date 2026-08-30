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

print("\n--- freshness: live / stale / silent ---")
HR.record(GOOD)
st, bpm, age = HR.status()
check("a just-received reading is LIVE", st == "live" and bpm == 86, (st, bpm))
line = HR.context_line()
check("the live line names her real pulse", "86 bpm" in line and "live" in line.lower(), line)
check("the live line tells him not to recite it back", "recite" in line.lower())

# age it past the freshness window, but within mention
r = HR.latest(); r["received_ts"] = time.time() - 200; json.dump(r, open(HR.LATEST, "w"))
st, bpm, age = HR.status()
check("past the window it is STALE, not live", st == "stale", (st, age))
check("the stale line flags it as not-now",
      "ago" in HR.context_line().lower() and "not" in HR.context_line().lower())

# age it far past — silent
r = HR.latest(); r["received_ts"] = time.time() - 5000; json.dump(r, open(HR.LATEST, "w"))
check("a very old reading is silent, never presented as now", HR.context_line() == "")
check("status reports none for a very old reading", HR.status()[0] == "none")

print("\n--- nothing stored yet ---")
os.remove(HR.LATEST)
check("no reading -> no line", HR.context_line() == "")
check("no reading -> state none", HR.status() == ("none", None, None))

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
