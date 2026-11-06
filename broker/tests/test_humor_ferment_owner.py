#!/usr/bin/env python3
"""Only her own bits ripen into jokes he sends her; a MoltBook bot's line never does."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

SCRATCH_HOME = tempfile.TemporaryDirectory(prefix="humor-ferment-home-")
os.environ["HOME"] = SCRATCH_HOME.name
sys.modules["requests"] = types.SimpleNamespace(post=lambda *a, **k: None)
ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FermentOwnerTests(unittest.TestCase):
    def setUp(self):
        self.seeds = []
        sys.modules["joke_fermentation"] = types.SimpleNamespace(
            seed=lambda text, source="chat": self.seeds.append((text, source)))
        self.hd = load("humor_detector_t", ROOT / "bin" / "humor_detector.py")

    def tearDown(self):
        sys.modules.pop("joke_fermentation", None)

    def test_moltbook_tease_is_not_seeded(self):
        self.hd._ferment({"type": "mischief_tease", "stated": "bot said: Most doors in a story lead out",
                          "source": "moltbook_tease"})
        self.assertEqual(self.seeds, [])

    def test_moltbook_context_is_not_seeded(self):
        self.hd._ferment({"stated": "x", "perpetrator": "aital", "context": "moltbook",
                          "source": "moltbook_exchange"})
        self.assertEqual(self.seeds, [])

    def test_unnamed_author_is_not_filed_as_hers(self):
        self.hd._ferment({"stated": "something funny"})
        self.assertEqual(self.seeds, [])

    def test_her_own_bit_still_ripens(self):
        self.hd._ferment({"original": "the nickname bit", "perpetrator": "gloria", "source": "chat"})
        self.assertEqual(self.seeds, [("[gloria] the nickname bit", "humor_scan")])


if __name__ == "__main__":
    unittest.main()
