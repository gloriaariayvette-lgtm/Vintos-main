#!/usr/bin/env python3
"""Named proteins bind to exact sourced sequences; no network or real Mac is reachable."""
import importlib.util
import os
import sys
import tempfile
import types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-sequence-binding-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_CHEMISTRY_MAC_CONFIG"] = os.path.join(HOME, "chemistry-mac.json")
sys.path.insert(0, os.path.join(REPO, "scripts"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mac = load("chemistry_mac_sequence_test", os.path.join(REPO, "scripts", "chemistry_mac.py"))
assert mac.CONFIG.startswith(HOME), mac.CONFIG
sent = []


def record(accession, sequence):
    return {"primaryAccession": accession, "sequence": {"value": sequence, "length": len(sequence)}}


def resolver(accession):
    return record(accession, "ACDEFGHI"), {"provider": "UniProtKB", "accession": accession,
                                           "receipt_id": "receipt-test"}


def transport(body):
    sent.append(body)
    p = body["parameters"]
    sequence = p["sequence"]
    result = {"title": "Folding %s (%d aa): %s" % (p["requested_accession"], len(sequence), sequence),
              "requested_accession": p["requested_accession"], "modeled_sequence": sequence,
              "modeled_sequence_length": len(sequence), "sequence_source": p["sequence_source"],
              "hp_mapping": mac._hp_mapping(sequence)}
    return {"ok": True, "run_id": "RUN-SEQ", "run": {"result": result}}


good = mac.run("protein", {"target_accession": "P12345", "focus": "exact sequence"}, 128,
               resolver=resolver, transport=transport)
assert good["ok"] is True and good["sequence_check"]["outcome"] == "SEQUENCE_ACCESSION_MATCH", good
assert sent[0]["parameters"]["sequence"] == "ACDEFGHI"
assert sent[0]["parameters"]["requested_accession"] == "P12345"
assert sent[0]["parameters"]["sequence_source"]["accession"] == "P12345"

missing = mac.run("protein", {"target_accession": "Q99999"}, resolver=lambda accession: (None, {}),
                  transport=lambda body: (_ for _ in ()).throw(AssertionError("real Mac reached")))
assert missing["ok"] is False and missing["refused"] == "sequence_unavailable", missing

long_sequence = "A" * 88
too_long = mac.run("protein", {"target_accession": "A1L190"},
                   resolver=lambda accession: (record(accession, long_sequence),
                                                {"provider": "UniProtKB", "accession": accession}),
                   transport=lambda body: (_ for _ in ()).throw(AssertionError("real Mac reached")))
assert too_long["ok"] is False and too_long["refused"] == "sequence_too_long", too_long
assert too_long["requested_sequence"] == long_sequence and too_long["requested_sequence_length"] == 88
assert too_long["modeled_sequence"] is None and len(too_long["hp_mapping"]) == 88


def wrong_transport(body):
    return {"ok": True, "run_id": "RUN-WRONG", "run": {"result": {
        "title": "Folding LVEALYLV", "requested_accession": "P12345",
        "real_sequence": "LVEALYLV", "modeled_sequence_length": 8,
        "sequence_source": {"provider": "built_in_fragment", "accession": "insulin_b_core"}}}}


wrong = mac.run("protein", {"target_accession": "P12345"}, resolver=resolver, transport=wrong_transport)
assert wrong["ok"] is False and wrong["refused"] == "sequence_accession_mismatch", wrong
assert wrong["sequence_check"]["outcome"] == "SEQUENCE_ACCESSION_MISMATCH"
assert "modeled sequence differs" in wrong["error"] and "title disagrees" in wrong["error"]

# Execute the tracked Mac experiment with a fake lattice implementation.  It must preserve
# the actual residue sequence and refuse both missing and oversized named proteins.
sys.modules["fold"] = types.SimpleNamespace(experiment=lambda parameters, shots: {
    "display": ["fold", "result"], "lattice": parameters["sequence"]})
protein = load("qlab_protein_sequence_test",
               os.path.join(REPO, "mac", "qlab", "bench", "experiments", "protein.py"))
mac_result = protein.experiment({"target_accession": "P12345", "requested_accession": "P12345",
    "sequence": "ACDEFGHI", "sequence_source": {"provider": "UniProtKB", "accession": "P12345"}}, 128)
assert mac_result["modeled_sequence"] == "ACDEFGHI" and mac_result["modeled_sequence_length"] == 8
assert mac_result["requested_accession"] == "P12345" and len(mac_result["hp_mapping"]) == 8
assert "P12345" in mac_result["title"] and "ACDEFGHI" in mac_result["title"]
try:
    protein.experiment({"target_accession": "A1L190", "sequence_source": {
        "provider": "UniProtKB", "accession": "A1L190"}}, 128)
    raise AssertionError("missing named sequence was not refused")
except ValueError as exc:
    assert "no sourced sequence" in str(exc)
try:
    protein.experiment({"target_accession": "A1L190", "sequence": long_sequence,
                        "sequence_source": {"provider": "UniProtKB", "accession": "A1L190"}}, 128)
    raise AssertionError("oversized named sequence was not refused")
except ValueError as exc:
    assert "88 residues" in str(exc) and "limit is 9" in str(exc)

# The grader must name the identity failure rather than bury it under NO_GRADEABLE_POINTS.
lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
grade = load("chemistry_grade_sequence_test", os.path.join(REPO, "scripts", "chemistry_grade.py"))
graded = grade.grade("RUN-WRONG", "protein", wrong, {"experiment": "protein", "parameters": {
    "target_accession": "P12345", "sequence": "ACDEFGHI"}, "shots": 128})
assert graded["execution_state"] == "failed"
assert graded["aggregate_accuracy"] == "SEQUENCE_ACCESSION_MISMATCH", graded
assert graded["sequence_check"]["requested_accession"] == "P12345"
session_source = open(os.path.join(REPO, "scripts", "chemistry_session.py"), encoding="utf-8").read()
assert '"SEQUENCE_ACCESSION_MISMATCH"' in session_source and "grading.grade(result[\"run_id\"]" in session_source

assert grade.GRADES.startswith(HOME) and mac.CONFIG.startswith(HOME)
assert not os.path.exists(os.path.expanduser("~/.vintos/chemistry-mac.json")) or HOME in os.path.expanduser("~/.vintos/chemistry-mac.json")
print("PASS named protein sequence binding, refusal, Mac contract, and grader mismatch")
