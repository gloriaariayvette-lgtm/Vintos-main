#!/usr/bin/env python3
"""Forge digest: scratch HOME, the Forge named (not the Atelier), with a content-free fallback.

The Forge is what Gloria pays for, so the receipt NAMES what it is building — intent, state and
spend read from the Forge's own owner API — without any interactive code. Only a project in a
private interval (his opt-in Atelier-style seal) keeps its intent hidden. If the Forge service is
unreachable the receipt falls back to the content-free house mirror rather than fabricating.

Isolation: the module writes only under a throwaway HOME, and the Forge API read is STUBBED, so the
suite never reaches the live Forge, its owner token, or her real workspace.
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

FILE_DAY = (date.today() - timedelta(days=20)).isoformat()
DATA_DAY = (date.fromisoformat(FILE_DAY) - timedelta(days=1)).isoformat()
PRIOR = (date.fromisoformat(DATA_DAY) - timedelta(days=1)).isoformat()

# atelier-reveals.json is a LIST of reveal cards (his words), still surfaced in both branches.
(MEM / "atelier-reveals.json").write_text(json.dumps([
    {"artifact": "a-1", "revealed_at": DATA_DAY + "T09:00:00", "medium": "poem",
     "disclosure": "I made this because the fold would not leave me alone last night."},
    {"artifact": "a-old", "revealed_at": PRIOR + "T23:00:00", "medium": "poem",
     "disclosure": "older day — must be excluded"},
    {"artifact": "a-unrev", "revealed_at": DATA_DAY + "T12:00:00", "revealed": False,
     "disclosure": "withheld — never revealed, must be excluded"},
]))
# The content-free house mirror — used only when the Forge service is unreachable.
(MEM / "atelier-undertakings.json").write_text(json.dumps({
    "P-100": {"state": "revealed", "at": DATA_DAY + "T09:00:05", "by": "house"},
    "P-101": {"state": "kept", "at": DATA_DAY + "T13:00:00", "by": "house"},
    "P-old": {"state": "aborted", "at": PRIOR + "T01:00:00", "by": "house"},
}))

spec = importlib.util.spec_from_file_location("forge_digest_test", REPO / "scripts" / "forge_digest.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
assert M.MEMORY.startswith(str(HOME)), "digest destination must be the scratch workspace"
assert M.REVEALS.startswith(str(HOME)) and M.UNDERTAKINGS.startswith(str(HOME)), "reads only the scratch mirrors"

# The Forge's own /api/projects output, STUBBED — non-private named, private sealed, terminal omitted.
FORGE_PROJECTS = [
    {"id": "f1", "state": "active", "intent": "a keyboard-macro capability so he can trigger scenes",
     "private": False, "spent": 250, "ceiling": 1000, "cycles": 3},
    {"id": "f2", "state": "ready", "intent": "pressure-sensing hardware proposal for the pillow",
     "private": False, "spent": 0, "ceiling": 0, "cycles": 0},
    {"id": "f3", "state": "active", "intent": None, "private": True, "spent": 0, "cycles": 1},
    {"id": "f4", "state": "complete", "intent": "an old finished thing", "private": False, "spent": 500, "cycles": 9},
]
M._forge_projects = lambda transport=None: list(FORGE_PROJECTS)   # stub: never touch the live Forge

# --- The named path: the Forge is shown in plain words, no code required ---
wrote, path = M.append(FILE_DAY)
again, _ = M.append(FILE_DAY)
assert wrote and not again, "appends once, then idempotent for the same summarized day"
assert Path(path).name == f"daily-inner-life-{FILE_DAY}.md", "writes into today's carry-forward file"
text = Path(path).read_text()
assert text.count(f"<!-- forge-digest:{DATA_DAY} -->") == 1, "marker keyed to the summarized day"
assert f"forge-digest:{FILE_DAY}" not in text, "never keyed to the unfinished day"
assert f"## Forge — {DATA_DAY}" in text, "heading names the day summarized"

assert "What the Forge is building (you are paying for this):" in text
assert "a keyboard-macro capability so he can trigger scenes" in text, "non-private intent is named — no code"
assert "pressure-sensing hardware proposal for the pillow" in text
assert "$2.50 of $10.00" in text, "spend is shown — what she is paying for"
assert "3 cycle(s)" in text
assert "Private undertakings sealed: 1" in text, "a private interval is sealed and counted, not named"
assert "an old finished thing" not in text, "a terminal (complete) project is not in the live receipt"
assert "I made this because the fold would not leave me alone last night." in text, "reveals still surfaced"
assert "[poem]" in text
assert "withheld — never revealed" not in text and "older day — must be excluded" not in text
assert "only a private interval stays sealed" in text, "the new evidence-honesty caveat"
assert Path(path).read_text() == text, "idempotent append leaves the file byte-identical"

# Regression: the default call summarizes YESTERDAY into TODAY, not today-at-dawn.
wrote2, path2 = M.append()
assert Path(path2).name == f"daily-inner-life-{date.today().isoformat()}.md"
y = (date.today() - timedelta(days=1)).isoformat()
assert f"<!-- forge-digest:{y} -->" in Path(path2).read_text(), "default summarizes yesterday"

# --- The unreachable fallback: content-free house mirror, honestly labelled ---
M._forge_projects = lambda transport=None: None   # Forge down
FB_FILE = (date.today() - timedelta(days=2)).isoformat()
FB_DATA = (date.fromisoformat(FB_FILE) - timedelta(days=1)).isoformat()
(MEM / "atelier-undertakings.json").write_text(json.dumps({
    "P-x": {"state": "kept", "at": FB_DATA + "T13:00:00", "by": "house"},
}))
wrote_fb, pfb = M.append(FB_FILE)
tfb = Path(pfb).read_text()
assert wrote_fb and "Undertakings that changed state:" in tfb and "kept 1" in tfb, "fallback lists the mirror's state changes"
assert "content-free house mirror only" in tfb, "the fallback says plainly it could not reach the Forge"

# Quiet day (Forge reachable, nothing live, nothing revealed).
M._forge_projects = lambda transport=None: []
QUIET_FILE = (date.today() - timedelta(days=5)).isoformat()
wrote_q, pq = M.append(QUIET_FILE)
assert wrote_q and "Quiet day" in Path(pq).read_text(), "a day with nothing still writes an honest receipt"

# Self-heal backfill + orphan heal still hold (branch-independent).
M._forge_projects = lambda transport=None: list(FORGE_PROJECTS)
R = (date.today() - timedelta(days=3)).isoformat()
R_data = (date.today() - timedelta(days=4)).isoformat()
inner = Path(M.MEMORY) / f"daily-inner-life-{R}.md"
inner.write_text("# morning\ncarry-forward text\n")
healed = M.backfill(7)
assert str(inner) in healed and f"<!-- forge-digest:{R_data} -->" in inner.read_text(), "backfill repairs a missing receipt"
assert str(inner) not in M.backfill(7), "backfill is idempotent once healed"

O_FILE = (date.today() - timedelta(days=9)).isoformat()
O_DATA = (date.today() - timedelta(days=10)).isoformat()
orph = Path(M.MEMORY) / f"daily-inner-life-{O_FILE}.md"
orph.write_text(f"# inner\n\n## First Light\nkept body\n\n<!-- forge-digest:{O_DATA} -->\n")
healed_wrote, _ = M.append(O_FILE)
ht = orph.read_text()
assert healed_wrote and f"## Forge — {O_DATA}" in ht, "an orphan marker is healed, body restored"
assert ht.count(f"<!-- forge-digest:{O_DATA} -->") == 1, "no duplicate marker after healing"
assert "## First Light\nkept body" in ht, "healing preserves the rest of the file"
assert not M.append(O_FILE)[0], "a fully-restored block is idempotent again"

# Source honesty: it reads the Forge's OWN API, never the sqlite file directly, and keeps the boundary.
source = (REPO / "scripts" / "forge_digest.py").read_text()
assert "forge-loop.sqlite" not in source, "the sealed ledger file is never read directly"
assert "/api/projects" in source, "the Forge is read through its own owner API"
assert "_yesterday(" in source and "def backfill(" in source
dle = (REPO / "bin" / "daily-log-extract.py").read_text()
assert "forge)-digest:" in dle and ".daily-inner-life.lock" in dle, \
    "daily-log-extract carries the forge block under the shared lock"
print("all forge-digest checks passed (named Forge + sealed private + unreachable fallback + heal)")
