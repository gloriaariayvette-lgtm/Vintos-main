#!/usr/bin/env python3
"""Synthetic-only witness contracts. No sender, model or live store imported."""
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
import witness_receipts as W
import evidence_provenance as EP
SPEC = importlib.util.spec_from_file_location("judges_replay", ROOT / "experiments/judges-witness/replay.py")
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


def fixture(turn="fixture-turn", start=100, final=110):
    attempts = [{"attempt_id": "attempt-1", "outcome": "failed", "requested_model": "fixture-a"},
                {"attempt_id": "attempt-2", "outcome": "selected", "requested_model": "fixture-a",
                 "served_model": "fixture-b", "identity_evidence": "response_metadata"}]
    receipt = W.receipt(turn, "fixture-chat", start, final, "A synthetic reply?", "context-1",
                        attempts, "attempt-2", "delivered")
    row = {"role": "assistant", "content": "A synthetic reply?", "turn_id": turn,
           "surface": "fixture-chat", "generation_provenance": {
               "turn_id": turn, "output_provenance": "ordinary_generation", "may_witness": True},
           "witness_receipt": receipt}
    nodes = {"context-1": {"id": "context-1", "kind": "context", "at": 90,
                           "complete": True, "parents": []}}
    forecast = {"turn_id": turn, "surface": "fixture-chat", "mode": "on_message", "ts": start + 1,
                "arrived_at": start - 1, "self": {"emb": [1., 0.], "mode": "on_message",
                    "source": "fixture-self", "checkpoint_id": "fixture-checkpoint", "context_last_ts": 80}}
    embedding = {"turn_id": turn, "response_sha256": W.digest(row["content"]),
                 "encoder_id": "fixture-encoder", "emb": [0.8, 0.6]}
    checkpoints = {"fixture-checkpoint": {"encoder_id": "fixture-encoder", "trained_at": 50,
                                          "source": "fixture-self"}}
    return row, nodes, forecast, embedding, checkpoints


class WitnessTests(unittest.TestCase):
    def setUp(self):
        self.row, self.nodes, self.f, self.e, self.ck = fixture()

    def admit(self, row=None):
        return W.admission(row or self.row, self.nodes, 1000)

    def score(self, forecasts=None, rows=None, embeddings=None, checkpoints=None, minimum=20):
        return R.innovation(rows or [self.row], forecasts if forecasts is not None else [self.f],
                            embeddings if embeddings is not None else [self.e],
                            checkpoints if checkpoints is not None else self.ck, minimum)

    def test_clean_explicit_receipt(self):
        self.assertEqual(self.admit(), "eligible")
        attempts = self.row["witness_receipt"]["generation"]["attempts"]
        self.assertEqual(attempts[1]["served_model"], "fixture-b")
        self.assertEqual(attempts[0]["served_model"], None)

    def test_requested_is_not_actual(self):
        a = self.row["witness_receipt"]["generation"]["attempts"][1]
        a["identity_evidence"] = "unknown"
        self.assertEqual(self.admit(), "unknown_served_model")

    def test_provenance_fields_and_denial(self):
        p = self.row.pop("generation_provenance")
        self.row["provenance"] = p
        self.assertEqual(self.admit(), "eligible")
        self.row["generation_provenance"] = dict(p, may_witness=False)
        self.assertEqual(self.admit(), "ineligible_provenance")

    def test_legacy_stays_unknown_only_for_new_reader(self):
        del self.row["generation_provenance"]
        self.assertEqual(self.admit(), "unknown_provenance")
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(EP.output_can_witness(None))

    def test_normalize_preserves_allowlisted_receipt(self):
        p = dict(self.row["generation_provenance"], witness_receipt=self.row["witness_receipt"])
        p["witness_receipt"]["untrusted_payload"] = "synthetic discarded field"
        normalized = EP.normalize(p)
        self.assertEqual(normalized["witness_receipt"], W.normalize_receipt(p["witness_receipt"]))
        self.assertNotIn("untrusted_payload", normalized["witness_receipt"])

    def test_malformed_receipts_fail_closed(self):
        for value in (None, [], {}, {"schema": W.SCHEMA, "generation": []}):
            self.assertEqual(W.normalize_receipt(value)["status"], "unknown")
        self.row["witness_receipt"]["generation"]["attempts"] = [[]]
        self.assertEqual(self.admit(), "unknown_receipt")

    def test_final_response_and_delivery(self):
        self.row["content"] += " changed"
        self.assertEqual(self.admit(), "response_changed")
        self.row["content"] = "A synthetic reply?"
        self.row["witness_receipt"]["delivery"] = "unknown"
        self.assertEqual(self.admit(), "unconfirmed_delivery")

    def test_effect_through_value_map(self):
        self.nodes["context-1"]["parents"] = ["map"]
        self.nodes["map"] = {"id": "map", "kind": "value_map", "at": 70, "complete": True, "parents": ["effect"]}
        self.nodes["effect"] = {"id": "effect", "kind": "behaviour_receipt", "at": 60, "complete": True, "parents": []}
        self.assertEqual(self.admit(), "influenced_lineage")

    def test_unknown_lineage_never_clean(self):
        for mutation in ({"parents": ["missing"]}, {"parents": ["context-1"]},
                         {"complete": False}, {"at": 101}, {"kind": "unrecognized"}):
            self.nodes["context-1"] = dict(fixture()[1]["context-1"], **mutation)
            self.assertEqual(self.admit(), "unknown_lineage")

    def test_cutoff_and_naive_clock(self):
        self.assertEqual(W.admission(self.row, self.nodes, 110), "outside_cutoff")
        for v in (True, float("nan"), "2026-01-01T10:00:00"):
            with self.assertRaises(ValueError): W.instant(v)

    def test_census_duplicate_and_denial(self):
        sources = [("canonical", [self.row]), ("merged", [copy.deepcopy(self.row)])]
        summary, rows = R.census(sources, self.nodes, 1000)
        self.assertEqual(summary["eligible_replies"], 1)
        self.assertEqual(len(rows), 1)
        sources[1][1][0]["admitted"] = False
        summary, rows = R.census(sources, self.nodes, 1000)
        self.assertEqual(rows, [])
        self.assertEqual(summary["held"]["duplicate_held"], 1)

    def test_ledger_and_missing_sources(self):
        ledger = dict(self.row, vintos=self.row["content"])
        del ledger["role"]; del ledger["content"]
        self.assertEqual(R.census([("ledger", [ledger])], self.nodes, 1000)[0]["eligible_replies"], 1)
        self.assertEqual(R.census([], {}, 1000)[0]["eligible_replies"], 0)

    def test_forecast_matches_final_once(self):
        summary, rows = self.score(forecasts=[self.f, copy.deepcopy(self.f)])
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["error"], .2)
        self.assertIsNone(rows[0]["innovation_percentile"])
        self.assertEqual(summary["held"]["duplicate_forecasts"], 1)

    def test_forecast_identity_and_causality(self):
        for mutation in ({"ts": 110}, {"ts": 111}, {"mode": "ahead"},
                         {"surface": "other"}, {"turn_id": "other"}):
            self.assertEqual(self.score(forecasts=[dict(self.f, **mutation)])[1], [])
        self.f["self"]["context_last_ts"] = 100
        self.assertEqual(self.score()[1], [])

    def test_checkpoint_and_embedding_required(self):
        self.assertEqual(self.score(checkpoints={})[1], [])
        self.assertEqual(self.score(embeddings=[])[1], [])
        self.e["response_sha256"] = W.digest("different synthetic reply")
        self.assertEqual(self.score()[1], [])

    def test_forecast_source_matches_checkpoint(self):
        self.f["self"]["source"] = "different-forecast-source"
        self.assertEqual(self.score()[1], [])

    def test_vectors_reject_invalid(self):
        for a, b in (([], []), ([1], [1, 2]), ([0, 0], [1, 0]),
                     ([float("nan")], [1]), ([True], [1])):
            with self.assertRaises(ValueError): R.cosine_error(a, b)

    def test_percentile_uses_earlier_outcomes_only(self):
        r2, _, f2, e2, _ = fixture("fixture-2", 120, 130)
        r3, _, f3, e3, _ = fixture("fixture-3", 120, 130)
        _, rows = self.score(rows=[self.row, r2, r3], forecasts=[f3, f2, self.f],
                             embeddings=[self.e, e2, e3], minimum=1)
        self.assertEqual([r["prior_n"] for r in rows], [0, 1, 1])
        self.assertEqual(rows[1]["innovation_percentile"], 50)
        self.assertEqual(rows[2]["innovation_percentile"], 50)

    def test_scratch_rejects_live_parent_and_symlink(self):
        with tempfile.TemporaryDirectory(prefix="witness-test-") as td:
            root = Path(td).resolve()
            self.assertNotIn(".vintos", root.parts)
            live = root / ".vintos" / "workspace"
            live.mkdir(parents=True, mode=0o700)
            with patch.dict(os.environ, {"SPARK_WORKSPACE": str(live)}):
                with self.assertRaises(ValueError): R.scratch_root(live)
            with patch.dict(os.environ, {"SPARK_WORKSPACE": str(root)}):
                self.assertEqual(R.scratch_root(root), root)
                with self.assertRaises(ValueError): R.inside(root, root.parent)
                link = root / "alias"; link.symlink_to(root.parent)
                with self.assertRaises(ValueError): R.inside(root, link / "escape")

    def test_cli_scratch_only_and_repeatable(self):
        with tempfile.TemporaryDirectory(prefix="witness-test-") as td:
            root = Path(td).resolve()
            self.assertNotIn(".vintos", root.parts)
            bundle = {"input_kind": "synthetic", "sources": [{"kind": "canonical", "rows": [self.row]}],
                      "lineage": list(self.nodes.values()), "forecasts": [self.f],
                      "embeddings": [self.e], "checkpoints": self.ck}
            source = root / "fixture.json"; source.write_text(json.dumps(bundle))
            before = source.read_bytes()
            env = dict(os.environ, SPARK_WORKSPACE=str(root), PYTHONDONTWRITEBYTECODE="1")
            for name in ("first", "restart"):
                result = subprocess.run([sys.executable, str(R.__file__), "--scratch", str(root),
                    "--input", str(source), "--output", str(root / name), "--cutoff", "1970-01-01T00:16:40Z"],
                    env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(before, source.read_bytes())
            self.assertEqual((root / "first/aggregate.json").read_bytes(), (root / "restart/aggregate.json").read_bytes())
            self.assertEqual((root / "first/aggregate.json").stat().st_mode & 0o777, 0o600)

    def test_guard_denies_subprocess_rename_and_external_write(self):
        with tempfile.TemporaryDirectory(prefix="witness-test-") as td:
            root = Path(td).resolve()
            # Separate interpreter: audit hooks cannot be removed from this suite.
            code = '''import importlib.util, pathlib, sys
s=importlib.util.spec_from_file_location("replay",sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
root=pathlib.Path(sys.argv[2]); out=root/"output"; m.install_guard(root,out)
out.mkdir(mode=0o700)
for event,args in [("subprocess.Popen",("unused",[],None,None)),("socket.connect",(None,None)),("os.rename",(str(out/"a"),str(root/"b"),-1,-1)),("open",(str(root/"forbidden"),"w",0))]:
    try: sys.audit(event,*args)
    except PermissionError: pass
    else: raise AssertionError(event)
'''
            result = subprocess.run([sys.executable, "-c", code, str(R.__file__), str(root)],
                                    capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / "forbidden").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
