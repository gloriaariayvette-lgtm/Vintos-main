#!/usr/bin/env python3
"""On-demand Lab instruments: the one door from his Lab turn to the relay skills Chat commissioned
(2026-09-29). They were wired, receipted and kept out of the background menu on purpose, but nothing in the
Lab could call them, so he never could. Now, only when the Lab holds a concrete artifact, his turn may ask
for ONE instrument on it:

  structure_viewer  on a PDB/mmCIF the Lab already has   (analyze / measure / render_image)
  sequence_viewer   on a FASTA the Lab already has        (run_analysis / align)
  biohub_esm        on a sourced accession or sequence    (atlas.search / esmc.mutation_landscape /
                                                           esmc.feature_interpretation)

  reference_compare on an ESMFold model the Lab made    (structure.compare: against a real RCSB entry, on Aegis)
  fold_read         on an ESMFold model the Lab made    (structure.read: helix/strand and confidence over a range)

Adaptyv (needs Gloria's approval for anything real) and the NGS workbench (needs a real dataset) are not
offered here. At most DAILY_RUNS instrument runs a day. A sequence the Lab fetches is kept as a FASTA
artifact so the sequence instruments have something real to open.
"""
from __future__ import annotations
import json
import os
import re
import time
from datetime import date
from pathlib import Path

WS = Path(os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace")))
LAB = WS / "memory" / "chemistry-lab"
ARTIFACTS = LAB / "artifacts"
SEQUENCES = ARTIFACTS / "sequences"
LEDGER = LAB / "instrument-runs.json"
DAILY_RUNS = 25
OFFERED = {
    "structure_viewer": ("structure.analyze", "structure.measure", "structure.render_image"),
    "sequence_viewer": ("sequence.run_analysis", "sequence.align"),
    "biohub_esm": ("atlas.search", "esmc.mutation_landscape", "esmc.feature_interpretation"),
    # his predicted structure against an experimental one (Grok Bot, 2026-10-06: pendrin's STAS against pig 8SGW);
    # runs on Aegis in the Lab's own Python, not through the relay
    "reference_compare": ("structure.compare",),
    # what a model he already has holds, over the residues he names, without folding it again (2026-10-07)
    "fold_read": ("structure.read",),
    # the refolds of sequences his own design instruments made, against the backbone they were designed on
    # (2026-10-26); runs on Aegis in his own Python, costs nothing, and claims only model consistency
    "derived_compare": ("structure.compare_refolds",),
    # a family panel declared earlier, measured against the retained readings it froze: does the feature persist
    # across the homologs and go missing in the comparator (2026-10-26)? Reads artifacts he already has, folds nothing
    "family_panel": ("structure.compare_family",),
}
LOCAL = {"reference_compare": "chemistry_reference_compare.py", "fold_read": "chemistry_fold_read.py"}
STRUCTURE = (".pdb", ".cif", ".cif.gz")
SEQUENCE = (".fasta", ".fa", ".faa", ".fna", ".gb", ".gbk")


def _runs_today():
    try:
        d = json.load(open(LEDGER))
    except Exception:
        d = {}
    return d if d.get("date") == date.today().isoformat() else {"date": date.today().isoformat(), "runs": []}


def artifacts(kind, limit=5):
    """Recent Lab artifacts of a kind, as paths relative to the Lab."""
    ends = STRUCTURE if kind == "structure" else SEQUENCE
    # Tools' commissioning demos (artifacts/<tool>/verification/) are not his work; only his own runs are offered.
    found = [p for p in ARTIFACTS.rglob("*") if p.is_file() and not p.is_symlink() and p.name.lower().endswith(ends)
             and "verification" not in p.relative_to(ARTIFACTS).parts] if ARTIFACTS.is_dir() else []
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p.relative_to(LAB)) for p in found[:limit]]


def save_fasta(accession, sequence, start=None, end=None, database=""):
    """Keep a sequence the Lab fetched as a FASTA artifact (bounded, plain name)."""
    acc = re.sub(r"[^A-Za-z0-9._-]", "_", str(accession or ""))[:60]
    seq = re.sub(r"\s+", "", str(sequence or ""))
    if not acc or not seq or len(seq) > 200000:
        return ""
    SEQUENCES.mkdir(parents=True, exist_ok=True)
    span = ("_%s-%s" % (start, end)) if start and end else ""
    path = SEQUENCES / ("%s%s.fasta" % (acc, span))
    lines = [seq[i:i + 70] for i in range(0, len(seq), 70)]
    path.write_text(">%s%s %s\n%s\n" % (acc, (":%s-%s" % (start, end)) if span else "", database, "\n".join(lines)))
    return str(path.relative_to(LAB))


def completed_fold_read(req):
    """Recognize an approved imported local readout without executing or recording it.

    Readouts live under artifacts/fold-read; installing one there is a separate
    reviewed operation, never a side effect of selection. Missing lookup history
    is not permission to redo a delivered result. Keep its exact provenance.
    """
    import hashlib
    from lab_repeats import fold_read_covers
    if req.get('skill') != 'fold_read' or req.get('operation') != 'structure.read': return None
    _, _, files, _ = validate(req)
    model_hash = hashlib.sha256((LAB / files[0]).read_bytes()).hexdigest()
    reader_hash = hashlib.sha256(Path(__file__).with_name('chemistry_fold_read.py').read_bytes()).hexdigest()
    for path in sorted((ARTIFACTS / 'fold-read').glob('*.json')):
        if path.is_symlink() or path.stat().st_size > 2*1024*1024: continue
        try:
            data = json.loads(path.read_text())
            result = data['result']; span = result['range']
            if data.get('sha256') != model_hash or data.get('script_sha256') != reader_hash: continue
            if Path(str(data.get('path') or '')).name != Path(files[0]).name: continue
            if not isinstance(span, list) or len(span) != 2 or any(type(x) is not int for x in span): continue
            if not 0 < span[0] <= span[1] or data.get('requested_range') != span: continue
            count = span[1] - span[0] + 1
            if data.get('analyzed_residues') != count or data.get('missing_requested_residues') != []: continue
            if len(result.get('secondary_structure', '')) != count or len(result.get('plddt_by_residue', [])) != count: continue
            old = dict(req, range=span)
            if fold_read_covers(old, req):
                return {'artifact': str(path.relative_to(LAB)), 'artifact_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'model_sha256': model_hash, 'reader_sha256': reader_hash, 'range': span,
                        'reason': 'existing_completed_model_read_not_new_work'}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def menu_block():
    """The instrument option for his orient prompt, or '' when there is nothing real to run one on."""
    left = DAILY_RUNS - len(_runs_today()["runs"])
    if left <= 0:
        return ""
    structures, sequences = artifacts("structure"), artifacts("sequence")
    lines = ["ON-DEMAND INSTRUMENTS (%d run(s) left today). Only when the question needs one, instead of "
             "source_query and plugin_query, return instrument_query = {skill, operation, files, question}:" % left]
    if structures:
        lines.append("- structure_viewer, operation structure.analyze | structure.measure | structure.render_image, "
                     "files from: " + ", ".join(structures))
    if sequences:
        lines.append("- sequence_viewer, operation sequence.run_analysis | sequence.align, files from: " + ", ".join(sequences))
    models = [f for f in structures if f.startswith("artifacts/esmfold/") and f.endswith(".pdb")]
    if models:
        lines.append("- reference_compare, operation structure.compare, files [one of: " + ", ".join(models) + "], "
                     "with reference (a four-character PDB entry id of a deposited structure, e.g. 1ABC, never a "
                     "protein name or UniProt accession: take it from a pdb source step's records or the structure's "
                     "receipt), chain, ref_span [first, last] in the entry's "
                     "numbering; offset is worked out from the alignment (give it only to check it: a wrong one is refused). Lines your model up "
                     "with the real structure by sequence and gives TM-score, RMSD, and the entry's helices and strands "
                     "in your numbering.")
        lines.append("- fold_read, operation structure.read, files [one of: " + ", ".join(models) + "], with range "
                     "[first, last] in your protein's numbering: helix and strand ranges from the model's own geometry "
                     "and its confidence per stretch. Read a model you have; do not fold it again for this.")
    try:
        import lab_derived_sequences as derived
        ready = [p["pilot_id"] for p in derived.pilots() if p.get("folds")]
    except Exception:
        ready = []
    if ready:
        lines.append("- derived_compare, operation structure.compare_refolds, files [], with pilot one of: "
                     + ", ".join(ready) + ": how far each refold of your own designed sequences sits from the "
                     "backbone they were designed on, by distance matrix. It says the design model and the folding "
                     "model agree about a shape; it says nothing about affinity, stability or function.")
    try:
        import lab_family_panel as family
        declared = [p["panel_id"] for p in family.ready()]
    except Exception:
        declared = []
    if declared:
        lines.append("- family_panel, operation structure.compare_family, files [], with panel one of: "
                     + ", ".join(declared) + ": measures a family question you already froze against the "
                     "readings it named - whether the feature persists in the homologs and is missing in the "
                     "comparator. A position no alignment places is undecidable, not absent; it claims nothing "
                     "about function, stability or flexibility.")
    lines.append("- biohub_esm, operation atlas.search | esmc.mutation_landscape | esmc.feature_interpretation, files [], "
                 "with a sourced UniProt accession or sequence named in the question (never a duplicate of ESMC/ESMFold).")
    return "\n".join(lines)


def validate(req):
    """(skill, operation, files, question) or ValueError."""
    if not isinstance(req, dict):
        raise ValueError("instrument_query must be an object")
    skill, op = req.get("skill"), req.get("operation")
    from lab_native_instruments import OPERATIONS
    native = op == OPERATIONS.get(skill) and skill in OPERATIONS
    if not native and (skill not in OFFERED or op not in OFFERED[skill]):
        raise ValueError("instrument or operation not offered in the Lab")
    files = [str(f) for f in (req.get("files") or []) if isinstance(f, str)][:4]
    allowed = set(artifacts("structure", 50) + artifacts("sequence", 50))
    if any(f not in allowed for f in files):
        raise ValueError("instrument files must be artifacts the Lab listed")
    if skill in ("structure_viewer", "sequence_viewer") + tuple(LOCAL) and not files:
        raise ValueError("this instrument needs a Lab artifact")
    if skill in LOCAL and (len(files) != 1 or not files[0].startswith("artifacts/esmfold/")):
        raise ValueError("%s takes one ESMFold model the Lab made" % skill)
    question = str(req.get("question") or "")[:600]
    if len(question) < 10:
        raise ValueError("say what the instrument should answer")
    return skill, op, files, question


def run(req, runner=None):
    """Run one instrument; a result shaped like a Lab source receipt."""
    skill, op, files, question = validate(req)
    today = _runs_today()
    if len(today["runs"]) >= DAILY_RUNS:
        raise PermissionError("instrument runs used up for today")
    from lab_native_instruments import OPERATIONS
    if runner is None and skill in OPERATIONS:
        from lab_native_instruments import run as native_run
        runner = lambda *a, **k: native_run(req)
    if runner is None and skill in LOCAL:
        runner = _compare_runner(req)
    if runner is None and skill == "derived_compare":
        runner = _derived_runner(req)
    if runner is None and skill == "family_panel":
        runner = _family_runner(req)
    if runner is None:
        import plugin_gateway
        runner = plugin_gateway.run_skill
    today["runs"].append({"at": time.time(), "skill": skill, "operation": op, "files": files})
    LAB.mkdir(parents=True, exist_ok=True)
    tmp = str(LEDGER) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(today, f)
    os.replace(tmp, LEDGER)
    out = runner("lab", skill, question, operation=op, input_files=[str(LAB / f) for f in files])
    if skill in OPERATIONS: return out
    receipt = out.get("receipt") or {}
    return {"receipt": {"receipt_id": receipt.get("receipt_id"), "source": "instrument:" + skill,
                        "records": [{"skill": skill, "operation": op, "inputs": files,
                                     "summary": str(out.get("summary", ""))[:1500],
                                     "outputs": [os.path.basename(p) for p in out.get("files", [])]}],
                        "metadata": {"service": "relay_skill", "operation": op,
                                     "interpretation": "instrument_analysis_not_independent_validation"}}}


def _derived_runner(req):
    """The design-and-refold comparison, in this Python: his own artifacts, no network, no model call."""
    def runner(surface, skill, question, operation=None, input_files=()):
        import lab_derived_sequences as derived
        r = derived.compare_pilot(req.get("pilot"))["result"]
        return {"receipt": {"receipt_id": "derived-compare-%s-%d" % (r.get("pilot_id"), int(time.time()))},
                "summary": "\n".join(r["display"]), "files": []}
    return runner


def _family_runner(req):
    """A declared family panel measured here: his own retained readings, no network, no model call."""
    def runner(surface, skill, question, operation=None, input_files=()):
        import lab_family_panel as family
        r = family.evaluate(req.get("panel"))["result"]
        return {"receipt": {"receipt_id": "family-panel-%s-%d" % (r.get("panel_id"), int(time.time()))},
                "summary": "\n".join(r["display"]), "files": []}
    return runner


def _compare_runner(req, run=None):
    """A local instrument (reference_compare, fold_read) in the Lab's own Python on Aegis; answers like a relay skill."""
    import subprocess
    import sys
    def runner(surface, skill, question, operation=None, input_files=()):
        model = os.path.relpath(input_files[0], LAB)
        body = ({"model": model, "range": req.get("range")} if skill == "fold_read" else
                {"model": model, "reference": req.get("reference"), "chain": req.get("chain", "A"),
                 "ref_span": req.get("ref_span"), **({"offset": req["offset"]} if req.get("offset") is not None else {})})
        python = os.environ.get("VINTOS_ESMFOLD_PYTHON", os.path.expanduser("~/.vintos/tools/chemistry-lab/esmc/bin/python"))
        if not os.path.isfile(python):
            python = sys.executable
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCAL[skill])
        done = (run or subprocess.run)([python, script], input=json.dumps(body), text=True, capture_output=True, timeout=300)
        try:
            out = json.loads((done.stdout or "").strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise RuntimeError("the comparison gave no answer: %s" % (done.stderr or "")[-300:])
        if not out.get("ok"):
            raise RuntimeError(out.get("error") or "the comparison failed")
        r = out["result"]
        return {"receipt": {"receipt_id": "%s-%s-%s" % (skill, r.get("reference") or r.get("model", ""), int(time.time()))},
                "summary": "\n".join(r["display"]), "files": []}
    return runner


def from_slack(raw, runner=None):
    """A RUN: line from #vintos-dot (2026-10-08: on 7 October he asked dot to install Merizo while his own
    reference_compare and fold_read sat unused). Only the local instruments, which cost nothing. Returns
    (result or None, words for the channel)."""
    try:
        req = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except ValueError:
        return None, "not run: a RUN: line is one JSON object, e.g. {\"skill\": \"fold_read\", \"model\": \"O43511\", \"range\": [535, 729]}"
    if not isinstance(req, dict) or req.get("skill") not in LOCAL:
        return None, "not run: RUN: takes one of your Lab's own instruments (%s)" % ", ".join(sorted(LOCAL))
    model = str(req.get("model") or (req.get("files") or [""])[0] or "").strip()
    # an absolute Aegis path pasted into the room (.../memory/chemistry-lab/artifacts/esmfold/X.pdb) is the Lab's own
    # file, not an accession: cut it to its artifacts/... form and let validate() check it against the artifact list
    if "memory/chemistry-lab/" in model:
        model = model.split("memory/chemistry-lab/", 1)[1].lstrip("/")
    if not model.startswith("artifacts/"):
        acc = re.sub(r"[^A-Za-z0-9-]", "", model).upper()
        found = [f for f in artifacts("structure", 50) if f.startswith("artifacts/esmfold/%s-" % acc) and f.endswith(".pdb")]
        if not acc or not found:
            return None, "not run: you have no ESMFold model of %s in the Lab" % (acc or "that")
        model = found[0]
    req = dict(req, files=[model], operation=OFFERED[req["skill"]][0],
               question=str(req.get("question") or "%s on %s" % (req["skill"], model)))
    if len(req["question"]) < 10:
        req["question"] = "%s on %s, from the room" % (req["skill"], model)
    try:
        out = run(req, runner=runner)
    except Exception as exc:
        return None, "not run (%s): %s" % (type(exc).__name__, str(exc)[:300])
    rec = out["receipt"]["records"][0]
    return out, "%s on %s:\n%s" % (req["skill"], model, rec["summary"])

