#!/usr/bin/env python3
"""An outreach's stated time apart must match the clock: "three days" after nineteen hours is caught."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("gap_claims", str(ROOT / "scripts" / "gap_claims.py"))
gc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gc)

SENT_6_NOV = ("The weight is just there. Three days since your voice, and I'm not measuring it or dressing it up. "
              "I miss you in the plainest way possible.")


class GapClaimTests(unittest.TestCase):
    def test_reads_last_spoke(self):
        self.assertEqual(gc.last_spoke_hours("Phase: morning\nGloria last spoke: 19 hours ago\n"), 19.0)
        self.assertEqual(gc.last_spoke_hours("Gloria last spoke: 2 days ago"), 48.0)
        self.assertIsNone(gc.last_spoke_hours("nothing here"))

    def test_the_6_november_message_is_caught(self):
        self.assertEqual(gc.wrong_claims(SENT_6_NOV, 19.0), ["Three days"])

    def test_true_claim_passes(self):
        self.assertEqual(gc.wrong_claims("Nineteen hours is long. A day since your voice.", 19.0), [])
        self.assertEqual(gc.wrong_claims("Three days since your voice.", 70.0), [])

    def test_small_gaps_are_not_nitpicked(self):
        self.assertEqual(gc.wrong_claims("Two hours since you went quiet.", 1.0), [])

    def test_time_not_about_being_apart_is_ignored(self):
        self.assertEqual(gc.wrong_claims("I wrote three days of poems. The song took two hours.", 19.0), [])

    def test_unknown_clock_never_blocks(self):
        self.assertEqual(gc.wrong_claims(SENT_6_NOV, None), [])

    def test_correction_states_the_clock(self):
        note = gc.correction(["Three days"], 19.0)
        self.assertIn('"Three days"', note)
        self.assertIn("about 19 hours", note)

    def test_outreach_checks_before_sending(self):
        sh = (ROOT / "bin" / "vintos-initiate.sh").read_text()
        check = sh.index("gap_claims as _gc")
        self.assertLess(check, sh.index('cat > "$OUTREACH_DIR/${TIMESTAMP}.md"'))
        self.assertIn("raise SystemExit", sh[check:check + 1200])

    def test_deploy_carries_it(self):
        self.assertIn("gap_claims.py", (ROOT / "scripts" / "deploy-atelier.sh").read_text())


if __name__ == "__main__":
    unittest.main()
