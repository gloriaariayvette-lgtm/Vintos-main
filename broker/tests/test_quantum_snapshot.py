#!/usr/bin/env python3
import importlib.util
import json
import os
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
spec = importlib.util.spec_from_file_location("quantum_snapshot",
    os.path.join(ROOT, "scripts", "quantum_snapshot.py"))
QS = importlib.util.module_from_spec(spec); spec.loader.exec_module(QS)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_mem, self.old_out = QS.MEM, QS.OUT
        QS.MEM = self.tmp.name; QS.OUT = os.path.join(self.tmp.name, "quantum-inputs")

    def tearDown(self):
        QS.MEM, QS.OUT = self.old_mem, self.old_out
        self.tmp.cleanup()

    def write(self, name, body, raw=False):
        with open(os.path.join(self.tmp.name, name), "w") as f:
            f.write(body if raw else json.dumps(body))

    def test_current_numbers_become_optional_palettes(self):
        self.write("emotional-state.txt",
                   "Arousal: 0.703\nWarmth: 0.5\nTension: 0.4\nPlayfulness: 0.8\n", raw=True)
        self.write("withheld.json", {"confidence": 0.85, "novelty": 0.625})
        self.write("relationship-model.json", {"current_state": {"depth": 0.7}})
        self.write("gloria-model.json", {"current_state": {"warmth": 1.0, "tension": 0.2,
                                                               "playfulness": 0.8}})
        got = QS.refresh()
        self.assertIn("emotion_withheld", got["prepared"])
        self.assertIn("relationship_entanglement", got["prepared"])
        with open(os.path.join(QS.OUT, "emotion_withheld.json")) as f:
            emotion = json.load(f)
        with open(os.path.join(QS.OUT, "relationship_entanglement.json")) as f:
            relation = json.load(f)
        self.assertEqual(emotion["felt_intensity"], 0.703)
        self.assertEqual(emotion["withheld_pressure"], 0.85)
        self.assertEqual(relation["his"]["play"], 0.8)
        self.assertEqual(relation["her_predicted"]["warmth"], 1.0)

    def test_missing_pass_does_not_erase_an_older_palette(self):
        os.makedirs(QS.OUT)
        path = os.path.join(QS.OUT, "emotion_withheld.json")
        self.write("quantum-inputs/emotion_withheld.json", {"felt_intensity": 0.9})
        QS.refresh()
        with open(path) as f:
            self.assertEqual(json.load(f)["felt_intensity"], 0.9)

    def test_projection_is_stable_and_bounded(self):
        a = QS._project([0.1, -0.2, 0.3] * 300)
        b = QS._project([0.1, -0.2, 0.3] * 300)
        self.assertEqual(a, b)
        self.assertTrue(all(0.0 <= x <= 1.0 for x in a))


if __name__ == "__main__": unittest.main(verbosity=2)
