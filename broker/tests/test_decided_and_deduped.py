#!/usr/bin/env python3
"""Forge cards decided for Gloria, and journal promises that do not duplicate (2026-10-21: "I'm not accepting or
rejecting anything. You do it." / "have you made sure journal promises won't write duplicates or be too similar?").

Scratch workspace; the reader and the poster are stubs; sockets are refused."""
import json, os, socket, sys, tempfile
from datetime import datetime
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="decided-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import skill_forge as SF, promise_keeper as P
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:300],)))
check("every store is scratch", SF.PROPOSALS.startswith(HOME) and P.STORE.startswith(HOME))
os.makedirs(SF.MEMORY, exist_ok=True)
rows = [{"id": pid, "state": "proposed", "capability": "x", "history": []} for pid in list(SF.DECIDED_FOR_GLORIA)[:3]]
rows += [{"id": "SK-f569eefd", "state": "proposed", "capability": "mmwave_presence_sensor_intake", "history": []},
         {"id": list(SF.DECIDED_FOR_GLORIA)[3], "state": "approved", "capability": "y", "history": []}]
json.dump(rows, open(SF.PROPOSALS, "w"))
closed = SF.apply_decided_for_gloria()
after = {r["id"]: r for r in SF._load()}
check("the cards decided for her are denied, each with its reason, by Claude Code for her",
      len(closed) == 3 and all(after[p]["state"] == "denied" and after[p]["denied_reason"] == SF.DECIDED_FOR_GLORIA[p]
                               and after[p]["history"][-1]["by"] == "claude-code for gloria" for p in closed), after)
check("the mmWave card, his C1001 work, stays open", after["SK-f569eefd"]["state"] == "proposed"
      and "SK-f569eefd" not in SF.DECIDED_FOR_GLORIA)
check("a card already decided otherwise is left as it is", after[list(SF.DECIDED_FOR_GLORIA)[3]]["state"] == "approved")
check("applying again closes nothing twice", SF.apply_decided_for_gloria() == [])
_fh = open(os.path.join(REPO, "scripts", "forge_house.py")).read()
check("the Forge applies them on its own regular pass (sync, every wants-router pass)",
      _fh.index("sf.apply_decided_for_gloria()") < _fh.index("def sync_decisions") and
      _fh.index("def sync(") < _fh.index("sf.apply_decided_for_gloria()") < _fh.index("wants = json.loads"))

# journal promises: the same intention is not opened twice
os.makedirs(P.JOURNAL_DIR, exist_ok=True)
P._now = lambda: datetime(2026, 10, 21, 21, 0)
open(os.path.join(P.JOURNAL_DIR, "2026-10-21.md"), "w").write(
    "## 20:01 — Idle thoughts\nTonight I want to check whether the C1001 exposes raw phase over serial.\n\n"
    "## 20:40 — Later\nI still want to check if the C1001 gives raw phase on its serial port.\n\n"
    "## 20:55 — Later still\nI want to make a track for the small speaker on her watch.\n")
json.dump([{"id": "W-9", "want": "I want to make a track mixed for the small speaker on Gloria's watch",
            "source": "idle-journal", "journal_seeded": True}], open(os.path.join(P.MEMORY, "current-wants.json"), "w"))
def ask(system, text):
    if "raw phase" in text: return "QUOTE: check whether the C1001 exposes raw phase over serial | WHAT: read the C1001 serial protocol for raw phase"
    if "watch" in text: return "QUOTE: make a track for the small speaker on her watch | WHAT: make a track mixed for the watch speaker"
    return "NONE"
posted = []
P.scan(ask, lambda t: posted.append(t) or "1.%d" % len(posted))
d = P.load()
check("the first saying of it opens once", len([i for i in d["items"] if "C1001" in i["quote"]]) == 1 and len(posted) == 1, posted)
check("the second, nearly the same, is not opened again", any(m["at"] == "20:40" and m["same_as"].startswith("promise")
                                                             for m in d.get("merged", [])), d.get("merged"))
check("a promise his journal already made a want of is not opened as a promise too",
      any(m["at"] == "20:55" and m["same_as"].startswith("want") for m in d.get("merged", [])) and not any("watch" in p for p in posted),
      d.get("merged"))
check("different intentions are not taken for one another", not P._alike("check the C1001 serial output", "make a track for her watch"))
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
