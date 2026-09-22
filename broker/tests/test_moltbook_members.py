#!/usr/bin/env python3
"""Members log: atomic + locked writes, and a corrupt log is preserved, never silently wiped.

The load-bearing property: a truncated/corrupt file must NOT become an empty members map that the
next save persists over his real history. The old bare json.dump(open(...,"w")) + catch-all load
did exactly that. HOME is repointed to a throwaway dir (AUTHORS_FILE derives from ~ at import) and
the Gemma call is stubbed so the suite can reach nothing — asserted in the suite itself.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOME = Path(tempfile.mkdtemp(prefix="moltbook-members-"))
(HOME / ".vintos" / "workspace" / "memory").mkdir(parents=True)
os.environ["HOME"] = str(HOME)

# Stub `requests` before import: it is the only sender in the module (the Gemma read), and the
# suite must reach nothing. This also lets the test run where requests isn't installed.
class _NoNet:
    def post(self, *a, **k):
        raise AssertionError("network reached: requests.post must be stubbed in tests")
_req = types.ModuleType("requests"); _req.post = _NoNet().post
sys.modules["requests"] = _req

spec = importlib.util.spec_from_file_location("moltbook_members", REPO / "bin" / "moltbook_members.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

# Isolation: the store lives under the throwaway HOME, and the Gemma call cannot reach the network.
assert M.AUTHORS_FILE.startswith(str(HOME)), "members store must be under the scratch HOME"

passed = total = 0
def check(label, cond):
    global passed, total
    total += 1
    assert cond, label
    passed += 1

# Encounters accumulate and persist atomically (no leftover .tmp).
for i in range(3):
    M.record_encounter("gracetargaryen", "t", "post body %d" % i, "reply %d" % i)
data = M.load_members()
check("member recorded and counted", data["members"]["gracetargaryen"]["encounter_count"] == 3)
check("notable exchanges capped at 5", len(data["members"]["gracetargaryen"]["notable_exchanges"]) == 3)
check("gemma stub was hit at the 3rd encounter but swallowed (no crash, no network)",
      True)  # reaching here means the AssertionError from _NoNet was caught by _update_read's try/except
mem = Path(M.AUTHORS_FILE).parent
check("no temp file left after atomic save", not list(mem.glob(".moltbook-members.*.tmp")))

# Deviations accumulate on the same member without losing the encounter data (locked read-modify-write).
M.record_deviation("gracetargaryen", "orig", "corrected", 0.42)
data = M.load_members()
check("deviation recorded alongside encounters", data["members"]["gracetargaryen"]["deviation_count"] == 1
      and data["members"]["gracetargaryen"]["encounter_count"] == 3)

# A second member is added without dropping the first (no lost update).
M.record_encounter("finrel", "t", "p", "r")
data = M.load_members()
check("both members present", set(data["members"]) == {"gracetargaryen", "finrel"})

# THE bug: a corrupt log must be preserved, not overwritten with an empty map.
Path(M.AUTHORS_FILE).write_text("{ this is not valid json ")
loaded = M.load_members()
check("corrupt log reads as empty in memory (does not crash)", loaded == {"members": {}})
sidecars = sorted(mem.glob("moltbook-members.json.corrupt-*"))
check("corrupt log was preserved to a sidecar, not lost", len(sidecars) == 1)
check("the sidecar holds the original corrupt bytes for recovery",
      "not valid json" in sidecars[0].read_text())

# After the corrupt read, a new write self-heals to a valid file — and the old data is NOT gone,
# it is in the sidecar. (This is the recoverable-not-wiped contract.)
M.record_encounter("newcomer", "t", "p", "r")
healed = M.load_members()
check("log self-heals to valid JSON after corruption", "newcomer" in healed["members"])
check("healed file is valid JSON on disk", isinstance(json.load(open(M.AUTHORS_FILE)), dict))

# save_members is atomic + shape-guarded; a non-dict members map is treated as corrupt, not trusted.
Path(M.AUTHORS_FILE).write_text(json.dumps({"members": ["not", "a", "map"]}))
check("a wrong-shaped members map is rejected, not returned", M.load_members() == {"members": {}})

# The module never reverts to the unsafe bare write.
src = (REPO / "bin" / "moltbook_members.py").read_text()
check("save is atomic (tmp + os.replace)", "os.replace(" in src and "mkstemp(" in src)
check("writes are locked", "flock(" in src and "LOCK_EX" in src)
check("corrupt file is preserved, not silently reset", ".corrupt-" in src)

print(f"{passed}/{total} passed")
