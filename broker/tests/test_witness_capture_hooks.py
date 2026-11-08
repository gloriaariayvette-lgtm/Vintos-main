#!/usr/bin/env python3
"""Actual handler capture segments with stubbed routing, plus private sink guards.

The giant application is not imported: unrelated body/device/feed code never runs.
This tests the executed capture path and its placement, not a full app HTTP run.
"""
import ast
import asyncio
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "bin")]
import witness_capture as W
import gen_result as G


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="witness-hooks-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.assertNotIn(".vintos", self.root.parts)
        self.environment = patch.dict(os.environ, SPARK_WORKSPACE=str(self.root), JUDGES_CAPTURE_SCRATCH=str(self.root))
        self.environment.start(); self.addCleanup(self.environment.stop)

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(W.begin_shadow("fixture-turn", "fixture-chat", 100))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_private_packet_and_no_delivery_inference(self):
        c = W.begin_shadow("fixture-turn", "fixture-chat", 100)
        c.observe(G.make_result("fixture", status="valid", text="synthetic raw"))
        c.select("synthetic raw")
        self.assertTrue(W.finish_shadow(c, "synthetic final", 110, test_mode=True))
        paths = list(self.root.glob("capture-*.json"))
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].stat().st_mode & 0o777, 0o600)
        packet = json.loads(paths[0].read_text())
        self.assertEqual(packet["content"], packet["witness_final_text"])
        self.assertEqual(packet["transport"], "handed_to_framework")
        self.assertEqual(packet["witness_receipt"]["delivery"], "unknown")
        self.assertTrue(packet["test_mode"])
        self.assertFalse(packet["lineage"][0]["complete"])

    def test_scratch_rejects_live_roots_and_symlinks(self):
        live = self.root / ".vintos" / "workspace"; live.mkdir(parents=True, mode=0o700)
        alias = self.root / "alias"; alias.symlink_to(live)
        for location in (live, alias, self.root.parent, ROOT):
            with patch.dict(os.environ, SPARK_WORKSPACE=str(location), JUDGES_CAPTURE_SCRATCH=str(location)):
                with self.assertRaises(ValueError): W.begin_shadow("fixture-turn", "fixture-chat", 100)
        self.assertEqual(list(live.iterdir()), [])

    def test_permissions_and_workspace_must_match(self):
        with patch.dict(os.environ, SPARK_WORKSPACE="different-workspace"):
            with self.assertRaises(ValueError): W.begin_shadow("fixture-turn", "fixture-chat", 100)
        self.root.chmod(0o755)
        with self.assertRaises(ValueError): W.begin_shadow("fixture-turn", "fixture-chat", 100)
        self.root.chmod(0o700)
        c = W.begin_shadow("fixture-turn", "fixture-chat", 100)
        self.root.chmod(0o755)
        with self.assertRaises(ValueError): W.finish_shadow(c, "synthetic", 110)
        self.root.chmod(0o700)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_tactical_provenance_is_retained(self):
        c = W.begin_shadow("fixture-turn", "fixture-chat", 100)
        p = {"turn_id": "fixture-turn", "output_provenance": "stratagem_influenced", "may_witness": False}
        W.finish_shadow(c, "synthetic", 110, p)
        packet = json.loads(next(self.root.glob("capture-*.json")).read_text())
        self.assertFalse(packet["generation_provenance"]["may_witness"])
        self.assertEqual(packet["reply_node"]["influence"], "influenced")

    def handler_segments(self, retry=False, replacement=False):
        source = (ROOT / "bin/server.py").read_text()
        self.assertEqual(source, (ROOT / "scripts/server.py").read_text())
        tree = ast.parse(source)
        handler = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "avatar_chat")
        outer = next(n for n in handler.body if isinstance(n, ast.Try) and any(
            isinstance(x, ast.Import) and any(a.name == "model_router" for a in x.names) for x in n.body))
        start = next(i for i, n in enumerate(outer.body) if isinstance(n, ast.Import)
                     and any(a.name == "model_router" for a in n.names))
        setup = outer.body[start:start + 5]
        self.assertTrue(isinstance(setup[-1], ast.Assign) and setup[-1].targets[0].id == "_witness_selected")
        routed = sorted([n for n in ast.walk(outer) if isinstance(n, ast.Assign)
                         and isinstance(n.value, ast.Await) and isinstance(n.value.value, ast.Call)
                         and isinstance(n.value.value.func, ast.Attribute)
                         and n.value.value.func.attr == "route_reply"], key=lambda n: n.lineno)
        self.assertEqual(len(routed), 3)
        prepared = sorted([n for n in ast.walk(outer) if isinstance(n, ast.Assign) and any(
            isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "prepare_shadow"
            for c in ast.walk(n.value))], key=lambda n: n.lineno)
        chosen = sorted([n for n in ast.walk(outer) if isinstance(n, ast.Assign)
                         and isinstance(n.value, ast.Name) and n.value.id == "_witness_request"
                         and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "_witness_selected"],
                        key=lambda n: n.lineno)
        self.assertEqual(len(prepared), 3)
        self.assertEqual(len(chosen), 3)
        for before, route, after in zip(prepared, routed, chosen):
            self.assertLess(before.lineno, route.lineno)
            self.assertLess(route.lineno, after.lineno)
        for node in routed:
            self.assertTrue(any(k.arg is None and isinstance(k.value, ast.Name) and k.value.id == "_witness_kwargs"
                                for k in node.value.value.keywords))
        select = next(n for n in outer.body if isinstance(n, ast.If) and any(
            isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "select" for c in ast.walk(n)))
        guard = next(n for n in outer.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                     and isinstance(n.value.func, ast.Name) and n.value.func.id == "_sg_guard")
        final = next(n for n in outer.body if isinstance(n, ast.If) and any(
            isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "finish_shadow" for c in ast.walk(n)))
        ret = next(n for n in outer.body if isinstance(n, ast.Return) and n.lineno > final.lineno)
        self.assertLess(routed[-1].lineno, select.lineno)
        self.assertLess(select.lineno, guard.lineno)
        self.assertLess(guard.lineno, final.lineno)
        self.assertEqual(outer.body.index(ret), outer.body.index(final) + 1)
        # A stubbed postprocessing edit proves the final guard output, rather
        # than the raw generation, is what reaches the sink and return value.
        edit = ast.parse('reply = reply + " after postprocessing"').body[0]
        route_body = [prepared[0], routed[0], chosen[0]]
        if retry:
            # Execute the actual repeat decision and its exception path; no
            # provider, judge, store, device or notification code is imported.
            repeat = next(n for n in outer.body if isinstance(n, ast.Try) and any(
                isinstance(c, ast.Assign) and c.lineno == routed[1].lineno for c in ast.walk(n)))
            route_body.append(repeat)
        if replacement:
            route_body.append(ast.Try(body=[prepared[2], routed[2], chosen[2]], handlers=[
                ast.ExceptHandler(type=ast.Name(id="Exception", ctx=ast.Load()), body=[ast.Pass()])],
                orelse=[], finalbody=[]))
        fn = ast.AsyncFunctionDef(name="exercise", args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=copy.deepcopy(setup + route_body + [select, edit, guard, final, ret]), decorator_list=[])
        return ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))

    def exercise(self, sink_failure=False, enabled=True, responses=None, retry=False, replacement=False):
        calls = []
        responses = responses or ["synthetic raw"]
        async def provider(*args):
            calls.append(args)
            response = responses[len(calls) - 1]
            if isinstance(response, Exception): raise response
            r = G.from_openai({"model": "fixture-observed", "choices": [{"message": {"content": response},
                                      "finish_reason": "stop"}]}, "fixture")
            r["route"] = "fixture-route"
            r.update(observed_model="fixture-observed", identity_evidence="response_metadata")
            return r
        router_tree = ast.parse((ROOT / "bin/model_router.py").read_text())
        wrapper = next(n for n in router_tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "route_reply")
        router_ns = {"route_reply_result": provider, "GR": G}
        exec(compile(ast.Module(body=[wrapper], type_ignores=[]), "stubbed-router", "exec"), router_ns)
        router = types.ModuleType("model_router"); router.route_reply = router_ns["route_reply"]
        self.assertIs(router_ns["route_reply_result"], provider)
        turn = types.SimpleNamespace(turn_id="fixture-turn", carries_capsule=False)
        clock = iter(range(100, 200))
        ns = {"_turn": turn, "_surface": "fixture-chat", "time": types.SimpleNamespace(time=lambda: next(clock)),
              "messages": [{"content": "synthetic system"}], "params": {}, "LM_STUDIO_API": "unused",
              "LLM_AUTH_HEADERS": {}, "_reason": False, "_prov_envelope": None, "_test_turn": True,
              "_note_task": None, "_rr_keep": False, "_sg_guard": lambda text, turn: text + " after final guard",
              "av_history": [], "_same_as_last_reply": lambda text, history: text == "synthetic repeat"}
        code = compile(self.handler_segments(retry, replacement), "actual-handler-capture-segments", "exec")
        def failed(*args, **kwargs): raise OSError("synthetic sink failure")
        with patch.dict(sys.modules, {"model_router": router}), contextlib.redirect_stdout(io.StringIO()):
            with contextlib.ExitStack() as stack:
                if sink_failure: stack.enter_context(patch.object(W, "finish_shadow", failed))
                if not enabled: stack.enter_context(patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=""))
                exec(code, ns)
                answer = asyncio.run(ns["exercise"]())
        self.assertEqual(len(calls), len(responses))
        return answer

    def test_actual_repeat_selection_accept_reject_and_failure(self):
        for response, selected in (("synthetic new", "request-2"), ("synthetic repeat", None),
                                   (OSError("synthetic router failure"), "request-1")):
            with self.subTest(selected=selected):
                self.exercise(responses=["synthetic repeat", response], retry=True)
                path = next(self.root.glob("capture-*.json"))
                packet = json.loads(path.read_text()); path.unlink()
                self.assertEqual(len(packet["requests"]), 2)
                attempts = packet["observed_attempts"]
                chosen = [a["request_id"] for a in attempts if a["outcome"] == "selected"]
                self.assertEqual(chosen, [selected] if selected else [])
                if selected is None:
                    self.assertEqual(packet["witness_receipt"]["status"], "unknown")

    def test_replacement_route_equal_text_uses_its_own_attempt(self):
        self.exercise(responses=["synthetic raw", "synthetic raw"], replacement=True)
        packet = json.loads(next(self.root.glob("capture-*.json")).read_text())
        chosen = [a for a in packet["observed_attempts"] if a["outcome"] == "selected"]
        self.assertEqual(chosen[0]["request_id"], "request-2")

    def test_replacement_route_failure_keeps_original_identity(self):
        self.exercise(responses=["synthetic raw", OSError("synthetic router failure")], replacement=True)
        packet = json.loads(next(self.root.glob("capture-*.json")).read_text())
        chosen = [a for a in packet["observed_attempts"] if a["outcome"] == "selected"]
        self.assertEqual(chosen[0]["request_id"], "request-1")

    def test_actual_handler_segments_bind_final_guard_output(self):
        answer = self.exercise()
        packet = json.loads(next(self.root.glob("capture-*.json")).read_text())
        self.assertEqual(packet["witness_final_text"], answer["reply"])
        self.assertEqual(answer["reply"], "synthetic raw after postprocessing after final guard")
        self.assertEqual(packet["witness_receipt"]["generation"]["attempts"][0]["served_model"], "fixture-observed")
        self.assertEqual(packet["witness_receipt"]["generation"]["attempts"][0]["request_id"], "request-1")
        self.assertEqual(packet["requests"][0]["at"], 101)
        observed = next(n for n in packet["lineage"] if n.get("observation") == "router_result")
        self.assertEqual(observed["at"], 102)
        self.assertEqual(observed["time_basis"], "observed")

    def test_disabled_and_failed_capture_do_not_change_reply(self):
        disabled = self.exercise(enabled=False)
        failed = self.exercise(sink_failure=True)
        self.assertEqual(disabled, failed)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_failed_write_sync_or_publication_leaves_no_packet(self):
        def partial(obj, file, **kwargs):
            file.write('{"partial":')
            raise OSError("synthetic full disk")
        for target, fault in ((W.json, "dump"), (W.os, "fsync"), (W.os, "link")):
            with self.subTest(fault=fault):
                c = W.begin_shadow("fixture-turn", "fixture-chat", 100)
                error = partial if fault == "dump" else OSError("synthetic failure")
                with patch.object(target, fault, side_effect=error):
                    with self.assertRaises(OSError): W.finish_shadow(c, "synthetic final", 110)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_atomic_publication_never_overwrites_existing_packet(self):
        existing = self.root / "capture-fixed.json"
        existing.write_text("existing synthetic packet")
        with patch.object(W.uuid, "uuid4", return_value=types.SimpleNamespace(hex="fixed")):
            c = W.begin_shadow("fixture-turn", "fixture-chat", 100)
            with self.assertRaises(FileExistsError): W.finish_shadow(c, "synthetic final", 110)
        self.assertEqual(existing.read_text(), "existing synthetic packet")
        self.assertEqual(list(self.root.iterdir()), [existing])


if __name__ == "__main__":
    unittest.main(verbosity=2)
