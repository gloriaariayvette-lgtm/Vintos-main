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
        self.assertIn("relationship", question)
        self.assertNotIn("sequence length", question)

    def test_early_sourced_connection_is_attached_to_a_line(self):
        inquiry = C._inquiry({"question": C._record_connection_question("Tannase", "P78581"),
                              "uniprot_query": "accession:P78581"})
        attached = C._on_line(inquiry, {}, None)
        self.assertTrue(attached.get("line_opened"), attached)
        self.assertEqual(L.get(attached["line_id"])["state"], "open")
        L.end(attached["line_id"], "dropped", "test cleanup")

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
