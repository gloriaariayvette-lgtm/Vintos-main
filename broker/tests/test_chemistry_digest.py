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
from datetime import date, timedelta
from pathlib import Path
import tempfile

REPO = Path(__file__).resolve().parents[2]
HOME = Path(tempfile.mkdtemp(prefix="vintos-chemistry-digest-"))
WS = HOME / ".vintos" / "workspace"
LAB = WS / "memory" / "chemistry-lab"
LAB.mkdir(parents=True)
os.environ["HOME"] = str(HOME); os.environ["SPARK_WORKSPACE"] = str(WS)

# Keep the fixed-fixture exercise outside the rolling seven-day backfill window. A
# calendar literal eventually entered that window and made the later "ghost" assertion
# refer to the fixture file itself.
FILE_DAY = (date.today() - timedelta(days=20)).isoformat()
DATA_DAY = (date.fromisoformat(FILE_DAY) - timedelta(days=1)).isoformat()
PRIOR = (date.fromisoformat(DATA_DAY) - timedelta(days=1)).isoformat()

def rows(name, values):
    with open(LAB / name, "w") as handle:
        for value in values: handle.write(json.dumps(value) + "\n")

rows("notebook.jsonl", [
    {"at": DATA_DAY + "T01:00:00Z", "kind": "inquiry", "next_question": "which fold returns?"},
    {"at": DATA_DAY + "T02:00:00Z", "kind": "owed_reading", "reading": {"next_question": "what changes at 0.8 A?"}},
    {"at": DATA_DAY + "T02:30:00Z", "kind": "reflection",
     "attention": "the compact fold keeps snapping back to the same basin",
     "inquiry": {"question": "what makes this basin so deep?"}},
    {"at": DATA_DAY + "T04:00:00Z", "kind": "frontier_session",
     "reading": "the VQE run sat well above Hartree-Fock",
     "what_surprised_me": "how cleanly the release resolved"},
    {"at": FILE_DAY + "T06:00:00Z", "kind": "inquiry"},          # today so far — must be excluded
    {"at": PRIOR + "T23:00:00Z", "kind": "atelier-secret"},      # older day — must be excluded
])
rows("taste-observations.jsonl", [
    {"at": DATA_DAY + "T02:10:00Z", "kind": "accession", "key": "P12345",
     "signal": "chosen", "eligibility": "echo_of_injected_taste"},
    {"at": PRIOR + "T01:00:00Z", "kind": "molecule", "key": "old", "signal": "chosen",
     "eligibility": "eligible"},                                 # older day — must be excluded
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
# His own words are surfaced verbatim, not just counted — a day is more than row totals.
assert "A few of today's readings:" in text and "the compact fold keeps snapping back to the same basin" in text
assert "(on: what makes this basin so deep?)" in text, "a reflection carries the inquiry it answered"
assert "Frontier session:" in text and "the VQE run sat well above Hartree-Fock" in text \
    and "how cleanly the release resolved" in text
assert "Taste he noted:" in text and "chosen — accession:P12345 [echo_of_injected_taste]" in text
assert "molecule:old" not in text, "older-day taste is excluded like every other older row"
assert "Next questions:" in text and "which fold returns?" in text, "the recent questions, not just one"
assert "none recorded" not in text, "a day with rows is never an empty receipt"

# Idempotent for the same summarized day.
again, _ = M.append(FILE_DAY)
assert not again and Path(path).read_text() == text

# Regression: the default call summarizes YESTERDAY into TODAY, not today-at-dawn.
wrote2, path2 = M.append()   # file_day=today, data_day=yesterday
assert Path(path2).name == f"daily-inner-life-{date.today().isoformat()}.md"
y = (date.today() - timedelta(days=1)).isoformat()
assert f"<!-- chemistry-lab-digest:{y} -->" in Path(path2).read_text(), "default summarizes yesterday"

# Self-heal: a recent carry-forward file that exists but lacks its receipt gets backfilled,
# once, and a day that never had a morning file is never fabricated. One missed first-light
# morning repairs itself instead of becoming a daily battle.
R = (date.today() - timedelta(days=2)).isoformat()        # a morning that happened
R_data = (date.today() - timedelta(days=3)).isoformat()   # the day it should summarize
inner = Path(M.MEMORY) / f"daily-inner-life-{R}.md"
inner.write_text("# morning\ncarry-forward text\n")       # exists, but no chemistry receipt
healed = M.backfill(7)
assert str(inner) in healed, "backfill repairs a file that is missing its receipt"
assert f"<!-- chemistry-lab-digest:{R_data} -->" in inner.read_text(), "backfilled marker keyed to the summarized day"
assert M.backfill(7) == [] or str(inner) not in M.backfill(7), "backfill is idempotent once a day is healed"
ghost = date.today() - timedelta(days=6)
assert not (Path(M.MEMORY) / f"daily-inner-life-{ghost.isoformat()}.md").exists(), "a day with no morning file is never fabricated"

# Orphan heal: a marker left with NO body (a rewriter stripped the section) must be restored,
# not read as already-present. This is the "comes off the ledger and won't come back" bug —
# the lingering marker was blocking the digest from re-adding the block.
O_FILE = (date.today() - timedelta(days=4)).isoformat()
O_DATA = (date.today() - timedelta(days=5)).isoformat()
orph = Path(M.MEMORY) / f"daily-inner-life-{O_FILE}.md"
orph.write_text(f"# inner\n\n## First Light\nkept body\n\n<!-- chemistry-lab-digest:{O_DATA} -->\n")
healed_wrote, _ = M.append(O_FILE)
ht = orph.read_text()
assert healed_wrote, "an orphan marker is healed, not skipped as already-present"
assert f"## Chemistry Lab — {O_DATA}" in ht, "the body is restored under the orphan marker"
assert ht.count(f"<!-- chemistry-lab-digest:{O_DATA} -->") == 1, "no duplicate marker after healing"
assert "## First Light\nkept body" in ht, "healing preserves the rest of the file"
assert not M.append(O_FILE)[0], "a fully-restored block is idempotent again"

source = (REPO / "scripts" / "chemistry_digest.py").read_text()
assert "memory/atelier" not in source and "atelier-reveals" not in source
assert "_yesterday(" in source, "the day-boundary helper is in use"
assert "def backfill(" in source, "self-healing backfill is present"
dle = (REPO / "bin" / "daily-log-extract.py").read_text()
assert "chemistry-lab|q1-lab" in dle and ".daily-inner-life.lock" in dle, "daily-log-extract carries the lab blocks under the shared lock"
print("all chemistry-digest checks passed (append + backfill + orphan heal)")
