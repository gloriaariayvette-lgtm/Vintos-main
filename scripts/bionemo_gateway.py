#!/usr/bin/env python3
"""Bounded hosted NVIDIA NIM calls; one durable reservation per attempted job.

No key or provider request is made at import. Transport is injectable so tests
cannot reach NVIDIA. A timeout has an unknown outcome and is never retried.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
from datetime import datetime
from urllib.request import Request
from zoneinfo import ZoneInfo

from lab_http import open_request
from plugin_catalog import policy

KEY_FILE = Path(os.environ.get("VINTOS_NVIDIA_KEY_FILE", "~/.config/vintos/nvidia-nim.key")).expanduser()
LEDGER = Path(os.environ.get("VINTOS_NVIDIA_LEDGER", "~/.vintos/workspace/memory/nvidia-nim-attempts.jsonl")).expanduser()
DAY_ZONE = ZoneInfo("America/Chicago")
DAILY_LIMIT = 3
MAX_REQUEST = 112 * 1024
MAX_RESPONSE = 8 * 1024 * 1024
ENDPOINTS = {
    "nvidia_nim.boltz2": "https://health.api.nvidia.com/v1/biology/mit/boltz2/predict",
    "nvidia_nim.diffdock": "https://health.api.nvidia.com/v1/biology/mit/diffdock",
    "nvidia_nim.proteinmpnn": "https://health.api.nvidia.com/v1/biology/ipd/proteinmpnn/predict",
    "nvidia_nim.rfdiffusion": "https://health.api.nvidia.com/v1/biology/ipd/rfdiffusion/generate",
}
FIELDS = {
    "nvidia_nim.boltz2": frozenset(("polymers", "ligands", "recycling_steps", "sampling_steps",
                                    "diffusion_samples", "step_scale", "output_format")),
    "nvidia_nim.diffdock": frozenset(("protein", "ligand", "ligand_file_type", "num_poses",
                                      "time_divisions", "steps", "save_trajectory")),
    "nvidia_nim.proteinmpnn": frozenset(("input_pdb", "input_pdb_chains", "num_seq_per_target",
                                         "sampling_temp", "use_soluble_model", "ca_only",
                                         "omit_AAs")),
    "nvidia_nim.rfdiffusion": frozenset(("input_pdb", "contigs", "diffusion_steps",
                                         "hotspot_res")),
}


def _bounded_int(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name + " must be " + str(low) + ".." + str(high))


def validate(tool, arguments):
    if tool not in ENDPOINTS: raise PermissionError("unsupported hosted NIM operation")
    if not isinstance(arguments, dict) or set(arguments) - FIELDS[tool]:
        raise ValueError("unsupported NIM argument")
    encoded = json.dumps(arguments, sort_keys=True, allow_nan=False).encode()
    if len(encoded) > MAX_REQUEST: raise ValueError("NIM input exceeds gateway limit")
    if tool == "nvidia_nim.boltz2":
        polymers = arguments.get("polymers")
        if not isinstance(polymers, list) or not 1 <= len(polymers) <= 4:
            raise ValueError("1..4 exact polymers required")
        for row in polymers:
            if not isinstance(row, dict) or set(row) - {"id", "molecule_type", "sequence"}:
                raise ValueError("unsupported polymer specification")
            if row.get("molecule_type") not in ("protein", "dna", "rna"):
                raise ValueError("protein, DNA, or RNA polymer required")
            alphabet = "ACDEFGHIKLMNPQRSTVWYBXZJUO" if row["molecule_type"] == "protein" else "ACGTUN"
            if not isinstance(row.get("sequence"), str) or not 1 <= len(row["sequence"]) <= 4096 or any(c not in alphabet for c in row["sequence"]):
                raise ValueError("bounded uppercase polymer sequence required")
            if not isinstance(row.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9]{1,8}", row["id"]):
                raise ValueError("polymer chain ID required")
        ligands = arguments.get("ligands", [])
        if not isinstance(ligands, list) or len(ligands) > 2: raise ValueError("at most two ligands")
        for row in ligands:
            if not isinstance(row, dict) or set(row) - {"id", "smiles", "ccd", "predict_affinity"} or not isinstance(row.get("id"), str):
                raise ValueError("unsupported ligand specification")
            if bool(row.get("smiles")) == bool(row.get("ccd")): raise ValueError("exactly one ligand representation required")
            if row.get("smiles") and (not isinstance(row["smiles"], str) or len(row["smiles"]) > 512):
                raise ValueError("bounded SMILES required")
            if row.get("ccd") and (not isinstance(row["ccd"], str) or not re.fullmatch("[A-Z0-9]{1,8}", row["ccd"])):
                raise ValueError("valid CCD code required")
        if sum(row.get("predict_affinity") is True for row in ligands) > 1:
            raise ValueError("only one affinity target")
        for name, bounds in (("recycling_steps",(1,10)),("sampling_steps",(1,200)),("diffusion_samples",(1,4))):
            if name in arguments: _bounded_int(arguments[name], *bounds, name)
        if arguments.get("output_format", "mmcif") != "mmcif": raise ValueError("mmcif output required")
    elif tool == "nvidia_nim.diffdock":
        protein = arguments.get("protein")
        if not isinstance(protein, str) or "ATOM" not in protein or len(protein) > 100000:
            raise ValueError("inline ATOM receptor required")
        if not isinstance(arguments.get("ligand"), str) or not 1 <= len(arguments["ligand"]) <= 10000:
            raise ValueError("inline ligand required")
        if arguments.get("ligand_file_type") not in ("txt", "sdf", "mol2"):
            raise ValueError("ligand_file_type must be txt, sdf, or mol2")
        for name, bounds in (("num_poses",(1,10)),("time_divisions",(1,20)),("steps",(1,18))):
            if name in arguments: _bounded_int(arguments[name], *bounds, name)
        if arguments.get("save_trajectory", False) is not False:
            raise ValueError("trajectory output is disabled")
    elif tool == "nvidia_nim.proteinmpnn":
        pdb = arguments.get("input_pdb")
        if not isinstance(pdb, str) or "ATOM" not in pdb or len(pdb) > 100000:
            raise ValueError("inline PDB backbone required")
        if "num_seq_per_target" in arguments:
            _bounded_int(arguments["num_seq_per_target"], 1, 10, "num_seq_per_target")
        if "sampling_temp" in arguments and (not isinstance(arguments["sampling_temp"], list)
            or not 1 <= len(arguments["sampling_temp"]) <= 3
            or any(type(x) not in (int,float) or not 0 < x <= 1 for x in arguments["sampling_temp"])):
            raise ValueError("bounded sampling_temp list required")
    else:
        pdb = arguments.get("input_pdb")
        if not isinstance(pdb, str) or "ATOM" not in pdb or len(pdb) > 100000:
            raise ValueError("inline PDB, including a dummy for de novo, required")
        if not isinstance(arguments.get("contigs"), str) or not re.fullmatch(r"[A-Za-z0-9/ ,.-]{2,200}", arguments["contigs"]):
            raise ValueError("bounded contigs required")
        if "diffusion_steps" in arguments:
            _bounded_int(arguments["diffusion_steps"], 1, 50, "diffusion_steps")
        if "hotspot_res" in arguments and (not isinstance(arguments["hotspot_res"], list)
            or len(arguments["hotspot_res"]) > 16
            or any(not isinstance(x,str) or not re.fullmatch("[A-Za-z][0-9]{1,5}",x) for x in arguments["hotspot_res"])):
            raise ValueError("bounded hotspot residues required")
    return encoded


def _key():
    path = KEY_FILE
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise RuntimeError("NVIDIA key file absent or not mode 0600")
    key = path.read_text().strip()
    if not 20 <= len(key) <= 4096 or any(c.isspace() for c in key):
        raise RuntimeError("NVIDIA key file is invalid")
    return key


def reserve(tool, arguments, *, moment=None):
    """An append-only attempted-job cap. Reserve before contacting NVIDIA."""
    now = moment or datetime.now(DAY_ZONE)
    day = now.astimezone(DAY_ZONE).date().isoformat()
    LEDGER.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(LEDGER.parent, 0o700)
    lock_path = Path(str(LEDGER) + ".lock")
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = [json.loads(x) for x in LEDGER.read_text().splitlines() if x.strip()] if LEDGER.exists() else []
        used = sum(x.get("event") == "reserved" and x.get("day") == day for x in rows)
        if used >= DAILY_LIMIT: raise PermissionError("NVIDIA NIM daily attempt limit reached (3)")
        row = {"event":"reserved","day":day,"at":now.isoformat(),"tool":tool,
               "request_sha256":hashlib.sha256(json.dumps(arguments,sort_keys=True).encode()).hexdigest(),
               "used":used+1,"limit":DAILY_LIMIT}
        with LEDGER.open("a") as stream:
            os.chmod(LEDGER, 0o600)
            stream.write(json.dumps(row,sort_keys=True)+"\n")
            stream.flush(); os.fsync(stream.fileno())
        return row


def _post(url, encoded, key):
    request = Request(url, data=encoded, method="POST",
                      headers={"Content-Type":"application/json","Authorization":"Bearer "+key})
    with open_request(request, timeout=300) as response:
        body = response.read(MAX_RESPONSE + 1)
    if len(body) > MAX_RESPONSE: raise ValueError("NIM result exceeds gateway limit")
    return json.loads(body)


def call(surface, plugin, tool, arguments, purpose, *, transport=None, store=None):
    entry = policy(plugin, surface, tool)
    if plugin != "nvidia_nim": raise PermissionError("not an NVIDIA NIM operation")
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 1000:
        raise ValueError("bounded scientific purpose required")
    encoded = validate(tool, arguments)
    key = _key()  # Missing credential never consumes a job.
    reservation = reserve(tool, arguments)
    result = (transport or _post)(ENDPOINTS[tool], encoded, key)
    if not isinstance(result, dict): raise RuntimeError("NIM returned no result object")
    if store is None:
        from plugin_gateway import _store
        store = _store
    receipt = store(surface, plugin, tool, arguments, result, entry["visibility"])
    receipt["reservation"] = {k:reservation[k] for k in ("day","used","limit")}
    from plugin_gateway import summary
    return {"ok":True,"receipt":receipt,"summary":summary(result)}
