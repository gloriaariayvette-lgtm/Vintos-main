#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class WantPlanLifecycleTests(unittest.TestCase):
    def test_creation_names_planner_empty_as_blocked(self):
        for rel in ("scripts/emoclaw_utils.py", "bin/emoclaw_utils.py"):
            text = (ROOT / rel).read_text(errors="replace")
            self.assertIn('entry["plan_state"] = "BLOCKED"', text, rel)
            self.assertIn('"PLANNER_NO_RESULT"', text, rel)

    def test_execution_door_repairs_legacy_missing_plans(self):
        text = (ROOT / "bin/wants-router.py").read_text(errors="replace")
        self.assertIn("def _ensure_plan", text)
        self.assertIn("_ensure_plan(want", text)
        self.assertIn('want["plan_state"] = "READY"', text)
        self.assertIn('want["plan_state"] = "BLOCKED"', text)

    def test_silence_and_elapsed_time_do_not_close_gloria_wants(self):
        text = (ROOT / "bin/wants-router.py").read_text(errors="replace")
        self.assertNotIn('dismissed_by"] = "gloria_no_reply"', text)
        self.assertNotIn("Fulfilled stale gloria-routed", text)
        self.assertIn('want["encounter_state"] = "HELD"', text)

    def test_entrypoint_is_after_the_helpers_main_calls(self):
        text = (ROOT / "bin/wants-router.py").read_text(errors="replace")
        entry = text.rindex('if __name__ == "__main__":')
        self.assertLess(text.index("def _mark_attempt"), entry)
        self.assertLess(text.index("def _open_gloria_discussion"), entry)

    def test_plan_repair_mode_never_executes_wants(self):
        text = (ROOT / "bin/wants-router.py").read_text(errors="replace")
        self.assertIn('"--repair-plans-only"', text)
        branch = text.index("if _args.repair_plans_only:")
        next_execution_loop = text.index("for want in wants:\n        text =", branch + 1)
        self.assertIn("return", text[branch:next_execution_loop])

    def test_deploy_owns_both_runtime_organs(self):
        deploy = (ROOT / "scripts/deploy-atelier.sh").read_text(errors="replace")
        self.assertIn("blush-ledger.py wants-router.py", deploy)


if __name__ == "__main__": unittest.main(verbosity=2)
