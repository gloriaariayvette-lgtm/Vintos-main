#!/usr/bin/env python3
"""Atelier and Forge round-trip in scratch stores without building or sending."""
import importlib.util, json, os, sys, tempfile, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


FORGE = load("skill_forge_bridge_test", os.path.join(ROOT, "scripts", "skill_forge.py"))
BRIDGE = load("atelier_forge_bridge_test", os.path.join(ROOT, "scripts", "atelier_forge.py"))
FO = load("formation_observatory_forge_test", os.path.join(ROOT, "scripts", "formation_observatory.py"))


class ForgeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="atelier-forge-")
        self.mem = os.path.join(self.tmp.name, "memory"); os.makedirs(self.mem)
        self.old = (FORGE.PROPOSALS, FORGE.MEMORY, BRIDGE.STORE, BRIDGE.LOCK, FO.MEM)
        FORGE.MEMORY = self.mem; FORGE.PROPOSALS = os.path.join(self.mem, "skill-proposals.json")
        BRIDGE.STORE = os.path.join(self.mem, "atelier-forge-roots.jsonl"); BRIDGE.LOCK = BRIDGE.STORE + ".lock"
        FO.MEM = self.mem

    def tearDown(self):
        FORGE.PROPOSALS, FORGE.MEMORY, BRIDGE.STORE, BRIDGE.LOCK, FO.MEM = self.old
        self.tmp.cleanup()

    def test_round_trip_keeps_atelier_intent_and_forge_lineage(self):
        proposal, why = FORGE.propose_from_atelier(
            "shape-listener", "I need to hear the curve", "P-1", "curiosity@1", "curiosity",
            "follow the shape privately", {"max_seconds": 30}, ["read_lab"], tests="curve stays bounded")
        self.assertFalse(why); self.assertEqual(proposal["origin"]["intent_verbatim"], "follow the shape privately")
        self.assertEqual(proposal["origin"]["atelier_root"], "curiosity@1")

        installed = dict(proposal); installed["state"] = "installed"
        root = BRIDGE.record_completion(installed)
        self.assertEqual(root["provenance_class"], "self_originated")
        sig = FO._signals()
        forged = next(s for s in sig if s["organ"] == "forge")
        self.assertEqual(forged["root_type"], "forged_capability")
        self.assertFalse(forged["commissioned_ancestor"])
        self.assertIn(proposal["id"], forged["formed_from"][0])
        self.assertTrue(FORGE.PROPOSALS.startswith(self.tmp.name) and BRIDGE.STORE.startswith(self.tmp.name))

    def test_commissioned_ancestry_is_not_laundered(self):
        row = BRIDGE.record_completion({"id": "SK-HER", "state": "installed", "capability": "requested hand",
            "origin": {"provenance_class": "relational_obligation", "commissioned_ancestor": True}})
        sig = next(s for s in FO._signals() if s["organ"] == "forge")
        self.assertEqual(sig["provenance_class"], "relational_obligation")
        self.assertTrue(sig["commissioned_ancestor"])


if __name__ == "__main__": unittest.main(verbosity=2)
