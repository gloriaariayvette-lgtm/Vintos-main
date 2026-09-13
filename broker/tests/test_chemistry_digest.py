#!/usr/bin/env python3
"""Chemistry digest: scratch HOME, mechanical rows, one marked append."""
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

DAY = "2026-09-13"
def rows(name, values):
    with open(LAB / name, "w") as handle:
        for value in values: handle.write(json.dumps(value) + "\n")

rows("notebook.jsonl", [
    {"at": DAY + "T01:00:00Z", "kind": "inquiry", "next_question": "which fold returns?"},
    {"at": DAY + "T02:00:00Z", "kind": "owed_reading", "reading": {"next_question": "what changes at 0.8 A?"}},
    {"at": "2026-09-12T23:00:00Z", "kind": "atelier-secret"},
])
rows("sessions.jsonl", [
    {"at": DAY + "T02:00:00Z", "state": "completed", "mac_run_id": "RUN-1",
     "plan": {"experiment": "molecule"},
     "grade": {"execution_state": "completed", "aggregate_accuracy": "ALL_WORSE_THAN_HARTREE_FOCK"}},
    {"at": DAY + "T03:00:00Z", "state": "held_reading_owed", "owed_reading": "STILL_HELD"},
])
rows("experiment-grades.jsonl", [{"at": DAY + "T02:00:01Z", "run_id": "RUN-1",
                                   "experiment": "molecule", "execution_state": "completed",
                                   "aggregate_accuracy": "ALL_WORSE_THAN_HARTREE_FOCK"}])

spec = importlib.util.spec_from_file_location("chemistry_digest_test", REPO / "scripts" / "chemistry_digest.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
assert M.MEMORY.startswith(str(HOME)) and M.LAB.startswith(str(HOME))
wrote, path = M.append(DAY)
assert wrote and Path(path).is_relative_to(HOME)
text = Path(path).read_text()
assert text.count("<!-- chemistry-lab-digest:%s -->" % DAY) == 1
assert "inquiry 1" in text and "owed_reading 1" in text
assert "execution=completed; accuracy=ALL_WORSE_THAN_HARTREE_FOCK; run=RUN-1" in text
assert "owed/held 1; settled 1" in text and "what changes at 0.8 A?" in text
assert "atelier-secret" not in text and "Execution is not correctness" in text
again, _ = M.append(DAY)
assert not again and Path(path).read_text() == text
source = (REPO / "scripts" / "chemistry_digest.py").read_text()
assert "memory/atelier" not in source and "atelier-reveals" not in source
print("12/12 passed")
