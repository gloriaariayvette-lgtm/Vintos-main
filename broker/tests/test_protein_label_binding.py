#!/usr/bin/env python3
"""A run labelled with one protein may not fold another: the accession must be that protein.

A plan that said HFE with target_accession P02794 folded ferritin heavy chain under HFE's name.
No network, Mac or ESMFold is reachable here; every store is scratch.
"""
import importlib.util
import os
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-protein-label-")
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


mac = load("chemistry_mac_label_test", os.path.join(REPO, "scripts", "chemistry_mac.py"))
# Isolation: the doorway config is scratch, and nothing below may reach the Mac or ESMFold.
assert mac.CONFIG.startswith(HOME), mac.CONFIG


def never_mac(body):
    raise AssertionError("real Mac reached")


def never_esmfold(body):
    raise AssertionError("real ESMFold reached")


# What UniProt returns for P02794: ferritin heavy chain, gene FTH1, entry FRIH_HUMAN (names only; the
# sequence is short so the toy lattice route is taken and the stub transport sees it).
FERRITIN = {"primaryAccession": "P02794", "uniProtkbId": "FRIH_HUMAN",
            "genes": [{"geneName": {"value": "FTH1"}, "synonyms": [{"value": "FTH"}, {"value": "FTHL6"}]}],
            "proteinDescription": {"recommendedName": {"fullName": {"value": "Ferritin heavy chain"},
                                                       "shortNames": [{"value": "Ferritin H subunit"}]}},
            "sequence": {"value": "ACDEFGHI", "length": 8}}


def resolver(accession):
    assert accession == "P02794", accession
    return FERRITIN, {"provider": "UniProtKB", "accession": accession, "receipt_id": "receipt-test"}


sent = []


def transport(body):
    sent.append(body)
    p = body["parameters"]
    sequence = p["sequence"]
    result = {"title": "Folding %s (%d aa): %s" % (p["requested_accession"], len(sequence), sequence),
              "requested_accession": p["requested_accession"], "modeled_sequence": sequence,
              "modeled_sequence_length": len(sequence), "sequence_source": p["sequence_source"],
              "hp_mapping": mac._hp_mapping(sequence)}
    return {"ok": True, "run_id": "RUN-LABEL", "run": {"result": result}}


# The bug: labelled HFE, accession P02794. It must be refused before anything folds.
wrong = mac.run("protein", {"target_accession": "P02794", "protein_name": "HFE"},
                resolver=resolver, transport=never_mac, esmfold_worker=never_esmfold)
assert wrong["ok"] is False and wrong["refused"] == "protein_accession_mismatch", wrong
assert "HFE" in wrong["error"] and "FTH1" in wrong["error"], wrong["error"]
assert wrong["requested_accession"] == "P02794" and "FRIH_HUMAN" in wrong["record_names"]

# The same accession under its own names goes through, by gene symbol, synonym, entry name or protein name.
for label in ("FTH1", "fth1", "FTHL6", "FRIH", "ferritin heavy chain", "Ferritin H subunit"):
    sent.clear()
    good = mac.run("protein", {"target_accession": "P02794", "protein_name": label},
                   resolver=resolver, transport=transport, esmfold_worker=never_esmfold)
    assert good["ok"] is True and good["sequence_check"]["outcome"] == "SEQUENCE_ACCESSION_MATCH", (label, good)
    assert sent[0]["parameters"]["requested_protein"] == [label]
    assert good["sequence_request"]["requested_protein"] == [label]

# Two names given: both must be this protein.
mixed = mac.run("protein", {"target_accession": "P02794", "gene": "FTH1", "protein_name": "HFE"},
                resolver=resolver, transport=never_mac, esmfold_worker=never_esmfold)
assert mixed["ok"] is False and mixed["refused"] == "protein_accession_mismatch", mixed

# A plan that names no protein behaves exactly as before: the accession alone is enough.
sent.clear()
plain = mac.run("protein", {"target_accession": "P02794"}, resolver=resolver, transport=transport,
                esmfold_worker=never_esmfold)
assert plain["ok"] is True and "requested_protein" not in sent[0]["parameters"], plain

# A record that carries no names cannot prove a label: refused, not waved through.
nameless = mac.run("protein", {"target_accession": "P02794", "protein_name": "HFE"},
                   resolver=lambda accession: ({"primaryAccession": accession,
                                                "sequence": {"value": "ACDEFGHI", "length": 8}},
                                               {"provider": "UniProtKB", "accession": accession}),
                   transport=never_mac, esmfold_worker=never_esmfold)
assert nameless["ok"] is False and nameless["refused"] == "protein_accession_mismatch", nameless

# The planner asks for the label, and the UniProt fetch brings back the gene names the check reads.
session_source = open(os.path.join(REPO, "scripts", "chemistry_session.py"), encoding="utf-8").read()
assert "parameters.protein_name" in session_source, "the lens must be asked which protein it means"
sources_source = open(os.path.join(REPO, "scripts", "lab_sources.py"), encoding="utf-8").read()
assert "gene_names" in sources_source, "UniProt must be asked for gene names"

# "Full name (SYMBOL)" is the record's when both parts are (2026-10-05: A1L190 refused as "not Synaptonemal complex
# central element protein 3 (SYCE3)" while UniProt named it exactly that); a symbol that is not its own still refuses.
_syce3 = ["SYCE3_HUMAN", "SYCE3", "C22orf41", "THEG2", "Synaptonemal complex central element protein 3",
          "Testis highly expressed gene 2 protein"]
assert mac._names_match("Synaptonemal complex central element protein 3 (SYCE3)", _syce3)
assert mac._names_match("SYCE3 (Synaptonemal complex central element protein 3)", _syce3)
assert not mac._names_match("Synaptonemal complex central element protein 3 (FTH1)", _syce3)
assert not mac._names_match("Ferritin heavy chain (SYCE3)", _syce3)

assert not os.path.exists(os.path.expanduser("~/.vintos/chemistry-mac.json")) or HOME in os.path.expanduser("~/.vintos/chemistry-mac.json")
print("PASS a run labelled with one protein cannot fold another accession")
