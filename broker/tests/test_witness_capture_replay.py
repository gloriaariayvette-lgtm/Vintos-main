#!/usr/bin/env python3
"""Synthetic capture-to-census contract; no application, model or sender."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import witness_capture as C

spec = importlib.util.spec_from_file_location("capture_replay", ROOT / "experiments/judges-witness/replay.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def capture():
    c = C.Capture("fixture-turn", "fixture-chat", 100)
    c.observe({"status": "valid", "text": "Synthetic reply?", "observed_model": "fixture-model",
               "identity_evidence": "response_metadata"})
    c.select("Synthetic reply?")
    return c


def packet():
    p = capture().finalize("Synthetic final reply?", 110, "handed_to_framework")
    p.update(role="assistant", content=p["witness_final_text"], test_mode=False,
             generation_provenance={"turn_id": "fixture-turn", "output_provenance": "ordinary_generation",
                                    "may_witness": True})
    return p


class Tests(unittest.TestCase):
    def census(self, p, lineage=None):
        sources = [("capture", [p])]
        return R.census(sources, R.snapshot_nodes(sources, lineage or []), 1000)

    def test_packet_is_counted_without_inventing_delivery(self):
        p = packet(); before = copy.deepcopy(p)
        summary, rows = self.census(p)
        self.assertEqual(summary["source_rows"], {"capture": 1})
        self.assertEqual(summary["held"], {"unconfirmed_delivery": 1})
        self.assertEqual(rows, [])
        self.assertEqual(p, before)

    def test_confirmed_fixture_still_requires_context_ancestry(self):
        p = packet()
        p["witness_receipt"]["delivery"] = "delivered"  # synthetic attestation only
        summary, rows = self.census(p)
        self.assertEqual(summary["held"], {"unknown_lineage": 1})
        self.assertEqual(rows, [])

    def test_test_and_tactical_packets_stay_excluded(self):
        for key in ("test_mode", "tactical", "character_influenced"):
            p = packet(); p[key] = True
            self.assertEqual(self.census(p)[0]["held"], {"excluded_act": 1})

    def test_equal_nodes_can_repeat_but_conflicts_never_win(self):
        p = packet()
        sources = [("capture", [p, copy.deepcopy(p)])]
        nodes = R.snapshot_nodes(sources, [])
        self.assertEqual(set(nodes), {n["id"] for n in p["lineage"]} | {p["reply_node"]["id"]})
        self.assertEqual(nodes[p["reply_node"]["id"]]["kind"], "reply")
        self.assertFalse(nodes[p["reply_node"]["id"]]["complete"])
        bad = copy.deepcopy(p); bad["lineage"][0]["complete"] = True
        for packets in ([p, bad], [bad, p]):
            with self.assertRaises(ValueError): R.snapshot_nodes([("capture", packets)], [])
        with self.assertRaises(ValueError): R.snapshot_nodes([("capture", [p])], bad["lineage"])
        self.assertEqual(R.snapshot_nodes([("capture", [p])], p["lineage"]), nodes)
        with self.assertRaises(ValueError): R.snapshot_nodes([], p["lineage"] * 2)

    def test_bad_packet_shapes_are_refused(self):
        for change in ({"schema": "unsupported"}, {"lineage": {}}, {"reply_node": None},
                       {"reply_node": {"kind": "ordinary_source", "id": "fake"}}, {"turn_id": "different"}):
            p = dict(packet(), **change)
            with self.assertRaises(ValueError): R.snapshot_nodes([("capture", [p])], [])

    def test_private_sink_packet_replays_without_models_or_delivery_upgrade(self):
        with tempfile.TemporaryDirectory(prefix="witness-replay-") as td:
            root = Path(td).resolve()
            self.assertNotIn(".vintos", root.parts)
            env = dict(os.environ, SPARK_WORKSPACE=str(root), JUDGES_CAPTURE_SCRATCH=str(root),
                       PYTHONDONTWRITEBYTECODE="1")
            with patch.dict(os.environ, env):
                c = capture(); c._scratch_root = root
                C.finish_shadow(c, "Synthetic final reply?", 110,
                                packet()["generation_provenance"], test_mode=False)
            path = next(root.glob("capture-*.json"))
            before = path.read_bytes()
            bundle = {"input_kind": "synthetic", "sources": [{"kind": "capture", "rows": [json.loads(before)]}]}
            source = root / "bundle.json"; source.write_text(json.dumps(bundle))
            reports = []
            for name in ("first", "restart"):
                result = subprocess.run([sys.executable, str(R.__file__), "--scratch", str(root),
                    "--input", str(source), "--output", str(root / name), "--cutoff", "1970-01-01T00:16:40Z"],
                    env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = (root / name / "aggregate.json").read_text()
                self.assertNotIn("fixture-turn", report)
                self.assertNotIn("Synthetic final", report)
                reports.append(report)
            self.assertEqual(reports[0], reports[1])
            self.assertEqual(path.read_bytes(), before)
            report = json.loads(reports[0])
            self.assertEqual(report["input_kind"], "synthetic")
            self.assertEqual(report["census"]["held"], {"unconfirmed_delivery": 1})
            self.assertEqual(report["innovation"]["groups"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
