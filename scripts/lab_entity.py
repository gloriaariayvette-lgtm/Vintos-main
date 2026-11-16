#!/usr/bin/env python3
"""Entity grounding for Lab investigations (DRAFT, branch claude/lab-entity-grounding; Gloria decides any deploy).

Off by default. LAB_ENTITY_GROUNDING=1 (environment or vintos.env, read at every call) turns it on; removing the line
is the rollback.

Why (16 Nov measurement): of 433 investigations whose question's protein and whose structure files' protein can both
be identified, 104 ran every structure step on a model of ANOTHER protein (99 on the pendrin model O43511). The
planner's structure menu was the 8 newest structure files Lab-wide, and the offer check only asked "is it listed",
never "is it this investigation's protein".

What it does, only when the investigation's protein is RESOLVED (an accession in its question, or a completed UniProt
accession lookup in it); an unresolved investigation is planned exactly as today (fail-open):
  structure_menu(investigation, n)  the structure files offered to the planner: ESMFold models of THIS protein, plus
                                    non-model structures (references), newest first; never another protein's model
  labels(paths)                     {path: "GENE (Protein name)"} from the Lab's completed UniProt lookups
  note(investigation)               when no model of this protein is listed: the planner is told to acquire it first
  problem(investigation, route, request)
                                    (why) when an instrument step names an ESMFold model of another protein; None
                                    otherwise -> the Lab refuses it as "off_target_structure" and re-plans
"""
import json
import os
import re
from pathlib import Path

import lab_instruments

_ACCESSION = re.compile(r"(?<![A-Z0-9])(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?![A-Z0-9])")
_GENE = re.compile(r'"geneName"\s*:\s*\{\s*"value"\s*:\s*"([^"]+)"')
_NAME = re.compile(r'"recommendedName"\s*:\s*\{\s*"fullName"\s*:\s*\{\s*"value"\s*:\s*"([^"]+)"')
_CACHE = {"key": None, "ids": {}}


def enabled():
    try:
        import env_file
        path = os.path.join(os.path.dirname(os.path.abspath(str(lab_instruments.WS))), "vintos.env")
        v = env_file.value("LAB_ENTITY_GROUNDING", "", path=path)
    except Exception:
        v = os.environ.get("LAB_ENTITY_GROUNDING", "")
    return str(v or os.environ.get("LAB_ENTITY_GROUNDING", "")).strip().lower() in ("1", "on", "true", "yes")


def _investigations():
    p = lab_instruments.LAB / "investigations.json"
    try:
        with open(p) as fh:
            return p, json.load(fh).get("investigations", [])
    except Exception:
        return p, []


def _uniprot_accession(step):
    r = step.get("executed_request") or step.get("request") or {}
    if not isinstance(r, dict) or str(r.get("source") or "").lower() != "uniprot":
        return None
    m = re.match(r"\s*accession:\s*([A-Z0-9]+)\s*$", str(r.get("query") or ""), re.I)
    return m.group(1).upper() if m and _ACCESSION.fullmatch(m.group(1).upper()) else None


def identities():
    """{accession: (genes, protein name)} from every completed UniProt accession lookup the Lab holds."""
    p, inv = _investigations()
    try:
        key = (str(p), os.stat(p).st_mtime_ns)
    except OSError:
        key = None
    if key is not None and key == _CACHE["key"]:
        return _CACHE["ids"]
    ids = {}
    for i in inv:
        for s in i.get("steps") or []:
            a = _uniprot_accession(s)
            if not a or a in ids or s.get("state") != "completed" or not s.get("output_file"):
                continue
            try:
                txt = (lab_instruments.LAB / s["output_file"]).read_text(errors="ignore")
            except OSError:
                continue
            genes, name = list(dict.fromkeys(_GENE.findall(txt)))[:2], (_NAME.findall(txt) or [""])[0]
            if genes or name:
                ids[a] = (genes, name)
    _CACHE.update(key=key, ids=ids)
    return ids


def model_accession(path):
    """The accession an ESMFold model was folded from (artifacts/esmfold/<ACC>-<hash>.pdb); None for anything else."""
    m = re.match(r"artifacts/esmfold/([A-Za-z0-9]+)-[0-9a-f]{6,}\.(?:pdb|cif)$", str(path))
    return m.group(1).upper() if m and _ACCESSION.fullmatch(m.group(1).upper()) else None


def resolved(investigation):
    """The accessions this investigation is about: named in its question, or looked up (completed) in it."""
    acc = set(_ACCESSION.findall(str(investigation.get("question") or "").upper()))
    for s in investigation.get("steps") or []:
        a = _uniprot_accession(s)
        if a and s.get("state") == "completed":
            acc.add(a)
    return acc


def labels(paths):
    ids, out = identities(), {}
    for p in paths:
        a = model_accession(p)
        if a and a in ids:
            g, n = ids[a]
            out[p] = "%s (%s)" % ("/".join(g) or a, n) if n else "/".join(g) or a
    return out


def structure_menu(investigation, limit=8):
    everything = lab_instruments.artifacts("structure", 50)
    acc = resolved(investigation) if enabled() else set()
    if not acc:
        return everything[:limit]
    return [p for p in everything if model_accession(p) is None or model_accession(p) in acc][:limit]


def note(investigation):
    if not enabled():
        return ""
    acc = resolved(investigation)
    if not acc:
        return ""
    if any(model_accession(p) in acc for p in lab_instruments.artifacts("structure", 50)):
        return ""
    names = ", ".join(sorted(acc))
    return ("No structure model of %s is held yet: acquire it first (fold %s with ESMFold, or read its UniProt record) "
            "before any structural step; a model of another protein cannot answer this question." % (names, names))


def problem(investigation, route, request):
    if not enabled() or route not in ("instrument", "native") or not isinstance(request, dict):
        return None
    acc = resolved(investigation)
    if not acc:
        return None
    raw = request.get("files")
    files = [raw] if isinstance(raw, str) else [f for f in raw or [] if isinstance(f, str)] if isinstance(raw, list) else []
    other = [(f, model_accession(f)) for f in files if model_accession(f) and model_accession(f) not in acc]
    if not other:
        return None
    lab = labels([f for f, _ in other])
    return ("%s is a model of %s, not of this investigation's protein (%s); fold or look up %s first, or work from "
            "sources" % (other[0][0], lab.get(other[0][0]) or other[0][1], ", ".join(sorted(acc)), ", ".join(sorted(acc))))
