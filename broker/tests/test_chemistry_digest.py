#!/usr/bin/env python3
"""Chemistry digest: scratch HOME, mechanical rows, one marked append.

The load-bearing property is the day boundary: first-light runs before dawn and
summarizes the PREVIOUS day, so the digest must report yesterday's finished rows into
today's carry-forward file — never today's barely-started rows. The original bug rendered
date.today() at 5am and left an empty marker over a full day of real work.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile

REPO = Path(__file__).resolve().parents[2]
HOME = Path(tempfile.mkdtemp(prefix="vintos-chemistry-digest-"))
WS = HOME / ".vintos" / "workspace"
LAB = WS / "memory" / "chemistry-lab"
LAB.mkdir(parents=True)
os.environ["HOME"] = str(HOME); os.environ["SPARK_WORKSPACE"] = str(WS)

DATA_DAY = "2026-09-13"   # the finished day, with real rows (like the 1,177 seen live)
FILE_DAY = "2026-09-14"   # the morning after — the file first-light writes into
PRIOR = "2026-09-12"      # the day before that — must not bleed in

def rows(name, values):
    with open(LAB / name, "w") as handle:
        for value in values: handle.write(json.dumps(value) + "\n")

rows("notebook.jsonl", [
    {"at": DATA_DAY + "T01:00:00Z", "kind": "inquiry", "next_question": "which fold returns?"},
    {"at": DATA_DAY + "T02:00:00Z", "kind": "owed_reading", "reading": {"next_question": "what changes at 0.8 A?"}},
    {"at": FILE_DAY + "T06:00:00Z", "kind": "inquiry"},          # today so far — must be excluded
    {"at": PRIOR + "T23:00:00Z", "kind": "atelier-secret"},      # older day — must be excluded
])
rows("sessions.jsonl", [
    {"at": DATA_DAY + "T02:00:00Z", "state": "completed", "mac_run_id": "RUN-1",
     "plan": {"experiment": "molecule"},
     "grade": {"execution_state": "completed", "aggregate_accuracy": "ALL_WORSE_THAN_HARTREE_FOCK"}},
    {"at": DATA_DAY + "T03:00:00Z", "state": "held_reading_owed", "owed_reading": "STILL_HELD"},
])
rows("experiment-grades.jsonl", [{"at": DATA_DAY + "T02:00:01Z", "run_id": "RUN-1",
                                   "experiment": "molecule", "execution_state": "completed",
                                   "aggregate_accuracy": "ALL_WORSE_THAN_HARTREE_FOCK"}])

spec = importlib.util.spec_from_file_location("chemistry_digest_test", REPO / "scripts" / "chemistry_digest.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
assert M.MEMORY.startswith(str(HOME)) and M.LAB.startswith(str(HOME))

# The morning-after append: yesterday's data, today's file, marker keyed to the data day.
wrote, path = M.append(FILE_DAY)
assert wrote and Path(path).is_relative_to(HOME)
assert Path(path).name == f"daily-inner-life-{FILE_DAY}.md", "writes into today's carry-forward file"
text = Path(path).read_text()
assert text.count(f"<!-- chemistry-lab-digest:{DATA_DAY} -->") == 1, "marker keyed to the summarized day"
assert f"chemistry-lab-digest:{FILE_DAY}" not in text, "never keyed to the unfinished day"
assert f"## Chemistry Lab — {DATA_DAY}" in text, "heading names the day summarized"

# Yesterday's real rows are there; the unfinished day and older days are not.
assert "inquiry 1" in text and "owed_reading 1" in text
assert "execution=completed; accuracy=ALL_WORSE_THAN_HARTREE_FOCK; run=RUN-1" in text
assert "owed/held 1; settled 1" in text and "what changes at 0.8 A?" in text
assert "atelier-secret" not in text and "Execution is not correctness" in text
assert "none recorded" not in text, "a day with rows is never an empty receipt"

# Idempotent for the same summarized day.
again, _ = M.append(FILE_DAY)
assert not again and Path(path).read_text() == text

# Regression: the default call summarizes YESTERDAY into TODAY, not today-at-dawn.
from datetime import date, timedelta
wrote2, path2 = M.append()   # file_day=today, data_day=yesterday
assert Path(path2).name == f"daily-inner-life-{date.today().isoformat()}.md"
y = (date.today() - timedelta(days=1)).isoformat()
assert f"<!-- chemistry-lab-digest:{y} -->" in Path(path2).read_text(), "default summarizes yesterday"

source = (REPO / "scripts" / "chemistry_digest.py").read_text()
assert "memory/atelier" not in source and "atelier-reveals" not in source
assert "_yesterday(" in source, "the day-boundary helper is in use"
print("16/16 passed")
