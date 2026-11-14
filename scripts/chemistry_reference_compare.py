#!/usr/bin/env python3
"""Check one of his predicted structures against a real experimental one (Grok Bot, 2026-10-06: "After the
O43511 STAS run: a real structure to check it against"; Gloria installed tmtools for it).

Runs in the Lab's own Python (the ESMFold environment, which has tmtools, BioPython and numpy). One JSON request
on stdin, one JSON receipt on stdout:

    {"model": "artifacts/esmfold/O43511-....pdb" or "O43511",      his ESMFold model (newest for an accession)
     "reference": "8SGW", "chain": "C",                             an RCSB entry and its chain
     "ref_span": [535, 729],                                        the stretch to compare, in the entry's numbering
     "offset": 0}                                                   optional: entry number + offset = his number

8SGW is numbered as human pendrin across 520-740 (Grok Bot, 7 October, correcting the five-residue shift it gave on
6 October: the pig UniProt entry is shifted, the deposited file is not), its STAS is described on chains C and D, and
586-653 has no density. The offset is worked out from the sequence alignment itself (the commonest model-minus-entry
number over the aligned residues in the span); a supplied offset that disagrees with it is refused, because it would
only relabel the results (the structural alignment does not use it): with -5, the gap 586-653 is reported as
581-648 and every helix five places off (2026-10-08).

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
from collections import Counter
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
    offset = req.get("offset")
    # The planner sometimes appends the chain to the entry id ("1ABC_A", "1ABCA"); split it off so a well-formed
    # reference is not refused. A UniProt accession is not a PDB id and is still refused, now with a reason that says so.
    if not PDB_ID.fullmatch(ref):
        m = re.fullmatch(r"([0-9][A-Za-z0-9]{3})[ _-]?([A-Za-z0-9])", ref)
        if m:
            ref = m.group(1)
            if not req.get("chain"):
                chain = m.group(2)
    if not PDB_ID.fullmatch(ref):
        # name what was given and where a real id comes from: on 25 October all 10 compares were refused here, each
        # given a protein name or UniProt accession, and the bare refusal never said what to fetch instead
        raise ValueError("reference must be a four-character PDB entry id such as 1ABC (a deposited structure to "
                         "compare the model against, not a protein name or UniProt accession); got %r. Take the id "
                         "from a pdb source step's records or the structure's receipt"
                         % str(req.get("reference") or "")[:40])
    if not CHAIN.fullmatch(chain):
        raise ValueError("chain must be a chain id")
    if not (isinstance(span, list) and len(span) == 2 and all(isinstance(x, int) for x in span)
            and 0 < span[0] < span[1] and span[1] - span[0] <= MAX_SPAN):
        raise ValueError("ref_span must be [first, last] residue numbers in the entry")
    if offset is not None and (not isinstance(offset, int) or isinstance(offset, bool) or abs(offset) > 2000):
        raise ValueError("offset must be a whole number, or left out")
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


AGREE = 0.9     # share of aligned residues that must share one numbering shift for it to label the results


def numbering(pairs, model_res, ref_res, offset=None):
    """(offset, agreement): the shift from the entry's numbers to his, from the aligned residues themselves. A
    supplied offset that disagrees with it is refused (ValueError), naming the one the alignment gives."""
    diffs = Counter(model_res[i][0] - ref_res[j][0] for i, j in pairs)
    derived, n = diffs.most_common(1)[0]
    agree = n / sum(diffs.values())
    if offset is not None and offset != derived:
        i, j = next((i, j) for i, j in pairs if model_res[i][0] - ref_res[j][0] == derived)
        raise ValueError("offset %d disagrees with the sequence alignment, which puts the entry's residue %d at your "
                         "residue %d (offset %d, for %.0f%% of the aligned residues). Leave offset out, or give %d."
                         % (offset, ref_res[j][0], model_res[i][0], derived, agree * 100, derived))
    return derived, agree


def gaps_in(present, span, offset):
    """The entry's residue numbers in the span with no coordinates (no density), as [first, last] runs in his numbering."""
    gaps, run = [], []
    for n in range(span[0], span[1] + 1):
        if n in present:
            continue
        if run and n != run[-1] + 1:
            gaps.append([run[0] + offset, run[-1] + offset]); run = []
        run.append(n)
    if run:
        gaps.append([run[0] + offset, run[-1] + offset])
    return gaps


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


def _cif_values(d, key):
    """One mmCIF item as a list of its real values ('?' and '.' are mmCIF for "not given")."""
    v = d.get(key)
    v = v if isinstance(v, list) else ([] if v is None else [v])
    return [str(x).strip() for x in v if str(x).strip() not in ("", "?", ".")]


def reference_identity(path, chain=None):
    """(title, organism) of the entry, from its own mmCIF; either is None when the file does not give it.

    12 November: a comparison said "TM 0.929 against 7WK1" and nothing else about the entry, and a blind sufficiency
    check accepted it as an answer about flowering plants; 7WK1 is mouse pendrin. The organism is the compared
    chain's own entity when the file ties the chain to one, else every source organism the entry names."""
    from Bio.PDB.MMCIF2Dict import MMCIF2Dict
    try:
        d = MMCIF2Dict(str(path))
    except Exception:
        return None, None
    title = (_cif_values(d, "_struct.title") or [None])[0]
    entity = None
    if chain:
        asym = d.get("_atom_site.auth_asym_id"); ent = d.get("_atom_site.label_entity_id")
        if isinstance(asym, list) and isinstance(ent, list):
            entity = next((e for a, e in zip(asym, ent) if a == chain), None)
    organisms = []
    for id_key, name_key in (("_entity_src_gen.entity_id", "_entity_src_gen.pdbx_gene_src_scientific_name"),
                             ("_entity_src_nat.entity_id", "_entity_src_nat.pdbx_organism_scientific_name"),
                             ("_pdbx_entity_src_syn.entity_id", "_pdbx_entity_src_syn.organism_scientific")):
        names = d.get(name_key)
        names = names if isinstance(names, list) else ([] if names is None else [names])
        ids = d.get(id_key)
        ids = ids if isinstance(ids, list) else ([] if ids is None else [ids])
        rows = list(zip(ids, names)) if len(ids) == len(names) else [(None, n) for n in names]
        if entity is not None and any(i == entity for i, _ in rows):
            rows = [(i, n) for i, n in rows if i == entity]
        organisms += [str(n).strip() for _, n in rows if str(n).strip() not in ("", "?", ".")]
        if organisms:
            break
    organism = ", ".join(dict.fromkeys(organisms)) or None
    return title, organism


def identity_line(title, organism):
    """The display line that says what the entry is, so no reader takes a TM-score for a species it is not."""
    if not title and not organism:
        return "the entry is: (its file gives no title and no source organism)"
    return "the entry is: %s (%s)" % (title or "(no title in its file)", organism or "source organism not given in its file")


# A next question that asks for a comparison against a deposited structure but names no entry cannot run:
# reference_compare needs a four-character PDB id and a ref_span (13 November: refused 32+ times in one day).
NO_REFERENCE_NAMED = "(no reference structure named)"
_NAMED_ENTRY = re.compile(r"(?<![A-Za-z0-9])[0-9](?=[A-Za-z0-9]{3}(?![A-Za-z0-9]))[A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*")
_ASKS_COMPARE = re.compile(r"reference_compare|structure\.compare|\b(?:compar\w*|tm-?score|rmsd|deviat\w*|superpos\w*|"
                           r"align\w*|conserv\w*)\b", re.I)
_TO_A_STRUCTURE = re.compile(r"reference_compare|structure\.compare|\b(?:reference|experimental|deposited|crystal|"
                             r"cryo-?em|pdb)\b", re.I)


def names_no_reference(text):
    """True when the text asks for a comparison against a reference structure without naming its PDB entry."""
    text = str(text or "")
    return bool(_ASKS_COMPARE.search(text) and _TO_A_STRUCTURE.search(text) and not _NAMED_ENTRY.search(text))


def mark_unnamed_reference(text):
    """The text, with NO_REFERENCE_NAMED after it when it asks for a comparison it names no entry for."""
    text = str(text or "")
    if not text.strip() or NO_REFERENCE_NAMED in text or not names_no_reference(text):
        return text
    return text.rstrip() + " " + NO_REFERENCE_NAMED


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
    offset, agreement = numbering(pairs, model_res, ref_res, offset)
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
    gaps = gaps_in(present, span, offset)
    identity = sum(a == b for a, b in zip(seq_m, seq_r)) / len(pairs)
    title, organism = reference_identity(ref_path, chain)
    # second, so it survives the Lab's 1,500-character receipt summary and a checker's shortened excerpt
    lines = ["%s vs %s chain %s, residues %d-%d of the entry (%d-%d of his protein)" % (
                 model_path.name, ref, chain, span[0], span[1], span[0] + offset, span[1] + offset),
             identity_line(title, organism),
             "compared: %d residues present in both, %.0f%% identical" % (len(pairs), identity * 100),
             "numbering: entry number %+d = his number, from the alignment (%.0f%% of aligned residues agree)%s" % (
                 offset, agreement * 100, "" if agreement >= AGREE else "; NOT one shift, so positions below are approximate"),
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
        "reference": ref, "reference_title": title, "reference_organism": organism, "chain": chain, "ref_span": span, "offset": offset, "offset_from": "sequence alignment",
        "offset_agreement": round(agreement, 3), "compared": len(pairs),
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
