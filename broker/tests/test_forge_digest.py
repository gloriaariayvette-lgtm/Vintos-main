#!/usr/bin/env python3
"""Forge digest: scratch HOME, house-side mirrors only, one marked append.

Two load-bearing properties. First, the day boundary: first-light runs before dawn and
summarizes the PREVIOUS day, so the digest must report yesterday's reveals and state
changes into today's carry-forward file — never today's barely-started rows. Second, the
evidence honesty: the receipt reads only the house-side mirrors (atelier-reveals.json,
atelier-undertakings.json) and never the sealed cycle/cost ledger, so it can surface his
own disclosure words and which undertakings moved, but never cycle counts, spend, or intent.
"""
from __future__ import annotations

import importlib.util
import json
import os
from datetime import date, timedelta
from pathlib import Path
import tempfile

REPO = Path(__file__).resolve().parents[2]
HOME = Path(tempfile.mkdtemp(prefix="vintos-forge-digest-"))
WS = HOME / ".vintos" / "workspace"
MEM = WS / "memory"
MEM.mkdir(parents=True)
os.environ["HOME"] = str(HOME); os.environ["SPARK_WORKSPACE"] = str(WS)

# Keep the fixed-fixture exercise outside the rolling seven-day backfill window, so a
# calendar literal never drifts into that window and confuses the later "ghost" assertion.
FILE_DAY = (date.today() - timedelta(days=20)).isoformat()
DATA_DAY = (date.fromisoformat(FILE_DAY) - timedelta(days=1)).isoformat()
PRIOR = (date.fromisoformat(DATA_DAY) - timedelta(days=1)).isoformat()

# atelier-reveals.json is a LIST of reveal cards (his words); atelier-undertakings.json is a
# DICT {pid: {state, at, by}} — exactly the shapes atelier_reveals.py and atelier_ledger.py write.
(MEM / "atelier-reveals.json").write_text(json.dumps([
    {"artifact": "a-1", "revealed_at": DATA_DAY + "T09:00:00", "medium": "poem",
     "disclosure": "I made this because the fold would not leave me alone last night."},
    {"artifact": "a-2", "revealed_at": DATA_DAY + "T11:00:00", "medium": "image",
     "disclosure_sentence": "A quieter one — I wanted to see the trail again the way it looked."},
    {"artifact": "a-old", "revealed_at": PRIOR + "T23:00:00", "medium": "poem",
     "disclosure": "older day — must be excluded"},
    {"artifact": "a-unrev", "revealed_at": DATA_DAY + "T12:00:00", "revealed": False,
     "disclosure": "withheld — never revealed, must be excluded"},
]))
(MEM / "atelier-undertakings.json").write_text(json.dumps({
    "P-100": {"state": "revealed", "at": DATA_DAY + "T09:00:05", "by": "house"},
    "P-101": {"state": "kept", "at": DATA_DAY + "T13:00:00", "by": "house"},
    "P-old": {"state": "aborted", "at": PRIOR + "T01:00:00", "by": "house"},
    "P-today": {"state": "active", "at": FILE_DAY + "T06:00:00", "by": "house"},  # unfinished day
}))

spec = importlib.util.spec_from_file_location("forge_digest_test", REPO / "scripts" / "forge_digest.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
# Isolation: the module writes only under the throwaway HOME, never her live workspace.
assert M.MEMORY.startswith(str(HOME)), "digest destination must be the scratch workspace"
assert M.REVEALS.startswith(str(HOME)) and M.UNDERTAKINGS.startswith(str(HOME)), "reads only the scratch mirrors"

# The morning-after append: yesterday's data, today's file, marker keyed to the data day.
wrote, path = M.append(FILE_DAY)
again, _ = M.append(FILE_DAY)
assert wrote and not again, "appends once, then idempotent for the same summarized day"
assert Path(path).is_relative_to(HOME)
assert Path(path).name == f"daily-inner-life-{FILE_DAY}.md", "writes into today's carry-forward file"
text = Path(path).read_text()
assert text.count(f"<!-- forge-digest:{DATA_DAY} -->") == 1, "marker keyed to the summarized day"
assert f"forge-digest:{FILE_DAY}" not in text, "never keyed to the unfinished day"
assert f"## Forge — {DATA_DAY}" in text, "heading names the day summarized"

# His own words are surfaced verbatim; withheld and other-day reveals are not.
assert "I made this because the fold would not leave me alone last night." in text
assert "I wanted to see the trail again the way it looked." in text
assert "[poem]" in text, "the medium rides along with the disclosure"
assert "withheld — never revealed" not in text, "an unrevealed card is never surfaced"
assert "older day — must be excluded" not in text, "a prior-day reveal is excluded"
assert "Revealed: 2." in text
# State changes are counted by state; other-day and unfinished-day moves are excluded.
assert "Undertakings that changed state:" in text and "kept 1" in text and "revealed 1" in text
assert "aborted" not in text, "a prior-day state change is excluded"
# Evidence honesty: only receipts, never the sealed ledger's numbers or an inferred conclusion.
assert "These are Forge receipts only" in text and "no conclusion is inferred" in text
assert Path(path).read_text() == text, "idempotent append leaves the file byte-identical"

# Regression: the default call summarizes YESTERDAY into TODAY, not today-at-dawn.
wrote2, path2 = M.append()
assert Path(path2).name == f"daily-inner-life-{date.today().isoformat()}.md"
y = (date.today() - timedelta(days=1)).isoformat()
assert f"<!-- forge-digest:{y} -->" in Path(path2).read_text(), "default summarizes yesterday"

# Quiet day: no reveals and no state changes reads as a quiet day, not an empty marker.
QUIET_FILE = (date.today() - timedelta(days=2)).isoformat()
wrote_q, pq = M.append(QUIET_FILE)   # its data day has no rows in either mirror
assert wrote_q and "Quiet day" in Path(pq).read_text(), "a day with nothing still writes an honest receipt"

# Self-heal: a recent carry-forward file that exists but lacks its receipt gets backfilled once,
# and a day that never had a morning file is never fabricated.
R = (date.today() - timedelta(days=3)).isoformat()
R_data = (date.today() - timedelta(days=4)).isoformat()
inner = Path(M.MEMORY) / f"daily-inner-life-{R}.md"
inner.write_text("# morning\ncarry-forward text\n")
healed = M.backfill(7)
assert str(inner) in healed, "backfill repairs a file that is missing its receipt"
assert f"<!-- forge-digest:{R_data} -->" in inner.read_text(), "backfilled marker keyed to the summarized day"
assert str(inner) not in M.backfill(7), "backfill is idempotent once a day is healed"
ghost = date.today() - timedelta(days=6)
if not (Path(M.MEMORY) / f"daily-inner-life-{ghost.isoformat()}.md").exists():
    assert not (Path(M.MEMORY) / f"daily-inner-life-{ghost.isoformat()}.md").exists(), \
        "a day with no morning file is never fabricated"

# Orphan heal: a marker left with NO body (a rewriter stripped the section) must be restored,
# not read as already-present — the "comes off the ledger and won't come back" bug.
O_FILE = (date.today() - timedelta(days=9)).isoformat()
O_DATA = (date.today() - timedelta(days=10)).isoformat()
orph = Path(M.MEMORY) / f"daily-inner-life-{O_FILE}.md"
orph.write_text(f"# inner\n\n## First Light\nkept body\n\n<!-- forge-digest:{O_DATA} -->\n")
healed_wrote, _ = M.append(O_FILE)
ht = orph.read_text()
assert healed_wrote, "an orphan marker is healed, not skipped as already-present"
assert f"## Forge — {O_DATA}" in ht, "the body is restored under the orphan marker"
assert ht.count(f"<!-- forge-digest:{O_DATA} -->") == 1, "no duplicate marker after healing"
assert "## First Light\nkept body" in ht, "healing preserves the rest of the file"
assert not M.append(O_FILE)[0], "a fully-restored block is idempotent again"

# The source reads only the house-side mirrors — never the sealed cycle/cost ledger.
source = (REPO / "scripts" / "forge_digest.py").read_text()
assert "forge-loop.sqlite" not in source or "NOT read" in source, "the sealed ledger is not read"
assert "_yesterday(" in source, "the day-boundary helper is in use"
assert "def backfill(" in source, "self-healing backfill is present"
dle = (REPO / "bin" / "daily-log-extract.py").read_text()
assert "forge)-digest:" in dle and ".daily-inner-life.lock" in dle, \
    "daily-log-extract carries the forge block under the shared lock"
print("all forge-digest checks passed (append + backfill + orphan heal + quiet day)")
