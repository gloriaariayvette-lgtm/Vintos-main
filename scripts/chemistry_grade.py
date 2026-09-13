#!/usr/bin/env python3
"""Chemistry Lab correctness grading: did the instrument run, and was the answer good?

Those are two different facts and this module refuses to merge them.  A Mac experiment
that completes, returns numbers, and writes a full ledger row is *operational*.  Whether
its variational energy beat the Hartree-Fock reference is a separate verdict, and the
one the Lab kept losing: a poor H2 optimisation was recorded as ``completed`` and read
downstream as a success.

Three laws:

1. **The verdict is computed here, on Aegis, from the numbers the Mac returned.**  The
   bench may report its own error and recovered correlation; those are kept as
   ``host_reported`` and never decide anything.  A host cannot grade itself.
2. **Isolation is host-attested, not proven.**  The Mac's isolation block is copied
   verbatim and labelled as an attestation.  This repository holds no independent
   evidence for the chemistry bench's sandbox, and the row says so rather than implying
   otherwise.
3. **A variational energy below the exact ground state is a bug, not a triumph.**  That
   check runs before any success outcome, so no ordering accident can turn a broken
   Hamiltonian into ``BETTER_THAN_HARTREE_FOCK``.

A negative ``correlation_recovered`` is correct output, not a malformed one: it is
precisely how "worse than Hartree-Fock" expresses itself on that scale.

Grades live beside the Lab that produced them (``memory/chemistry-lab/``) and never in
general memory.  The record shape deliberately mirrors ``grading_contract.py`` -- target,
outcome, counts_as, one row per graded thing -- but the Lab writes only below its own
root, so it keeps its own store rather than borrowing that one.

    grade(run_id, experiment, mac_result, plan=None)  -> the row (or a refusal)
    history(limit) / latest(run_id) / summary_block(limit)
    python3 chemistry_grade.py                        the last grades
"""
from __future__ import annotations

import json
import math
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import chemistry_lab as lab

GRADES = os.path.join(lab.ROOT, "experiment-grades.jsonl")

# Bumped whenever the arithmetic or the outcome vocabulary changes.  Idempotence is keyed
# on (run_id, grader_version): a re-grade under a new grader is a new row, not a refusal,
# so an improved grader can revisit old runs without erasing what the old one said.
GRADER_VERSION = "chemistry_grade/1"

# Hartree.  Chemical accuracy is ~1.6e-3 Ha; this is far tighter, because the question
# here is only "is it on the right side of the reference", not "is it chemically useful".
DEFAULT_TOLERANCE = 1e-6
ENERGY_SANITY = 1e6

ACCURACY_OUTCOMES = ("BETTER_THAN_HARTREE_FOCK", "AT_HARTREE_FOCK", "WORSE_THAN_HARTREE_FOCK",
                     "INVALID_BELOW_EXACT", "UNGRADED_NO_REFERENCE", "UNGRADED_UNREADABLE")
# Only a real comparison against a real reference counts toward accuracy.  Everything else
# counts as nothing: never a miss, never a success.
COUNTS_AS = {"BETTER_THAN_HARTREE_FOCK": "accuracy", "AT_HARTREE_FOCK": "accuracy",
             "WORSE_THAN_HARTREE_FOCK": "accuracy", "INVALID_BELOW_EXACT": "nothing",
             "UNGRADED_NO_REFERENCE": "nothing", "UNGRADED_UNREADABLE": "nothing"}

EXECUTION_STATES = ("completed", "completed_no_points", "completed_with_unreadable_points",
                    "failed", "unknown_after_timeout")

# The doorway nests the bench's own payload.  The observed shape is
# reply["run"]["result"]["results"]; the others are kept so an older or flatter bench reply
# still parses, and the row records which path was actually taken.
POINTS_PATHS = (("run", "result", "results"), ("run", "results"), ("result", "results"),
                ("results",), ("run", "result", "points"), ("result", "points"))
# A bench that returns one point rather than a curve.
SINGLE_PATHS = (("run", "result"), ("result",), ())

FIELDS = {
    "vqe": ("vqe_energy", "vqe", "energy_vqe", "vqe_energy_hartree", "optimized_energy",
            "lowest_energy", "energy"),
    "hartree_fock": ("hartree_fock_energy", "hartree_fock", "hf_energy", "hf",
                     "hartree_fock_energy_hartree", "reference_energy"),
    "exact": ("exact_energy", "fci_energy", "exact", "fci", "exact_ground_state_energy",
              "ground_state_energy"),
    "bond_length": ("bond_length", "bond_length_angstrom", "r", "distance", "geometry_r",
                    "separation"),
}
HOST_REPORTED = ("error", "energy_error", "recovered_correlation", "correlation_recovered",
                 "converged", "iterations", "ansatz", "optimizer", "basis", "molecule", "seed")


def _tolerance():
    try: value = float(lab.config().get("grade_tolerance_hartree", DEFAULT_TOLERANCE))
    except Exception: return DEFAULT_TOLERANCE
    return value if math.isfinite(value) and value > 0 else DEFAULT_TOLERANCE


def _number(value):
    """A usable energy, or None.  Bools are not energies; strings that parse are."""
    if isinstance(value, bool) or value is None: return None
    try: number = float(value)
    except (TypeError, ValueError): return None
    if not math.isfinite(number) or abs(number) > ENERGY_SANITY: return None
    return number


def _dig(value, path):
    for key in path:
        if not isinstance(value, dict): return None
        value = value.get(key)
    return value


def _points(mac_result):
    """The per-geometry results, and the path they were found at, so the parse is auditable."""
    if not isinstance(mac_result, dict): return [], None
    for path in POINTS_PATHS:
        found = _dig(mac_result, path)
        if isinstance(found, list) and found:
            return [row for row in found if isinstance(row, dict)], ".".join(path) or "."
    for path in SINGLE_PATHS:
        found = _dig(mac_result, path) if path else mac_result
        if isinstance(found, dict) and any(k in found for k in FIELDS["vqe"]):
            return [found], (".".join(path) or ".") + "#single"
    return [], None


def _resolve(point):
    """Pull the three energies out of one bench point, recording which key each came from."""
    values, mapping = {}, {}
    for name, aliases in FIELDS.items():
        for alias in aliases:
            if alias not in point: continue
            number = _number(point[alias])
            if number is None: continue
            values[name] = number; mapping[name] = alias
            break
    return values, mapping


def _accuracy(values, tol):
    """The per-point verdict.

    Order matters and is not cosmetic.  INVALID_BELOW_EXACT is tested first: a run that
    dips below the exact ground state has violated the variational principle, which means
    a broken Hamiltonian or a mis-scaled energy, and must never be reported as the best
    result of the day.
    """
    vqe, hf, exact = values.get("vqe"), values.get("hartree_fock"), values.get("exact")
    if vqe is None: return "UNGRADED_UNREADABLE", "no readable variational energy"
    if exact is not None and vqe < exact - tol:
        return "INVALID_BELOW_EXACT", "below the exact ground state by %.9f Ha" % (exact - vqe)
    if hf is None: return "UNGRADED_NO_REFERENCE", "no Hartree-Fock reference in the result"
    if vqe < hf - tol: return "BETTER_THAN_HARTREE_FOCK", "below Hartree-Fock by %.9f Ha" % (hf - vqe)
    if abs(vqe - hf) <= tol: return "AT_HARTREE_FOCK", "no correlation energy recovered"
    return "WORSE_THAN_HARTREE_FOCK", "above Hartree-Fock by %.9f Ha" % (vqe - hf)


def _correlation(values, tol):
    """(hf - vqe) / (hf - exact).  Negative is a real reading, not an error."""
    vqe, hf, exact = values.get("vqe"), values.get("hartree_fock"), values.get("exact")
    if vqe is None or hf is None or exact is None: return None, "reference incomplete"
    denominator = hf - exact
    if abs(denominator) <= tol: return None, "reference carries no correlation energy"
    return round((hf - vqe) / denominator, 6), None


def _aggregate(rows):
    """One clearly named verdict over a whole curve."""
    if not rows: return "NO_GRADEABLE_POINTS"
    outcomes = {row["accuracy_outcome"] for row in rows}
    if "INVALID_BELOW_EXACT" in outcomes: return "ANY_INVALID_BELOW_EXACT"
    graded = {o for o in outcomes if COUNTS_AS.get(o) == "accuracy"}
    if not graded: return "NO_GRADEABLE_POINTS"
    if graded == {"BETTER_THAN_HARTREE_FOCK"}: return "ALL_BETTER_THAN_HARTREE_FOCK"
    if graded == {"WORSE_THAN_HARTREE_FOCK"}: return "ALL_WORSE_THAN_HARTREE_FOCK"
    if graded == {"AT_HARTREE_FOCK"}: return "ALL_AT_HARTREE_FOCK"
    return "MIXED"


def _execution_state(mac_result, points, unreadable):
    """Whether the instrument ran.  Deliberately not a statement about the answer."""
    if not isinstance(mac_result, dict): return "failed"
    if mac_result.get("state") == "unknown_after_timeout": return "unknown_after_timeout"
    if not mac_result.get("ok"): return "failed"
    if not points: return "completed_no_points"
    if unreadable: return "completed_with_unreadable_points"
    return "completed"


def _isolation(mac_result):
    """The bench's own sandbox claim, kept as an attestation and labelled as one."""
    block = _dig(mac_result, ("run", "isolation")) or _dig(mac_result, ("isolation",)) \
        or _dig(mac_result, ("run", "result", "isolation"))
    if not isinstance(block, dict):
        return {"isolation_receipted": False, "isolation_attestation": "absent", "isolation": None}
    return {"isolation_receipted": True, "isolation_attestation": "host_attested",
            "isolation": {str(k)[:40]: (v if isinstance(v, (bool, int, float)) else str(v)[:200])
                          for k, v in list(block.items())[:12]}}


def graded_already(run_id, grader_version=None):
    """Read the version at call time, not at import: a default bound to the module constant
    would pin the idempotence key to whatever it was when this file was first imported, and
    an improved grader could then never revisit a run."""
    version = grader_version or GRADER_VERSION
    return any(row.get("run_id") == run_id and row.get("grader_version") == version
               for row in lab._jsonl(GRADES))


def grade(run_id, experiment, mac_result, plan=None):
    """Grade one Mac run.  Returns the appended row, or a refusal when already graded."""
    run_id = str(run_id or "")[:64]
    if not run_id: return {"refused": "a run without a run_id cannot be graded idempotently"}
    if graded_already(run_id):
        return {"refused": "run %s is already graded by %s" % (run_id, GRADER_VERSION)}
    tol = _tolerance()
    points, points_path = _points(mac_result)
    rows, unreadable, field_map = [], 0, {}
    for index, point in enumerate(points[:64]):
        values, mapping = _resolve(point)
        outcome, detail = _accuracy(values, tol)
        recovered, why = _correlation(values, tol)
        if outcome == "UNGRADED_UNREADABLE": unreadable += 1
        field_map.update(mapping)
        rows.append({"index": index, "bond_length": values.get("bond_length"),
                     "vqe_energy": values.get("vqe"), "hartree_fock_energy": values.get("hartree_fock"),
                     "exact_energy": values.get("exact"),
                     "energy_above_hartree_fock": (round(values["vqe"] - values["hartree_fock"], 9)
                                                   if values.get("vqe") is not None
                                                   and values.get("hartree_fock") is not None else None),
                     "correlation_recovered": recovered, "correlation_note": why,
                     "accuracy_outcome": outcome, "counts_as": COUNTS_AS[outcome], "detail": detail,
                     "host_reported": {k: (point[k] if isinstance(point[k], (bool, int, float))
                                           else str(point[k])[:120])
                                       for k in HOST_REPORTED if k in point}})
    row = {"grade_id": "CG-" + uuid.uuid4().hex[:10], "at": lab.now_iso(),
           "run_id": run_id, "experiment": str(experiment or "")[:80],
           "grader_version": GRADER_VERSION, "tolerance_hartree": tol,
           "execution_state": _execution_state(mac_result, points, unreadable),
           "aggregate_accuracy": _aggregate(rows),
           "graded_points": sum(1 for r in rows if r["counts_as"] == "accuracy"),
           "total_points": len(rows), "unreadable_points": unreadable,
           "points_path": points_path, "field_map": field_map, "points": rows,
           "plan": {k: plan.get(k) for k in ("experiment", "parameters", "shots", "question")}
                   if isinstance(plan, dict) else None,
           "truth_status": "aegis_computed_verdict_over_host_supplied_numbers",
           "evidence_standing": "lab_local_correctness_record_not_biological_evidence"}
    row.update(_isolation(mac_result))
    lab._append(GRADES, row)
    return row


def history(limit=20):
    return lab._jsonl(GRADES)[-int(limit):]


def latest(run_id):
    for row in reversed(lab._jsonl(GRADES)):
        if row.get("run_id") == run_id: return row
    return None


def summary_block(limit=4):
    """A small honest block for his Lab context: what ran, and what was actually good."""
    rows = [r for r in lab._jsonl(GRADES) if r.get("total_points")][-int(limit):]
    if not rows: return ""
    lines = ["[RECENT EXPERIMENT GRADES — ran and good are different facts]"]
    for row in rows:
        # Only a point that actually counts toward accuracy may be called the best one; a
        # below-exact point has the lowest number and the least standing.
        best = min((p for p in row.get("points", [])
                    if p.get("counts_as") == "accuracy" and p.get("energy_above_hartree_fock") is not None),
                   key=lambda p: p["energy_above_hartree_fock"], default=None)
        lines.append("%s %s: execution %s, accuracy %s%s" % (
            str(row.get("at", ""))[:16], row.get("experiment", "?"), row.get("execution_state"),
            row.get("aggregate_accuracy"),
            (", best point %+0.6f Ha vs Hartree-Fock" % best["energy_above_hartree_fock"]) if best else ""))
    return "\n".join(lines)


if __name__ == "__main__":
    for entry in history(int(sys.argv[1]) if len(sys.argv) > 1 else 10):
        print("%s %-10s %-12s exec=%-30s accuracy=%s (%d/%d points)" % (
            str(entry.get("at"))[:19], entry.get("run_id"), entry.get("experiment"),
            entry.get("execution_state"), entry.get("aggregate_accuracy"),
            entry.get("graded_points", 0), entry.get("total_points", 0)))
