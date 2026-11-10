#!/usr/bin/env python3
"""Synthetic capture tests. Pure modules and an extracted router function only."""
import ast
import asyncio
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bin")]
import gen_result as G
from witness_capture import Capture, prepare_shadow
from witness_receipts import digest, lineage_status, normalize_receipt


def result(text="synthetic raw reply", actual="observed-fixture"):
    r = G.from_openai({"model": actual, "choices": [{"message": {"content": text},
                         "finish_reason": "stop"}]}, "fixture")
    r.update(observed_model=actual, identity_evidence="response_metadata" if actual else "unknown")
    return r


class Tests(unittest.TestCase):
    def test_monotonic_lifecycle_retains_raw_backstep_without_witness_promotion(self):
        c=Capture('synthetic-clock','avatar',100,monotonic=iter([10.,11.,12.,13.,14.]).__next__)
        inv=prepare_shadow(c,'synthetic',[],{},False,lambda:101)[0]
        inv.observe(result('synthetic raw'));c.select('synthetic raw',request=inv)
        c.before_final_guard('synthetic final',98)
        packet=c.finalize('synthetic final',99)
        clock=packet['capture_clock']
        self.assertEqual([x['wall_at'] for x in clock['samples']],[101,101,98,99])
        self.assertEqual([x['elapsed_seconds'] for x in clock['samples']],[1,2,3,4])
        self.assertEqual(clock['wall_order'],'unknown')
        self.assertEqual(packet['witness_receipt']['finalized_at'],99)
        self.assertEqual(normalize_receipt(packet['witness_receipt'])['status'],'unknown')
        self.assertEqual(packet['observed_attempts'][0]['served_model'],'observed-fixture')
        self.assertFalse(packet['reply_node']['complete'])
        self.assertEqual(packet['reply_node']['at'],99)

    def test_monotonic_finalization_cannot_hide_internal_backstep_when_final_recovers(self):
        c=Capture('synthetic-clock','avatar',100,monotonic=iter([10.,11.,12.,13.]).__next__)
        inv=c.request('synthetic',[],{},False,101);inv.observe(result('synthetic raw'))
        c.select('synthetic raw',request=inv);c.before_final_guard('synthetic final',98)
        packet=c.finalize('synthetic final',110)
        self.assertEqual(packet['capture_clock']['wall_order'],'unknown')
        self.assertEqual(packet['witness_receipt']['status'],'unknown')

    def test_monotonic_lifecycle_bad_clock_and_reselection_still_refuse(self):
        c=Capture('synthetic-clock','avatar',100,monotonic=iter([10.,11.,10.9]).__next__)
        c.before_final_guard('synthetic',101)
        with self.assertRaises(ValueError):c.finalize('synthetic',99)
        with self.assertRaises(ValueError):c.select('synthetic')
        for bad in (float('nan'),float('inf'),True,-1):
            with self.assertRaises(ValueError):Capture('synthetic','avatar',100,monotonic=lambda:bad)

    def test_monotonic_normal_wall_keeps_recorded_identity_and_unknown_delivery(self):
        c=Capture('synthetic-clock','avatar',100,monotonic=iter([10.,11.,12.]).__next__)
        inv=c.request('synthetic',[],{},False,101);inv.observe(result('synthetic raw'))
        c.select('synthetic raw',request=inv);packet=c.finalize('synthetic raw',102)
        self.assertEqual(packet['witness_receipt']['status'],'recorded')
        self.assertEqual(packet['witness_receipt']['delivery'],'unknown')
        self.assertEqual(packet['capture_clock']['wall_order'],'observed')

    def test_finalization_boundaries_bind_selected_output_to_exact_return(self):
        c = Capture("turn-1", "fixture-chat", 100)
        invocation = c.request("system", [], {}, False, 101)
        invocation.observe(result("synthetic raw"))
        c.select("synthetic raw", request=invocation)
        c.before_final_guard("synthetic edited", 105)
        p = c.finalize("synthetic guarded", 110)
        nodes = {n["id"]: n for n in p["lineage"]}
        before, final = [nodes[k] for k in p["finalization"]["boundary_ids"]]
        self.assertEqual(before["before_sha256"], digest("synthetic raw"))
        self.assertEqual(before["response_sha256"], final["before_sha256"])
        self.assertEqual(final["response_sha256"], digest("synthetic guarded"))
        self.assertEqual(p["reply_node"]["response_sha256"], digest("synthetic guarded"))
        self.assertEqual(final["parents"], [before["id"]])
        self.assertIn(final["id"], p["reply_node"]["parents"])
        self.assertTrue(before["changed"] and final["changed"])
        self.assertFalse(before["complete"] or final["complete"])
        self.assertNotIn("synthetic edited", str(p))
        self.assertEqual(lineage_status(c.context_id, nodes, 110), "unknown")

    def test_finalization_without_selection_or_boundary_does_not_invent_editor(self):
        c = Capture("turn-1", "fixture-chat", 100)
        p = c.finalize("synthetic final", 110)
        nodes = {n["id"]: n for n in p["lineage"]}
        node = nodes[p["finalization"]["boundary_ids"][0]]
        self.assertIsNone(node["changed"])
        self.assertIsNone(node["before_sha256"])
        self.assertEqual(node["parents"], [])
        self.assertEqual(node["origin"], "unknown")
        self.assertEqual(lineage_status(c.context_id, nodes, 110), "unknown")

    def test_finalization_boundaries_reject_reordering_and_reselection(self):
        c = Capture("turn-1", "fixture-chat", 100)
        c.before_final_guard("same", 105)
        with self.assertRaises(ValueError): c.before_final_guard("again", 106)
        with self.assertRaises(ValueError): c.select("same")
        with self.assertRaises(ValueError): c.request("late", [], {}, False, 106)
        with self.assertRaises(ValueError): c.observe(result("late"))
        with self.assertRaises(ValueError): c.finalize("same", 104)
        p = c.finalize("same", 110)
        final = next(n for n in p["lineage"] if n.get("boundary") == "handler_return")
        self.assertFalse(final["changed"])
        with self.assertRaises(ValueError): c.before_final_guard("late", 111)

    def test_explicit_original_binds_only_its_exact_fragment_and_input_version(self):
        c = Capture("turn-1", "fixture-chat", 100)
        message = {"role": "user", "content": "Synthetic framing: αβ. Synthetic tail."}
        self.assertTrue(c.bind_counterpart_input("αβ", message, 0))
        c.request("system", [message], {}, False, 101)
        p = c.finalize("final", 110)
        source = next(n for n in p["lineage"] if n.get("kind") == "ordinary_source")
        self.assertEqual(source["source_sha256"], digest("αβ"))
        self.assertEqual(source["origin"], "counterpart_verbatim")
        node = next(n for n in p["lineage"] if n.get("slot") == 1)
        self.assertEqual(node["parents"], [source["id"]])
        span = node["source_bindings"][0]["span"]
        self.assertEqual(message["content"][span["start"]:span["end"]], "αβ")
        self.assertEqual(span["unit"], "unicode_codepoints")
        self.assertEqual(node["origin"], "unknown")
        self.assertFalse(node["complete"])
        self.assertNotIn("αβ", str(p))
        self.assertNotIn(message["content"], str(p))

    def test_absent_empty_ambiguous_or_unlocated_original_never_becomes_external(self):
        for original, message in ((None, {"role": "user", "content": "unmarked text"}),
                ("", {"role": "user", "content": "event text"}),
                (" ", {"role": "user", "content": "event text"}),
                ("missing", {"role": "user", "content": "other text"}),
                ("same", {"role": "user", "content": "same then same"}),
                ("same", {"role": "assistant", "content": "same"}),
                ("same", {"role": "user", "content": [{"type": "image", "text": "same"}]}),
                ("same", {"role": "user", "content": [{"type": "text", "text": "same"},
                                                        {"type": "text", "text": "same"}]})):
            c = Capture("turn-1", "fixture-chat", 100)
            self.assertFalse(c.bind_counterpart_input(original, message, 0))
            c.request("system", [message], {}, False, 101)
            p = c.finalize("final", 110)
            self.assertFalse(any(n["kind"] == "ordinary_source" for n in p["lineage"]))
            self.assertFalse(any(n.get("source_bindings") for n in p["lineage"]))

    def test_structured_input_records_text_part_and_leaves_images_unknown(self):
        c = Capture("turn-1", "fixture-chat", 100)
        message = {"role": "user", "content": [{"type": "image", "data": "synthetic-image"},
                    {"type": "text", "text": "prefix original suffix"}]}
        self.assertTrue(c.bind_counterpart_input("original", message, 0))
        c.request("system", [message], {}, False, 101)
        p = c.finalize("final", 110)
        node = next(n for n in p["lineage"] if n.get("slot") == 1)
        self.assertEqual(node["source_bindings"][0]["span"]["part"], 1)
        self.assertFalse(node["complete"])
        self.assertEqual(len([n for n in p["lineage"] if n["kind"] == "ordinary_source"]), 1)

    def test_bindings_do_not_move_to_identical_history_or_changed_inputs(self):
        for change in ("move", "edit"):
            c = Capture("turn-1", "fixture-chat", 100)
            message = {"role": "user", "content": "original"}
            self.assertTrue(c.bind_counterpart_input("original", message, 1))
            history = [{"role": "assistant", "content": "previous"}, message]
            if change == "move": history.reverse()
            else: message["content"] = "edited original"
            c.request("system", history, {}, False, 101)
            p = c.finalize("final", 110)
            self.assertFalse(any(n.get("source_bindings") for n in p["lineage"]))

    def test_retry_preserves_exact_bound_current_input_and_not_new_instructions(self):
        c = Capture("turn-1", "fixture-chat", 100)
        message = {"role": "user", "content": "original"}
        self.assertTrue(c.bind_counterpart_input("original", message, 0))
        c.request("system", [message], {}, False, 101)
        c.request("system", [message, {"role": "user", "content": "synthetic retry"}], {}, False, 102)
        p = c.finalize("final", 110)
        bound = [n for n in p["lineage"] if n.get("source_bindings")]
        self.assertEqual(len(bound), 2)
        self.assertTrue(all(n["slot"] == 1 and not n["complete"] for n in bound))
        self.assertEqual(lineage_status(c.context_id, {n["id"]: n for n in p["lineage"]}, 110), "unknown")

    def test_external_binding_lifecycle_is_immutable_after_routing(self):
        message = {"role": "user", "content": "original"}
        for slot in (True, -1, "0"):
            c = Capture("turn-1", "fixture-chat", 100)
            self.assertFalse(c.bind_counterpart_input("original", message, slot))
        c = Capture("turn-1", "fixture-chat", 100)
        c.request("system", [message], {}, False, 101)
        with self.assertRaises(ValueError): c.bind_counterpart_input("original", message, 0)

    def test_explicit_request_disambiguates_identical_responses(self):
        for selected_index in (0, 1):
            c = Capture("turn-1", "fixture-chat", 100)
            requests = []
            for i in range(2):
                invocation = c.request("synthetic system", [], {}, False, 101 + i)
                invocation.observe(result("identical", actual="fixture-%d" % i))
                requests.append(invocation)
            c.select("identical", request=requests[selected_index])
            p = c.finalize("final", 110)
            attempts = p["witness_receipt"]["generation"]["attempts"]
            chosen = next(a for a in attempts if a["outcome"] == "selected")
            self.assertEqual(chosen["served_model"], "fixture-%d" % selected_index)
            self.assertEqual(chosen["request_id"], "request-%d" % (selected_index + 1))
            self.assertEqual(chosen["input_sha256"], p["requests"][selected_index]["input_sha256"])

    def test_explicit_root_in_equal_text_stages(self):
        c = Capture("turn-1", "fixture-chat", 100)
        invocation = c.request("system", [], {}, False, 101)
        r = result("same", actual="fixture-selected")
        r["stages"] = [result("same", actual="fixture-discarded"), r]
        invocation.observe(r)
        c.select("same", request=invocation)
        attempts = c.finalize("same", 110)["witness_receipt"]["generation"]["attempts"]
        self.assertEqual([a["outcome"] for a in attempts], ["discarded", "selected"])

    def test_missing_foreign_or_invalidated_request_never_falls_back_to_text(self):
        for token_kind in ("none", "foreign", "double_observed", "wrong_text"):
            c = Capture("turn-1", "fixture-chat", 100)
            token = c.request("system", [], {}, False, 101)
            token.observe(result("same"))
            raw = "same"
            if token_kind == "none": token = None
            if token_kind == "foreign":
                other = Capture("turn-2", "fixture-chat", 100)
                token = other.request("system", [], {}, False, 101)
                token.observe(result("same"))
            if token_kind == "double_observed":
                with self.assertRaises(ValueError): token.observe(result("same"))
            if token_kind == "wrong_text": raw = "unobserved"
            c.select(raw, request=token)
            self.assertEqual(c.finalize("same", 110)["witness_receipt"]["status"], "unknown")

    def test_request_is_snapshot_of_actual_arguments_not_configured_identity(self):
        c = Capture("turn-1", "fixture-chat", 100)
        messages = [{"role": "user", "content": [{"type": "text", "text": "synthetic input"}]}]
        params = {"temperature": 0.25}
        a = c.request("synthetic system", messages, params, False, 101)
        messages[0]["content"][0]["text"] = "edited input"
        params["temperature"] = 0.5
        b = c.request("synthetic system", messages, params, False, 102)
        p = c.finalize("synthetic final", 110)
        self.assertNotEqual(p["requests"][0]["input_sha256"], p["requests"][1]["input_sha256"])
        self.assertNotIn("synthetic input", str(p))
        self.assertNotIn("synthetic system", str(p))
        self.assertNotIn("edited input", str(p))
        inputs = [n for n in p["lineage"] if "slot" in n]
        self.assertEqual(len(inputs), 4)
        self.assertTrue(all(n["origin"] == "unknown" and n["complete"] is False for n in inputs))
        self.assertNotEqual(a.request_id, b.request_id)

    def test_retry_retains_previous_request_and_result_dependencies(self):
        c = Capture("turn-1", "fixture-chat", 100)
        a = c.request("system", [], {}, False, 101)
        a.observe(result("old"))
        b = c.request("system", [], {}, False, 102)
        b.observe(result("new"))
        c.select("new", request=b)
        p = c.finalize("new", 110)
        nodes = {n["id"]: n for n in p["lineage"]}
        second = nodes[p["requests"][1]["context_receipt_id"]]
        self.assertIn(p["requests"][0]["context_receipt_id"], second["parents"])
        self.assertIn(c.context_id + ":attempt-1", second["parents"])
        self.assertEqual(lineage_status(c.context_id, nodes, 110), "unknown")
        self.assertFalse(p["attempt_history_complete"])

    def test_clock_regressions_and_partial_observation_stay_unknown(self):
        c = Capture("turn-1", "fixture-chat", 100)
        clock = iter([101, 105])
        a, kwargs = prepare_shadow(c, "system", [], {}, False, lambda: next(clock))
        kwargs["observer"](result("same"))
        with self.assertRaises(ValueError): c.request("system", [], {}, False, 104)
        with self.assertRaises(ValueError): c.finalize("same", 104)
        c.select("same", request=a)
        self.assertEqual(c.finalize("same", 106)["witness_receipt"]["status"], "recorded")
        self.assertEqual(prepare_shadow(c, "system", [], {}, False, 107), (None, {}))

    def test_selection_is_offered_not_admitted_and_does_not_copy_errors(self):
        c = Capture("turn-1", "fixture-chat", 100)
        c.context_selection({"ts": 99, "selection_id": "fixture-selection", "selection_version": 3,
            "offers": {"fixture-organ": {"state": "organ_error", "err": "private synthetic exception"},
                       "fixture-other": {"state": "offered", "influence_id": "fixture-version"}}})
        p = c.finalize("final", 110)
        selection = next(n for n in p["lineage"] if n.get("observation") == "context_selection")
        self.assertEqual(selection["scope"], "offers_not_admission")
        self.assertFalse(selection["complete"])
        self.assertIn(selection["id"], p["lineage"][0]["parents"])
        self.assertNotIn("private synthetic exception", str(p))

    def test_incomplete_request_binding_is_rejected_by_normalization(self):
        c = Capture("turn-1", "fixture-chat", 100)
        a = c.request("system", [], {}, False, 101); a.observe(result("same"))
        c.select("same", request=a)
        r = c.finalize("same", 110)["witness_receipt"]
        del r["generation"]["attempts"][0]["input_sha256"]
        self.assertEqual(normalize_receipt(r)["status"], "unknown")

    def test_observed_identity_is_separate_from_configuration(self):
        r = G.make_result("fixture", model="configured-fixture", status="valid", text="synthetic")
        c = Capture("turn-1", "fixture-chat", 100)
        c.observe(r); c.select("synthetic")
        packet = c.finalize("synthetic", 110)
        self.assertIsNone(packet["witness_receipt"]["generation"]["attempts"][0]["served_model"])
        self.assertEqual(result()["observed_model"], "observed-fixture")
        missing = result(actual=None)
        missing["model"] = "configured-fallback"
        self.assertIsNone(missing["observed_model"])

    def test_shared_parsers_keep_exact_wire_contract(self):
        r = G.from_anthropic({"model": "observed-fixture", "content": [{"type": "text", "text": "synthetic"}],
                              "stop_reason": "end_turn"})
        self.assertEqual(set(r), set(G.KEYS))
        self.assertEqual(set(G.from_openai({"model": "fixture", "choices": []}, "fixture")), set(G.KEYS))
        self.assertEqual(set(G.make_result("fixture")), set(G.KEYS))

    def test_relay_claim_is_retained_without_observed_identity(self):
        r = G.make_result("fixture", text="synthetic", status="valid", model="claimed-fixture")
        r.update(claimed_model="claimed-fixture", identity_evidence="claimed")
        c = Capture("turn-1", "fixture-chat", 100)
        c.observe(r); c.select("synthetic")
        p = c.finalize("final", 110)
        self.assertIsNone(p["witness_receipt"]["generation"]["attempts"][0]["served_model"])
        self.assertEqual(p["identity_claims"], [{"attempt_id": "attempt-1", "claimed_model": "claimed-fixture",
                                                "evidence": "relay_claim"}])

    def test_fallback_stages_and_self_reference(self):
        failed = G.make_result("fixture", status="unavailable", reason="private synthetic reason")
        selected = result()
        selected["stages"] = [failed, selected]
        c = Capture("turn-1", "fixture-chat", 100)
        c.observe(selected); c.select("synthetic raw reply")
        p = c.finalize("synthetic final reply", 110, "handed_to_framework")
        r = p["witness_receipt"]
        self.assertEqual([a["outcome"] for a in r["generation"]["attempts"]], ["failed", "selected"])
        self.assertEqual(r["response_sha256"], digest("synthetic final reply"))
        self.assertEqual(r["delivery"], "unknown")
        self.assertFalse(p["attempt_history_complete"])
        self.assertNotIn("private synthetic reason", str(p))
        self.assertNotIn("synthetic raw reply", str(p))

    def test_context_and_reply_remain_explicitly_incomplete(self):
        c = Capture("turn-1", "fixture-chat", 100)
        c.observe(result()); c.select("synthetic raw reply")
        p = c.finalize("synthetic final", 110)
        self.assertEqual(p["reply_node"]["kind"], "reply")
        self.assertFalse(p["reply_node"]["complete"])
        nodes = {n["id"]: n for n in p["lineage"]}
        self.assertEqual(lineage_status("context:turn-1", nodes, 100), "unknown")

    def test_interleaved_requests_never_share_attempts(self):
        a, b = Capture("a", "fixture-chat", 100), Capture("b", "fixture-chat", 100)
        a.observe(result("reply A")); b.observe(result("reply B"))
        a.select("reply A"); b.select("reply B")
        self.assertEqual(a.finalize("A", 110)["turn_id"], "a")
        self.assertEqual(b.finalize("B", 110)["turn_id"], "b")

    def test_raw_selection_and_finalization_are_explicit(self):
        c = Capture("turn-1", "fixture-chat", 100)
        c.observe(result()); c.select("unobserved reply")
        p = c.finalize("synthetic final", 110)
        self.assertEqual(p["witness_receipt"]["status"], "unknown")
        with self.assertRaises(ValueError): c.finalize("again", 111)
        with self.assertRaises(ValueError): c.observe(result())
        other = Capture("turn-2", "fixture-chat", 100)
        with self.assertRaises(ValueError): other.finalize("synthetic", 110, "delivered")

    def test_repeat_then_new_selection(self):
        c = Capture("turn-1", "fixture-chat", 100)
        c.observe(result("repeat")); c.observe(result("new synthetic reply"))
        c.select("new synthetic reply")
        r = c.finalize("final", 110)["witness_receipt"]
        self.assertEqual([a["outcome"] for a in r["generation"]["attempts"]], ["discarded", "selected"])

    def test_equal_text_cannot_identify_which_attempt_was_selected(self):
        for same_model in (True, False):
            with self.subTest(same_model=same_model):
                c = Capture("turn-1", "fixture-chat", 100)
                c.observe(result("identical synthetic reply", actual="fixture-first"))
                c.observe(result("identical synthetic reply", actual=(
                    "fixture-first" if same_model else "fixture-second")))
                c.select("identical synthetic reply")
                self.assertEqual(c.finalize("synthetic final", 110)["witness_receipt"]["status"], "unknown")

    def test_router_observer_is_optional_and_noninterfering(self):
        # Execute only the wrapper with an async recorder; never import provider clients.
        tree = ast.parse((ROOT / "bin/model_router.py").read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "route_reply")
        calls = []
        async def fake(*args):
            calls.append(args)
            r = result(); r["route"] = "fixture-route"
            r["stages"] = [r]
            return r
        ns = {"route_reply_result": fake, "GR": G}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "isolated-router-wrapper", "exec"), ns)
        self.assertIs(ns["route_reply_result"], fake)
        args = ("fixture-chat", "synthetic system", [], {}, "unused", {}, "configured-fixture")
        baseline = asyncio.run(ns["route_reply"](*args))
        capture = Capture("turn-1", "fixture-chat", 100)
        self.assertEqual(asyncio.run(ns["route_reply"](*args, observer=capture.observe)), baseline)
        def broken(_): raise ValueError("synthetic observer fault")
        self.assertEqual(asyncio.run(ns["route_reply"](*args, observer=broken)), baseline)
        def mutating(r):
            r["stages"][0]["text"] = "mutated text"
            r["status"] = "error"
            r["route"] = "mutated route"
        self.assertEqual(asyncio.run(ns["route_reply"](*args, observer=mutating)), baseline)
        self.assertEqual(len(calls), 4)
        capture.select(baseline[0])
        self.assertEqual(capture.finalize(baseline[0], 110)["witness_receipt"]["status"], "recorded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
