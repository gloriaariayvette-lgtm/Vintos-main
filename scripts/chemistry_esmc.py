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
# One pass reads at most WINDOW residues: the size the GPU has run beside Gemma. A longer protein is read in
# overlapping windows of that size and every residue averaged over the windows it fell in, so the whole chain is in
# the vector and no pass is bigger than before (Gloria, 2026-10-07: pendrin's embedding stopped at residue 350 of
# 780; its STAS domain, 535-729, was never in it). MAX_LENGTH bounds the time a very long protein can take.
WINDOW = 350
STRIDE = 300
MAX_LENGTH = 2100


def windows(length, window=WINDOW, stride=STRIDE):
    """[(start, end)] half-open, covering 0..length; the last window ends at length."""
    if length <= window:
        return [(0, length)]
    starts = list(range(0, length - window, stride)) + [length - window]
    return [(a, a + window) for a in sorted(set(starts))]


def pool(per_window, length):
    """Average each residue over the windows that held it, then over the chain. per_window: [(start, end, rows)]."""
    total = np.zeros((length, per_window[0][2].shape[1]), dtype=np.float64)
    count = np.zeros((length, 1), dtype=np.float64)
    for a, b, rows in per_window:
        total[a:b] += rows
        count[a:b] += 1
    return (total / count).mean(axis=0).astype(np.float32)


def main():
    body = json.load(sys.stdin)
    rows = body.get("records", []) if isinstance(body, dict) else []
    rows = rows[:MAX_BATCH]
    if not rows:
        print(json.dumps({"ok": True, "model": MODEL, "embeddings": []}))
        return
    # The same measured adapter runs on Aegis and the Mac.  CUDA has first
    # claim on Aegis; Apple Silicon should use its actual MPS backend rather
    # than silently turning a requested Mac measurement into a CPU run.
    device = ("cuda" if torch.cuda.is_available() else
              "mps" if torch.backends.mps.is_available() else "cpu")
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
            parts = []
            for a, b in windows(len(sequence)):
                piece = sequence[a:b]
                encoded = model.encode(ESMProtein(sequence=piece))
                result = model.logits(encoded, LogitsConfig(sequence=False, return_embeddings=True))
                # Residue positions only; boundary tokens are not biology.
                parts.append((a, b, result.embeddings[0, 1:len(piece) + 1].float().cpu().numpy()))
            vector = pool(parts, len(sequence))
            digest = hashlib.sha256(vector.tobytes()).hexdigest()
            destination = ARTIFACTS / (accession + "-" + digest[:12] + ".npy")
            temporary = destination.with_suffix(".tmp.npy")
            np.save(temporary, vector, allow_pickle=False)
            os.replace(temporary, destination)
            receipts.append({
                "accession": accession,
                "sequence_length": len(sequence),
                "windows": [[a + 1, b] for a, b, _ in parts],
                "dimension": int(vector.shape[0]),
                "embedding_sha256": digest,
                "artifact": str(destination.relative_to(WS)),
                "l2_norm": round(float(np.linalg.norm(vector)), 6),
            })
    print(json.dumps({"ok": True, "model": MODEL, "device": device,
                      "embeddings": receipts}, sort_keys=True))


if __name__ == "__main__":
    main()
