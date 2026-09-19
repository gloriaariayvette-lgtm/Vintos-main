"""Read only explicit offline artifacts and write results atomically."""

from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Any, Iterable

import numpy as np

MAGIC = 0x56525344


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no}: row is not an object")
            rows.append(value)
    return rows


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read_residual(path: Path) -> np.ndarray:
    with path.open("rb") as handle:
        header = handle.read(16)
        if len(header) != 16:
            raise ValueError(f"short residual header: {path}")
        magic, version, layers, embd = struct.unpack("<IIII", header)
        if magic != MAGIC or version != 1 or not layers or not embd:
            raise ValueError(f"invalid residual header: {path}")
        data = np.fromfile(handle, dtype="<f4")
    expected = layers * embd
    if data.size != expected:
        raise ValueError(f"residual size mismatch: {path}: {data.size} != {expected}")
    matrix = data.reshape(layers, embd).astype(np.float64)
    if not np.isfinite(matrix).all():
        raise ValueError(f"non-finite residual: {path}")
    return matrix
