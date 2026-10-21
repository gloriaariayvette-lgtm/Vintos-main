#!/usr/bin/env python3
"""A saved sourced record already reviewed (or gone) when its turn runs is a refusal, not a fault (F-f102059463,
20 October: Q67BT3 was reviewed at 07:18 UTC and a later orient pass handed it on at 07:21, faulting the whole turn).
Scratch HOME, set before the Lab is imported; no model, no network, nothing sent."""

# Legacy phase regressions; chained autonomous turns have their own isolated suite.
import sys as _legacy_sys, types as _legacy_types
_legacy_sys.modules["lab_investigations"] = _legacy_types.SimpleNamespace(turn=lambda *a, **k: None)
import contextlib
import importlib.util
import json
import os
os.environ["VINTOS_LAB_CAMPAIGNS"] = "0"   # this suite tests the ordinary loop; test_lab_campaign tests campaigns
import socket
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-sourced-reviewed-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS

NET_CALLS = []
def _no_network(*a, **k):
    NET_CALLS.append(a[:1]); raise AssertionError("this suite must never reach the network or a process")
socket.socket.connect = _no_network
socket.create_connection = _no_network
subprocess.Popen = _no_network
sys.modules["lab_http"] = types.SimpleNamespace(open_request=_no_network)
sys.modules["chemistry_sources"] = types.SimpleNamespace(flush_reports=lambda *a, **k: None, query=_no_network)
sys.modules["lab_forge_consumer"] = types.SimpleNamespace(consume_one=lambda *a, **k: None)
sys.modules["atelier_lab_lean"] = types.SimpleNamespace(today=lambda: None)
@contextlib.contextmanager
def admitted(*a, **k): yield types.SimpleNamespace()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
spec = importlib.util.spec_from_file_location("chemistry_lab_sourced_test", os.path.join(REPO, "scripts", "chemistry_lab.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
sys.modules["chemistry_lab"] = M
M.urllib.request.urlopen = _no_network
M._ask = _no_network

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:200]) if detail and not ok else ""))

INDEX = os.path.join(M.ROOT, "sourced-record-index.json")
check("every path the Lab writes is in the scratch workspace, the record index and set-aside list included",
      all(p.startswith(HOME) for p in (M.ROOT, M.CONFIG, M.STATE, M.NOTEBOOK, M.FAULTS, M.SOURCED_SET_ASIDE, INDEX)))

M._ensure()
json.dump({"enabled": True}, open(M.CONFIG, "w"))
M.set_enabled(True)

def record(acc, name):
    return {"accession": acc, "protein_name": name, "organism": "Homo sapiens"}

def assigned(acc):
    return {"browse_lane": "protein", "uniprot_query": "accession:" + acc,
            "question": "What do curated UniProt records for %s establish?" % acc, "why_now": "test",
            "assignment_resolution": {"reason": "exact_previously_sourced_record", "accession": acc}}

def rows(path):
    return [json.loads(x) for x in open(path) if x.strip()] if os.path.exists(path) else []

def turn(acc):
    """One tick whose orient hands over the saved record `acc`; what it returned, wrote and left behind."""
    json.dump({"phase": "orient"}, open(M.STATE, "w"))
    faults_before, notes_before = len(rows(M.FAULTS)), len(rows(M.NOTEBOOK))
    M._orient = lambda context, lean=None: assigned(acc)
    out = M.tick()
    return (out, M._load(M.STATE, {}), rows(M.FAULTS)[faults_before:], rows(M.NOTEBOOK)[notes_before:],
            acc in (M._load(M.SOURCED_SET_ASIDE, []) or []))

M._append(M.NOTEBOOK, {"kind": "source_read", "source": "UniProtKB REST",
                       "records": [record("Q67BT3", "Reviewed protein"), record("P02792", "Ferritin light chain")]})
M._append(M.NOTEBOOK, {"kind": "reflection", "source_accessions": ["Q67BT3"], "factual_observation": "already reviewed"})

print("\n--- a record already reviewed when its turn runs ---")
out, state, faults, notes, aside = turn("Q67BT3")
check("the tick completes, not held_fault", out.get("state") == "completed" and state.get("effective_state") != "held_fault", out)
check("no tick fault is written", not faults, faults)
check("the phase stays orient and the inquiry is cleared", state.get("phase") == "orient" and "inquiry" not in state, state)
check("an inquiry_refused note names the accession",
      any(n.get("kind") == "inquiry_refused" and "Q67BT3" in str(n.get("why")) for n in notes), notes)
check("the accession is set aside", aside)

print("\n--- a record never in the index ---")
out, state, faults, notes, aside = turn("Q9ZZZ9")
check("the tick completes without a fault", out.get("state") == "completed" and not faults, (out, faults))
check("the phase stays orient and the inquiry is cleared", state.get("phase") == "orient" and "inquiry" not in state, state)
check("an inquiry_refused note names it, and it is set aside",
      aside and any(n.get("kind") == "inquiry_refused" and "Q9ZZZ9" in str(n.get("why")) for n in notes), notes)

print("\n--- an unreviewed saved record is unchanged ---")
out, state, faults, notes, aside = turn("P02792")
check("it goes to reflect with its own record",
      out.get("next_phase") == "reflect" and [r.get("accession") for r in state.get("records") or []] == ["P02792"], (out, state.get("records")))
check("no fault, no refusal, not set aside",
      not faults and not any(n.get("kind") == "inquiry_refused" for n in notes) and not aside, (faults, notes))

print("\n--- the selector skips what is set aside ---")
M._append(M.NOTEBOOK, {"kind": "source_read", "source": "UniProtKB REST",
                       "records": [record("O15111", "Set-aside protein"), record("P55957", "Next protein")]})
M._set_aside_sourced("O15111")
M._set_aside_sourced("P02792")
real = (M._inquiry, M._held_question, M.spent_retrieval)
M._inquiry = lambda value, lean=None: dict(value)
M._held_question = lambda inquiry: False
M.spent_retrieval = lambda inquiry, spent: False
try:
    picked = M._next_sourced_record(None, {"subjects": []})
finally:
    M._inquiry, M._held_question, M.spent_retrieval = real
check("a set-aside accession is never picked; the next unreviewed one is",
      (picked or {}).get("assignment_resolution", {}).get("accession") == "P55957", picked)

check("nothing reached the network or a process", NET_CALLS == [], NET_CALLS)
print("\n%d/%d passed" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
