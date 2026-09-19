"""Stream the exact quantized tied-output matrix and expose promoted/suppressed tokens."""

from __future__ import annotations

import heapq
import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .io import atomic_json


def _gguf_module(root: Path):
    candidate = Path(os.environ.get("LLAMA_CPP_GGUF_PY", root / ".build" / "llama.cpp" / "gguf-py"))
    if not candidate.exists():
        raise ValueError("gguf-py not found; build the pinned extractor or set LLAMA_CPP_GGUF_PY")
    sys.path.insert(0, str(candidate))
    return importlib.import_module("gguf")


def _tokens(reader: Any) -> list[str]:
    field = reader.get_field("tokenizer.ggml.tokens")
    if field is None:
        raise ValueError("model has no tokenizer.ggml.tokens")
    return [bytes(field.parts[index]).decode("utf-8", errors="replace") for index in field.data]


def analyze(model: Path, direction_dir: Path, root: Path, limit: int = 50, chunk: int = 1024) -> dict[str, Any]:
    gguf = _gguf_module(root)
    values = np.load(direction_dir / "direction.npz", allow_pickle=False)
    direction = values["direction"].astype(np.float32)
    reader = gguf.GGUFReader(str(model), "r")
    tensor = next((item for item in reader.tensors if item.name == "output.weight"), None)
    source = "output.weight"
    if tensor is None:
        tensor = next((item for item in reader.tensors if item.name == "token_embd.weight"), None)
        source = "token_embd.weight_tied_output"
    if tensor is None:
        raise ValueError("no output or tied token-embedding tensor")
    if int(tensor.shape[0]) != direction.size:
        raise ValueError(f"unembedding width {tensor.shape[0]} != direction {direction.size}")
    vocab = _tokens(reader)
    if len(vocab) != int(tensor.shape[1]):
        raise ValueError("vocabulary and output matrix disagree")
    high: list[tuple[float, int]] = []
    low: list[tuple[float, int]] = []
    for start in range(0, len(vocab), chunk):
        stop = min(start + chunk, len(vocab))
        block = gguf.dequantize(tensor.data[start:stop], tensor.tensor_type).astype(np.float64)
        scores = np.einsum("ij,j->i", block, direction.astype(np.float64), optimize=False)
        if not np.isfinite(scores).all():
            raise ValueError(f"non-finite unembedding projection in token rows {start}:{stop}")
        for offset, score in enumerate(scores):
            token_id = start + offset; value = float(score)
            if len(high) < limit: heapq.heappush(high, (value, token_id))
            elif value > high[0][0]: heapq.heapreplace(high, (value, token_id))
            item = (-value, token_id)
            if len(low) < limit: heapq.heappush(low, item)
            elif item > low[0]: heapq.heapreplace(low, item)
    promoted = [{"token_id": idx, "token": vocab[idx], "score": score} for score, idx in sorted(high, reverse=True)]
    suppressed = [{"token_id": idx, "token": vocab[idx], "score": -neg} for neg, idx in sorted(low, reverse=True)]
    report = {
        "schema": 1, "tensor": source, "quantization_type": int(tensor.tensor_type),
        "vocabulary_size": len(vocab), "direction_width": int(direction.size),
        "promoted": promoted, "suppressed": suppressed,
        "status": "produced_pending_human_semantic_review",
        "truth_status": "exact_quantized_weight_projection_not_interpretation",
    }
    atomic_json(direction_dir / "unembedding.json", report)
    return report


def review(direction_dir: Path, reviewer: str, passed: bool, note: str) -> dict[str, Any]:
    evidence = json.loads((direction_dir / "unembedding.json").read_text(encoding="utf-8"))
    validation_path = direction_dir / "validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    verdict = "passed" if passed else "failed"
    validation["unembedding"] = {
        "status": verdict, "reviewer": reviewer, "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "note": note[:1000], "tensor": evidence["tensor"], "admission_blocking": not passed,
    }
    atomic_json(validation_path, validation)
    return validation["unembedding"]
