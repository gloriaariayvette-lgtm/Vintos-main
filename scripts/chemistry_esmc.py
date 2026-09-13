#!/usr/bin/env python3
"""Measured ESMC adapter for the Chemistry Lab.

Reads a bounded JSON batch from stdin, writes full vectors only beneath the
visible Chemistry Lab artifact store, and returns content-addressed receipts.
It never writes into general memory or the Atelier.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch
from esm.models.esmc import ESMC
from esm.sdk.api import ESMProtein, LogitsConfig

WS = Path(os.environ.get("SPARK_WORKSPACE", "~/.vintos/workspace")).expanduser().resolve()
ARTIFACTS = WS / "memory" / "chemistry-lab" / "artifacts" / "esmc"
MODEL = os.environ.get("CHEM_LAB_ESMC_MODEL", "esmc_600m")
MAX_BATCH = 4
MAX_LENGTH = 350


def main():
    body = json.load(sys.stdin)
    rows = body.get("records", []) if isinstance(body, dict) else []
    rows = rows[:MAX_BATCH]
    if not rows:
        print(json.dumps({"ok": True, "model": MODEL, "embeddings": []}))
        return
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ESMC.from_pretrained(MODEL).to(device).eval()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    receipts = []
    with torch.inference_mode():
        for row in rows:
            accession = str(row.get("accession", "unknown"))[:32]
            sequence = "".join(c for c in str(row.get("sequence", "")).upper()
                               if "A" <= c <= "Z")[:MAX_LENGTH]
            if not sequence:
                continue
            encoded = model.encode(ESMProtein(sequence=sequence))
            result = model.logits(encoded, LogitsConfig(sequence=False, return_embeddings=True))
            # Pool residue positions only; boundary tokens are not biology.
            vector = result.embeddings[0, 1:len(sequence) + 1].float().mean(dim=0).cpu().numpy()
            digest = hashlib.sha256(vector.tobytes()).hexdigest()
            destination = ARTIFACTS / (accession + "-" + digest[:12] + ".npy")
            temporary = destination.with_suffix(".tmp.npy")
            np.save(temporary, vector, allow_pickle=False)
            os.replace(temporary, destination)
            receipts.append({
                "accession": accession,
                "sequence_length": len(sequence),
                "dimension": int(vector.shape[0]),
                "embedding_sha256": digest,
                "artifact": str(destination.relative_to(WS)),
                "l2_norm": round(float(np.linalg.norm(vector)), 6),
            })
    print(json.dumps({"ok": True, "model": MODEL, "device": device,
                      "embeddings": receipts}, sort_keys=True))


if __name__ == "__main__":
    main()
