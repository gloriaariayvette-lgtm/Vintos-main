#!/usr/bin/env python3
"""Check one of his predicted structures against a real experimental one (Grok Bot, 2026-10-06: "After the
O43511 STAS run: a real structure to check it against"; Gloria installed tmtools for it).

Runs in the Lab's own Python (the ESMFold environment, which has tmtools, BioPython and numpy). One JSON request
on stdin, one JSON receipt on stdout:

    {"model": "artifacts/esmfold/O43511-....pdb" or "O43511",      his ESMFold model (newest for an accession)
     "reference": "8SGW", "chain": "A",                             an RCSB entry and its chain
     "ref_span": [540, 734],                                        the stretch to compare, in the entry's numbering
     "offset": -5}                                                  entry number + offset = his protein's number

The model and the entry are lined up by their sequences, so a fragment model, a shifted numbering and a loop the
entry leaves out (pendrin's IVS has no density) need no guessing: only residues present in both, inside the span,
are compared. TM-align is run on that fixed alignment (and once free, for contrast). The entry's own helices and
strands are reported in his protein's numbering, each with how far the model sits from it after superposition.

What this is not: the entry is another species and, for pendrin, a domain-swapped dimer while ESMFold folded one
chain, so a difference can be real biology, not an error. A model is never proven by this; it is compared.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

WS = Path(os.environ.get("SPARK_WORKSPACE", "~/.vintos/workspace")).expanduser().resolve()
LAB = WS / "memory" / "chemistry-lab"
ARTIFACTS = LAB / "artifacts"
MODELS = ARTIFACTS / "esmfold"
REFERENCES = ARTIFACTS / "reference"
RCSB = "https://files.rcsb.org/download/%s.cif"
MAX_REFERENCE_BYTES = 40 * 1024 * 1024
MAX_SPAN = 1200
PDB_ID = re.compile(r"[0-9][A-Za-z0-9]{3}")
CHAIN = re.compile(r"[A-Za-z0-9]{1,4}")
ACCESSION = re.compile(r"[A-Z0-9]{6,10}(?:-[1-9][0-9]*)?")


def _inside(path, root):
    try:
        return os.path.commonpath((str(root.resolve()), str(path.resolve()))) == str(root.resolve())
    except (OSError, ValueError):
        return False


def _model_path(name):
    name = str(name or "").strip()
    if ACCESSION.fullmatch(name.upper()):
        found = sorted(MODELS.glob(name.upper() + "-*.pdb"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not found:
            raise ValueError("no ESMFold model of %s in the Lab" % name.upper())
        return found[0]
    path = (LAB / name) if not os.path.isabs(name) else Path(name)
    if not name.lower().endswith(".pdb") or not path.is_file() or not _inside(path, ARTIFACTS):
        raise ValueError("model must be a .pdb the Lab made, or an accession it has a model of")
    return path


def validate(req):
    if not isinstance(req, dict):
        raise ValueError("request must be an object")
    ref = str(req.get("reference") or "").strip().upper()
    chain = str(req.get("chain") or "A").strip()
    span = req.get("ref_span")
    offset = req.get("offset", 0)
    if not PDB_ID.fullmatch(ref):
        raise ValueError("reference must be a four-character PDB id")
    if not CHAIN.fullmatch(chain):
        raise ValueError("chain must be a chain id")
    if not (isinstance(span, list) and len(span) == 2 and all(isinstance(x, int) for x in span)
            and 0 < span[0] < span[1] and span[1] - span[0] <= MAX_SPAN):
        raise ValueError("ref_span must be [first, last] residue numbers in the entry")
    if not isinstance(offset, int) or abs(offset) > 2000:
        raise ValueError("offset must be a whole number")
    return _model_path(req.get("model")), ref, chain, span, offset


def fetch_reference(ref, get=None):
    """The entry's mmCIF, kept under the Lab's artifacts; fetched once from RCSB."""
    REFERENCES.mkdir(parents=True, exist_ok=True)
    path = REFERENCES / (ref + ".cif")
    if path.is_file() and path.stat().st_size > 0:
        return path
    if get is None:
        def get(url):
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "vintos-lab"}), timeout=120) as r:
                return r.read(MAX_REFERENCE_BYTES + 1)
    data = get(RCSB % ref)
    if not data or len(data) > MAX_REFERENCE_BYTES or b"_atom_site" not in data[:MAX_REFERENCE_BYTES]:
        raise RuntimeError("RCSB did not return a structure for %s" % ref)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


def _residues(structure, chain_id=None):
    """[(number, one-letter, CA xyz)] for the standard residues of one chain (the first, when none is named)."""
    from Bio.SeqUtils import seq1
    model = next(iter(structure))
    chains = [c for c in model if chain_id is None or c.id == chain_id]
    if not chains:
        raise ValueError("chain %s is not in the entry" % chain_id)
    out = []
    for res in chains[0]:
        if res.id[0] != " " or "CA" not in res:
            continue
        aa = seq1(res.get_resname())
        if aa and aa != "X":
            out.append((res.id[1], aa, [float(v) for v in res["CA"].coord]))
    return out


def _pairs(model_res, ref_res):
    """(model index, reference index) for residues the sequence alignment puts together."""
    from Bio.Align import PairwiseAligner
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.match_score, aligner.mismatch_score = 2, -1
    aligner.open_gap_score, aligner.extend_gap_score = -10, -0.5
    aln = aligner.align("".join(r[1] for r in model_res), "".join(r[1] for r in ref_res))[0]
    pairs = []
    for (a0, a1), (b0, b1) in zip(*aln.aligned):
        pairs += list(zip(range(a0, a1), range(b0, b1)))
    return pairs


def _kabsch(p, q):
    """Rotation and translation that put p onto q (rows are points)."""
    import numpy as np
    pc, qc = p.mean(0), q.mean(0)
    h = (p - pc).T @ (q - qc)
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    rot = vt.T @ np.diag([1, 1, d]) @ u.T
    return rot, qc - pc @ rot.T


def secondary_structure(path, chain):
    """The entry's helices and strands on one chain, as [(kind, first, last)] in its numbering."""
    from Bio.PDB.MMCIF2Dict import MMCIF2Dict
    d = MMCIF2Dict(str(path))
    def rows(prefix, keys):
        cols = [d.get(prefix + k) for k in keys]
        if not all(cols):
            return []
        cols = [c if isinstance(c, list) else [c] for c in cols]
        return list(zip(*cols))
    out = []
    for kind, b, e, ch in rows("_struct_conf.", ("conf_type_id", "beg_auth_seq_id", "end_auth_seq_id", "beg_auth_asym_id")):
        if ch == chain and str(kind).upper().startswith("HELX"):
            out.append(("helix", int(b), int(e)))
    for b, e, ch in rows("_struct_sheet_range.", ("beg_auth_seq_id", "end_auth_seq_id", "beg_auth_asym_id")):
        if ch == chain:
            out.append(("strand", int(b), int(e)))
    return sorted(set(out), key=lambda x: x[1])


def compare(req, get=None):
    import numpy as np
    from Bio.PDB import MMCIFParser, PDBParser
    from tmtools import tm_align
    model_path, ref, chain, span, offset = validate(req)
    ref_path = fetch_reference(ref, get=get)
    model_res = _residues(PDBParser(QUIET=True).get_structure("model", str(model_path)))
    ref_res = _residues(MMCIFParser(QUIET=True).get_structure(ref, str(ref_path)), chain)
    if not model_res or not ref_res:
        raise RuntimeError("no residues to compare")
    pairs = [(i, j) for i, j in _pairs(model_res, ref_res) if span[0] <= ref_res[j][0] <= span[1]]
    if len(pairs) < 20:
        raise RuntimeError("only %d residues line up inside the span; nothing fair to compare" % len(pairs))
    p = np.array([model_res[i][2] for i, _ in pairs]); q = np.array([ref_res[j][2] for _, j in pairs])
    seq_m = "".join(model_res[i][1] for i, _ in pairs); seq_r = "".join(ref_res[j][1] for _, j in pairs)
    fixed = tm_align(p, q, seq_m, seq_r, [seq_m, seq_r])
    free = tm_align(p, q, seq_m, seq_r)
    rot, t = _kabsch(p, q)
    dev = np.linalg.norm(p @ rot.T + t - q, axis=1)
    rmsd = float(np.sqrt((dev ** 2).mean()))
    at = {ref_res[j][0]: float(dev[k]) for k, (_, j) in enumerate(pairs)}
    present = {r[0] for r in ref_res}
    elements = []
    for kind, b, e in secondary_structure(ref_path, chain):
        if e < span[0] or b > span[1]:
            continue
        d = [at[n] for n in range(b, e + 1) if n in at]
        elements.append({"kind": kind, "entry": [b, e], "protein": [b + offset, e + offset],
                         "compared": len(d), "mean_deviation_A": round(sum(d) / len(d), 2) if d else None})
    missing = [n for n in range(span[0], span[1] + 1) if n not in present]
    gaps, run = [], []
    for n in missing:
        if run and n != run[-1] + 1:
            gaps.append([run[0] + offset, run[-1] + offset]); run = []
        run.append(n)
    if run:
        gaps.append([run[0] + offset, run[-1] + offset])
    identity = sum(a == b for a, b in zip(seq_m, seq_r)) / len(pairs)
    lines = ["%s vs %s chain %s, residues %d-%d of the entry (%d-%d of his protein)" % (
                 model_path.name, ref, chain, span[0], span[1], span[0] + offset, span[1] + offset),
             "compared: %d residues present in both, %.0f%% identical" % (len(pairs), identity * 100),
             "TM-score on the sequence alignment: %.3f (by his model), %.3f (by the entry); RMSD %.2f A" % (
                 fixed.tm_norm_chain1, fixed.tm_norm_chain2, rmsd),
             "TM-align left free: %.3f / %.3f, RMSD %.2f A" % (free.tm_norm_chain1, free.tm_norm_chain2, free.rmsd)]
    if gaps:
        lines.append("not in the entry (no density, left out): " + ", ".join("%d-%d" % tuple(g) for g in gaps))
    for el in elements:
        lines.append("%s %d-%d (entry %d-%d): %s" % (el["kind"], el["protein"][0], el["protein"][1], el["entry"][0],
                     el["entry"][1], ("mean %.2f A from his model" % el["mean_deviation_A"]) if el["compared"]
                     else "not in his model"))
    if not elements:
        lines.append("the entry names no helices or strands in this span")
    return {"ok": True, "result": {
        "model": str(model_path.relative_to(WS)) if _inside(model_path, WS) else model_path.name,
        "reference": ref, "chain": chain, "ref_span": span, "offset": offset, "compared": len(pairs),
        "identity": round(identity, 3), "tm_fixed": [round(fixed.tm_norm_chain1, 4), round(fixed.tm_norm_chain2, 4)],
        "tm_free": [round(free.tm_norm_chain1, 4), round(free.tm_norm_chain2, 4)], "rmsd_A": round(rmsd, 3),
        "missing_in_entry": gaps, "elements": elements, "display": lines,
        "truth_status": "comparison_to_an_experimental_structure_of_another_species_not_proof"}}


def main():
    try:
        print(json.dumps(compare(json.load(sys.stdin)), ensure_ascii=False)); return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})); return 2


if __name__ == "__main__":
    raise SystemExit(main())
