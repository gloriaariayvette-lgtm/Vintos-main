#!/usr/bin/env python3
"""What is actually in one of his ESMFold models: confidence per residue and helix/strand per residue, read from
the model file itself (Gloria, 2026-10-07; his own words on 6 October: "the fold output has no secondary-structure
channel at all ... I mis-modeled my own instrument").

ESMFold writes each residue's confidence (pLDDT) into the model's B-factor column; the Lab kept only the mean. The
helix/strand call is made from the model's own CA geometry, P-SEA style (Labesse et al. 1997): distances from each
CA to the CAs two, three and four residues on. A strand is also required to lie beside another extended stretch
(a CA 4.2-5.6 A away, at least three residues off), so a loose extended loop is not called a strand. It is a
geometric reading of a prediction, not DSSP and not an experimental structure.

As a script: one JSON request on stdin {"model": path, "range": [first, last] (optional, his numbering)}, one JSON
receipt on stdout. As a module: read_pdb(text) and summary(read, first, last).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WS = Path(os.environ.get("SPARK_WORKSPACE", "~/.vintos/workspace")).expanduser().resolve()
ARTIFACTS = WS / "memory" / "chemistry-lab" / "artifacts"
# P-SEA distance windows (A): CA(i) to CA(i+2), CA(i+3), CA(i+4)
HELIX = ((5.0, 6.0), (4.8, 5.8), (5.8, 7.0))
STRAND = ((5.8, 7.2), (9.0, 10.8), (11.3, 13.5))
PAIR = (4.2, 5.6)
MIN_HELIX, MIN_STRAND = 5, 3
BANDS = ((90, "very high"), (70, "confident"), (50, "low"), (0, "very low"))


def read_pdb(text):
    """{'residues': [(number, one-letter-ish name, (x,y,z) of CA, plddt)], 'ss': 'HHHEE--...'} from PDB text."""
    rows, seen = [], set()
    for line in str(text).splitlines():
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        key = (line[21], line[22:27])
        if key in seen:
            continue
        seen.add(key)
        try:
            xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            b = float(line[60:66])
        except ValueError:
            continue
        rows.append((int(line[22:26]), line[17:20].strip(), xyz, b))
    if rows and max(r[3] for r in rows) <= 1.0:          # transformers' ESMFold writes 0..1
        rows = [(n, name, xyz, b * 100.0) for n, name, xyz, b in rows]
    return {"residues": rows, "ss": assign([r[2] for r in rows])}


def _d(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _fits(ca, i, windows):
    for k, (lo, hi) in zip((2, 3, 4), windows):
        if i + k >= len(ca) or not lo <= _d(ca[i], ca[i + k]) <= hi:
            return False
    return True


def assign(ca):
    """One letter per residue: H helix, E strand, - neither."""
    n = len(ca)
    ss = ["-"] * n
    for i in range(n):
        if _fits(ca, i, HELIX):
            for j in range(i, min(n, i + 5)):
                ss[j] = "H"
    ext = [False] * n
    for i in range(n):
        if ss[i] != "H" and _fits(ca, i, STRAND):
            for j in range(i, min(n, i + 5)):
                ext[j] = ext[j] or ss[j] != "H"
    for i in range(n):
        if ext[i] and any(ext[j] and abs(i - j) >= 3 and PAIR[0] <= _d(ca[i], ca[j]) <= PAIR[1] for j in range(n)):
            ss[i] = "E"
    out = "".join(ss)
    for letter, least in (("H", MIN_HELIX), ("E", MIN_STRAND)):    # too short to call: back to nothing
        out = "".join("-" if c == letter and _run(out, i, letter) < least else c for i, c in enumerate(out))
    return out


def _run(s, i, letter):
    a = i
    while a > 0 and s[a - 1] == letter:
        a -= 1
    b = i
    while b + 1 < len(s) and s[b + 1] == letter:
        b += 1
    return b - a + 1


def _segments(numbers, labels):
    out, start = [], 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start] or numbers[i] != numbers[i - 1] + 1:
            out.append((labels[start], numbers[start], numbers[i - 1]))
            start = i
    return out


def _band(p):
    return next(name for floor, name in BANDS if p >= floor)


def summary(read, first=None, last=None):
    rows = [r for r in read["residues"] if (first is None or r[0] >= first) and (last is None or r[0] <= last)]
    if not rows:
        raise ValueError("no residues of the model in %s-%s" % (first, last))
    index = {r[0]: k for k, r in enumerate(read["residues"])}
    nums = [r[0] for r in rows]
    ss = "".join(read["ss"][index[n]] for n in nums)
    plddt = [round(r[3], 1) for r in rows]
    helices = [[a, b] for kind, a, b in _segments(nums, list(ss)) if kind == "H"]
    strands = [[a, b] for kind, a, b in _segments(nums, list(ss)) if kind == "E"]
    bands = [[name, a, b] for name, a, b in _segments(nums, [_band(p) for p in plddt])]
    lines = ["residues %d-%d: %d helix, %d strand, %d neither; mean pLDDT %.1f" % (
                 nums[0], nums[-1], ss.count("H"), ss.count("E"), ss.count("-"), sum(plddt) / len(plddt)),
             "helices: " + (", ".join("%d-%d" % tuple(h) for h in helices) or "none"),
             "strands: " + (", ".join("%d-%d" % tuple(s) for s in strands) or "none"),
             "confidence: " + "; ".join("%s %d-%d" % tuple(b) for b in bands)]
    return {"range": [nums[0], nums[-1]], "secondary_structure": ss, "helices": helices, "strands": strands,
            "plddt_by_residue": plddt, "confidence_bands": bands, "mean_plddt": round(sum(plddt) / len(plddt), 2),
            "display": lines, "method": "CA-geometry assignment (P-SEA style) on the predicted model; not DSSP, "
                                        "not an experimental structure"}


def _inside(path, root):
    try:
        return os.path.commonpath((str(root.resolve()), str(path.resolve()))) == str(root.resolve())
    except (OSError, ValueError):
        return False


def main():
    try:
        req = json.load(sys.stdin)
        path = Path(str(req.get("model") or ""))
        path = path if path.is_absolute() else WS / "memory" / "chemistry-lab" / path
        if not str(path).endswith(".pdb") or not path.is_file() or not _inside(path, ARTIFACTS):
            raise ValueError("model must be a .pdb the Lab made")
        rng = req.get("range") or [None, None]
        if not (isinstance(rng, list) and len(rng) == 2):
            raise ValueError("range must be [first, last]")
        out = summary(read_pdb(path.read_text()), *rng)
        out["model"] = path.name
        print(json.dumps({"ok": True, "result": out}))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
