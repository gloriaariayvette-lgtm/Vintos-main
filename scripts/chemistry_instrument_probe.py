#!/usr/bin/env python3
"""Exercise one installed Aegis Chemistry Lab instrument, or name its exact failure.

This is a commissioning probe, not a general command runner.  Every subcommand owns a
fixed, bounded invocation and emits one JSON object.  Success means a real artifact or
server reply was observed; importing a package is never enough.  Failure includes a typed,
bounded diagnosis and a digest of the full traceback, while the traceback itself remains
in the invoking process's captured evidence rather than the visible Lab ledger.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import traceback

TOOLS = pathlib.Path(os.environ.get("CHEM_LAB_TOOLS", "~/.vintos/tools/chemistry-lab")).expanduser()
PROTEIN_ROOT = pathlib.Path(os.environ.get("CHEM_LAB_PROTEINMPNN_ROOT", "~/protein-tools/ProteinMPNN")).expanduser()
FOUNDRY_CKPT = pathlib.Path(os.environ.get(
    "CHEM_LAB_RFD3_CHECKPOINT", str(TOOLS / "checkpoints" / "foundry" / "rfd3_latest.ckpt")))
SEQUENCE = "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP"


def _emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _run(argv, timeout):
    return subprocess.run([str(x) for x in argv], text=True, capture_output=True,
                          timeout=timeout, check=False)


def _failure(instrument, entry, exc=None, *, failure_type="exception", detail=""):
    full = traceback.format_exc() if exc is not None else str(detail)
    message = str(detail) if detail else (str(exc) if exc is not None else "")
    _emit({"ok": False, "instrument": instrument, "entry_point": entry,
           "failure": {"type": failure_type,
                       "error": message[:300],
                       "traceback_sha256": hashlib.sha256(full.encode("utf-8", "replace")).hexdigest()}})
    return 2


def protein_mpnn():
    py = TOOLS / "proteinmpnn" / "bin" / "python"
    script = PROTEIN_ROOT / "protein_mpnn_run.py"
    pdb = PROTEIN_ROOT / "inputs" / "PDB_monomers" / "pdbs" / "6MRR.pdb"
    entry = "%s --pdb_path 6MRR.pdb --num_seq_per_target 1" % script
    try:
        with tempfile.TemporaryDirectory(prefix="vintos-mpnn-probe-") as out:
            done = _run([py, script, "--pdb_path", pdb, "--out_folder", out,
                         "--num_seq_per_target", "1", "--batch_size", "1",
                         "--sampling_temp", "0.1", "--seed", "37"], 300)
            if done.returncode:
                return _failure("protein_mpnn", entry, failure_type="nonzero_exit",
                                detail="exit %d" % done.returncode)
            fastas = list(pathlib.Path(out).rglob("*.fa"))
            if not fastas: return _failure("protein_mpnn", entry, failure_type="artifact_absent",
                                           detail="no FASTA produced")
            records = sum(1 for line in fastas[0].read_text(errors="replace").splitlines()
                          if line.startswith(">"))
            if records < 2: return _failure("protein_mpnn", entry, failure_type="result_unusable",
                                            detail="designed sequence absent")
            _emit({"ok": True, "instrument": "protein_mpnn", "entry_point": entry,
                   "verification": "one fixed-backbone design completed",
                   "output": {"pdb": "6MRR.pdb", "fasta_records": records,
                              "artifact_count": len(fastas)}})
            return 0
    except Exception as exc: return _failure("protein_mpnn", entry, exc)


def rfdiffusion():
    exe = TOOLS / "foundry" / "bin" / "rfd3"
    entry = "%s design +specification.length=10 n_batches=1 num_timesteps=2" % exe
    try:
        with tempfile.TemporaryDirectory(prefix="vintos-rfd3-probe-") as out:
            done = _run([exe, "design", "out_dir=" + out, "inputs=null",
                         "+specification.length=10", "ckpt_path=" + str(FOUNDRY_CKPT),
                         "diffusion_batch_size=1", "n_batches=1",
                         "inference_sampler.num_timesteps=2", "low_memory_mode=True",
                         "skip_existing=False"], 600)
            if done.returncode:
                return _failure("rfdiffusion", entry, failure_type="nonzero_exit",
                                detail="exit %d" % done.returncode)
            root = pathlib.Path(out)
            jsons, structures = list(root.rglob("*.json")), list(root.rglob("*.cif.gz"))
            if not jsons or not structures:
                return _failure("rfdiffusion", entry, failure_type="artifact_absent",
                                detail="expected JSON and CIF.GZ")
            _emit({"ok": True, "instrument": "rfdiffusion", "entry_point": entry,
                   "verification": "one 10-residue two-step diffusion completed",
                   "output": {"json_artifacts": len(jsons), "structure_artifacts": len(structures),
                              "device": "cuda"}})
            return 0
    except Exception as exc: return _failure("rfdiffusion", entry, exc)


def structure_prediction():
    entry = "transformers.EsmForProteinFolding.from_pretrained(facebook/esmfold_v1)"
    try:
        import torch
        from transformers import AutoTokenizer, EsmForProteinFolding
        model_name = "facebook/esmfold_v1"
        tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        model = EsmForProteinFolding.from_pretrained(
            model_name, local_files_only=True, low_cpu_mem_usage=True)
        model.esm = model.esm.half(); model = model.cuda().eval(); model.trunk.set_chunk_size(32)
        sequence = SEQUENCE[:20]
        inputs = tokenizer([sequence], return_tensors="pt", add_special_tokens=False)["input_ids"].cuda()
        with torch.no_grad(): result = model(inputs)
        pdb = model.output_to_pdb(result)[0]
        if "ATOM" not in pdb:
            return _failure("structure_prediction", entry, failure_type="artifact_absent",
                            detail="ESMFold returned no PDB")
        _emit({"ok": True, "instrument": "structure_prediction", "entry_point": entry,
               "verification": "ESMFold predicted one short sequence",
               "output": {"sequence_length": len(sequence), "pdb_lines": len(pdb.splitlines()),
                          "mean_plddt": round(float(result.plddt.mean().cpu()), 6),
                          "device": "cuda"}})
        return 0
    except Exception as exc:
        return _failure("structure_prediction", entry, exc, failure_type="prediction_failed")


def protein_design_mcp():
    entry = "protein_design_mcp.server.call_tool(get_design_status)"
    async def invoke():
        from protein_design_mcp.server import call_tool, list_tools
        tools = await list_tools()
        reply = await call_tool("get_design_status", {"job_id": "vintos-probe-does-not-exist"})
        return tools, reply
    try:
        tools, reply = asyncio.run(invoke())
        names = [tool.name for tool in tools]
        text = " ".join(str(getattr(item, "text", "")) for item in reply)
        if "get_design_status" not in names or "Job not found" not in text:
            return _failure("protein_design_mcp", entry, failure_type="dispatch_unproved",
                            detail="server did not return the expected typed reply")
        _emit({"ok": True, "instrument": "protein_design_mcp", "entry_point": entry,
               "verification": "server listed tools and dispatched one status call",
               "output": {"tool_count": len(names), "reply": "typed_job_not_found",
                          "house_connected": False,
                          "connection_needed": "register the stdio server with a bounded Lab orchestrator"}})
        return 0
    except Exception as exc: return _failure("protein_design_mcp", entry, exc)


COMMANDS = {"protein_mpnn": protein_mpnn, "rfdiffusion": rfdiffusion,
            "structure_prediction": structure_prediction,
            "protein_design_mcp": protein_design_mcp}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) == 2 else ""
    if name not in COMMANDS:
        _emit({"ok": False, "failure": {"type": "unknown_probe"}}); raise SystemExit(2)
    raise SystemExit(COMMANDS[name]())
