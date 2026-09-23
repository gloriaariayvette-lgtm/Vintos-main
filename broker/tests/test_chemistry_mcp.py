#!/usr/bin/env python3
"""Bounded MCP Lab route; every store and worker stays in this scratch process."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[2]
HOME = tempfile.mkdtemp(prefix="vintos-chem-mcp-test-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = str(Path(HOME) / "workspace")
os.environ["CHEM_LAB_MCP_PYTHON"] = str(Path(HOME) / "missing-mcp-python")
sys.path.insert(0, str(ROOT / "scripts"))

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

lab = load("chemistry_lab")
mcp = load("chemistry_mcp")
sources = load("chemistry_sources")
assert lab.ROOT.startswith(HOME) and mcp.PYTHON.startswith(HOME)
sequence = "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP"
from lab_sources import receipt
source = receipt("uniprot", {"accession": "P00001"}, {"sequence": sequence})
lab._append(str(Path(lab.ROOT) / "source-receipts.jsonl"), source)
spec = {"tool": "score_stability", "sequence": sequence, "source_receipt_id": source["receipt_id"]}
calls = []

def fake_runner(argv, input_text):
    calls.append((argv, input_text))
    return types.SimpleNamespace(returncode=0, stdout=json.dumps({
        "tool": "score_stability", "content": ['{"score": -2.4}']}))

result = mcp.call(spec, runner=fake_runner)
assert len(calls) == 1 and json.loads(calls[0][1]) == {"sequence": sequence}
assert calls[0][0][0].startswith(HOME) and calls[0][0][1].endswith("chemistry_mcp.py")
assert Path(result["artifact"]).is_file()
assert os.stat(result["artifact"]).st_mode & 0o077 == 0
assert result["source_receipt_ids"] == [source["receipt_id"]]
assert "-2.4" in result["summary"] and "not_experimental_validation" in result["truth_status"]

for bad in (
    dict(spec, tool="design_binder"),
    dict(spec, tool="predict_structure"),
    dict(spec, sequence="BAD"),
    dict(spec, sequence="A" * 161),
    dict(spec, source_receipt_id="0" * 64),
    dict(spec, sequence="A" * len(sequence)),
    dict(spec, predictor="alphafold2"),
):
    try: mcp.call(bad, runner=fake_runner)
    except ValueError: pass
    else: raise AssertionError("unsafe or unsourced query accepted")
assert len(calls) == 1, "invalid queries must never reach the worker"

# Reproduce the installed server's ndarray serialization fault without importing
# its real GPU package or reaching any real provider during a deploy suite.
class FakeArray:
    def tolist(self): return [0.1, 0.2]
fake_server = types.ModuleType("protein_design_mcp.server")
fake_server.json = json
async def fake_call_tool(name, args):
    assert name == "score_stability" and args["sequence"] == sequence
    return [types.SimpleNamespace(text=fake_server.json.dumps({"per_residue_scores": FakeArray()}))]
fake_server.call_tool = fake_call_tool
fake_package = types.ModuleType("protein_design_mcp")
fake_package.server = fake_server
sys.modules["protein_design_mcp"] = fake_package
sys.modules["protein_design_mcp.server"] = fake_server
assert json.loads(mcp._worker("score_stability", {"sequence": sequence})["content"][0])["per_residue_scores"] == [0.1, 0.2]
assert fake_server.json is json, "worker must restore the server module's original serializer"

# The second native route is provenance-bound to an exact PDB identifier and
# cannot turn literature expansion on behind the planner's back.
pdb_source = receipt("uniprot", {"accession": "P00002"},
                     {"crossrefs": [{"database": "PDB", "id": "1CRN"}]})
lab._append(str(Path(lab.ROOT) / "source-receipts.jsonl"), pdb_source)
hotspot = {"tool": "suggest_hotspots", "target": "1CRN", "criteria": "exposed",
           "source_receipt_id": pdb_source["receipt_id"]}
hot = mcp.call(hotspot, runner=lambda argv, body: types.SimpleNamespace(returncode=0, stdout=json.dumps({
    "tool": "suggest_hotspots", "content": ['{"suggested_hotspots":[{"residues":["A7"]}]}']})))
assert hot["source_receipt_ids"] == [pdb_source["receipt_id"]]
for bad_hotspot in (dict(hotspot, target="2BAD"), dict(hotspot, criteria="anything"),
                    dict(hotspot, include_literature=True)):
    try: mcp.call(bad_hotspot, runner=fake_runner)
    except ValueError: pass
    else: raise AssertionError("unsourced or widened hotspot query accepted")

# Hosted mappings retain the same source rule but delegate to the already capped
# NVIDIA gateway. No provider, key, network or real ledger is reached in this test.
hosted_calls=[]
fake_bionemo=types.ModuleType("bionemo_gateway")
def hosted_call(*args, **kwargs):
    hosted_calls.append((args,kwargs))
    return {"receipt":{"receipt_id":"b"*64,"result_sha256":"c"*64,
                       "artifact":str(Path(HOME)/"hosted.json")},"summary":"mmCIF kept"}
fake_bionemo.call=hosted_call
sys.modules["bionemo_gateway"]=fake_bionemo
fold=mcp.call({"tool":"predict_structure_boltz","sequence":sequence,
               "source_receipt_id":source["receipt_id"]})
assert fold["backend_receipt_id"] == "b"*64 and len(hosted_calls)==1
assert hosted_calls[0][0][2] == "nvidia_nim.boltz2"
assert hosted_calls[0][0][3]["polymers"][0]["sequence"] == sequence
complex_result=mcp.call({"tool":"predict_complex","sequences":[sequence,sequence],
                         "source_receipt_ids":[source["receipt_id"]]})
assert complex_result["backend_receipt_id"] == "b"*64 and len(hosted_calls)==2
assert len(hosted_calls[1][0][3]["polymers"]) == 2
assert len(mcp.capabilities()) == 19
assert mcp.capabilities()["rosetta_score"]["state"] == "unavailable"

original = mcp.call
mcp.call = lambda value: original(value, runner=fake_runner)
linked = sources.query_protein_design_mcp(spec)
assert linked["instrument_receipt"]["source"] == "protein_design_mcp"
assert linked["instrument_receipt"]["metadata"]["artifact"].startswith(HOME)
assert linked["instrument_result"]["result_sha256"] == result["result_sha256"]
assert len(lab._jsonl(str(Path(lab.ROOT) / "source-receipts.jsonl"))) == 3

import chemistry_probe as probe
probe.AEGIS_PROBES = {}
probe.probe_aegis = lambda name: (_ for _ in ()).throw(AssertionError("real probe reached"))
assert probe.PROBES.startswith(HOME)
assert probe.probe_aegis.__name__ == "<lambda>"
session = load("chemistry_session")
session._frontier = lambda *args, **kwargs: None
import asyncio
async def fake_frontier(*args, **kwargs):
    prompt = args[2]
    assert "AVAILABLE NAMED EXPERIMENTS" in prompt
    if "Protein-design orchestrator" in prompt:
        assert "score_stability" in prompt and "suggest_hotspots" in prompt and "predict_complex" in prompt
    return json.dumps({"experiment": "fold", "parameters": {}, "shots": 512,
                       "question": "What does this score suggest?", "why_this": "sourced sequence",
                       "instrument_query": spec})
session._frontier = fake_frontier
plan = session._plan("Sourced accession P00001.", ["fold"], "claude",
                     {"protein_design_mcp": {"available": True, "state": "measured"}})
assert plan["instrument_query"] == spec
assert plan["source_query"] is None and plan["plugin_query"] is None
plan_off = session._plan("Sourced accession P00001.", ["fold"], "claude",
                         {"protein_design_mcp": {"available": False, "state": "not_measured"}})
assert plan_off["instrument_query"] is None
print("PASS bounded MCP source, receipt, planner route, worker and store isolation")
