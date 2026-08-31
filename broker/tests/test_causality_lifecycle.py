#!/usr/bin/env python3
"""Causality tenure is seven honest nights, never seven days plus one story."""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_engine():
    spec = importlib.util.spec_from_file_location(
        "causality_lifecycle_test", ROOT / "scripts" / "causality-engine.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CausalityLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.c = load_engine()

    def hypothesis(self, formed="2026-08-20", material="a different formation event"):
        h = {
            "formed": formed + "T04:00:00",
            "formed_date": formed,
            "status": "untested",
            "marks": [],
            "days_tested": 0,
            "graduated": False,
            "hypothesis": "Plain speech lowers the need to brace.",
            "test": "Notice a new occasion for plain speech.",
            "source": "test",
            "subject": "self",
        }
        return self.c._stamp_formation(h, material)

    def test_every_due_hypothesis_gets_yes_no_or_unconfirmed(self):
        hs = [self.hypothesis() for _ in range(3)]
        db = {"hypotheses": hs, "tested": 0}
        ctx = {"interactions": "[09:12] Gloria: stay | Vintos: I stayed plainly"}
        eid = self.c._build_evidence_catalog(ctx, "2026-08-21")[0]["id"]
        self.c.ask_llm = lambda *a, **k: (
            f"1. RECURRED: yes\n1. EVIDENCE_IDS: {eid}\n"
            "1. EVIDENCE: At 09:12 he answered the actual question plainly.\n\n"
            f"2. RECURRED: no\n2. EVIDENCE_IDS: {eid}\n"
            "2. EVIDENCE: At 09:12 the occasion arose and bracing stayed present.\n\n"
            "3. RECURRED: unsure\n3. EVIDENCE_IDS: none\n"
            "3. EVIDENCE: Nothing today bore on this either way."
        )
        self.c.test_existing_hypotheses(
            db, {}, today="2026-08-21", context=ctx)
        self.assertEqual([h["marks"][-1]["verdict"] for h in hs],
                         ["yes", "no", "unconfirmed"])
        self.assertTrue(all(h["last_tested"] == "2026-08-21" for h in hs))
        self.assertEqual(db["tested"], 3)

    def test_formation_day_is_never_a_test_day(self):
        h = self.hypothesis(formed="2026-08-21")
        db = {"hypotheses": [h], "tested": 0}
        self.c.ask_llm = lambda *a, **k: self.fail("formation-day evaluator was called")
        self.c.test_existing_hypotheses(
            db, {}, today="2026-08-21", context={"interactions": "something"})
        self.assertEqual(h["marks"], [])

    def test_formation_root_cannot_confirm_its_own_hypothesis(self):
        root = "[09:12] Gloria: stay | Vintos: I stayed plainly"
        h = self.hypothesis(material=root)
        db = {"hypotheses": [h], "tested": 0}
        ctx = {"interactions": root}
        eid = self.c._build_evidence_catalog(ctx, "2026-08-21")[0]["id"]
        self.c.ask_llm = lambda *a, **k: (
            f"1. RECURRED: yes\n1. EVIDENCE_IDS: {eid}\n"
            "1. EVIDENCE: At 09:12 he answered the actual question plainly."
        )
        self.c.test_existing_hypotheses(db, {}, today="2026-08-21", context=ctx)
        mark = h["marks"][-1]
        self.assertEqual(mark["verdict"], "unconfirmed")
        self.assertEqual(mark["reason"], "formation_root_cannot_witness")
        self.assertEqual(mark["lineage_state"], "ineligible")

    def test_same_evidence_cannot_vote_twice_under_a_new_daily_id(self):
        h = self.hypothesis()
        text = "[09:12] Gloria: stay | Vintos: I stayed plainly"
        first = self.c._catalog_item("2026-08-21", "interactions", text, 0)
        second = self.c._catalog_item("2026-08-22", "interactions", text, 0)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.c._record_nightly(h, "2026-08-21", "yes", "a concrete first occasion", [first])
        self.c._record_nightly(h, "2026-08-22", "yes", "the same occasion copied", [second])
        self.assertEqual(h["marks"][-1]["verdict"], "unconfirmed")
        self.assertEqual(h["marks"][-1]["reason"], "evidence_occasion_reused")

    def test_seven_nights_plus_only_one_yes_does_not_graduate(self):
        h = self.hypothesis(formed="2026-08-01")
        for n in range(1, 8):
            day = f"2026-08-{n+1:02d}"
            if n == 1:
                item = self.c._catalog_item(day, "interactions", "a new concrete occasion", 0)
                self.c._record_nightly(h, day, "yes", "a new concrete occasion supported it", [item])
            else:
                self.c._record_nightly(h, day, "unconfirmed", reason="no_bearing_evidence")
        ready = self.c.graduation_readiness(h, today="2026-08-08")
        self.assertEqual(ready["state"], "HELD")
        self.assertEqual(ready["reason"], "independent_support_insufficient")
        self.assertEqual(ready["nightly_evaluations"], 7)

    def test_two_distinct_yes_votes_across_seven_nights_are_eligible(self):
        h = self.hypothesis(formed="2026-08-01")
        for n in range(1, 8):
            day = f"2026-08-{n+1:02d}"
            if n in (1, 5):
                item = self.c._catalog_item(day, "interactions", f"new occasion number {n}", 0)
                self.c._record_nightly(h, day, "yes", f"new concrete occasion number {n}", [item])
            else:
                self.c._record_nightly(h, day, "unconfirmed", reason="no_bearing_evidence")
        ready = self.c.graduation_readiness(h, today="2026-08-08")
        self.assertEqual(ready["state"], "eligible_day_7")
        self.assertEqual((ready["yes"], ready["no"], ready["unconfirmed"]), (2, 0, 5))

    def test_legacy_marks_cannot_impersonate_lineaged_nightly_trials(self):
        h = self.hypothesis(formed="2026-08-01")
        h["marks"] = [{"date": "2026-08-02", "outcome": "attempted",
                       "evidence": "old prose without ids"}] * 7
        ready = self.c.graduation_readiness(h, today="2026-08-20")
        self.assertEqual(ready["state"], "HELD")
        self.assertEqual(ready["reason"], "nightly_history_incomplete")

    def test_unreachable_reviewer_cannot_turn_eligibility_into_graduation(self):
        h = self.hypothesis(formed="2026-08-01")
        for n in range(1, 8):
            day = f"2026-08-{n+1:02d}"
            if n in (1, 5):
                item = self.c._catalog_item(day, "interactions", f"new review occasion {n}", 0)
                self.c._record_nightly(h, day, "yes", f"new review occasion {n} supported it", [item])
            else:
                self.c._record_nightly(h, day, "unconfirmed", reason="no_bearing_evidence")
        db = {"hypotheses": [h]}
        fake_requests = types.SimpleNamespace(
            post=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("reviewer down")))
        old_requests = sys.modules.get("requests")
        with tempfile.TemporaryDirectory() as td:
            self.c.MEMORY = td
            sys.modules["requests"] = fake_requests
            try:
                graduated, vanished = self.c.graduate_hypotheses(db)
            finally:
                if old_requests is None:
                    sys.modules.pop("requests", None)
                else:
                    sys.modules["requests"] = old_requests
        self.assertEqual((graduated, vanished), (0, 0))
        self.assertFalse(h["graduated"])
        self.assertEqual(h["status"], "review_held")
        self.assertIn(h, db["hypotheses"])

    def test_empty_material_is_recorded_not_silently_skipped(self):
        h = self.hypothesis()
        db = {"hypotheses": [h], "tested": 0}
        self.c.test_existing_hypotheses(db, {}, today="2026-08-21", context={})
        self.assertEqual(h["marks"][-1]["verdict"], "unconfirmed")
        self.assertEqual(h["marks"][-1]["reason"], "no_new_evidence_occasions")

    def test_expiry_cannot_delete_an_unresolved_hypothesis(self):
        source = (ROOT / "scripts" / "causality-engine.py").read_text()
        self.assertNotIn("Hard-expired", source)
        self.assertNotIn("db[\"hypotheses\"] = [h for h in db[\"hypotheses\"]", source)

    def test_deployed_twins_are_the_same_file(self):
        dashed = ROOT / "scripts" / "causality-engine.py"
        underscored = ROOT / "scripts" / "causality_engine.py"
        self.assertEqual(dashed.read_bytes(), underscored.read_bytes())

    def test_app_distinguishes_unconfirmed_from_untested(self):
        server = (ROOT / "bin" / "server.py").read_text()
        self.assertIn('status = "UNCONFIRMED"', server)
        self.assertIn('status = "LEGACY EVALUATED"', server)
        self.assertIn('"nightly_evaluations": len(nightly)', server)


if __name__ == "__main__":
    unittest.main()
