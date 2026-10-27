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

  ngs_workbench     on a FASTQ read sample the Lab holds    (list_workflows / plan_nextflow / plan_snakemake:
                                                           planning only, nothing is executed)

Adaptyv (needs Gloria's approval for anything real) is not offered here. The NGS workbench is offered only once
the Lab holds a real read sample (sequencing_reads keeps the first reads of a public run, 2026-10-27). At most DAILY_RUNS
instrument runs a day, of which at most RELAY_DAILY_RUNS on the relay (a model turn each, on the Mac). A sequence the Lab fetches is kept as a FASTA
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
# 100 instrument runs a day in all (Gloria, 27 October: 25 a day was used up by mid-afternoon on 26 October). The
# local instruments (fold_read, reference_compare, derived_compare, family_panel, the native ones) run in his own Python
# on Aegis and cost nothing. The relay instruments do not: each run is a whole model turn on the Mac relay's chat
# account, which has its plan's usage limits, and biohub_esm also spends Biohub's metered ESM calls. Those stay at the
# old 25 a day, inside the 100.
DAILY_RUNS = 100
RELAY = ("structure_viewer", "sequence_viewer", "biohub_esm", "ngs_workbench")
RELAY_DAILY_RUNS = 25
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
    # a real public read sample (lab_sequencing, 2026-10-27): workflows planned over it, never executed
    "ngs_workbench": ("list_workflows", "plan_nextflow", "plan_snakemake"),
}
LOCAL = {"reference_compare": "chemistry_reference_compare.py", "fold_read": "chemistry_fold_read.py"}
STRUCTURE = (".pdb", ".cif", ".cif.gz")
READS = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
SEQUENCE = (".fasta", ".fa", ".faa", ".fna", ".gb", ".gbk") + READS


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


def read_samples(limit=5):
    """The FASTQ read samples among the Lab's sequence artifacts: what the NGS workbench can be given."""
    return [f for f in artifacts("sequence", 50) if f.lower().endswith(READS)][:limit]


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


def relay_runs_left():
    """Runs left today for the relay instruments (a model turn each on the Mac relay), within runs_left()."""
    used = len([r for r in _runs_today()["runs"] if isinstance(r, dict) and r.get("skill") in RELAY])
    return max(0, min(RELAY_DAILY_RUNS - used, runs_left()))


def menu_block():
    """The instrument option for his orient prompt, or '' when there is nothing real to run one on."""
    left = DAILY_RUNS - len(_runs_today()["runs"])
    if left <= 0:
        return ""
    relay = relay_runs_left()
    structures, sequences = artifacts("structure"), artifacts("sequence")
    lines = ["ON-DEMAND INSTRUMENTS (%d run(s) left today, %d of them for the ones marked relay). Only when the "
             "question needs one, instead of "
             "source_query and plugin_query, return instrument_query = {skill, operation, files, question}:" % (left, relay)]
    if not relay:     # the relay instruments are not offered once their own runs are spent
        sequences = []
    if structures and relay:
        lines.append("- structure_viewer (relay), operation structure.analyze | structure.measure | structure.render_image, "
                     "files from: " + ", ".join(structures))
    if sequences:
        lines.append("- sequence_viewer (relay), operation sequence.run_analysis | sequence.align, files from: " + ", ".join(sequences))
    samples = read_samples() if relay else []
    if samples:
        lines.append("- ngs_workbench (relay), operation list_workflows | plan_nextflow | plan_snakemake, files [one of: "
                     + ", ".join(samples) + "]: the first reads of a public run (its sequencing_reads receipt says "
                     "which). Plans a workflow over the sample; nothing is executed.")
    models = [f for f in structures if f.startswith("artifacts/esmfold/") and f.endswith(".pdb")]
    if models:
        lines.append("- reference_compare, operation structure.compare, files [one of: " + ", ".join(models) + "], "
                     "with reference (a four-character PDB entry id of a deposited structure, e.g. 1ABC, from a pdb "
                     "source step's records or the structure's receipt; given none, or the protein's accession, the Lab "
                     "picks one of its entries and says which), chain, ref_span [first, last] in the entry's "
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
    if relay:
        lines.append("- biohub_esm (relay), operation atlas.search | esmc.mutation_landscape | esmc.feature_interpretation, files [], "
                     "with a sourced UniProt accession or sequence named in the question (never a duplicate of ESMC/ESMFold).")
    return "\n".join(lines) if len(lines) > 1 else ""


def runs_left():
    return max(0, DAILY_RUNS - len(_runs_today()["runs"]))


def skill_operations():
    """Every instrument the Lab has, with its exact operation names: the offered ones and the native ones."""
    from lab_native_instruments import OPERATIONS
    out = {k: list(v) for k, v in OFFERED.items()}
    out.update({k: [v] for k, v in OPERATIONS.items()})
    return out


# What each instrument does, in one line: what a refusal tells him, so the next step can name a real one (Gloria,
# 27 October: "name the real instruments in the moment").
WHAT = {
    "fold_read": "helices, strands and confidence over a residue range of one of your ESMFold models (local)",
    "reference_compare": "one of your ESMFold models against a deposited PDB entry: TM-score, RMSD, the entry's "
                         "helices and strands in your numbering (local)",
    "derived_compare": "how far the refolds of your designed sequences sit from the backbone they were designed on (local)",
    "family_panel": "a family panel you froze, measured against its retained readings (local)",
    "structure_viewer": "analyze, measure distances/angles in, or render a structure file the Lab holds (relay)",
    "sequence_viewer": "analyze or align a FASTA/GenBank file the Lab holds (relay)",
    "ngs_workbench": "plan a Nextflow/Snakemake workflow over a read sample the Lab holds; nothing is executed (relay)",
    "biohub_esm": "Biohub ESM: Atlas neighbours, mutation landscape or feature interpretation of a sourced accession (relay)",
    "protein_mpnn": "design sequences for a PDB backbone the Lab holds (local, route native)",
    "rfdiffusion": "generate a short new backbone, 10-80 residues (local, route native)",
    "openmm": "relax a structure the Lab holds on a C-alpha elastic network (local, route native)",
}


class NotOffered(ValueError):
    """An instrument or operation the Lab does not have, with what it has right now."""


def available_now():
    """The instruments he can name on his next step, right now, one line each: name, its operations, what it does,
    and what it takes. Only those with something real to run on and a run left today."""
    menu = planner_menu()
    if menu.get("runs_left_today", 0) <= 0:
        return [menu.get("state", "No instrument run is left today.")]
    lines = []
    for name, row in list((menu.get("skills") or {}).items()) + list((menu.get("native_skills") or {}).items()):
        files = row.get("files") or []
        takes = (" files: one of %s" % ", ".join(files[:2]) + (" (+%d more)" % (len(files) - 2) if len(files) > 2 else "")
                 if files else "")
        also = (" also: " + ", ".join(sorted(row["also"]))) if isinstance(row.get("also"), dict) else ""
        lines.append("%s [%s]: %s.%s%s" % (name, " | ".join(row.get("operations") or []), WHAT.get(name, ""), takes, also))
    lines.append("%d run(s) left today, %d of them for the relay instruments." % (menu["runs_left_today"],
                                                                                menu.get("relay_runs_left_today", 0)))
    return lines


def not_offered(why):
    """A NotOffered refusal: why, then every instrument he can name instead, right now."""
    return NotOffered("%s. Instruments the Lab has right now (route instrument, {skill, operation, files, question}): %s"
                      % (why, " | ".join(available_now())))


def planner_menu():
    """The instrument route as the investigation planner must write it: the exact skill and operation names, the
    files each one takes, and the runs left today. It is there also when no run is left, saying so.

    On 26 October the day's 25th run was at 15:33 UTC; from then on menu_block() was empty, the investigation planner
    was shown no instrument at all, and 42 of her instrument requests that evening named one from memory under keys
    of her own ({"instrument": "structure_viewer"}, {"artifact": <a model>}), each refused as "not offered"."""
    from lab_native_instruments import OPERATIONS
    left = runs_left()
    if left <= 0:
        return {"runs_left_today": 0,
                "state": ("No instrument run is left today: routes instrument and native are not run until tomorrow. "
                          "Choose a source, plugin, experiment, representation, read_output or finish."),
                "skills": {k: v for k, v in skill_operations().items()}}
    structures, sequences = artifacts("structure"), artifacts("sequence")
    models = [f for f in structures if f.startswith("artifacts/esmfold/") and f.endswith(".pdb")]
    skills = {}
    relay = relay_runs_left()
    if not relay:     # the relay instruments are not offered once their own runs are spent
        sequences = []
    if structures and relay:
        skills["structure_viewer"] = {"operations": list(OFFERED["structure_viewer"]), "files": structures}
    if sequences:
        skills["sequence_viewer"] = {"operations": list(OFFERED["sequence_viewer"]), "files": sequences}
    samples = read_samples() if relay else []
    if samples:
        skills["ngs_workbench"] = {"operations": list(OFFERED["ngs_workbench"]), "files": samples,
                                   "gives": "a workflow plan over the read sample; planning only, nothing is executed"}
    if models:
        skills["reference_compare"] = {
            "operations": list(OFFERED["reference_compare"]), "files": models,
            "also": {"reference": "four-character PDB entry id of a deposited structure (from a pdb source step); "
                                  "given none or the protein's accession, the Lab picks one of its entries and says which",
                     "chain": "A", "ref_span": "[first, last] in the entry's numbering"},
            "gives": "TM-score, RMSD, the entry's helices and strands in your numbering"}
        skills["fold_read"] = {"operations": list(OFFERED["fold_read"]), "files": models,
                               "also": {"range": "[first, last] in your protein's numbering"},
                               "gives": "helix and strand ranges and confidence per stretch of a model you have"}
    try:
        import lab_derived_sequences as derived
        ready = [p["pilot_id"] for p in derived.pilots() if p.get("folds")]
    except Exception:
        ready = []
    if ready:
        skills["derived_compare"] = {"operations": list(OFFERED["derived_compare"]), "files": [],
                                     "also": {"pilot": "one of " + ", ".join(ready)}}
    try:
        import lab_family_panel as family
        declared = [p["panel_id"] for p in family.ready()]
    except Exception:
        declared = []
    if declared:
        skills["family_panel"] = {"operations": list(OFFERED["family_panel"]), "files": [],
                                  "also": {"panel": "one of " + ", ".join(declared)}}
    if relay:
        skills["biohub_esm"] = {"operations": list(OFFERED["biohub_esm"]), "files": [],
                                "note": "a sourced UniProt accession or sequence named in the question"}
    native = {k: {"operations": [v], "route": "native"} for k, v in OPERATIONS.items()}
    return {"runs_left_today": left, "relay_runs_left_today": relay,
            **({} if relay else {"relay_state": "structure_viewer, sequence_viewer, ngs_workbench and biohub_esm have no "
                                                "run left today (%d a day: each is a model turn on the Mac); the "
                                                "local instruments still run" % RELAY_DAILY_RUNS}),
            "request": {"skill": "<one name from skills, under the key skill>", "operation": "<one of its operations>",
                        "files": ["<one of its files>"], "question": "<what it should answer>"},
            "skills": skills, "native_skills": native}


def validate(req):
    """(skill, operation, files, question) or ValueError."""
    if not isinstance(req, dict):
        raise ValueError("instrument_query must be an object")
    skill, op = req.get("skill"), req.get("operation")
    from lab_native_instruments import OPERATIONS
    native = op == OPERATIONS.get(skill) and skill in OPERATIONS
    if not native and (skill not in OFFERED or op not in OFFERED[skill]):
        raise not_offered("instrument or operation not offered in the Lab (%s, %s)"
                          % (str(skill)[:40] if skill else "no skill named", str(op)[:40] if op else "no operation named"))
    files = [str(f) for f in (req.get("files") or []) if isinstance(f, str)][:4]
    allowed = set(artifacts("structure", 50) + artifacts("sequence", 50))
    if any(f not in allowed for f in files):
        raise ValueError("instrument files must be artifacts the Lab listed")
    if skill in ("structure_viewer", "sequence_viewer", "ngs_workbench") + tuple(LOCAL) and not files:
        raise ValueError("this instrument needs a Lab artifact")
    if skill == "ngs_workbench" and any(not f.lower().endswith(READS) for f in files):
        raise ValueError("ngs_workbench takes a FASTQ read sample the Lab holds (from sequencing_reads)")
    if skill in LOCAL and (len(files) != 1 or not files[0].startswith("artifacts/esmfold/")):
        raise ValueError("%s takes one ESMFold model the Lab made" % skill)
    if skill == "reference_compare":
        # the compare's own input checks, here, before a run is spent: on 26 October 10 of the day's 11 instrument
        # runs were compares refused inside the instrument for naming no PDB entry, each taking one of DAILY_RUNS
        import chemistry_reference_compare
        chemistry_reference_compare.validate(dict(req, model=files[0]))
    question = str(req.get("question") or "")[:600]
    if len(question) < 10:
        raise ValueError("say what the instrument should answer")
    return skill, op, files, question


def run(req, runner=None):
    """Run one instrument; a result shaped like a Lab source receipt."""
    skill, op, files, question = validate(req)
    today = _runs_today()
    if len(today["runs"]) >= DAILY_RUNS:
        raise PermissionError("instrument runs used up for today (%d a day)" % DAILY_RUNS)
    if skill in RELAY and relay_runs_left() <= 0:
        raise PermissionError("%s has no run left today: the relay instruments (%s) run at most %d a day, each a model "
                              "turn on the Mac; the local ones (%s) still run"
                              % (skill, ", ".join(RELAY), RELAY_DAILY_RUNS, ", ".join(sorted(LOCAL))))
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

