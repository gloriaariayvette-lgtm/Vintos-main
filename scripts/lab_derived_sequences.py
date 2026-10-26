#!/usr/bin/env python3
"""Provenance for sequences his own design instruments made, so a refold can be compared.

The native instruments (`lab_native_instruments`) already emit design artifacts: ProteinMPNN
writes a FASTA of candidate sequences for a sourced backbone. Nothing joined that output to the
fold lane, so a designed sequence could only be folded by handing it a natural UniProt accession
it does not have. This module is that join, and it refuses the shortcut:

  register(receipt)      one record per candidate sequence, with the design artifact's hash, the
                         sourced parent structure's hash, and a derived id minted from both. The
                         parent's accession is kept as the parent's, never as this sequence's.
  fold_request(id)       the body the fold lane takes for a derived sequence: a derived id and the
                         sequence, and no accession field at all.
  open_pilot/note_fold   the loop's bounds: one pilot a day, at most two candidates, two folds.
  compare_pilot(id)      how far each refold sits from the sourced backbone, as a distance-matrix
                         comparison (no superposition, so no fitting choices): model consistency.

What this is not: a refold that sits close to its parent backbone says the design model and the
folding model agree about it. It is not affinity, not stability, not a functional protein, and the
OpenMM lane beside it is a C-alpha elastic model, not atomistic validation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

WS = Path(os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace")))
LAB = WS / "memory" / "chemistry-lab"
ARTIFACTS = LAB / "artifacts"
DERIVED = ARTIFACTS / "derived"
LEDGER = LAB / "derived-pilots.json"

# The fold lane's own ceiling (chemistry_esmfold.MAX_LENGTH, measured on Aegis's RTX 5080, not extrapolated).
# Kept as a number here so this module stays importable without the fold lane; the suite checks the two agree.
MAX_LENGTH = 911
MIN_LENGTH = 4
AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
MAX_CANDIDATES = 2          # "at most two existing-tool candidates"
MAX_FOLDS_PER_PILOT = 2     # two folds and one comparison
PILOTS_PER_DAY = 1          # with two folds a pilot, this is the GPU bound the proposal asked for
GPU_MINUTES_CEILING = 20    # proposed ceiling per pilot; not a measured figure
DESIGN_INSTRUMENTS = {"protein_mpnn": "sequence.design"}
DERIVED_ID = re.compile(r"DRV-[0-9a-f]{12}")
PILOT_ID = re.compile(r"PILOT-[0-9a-f]{10}")
ACCESSION = re.compile(r"[A-Z0-9]{6,10}(?:-[1-9][0-9]*)?")
CLOSE_ANGSTROM = 2.0        # a residue pair counted as "held" in the distance comparison
MIN_COMPARED = 20           # fewer paired residues than this is nothing fair to compare
AA3 = {"ALA": "A", "CYS": "C", "ASP": "D", "GLU": "E", "PHE": "F", "GLY": "G", "HIS": "H", "ILE": "I",
       "LYS": "K", "LEU": "L", "MET": "M", "ASN": "N", "PRO": "P", "GLN": "Q", "ARG": "R", "SER": "S",
       "THR": "T", "VAL": "V", "TRP": "W", "TYR": "Y"}
TRUTH = "designed_sequence_derived_from_his_own_model_not_a_natural_protein"
COMPARE_TRUTH = "model_self_consistency_between_design_and_folding_not_affinity_or_function"


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _inside(path, root):
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


def _artifact(rel, suffix=None):
    """The file an artifact path names, checked to be a real file inside the Lab's artifact store."""
    rel = str(rel or "").strip()
    if not rel or os.path.isabs(rel) or ".." in Path(rel).parts:
        raise ValueError("artifact must be a path relative to the Lab, inside its artifact store")
    path = LAB / rel
    if path.is_symlink() or not path.is_file() or not _inside(path, ARTIFACTS):
        raise ValueError("no such Lab artifact: %s" % rel[:120])
    if suffix and not rel.endswith(suffix):
        raise ValueError("%s must be a %s artifact" % (rel[:120], suffix))
    return path


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def parent_accession(rel):
    """The accession the sourced backbone's own filename carries, or '' — the PARENT's identity, never the
    derived sequence's. ESMFold's models are named <ACCESSION>-<digest>.pdb."""
    stem = Path(str(rel)).name.split("-")[0].upper()
    return stem if ACCESSION.fullmatch(stem) else ""


def read_fasta(text):
    """[(header, sequence)] from a FASTA, in file order; sequences upper-cased with whitespace removed."""
    out = []
    for line in str(text).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            out.append([line[1:].strip(), ""])
        elif out:
            out[-1][1] += re.sub(r"\s+", "", line.upper())
    return [(h, s) for h, s in out if s]


def candidates(text):
    """The designed records of a ProteinMPNN FASTA: the ones its header marks as a sample. ProteinMPNN
    restates the input sequence as the first record; that is the backbone's own sequence, not a candidate."""
    records = read_fasta(text)
    designed = [(h, s) for h, s in records if "sample=" in h.lower()]
    return designed if designed else records[1:]


def _check_sequence(sequence):
    if not MIN_LENGTH <= len(sequence) <= MAX_LENGTH or any(c not in AMINO_ACIDS for c in sequence):
        raise ValueError("a candidate must be %d..%d standard amino acids" % (MIN_LENGTH, MAX_LENGTH))
    return sequence


def derived_id(design_sha256, sequence):
    return "DRV-" + hashlib.sha256((str(design_sha256) + "\x00" + sequence).encode()).hexdigest()[:12]


def register(receipt):
    """Records for the candidates in one native design receipt.

    `receipt` is a `lab_native_instruments.run()` result. Both hashes it names are recomputed from the
    files themselves: a receipt whose artifact has changed underneath it registers nothing.
    """
    if not isinstance(receipt, dict) or not receipt.get("ok"):
        raise ValueError("a completed native design receipt is required")
    skill = str(receipt.get("instrument") or "")
    if DESIGN_INSTRUMENTS.get(skill) != receipt.get("operation"):
        raise ValueError("this adapter takes a sequence-design receipt (%s)" % ", ".join(sorted(DESIGN_INSTRUMENTS)))
    inputs = receipt.get("inputs") or []
    if len(inputs) != 1:
        raise ValueError("a design receipt names exactly one sourced parent structure")
    parent_rel = str((inputs[0] or {}).get("file") or "")
    parent = _artifact(parent_rel, ".pdb")
    parent_sha = _sha256(parent)
    if (inputs[0] or {}).get("sha256") != parent_sha:
        raise ValueError("the parent structure has changed since the design ran; its hash does not match the receipt")
    fasta = [f for f in (receipt.get("files") or []) if str((f or {}).get("file") or "").endswith(".fa")]
    if len(fasta) != 1:
        raise ValueError("a design receipt names exactly one FASTA of candidates")
    design_rel = str(fasta[0]["file"])
    design = _artifact(design_rel, ".fa")
    design_sha = _sha256(design)
    if fasta[0].get("sha256") != design_sha:
        raise ValueError("the design artifact has changed since the receipt was written")
    found = candidates(design.read_text(encoding="utf-8", errors="replace"))
    if not found:
        raise ValueError("the design artifact holds no candidate sequence")
    if len(found) > MAX_CANDIDATES:
        raise ValueError("a pilot takes at most %d candidates; this artifact holds %d" % (MAX_CANDIDATES, len(found)))
    backbone = structure_sequence(parent.read_text(encoding="utf-8", errors="replace"))
    out = []
    for header, sequence in found:
        _check_sequence(sequence)
        ident = derived_id(design_sha, sequence)
        record = {
            "derived_id": ident, "sequence": sequence, "length": len(sequence),
            "instrument": skill, "operation": receipt.get("operation"),
            "design_artifact": design_rel, "design_sha256": design_sha, "design_header": str(header)[:300],
            "parent_structure": parent_rel, "parent_sha256": parent_sha,
            "parent_accession": parent_accession(parent_rel),
            "parent_accession_belongs_to": "the sourced parent structure, not this sequence",
            "natural_accession": None, "is_natural_sequence": False,
            "identity_to_parent_sequence": _identity(sequence, "".join(a for _, a, _ in backbone)),
            "registered_at": _now(), "truth_status": TRUTH,
        }
        write_json(DERIVED / (ident + ".json"), record)
        out.append(record)
    return out


def record(ident):
    """One registered record, with its id checked against the sequence and design hash it claims."""
    ident = str(ident or "").strip()
    if not DERIVED_ID.fullmatch(ident):
        raise ValueError("a derived sequence id looks like DRV-0123456789ab")
    path = DERIVED / (ident + ".json")
    if path.is_symlink() or not path.is_file():
        raise ValueError("no derived sequence %s is registered" % ident)
    data = json.loads(path.read_text(encoding="utf-8"))
    if derived_id(data.get("design_sha256"), str(data.get("sequence") or "")) != ident:
        raise ValueError("the record of %s does not match its id" % ident)
    return data


def fold_request(ident):
    """The fold body for a derived sequence: a derived id and the sequence, and no accession field.

    A designed sequence has no natural accession. Giving it one would file a model of his own design
    under a real protein's identity, so this request carries neither `accession` nor `sequence_source`.
    """
    data = record(ident)
    return {"derived_id": data["derived_id"], "sequence": data["sequence"],
            "provenance": {"instrument": data["instrument"], "operation": data["operation"],
                           "design_artifact": data["design_artifact"], "design_sha256": data["design_sha256"],
                           "parent_structure": data["parent_structure"], "parent_sha256": data["parent_sha256"],
                           "parent_accession": data["parent_accession"]},
            "is_natural_sequence": False, "truth_status": TRUTH}


def verify_fold_request(body):
    """The record a derived fold body names, or ValueError. The fold lane calls this instead of its
    natural-accession validator, and a body that mixes the two is refused rather than repaired."""
    if not isinstance(body, dict):
        raise ValueError("request must be an object")
    for field in ("accession", "sequence_source", "hp_mapping"):
        if body.get(field):
            raise ValueError("a designed sequence is not a natural protein: remove %s from a derived fold "
                             "request (its provenance is its parent's hashes, not an accession)" % field)
    data = record(body.get("derived_id"))
    sequence = re.sub(r"\s+", "", str(body.get("sequence") or "").upper())
    if sequence != data["sequence"]:
        raise ValueError("the sequence does not match what %s was registered with" % data["derived_id"])
    provenance = body.get("provenance") if isinstance(body.get("provenance"), dict) else {}
    for field in ("design_sha256", "parent_sha256"):
        if provenance.get(field) and provenance[field] != data[field]:
            raise ValueError("the request's %s does not match the registered provenance" % field)
    return data


# ---------------------------------------------------------------- the loop's bounds

def _ledger():
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    pilots = data.get("pilots")
    return {"pilots": pilots if isinstance(pilots, list) else []}


def pilots(day=None):
    rows = _ledger()["pilots"]
    return [p for p in rows if day is None or p.get("date") == day]


def pilot(pilot_id):
    for row in _ledger()["pilots"]:
        if row.get("pilot_id") == pilot_id:
            return row
    raise ValueError("no pilot %s" % str(pilot_id)[:40])


def open_pilot(derived_ids, *, today=None):
    """One pilot over one parent backbone and at most two of its candidates.

    Opening the same set again returns the pilot already open; a second, different pilot on the same
    day is refused, which is what keeps the fold work inside the ceiling the proposal asked for.
    """
    ids = [str(i) for i in (derived_ids or [])]
    if not 1 <= len(ids) <= MAX_CANDIDATES or len(set(ids)) != len(ids):
        raise ValueError("a pilot takes 1..%d distinct derived sequences" % MAX_CANDIDATES)
    records = [record(i) for i in ids]
    parents = {r["parent_structure"] for r in records}
    if len(parents) != 1:
        raise ValueError("the candidates of one pilot must come from one sourced parent structure")
    parent_rel = parents.pop()
    parent = _artifact(parent_rel, ".pdb")
    parent_sha = _sha256(parent)
    if {r["parent_sha256"] for r in records} != {parent_sha}:
        raise ValueError("the parent structure has changed since these candidates were registered")
    day = today or date.today().isoformat()
    ident = "PILOT-" + hashlib.sha256(("\x00".join([day, parent_rel] + sorted(ids))).encode()).hexdigest()[:10]
    data = _ledger()
    for row in data["pilots"]:
        if row.get("pilot_id") == ident:
            return row
    if len([p for p in data["pilots"] if p.get("date") == day]) >= PILOTS_PER_DAY:
        raise PermissionError("one derived design-and-refold pilot a day; %s already has one" % day)
    row = {"pilot_id": ident, "date": day, "opened_at": _now(), "parent_structure": parent_rel,
           "parent_sha256": parent_sha, "derived": sorted(ids), "folds": [],
           "gpu_minutes_ceiling": GPU_MINUTES_CEILING, "max_folds": MAX_FOLDS_PER_PILOT}
    data["pilots"].append(row)
    write_json(LEDGER, data)
    return row


def note_fold(pilot_id, ident, structure_rel):
    """Record one refold of a registered candidate against its pilot, inside the pilot's fold budget."""
    data = _ledger()
    row = next((p for p in data["pilots"] if p.get("pilot_id") == pilot_id), None)
    if row is None:
        raise ValueError("no pilot %s" % str(pilot_id)[:40])
    ident = record(ident)["derived_id"]
    if ident not in (row.get("derived") or []):
        raise ValueError("%s is not a candidate of this pilot" % ident)
    folds = row.setdefault("folds", [])
    if any(f.get("derived_id") == ident for f in folds):
        raise ValueError("%s has already been refolded in this pilot" % ident)
    if len(folds) >= int(row.get("max_folds") or MAX_FOLDS_PER_PILOT):
        raise PermissionError("this pilot's %d folds are used" % MAX_FOLDS_PER_PILOT)
    path = _artifact(structure_rel, ".pdb")
    folds.append({"derived_id": ident, "structure": str(structure_rel), "sha256": _sha256(path), "at": _now()})
    write_json(LEDGER, data)
    return row


# ---------------------------------------------------------------- the comparison

ESMFOLD_PYTHON = os.environ.get("VINTOS_ESMFOLD_PYTHON",
                                os.path.expanduser("~/.vintos/tools/chemistry-lab/esmc/bin/python"))


def fold_candidate(pilot_id, ident, *, run=None, admit=True):
    """Refold one registered candidate through the fold lane, inside this pilot's fold budget.

    The budget is checked before the GPU is asked for, not after, and foreground use is admitted first
    (`compute_admission`): a refold waits for her, it never preempts. The receipt is only recorded when
    the structure it names exists and is filed under the derived id, not under a natural accession.
    """
    import json as _json
    import subprocess
    row = pilot(str(pilot_id or "").strip())
    data = record(ident)
    if data["derived_id"] not in (row.get("derived") or []):
        raise ValueError("%s is not a candidate of this pilot" % data["derived_id"])
    folds = row.get("folds") or []
    if any(f.get("derived_id") == data["derived_id"] for f in folds):
        raise ValueError("%s has already been refolded in this pilot" % data["derived_id"])
    if len(folds) >= int(row.get("max_folds") or MAX_FOLDS_PER_PILOT):
        raise PermissionError("this pilot's %d folds are used" % MAX_FOLDS_PER_PILOT)
    if admit:
        import compute_admission
        compute_admission.admit("background", organ="lab-derived-refold", stage="esmfold")
    python = ESMFOLD_PYTHON if os.path.isfile(ESMFOLD_PYTHON) else "python3"
    script = str(Path(__file__).with_name("chemistry_esmfold.py"))
    done = (run or subprocess.run)([python, script], input=_json.dumps(fold_request(data["derived_id"])),
                                   text=True, capture_output=True, timeout=1800)
    try:
        out = _json.loads((done.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError("the refold gave no answer: %s" % (done.stderr or "")[-300:])
    if not out.get("ok"):
        raise RuntimeError(out.get("error") or "the refold failed")
    result = out["result"]
    if result.get("derived_id") != data["derived_id"] or result.get("requested_accession"):
        raise RuntimeError("the refold receipt does not name this designed sequence as its own identity")
    structure = str(result.get("structure_artifact") or "")
    marker = "memory/chemistry-lab/"
    if marker not in structure:
        raise RuntimeError("the refold's structure is not a Lab artifact")
    note_fold(row["pilot_id"], data["derived_id"], structure.split(marker, 1)[1])
    return result


def structure_sequence(pdb_text):
    """[(residue number, one-letter, (x, y, z))] over the C-alpha atoms of the first chain in a PDB."""
    out, chain = [], None
    for line in str(pdb_text).splitlines():
        if not line.startswith("ATOM") or len(line) < 54 or line[12:16].strip() != "CA":
            continue
        if line[16:17] not in (" ", "A"):
            continue
        if chain is None:
            chain = line[21:22]
        elif line[21:22] != chain:
            continue
        aa = AA3.get(line[17:20].strip().upper())
        try:
            number = int(line[22:26])
            xyz = tuple(float(line[i:i + 8]) for i in (30, 38, 46))
        except ValueError:
            continue
        if aa:
            out.append((number, aa, xyz))
    return out


def _identity(a, b):
    pairs = list(zip(str(a), str(b)))
    return round(sum(x == y for x, y in pairs) / len(pairs), 3) if pairs else None


def _distance_comparison(parent, model):
    """Distance-matrix comparison of two C-alpha traces paired by residue number.

    No superposition: every pair of residues present in both gives one distance in each structure, and
    the comparison is over those distances. Rotation and translation therefore cannot flatter a result,
    and no fitting choice is made on the Lab's behalf.
    """
    import math
    pa = {n: x for n, _, x in parent}
    pm = {n: x for n, _, x in model}
    shared = sorted(set(pa) & set(pm))
    if len(shared) < MIN_COMPARED:
        raise ValueError("only %d residues are in both structures; nothing fair to compare" % len(shared))
    def dist(p, q):
        return math.sqrt(sum((p[i] - q[i]) ** 2 for i in range(3)))
    total, close, worst, count = 0.0, 0, (0.0, None, None), 0
    for i, n in enumerate(shared):
        for m in shared[i + 1:]:
            delta = dist(pa[n], pa[m]) - dist(pm[n], pm[m])
            total += delta * delta
            count += 1
            if abs(delta) <= CLOSE_ANGSTROM:
                close += 1
            if abs(delta) > worst[0]:
                worst = (abs(delta), n, m)
    seq_parent = {n: a for n, a, _ in parent}
    seq_model = {n: a for n, a, _ in model}
    return {"compared_residues": len(shared), "compared_pairs": count,
            "drmsd_A": round((total / count) ** 0.5, 3),
            "pairs_within_%.1fA" % CLOSE_ANGSTROM: round(close / count, 3),
            "largest_disagreement_A": round(worst[0], 2),
            "largest_disagreement_between": [worst[1], worst[2]],
            "identity_to_parent_sequence": _identity("".join(seq_model[n] for n in shared),
                                                     "".join(seq_parent[n] for n in shared)),
            "residue_range": [shared[0], shared[-1]]}


def compare_refolds(parent_rel, folds):
    """How far each refold sits from the sourced backbone, and from the other refold."""
    parent = structure_sequence(_artifact(parent_rel, ".pdb").read_text(encoding="utf-8", errors="replace"))
    if len(parent) < MIN_COMPARED:
        raise ValueError("the parent structure has too few C-alpha atoms to compare")
    rows, traces = [], {}
    for fold in folds or []:
        ident = str((fold or {}).get("derived_id") or "")
        data = record(ident)
        path = _artifact((fold or {}).get("structure"), ".pdb")
        if _sha256(path) != (fold or {}).get("sha256", _sha256(path)):
            raise ValueError("the refold of %s has changed since it was recorded" % ident)
        trace = structure_sequence(path.read_text(encoding="utf-8", errors="replace"))
        traces[ident] = trace
        row = {"derived_id": ident, "structure": str(fold.get("structure")),
               "design_header": data.get("design_header"), "sequence_length": data["length"]}
        row.update(_distance_comparison(parent, trace))
        rows.append(row)
    if not rows:
        raise ValueError("a comparison needs at least one recorded refold")
    rows.sort(key=lambda r: r["drmsd_A"])
    between = None
    if len(rows) == 2:
        a, b = (r["derived_id"] for r in rows)
        between = dict(_distance_comparison(traces[a], traces[b]), pair=[a, b])
    lines = ["%d refold(s) of designed sequences against %s (%d C-alpha residues)" % (
                 len(rows), parent_rel, len(parent)),
             "compared by distance matrix, no superposition: lower dRMSD = the refold keeps the backbone's "
             "internal geometry"]
    for row in rows:
        lines.append("%s (%d aa, %.0f%% identical to the backbone's own sequence): dRMSD %.2f A over %d residues, "
                     "%.0f%% of residue pairs within %.1f A, worst %.2f A at %s-%s" % (
                         row["derived_id"], row["sequence_length"],
                         (row["identity_to_parent_sequence"] or 0) * 100, row["drmsd_A"], row["compared_residues"],
                         row["pairs_within_%.1fA" % CLOSE_ANGSTROM] * 100, CLOSE_ANGSTROM,
                         row["largest_disagreement_A"], *row["largest_disagreement_between"]))
    if between:
        lines.append("the two refolds against each other: dRMSD %.2f A" % between["drmsd_A"])
    lines.append("what this is: the design model and the folding model agreeing about a backbone. Not affinity, "
                 "not stability, not a functional protein.")
    return {"ok": True, "result": {"parent_structure": parent_rel, "parent_residues": len(parent),
                                   "method": "C-alpha distance-matrix comparison, residues paired by number, "
                                             "no superposition",
                                   "candidates": rows, "between_candidates": between,
                                   "closest_to_parent": rows[0]["derived_id"], "display": lines,
                                   "truth_status": COMPARE_TRUTH}}


def compare_pilot(pilot_id):
    row = pilot(str(pilot_id or "").strip())
    if not row.get("folds"):
        raise ValueError("this pilot has no recorded refold yet")
    out = compare_refolds(row["parent_structure"], row["folds"])
    out["result"]["pilot_id"] = row["pilot_id"]
    out["result"]["gpu_minutes_ceiling"] = row.get("gpu_minutes_ceiling", GPU_MINUTES_CEILING)
    return out


def _cli(argv):
    if argv[:1] == ["show"]:
        for row in pilots():
            print("%s  %s  parent %s  candidates %s  folds %d/%d" % (
                row.get("pilot_id"), row.get("date"), row.get("parent_structure"),
                ",".join(row.get("derived") or []), len(row.get("folds") or []), row.get("max_folds")))
        for path in sorted(DERIVED.glob("DRV-*.json")) if DERIVED.is_dir() else []:
            data = json.loads(path.read_text(encoding="utf-8"))
            print("%s  %d aa  from %s  parent %s" % (data.get("derived_id"), data.get("length"),
                                                     data.get("design_artifact"), data.get("parent_structure")))
        return 0
    if argv[:1] == ["compare"] and len(argv) == 2:
        print("\n".join(compare_pilot(argv[1])["result"]["display"]))
        return 0
    if argv[:1] == ["request"] and len(argv) == 2:
        print(json.dumps(fold_request(argv[1]), ensure_ascii=False, sort_keys=True))
        return 0
    print("usage: lab_derived_sequences.py show | compare <PILOT-id> | request <DRV-id>")
    return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
