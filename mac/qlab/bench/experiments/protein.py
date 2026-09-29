"""Fold a real, explicitly sourced protein fragment on the HP lattice.

Named-accession requests never fall back to a demonstration fragment.  The complete
sourced sequence, its accession, and its provenance must agree before the experiment
runs.  This lattice has nine usable residues; longer proteins are refused rather than
silently truncated and described as if they were modeled.
"""
from __future__ import annotations

import re
import fold as fold_experiment

HYDROPATHY = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5, "Q": -3.5, "E": -3.5,
    "G": -0.4, "H": -3.2, "I": 4.5, "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8,
    "P": -1.6, "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}
CHARGE = {"D": -1, "E": -1, "K": 1, "R": 1, "H": 0}
MAX_RESIDUES = 9

FRAGMENTS = {
    "insulin_b_core": ("LVEALYLV", "the hydrophobic middle of insulin's B chain"),
    "zinc_finger": ("FQCRICMR", "the metal-binding core of a zinc finger"),
    "amyloid_core": ("KLVFFAED", "the segment of amyloid-beta that drives aggregation"),
    "collagen_rep": ("GPPGPPGP", "collagen's repeat; proline everywhere, famously stiff"),
    "polyalanine": ("AAAAAAAA", "a control — nothing distinguishes one end from the other"),
}


def _accession(parameters):
    values = {str(parameters.get(key) or "").strip().upper()
              for key in ("requested_accession", "target_accession", "accession")
              if str(parameters.get(key) or "").strip()}
    if len(values) > 1: raise ValueError("conflicting protein accessions")
    value = values.pop() if values else ""
    if value and not re.fullmatch(r"[A-Z0-9]{6,10}(?:-[1-9][0-9]*)?", value):
        raise ValueError("invalid UniProt accession")
    return value


def translate(sequence, threshold=1.0):
    sequence = re.sub(r"\s+", "", str(sequence or "").upper())
    if not sequence or any(letter not in HYDROPATHY for letter in sequence):
        raise ValueError("sequence must contain only the 20 standard amino-acid letters")
    if len(sequence) > MAX_RESIDUES:
        raise ValueError("sourced sequence has %d residues; HP lattice limit is %d" %
                         (len(sequence), MAX_RESIDUES))
    hp = "".join("H" if HYDROPATHY[c] >= threshold else "P" for c in sequence)
    charges = "".join({1: "+", -1: "-"}.get(CHARGE.get(c, 0), "0") for c in sequence)
    return sequence, hp, charges


def experiment(parameters, shots):
    parameters = dict(parameters or {})
    accession = _accession(parameters)
    fragment = str(parameters.get("fragment") or "").strip()
    raw = str(parameters.get("sequence") or "").strip()
    source = parameters.get("sequence_source") if isinstance(parameters.get("sequence_source"), dict) else {}

    if accession:
        if fragment: raise ValueError("an accession run cannot select a built-in fragment")
        if not raw: raise ValueError("%s has no sourced sequence; refusing demo fallback" % accession)
        if str(source.get("accession") or "").upper() != accession:
            raise ValueError("sequence source accession does not match %s" % accession)
        note = "sourced from %s accession %s" % (source.get("provider") or "UniProtKB", accession)
    elif fragment:
        if fragment not in FRAGMENTS: raise ValueError("unknown built-in protein fragment")
        raw, note = FRAGMENTS[fragment]
        source = {"provider": "built_in_fragment", "accession": fragment}
    elif raw:
        note = "an explicitly supplied sequence"
        source = {"provider": "explicit_sequence", "accession": ""}
    else:
        raise ValueError("protein experiment requires a sourced sequence or an explicit fragment")

    threshold = float(parameters.get("hydrophobic_threshold", 1.0))
    sequence, hp, charges = translate(raw, threshold)
    if len(hp) < 4: raise ValueError("need at least four amino acids")

    lattice = dict(parameters)
    for key in ("fragment", "requested_accession", "target_accession", "accession", "sequence_source"):
        lattice.pop(key, None)
    lattice["sequence"] = hp
    lattice["charges"] = charges
    lattice.setdefault("layers", 3); lattice.setdefault("search_steps", 120)
    result = fold_experiment.experiment(lattice, shots)

    mapping = [{"position": index + 1, "residue": residue, "hp": hp[index],
                "hydropathy": HYDROPATHY[residue], "charge": charges[index]}
               for index, residue in enumerate(sequence)]
    rows = ["  %(position)d  %(residue)s  hydropathy %(hydropathy)+5.1f  -> %(hp)s%(charge)s" %
            dict(row, charge=("   charge " + row["charge"] if row["charge"] != "0" else ""))
            for row in mapping]
    identity = ("%s (%d aa): %s" % (accession, len(sequence), sequence)) if accession else sequence
    result.update({"title": "Folding " + identity, "requested_accession": accession,
                   "modeled_sequence": sequence, "real_sequence": sequence,
                   "modeled_sequence_length": len(sequence), "sequence_source": source,
                   "hp_mapping": mapping, "fragment_note": note,
                   "translation": {"hydropathy_threshold": threshold, "hp": hp, "charges": charges}})
    result["display"] = (["FOLDING " + identity, "", note, "", "actual amino-acid sequence:",
                          "  " + sequence, "", "how each residue maps to H/P:"] + rows +
                         ["", "  -> lattice sequence %s   charges %s" % (hp, charges), ""] +
                         list(result.get("display", []))[2:])
    result["question"] = ("Does this sourced fragment's HP-lattice shape put the hydrophobic "
                          "residues where expected, within this deliberately small model?")
    return result
