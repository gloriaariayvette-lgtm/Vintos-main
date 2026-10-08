#!/usr/bin/env python3
"""What the Lab may ask the Forge to build (Gloria, 2026-10-08: "We need to improve what the Forge is suggesting").

On 7 October the Forge held four "Missing Lab instrument" projects, and three were not worth building:
  - "A regulatory genomics database containing the specific Atlas ATAC-seq and AVI_SCORE fields": a misreading of
    a source he already reads (Atlas gives predicted effects in one fixed window; it has no AVI_SCORE field);
  - "A sequence retrieval tool for the NCBI Protein database or a specialized phage database": he has both;
  - "A molecular dynamics (MD) simulator ... free energy profile of water": a large build for a passing question.
The one worth keeping was specific and on his work: "a transcript-specific mapping tool to correlate the p.H723R
mutation" (pendrin's founder variant, beside his STAS comparison).

The only rule before was "not laboratory equipment". judge() now asks, in order and without any model call:
  own_source     it asks for fields inside a source he already reads
  already_have   the Lab already has it (HAVE, below)
  large          a simulator or training project: never sent on its own, kept for Gloria to ask for
  vague          it names nothing concrete to run on (a protein, gene, variant or structure)
  declined       Gloria cancelled a project like it
and only what passes all five goes to the Forge. What is held stays in the Lab with its reason, and his next
reflection is told why, so the same gap is not raised again in other words.
"""
from __future__ import annotations

import re

# What the Lab already reaches (lab_sources.py, chemistry_*.py, lab_instruments.py). Each: what a gap would say,
# and what to use instead.
HAVE = (
    (r"\b(?:ncbi|entrez|genbank|refseq|nuccore)\b|\bsequence retrieval\b|\bprotein (?:sequence )?database\b",
     "NCBI (source ncbi / ncbi_sequence: gene, protein, nucleotide, taxonomy, assembly; pubmed for papers)"),
    (r"\bphage (?:database|genomes?|db)\b|\bimg/?vr\b|\bviral genomes?\b", "IMG/VR phages (source imgvr) and BV-BRC (bvbrc)"),
    (r"\buniprot\b", "UniProt (source uniprot)"),
    (r"\b(?:rcsb|protein data bank|experimental structures?)\b|\bpdb (?:entry|entries|database|structures?)\b",
     "the PDB (source pdb), and reference_compare against an entry"),
    (r"\b(?:interpro|pfam|domain annotations?|protein famil(?:y|ies))\b", "InterPro and Pfam (source interpro)"),
    (r"\b(?:chembl|bioactivit\w*)\b", "ChEMBL (source chembl)"),
    (r"\bpubchem\b|\bcompound (?:database|properties)\b", "PubChem (source pubchem)"),
    (r"\breactome\b|\bpathway database\b", "Reactome (source reactome)"),
    (r"\brhea\b|\breaction database\b", "Rhea (source rhea)"),
    (r"\b(?:quickgo|gene ontology|go terms?)\b", "QuickGO (source quickgo)"),
    (r"\bmgnify\b|\bmetagenom\w*\b", "MGnify (source mgnify)"),
    (r"\bcosmic\b|\bsomatic mutations?\b", "COSMIC (source cosmic)"),
    (r"\b(?:atac|dnase|cage|chromatin accessibility|alphagenome|atlas)\b|\bregulatory (?:genomics|variant effect)\b",
     "Atlas (AlphaGenome: predicted variant effects in one fixed window, source atlas)"),
    (r"\b(?:structure prediction|esmfold|alphafold|fold(?:ing)? (?:the|a|its) (?:protein|sequence))\b",
     "ESMFold (his own folds)"),
    (r"\b(?:esm-?c|protein (?:language model )?embeddings?)\b", "ESM-C embeddings"),
    (r"\b(?:evo ?2|dna language model)\b", "Evo2"),
    (r"\b(?:tm-?align|tm-?score|structural (?:alignment|comparison|superposition)|rmsd)\b",
     "reference_compare (TM-align and RMSD against a PDB entry)"),
    (r"\b(?:hmmer|hmm (?:search|profile)|profile search)\b", "HMM profile search (lab_hmm)"),
    (r"\bcrispr arrays?\b|\bcrt\b", "CRISPR array detection (lab_crt)"),
    (r"\bgenomic (?:sequence|region|coordinates)\b|\breference genome\b|\bgrch38\b", "Ensembl genome regions"),
)
_HAVE = [(re.compile(rx, re.I), name) for rx, name in HAVE]
# A field or column inside a record: AVI_SCORE, "the X field", "fields for"
_FIELD = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b|\bfields?\b|\bcolumns?\b|\bcontaining the specific\b")
LARGE = re.compile(r"\b(?:molecular dynamics|md simulat\w*|free[- ]energy|quantum (?:chemistry|mechanic\w*)|dft\b|"
                   r"ab initio|metadynamics|monte carlo|docking (?:campaign|screen)|virtual screen\w*|"
                   r"train(?:ing)? (?:a|an|its own|my own|a new) (?:model|network|predictor)|whole[- ]genome assembl\w*|"
                   r"(?:large|full)[- ]scale simulat\w*)\b", re.I)
_VARIANT = re.compile(r"\b(?:p\.)?[A-Z][a-z]{0,2}\d{1,5}(?:[A-Z][a-z]{0,2}|\*|fs)\b|\brs\d{3,}\b|\bc\.\d+[ACGT]>[ACGT]\b")
_PDB = re.compile(r"\b\d[A-Za-z0-9]{3}\b(?=[^A-Za-z0-9]|$)")
DECLINED_LIKE = 0.5


def _subjects(text):
    try:
        import lab_repeats
        found = set(lab_repeats.subjects(text))
    except Exception:
        found = set(re.findall(r"\b[A-Z][A-Z0-9]{2,9}\b", str(text or "")))
    found |= {m.group(0) for m in _VARIANT.finditer(str(text or "")) if any(c.isdigit() for c in m.group(0))}
    found |= {m.group(0).upper() for m in _PDB.finditer(str(text or "")) if re.search(r"[A-Za-z]", m.group(0))}
    return found


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if len(w) > 3}


def _like(a, b):
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / min(len(wa), len(wb)) if wa and wb else 0.0


def have(gap):
    """What the Lab already has that the gap asks for, or ''."""
    return next((name for rx, name in _HAVE if rx.search(str(gap or ""))), "")


def judge(gap, question="", declined=()):
    """{"send": bool, "kind": one of send/own_source/already_have/large/vague/declined, "why": words for him}."""
    gap = str(gap or "").strip()
    got = have(gap)
    if got and _FIELD.search(gap):
        return {"send": False, "kind": "own_source",
                "why": "it asks for fields inside a source you already read (%s). Read what that source returns; "
                       "a field it does not have cannot be built into it." % got}
    if got:
        return {"send": False, "kind": "already_have", "why": "your Lab already has this: %s. Use it." % got}
    if LARGE.search(gap):
        return {"send": False, "kind": "large",
                "why": "a large build (%s) is not raised from one question. It is kept here; it goes to the Forge "
                       "when Gloria asks for it." % LARGE.search(gap).group(0)}
    if not _subjects(gap) and not _subjects(question):
        return {"send": False, "kind": "vague",
                "why": "it names nothing concrete to run on. Name the protein, gene, variant or structure and what "
                       "it would measure."}
    for title in declined or ():
        if _like(gap, title) >= DECLINED_LIKE:
            return {"send": False, "kind": "declined",
                    "why": "Gloria cancelled a project like it: %s" % str(title)[:160]}
    return {"send": True, "kind": "send", "why": ""}


def declined_titles(cfg):
    """Titles of Forge projects Gloria cancelled or abandoned, or [] when the Forge cannot be read."""
    try:
        import chemistry_sources
        rows = chemistry_sources._forge_projects(cfg) or []
    except Exception:
        return []
    return [str(r.get("title") or r.get("name") or r.get("intent") or "") for r in rows
            if isinstance(r, dict) and r.get("state") in ("cancelled", "abandoned")]


def inventory():
    """What the Lab has, in words, for his reflection prompt."""
    return "; ".join(dict.fromkeys(name for _, name in HAVE))
