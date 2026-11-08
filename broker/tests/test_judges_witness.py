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
                           "complete": True, "parents": ["external-0"]},
             "external-0": W.source_node("external-0", "counterpart_verbatim", 0, "Synthetic input.")}
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

    def test_ledger_explicit_denial_survives_permissive_envelope(self):
        self.row["generated_output_witness_eligible"] = False
        self.assertEqual(self.admit(), "excluded_act")

    def test_existing_evidence_standing_is_a_floor(self):
        for extra in ({"derived_from": ["missing-parent"]},
                      {"derived_from": [{"provenance": {"may_witness": False,
                          "output_provenance": "stratagem_influenced"}}]},
                      {"evidence_standing": "HELD"}, {"evidence_standing": "ineligible"}):
            with self.subTest(extra=extra):
                self.assertEqual(self.admit(dict(self.row, **extra)), "ineligible_evidence_standing")

    def test_exclusion_flags_and_tactical_origins(self):
        for flag in ("dream_only", "imported", "transplanted", "timestamp_estimated", "forgotten", "deleted"):
            with self.subTest(flag=flag):
                self.assertEqual(self.admit(dict(self.row, **{flag: True})), "excluded_act")
        for key in ("source", "witness_origin_source"):
            with self.subTest(key=key):
                self.assertEqual(self.admit(dict(self.row, **{key: "ghost_branch"})), "tactical_source")

    def test_join_only_agreeing_envelope_ids(self):
        del self.row["turn_id"]
        summary, rows = R.census([("canonical", [self.row])], self.nodes, 1000)
        self.assertEqual(summary["envelope_id_joins"], 1)
        self.assertEqual(rows[0]["turn_id"], "fixture-turn")
        self.row["provenance"] = dict(self.row["generation_provenance"], turn_id="different")
        self.assertEqual(R.census([("canonical", [self.row])], self.nodes, 1000)[1], [])

    def test_exact_final_text_is_separate_from_device_marks(self):
        self.row["witness_final_text"] = self.row["content"]
        self.row["witness_final_sha256"] = W.digest(self.row["content"])
        self.row["content"] += " [synthetic device annotation]"
        self.assertEqual(self.admit(), "missing_final_response")
        self.row["source"] = "ledger"
        self.assertEqual(self.admit(), "eligible")
        self.assertEqual(len(self.score()[1]), 1)
        self.row["witness_final_sha256"] = W.digest("a different synthetic final")
        self.assertEqual(self.admit(), "missing_final_response")

    def test_exact_final_text_cannot_substitute_unrelated_store_text(self):
        self.row.update(source="ledger", witness_final_text="a different synthetic reply",
                        witness_final_sha256=W.digest("a different synthetic reply"))
        self.assertEqual(self.admit(), "missing_final_response")

    def test_duplicate_hold_retains_copy_reason(self):
        denied = dict(self.row, deleted=True)
        summary, _ = R.census([("canonical", [self.row, denied])], self.nodes, 1000)
        self.assertEqual(summary["duplicate_held_copy_reasons"], {"excluded_act": 1})

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

    def test_request_binding_survives_provenance_and_merge(self):
        import build_merged_chat as merge
        attempt = self.row["witness_receipt"]["generation"]["attempts"][-1]
        attempt.update(request_id="fixture-request", input_sha256=W.digest("synthetic handler request"))
        p = dict(self.row["generation_provenance"], witness_receipt=self.row["witness_receipt"])
        normalized = EP.normalize(p)
        row = dict(self.row, generation_provenance=normalized)
        projected = merge.entry(row, "assistant", row["content"], "2026-01-01T00:00:00Z", "canonical")
        for receipt in (projected["witness_receipt"], projected["generation_provenance"]["witness_receipt"]):
            selected = receipt["generation"]["attempts"][-1]
            self.assertEqual(selected["request_id"], "fixture-request")
            self.assertEqual(selected["input_sha256"], W.digest("synthetic handler request"))

    def test_missing_receipt_module_is_explicit_unknown(self):
        p = dict(self.row["generation_provenance"], witness_receipt=self.row["witness_receipt"])
        with patch.dict(sys.modules, {"witness_receipts": None}):
            normalized = EP.normalize(p)
        self.assertEqual(normalized["witness_receipt"]["status"], "unknown")
        self.assertTrue(normalized["may_witness"])

    def test_future_bundles_include_receipt_dependency(self):
        spec = importlib.util.spec_from_file_location("witness_bundle_test", ROOT / "experiments/persistence-sprint/bundle.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix="witness-bundle-") as td:
            scratch = Path(td).resolve()
            self.assertNotIn(".vintos", scratch.parts)
            module.package_code(scratch / "code", ROOT)
            self.assertTrue((scratch / "code/scripts/witness_receipts.py").is_file())
            code = '''import sys
sys.path.insert(0,sys.argv[1])
import evidence_view as ev
assert ev.eligibility({"provenance":{"may_witness":True,"output_provenance":"ordinary_generation","witness_receipt":{"schema":"behaviour-witness-v1","status":"unknown"}}}) == ev.ELIGIBLE
'''
            result = subprocess.run([sys.executable, "-I", "-c", code, str(scratch / "code/scripts")],
                                    capture_output=True, text=True,
                                    env=dict(os.environ, SPARK_WORKSPACE=str(scratch), PYTHONDONTWRITEBYTECODE="1"))
            self.assertEqual(result.returncode, 0, result.stderr)

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
        self.nodes["effect"] = {"id": "effect", "kind": "behaviour_receipt", "at": 60, "complete": True, "parents": ["external-0"]}
        self.assertEqual(self.admit(), "influenced_lineage")

    def test_parentless_generated_nodes_are_unknown(self):
        for kind in sorted(W.KINDS - {"ordinary_source"}):
            with self.subTest(kind=kind):
                nodes = copy.deepcopy(self.nodes)
                nodes["context-1"]["parents"] = ["empty"]
                nodes["empty"] = {"id": "empty", "kind": kind, "at": 80, "complete": True, "parents": []}
                self.assertEqual(W.lineage_status("context-1", nodes, 100), "unknown")
        self.nodes["context-1"]["parents"] = []
        self.assertEqual(self.admit(), "unknown_lineage")

    def test_external_sibling_cannot_launder_parentless_value_map(self):
        self.nodes["map"] = {"id": "map", "kind": "value_map", "at": 80, "complete": True, "parents": []}
        for parents in (["external-0", "map"], ["map", "external-0"]):
            self.nodes["context-1"]["parents"] = parents
            self.assertEqual(self.admit(), "unknown_lineage")
        self.nodes["map"]["parents"] = ["external-0"]
        self.assertEqual(self.admit(), "eligible")

    def test_external_source_requires_origin_and_exact_version(self):
        self.nodes["context-1"]["parents"] = ["external"]
        for origin in sorted(W.SOURCE_ORIGINS):
            self.nodes["external"] = W.source_node("external", origin, 80, "synthetic input")
            self.assertEqual(self.admit(), "eligible")
        clean = copy.deepcopy(self.nodes["external"])
        for field in ("origin", "source_sha256"):
            self.nodes["external"] = dict(clean)
            del self.nodes["external"][field]
            self.assertEqual(self.admit(), "unknown_lineage")
        for origin in ("reply", "value_map", "journal", "unknown", ""):
            self.nodes["external"] = dict(clean, origin=origin)
            self.assertEqual(self.admit(), "unknown_lineage")
            with self.assertRaises(ValueError): W.source_node("external", origin, 80, "synthetic input")
        self.nodes["external"] = dict(clean, source_sha256="bad")
        self.assertEqual(self.admit(), "unknown_lineage")
        self.nodes["external"] = dict(clean, parents=["missing-generated-parent"])
        self.assertEqual(self.admit(), "unknown_lineage")

    def test_unmarked_reply_cannot_become_an_external_leaf(self):
        self.nodes["context-1"]["parents"] = ["unmarked"]
        self.nodes["unmarked"] = {"id": "unmarked", "kind": "ordinary_source", "at": 80,
                                  "parents": [], "complete": True}
        self.assertEqual(self.admit(), "unknown_lineage")

    def test_unknown_lineage_never_clean(self):
        for mutation in ({"parents": ["missing"]}, {"parents": ["context-1"]},
                         {"complete": False}, {"at": 101}, {"kind": "unrecognized"}):
            self.nodes["context-1"] = dict(fixture()[1]["context-1"], **mutation)
            self.assertEqual(self.admit(), "unknown_lineage")

    def test_lineage_root_must_be_context(self):
        self.nodes["context-1"]["kind"] = "ordinary_source"
        self.assertEqual(self.admit(), "unknown_lineage")

    def test_reply_shaped_ordinary_leaf_is_unknown(self):
        self.nodes["context-1"]["parents"] = ["pretend-source"]
        for shape in ({"role": "assistant"}, {"turn_id": "prior-reply"}, {"reply_text": "synthetic"}):
            self.nodes["pretend-source"] = dict(W.source_node(
                "pretend-source", "counterpart_verbatim", 80, "synthetic input"), **shape)
            self.assertEqual(self.admit(), "unknown_lineage")

    def test_reply_node_propagates_direct_and_indirect_influence(self):
        self.nodes.update({
            "old-context": {"id": "old-context", "at": 60, "kind": "context", "parents": ["external-0"], "complete": True},
            "old-reply": {"id": "old-reply", "at": 70, "kind": "reply", "parents": ["old-context"],
                          "context_receipt_id": "old-context", "turn_id": "old-turn", "influence": "influenced", "complete": True}})
        self.nodes["context-1"]["parents"] = ["old-reply"]
        self.assertEqual(self.admit(), "influenced_lineage")
        self.nodes["old-reply"]["influence"] = "clean"
        self.nodes["old-reply"]["character_influenced"] = True
        self.assertEqual(self.admit(), "influenced_lineage")
        del self.nodes["old-reply"]["character_influenced"]
        self.nodes["old-context"]["parents"] = ["effect"]
        self.nodes["effect"] = {"id": "effect", "at": 50, "kind": "judge_effect", "parents": ["external-0"], "complete": True}
        self.assertEqual(self.admit(), "influenced_lineage")
        self.nodes["old-reply"]["kind"] = "ordinary_source"
        self.assertEqual(self.admit(), "unknown_lineage")

    def test_shared_ancestry_is_memoized_and_edge_clocks_checked(self):
        class Counted(dict):
            calls = 0
            def get(self, *args):
                self.calls += 1
                return super().get(*args)
        nodes = Counted()
        for i in range(60):
            key = str(i)
            nodes[key] = {"id": key, "at": i, "kind": "context", "complete": True,
                          "parents": [str(i - 1)] * 2 if i else []}
        nodes["0"] = W.source_node("0", "sensor_observation", 0, "Synthetic observation.")
        self.assertEqual(W.lineage_status("59", nodes, 100), "clean")
        self.assertLess(nodes.calls, 200)
        nodes["59"]["parents"] = ["58", "earlier-parent"]
        nodes["earlier-parent"] = {"id": "earlier-parent", "at": 10, "kind": "context", "complete": True, "parents": ["57"]}
        self.assertEqual(W.lineage_status("59", nodes, 100), "unknown")

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

    def test_arrival_precedes_generation_and_context_precedes_arrival(self):
        self.f["arrived_at"] = 101
        self.assertEqual(self.score()[1], [])
        self.f["arrived_at"] = 99
        self.f["self"]["context_last_ts"] = 99
        self.assertEqual(self.score()[1], [])
        self.f["self"]["context_last_ts"] = 98
        self.assertEqual(len(self.score()[1]), 1)

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
