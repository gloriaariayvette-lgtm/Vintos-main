#!/usr/bin/env python3
"""Bounded Lab doorway to the installed protein-design MCP server.

Only sequence scoring is enabled. Design, mutation, arbitrary file paths,
and long-running jobs remain outside this doorway until separately bounded.
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
TOOLS = frozenset(("score_stability",))
AA = re.compile(r"[ACDEFGHIKLMNPQRSTVWY]{20,160}\Z")
RECEIPT_ID = re.compile(r"[0-9a-f]{64}\Z")
TIMEOUT = 180
MAX_OUTPUT = 128 * 1024


def instructions():
    return ("Aegis protein-design MCP (bounded Lab route): choose at most one instrument_query "
            "{tool:score_stability, sequence:20..160 standard amino acids, "
            "source_receipt_id:exact Lab source receipt containing that sequence}. "
            "This reports an ESM2 likelihood proxy, not measured thermodynamic stability. "
            "The other 18 installed server tools are not authorized by this route; "
            "use the separate commissioned Lab ESMFold instrument for structure prediction.")


def _validated(spec):
    if not isinstance(spec, dict) or set(spec) != {"tool", "sequence", "source_receipt_id"}:
        raise ValueError("instrument query requires exact tool, sequence and source receipt")
    tool, sequence, rid = spec["tool"], spec["sequence"], spec["source_receipt_id"]
    if tool not in TOOLS or not isinstance(sequence, str) or not AA.fullmatch(sequence):
        raise ValueError("unsupported instrument or sequence")
    if not isinstance(rid, str) or not RECEIPT_ID.fullmatch(rid):
        raise ValueError("source receipt id required")
    rows = lab._jsonl(os.path.join(lab.ROOT, "source-receipts.jsonl"))
    source = next((row for row in reversed(rows) if row.get("receipt_id") == rid), None)
    if not source or sequence not in json.dumps(source.get("records", {})):
        raise ValueError("exact sequence absent from the named source receipt")
    return tool, sequence, rid


def _worker(tool, sequence):
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
    arguments = {"sequence": sequence}
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
    tool, sequence, rid = _validated(spec)
    argv = [PYTHON, __file__, "--worker", tool]
    if runner is None:
        with tempfile.TemporaryDirectory(prefix="vintos-lab-mcp-") as scratch:
            done = subprocess.run(argv, input=sequence, text=True, capture_output=True,
                                  timeout=TIMEOUT, check=False, env={**os.environ, "TMPDIR": scratch})
    else:
        done = runner(argv, sequence)
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
    return {"tool": tool, "source_receipt_id": rid,
            "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
            "result_sha256": digest, "artifact": str(artifact),
            "summary": json.dumps(result["content"], ensure_ascii=False)[:2500],
            "truth_status": "model_prediction_not_experimental_validation"}


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--worker" or sys.argv[2] not in TOOLS:
        raise SystemExit(2)
    sequence = sys.stdin.read(161).strip()
    if not AA.fullmatch(sequence): raise SystemExit(2)
    print(json.dumps(_worker(sys.argv[2], sequence), ensure_ascii=False))
