#!/usr/bin/env python3
"""Causality compaction is bounded and epistemically conservative. Scratch HOME; no senders."""
import os, sys, json, tempfile, importlib.util, subprocess, shutil
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-causal-compact-")
os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
sys.path.insert(0, os.path.join(REPO, "scripts"))

spec = importlib.util.spec_from_file_location("causality_compaction_fixture",
    os.path.join(REPO, "scripts", "causality-engine.py"))
CE = importlib.util.module_from_spec(spec); spec.loader.exec_module(CE)
CE.WORKSPACE = WS; CE.MEMORY = MEM
CE.HYPOTHESIS_DB = os.path.join(MEM, "causality-hypotheses.json")
CE.RETIRED_PATH = os.path.join(MEM, "causality-retired.jsonl")
delivered = []
def _deliver(event_id, event):
    if event_id == "pending-receipt": raise RuntimeError("fixture destination down")
    delivered.append((event_id, event["kind"]))
CE._deliver = _deliver

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)) if detail and not ok else ""))

today = date(2026, 9, 14)
def row(name, age, source="causal-jepa", **extra):
    h = {"hypothesis_id": "CH-" + name, "hypothesis": name,
         "formed": str(today - timedelta(days=age)) + "T01:00:00",
         "formed_date": str(today - timedelta(days=age)), "source": source,
         "status": "held", "marks": []}
    h.update(extra); return h

active = row("active", 1)
active["marks"] = [{"schema_version": CE.CAUSALITY_SCHEMA, "date": str(today-timedelta(days=i)),
                    "verdict": "unconfirmed", "outcome": "unconfirmed"} for i in range(50)]
active["evidence"] = list(range(55)); active["nightly_evaluations"] = list(range(56))
active["history"] = list(range(57)); active["distribution"] = [{"prob": i/20} for i in range(20)]
active["formation"] = {"root_snippets": ["root-%d" % i for i in range(30)],
                       "root_fingerprints": ["F-%d" % i for i in range(30)],
                       "root_evidence_ids": ["E-%d" % i for i in range(30)]}
ordinary = row("ordinary-stale", 8)
ghost_young = row("ghost-young", 8, source="ghost_branch")
ghost_stale = row("ghost-stale", 33, source="ghost_branch")
confirmed = row("confirmed", 80, status="confirmed")
self_known = row("self-known", 80, self_knowledge={"text": "kept"})
db = {"hypotheses": [active, ordinary, ghost_young, ghost_stale, confirmed, self_known],
      "tested": 0, "confirmed": 0, "revised": 0,
      "deliveries": {
          "old-receipt": {"kind": "retired", "payload": {"x": 1}, "state": "delivered"},
          "pending-receipt": {"kind": "retired", "payload": {"x": 2}, "state": "pending"}}}
with open(CE.HYPOTHESIS_DB, "w") as handle: json.dump(db, handle, indent=2)

result = CE.compact_store(today=today)
after = json.load(open(CE.HYPOTHESIS_DB))
by_id = {h["hypothesis_id"]: h for h in after["hypotheses"]}
check("suite writes only beneath scratch HOME", os.path.commonpath([os.path.realpath(CE.HYPOTHESIS_DB), os.path.realpath(HOME)]) == os.path.realpath(HOME))
check("ordinary, legacy-confirmed, and 32-day Ghost evidence-poor rows retire", "CH-ordinary-stale" not in by_id and "CH-ghost-stale" not in by_id and "CH-confirmed" not in by_id and result["retired"] == 3, result)
check("Ghost Branch keeps its 32-day tenure", "CH-ghost-young" in by_id)
check("only graduated self-knowledge bypasses ordinary tenure", "CH-self-known" in by_id)
check("all configured histories are capped", all(len(by_id["CH-active"][k]) <= CE.HISTORY_CAP for k in ("marks", "evidence", "nightly_evaluations", "history")))
check("readable roots cap but anti-self-confirmation lineage stays complete", len(by_id["CH-active"]["formation"]["root_snippets"]) == CE.FORMATION_SNIPPET_CAP and len(by_id["CH-active"]["formation"]["root_fingerprints"]) == 30 and len(by_id["CH-active"]["formation"]["root_evidence_ids"]) == 30)
check("cause distributions are bounded", len(by_id["CH-active"]["distribution"]) == CE.DISTRIBUTION_CAP)
check("delivered outbox rows purge while pending failures survive", "old-receipt" not in after["deliveries"] and after["deliveries"].get("pending-receipt", {}).get("state") == "pending" and len(delivered) == 3, {"deliveries": after["deliveries"], "sent": delivered})
check("compact writer actually shrinks the fixture", result["after_bytes"] < result["before_bytes"], result)

# Realtime formation once lacked the nightly engine's shared daily budget. Historical repair keeps
# the first three ordinary rows for a day, preserves Ghost Branch and settled knowledge, and retires
# only the overflow as neither resolved nor refuted.
same_day = [row("burst-%d" % i, 0) for i in range(7)]
ghost_same_day = row("burst-ghost", 0, source="ghost_branch")
settled_same_day = row("burst-settled", 0, status="confirmed", self_knowledge={"text": "kept"})
budget_db = {"hypotheses": same_day + [ghost_same_day, settled_same_day]}
overflow = CE._retire_formation_overflow(budget_db, daily_cap=3)
check("one shared daily cap retires realtime formation overflow", len(overflow) == 4 and len(budget_db["hypotheses"]) == 5)
check("formation overflow never removes Ghost Branch or settled knowledge",
      ghost_same_day in budget_db["hypotheses"] and settled_same_day in budget_db["hypotheses"])
check("overflow retirement is honest, not a false resolution",
      all(h["retirement"]["reason"] == "daily_formation_cap_exceeded"
          and not h["retirement"]["resolved"] and not h["retirement"]["refuted"] for h in overflow))

# Direct producers share the same budget instead of appending and letting save silently cull the
# new row. Ghost Branch remains the sole explicitly protected formation kind.
actual_today = date.today().isoformat()
direct_budget = [dict(same_day[i], formed=actual_today + "T01:00:0%d" % i,
                      formed_date=actual_today) for i in range(3)]
CE.load_existing_hypotheses = lambda: CE.HypothesisSnapshot({"hypotheses": direct_budget, "deliveries": {}})
check("direct ordinary formation refuses a fourth row for the day",
      CE._add_hypothesis("a fourth ordinary theory", "watch tomorrow", "direct") is None)

fresh = row("fresh-formation", 0)
CE._stamp_formation(fresh, {"seed": "a real new occasion with enough words to fingerprint"})
catalog = CE._catalog_item(str(today), "interaction", "a separate new occasion with enough words to count", 0)
check("formation and nightly testing still operate", fresh["formation"]["root_fingerprints"] and CE._record_nightly(fresh, str(today), "yes", evidence=catalog["text"], items=[catalog]) and fresh["marks"][0]["verdict"] == "yes")

# The production entry is a cross-tree symlink. Exercise that exact shape from
# an unrelated real-file directory with helpers only under scratch workspace.
foreign = os.path.join(HOME, "Vintos"); os.makedirs(foreign, exist_ok=True)
foreign_script = os.path.join(foreign, "causality-engine.py")
shutil.copy2(os.path.join(REPO, "scripts", "causality-engine.py"), foreign_script)
entry = os.path.join(WS, "scripts", "causality-engine.py")
os.makedirs(os.path.dirname(entry), exist_ok=True)
os.symlink(foreign_script, entry)
shutil.copy2(os.path.join(REPO, "scripts", "store_guard.py"), os.path.join(WS, "scripts", "store_guard.py"))
probe = subprocess.run([sys.executable, entry, "--compact"], env={**os.environ, "HOME": HOME},
                       capture_output=True, text=True)
check("deployed cross-tree symlink imports its workspace helper", probe.returncode == 0 and '"after_bytes"' in probe.stdout, {"returncode": probe.returncode, "stderr": probe.stderr})

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
