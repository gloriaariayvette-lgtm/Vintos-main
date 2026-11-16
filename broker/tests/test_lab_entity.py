#!/usr/bin/env python3
"""LAB_ENTITY_GROUNDING (draft, 17 Nov): an investigation whose protein is resolved is offered only that protein's
structure models (plus reference structures), labelled; an instrument step on another protein's model is refused as
off_target_structure; an unresolved investigation, or the switch off, is planned exactly as before. Synthetic
fixtures in scratch stores only; every sender is blocked by the shared sandbox."""
import json
import os
from pathlib import Path
import unittest
import test_lab_tool_routing as sandbox
import lab_instruments
import lab_investigations as I
import lab_entity as E
import lab_planner_trial as T

C = sandbox.C
PEN = "artifacts/esmfold/O43511-60e20d840671.pdb"     # pendrin model
INS = "artifacts/esmfold/P01308-9165820aee40.pdb"     # insulin model
REF = "artifacts/reference/7WK1.cif"
UNIPROT = {"results": [{"primaryAccession": "%s", "genes": [{"geneName": {"value": "%s"}}],
                        "proteinDescription": {"recommendedName": {"fullName": {"value": "%s"}}}}]}


def uniprot_step(sid, acc, gene, name, state="completed"):
    out = "investigation-outputs/%s.json" % sid
    p = lab_instruments.LAB / out
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(json.loads(json.dumps(UNIPROT) % (acc, gene, name))))
    return {"id": sid, "state": state, "route": "source", "tool": "source:uniprot", "output_file": out,
            "request": {"source": "uniprot", "query": "accession:%s" % acc},
            "executed_request": {"source": "uniprot", "query": "accession:%s" % acc}}


class Base(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(lab_instruments.LAB.resolve().is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        os.environ.pop("LAB_ENTITY_GROUNDING", None)
        for f in (PEN, INS, REF):
            p = lab_instruments.LAB / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("MODEL\n")
        self.lib = {"id": "I-lib", "question": "library", "steps": [uniprot_step("S-pen", "O43511", "SLC26A4", "Pendrin"),
                                                                     uniprot_step("S-ins", "P01308", "INS", "Insulin")]}
        self.save([self.lib])

    def tearDown(self):
        os.environ.pop("LAB_ENTITY_GROUNDING", None)

    def save(self, invs):
        C._atomic(I._path("investigations.json"), {"investigations": invs})
        E._CACHE.update(key=None, ids={})

    def on(self):
        os.environ["LAB_ENTITY_GROUNDING"] = "1"


class Off(Base):
    def test_off_by_default_nothing_changes(self):
        inv = {"id": "I-1", "question": "What does P01308 look like?", "steps": []}
        self.assertFalse(E.enabled())
        self.assertEqual(E.structure_menu(inv, 8), lab_instruments.artifacts("structure", 8))
        self.assertIsNone(E.problem(inv, "instrument", {"skill": "fold_read", "files": [PEN]}))
        self.assertEqual(E.note(inv), "")


class On(Base):
    def test_identities_come_from_completed_uniprot_lookups(self):
        self.assertEqual(E.identities()["O43511"], (["SLC26A4"], "Pendrin"))
        self.assertEqual(E.labels([PEN, REF]), {PEN: "SLC26A4 (Pendrin)"})

    def test_resolved_from_the_question_or_a_completed_lookup_in_it(self):
        self.assertEqual(E.resolved({"question": "Is P01308 stable?", "steps": []}), {"P01308"})
        inv = {"question": "Insulin fold?", "steps": [uniprot_step("S-x", "P01308", "INS", "Insulin")]}
        self.assertEqual(E.resolved(inv), {"P01308"})
        failed = {"question": "Insulin fold?", "steps": [uniprot_step("S-y", "P01308", "INS", "Insulin", "failed")]}
        self.assertEqual(E.resolved(failed), set())

    def test_menu_offers_only_this_proteins_models_and_references(self):
        self.on()
        menu = E.structure_menu({"question": "Is P01308 stable?", "steps": []}, 8)
        self.assertIn(INS, menu)
        self.assertIn(REF, menu)
        self.assertNotIn(PEN, menu)

    def test_another_proteins_model_is_refused_with_its_identity(self):
        self.on()
        inv = {"question": "Is P01308 stable?", "steps": []}
        why = E.problem(inv, "instrument", {"skill": "structure_viewer", "files": [PEN]})
        self.assertIn("SLC26A4 (Pendrin)", why)
        self.assertIn("P01308", why)
        self.assertIsNone(E.problem(inv, "instrument", {"skill": "structure_viewer", "files": [INS]}))
        self.assertIsNone(E.problem(inv, "instrument", {"skill": "reference_compare", "files": [INS, REF]}))
        self.assertIsNone(E.problem(inv, "source", {"source": "uniprot", "query": "accession:O43511"}))

    def test_unresolved_investigation_is_planned_as_before(self):
        self.on()
        inv = {"question": "What do helix cores in this region do?", "steps": []}
        self.assertEqual(E.structure_menu(inv, 8), lab_instruments.artifacts("structure", 8))
        self.assertIsNone(E.problem(inv, "instrument", {"skill": "fold_read", "files": [PEN]}))
        self.assertEqual(E.note(inv), "")

    def test_acquire_first_when_no_model_of_the_protein_is_held(self):
        self.on()
        self.assertIn("acquire it first", E.note({"question": "Is Q9Y6K9 a kinase?", "steps": []}))
        self.assertEqual(E.note({"question": "Is P01308 stable?", "steps": []}), "")

    def test_the_planner_trial_check_names_the_new_rule(self):
        self.on()
        inv = {"id": "I-2", "question": "Is P01308 stable?", "steps": []}
        self.save([self.lib, inv])
        value = {"route": "instrument", "question": inv["question"], "request": {
            "skill": "fold_read", "operation": "structure.read", "files": [PEN], "range": [1, 10],
            "question": "read the helices of this model"}}
        rule, words = T.explain(value, inv)
        self.assertEqual(rule, "off_target_structure")
        self.assertIn("Pendrin", words)

    def test_the_planner_task_lists_identities_only_when_on(self):
        inv = {"id": "I-3", "question": "Is P01308 stable?", "steps": []}
        menu_off = E.structure_menu(inv, 8)
        self.on()
        self.assertNotEqual(set(E.structure_menu(inv, 8)), set(menu_off))
        self.assertEqual(E.labels(E.structure_menu(inv, 8)).get(INS), "INS (Insulin)")


if __name__ == "__main__":
    unittest.main()
