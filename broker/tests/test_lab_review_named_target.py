#!/usr/bin/env python3
"""An investigation's review establishes the target its question names, and still refuses a wrong one (26 October).

Three of that day's seven investigation reviews were refused by the entity check before anything was judged:
- two pendrin (O43511) structure investigations read O43511's ESMFold model and never searched UniProt, so "no
  retrieved record establishes the requested target", though the Lab holds the sourced O43511 record that model was
  folded from;
- a human AQP5 investigation ran the same UniProt search nine times and got human AQP5 as Swiss-Prot P55064 and as
  unreviewed A0ACI8R740, which read as "multiple retrieved targets require an explicit expectation mapping".

Scratch HOME and workspace; sockets refused; the model and the coverage checker are stubs that record their calls."""
import json, os, socket, sys, tempfile, unittest
from unittest.mock import patch
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-named-target-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C, lab_investigations as LI, lab_sources as S


def rec(acc, gene, name, entry, taxon=9606, organism="Homo sapiens", syn=(), aliases=()):
    return {"accession": acc, "id": entry, "protein_name": name, "taxon_id": taxon, "organism": organism,
            "protein_aliases": list(aliases),
            "genes": [{"geneName": {"value": gene}, "synonyms": [{"value": x} for x in syn]}],
            "function": "transports anions", "sequence": "MKV", "length": 3}


PENDRIN = rec("O43511", "SLC26A4", "Pendrin", "S26A4_HUMAN", syn=("PDS",))
AQP5 = rec("P55064", "AQP5", "Aquaporin-5", "AQP5_HUMAN")
AQP5_TREMBL = rec("A0ACI8R740", "AQP5", "Aquaporin-5", "A0ACI8R740_HUMAN")
AQP5_RAT = rec("P47864", "Aqp5", "Aquaporin-5", "AQP5_RAT", taxon=10116, organism="Rattus norvegicus")
AQP5_Q = ("What are the specific structural features of the human Aquaporin-5 (AQP5) pore and its associated "
          "selectivity filter?")
PENDRIN_Q = ("What is the precise mapping of the pendrin (O43511) protein domains, specifically the STAS domain and "
             "its orientation relative to the transmembrane helices?")
MODEL = "artifacts/esmfold/O43511-ac5611395a4c.pdb"


def fold_step(files=(MODEL,)):
    return {"id": "S-1", "state": "completed", "question": "fold read",
            "request": {"instrument_query": {"files": list(files), "operation": "structure.read"}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def ask(system, prompt, **k):
            self.calls.append(system[:40])
            return json.dumps({"answers_question": "no: stub", "attention": "", "factual_observation": "o",
                               "speculative_reading": "", "next_question": "n", "instrument_gap": ""})
        cover = lambda *a, **k: {"answered": False, "missing": ["stub"], "supports": [], "original_question": a[0]["question"]}
        self.stack = [patch.object(C, "_ask", ask), patch.object(C, "_coverage_check", cover)]
        for p in self.stack: p.start(); self.addCleanup(p.stop)

    def review(self, question, records, steps=None):
        obs = {"records": list(records), "LITERATURE": [], "prior_validated_evidence": [],
               "additional_source": {"receipt": {"source": "investigation", "records": []}}}
        if steps is not None: obs = LI._with_named_records(question, steps, obs)
        return C._reflect("", {"question": question}, obs), obs

    def refused(self, out):
        return "entity_context_check" in out and bool(out["entity_context_check"].get("issues"))


class Isolation(Base):
    def test_store_is_scratch_and_nothing_reaches_the_world(self):
        self.assertTrue(C.ROOT.startswith(HOME), C.ROOT)
        self.assertIs(socket.socket.connect, _no)
        self.assertEqual(NET, [])


class NamedAccession(Base):
    def test_before_the_fix_this_was_refused(self):
        out, _ = self.review(PENDRIN_Q, [])
        self.assertTrue(self.refused(out))
        self.assertIn("no retrieved record establishes the requested target", out["missing_evidence"])

    def test_the_lab_sourced_record_of_the_named_accession_establishes_it(self):
        with patch.object(C, "_sourced_record", side_effect=lambda a: dict(PENDRIN) if a == "O43511" else None):
            out, obs = self.review(PENDRIN_Q, [], [fold_step()])
        self.assertFalse(self.refused(out), out.get("missing_evidence"))
        self.assertEqual(out["entity_context_check"]["selected_accessions"], ["O43511"])
        added = [r for r in obs["records"] if r.get("identity_basis")]
        self.assertEqual([r["accession"] for r in added], ["O43511"])
        self.assertEqual(added[0]["identity_basis"], "lab_sourced_uniprot_record_not_fetched_by_this_investigation")

    def test_nothing_is_added_for_an_accession_no_step_worked_on(self):
        with patch.object(C, "_sourced_record", side_effect=lambda a: dict(PENDRIN)):
            out, obs = self.review(PENDRIN_Q, [], [fold_step(("artifacts/esmfold/P55064-0123456789ab.pdb",))])
        self.assertEqual(obs["records"], [])
        self.assertTrue(self.refused(out))

    def test_a_saved_record_of_another_accession_is_never_used(self):
        with patch.object(C, "_sourced_record", side_effect=lambda a: dict(AQP5)):
            out, obs = self.review(PENDRIN_Q, [], [fold_step()])
        self.assertEqual(obs["records"], [])
        self.assertTrue(self.refused(out))

    def test_a_record_the_investigation_already_fetched_is_not_doubled(self):
        with patch.object(C, "_sourced_record", side_effect=lambda a: dict(PENDRIN)) as looked:
            _out, obs = self.review(PENDRIN_Q, [PENDRIN], [fold_step()])
        self.assertEqual(len(obs["records"]), 1)
        looked.assert_not_called()

    def test_a_wrong_name_beside_the_accession_is_still_refused(self):
        q = "What is the domain map of human GLUT1 (O43511)?"
        with patch.object(C, "_sourced_record", side_effect=lambda a: dict(PENDRIN)):
            out, _ = self.review(q, [], [fold_step()])
        self.assertTrue(self.refused(out))
        self.assertIn("requested names not established by O43511: GLUT1", out["missing_evidence"])

    def test_a_gene_synonym_or_short_name_beside_the_accession_establishes_it(self):
        for q in ("What is the domain map of human PDS (O43511)?", "What is the domain map of human SLC26A4 (O43511)?"):
            out, _ = self.review(q, [PENDRIN])
            self.assertFalse(self.refused(out), (q, out.get("missing_evidence")))
        short = rec("Q00001", "ABC1", "Long recommended protein name", "ABC1_HUMAN", aliases=("LRPN",))
        out, _ = self.review("Where does human LRPN localize?", [short])
        self.assertFalse(self.refused(out), out.get("missing_evidence"))

    def test_normalized_records_carry_uniprot_short_names(self):
        raw = {"primaryAccession": "O43511", "uniProtkbId": "S26A4_HUMAN",
               "proteinDescription": {"recommendedName": {"fullName": {"value": "Pendrin"},
                                                          "shortNames": [{"value": "PDS1"}]},
                                      "alternativeNames": [{"fullName": {"value": "Sodium-independent chloride/iodide transporter"},
                                                            "shortNames": [{"value": "SICT"}]}]},
               "organism": {"scientificName": "Homo sapiens", "taxonId": 9606}, "genes": [], "sequence": {"value": "M"}}
        row = C.normalize_protein_records([raw])[0]
        self.assertEqual(row["protein_aliases"], ["Sodium-independent chloride/iodide transporter", "PDS1", "SICT"])


class OneNamedTarget(Base):
    def test_repeats_and_an_unreviewed_twin_map_to_the_curated_entry(self):
        e = S.question_entity_context({"question": AQP5_Q}, [AQP5, AQP5_RAT, AQP5_TREMBL] * 9)
        self.assertEqual(e["status"], "consistent", e["issues"])
        self.assertEqual(e["selected_accessions"], ["P55064"])
        self.assertEqual(e["target_mapping"], {"AQP5": "P55064"})
        self.assertEqual(e["set_aside_accessions"], ["A0ACI8R740"])

    def test_the_review_goes_on_to_the_mapped_target(self):
        out, _ = self.review(AQP5_Q, [AQP5, AQP5_TREMBL, AQP5_RAT, AQP5])
        self.assertFalse(self.refused(out), out.get("missing_evidence"))
        self.assertEqual(out["entity_context_check"]["target_mapping"], {"AQP5": "P55064"})

    def test_the_same_entry_fetched_twice_is_one_target(self):
        e = S.question_entity_context({"question": AQP5_Q}, [AQP5, AQP5])
        self.assertEqual(e["status"], "consistent", e["issues"])
        self.assertEqual(e["selected_accessions"], ["P55064"])

    def test_two_curated_entries_stay_refused(self):
        other = rec("P99999", "AQP5", "Aquaporin-5", "AQP5B_HUMAN")
        e = S.question_entity_context({"question": AQP5_Q}, [AQP5, other])
        self.assertIn("multiple retrieved targets require an explicit expectation mapping", e["issues"])

    def test_two_unreviewed_entries_stay_refused(self):
        other = rec("A0A000AAA1", "AQP5", "Aquaporin-5", "A0A000AAA1_HUMAN")
        e = S.question_entity_context({"question": AQP5_Q}, [AQP5_TREMBL, other])
        self.assertIn("multiple retrieved targets require an explicit expectation mapping", e["issues"])

    def test_the_wrong_species_is_still_refused(self):
        e = S.question_entity_context({"question": AQP5_Q}, [AQP5_RAT])
        self.assertTrue(e["issues"])
        self.assertTrue(any("taxon" in x for x in e["issues"]), e["issues"])

    def test_a_record_of_another_protein_is_still_refused(self):
        e = S.question_entity_context({"question": AQP5_Q}, [rec("P57764", "GSDMD", "Gasdermin-D", "GSDMD_HUMAN")])
        self.assertTrue(e["issues"])
        self.assertTrue(any("AQP5" in x for x in e["issues"]), e["issues"])

    def test_curated_is_read_from_the_flag_before_the_entry_name(self):
        self.assertTrue(S.curated_entry(AQP5))
        self.assertFalse(S.curated_entry(AQP5_TREMBL))
        self.assertFalse(S.curated_entry(dict(AQP5, curated=False)))
        self.assertFalse(S.curated_entry({"accession": "P55064"}))


if __name__ == "__main__":
    unittest.main()
