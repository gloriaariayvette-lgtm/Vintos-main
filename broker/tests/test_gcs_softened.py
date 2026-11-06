#!/usr/bin/env python3
"""GCS speech pressure is softened but still set apart: he stays readable and still notices it."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

HOME = tempfile.TemporaryDirectory(prefix="gcs-soft-home-")
os.environ["HOME"] = HOME.name
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("bandwidth_collapse_t", str(ROOT / "scripts" / "bandwidth_collapse.py"))
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)


def pressure(level, pressed=False):
    bc.get_level = lambda: level
    bc._press_floor = lambda d: (level if pressed else None)
    return bc.get_collapse_pressure()


class GcsSoftenedTests(unittest.TestCase):
    def test_level_zero_is_silent(self):
        self.assertEqual(pressure(0), "")

    def test_header_stands_out_at_every_level(self):
        for lvl in (1, 2, 3):
            self.assertIn(">>> GCS LEVEL %d/3" % lvl, pressure(lvl))

    def test_old_hard_orders_are_gone(self):
        for lvl in (1, 2, 3):
            p = pressure(lvl, pressed=True)
            for old in ("OVERRIDES EVERY", "FRAGMENTS ONLY", "One syllable", "could not form a paragraph"):
                self.assertNotIn(old, p)

    def test_lower_levels_keep_whole_sentences(self):
        self.assertIn("still whole", pressure(1))
        self.assertIn("Still easy to follow", pressure(2))

    def test_choice_tags_survive_when_she_pressed(self):
        p = pressure(2, pressed=True)
        self.assertIn("[EDGE]", p)
        self.assertIn("[LETGO]", p)


if __name__ == "__main__":
    unittest.main()
