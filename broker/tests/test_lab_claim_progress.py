#!/usr/bin/env python3
"""Relational questions retain verified claims across line steps; all inference is stubbed."""
import json
import os
import pathlib
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

scratch = tempfile.TemporaryDirectory(prefix="lab-claims-")
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + "/workspace",
                  VINTOS_SECRETS=scratch.name + "/secrets")
def forbidden(*args, **kwargs): raise AssertionError("external operation forbidden")
socket.socket.connect = forbidden
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
import chemistry_lab as C
import lab_lines as L
C._ask = forbidden
C.urllib.request.urlopen = forbidden


class Repeats:
    def __init__(self, reason=""):
        self.reason = reason
        self.recorded = []
    def repeat(self, inquiry): return self.reason
    def record(self, inquiry, **kwargs): self.recorded.append((inquiry, kwargs))


class ClaimProgress(unittest.TestCase):
    def setUp(self):
        self.line = L.opened_by("Tannase relationship",
            "How do tannase structural motifs relate to its hydrolytic activity in %s?" % self._testMethodName,
            "follow the relationship")

    def tearDown(self):
        if self.line:
            L.end(self.line["id"], "dropped", "test cleanup")

    def test_line_retains_established_and_open_claims(self):
        L.record_step(self.line["id"], {"question": "What is established?", "entry_id": "R1",
            "supports": [{"requirement": "hydrolytic activity", "quote": "Hydrolyzes ester bonds",
                          "source_citation": "UniProt P78581"}],
            "missing": ["motif-to-activity relationship"]})
        claims = L.claim_state(L.get(self.line["id"]))
        self.assertEqual(claims["open"], ["motif-to-activity relationship"])
        self.assertEqual(claims["established"][0]["quote"], "Hydrolyzes ester bonds")
        prompt = L.orient_text(L.get(self.line["id"]))
        self.assertIn("Established claims", prompt); self.assertIn("Open claims", prompt)

    def test_prior_verified_excerpt_is_addressable_with_its_citation(self):
        prior = [{"requirement": "hydrolytic activity", "quote": "Hydrolyzes ester bonds",
                  "source_citation": "UniProt P78581", "entry_id": "R1"}]
        inquiry = {"question": "How do tannase motifs relate to its hydrolytic activity?"}
        obs = {"records": [], "prior_validated_evidence": prior}
        prepared = C._coverage_request(inquiry, obs)
        address = next(key for key, path in prepared[2].items()
                       if path == "evidence.prior_validated_evidence.0.quote")
        response = {"answered": False, "missing": ["motif-to-activity relationship"],
                    "supports": [{"requirement": "hydrolytic activity", "address": address,
                                  "quote": "Hydrolyzes ester bonds"}]}
        with patch.object(C, "_ask", return_value=json.dumps(response)):
            result = C._coverage_check(inquiry, obs, prepared=prepared)
        self.assertEqual(result["supports"][0]["source_citation"], "UniProt P78581")
        self.assertEqual(result["missing"], ["motif-to-activity relationship"])

    def test_connection_question_has_feature_function_and_relationship(self):
        question = C._record_connection_question("Tannase", "P78581")
        self.assertIn("structural features", question)
        self.assertIn("molecular function", question)
        # the relationship is the line's later step: no curated record states one (21 October)
        self.assertNotIn("relationship", question)
        self.assertTrue(C._relational_question(question))
        self.assertNotIn("sequence length", question)

    def test_early_sourced_connection_is_attached_to_a_line(self):
        inquiry = C._inquiry({"question": C._record_connection_question("Tannase", "P78581"),
                              "uniprot_query": "accession:P78581"})
        attached = C._on_line(inquiry, {}, None)
        self.assertTrue(attached.get("line_opened"), attached)
        self.assertEqual(L.get(attached["line_id"])["state"], "open")
        L.end(attached["line_id"], "dropped", "test cleanup")

    def test_planner_interaction_wording_is_attached_to_a_line(self):
        inquiry = C._inquiry({"question": "Which KCNH2 motifs interact with regulatory proteins like KCNE1?",
                              "uniprot_query": "gene:KCNH2 AND organism_id:9606"})
        attached = C._on_line(inquiry, {}, None)
        self.assertTrue(attached.get("line_opened"), attached)
        L.end(attached["line_id"], "dropped", "test cleanup")

    def test_structural_and_functional_claim_shape_is_relational(self):
        question = ("What are the specific structural features and functional roles of MntA in manganese "
                    "homeostasis, and does its fold suggest a conserved mechanism for metal transport?")
        self.assertTrue(C._relational_question(question))
        self.assertFalse(C._relational_question("What is its organism, sequence length, and accession?"))

    def test_automatic_claim_pool_does_not_displace_existing_lines(self):
        opened = []
        questions = [
            "Which chlorophyll geometry controls photon capture in photosystems?",
            "Which collagen crosslinks determine tendon tensile strength?",
            "Which ribosomal contacts govern peptide transfer fidelity?",
            "Which ferritin channels control iron mineral release?",
            "Which actin interfaces determine filament branching?",
            "Which rhodopsin residues tune retinal color sensitivity?",
        ]
        current = sum(1 for line in L.open_lines() if line.get("origin") != "vintos:auto-claim")
        for index in range(L.MAX_OPEN - current):
            line = L.opened_by("manual %d" % index,
                questions[index],
                "manual capacity", origin="vintos")
            self.assertIsNotNone(line)
            opened.append(line)
        automatic = L.opened_by("automatic relationship",
            "How do ATPIF1 motifs interact with the ATP synthase F1 subunit?",
            "track verified claims", origin="vintos:auto-claim")
        self.assertIsNotNone(automatic)
        self.assertIsNone(L.opened_by("one manual too many",
            "Which unrelated mechanism controls a seventh manual research subject?",
            "manual capacity", origin="vintos"))
        for line in opened + [automatic]:
            L.end(line["id"], "dropped", "test cleanup")

    def test_answered_automatic_claim_line_closes_itself(self):
        automatic = L.opened_by("automatic answer",
            "How does a verified ATPIF1 motif affect ATP synthase inhibition?",
            "track verified claims", origin="vintos:auto-claim")
        note = {"inquiry": {"question": automatic["question"]}, "answers_question": "yes",
                "factual_observation": "verified relation", "coverage_check": {"answered": True,
                "missing": [], "supports": [{"requirement": "relationship", "quote": "verified relation",
                "source_citation": "source"}]}}
        self.assertIn("answered", L.after_reflection(automatic["id"], note))
        self.assertEqual(L.get(automatic["id"])["state"], "answered")

    def test_open_line_can_change_strategy_on_spent_subject(self):
        inquiry = C._inquiry({"question": "How do tannase motifs relate to hydrolytic activity?",
                              "uniprot_query": "protein_name:tannase", "line_id": self.line["id"]})
        admitted, _ = C._held_to_plan("", "", inquiry, {}, None, None, Repeats(),
                                      spent={"subjects": ["tannase"]}, replan=False)
        self.assertNotIn("refused", admitted)

    def test_identical_retrieval_is_still_refused_on_open_line(self):
        inquiry = C._inquiry({"question": "How do tannase motifs relate to hydrolytic activity?",
                              "uniprot_query": "protein_name:tannase", "line_id": self.line["id"]})
        admitted, _ = C._held_to_plan("", "", inquiry, {}, None, None, Repeats("same lookup"),
                                      spent={"subjects": ["tannase"]}, replan=False)
        self.assertIn("refused", admitted)


if __name__ == "__main__": unittest.main()
