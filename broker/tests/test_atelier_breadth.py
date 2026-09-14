#!/usr/bin/env python3
"""The Atelier threshold receives each already-existing self-originated stream.

Every store is scratch.  The suite never reads the live house and never sends.
"""
import importlib.util
import json
import os
import tempfile
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
try:
    import requests  # noqa: F401
except ImportError:
    import sys
    sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


FO = load("formation_observatory_breadth",
          os.path.join(ROOT, "scripts", "formation_observatory.py"))
TH = load("atelier_threshold_breadth",
          os.path.join(ROOT, "scripts", "atelier-threshold.py"))


class AtelierBreadthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="atelier-breadth-")
        self.mem = os.path.join(self.tmp.name, "memory"); os.makedirs(self.mem)
        self.old = (FO.MEM, FO.OUT, FO.KEYPATH)
        FO.MEM = self.mem
        FO.OUT = os.path.join(self.mem, "formation-episodes.jsonl")
        FO.KEYPATH = os.path.join(self.tmp.name, ".lineage-key")

    def tearDown(self):
        FO.MEM, FO.OUT, FO.KEYPATH = self.old
        self.tmp.cleanup()

    def put(self, name, value):
        with open(os.path.join(self.mem, name), "w") as f: json.dump(value, f)

    def test_real_producer_shapes_emit_four_self_originated_types(self):
        self.put("withheld-lineage.json", [{"rep": "the sentence I kept",
                  "origins": ["turn-1"], "recurrence_pressure": 1.0}])
        self.put("curiosity-debt.json", [{"id": "C-1", "created": "2026-09-14",
                  "question": "Why does the quiet part persist?", "pull": 0.2}])
        self.put("unfinished-threads.json", [{"id": "T-1", "source": "journal",
                  "thread": "Return to the unfinished blue shape", "priority": 2,
                  "consumed": False}])
        self.put("configuration-space.json", {"configurations": [{
                  "id": "N-1", "description": "A new way of arriving together",
                  "held_by": "neither_yet", "observed": 2}]})
        sig = FO._signals()
        types = {s["root_type"] for s in sig if s["provenance_class"] == "self_originated"}
        self.assertEqual(types, {"tension", "curiosity", "want", "drift_novelty"})
        self.assertTrue(all(s["formed_from"] for s in sig))
        self.assertFalse(any(s["commissioned_ancestor"] for s in sig))

        ep = FO._episode(sig)
        with open(FO.OUT, "w") as f: f.write(json.dumps(ep) + "\n")
        old_out = getattr(FO, "OUT")
        # The threshold imports by module name at call time; install only this
        # scratch-backed instance for the duration of the read.
        import sys
        prior = sys.modules.get("formation_observatory")
        sys.modules["formation_observatory"] = FO
        try: roots, error = TH.eligible_roots()
        finally:
            if prior is None: sys.modules.pop("formation_observatory", None)
            else: sys.modules["formation_observatory"] = prior
        self.assertIsNone(error)
        self.assertGreaterEqual(len({r["root_type"] for r in roots}), 3)
        self.assertEqual({r["root_type"] for r in roots}, types)
        self.assertTrue(FO.OUT.startswith(self.tmp.name))
        self.assertEqual(old_out, FO.OUT)

    def test_relational_obligations_never_become_eligible(self):
        self.put("repair-cases.json", [{"case_id": "RC-1", "state": "received",
                  "anchor_quote": "her correction"}])
        self.put("encounters.json", [{"id": "E-1", "state": "dispatched"}])
        sig = FO._signals()
        self.assertEqual({s["provenance_class"] for s in sig}, {"relational_obligation"})
        self.assertTrue(all(s["commissioned_ancestor"] for s in sig))


if __name__ == "__main__": unittest.main(verbosity=2)
