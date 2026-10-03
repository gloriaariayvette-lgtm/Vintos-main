#!/usr/bin/env python3
"""Protein domains from the sequence itself: HMMER's hmmscan against Pfam (Gloria installed both on Aegis,
2026-10-03). InterPro could only annotate a protein UniProt already had, and most phage proteins carry only an
NCBI accession, so a reverse transcriptase or a Cas1 in a phage genome went unnamed.

Pfam's own gathering thresholds (--cut_ga) decide what counts as a hit. A domain hit is a family resemblance, not a
function, an activity or novelty.
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import tempfile

PFAM = os.path.expanduser(os.environ.get("VINTOS_PFAM", "~/.vintos/tools/chemistry-lab/pfam/Pfam-A.hmm"))
MAX_PROTEINS = 24
MAX_RESIDUES = 6000
TIMEOUT = 600

# What the phage screen looks for. Names are Pfam's; a description match catches families named otherwise.
RT_NAMES = {"RVT_1", "RVT_2", "RVT_3", "RVT_N", "RVT_connect", "RVT_thumb", "GIIM", "Intron_maturas2"}
RT_WORDS = re.compile(r"reverse transcriptase", re.I)
CAS_NAMES = re.compile(r"^(Cas_|CRISPR_|Cas\d|Csm|Cmr|Csx|Csa|Cse|Csn|Csy|Csd)", re.I)
CAS_WORDS = re.compile(r"\bCRISPR\b|\bCas\d", re.I)


def hmmscan():
    return shutil.which("hmmscan") or ""


def available():
    """True when hmmscan and a pressed Pfam are both here."""
    return bool(hmmscan()) and all(os.path.exists(PFAM + ext) for ext in (".h3m", ".h3i", ".h3f", ".h3p"))


def _fasta(proteins):
    out = []
    for name, seq in proteins.items():
        seq = re.sub(r"[^A-Za-z]", "", str(seq or "")).upper()
        if seq:
            out.append(">%s\n%s" % (re.sub(r"\s+", "_", str(name))[:60], "\n".join(seq[i:i + 70] for i in range(0, len(seq), 70))))
    return "\n".join(out) + "\n"


def parse_domtbl(text):
    """hmmscan --domtblout rows: {query: [domain...]}, best first."""
    found = {}
    for line in str(text or "").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split(None, 22)
        if len(f) < 22:
            continue
        try:
            row = {"family": f[0], "pfam": f[1], "evalue": float(f[12]), "score": float(f[13]),
                   "from": int(f[17]), "to": int(f[18]), "description": (f[22] if len(f) > 22 else "").strip()[:120]}
        except ValueError:
            continue
        found.setdefault(f[3], []).append(row)
    for rows in found.values():
        rows.sort(key=lambda r: (r["from"], -r["score"]))
    return found


def scan(proteins, run=None):
    """Pfam domains of each protein ({name: sequence}); {name: [domain...]}. Raises when HMMER is not here."""
    proteins = dict(list((proteins or {}).items())[:MAX_PROTEINS])
    proteins = {k: v for k, v in proteins.items() if v and len(str(v)) <= MAX_RESIDUES}
    if not proteins:
        return {}
    if run is None and not available():
        raise RuntimeError("HMMER or Pfam is not installed (hmmscan, %s)" % PFAM)
    with tempfile.TemporaryDirectory(prefix="lab-hmm-") as tmp:
        faa, tbl = os.path.join(tmp, "q.faa"), os.path.join(tmp, "out.domtbl")
        open(faa, "w").write(_fasta(proteins))
        args = [hmmscan() or "hmmscan", "--cut_ga", "--noali", "--cpu", "2", "-o", os.devnull,
                "--domtblout", tbl, PFAM, faa]
        if run:
            text = run(args, open(faa).read())
        else:
            subprocess.run(args, check=True, timeout=TIMEOUT, capture_output=True)
            text = open(tbl).read()
    return parse_domtbl(text)


def is_rt(domain):
    return domain["family"] in RT_NAMES or bool(RT_WORDS.search(domain.get("description", "")))


def is_cas(domain):
    return bool(CAS_NAMES.search(domain["family"]) or CAS_WORDS.search(domain.get("description", "")))
