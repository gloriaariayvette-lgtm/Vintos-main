"""Atomic state replacement under failures; scratch paths and stubbed effects only."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import home_presence as hp


class AtomicPresence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in {"WS": str(root), "MEMORY": str(root), "CONFIG": str(root / "config.json"),
                            "STATE": str(root / "state.json")}.items():
            p = patch.object(hp, name, value); p.start(); self.addCleanup(p.stop)
        self.state = Path(hp.STATE)
        self.old = b'{"home": false, "misses": 4, "checked": 100}'
        self.state.write_bytes(self.old)
        self.probe, self.observe = Mock(return_value=True), Mock()
        for p in [patch.object(hp, "probe", self.probe),
                  patch.dict(sys.modules, {"sensor_reactions": types.SimpleNamespace(observe=self.observe)}),
                  patch.object(hp.subprocess, "run", side_effect=AssertionError("no hardware")),
                  patch("socket.socket.connect", side_effect=AssertionError("no network"))]:
            p.start(); self.addCleanup(p.stop)
        self.assertTrue(Path(hp.STATE).is_relative_to(root))
        self.assertIs(hp.probe, self.probe)
        self.assertIs(sys.modules["sensor_reactions"].observe, self.observe)

    def run_main(self):
        with contextlib.redirect_stdout(io.StringIO()): hp.main()

    def no_temps(self):
        self.assertEqual(list(Path(self.tmp.name).glob(".home-presence-*")), [])

    def test_complete_replacement_and_existing_sensor_call(self):
        replace = os.replace
        def inspect(src, dst):
            self.assertEqual(self.state.read_bytes(), self.old)
            self.assertTrue(json.loads(Path(src).read_bytes())["home"])
            self.assertEqual(Path(src).parent, self.state.parent)
            replace(src, dst)
        with patch.object(hp.os, "replace", side_effect=inspect): self.run_main()
        new = json.loads(self.state.read_bytes())
        self.assertTrue(new["home"])
        self.assertEqual(new["misses"], 0)
        self.observe.assert_called_once_with("presence", True, at=new["checked"])
        self.no_temps()

    def test_partial_write_failure_preserves_old_bytes(self):
        def fail(state, stream, **kwargs):
            stream.write('{"partial":'); raise OSError("fixture write failure")
        with patch.object(hp.json, "dump", side_effect=fail): self.run_main()
        self.assertEqual(self.state.read_bytes(), self.old); self.no_temps()

    def test_replace_failure_preserves_old_bytes(self):
        with patch.object(hp.os, "replace", side_effect=OSError("fixture replace failure")): self.run_main()
        self.assertEqual(self.state.read_bytes(), self.old); self.no_temps()

    def test_fsync_failure_preserves_old_bytes(self):
        with patch.object(hp.os, "fsync", side_effect=OSError("fixture fsync failure")): self.run_main()
        self.assertEqual(self.state.read_bytes(), self.old); self.no_temps()


if __name__ == "__main__": unittest.main()
