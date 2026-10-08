#!/usr/bin/env python3
"""Fold one exact sourced protein with the commissioned local ESMFold model.

The model and tokenizer are loaded from the existing local Hugging Face cache only.
The PDB is written beneath the Chemistry Lab artifact store; stdout contains one bounded
JSON receipt used by chemistry_mac's existing identity and grading contracts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys

# Measured on Aegis's RTX 5080 (15.9 GiB), 2026-10-01: 350 residues 8.7 GiB peak / 13 s, 600 10.3 GiB / 63 s,
# 911 13.3 GiB / 443 s. 350 was a guess that refused Band 3 (P02730, 911). The limit is the longest length
# measured, not extrapolated; chemistry_mac's 900 s timeout leaves 911 twice its time.
MAX_LENGTH = 911
AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
ACCESSION = re.compile(r"[A-Z0-9]{6,10}(?:-[1-9][0-9]*)?")
WS = Path(os.environ.get("SPARK_WORKSPACE", "~/.vintos/workspace")).expanduser().resolve()
ARTIFACTS = WS / "memory" / "chemistry-lab" / "artifacts" / "esmfold"
MODEL_CACHE = Path(os.environ.get(
    "VINTOS_CHEMISTRY_MODEL_CACHE",
    "~/.vintos/tools/chemistry-lab/checkpoints/huggingface")).expanduser().resolve()
MODEL_HUB = MODEL_CACHE / "hub"


def _validate(body):
    if not isinstance(body, dict): raise ValueError("request must be an object")
    accession = str(body.get("accession") or "").strip().upper()
    sequence = re.sub(r"\s+", "", str(body.get("sequence") or "").upper())
    source = body.get("sequence_source") if isinstance(body.get("sequence_source"), dict) else {}
    mapping = body.get("hp_mapping") if isinstance(body.get("hp_mapping"), list) else []
    if not ACCESSION.fullmatch(accession): raise ValueError("exact UniProt accession required")
    if not 4 <= len(sequence) <= MAX_LENGTH or any(c not in AMINO_ACIDS for c in sequence):
        raise ValueError("sequence must contain 4..%d standard amino acids" % MAX_LENGTH)
    if str(source.get("accession") or "").upper() != accession:
        raise ValueError("sequence source accession mismatch")
    if len(mapping) != len(sequence) or "".join(str(x.get("residue") or "") for x in mapping
                                                if isinstance(x, dict)) != sequence:
        raise ValueError("HP mapping does not match sequence")
    return accession, sequence, source, mapping


def first_residue(source):
    """The protein's own number for the first residue folded: 1, or a region's start (2026-10-08: a domain cut
    from a long chain, such as ADGRG6 CUB 41-149, is numbered as the protein, not from 1)."""
    region = (source or {}).get("region")
    try:
        return int(region[0]) if isinstance(region, (list, tuple)) and len(region) == 2 else 1
    except (TypeError, ValueError):
        return 1


def renumber(pdb, first):
    """PDB text with residue numbers (columns 23-26) moved so the first residue is `first`."""
    if first == 1:
        return pdb
    out = []
    for line in str(pdb).splitlines():
        if line.startswith(("ATOM", "HETATM", "TER")) and len(line) >= 26 and line[22:26].strip().lstrip("-").isdigit():
            line = line[:22] + "%4d" % (int(line[22:26]) + first - 1) + line[26:]
        out.append(line)
    return "\n".join(out) + ("\n" if str(pdb).endswith("\n") else "")


def fold(body):
    accession, sequence, source, mapping = _validate(body)
    import torch
    from transformers import AutoTokenizer, EsmForProteinFolding
    if not torch.cuda.is_available(): raise RuntimeError("ESMFold requires the commissioned CUDA instrument")
    model_name = "facebook/esmfold_v1"
    tokenizer = AutoTokenizer.from_pretrained(
        model_name, cache_dir=str(MODEL_HUB), local_files_only=True)
    model = EsmForProteinFolding.from_pretrained(
        model_name, cache_dir=str(MODEL_HUB), local_files_only=True, low_cpu_mem_usage=True)
    model.esm = model.esm.half(); model = model.cuda().eval(); model.trunk.set_chunk_size(32)
    inputs = tokenizer([sequence], return_tensors="pt", add_special_tokens=False)["input_ids"].cuda()
    with torch.no_grad(): output = model(inputs)
    pdb = renumber(model.output_to_pdb(output)[0], first_residue(source))
    if "ATOM" not in pdb: raise RuntimeError("ESMFold returned no PDB atoms")
    digest = hashlib.sha256(pdb.encode()).hexdigest()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    destination = ARTIFACTS / (accession + "-" + digest[:12] + ".pdb")
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(pdb, encoding="utf-8")
    os.replace(temporary, destination)
    mean_plddt = float(output.plddt.mean().cpu())
    # Transformers' ESMFold head emits confidence as a 0..1 probability, while
    # structure files and the Lab grader use the conventional 0..100 pLDDT scale.
    if 0.0 <= mean_plddt <= 1.0: mean_plddt *= 100.0
    mean_plddt = round(mean_plddt, 6)
    # What is in the model: confidence per residue and helix/strand from its own coordinates (2026-10-07: only the
    # mean was kept, and he re-folded O43511 twice for secondary structure the result never carried).
    try:
        import chemistry_fold_read as _fr
        _read = _fr.summary(_fr.read_pdb(pdb))
        structure_read = {k: _read[k] for k in ("secondary_structure", "helices", "strands", "confidence_bands",
                                                 "plddt_by_residue", "method", "display")}
    except Exception as exc:
        structure_read = {"error": "the model could not be read: %s" % str(exc)[:200]}
    title = "Folding %s (%d aa): %s" % (accession, len(sequence), sequence)
    if first_residue(source) != 1:
        title += " [residues %d-%d of %s, numbered as in the protein]" % (
            first_residue(source), first_residue(source) + len(sequence) - 1, accession)
    result = {"title": title, "requested_accession": accession,
              "modeled_sequence": sequence, "real_sequence": sequence,
              "modeled_sequence_length": len(sequence), "sequence_source": source,
              "hp_mapping": mapping, "mean_plddt": mean_plddt,
              "structure_read": structure_read,
              "structure_artifact": str(destination.relative_to(WS)),
              "structure_sha256": digest, "backend": "facebook/esmfold_v1",
              "display": [title, "", "actual amino-acid sequence:", sequence, "",
                          "ESMFold mean pLDDT: %.3f" % mean_plddt] + list(structure_read.get("display") or []) + [
                          "structure: " + str(destination.relative_to(WS))],
              "truth_status": "computational_structure_prediction_not_biological_fact"}
    return {"ok": True, "result": result}


def main():
    try:
        value = fold(json.load(sys.stdin)); print(json.dumps(value, ensure_ascii=False)); return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})); return 2


if __name__ == "__main__": raise SystemExit(main())
