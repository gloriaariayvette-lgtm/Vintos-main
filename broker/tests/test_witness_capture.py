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
from witness_capture import Capture
from witness_receipts import digest, lineage_status


def result(text="synthetic raw reply", actual="observed-fixture"):
    r = G.from_openai({"model": actual, "choices": [{"message": {"content": text},
                         "finish_reason": "stop"}]}, "fixture")
    r.update(observed_model=actual, identity_evidence="response_metadata" if actual else "unknown")
    return r


class Tests(unittest.TestCase):
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
