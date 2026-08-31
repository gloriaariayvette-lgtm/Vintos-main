#!/usr/bin/env python3
import importlib.util
import json
import os
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

try:
    import requests  # noqa: F401
except ImportError:
    import sys
    sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
spec = importlib.util.spec_from_file_location("atelier_quantum",
    os.path.join(ROOT, "scripts", "atelier_quantum.py"))
AQ = importlib.util.module_from_spec(spec); spec.loader.exec_module(AQ)
visit_spec = importlib.util.spec_from_file_location("atelier_visit",
    os.path.join(ROOT, "scripts", "atelier-visit.py"))
VISIT = importlib.util.module_from_spec(visit_spec); visit_spec.loader.exec_module(VISIT)


class QuantumDoorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = AQ.CONFIG
        AQ.CONFIG = os.path.join(self.tmp.name, "quantum-lab.json")

    def tearDown(self):
        AQ.CONFIG = self.old
        self.tmp.cleanup()

    def test_missing_config_is_typed_not_absence(self):
        got = AQ.status()
        self.assertFalse(got["ok"])
        self.assertFalse(got["configured"])
        self.assertIn("not configured", got["error"])

    def test_config_is_private_and_command_has_no_shell(self):
        AQ.configure("kevin@100.79.177.103", "~/.ssh/id_ed25519")
        self.assertEqual(os.stat(AQ.CONFIG).st_mode & 0o777, 0o600)
        cfg, error = AQ._read_config(); self.assertIsNone(error)
        cmd = AQ._command(cfg)
        self.assertEqual(cmd[0], "ssh")
        self.assertNotIn("sh", cmd[:1])
        self.assertIn("BatchMode=yes", cmd)

    def test_full_run_crosses_back(self):
        AQ.configure("kevin@100.79.177.103")
        reply = {"ok": True, "run": {"run_id": "r1", "result": {"shape": [0.2, 0.8]}}}
        proc = types.SimpleNamespace(returncode=0, stdout=json.dumps(reply), stderr="")
        with mock.patch.object(AQ.subprocess, "run", return_value=proc) as called:
            got = AQ.run_seed("emotion_withheld", {"felt_intensity": 0.8}, 512)
        self.assertTrue(got["ok"])
        sent = json.loads(called.call_args.kwargs["input"])
        self.assertEqual(sent["parameters"]["felt_intensity"], 0.8)
        self.assertEqual(sent["shots"], 512)
        self.assertFalse(called.call_args.kwargs.get("shell", False))

    def test_free_python_crosses_as_source(self):
        AQ.configure("kevin@100.79.177.103")
        proc = types.SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")
        with mock.patch.object(AQ.subprocess, "run", return_value=proc) as called:
            AQ.run_code("midnight", "def experiment(parameters, shots): return {}")
        sent = json.loads(called.call_args.kwargs["input"])
        self.assertEqual(sent["action"], "code")
        self.assertIn("def experiment", sent["source"])

    def test_visit_and_broker_are_wired(self):
        visit = Path(ROOT, "scripts", "atelier-visit.py").read_text(errors="replace")
        broker = Path(ROOT, "broker", "broker.py").read_text(errors="replace")
        deploy = Path(ROOT, "scripts", "deploy-atelier.sh").read_text(errors="replace")
        self.assertIn("quantum_block", visit)
        self.assertIn("quantum_loop", visit)
        self.assertIn("<quantum_code", visit)
        self.assertIn('"quantum": 3', broker)
        self.assertIn("atelier_quantum.py", deploy)

    def test_visit_returns_the_run_for_his_reading(self):
        lab = types.SimpleNamespace(run_seed=lambda *a, **k: {
            "ok": True, "run": {"run_id": "midnight-1", "result": {"shape": [0.3, 0.7]}}})
        responses = []
        def post(url, json=None, timeout=None):
            responses.append((url, json))
            body = {"ok": True}
            if url.endswith("/make"): body.update({"file": "run_quantum.json"})
            return types.SimpleNamespace(json=lambda: body)
        follow = ("<quantum_reading>The two pulls gather rather than cancel.</quantum_reading>"
                  "<piece kind=\"write\">I kept the shape.</piece><look>I looked.</look>"
                  "<handoff>Return to the second peak.</handoff><next_return>tomorrow</next_return>")
        first = ('<quantum experiment="emotion_withheld">'
                 '{"parameters":{"felt_intensity":0.7},"shots":256}</quantum>')
        with mock.patch.object(VISIT, "_quantum_module", return_value=lab), \
             mock.patch.object(VISIT, "ask", return_value=follow), \
             mock.patch.object(VISIT.requests, "post", side_effect=post):
            got = VISIT.quantum_loop("0123456789ab", "private context", first, "cap")
        self.assertIn("The two pulls gather", got)
        made = [body for url, body in responses if url.endswith("/make")][0]
        looked = [body for url, body in responses if url.endswith("/inspect")][0]
        self.assertEqual(made["kind"], "quantum")
        self.assertEqual(looked["note"], "The two pulls gather rather than cancel.")

    def test_free_code_is_a_first_class_request(self):
        req = VISIT._quantum_request(
            '<quantum_code name="midnight">```python\n'
            'def experiment(parameters, shots): return {"display": ["alive"]}\n'
            '```</quantum_code>')
        self.assertEqual(req["kind"], "code")
        self.assertTrue(req["source"].startswith("def experiment"))


if __name__ == "__main__": unittest.main(verbosity=2)
