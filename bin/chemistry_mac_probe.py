#!/usr/bin/env python3
"""Run fixed Chemistry Lab commissioning checks on the Mac and emit receiptable JSON.

Each named check uses its own existing environment. This file accepts no code, paths, or
model-selected arguments; it is a repeatable commissioning surface, not a second bench
doorway. Its stdout is one record suitable for ``chemistry_probe --record-run -``.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import traceback
import uuid

ROOT = pathlib.Path(os.environ.get("VINTOS_QLAB", "~/qlab")).expanduser()
SOURCE_SHA256 = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
PYTHONS = {"qpanda": ROOT / ".venv" / "bin" / "python",
           "vqnet": ROOT / ".venv" / "bin" / "python",
           "quantum_chemistry": ROOT / ".venv-pychemiq" / "bin" / "python",
           "mac_esmc": ROOT / ".venv-esmc" / "bin" / "python",
           "foundry": ROOT / ".venv-foundry" / "bin" / "python"}
TIMEOUTS = {"qpanda": 120, "vqnet": 120, "quantum_chemistry": 600,
            "mac_esmc": 900, "foundry": 900}


def _record(name, ok, verification, output=None, failure=None, entry_point=""):
    return {"ok": bool(ok), "run_id": "MAC-PROBE-" + name + "-" + uuid.uuid4().hex[:8],
            "instrument": name, "source_sha256": SOURCE_SHA256,
            "receipt": {"entry_point": entry_point, "verification": verification,
                        "device": "mac", "output": output or {}, "failure": failure},
            "truth_status": "host_executed_commissioning_probe"}


def _child(name):
    if name == "qpanda":
        import pyqpanda3.core as pq
        prog = pq.QProg(); prog << pq.H(0) << pq.CNOT(0, 1)
        prog << pq.measure(0, 0) << pq.measure(1, 1)
        qvm = pq.CPUQVM(); qvm.run(prog, 1000); counts = qvm.result().get_counts()
        bad = sum(v for k, v in counts.items() if k not in ("00", "11"))
        print(json.dumps({"ok": bad == 0 and sum(counts.values()) == 1000,
                          "output": {"shots": sum(counts.values()), "forbidden_counts": bad,
                                     "observed_states": ",".join(sorted(counts))}})); return
    if name == "vqnet":
        from pyvqnet.tensor import QTensor
        value = ((QTensor([1.0, 2.0, 3.0]) ** 2) + 1).numpy().tolist()
        print(json.dumps({"ok": value == [2.0, 5.0, 10.0], "output": {"result": str(value)}})); return
    if name == "mac_esmc":
        import torch
        from esm.models.esmc import ESMC
        from esm.sdk.api import ESMProtein, LogitsConfig
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        model = ESMC.from_pretrained("esmc_600m").to(device).eval()
        encoded = model.encode(ESMProtein(sequence="MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ"))
        result = model.logits(encoded, LogitsConfig(sequence=False, return_embeddings=True))
        vector = result.embeddings[0, 1:34].float().mean(dim=0).cpu()
        print(json.dumps({"ok": int(vector.shape[0]) > 0,
                          "output": {"dimension": int(vector.shape[0]), "device": device}})); return
    if name == "quantum_chemistry":
        import numpy as np
        from pychemiq.Molecules import Molecules
        from pychemiq.Optimizer import vqe_solver
        from pychemiq.Circuit.Ansatz import UCC
        from pychemiq import QMachineType, ChemiQ
        from pychemiq.Transform.Mapping import MappingType, Transform
        mol = Molecules(geometry=["H 0 0 0", "H 0 0 0.74"], basis="sto-3g",
                        multiplicity=1, charge=0)
        mapping = MappingType.Bravyi_Kitaev; pauli = Transform(mol.get_molecular_hamiltonian(), mapping)
        chemiq = ChemiQ(); chemiq.prepare_vqe(QMachineType.CPU_SINGLE_THREAD, mapping,
                                              mol.n_electrons, len(pauli.data()), pauli.get_max_index() + 1)
        ansatz = UCC("UCCSD", mol.n_electrons, mapping, chemiq=chemiq)
        result = vqe_solver(method="NELDER_MEAD", pauli=pauli, ansatz=ansatz, chemiq=chemiq,
                            init_para=np.zeros(ansatz.get_para_num()))
        energy = float(result.fun_val)
        print(json.dumps({"ok": energy < float(mol.hf_energy),
                          "output": {"vqe_hartree": energy, "hartree_fock": float(mol.hf_energy),
                                     "iterations": int(getattr(result, "iters", 0))}})); return
    raise ValueError("unknown child")


def _foundry():
    exe = ROOT / ".venv-foundry" / "bin" / "rfd3"
    ckpt = ROOT / "checkpoints" / "rfd3_latest.ckpt"
    with tempfile.TemporaryDirectory(prefix="vintos-rfd3-mac-") as out:
        argv = [exe, "design", "out_dir=" + out, "inputs=null", "+specification.length=10",
                "ckpt_path=" + str(ckpt), "diffusion_batch_size=1", "n_batches=1",
                "inference_sampler.num_timesteps=2", "low_memory_mode=True", "skip_existing=False"]
        done = subprocess.run([str(x) for x in argv], capture_output=True, text=True,
                              timeout=TIMEOUTS["foundry"], check=False)
        root = pathlib.Path(out); js = list(root.rglob("*.json")); cif = list(root.rglob("*.cif.gz"))
        if done.returncode or not js or not cif:
            raise RuntimeError("RFD3 exit=%d json=%d structure=%d" % (done.returncode, len(js), len(cif)))
        return {"json_artifacts": len(js), "structure_artifacts": len(cif), "device": "mps"}


def run(name):
    entry = {"qpanda": "pyqpanda CPUQVM Bell circuit, 1000 shots",
             "vqnet": "pyvqnet QTensor arithmetic",
             "quantum_chemistry": "pyChemiQ H2/STO-3G UCCSD VQE",
             "mac_esmc": "ESMC-600M embedding of 33 residues; MPS when available",
             "foundry": "rfd3 10-residue two-step diffusion on MPS"}[name]
    try:
        if name == "foundry": output = _foundry()
        else:
            with tempfile.TemporaryDirectory(prefix="vintos-mac-probe-") as work:
                done = subprocess.run([str(PYTHONS[name]), str(pathlib.Path(__file__).resolve()),
                                       "--child", name], capture_output=True, text=True, cwd=work,
                                      timeout=TIMEOUTS[name], check=False)
            if done.returncode: raise RuntimeError("child exit %d" % done.returncode)
            value = json.loads(done.stdout.strip().splitlines()[-1])
            if not value.get("ok"): raise RuntimeError("functional assertion failed")
            output = value.get("output") or {}
        return _record(name, True, "functional run completed", output=output, entry_point=entry)
    except Exception as exc:
        full = traceback.format_exc()
        return _record(name, False, "functional run failed", entry_point=entry,
                       failure={"type": exc.__class__.__name__, "error": str(exc)[:240],
                                "traceback_sha256": hashlib.sha256(full.encode()).hexdigest()})


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child": _child(sys.argv[2]); raise SystemExit(0)
    name = sys.argv[1] if len(sys.argv) == 2 else ""
    if name not in PYTHONS: print(json.dumps({"ok": False, "error": "unknown instrument"})); raise SystemExit(2)
    print(json.dumps(run(name), sort_keys=True))
