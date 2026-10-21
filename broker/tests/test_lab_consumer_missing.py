#!/usr/bin/env python3
"""A tick with lab_forge_consumer absent does its ordinary work and does not fault (SK-6e3a0436).
Scratch HOME only; no model or network."""
import contextlib
import importlib.util
import json
import os
os.environ["VINTOS_LAB_CAMPAIGNS"] = "0"   # this suite tests the ordinary loop; test_lab_campaign tests campaigns
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-consumer-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos.")
open(os.path.join(WS, "SELF-MODEL.md"), "w").write("I return to shapes.")
json.dump({"heading": "learning by making"}, open(os.path.join(WS, "memory", "living-trajectory.json"), "w"))

# Nothing sends, nothing reaches the network: the Lab's one door is stubbed, and so is its model call.
NET_CALLS = []
def _no_network(*a, **k):
    NET_CALLS.append(a[:1]); raise AssertionError("this suite must never reach the network")
sys.modules["lab_http"] = types.SimpleNamespace(open_request=_no_network)
sys.modules["chemistry_sources"] = types.SimpleNamespace(flush_reports=lambda *a, **k: None, query=_no_network)
# The consumer is made unimportable, as on a host where the deploy never landed it.
sys.modules["lab_forge_consumer"] = None
spec = importlib.util.spec_from_file_location("chemistry_lab_consumer_test", os.path.join(REPO, "scripts", "chemistry_lab.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
sys.modules["chemistry_lab"] = M
M.urllib.request.urlopen = _no_network

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:180]) if detail and not ok else ""))

check("every path the Lab writes is in the scratch workspace",
      M.WS == WS and all(p.startswith(HOME) for p in (M.ROOT, M.CONFIG, M.STATE, M.NOTEBOOK, M.FAULTS, M.RECEIPTS)), M.ROOT)
check("the consumer import is blocked for this suite", sys.modules.get("lab_forge_consumer") is None)

@contextlib.contextmanager
def admitted(*a, **k): yield types.SimpleNamespace()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
M._ensure()
json.dump({"enabled": True, "forge_report_intake": {"url": "http://127.0.0.1:8612/api/lab-intake"}}, open(M.CONFIG, "w"))
M.set_enabled(True)
M._orient = lambda context: {"uniprot_query": "reviewed:true AND length:[40 TO 350]", "question": "Which compact fold catches me?", "why_now": "shape"}
M._browse = lambda query, limit: {"records": [], "requested_query": query, "executed_query": query, "fallback_reason": None}
M._ask = _no_network

first = M.tick(); second = M.tick()
faults = [json.loads(x) for x in open(M.FAULTS) if x.strip()] if os.path.exists(M.FAULTS) else []
notes = [json.loads(x) for x in open(M.NOTEBOOK) if x.strip()]
check("the tick does its ordinary orient work without the consumer", first.get("kind") == "inquiry", first)
check("no ModuleNotFoundError reaches the fault log",
      not any("ModuleNotFoundError" in json.dumps(f) or "lab_forge_consumer" in json.dumps(f) for f in faults), faults)
missing = [n for n in notes if n.get("kind") == "forge_handback_unavailable"]
check("the missing consumer is written down once, not once per tick", len(missing) == 1 and "lab_forge_consumer" in missing[0].get("reason", ""), missing)
check("the second tick still works", second.get("kind") not in (None, "held_fault") and second.get("state") != "held_fault", second)
check("nothing reached the network", NET_CALLS == [], NET_CALLS)
print("\n%d/%d passed" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
