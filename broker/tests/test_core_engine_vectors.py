#!/usr/bin/env python3
"""RW-706bcf9c: core-engine publishes Core only when every vector is usable.

A missing, empty, non-numeric, boolean, non-finite or odd-length vector keeps
the previous core-vectors.json, on the store-lock route and on the direct-write
fallback alike. Valid output still publishes on both.
"""
import importlib.util
import json
import math
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "bin" / "core-engine.py"
spec = importlib.util.spec_from_file_location("core_engine_under_test", SOURCE)
CE = importlib.util.module_from_spec(spec); spec.loader.exec_module(CE)

PREVIOUS = {"generated": "2026-10-01T00:00:00", "source_events": 3, "clusters": 1,
            "core": [{"name": "kept", "vector": [0.6, 0.8, 0.0]}]}


def entry(name, vector, drop=False):
    e = {"name": name, "failure_pattern": "f", "almost_becoming": "a",
         "vector": vector, "confidence": 0.5, "violation_condition": "f",
         "polarity": "negative"}
    if drop: e.pop("vector")
    return e


class _Reply:
    def __init__(self, body): self._body = body
    def json(self): return self._body


class CoreEngineVectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (CE.MEMORY, CE.CORE_FILE, CE._sg_write, CE.embed,
                    CE.collect_friction_events, CE.generate_core_from_clusters)
        # Every path the module writes or reads goes to the throwaway directory.
        CE.MEMORY = self.tmp.name
        CE.CORE_FILE = os.path.join(self.tmp.name, "core-vectors.json")
        with open(CE.CORE_FILE, "w") as f: json.dump(PREVIOUS, f)
        # Nothing sends: the model calls go to a recorder, never the network.
        self.posts = []
        fake = types.ModuleType("requests")
        def post(url, **kw):
            self.posts.append(url)
            return _Reply({"choices": [{"message": {"content":
                "FAILURE: withdraws\nALMOST: stays\nNAME: staying_close"}}]})
        fake.post = post
        self.old_requests = sys.modules.get("requests")
        sys.modules["requests"] = fake
        self.sg_calls = []
        self.sg_result = True
        def sg(path, obj, who="organ"):
            self.sg_calls.append((path, obj))
            if self.sg_result:
                with open(path, "w") as f: json.dump(obj, f)
            return self.sg_result
        CE._sg_write = sg
        CE.embed = lambda text: {"a": [1.0, 0.0, 0.0], "b": [0.0, 1.0, 0.0]}.get(text, [0.0, 0.0, 1.0])
        CE.collect_friction_events = lambda: [
            {"text": "a", "resistance_score": 0.5, "source": "bis", "alternative": "", "polarity": "negative"},
            {"text": "b", "resistance_score": 0.4, "source": "bis", "alternative": "", "polarity": "negative"}]

    def tearDown(self):
        (CE.MEMORY, CE.CORE_FILE, CE._sg_write, CE.embed,
         CE.collect_friction_events, CE.generate_core_from_clusters) = self.old
        if self.old_requests is None: sys.modules.pop("requests", None)
        else: sys.modules["requests"] = self.old_requests
        self.tmp.cleanup()

    def assert_isolated(self):
        self.assertTrue(CE.CORE_FILE.startswith(self.tmp.name), "Core store must be throwaway")
        self.assertTrue(CE.MEMORY.startswith(self.tmp.name))
        self.assertEqual(sys.modules["requests"].post.__module__, __name__, "requests must be the stub")
        self.assertEqual(CE._sg_write.__module__, __name__, "_sg_write must be the stub")

    def read_core(self):
        with open(CE.CORE_FILE) as f: return json.load(f)

    def test_invalid_vectors_keep_previous_core_on_both_routes(self):
        bad = {
            "missing": entry("x", None, drop=True),
            "empty": entry("x", []),
            "not_a_list": entry("x", "0.1,0.2,0.3"),
            "nonnumeric": entry("x", [0.1, "0.2", 0.3]),
            "boolean": entry("x", [True, 0.0, 0.0]),
            "nan": entry("x", [0.1, math.nan, 0.3]),
            "inf": entry("x", [0.1, math.inf, 0.3]),
            "short": entry("x", [0.1, 0.2]),
        }
        for route in (True, False):
            for kind, bad_entry in bad.items():
                with self.subTest(route="store-lock" if route else "direct", kind=kind):
                    self.sg_result = route
                    self.sg_calls.clear()
                    # mixed: a good entry beside the bad one still refuses the whole Core
                    CE.generate_core_from_clusters = lambda c, top_n=5, b=bad_entry: [entry("good", [0.0, 1.0, 0.0]), b]
                    CE.bootstrap()
                    self.assert_isolated()
                    self.assertEqual(self.sg_calls, [], "rejected Core must not reach _sg_write")
                    self.assertEqual(self.read_core(), PREVIOUS, "previous Core must survive")

    def test_no_entries_keeps_previous_core(self):
        CE.generate_core_from_clusters = lambda c, top_n=5: []
        CE.bootstrap()
        self.assertEqual(self.sg_calls, [])
        self.assertEqual(self.read_core(), PREVIOUS)

    def test_valid_output_publishes_through_store_lock(self):
        CE.bootstrap()   # the real clustering and generation, with stubbed model calls
        self.assert_isolated()
        self.assertEqual(len(self.sg_calls), 1)
        core = self.read_core()["core"]
        self.assertEqual(len(core), 2)
        for e in core:
            self.assertEqual(len(e["vector"]), 3)
            self.assertTrue(all(math.isfinite(x) for x in e["vector"]))
        self.assertTrue(self.posts and all(u.startswith(CE.LM_URL) for u in self.posts))

    def test_valid_output_publishes_through_direct_write_fallback(self):
        self.sg_result = False   # store lock unavailable
        CE.bootstrap()
        self.assert_isolated()
        self.assertEqual(len(self.sg_calls), 1)
        core = self.read_core()["core"]
        self.assertEqual(len(core), 2)
        self.assertNotEqual(self.read_core(), PREVIOUS)


if __name__ == "__main__":
    unittest.main()
