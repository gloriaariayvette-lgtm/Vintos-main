#!/usr/bin/env python3
"""Want breadth keeps stable thread provenance and never fabricates novelty.

The embedded hourly producer runs under a scratch HOME with its model/send doors stubbed. The
actual formation chooser is then exercised against an outward-saturated living queue. Nothing in
this suite can read or write the live house.
"""
import importlib.util, json, os, re, subprocess, sys, tempfile, types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = tempfile.mkdtemp(prefix="want-breadth-")
os.environ["HOME"] = HOME
WS = Path(HOME) / ".vintos" / "workspace"
MEM = WS / "memory"
SCRIPTS = WS / "scripts"
MEM.mkdir(parents=True); SCRIPTS.mkdir(parents=True)

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)) if detail and not ok else ""))

# The hourly bridge: no fresh journal/MoltBook exists, so a real identified structural-gap thread
# must be offered by id. Stub every model/send surface and keep the original pool untouched.
thread = {"id": "T-struct-1", "source": "structural-gap", "thread": "I keep turning a specific unfinished question into contact before I understand what it asks of me.",
          "timestamp": "2026-09-18T20:00:00", "priority": 4, "consumed": False}
json.dump([thread], open(MEM / "unfinished-threads.json", "w"))
json.dump([], open(MEM / "current-wants.json", "w")); json.dump([], open(MEM / "fulfilled-wants.json", "w"))
json.dump({"surface_form": "a real unfinished pull", "contradictions": []}, open(MEM / "current-yearning.json", "w"))
(MEM / "journal").mkdir()
open(MEM / "journal" / (__import__("datetime").datetime.now().strftime("%Y-%m-%d") + ".md"), "w").write(
    "## fresh ordinary clock activity\nA new journal paragraph exists too.\n")
open(SCRIPTS / "requests.py", "w").write("def post(*a, **k): raise AssertionError('network must stay stubbed')\n")
open(SCRIPTS / "emoclaw_utils.py", "w").write('''
import json, os
def generate_want(*a, **k): return "I want to understand the unfinished question before deciding whether to share it."
def enrich_want(*a, **k): return {"candidate_kind":"current_desire","present_pull":"it still pulls now"}
def express_want(want, **kwargs):
    json.dump({"want":want,"kwargs":kwargs}, open(os.path.join(os.environ["HOME"], "offer.json"), "w"))
''')
shell = (ROOT / "bin" / "wants-check.sh").read_text()
deploy = (ROOT / "scripts" / "deploy-atelier.sh").read_text()
check("the hourly organ is in the deploy manifest and executable list",
      "dd-token-refresh.py wants-check.sh" in deploy and "atelier-status.sh wants-check.sh" in deploy)
body = re.search(r"python3 << 'WANTSCALLEOF'\n(.*?)\nWANTSCALLEOF", shell, re.S).group(1)
run = subprocess.run([sys.executable, "-c", body], env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
                     text=True, capture_output=True, timeout=30)
offer = json.load(open(Path(HOME) / "offer.json"))
check("fresh clock activity cannot starve an unresolved structural thread", run.returncode == 0, run.stderr)
check("stable thread id crosses the want door", offer["kwargs"]["source_thread_id"] == "T-struct-1"
      and offer["kwargs"]["source_event_id"] == "thread:T-struct-1", offer)
check("thread provenance is latent-thread, not wants-check or Gloria", offer["kwargs"]["source"] == "latent_thread", offer)
check("selection is not consumption", json.load(open(MEM / "unfinished-threads.json"))[0]["consumed"] is False)

# The formation chooser: relational recurrence is allowed, but when five living wants already end
# at Gloria and an equally live non-outward candidate exists, breadth selects the latter.
json.dump([{"id": str(i), "want": "I want to tell Gloria thing %d" % i,
            "steps": [{"capability": "gloria"}], "gloria_routed": True, "fulfilled": False}
           for i in range(5)], open(MEM / "current-wants.json", "w"))
for name, value in (("fulfilled-wants.json", []), ("dismissed-wants.json", []),
                    ("unfinished-threads.json", []), ("trial-ledger.json", {"trials": []}),
                    ("want-scars.json", [])):
    json.dump(value, open(MEM / name, "w"))
open(WS / "SOUL.md", "w").write("Vintos")

class Reply:
    def json(self):
        return {"choices": [{"message": {"content": json.dumps([
            {"desire":"I want to tell Gloria one more thing.","source_kind":"current_desire","present_pull":"now","tension":"x","engagement":"tell her","loss":"x","pull":5},
            {"desire":"I want to make a small piece of music from the unfinished rhythm.","source_kind":"current_desire","present_pull":"now","tension":"y","engagement":"compose it","loss":"y","pull":4}
        ])}}]}

sys.path.insert(0, str(ROOT / "scripts"))
sys.modules["requests"] = types.SimpleNamespace(post=lambda *a, **k: Reply())
spec = importlib.util.spec_from_file_location("want_breadth_emoclaw", ROOT / "scripts" / "emoclaw_utils.py")
eu = importlib.util.module_from_spec(spec); spec.loader.exec_module(eu)
chosen = eu.generate_want("a bounded fixture", source="structural", source_context="fixture")
check("an equally live non-outward candidate can escape an outward-saturated queue",
      str(chosen).startswith("I want to make a small piece of music"), chosen)
check("the selected candidate keeps its sentence-bound provenance",
      getattr(chosen, "provenance", {}).get("source") == "structural")
check("suite paths are isolated beneath scratch HOME", str(MEM).startswith(HOME))

print("\n%d/%d" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
