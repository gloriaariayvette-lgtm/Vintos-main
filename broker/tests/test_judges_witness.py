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

    def test_percentile_cannot_use_outcome_after_forecast_but_before_own_final(self):
        other,_,f2,e2,_=fixture('slow-target',105,200)
        _,rows=self.score(rows=[self.row,other],forecasts=[self.f,f2],embeddings=[self.e,e2],minimum=1)
        self.assertEqual([r['prior_n'] for r in rows],[0,0])
        self.assertIsNone(rows[1]['innovation_percentile'])

    def test_percentile_equal_outcome_forecast_clock_is_unknown(self):
        other,_,f2,e2,_=fixture('equal-target',109,200)
        self.assertEqual(f2['ts'],self.row['witness_receipt']['finalized_at'])
        _,rows=self.score(rows=[self.row,other],forecasts=[self.f,f2],embeddings=[self.e,e2],minimum=1)
        self.assertEqual(rows[1]['prior_n'],0)

    def test_equal_error_forecasts_are_not_identical_forecasts(self):
        self.e['emb']=[1.,0.]
        a=copy.deepcopy(self.f);a['self']['emb']=[.6,.8]
        b=copy.deepcopy(self.f);b['self']['emb']=[.6,-.8]
        report,rows=self.score(forecasts=[a,b])
        self.assertEqual(rows,[])
        self.assertEqual(report['held']['conflicting_forecast'],1)

    def test_equivalent_control_scores_cannot_hide_attestation_conflict(self):
        data=self.controls_fixture();a=data[1][0];b=copy.deepcopy(a)
        # A distinct producer attestation is not an identical duplicate merely
        # because its derived error and control summary happen to be equal.
        b['self']['context']['producer_receipt_id']='different-attestation'
        report,rows=self.control_score((data[0],[a,b],data[2],data[3]))
        self.assertEqual(rows,[])
        self.assertEqual(report['held']['conflicting_forecast'],1)

    def test_innovation_reference_separates_target_generator_and_revision(self):
        rows=[];forecasts=[];embeddings=[]
        for i in range(3):
            r,_,f,e,_=fixture('generator-'+str(i),100+i*30,110+i*30)
            if i==1:r['witness_receipt']['generation']['attempts'][1]['served_model']='other-generator'
            if i==2:r['witness_receipt']['generation']['attempts'][1]['served_revision']='other-revision'
            rows.append(r);forecasts.append(f);embeddings.append(e)
        report,details=self.score(rows=rows,forecasts=forecasts,embeddings=embeddings,minimum=1)
        self.assertEqual(len(report['groups']),3)
        self.assertEqual([r['prior_n'] for r in details],[0,0,0])

    def controls_fixture(self):
        first, _, _, e1, _ = fixture("earlier-1", 100, 110)
        second, _, _, e2, _ = fixture("earlier-2", 120, 130)
        target, _, forecast, e3, ck = fixture("target", 300, 310)
        e1["emb"], e2["emb"], e3["emb"] = [1., 0.], [0., 1.], [1., 0.]
        forecast["self"]["context_last_ts"] = 200
        forecast["self"]["context"] = {
            "schema": "forecast-reply-context-v1", "complete": True,
            "scope": "forecast_context_assistant_replies", "as_of": 200,
            "evaluation_block": "synthetic-block-a", "reply_refs": [
                {"turn_id": r["turn_id"], "response_sha256": W.digest(r["content"])} for r in (first, second)]}
        return [first, second, target], [forecast], [e1, e2, e3], ck

    def control_score(self, data):
        return R.innovation(*data)

    def test_paired_controls_use_exact_forecast_context(self):
        report, rows = self.control_score(self.controls_fixture())
        self.assertEqual(len(rows), 1)
        controls = rows[0]["controls"]
        self.assertEqual(controls["context_n"], 2)
        self.assertEqual(controls["last_reply_error"], 1.)
        self.assertAlmostEqual(controls["recent_mean_error"], 1 - 2 ** -.5)
        self.assertEqual(controls["last_reply_improvement"], 1.)
        self.assertEqual(report["baselines"]["paired_groups"][0]["n"], 1)
        self.assertEqual(report["baselines"]["unavailable"], {})

    def test_missing_context_does_not_invent_baselines_or_drop_head(self):
        report, rows = self.score()
        self.assertEqual(len(rows), 1)
        self.assertEqual(report["baselines"]["paired_groups"], [])
        self.assertEqual(report["baselines"]["unavailable"], {"missing_context_receipt": 1})

    def test_controls_require_complete_causal_bound_context(self):
        for mutation, reason in (({"complete": False}, "incomplete_context_receipt"),
                                 ({"as_of": 299}, "noncausal_context_receipt"),
                                 ({"evaluation_block": ""}, "missing_evaluation_block"),
                                 ({"scope": "all_history"}, "wrong_context_scope"),
                                 ({"reply_refs": []}, "missing_or_oversized_context")):
            data = self.controls_fixture()
            data[1][0]["self"]["context"].update(mutation)
            report, rows = self.control_score(data)
            self.assertEqual(len(rows), 1)
            self.assertEqual(report["baselines"]["unavailable"], {reason: 1})

    def test_controls_reject_target_duplicate_tied_and_reversed_context(self):
        for kind in ("target", "duplicate", "tie", "reversed", "future"):
            data = self.controls_fixture(); context = data[1][0]["self"]["context"]
            if kind == "target": context["reply_refs"][0]["turn_id"] = "target"
            if kind == "duplicate": context["reply_refs"][1] = copy.deepcopy(context["reply_refs"][0])
            if kind == "tie": data[0][1]["witness_receipt"]["finalized_at"] = 110
            if kind == "reversed": context["reply_refs"].reverse()
            if kind == "future": data[0][1]["witness_receipt"]["finalized_at"] = 300
            report, rows = self.control_score(data)
            self.assertEqual(rows[0]["controls"]["status"], "unavailable", kind)
            self.assertEqual(report["baselines"]["paired_groups"], [])

    def test_control_versions_encoder_surface_and_conflicts_are_checked(self):
        for kind in ("hash", "encoder", "surface", "conflict", "missing", "not_admitted"):
            data = self.controls_fixture()
            if kind == "hash": data[1][0]["self"]["context"]["reply_refs"][0]["response_sha256"] = W.digest("other")
            if kind == "encoder": data[2][0]["encoder_id"] = "different"
            if kind == "surface": data[0][0]["witness_receipt"]["surface"] = "other"
            if kind == "conflict": data[2].append(dict(data[2][0], emb=[0., 1.]))
            if kind == "missing": data[2].pop(0)
            if kind == "not_admitted": data[0].pop(0)
            _, rows = self.control_score(data)
            self.assertEqual(rows[0]["controls"]["status"], "unavailable", kind)

    def test_controls_do_not_use_uncited_more_recent_reply(self):
        data = self.controls_fixture()
        extra, _, _, emb, _ = fixture("uncited", 150, 160)
        emb["emb"] = [1., 0.]
        data[0].append(extra); data[2].append(emb)
        _, rows = self.control_score(data)
        self.assertEqual(rows[0]["controls"]["last_reply_error"], 1.)

    def test_recent_mean_normalizes_inputs_and_refuses_zero_mean(self):
        data = self.controls_fixture(); data[2][0]["emb"] = [100., 0.]
        _, rows = self.control_score(data)
        self.assertAlmostEqual(rows[0]["controls"]["recent_mean_error"], 1 - 2 ** -.5)
        data[2][1]["emb"] = [-1., 0.]
        _, rows = self.control_score(data)
        self.assertEqual(rows[0]["controls"]["status"], "unavailable")

    def test_paired_coverage_and_evaluation_blocks_are_not_pooled(self):
        data = self.controls_fixture()
        second, _, forecast, emb, _ = fixture("target-b", 400, 410)
        forecast["self"]["context_last_ts"] = 200
        forecast["self"]["context"] = copy.deepcopy(data[1][0]["self"]["context"])
        forecast["self"]["context"]["evaluation_block"] = "synthetic-block-b"
        third, _, f3, e3, _ = fixture("target-c", 500, 510)  # no context receipt
        data[0].extend([second, third]); data[1].extend([forecast, f3]); data[2].extend([emb, e3])
        report, rows = self.control_score(data)
        self.assertEqual(report["groups"][0]["n"], 3)
        self.assertEqual([g["n"] for g in report["baselines"]["paired_groups"]], [1, 1])
        self.assertEqual(report["baselines"]["unavailable"], {"missing_context_receipt": 1})

    def behaviour(self, rows=None, start=100, cutoff=200, surfaces=None):
        return R.behaviour_receipt(rows if rows is not None else [self.row], start, cutoff,
                                   surfaces if surfaces is not None else ['fixture-chat'])

    def test_behaviour_positive_control_and_private_manifest(self):
        report, private = self.behaviour()
        self.assertEqual(report['status'],'descriptive')
        self.assertEqual(report['groups'],[dict(group=1,n=1,mean_words=3,median_words=3,question_mark_fraction=1)])
        member=private['groups'][0]['members'][0]
        self.assertEqual(member['turn_id'],self.row['turn_id'])
        self.assertEqual(member['response_sha256'],W.digest(self.row['content']))
        self.assertEqual(member['context_receipt_id'],'context-1')
        for forbidden in ('fixture-turn','fixture-chat','fixture-b','context-1',self.row['content']):
            self.assertNotIn(forbidden,json.dumps(report))
        self.assertNotIn(self.row['content'],json.dumps(private))
        self.assertIn('completeness',report['coverage'])

    def test_behaviour_cross_midnight_window_is_inclusive_exclusive(self):
        start=W.instant('2026-11-08T00:00:00-06:00');end=W.instant('2026-11-09T00:00:00-06:00')
        rows=[fixture('boundary-'+str(i),at-1,at)[0] for i,at in enumerate((start-1,start,end-1,end))]
        report,private=self.behaviour(rows,start,end)
        self.assertEqual(report['eligible_observations'],2)
        self.assertEqual(report['not_in_summary'],{'outside_window':2})
        self.assertEqual([m['turn_id'] for m in private['groups'][0]['members']],['boundary-1','boundary-2'])
        with self.assertRaises(ValueError):self.behaviour(start=end,cutoff=start)
        with self.assertRaises(ValueError):self.behaviour(start='2026-11-08T00:00:00')

    def test_behaviour_does_not_pool_surfaces_models_or_revisions(self):
        rows=[fixture('group-'+str(i))[0] for i in range(4)]
        rows[1]['witness_receipt']['surface']='fixture-other'
        rows[2]['witness_receipt']['generation']['attempts'][1]['served_model']='fixture-other-model'
        rows[3]['witness_receipt']['generation']['attempts'][1]['served_revision']='fixture-revision'
        report,private=self.behaviour(rows,surfaces=['fixture-chat','fixture-other'])
        self.assertEqual([g['n'] for g in report['groups']],[1,1,1,1])
        self.assertEqual(len(private['groups']),4)
        report,_=self.behaviour(rows)
        self.assertEqual(report['eligible_observations'],3)
        self.assertEqual(report['not_in_summary'],{'outside_surface_scope':1})
        with self.assertRaises(ValueError):self.behaviour(surfaces=[])

    def test_behaviour_empty_window_is_unknown_not_zero_traits(self):
        report,private=self.behaviour([])
        self.assertEqual(report['status'],'no_eligible_observations')
        self.assertEqual(report['groups'],[])
        self.assertEqual(private['groups'],[])
        self.assertNotIn('mean_words',report)
        self.assertNotIn('question_mark_fraction',report)

    def test_behaviour_rebuild_order_and_source_removal(self):
        second=fixture('second',120,130)[0]
        first=self.behaviour([self.row,second])
        self.assertEqual(first,self.behaviour([second,self.row]))
        self.assertNotEqual(first[1]['receipt_id'],self.behaviour([self.row])[1]['receipt_id'])
        self.assertNotEqual(first[1]['receipt_id'],self.behaviour([self.row,second],start=99)[1]['receipt_id'])
        census,admitted=R.census([('canonical',[self.row]),('merged',[self.row])],self.nodes,1000)
        self.assertEqual(self.behaviour(admitted)[0]['eligible_observations'],1)
        _,empty=R.census([],self.nodes,1000)
        self.assertEqual(self.behaviour(empty)[0]['status'],'no_eligible_observations')

    def test_behaviour_refuses_double_count_bad_content_and_unknown_generator(self):
        with self.assertRaises(ValueError):self.behaviour([self.row,self.row])
        wrong=copy.deepcopy(self.row);wrong['content']='Different synthetic text'
        with self.assertRaises(ValueError):self.behaviour([wrong])
        wrong=copy.deepcopy(self.row)
        wrong['witness_receipt']['generation']['attempts'][1]['identity_evidence']='unknown'
        with self.assertRaises(ValueError):self.behaviour([wrong])
        wrong=copy.deepcopy(self.row);wrong['turn_id']='wrong-turn'
        with self.assertRaises(ValueError):self.behaviour([wrong])

    def test_behaviour_requested_identity_cannot_change_group(self):
        first=self.behaviour()[0]
        self.row['witness_receipt']['generation']['attempts'][1]['requested_model']='other-requested'
        self.assertEqual(first,self.behaviour()[0])

    def test_behaviour_influenced_descendants_do_not_enter_summary(self):
        self.nodes['effect']=dict(id='effect',kind='behaviour_receipt',at=50,complete=True,parents=['external-0'])
        self.nodes['context-1']['parents'].append('effect')
        report,admitted=R.census([('canonical',[self.row])],self.nodes,1000)
        self.assertEqual(report['eligible_replies'],0)
        self.assertEqual(self.behaviour(admitted)[0]['eligible_observations'],0)

    def reaction_events(self, text='haha'):
        before=dict(schema='witness-feedback-v1',event_id='fixture-before',kind='assistant_reply',
                    stream_id='fixture-stream',position=1,sequence_complete=True,at=110,
                    turn_id=self.row['turn_id'],surface='fixture-chat',content_sha256=W.digest(self.row['content']))
        after=dict(schema='witness-feedback-v1',event_id='fixture-reaction',kind='counterpart_message',
                   origin='authenticated_owner_message',witnessed=True,stream_id='fixture-stream',position=2,
                   sequence_complete=True,previous_event_id=before['event_id'],at=120,surface='fixture-chat',
                   text=text,content_sha256=W.digest(text))
        return [before,after]

    def feedback(self, events=None, rows=None, cutoff=1000):
        return R.feedback_receipts(rows if rows is not None else [self.row],
                                   events if events is not None else self.reaction_events(),cutoff)

    def test_feedback_haha_positive_exact_target_and_private_output(self):
        report,private=self.feedback()
        self.assertEqual(report['positive_targets'],1)
        self.assertEqual(private[0]['target_turn_id'],self.row['turn_id'])
        self.assertEqual(private[0]['label'],'positive')
        self.assertEqual(report['observation_reasons'],{'literal_haha_marker':1})
        for value in ('fixture-reaction','fixture-turn','fixture-stream',self.row['content']):
            self.assertNotIn(value,json.dumps(report))
        self.assertNotIn('"text"',json.dumps(private))

    def test_feedback_ha_absence_and_lower_signals_are_unknown(self):
        for text in ('ha','No laugh marker.','lol','😂','a hahalike word'):
            report,private=self.feedback(self.reaction_events(text))
            self.assertEqual(report['positive_targets'],0,text)
            self.assertEqual(private[0]['label'],'unknown')
        report,private=self.feedback([])
        self.assertEqual(private,[]);self.assertEqual(report['targets_without_positive_evidence'],1)
        for text in ('HAHA!','hahaha','hahah'):
            self.assertEqual(self.feedback(self.reaction_events(text))[0]['positive_targets'],1)

    def test_feedback_cannot_skip_intervening_ineligible_reply(self):
        events=self.reaction_events()
        intervening=dict(events[0],event_id='fixture-intervening',turn_id='not-admitted',position=2,at=115)
        events[1].update(position=3,previous_event_id='fixture-intervening')
        report,private=self.feedback(events+[intervening])
        self.assertEqual(private,[]);self.assertEqual(report['held'],{'target_not_eligible':1})
        events[1]['previous_event_id']='fixture-before'
        self.assertEqual(self.feedback(events+[intervening])[1],[])

    def test_feedback_requires_attested_adjacent_positions(self):
        for change in ({'position':4},{'position':True},{'sequence_complete':False},
                       {'previous_event_id':'wrong'},{'stream_id':'different'}, {'position':0}):
            events=self.reaction_events();events[1].update(change)
            self.assertEqual(self.feedback(events)[1],[],change)
        events=self.reaction_events();events[0]['sequence_complete']=False
        self.assertEqual(self.feedback(events)[1],[])

    def test_feedback_identity_version_surface_and_time_are_checked(self):
        for index,change in ((1,{'origin':'inferred'}),(1,{'content_sha256':W.digest('changed')}),
                (0,{'content_sha256':W.digest('wrong')}),(0,{'at':109}),(1,{'at':110}),
                (1,{'at':1000}),(1,{'surface':'other'}),(0,{'surface':'other'}),
                (1,{'at':'2026-11-08T12:00:00'}),(1,{'witnessed':False}),(1,{'deleted':True})):
            events=self.reaction_events();events[index].update(change)
            self.assertEqual(self.feedback(events)[1],[],change)

    def test_feedback_duplicates_and_conflicts_never_select_favourable_copy(self):
        events=self.reaction_events()
        self.assertEqual(self.feedback(events+copy.deepcopy(events))[0]['observations'],1)
        self.assertEqual(self.feedback(events)[0],self.feedback(list(reversed(events)))[0])
        changed=dict(events[1],text='ha',content_sha256=W.digest('ha'))
        self.assertEqual(self.feedback(events+[changed])[1],[])
        collision=dict(events[0],event_id='position-collision')
        self.assertEqual(self.feedback(events+[collision])[1],[])
        conflict=dict(events[0],turn_id='other')
        self.assertEqual(self.feedback(events+[conflict])[1],[])

    def practice_rating(self, stars=4):
        row=copy.deepcopy(self.row);row['witness_receipt']['surface']='humor_practice';row['surface']='humor_practice'
        event=dict(schema='witness-feedback-v1',event_id='fixture-rating',kind='practice_rating',
                   origin='authenticated_owner_rating',witnessed=True,at=130,stars=stars,
                   target_turn_id=row['turn_id'],target_sha256=W.digest(row['content']),surface='humor_practice')
        return row,event

    def test_feedback_practice_ratings_only_high_scores_are_positive(self):
        for stars in range(1,6):
            row,event=self.practice_rating(stars)
            report,private=self.feedback([event],[row])
            self.assertEqual(private[0]['stars'],stars)
            self.assertEqual(private[0]['label'],'positive' if stars>=4 else 'unknown')
            self.assertEqual(report['positive_targets'],int(stars>=4))
        for bad in (True,4.0,'5',0,6,None):
            row,event=self.practice_rating(bad)
            self.assertEqual(self.feedback([event],[row])[1],[])

    def test_feedback_practice_cannot_join_text_prefix_or_unknown_origin(self):
        for change in ({'target_turn_id':'missing'},{'target_sha256':W.digest('prefix')},
                       {'origin':'old-inferred-rating'},{'surface':'chat'}):
            row,event=self.practice_rating();event.update(change)
            self.assertEqual(self.feedback([event],[row])[1],[],change)
        row,event=self.practice_rating();row['witness_receipt']['surface']='chat'
        self.assertEqual(self.feedback([event],[row])[1],[])

    def test_feedback_repeated_ratings_are_not_multiple_positive_targets(self):
        row,event=self.practice_rating(5);later=dict(event,event_id='fixture-later-rating',at=140,stars=2)
        report,private=self.feedback([event,later],[row])
        self.assertEqual(report['observations'],2);self.assertEqual(report['positive_targets'],1)
        self.assertEqual([r['label'] for r in private],['positive','unknown'])
        self.assertEqual(self.feedback([event,later],[])[0]['positive_targets'],0)

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
                      "embeddings": [self.e], "checkpoints": self.ck, "feedback_events":self.reaction_events()}
            source = root / "fixture.json"; source.write_text(json.dumps(bundle))
            before = source.read_bytes()
            env = dict(os.environ, SPARK_WORKSPACE=str(root), PYTHONDONTWRITEBYTECODE="1")
            for name in ("first", "restart"):
                result = subprocess.run([sys.executable, str(R.__file__), "--scratch", str(root),
                    "--input", str(source), "--output", str(root / name), "--cutoff", "1970-01-01T00:16:40Z",
                    "--behaviour-start", "1970-01-01T00:01:40Z", "--behaviour-surface", "fixture-chat"],
                    env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(before, source.read_bytes())
            self.assertEqual((root / "first/aggregate.json").read_bytes(), (root / "restart/aggregate.json").read_bytes())
            self.assertEqual((root / "first/aggregate.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / "first/private-behaviour.json").read_bytes(), (root / "restart/private-behaviour.json").read_bytes())
            self.assertEqual((root / "first/private-behaviour.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / "first/private-feedback.json").read_bytes(), (root / "restart/private-feedback.json").read_bytes())
            self.assertEqual((root / "first/private-feedback.json").stat().st_mode & 0o777, 0o600)

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
