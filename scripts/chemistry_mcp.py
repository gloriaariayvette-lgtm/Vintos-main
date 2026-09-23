#!/usr/bin/env python3
"""Bounded Lab doorway to the installed protein-design MCP server.

The package advertises nineteen names, but several wrappers depend on runtimes not
installed in its venv. This module is the house authority: it exposes only proved
native calls and explicit mappings to already-commissioned house backends.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path: sys.path.insert(0, HERE)
import chemistry_lab as lab

PYTHON = os.environ.get("CHEM_LAB_MCP_PYTHON", os.path.expanduser("~/.vintos/tools/chemistry-lab/mcp/bin/python"))
NATIVE_TOOLS = frozenset(("score_stability", "suggest_hotspots"))
HOSTED_TOOLS = frozenset(("predict_structure_boltz", "predict_complex"))
TOOLS = NATIVE_TOOLS | HOSTED_TOOLS
AA = re.compile(r"[ACDEFGHIKLMNPQRSTVWY]{20,160}\Z")
RECEIPT_ID = re.compile(r"[0-9a-f]{64}\Z")
PDB_ID = re.compile(r"[0-9][A-Za-z0-9]{3}\Z")
TIMEOUT = 180
MAX_OUTPUT = 128 * 1024


def instructions():
    return ("Protein-design orchestrator (one instrument_query maximum): "
            "{tool:score_stability,sequence:20..160 amino acids,source_receipt_id}; "
            "{tool:suggest_hotspots,target:exact sourced PDB ID,criteria:exposed|conserved|druggable,source_receipt_id}; "
            "{tool:predict_structure_boltz,sequence:20..160 amino acids,source_receipt_id}; or "
            "{tool:predict_complex,sequences:[2..4 sourced protein sequences],source_receipt_ids:[matching receipts]}. "
            "Score and hotspot calls are local MCP operations. Boltz calls use the hosted NVIDIA route and its "
            "six-attempt daily cap. Predictions and hotspot suggestions are not experimental validation. "
            "Unproved package wrappers are excluded from this menu; the separate Lab ESMFold, ProteinMPNN, "
            "RFD3 and OpenMM instruments remain available through their commissioned Lab paths.")


def capabilities():
    """All nineteen advertised names, with an honest route or exact boundary."""
    available = {
        "score_stability": ("available", "native MCP; NumPy result adapted in worker"),
        "suggest_hotspots": ("available", "native MCP; sourced public PDB ID only, no literature expansion"),
        "predict_structure_boltz": ("available", "mapped to capped hosted NVIDIA Boltz-2"),
        "predict_complex": ("available", "mapped to capped hosted NVIDIA Boltz-2"),
        "predict_structure": ("use_house_instrument", "use commissioned Lab ESMFold; MCP wrapper fails in its venv"),
        "design_sequence": ("use_house_instrument", "use commissioned ProteinMPNN; artifact handoff not yet bounded here"),
        "generate_backbone": ("use_house_instrument", "use commissioned RFD3 or capped hosted RFdiffusion"),
        "energy_minimize": ("use_house_instrument", "use commissioned OpenMM; MCP venv lacks OpenMM"),
        "get_design_status": ("inactive", "no orchestrator-launched asynchronous MCP jobs"),
        "predict_affinity_boltz": ("inactive", "package semantics do not map to the commissioned ligand-affinity endpoint"),
        "validate_design": ("inactive", "depends on the broken MCP structure wrapper"),
        "analyze_interface": ("inactive", "requires a provenance-bound complex artifact handoff"),
        "optimize_sequence": ("inactive", "requires a provenance-bound target structure and design policy"),
        "design_binder": ("inactive", "unproved composite; RFdiffusion, ProteinMPNN and validation handoffs"),
        "design_fold": ("inactive", "unproved composite; three separately governed stages"),
        "rosetta_score": ("unavailable", "PyRosetta absent"),
        "rosetta_relax": ("unavailable", "PyRosetta absent"),
        "rosetta_interface_score": ("unavailable", "PyRosetta absent"),
        "rosetta_design": ("unavailable", "PyRosetta absent"),
    }
    return {name: {"state": state, "reason": reason} for name, (state, reason) in available.items()}


def _source(rid):
    if not isinstance(rid, str) or not RECEIPT_ID.fullmatch(rid):
        raise ValueError("source receipt id required")
    rows = lab._jsonl(os.path.join(lab.ROOT, "source-receipts.jsonl"))
    row = next((item for item in reversed(rows) if item.get("receipt_id") == rid), None)
    if not row: raise ValueError("unknown source receipt")
    return row


def _validated(spec):
    if not isinstance(spec, dict) or spec.get("tool") not in TOOLS:
        raise ValueError("unsupported protein-design operation")
    tool = spec["tool"]
    if tool in ("score_stability", "predict_structure_boltz"):
        if set(spec) != {"tool", "sequence", "source_receipt_id"}:
            raise ValueError("sequence operation requires exact tool, sequence and source receipt")
        sequence, rid = spec["sequence"], spec["source_receipt_id"]
        source = _source(rid)
        if not isinstance(sequence, str) or not AA.fullmatch(sequence) or sequence not in json.dumps(source.get("records", {})):
            raise ValueError("exact bounded sequence absent from the named source receipt")
        return tool, {"sequence": sequence}, [rid]
    if tool == "suggest_hotspots":
        if set(spec) != {"tool", "target", "criteria", "source_receipt_id"}:
            raise ValueError("hotspot operation requires exact target, criteria and source receipt")
        target, criteria, rid = spec["target"], spec["criteria"], spec["source_receipt_id"]
        source = _source(rid)
        if not isinstance(target, str) or not PDB_ID.fullmatch(target) or target not in json.dumps(source):
            raise ValueError("exact PDB target absent from the named source receipt")
        if criteria not in ("exposed", "conserved", "druggable"):
            raise ValueError("unsupported hotspot criteria")
        return tool, {"target": target, "criteria": criteria, "include_literature": False}, [rid]
    if set(spec) != {"tool", "sequences", "source_receipt_ids"}:
        raise ValueError("complex prediction requires exact sequences and source receipts")
    sequences, rids = spec["sequences"], spec["source_receipt_ids"]
    if not isinstance(sequences, list) or not 2 <= len(sequences) <= 4 or any(not isinstance(x, str) or not AA.fullmatch(x) for x in sequences):
        raise ValueError("2..4 bounded protein sequences required")
    if not isinstance(rids, list) or not 1 <= len(rids) <= 4:
        raise ValueError("1..4 source receipt ids required")
    sources = [_source(rid) for rid in rids]
    blob = json.dumps([row.get("records", {}) for row in sources])
    if any(sequence not in blob for sequence in sequences):
        raise ValueError("each sequence must occur in the named source receipts")
    return tool, {"sequences": sequences}, rids


def _worker(tool, arguments):
    import protein_design_mcp.server as server
    # This installed MCP release returns numpy arrays from score_stability, then
    # calls plain json.dumps on the result. Keep the compatibility fix scoped to
    # this disposable worker process; never edit the installed package in place.
    def native(value):
        if hasattr(value, "tolist"): return value.tolist()
        if hasattr(value, "item"): return value.item()
        raise TypeError("MCP result contains an unsupported value")
    original_json = server.json
    proxy = types.ModuleType("mcp_json_adapter")
    proxy.__dict__.update(original_json.__dict__)
    proxy.dumps = lambda value, *args, **kwargs: original_json.dumps(
        value, *args, default=native, allow_nan=False, **kwargs)
    server.json = proxy
    try:
        reply = asyncio.run(server.call_tool(tool, arguments))
    finally:
        server.json = original_json
    content = [str(getattr(item, "text", "")) for item in reply]
    if not content or not any(item.strip() for item in content):
        raise RuntimeError("protein-design MCP returned no result")
    encoded = json.dumps(content, ensure_ascii=False)
    if len(encoded.encode()) > MAX_OUTPUT: raise RuntimeError("protein-design MCP result too large")
    for item in content:
        if re.match(r"\s*(?:error|traceback|exception|failed)\b", item, re.I):
            raise RuntimeError("protein-design MCP returned a tool error")
        try: value = json.loads(item)
        except ValueError: value = {}
        if isinstance(value, dict) and (value.get("error") or value.get("isError")):
            raise RuntimeError("protein-design MCP returned a tool error")
    return {"tool": tool, "content": content}


def call(spec, *, runner=None):
    tool, arguments, rids = _validated(spec)
    if tool in HOSTED_TOOLS:
        from bionemo_gateway import call as hosted_call
        sequences = arguments.get("sequences") or [arguments["sequence"]]
        request = {"polymers": [{"id": chr(65 + i), "molecule_type": "protein", "sequence": sequence}
                                for i, sequence in enumerate(sequences)],
                   "recycling_steps": 3, "sampling_steps": 50, "diffusion_samples": 1,
                   "output_format": "mmcif"}
        outcome = hosted_call("lab", "nvidia_nim", "nvidia_nim.boltz2", request,
                              "protein-design orchestrator: " + tool)
        receipt = outcome["receipt"]
        return {"tool": tool, "source_receipt_ids": rids,
                "result_sha256": receipt["result_sha256"], "artifact": receipt["artifact"],
                "summary": outcome["summary"], "backend_receipt_id": receipt["receipt_id"],
                "truth_status": "hosted_model_prediction_not_experimental_validation"}
    argv = [PYTHON, __file__, "--worker", tool]
    encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
    if runner is None:
        with tempfile.TemporaryDirectory(prefix="vintos-lab-mcp-") as scratch:
            done = subprocess.run(argv, input=encoded, text=True, capture_output=True,
                                  timeout=TIMEOUT, check=False, env={**os.environ, "TMPDIR": scratch})
    else:
        done = runner(argv, encoded)
    if done.returncode: raise RuntimeError("protein-design MCP worker failed; outcome not retried")
    if len(done.stdout.encode()) > MAX_OUTPUT: raise RuntimeError("protein-design MCP output too large")
    try: result = json.loads(done.stdout)
    except ValueError as exc: raise RuntimeError("protein-design MCP returned unreadable output") from exc
    if not isinstance(result, dict) or result.get("tool") != tool or not result.get("content"):
        raise RuntimeError("protein-design MCP returned an invalid result")
    artifact_dir = Path(lab.ROOT) / "mcp-results"
    artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(artifact_dir, 0o700)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True).encode()
    digest = hashlib.sha256(payload).hexdigest()
    artifact = artifact_dir / (digest + ".json")
    if not artifact.exists():
        fd, temporary = tempfile.mkstemp(prefix=".mcp-", dir=artifact_dir)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, artifact)
        finally:
            try: os.unlink(temporary)
            except OSError: pass
    return {"tool": tool, "source_receipt_ids": rids,
            "arguments_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            "result_sha256": digest, "artifact": str(artifact),
            "summary": json.dumps(result["content"], ensure_ascii=False)[:2500],
            "truth_status": "model_prediction_not_experimental_validation"}


if __name__ == "__main__":
    if sys.argv[1:] == ["--capabilities"]:
        print(json.dumps(capabilities(), ensure_ascii=False, sort_keys=True))
        raise SystemExit(0)
    if len(sys.argv) != 3 or sys.argv[1] != "--worker" or sys.argv[2] not in TOOLS:
        raise SystemExit(2)
    try: arguments = json.loads(sys.stdin.read(4096))
    except ValueError: raise SystemExit(2)
    if not isinstance(arguments, dict): raise SystemExit(2)
    print(json.dumps(_worker(sys.argv[2], arguments), ensure_ascii=False))
