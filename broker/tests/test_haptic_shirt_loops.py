"""Offline shirt transport/prompt checks; no Bluetooth or serial access is allowed."""
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
assert Path.home().name.startswith('vs-') and ROOT.is_relative_to(Path.home().resolve()), 'Run this suite through scripts/run_isolated_test.py'
sys.path.insert(0, str(ROOT / 'hardware/haptic_shirt'))

def forbidden(*args, **kwargs):
    raise AssertionError('An offline shirt test attempted a hardware connection')

bleak = types.ModuleType('bleak')
bleak.BleakClient = forbidden
bleak.BleakScanner = forbidden
exc = types.ModuleType('bleak.exc')
exc.BleakError = type('BleakError', (Exception,), {})
sys.modules['bleak'] = bleak
sys.modules['bleak.exc'] = exc

import test_shirt_signals
import test_shirt_loops
assert test_shirt_loops.playback_control is not None
suite = unittest.TestSuite([
    unittest.defaultTestLoader.loadTestsFromModule(test_shirt_signals),
    unittest.defaultTestLoader.loadTestsFromModule(test_shirt_loops),
])
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
