#!/usr/bin/env python3
"""Chemistry structure gallery.

Law: only bounded, already-produced PDB/mmCIF artifacts below the Chemistry Lab's
artifact root may become view data.  Parsing is a read receipt, never a claim that
the predicted structure is biologically true, and this module never writes or
reaches the network.
"""
from __future__ import annotations

import gzip
import hashlib
import os
import shlex
from pathlib import Path

WS = Path(os.environ.get("SPARK_WORKSPACE", "~/.vintos/workspace")).expanduser().resolve()
ROOT = WS / "memory" / "chemistry-lab" / "artifacts"
MAX_FILES = 80
MAX_COMPRESSED_BYTES = 4 * 1024 * 1024
MAX_TEXT_BYTES = 12 * 1024 * 1024
MAX_ATOMS = 6000


def _allowed(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".pdb") or name.endswith(".cif") or name.endswith(".cif.gz")


def _inside(path: Path) -> bool:
    try:
        return os.path.commonpath((str(ROOT.resolve()), str(path.resolve()))) == str(ROOT.resolve())
    except (OSError, ValueError):
        return False


def _files() -> list[Path]:
    if not ROOT.is_dir(): return []
    rows = [p for p in ROOT.rglob("*") if p.is_file() and not p.is_symlink() and _allowed(p) and _inside(p)]
    rows.sort(key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)
    return rows[:MAX_FILES]


def _id(path: Path) -> str:
    return hashlib.sha256(str(path.relative_to(ROOT)).encode()).hexdigest()[:20]


def inventory(limit: int = 24) -> list[dict]:
    """Return bounded metadata only; paths remain relative to the Lab artifact root."""
    limit = max(1, min(int(limit), 40))
    out = []
    for path in _files()[:limit]:
        rel = str(path.relative_to(ROOT))
        kind = "mmcif" if path.name.lower().endswith((".cif", ".cif.gz")) else "pdb"
        out.append({"artifact_id": _id(path), "name": path.name.removesuffix(".gz"),
                    "kind": kind, "source": rel, "bytes": path.stat().st_size,
                    "truth_status": "computational_structure_artifact_not_biological_fact"})
    return out


def _read(path: Path) -> str:
    size = path.stat().st_size
    if size > MAX_COMPRESSED_BYTES: raise ValueError("structure artifact exceeds compressed-size bound")
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        text = handle.read(MAX_TEXT_BYTES + 1)
    if len(text.encode("utf-8", errors="replace")) > MAX_TEXT_BYTES:
        raise ValueError("structure artifact exceeds expanded-size bound")
    return text


def _atom(x, y, z, element, name, chain, residue, seq):
    return {"x": round(float(x), 4), "y": round(float(y), 4), "z": round(float(z), 4),
            "element": str(element or "C").upper()[:2], "name": str(name or "")[:6],
            "chain": str(chain or "")[:8], "residue": str(residue or "")[:8],
            "seq": str(seq or "")[:12]}


def _pdb(text: str) -> list[dict]:
    atoms = []
    for line in text.splitlines():
        if not line.startswith(("ATOM  ", "HETATM")): continue
        try:
            name = line[12:16].strip(); element = line[76:78].strip() or "".join(c for c in name if c.isalpha())[:1]
            atoms.append(_atom(line[30:38], line[38:46], line[46:54], element, name,
                               line[21:22].strip(), line[17:20].strip(), line[22:26].strip()))
        except (TypeError, ValueError):
            continue
        if len(atoms) >= MAX_ATOMS: break
    return atoms


def _cif(text: str) -> list[dict]:
    lines = text.splitlines(); headers = []; atoms = []; i = 0
    while i < len(lines):
        if lines[i].strip() != "loop_": i += 1; continue
        i += 1; headers = []
        while i < len(lines) and lines[i].strip().startswith("_atom_site."):
            headers.append(lines[i].strip()); i += 1
        if not headers: continue
        keys = {name.split(".", 1)[1]: n for n, name in enumerate(headers)}
        needed = ("Cartn_x", "Cartn_y", "Cartn_z")
        if not all(k in keys for k in needed): continue
        while i < len(lines):
            raw = lines[i].strip()
            if not raw or raw == "#" or raw == "loop_" or raw.startswith("_"): break
            try: fields = shlex.split(raw)
            except ValueError: fields = raw.split()
            if len(fields) >= len(headers) and fields[0] in ("ATOM", "HETATM"):
                get = lambda *names: next((fields[keys[n]] for n in names if n in keys), "")
                try:
                    atoms.append(_atom(get("Cartn_x"), get("Cartn_y"), get("Cartn_z"),
                                       get("type_symbol"), get("label_atom_id", "auth_atom_id"),
                                       get("auth_asym_id", "label_asym_id"),
                                       get("auth_comp_id", "label_comp_id"),
                                       get("auth_seq_id", "label_seq_id")))
                except (TypeError, ValueError): pass
                if len(atoms) >= MAX_ATOMS: return atoms
            i += 1
        if atoms: return atoms
    return atoms


def structure(artifact_id: str) -> dict:
    """Resolve an opaque inventory id and return finite display coordinates only."""
    wanted = str(artifact_id)[:32]
    path = next((p for p in _files() if _id(p) == wanted), None)
    if path is None: return {"ok": False, "artifact_id": wanted, "error": "structure artifact not found"}
    text = _read(path); atoms = _cif(text) if path.name.lower().endswith((".cif", ".cif.gz")) else _pdb(text)
    if not atoms: return {"ok": False, "artifact_id": wanted, "error": "structure contained no readable atoms"}
    rel = str(path.relative_to(ROOT))
    return {"ok": True, "artifact_id": wanted, "name": path.name.removesuffix(".gz"),
            "kind": "mmcif" if ".cif" in path.name.lower() else "pdb", "source": rel,
            "atoms": atoms, "atom_count": len(atoms), "truncated": len(atoms) == MAX_ATOMS,
            "truth_status": "parsed_from_computational_structure_artifact_not_biological_fact"}

