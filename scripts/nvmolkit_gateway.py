#!/usr/bin/env python3
"""A bounded local GPU bridge into the dedicated Aegis nvMolKit environment."""
import json
import os
from pathlib import Path
import re
import subprocess

from plugin_catalog import policy

PYTHON = Path(os.environ.get("VINTOS_NVMOLKIT_PYTHON", "~/.vintos/tools/nvmolkit-venv/bin/python")).expanduser()
WORKER = Path(__file__).with_name("nvmolkit_worker.py")
OPERATIONS = {"nvmolkit.fingerprints":"fingerprints", "nvmolkit.similarity":"similarity",
              "nvmolkit.cluster":"cluster", "nvmolkit.conformers":"conformers"}


def validate(tool, arguments):
    if tool not in OPERATIONS: raise PermissionError("unknown nvMolKit operation")
    if not isinstance(arguments, dict): raise ValueError("arguments object required")
    allowed = {"smiles","cutoff","conformers_per_molecule","seed"}
    if set(arguments) - allowed: raise ValueError("unsupported nvMolKit argument")
    smiles = arguments.get("smiles")
    maximum = 16 if tool == "nvmolkit.conformers" else 128
    if not isinstance(smiles, list) or not 1 <= len(smiles) <= maximum:
        raise ValueError("bounded SMILES list required")
    if any(not isinstance(x,str) or not 1 <= len(x) <= 512 or not re.fullmatch(r"[A-Za-z0-9@+\-\[\]()=#$/\\.%:*]+",x) for x in smiles):
        raise ValueError("plain bounded SMILES required")
    if tool == "nvmolkit.cluster":
        cutoff=arguments.get("cutoff")
        if type(cutoff) not in (int,float) or not 0 < cutoff < 1:
            raise ValueError("cluster cutoff must be between 0 and 1")
    elif "cutoff" in arguments: raise ValueError("cutoff only applies to clustering")
    if tool == "nvmolkit.conformers":
        count=arguments.get("conformers_per_molecule",1)
        if type(count) is not int or not 1 <= count <= 3:
            raise ValueError("1..3 conformers per molecule required")
        seed=arguments.get("seed",42)
        if type(seed) is not int or not 1 <= seed < 2**31:
            raise ValueError("positive bounded seed required")
    elif "conformers_per_molecule" in arguments or "seed" in arguments:
        raise ValueError("conformer settings require conformer operation")
    payload = {"operation":OPERATIONS[tool],**arguments}
    encoded = json.dumps(payload,allow_nan=False).encode()
    if len(encoded) > 65536: raise ValueError("nvMolKit input too large")
    return encoded


def call(surface, plugin, tool, arguments, purpose, *, transport=None):
    entry = policy(plugin,surface,tool)
    if plugin != "nvmolkit": raise PermissionError("not an nvMolKit operation")
    if not isinstance(purpose,str) or not purpose.strip() or len(purpose) > 1000:
        raise ValueError("bounded scientific purpose required")
    encoded = validate(tool,arguments)
    if not PYTHON.is_file() or not WORKER.is_file():
        raise RuntimeError("isolated nvMolKit runtime unavailable")
    if transport is None:
        done=subprocess.run([str(PYTHON),str(WORKER)],input=encoded,capture_output=True,
                            timeout=180,check=False)
        if done.returncode:
            raise RuntimeError("nvMolKit worker failed: "+done.stderr.decode(errors="replace")[-240:])
        if len(done.stdout)>8*1024*1024: raise ValueError("nvMolKit result too large")
        result=json.loads(done.stdout)
    else:
        result=transport(json.loads(encoded))
    if not isinstance(result,dict): raise RuntimeError("nvMolKit returned no result object")
    from plugin_gateway import _store,summary
    receipt=_store(surface,plugin,tool,arguments,result,entry["visibility"])
    return {"ok":True,"receipt":receipt,"summary":summary(result)}
