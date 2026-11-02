#!/usr/bin/env python3
"""Her sleep history from an Apple Health export, and nothing else from it (2 November).

In the Health app: profile picture, Export All Health Data. That gives export.zip (apple_health_export/export.xml).
This reads only the sleep entries (HKCategoryTypeIdentifierSleepAnalysis: in bed, asleep core/deep/REM/unspecified,
awake), each with its start, end, stage and the device that recorded it, into memory/health-sleep-history.jsonl.
Every other record in the export is passed over unread. Run again with a newer export: rows already kept are not
added twice. Nothing is sent anywhere.

    python3 health_sleep_import.py ~/export.zip --dry-run    # counts only, writes nothing
    python3 health_sleep_import.py ~/export.zip
"""
import argparse, json, os, sys, zipfile
from datetime import datetime
import xml.etree.ElementTree as ET

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
OUT = os.path.join(WS, "memory", "health-sleep-history.jsonl")
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
STAGES = {"HKCategoryValueSleepAnalysisInBed": "in_bed", "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",
          "HKCategoryValueSleepAnalysisAsleep": "asleep", "HKCategoryValueSleepAnalysisAsleepCore": "core",
          "HKCategoryValueSleepAnalysisAsleepDeep": "deep", "HKCategoryValueSleepAnalysisAsleepREM": "rem",
          "HKCategoryValueSleepAnalysisAwake": "awake"}


def _when(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S %z")


def _open(path):
    if zipfile.is_zipfile(path):
        z = zipfile.ZipFile(path)
        name = next((n for n in z.namelist() if n.endswith("/export.xml") or n == "export.xml"), None)
        if name is None: raise SystemExit("no export.xml in %s" % path)
        return z.open(name)
    return open(path, "rb")


def read(path):
    """Sleep rows, in file order. The export can be gigabytes: each element is cleared once read."""
    with _open(path) as stream:
        for _, el in ET.iterparse(stream, events=("end",)):
            if el.tag == "Record" and el.get("type") == SLEEP:
                start, end = _when(el.get("startDate")), _when(el.get("endDate"))
                stage = STAGES.get(el.get("value"), "unknown")
                yield {"start": start.isoformat(), "end": end.isoformat(), "start_ts": start.timestamp(),
                       "end_ts": end.timestamp(), "minutes": round((end - start).total_seconds() / 60, 1),
                       "stage": stage, "recorded_by": (el.get("sourceName") or "")[:60],
                       "source": "Apple Health export", "estimate": "device estimate, not a medical fact"}
            if el.tag in ("Record", "Workout", "ActivitySummary", "ClinicalRecord", "Correlation"):
                el.clear()


def key(r):
    return (round(r["start_ts"]), round(r["end_ts"]), r["stage"], r["recorded_by"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export", help="export.zip or export.xml")
    ap.add_argument("--dry-run", action="store_true", help="count only; write nothing")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    have = set()
    if os.path.exists(a.out):
        for line in open(a.out):
            try: have.add(key(json.loads(line)))
            except (ValueError, KeyError): pass
    new, stages, first, last = [], {}, None, None
    for r in read(a.export):
        if key(r) in have: continue
        have.add(key(r)); new.append(r)
        stages[r["stage"]] = stages.get(r["stage"], 0) + 1
        first = min(first or r["start"], r["start"]); last = max(last or r["end"], r["end"])
    new.sort(key=lambda r: r["start_ts"])
    print(json.dumps({"new_rows": len(new), "by_stage": stages, "from": first, "to": last,
                      "written_to": None if a.dry_run else a.out}, indent=1))
    if a.dry_run or not new: return 0
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "a") as f:
        for r in new: f.write(json.dumps(r) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
