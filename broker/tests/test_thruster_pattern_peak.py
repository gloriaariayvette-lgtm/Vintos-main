#!/usr/bin/env python3
"""The thruster's patterns peak lower (Gloria, 11 November): a pattern step at 20 is 50% of the machine, a steady
level keeps 60%, and his number after a pattern sets its peak instead of being ignored. Stubs only; scratch HOME."""
import os, sys, tempfile, unittest
from pathlib import Path
scratch = tempfile.TemporaryDirectory(prefix='thruster-peak-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/x')
os.makedirs(scratch.name + '/.vintos/workspace/memory', exist_ok=True)
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
import requests
def _no_send(*a, **k): raise requests.ConnectionError('this suite reaches nothing')
requests.post = requests.get = _no_send
import thruster_link as TH, toy_link as T, device_patterns as P

class Peak(unittest.TestCase):
    def test_pattern_ceiling_is_lower_than_steady(self):
        self.assertEqual(TH._scalar(20), 0.6)
        self.assertEqual(TH._scalar(20, pattern=True), 0.5)
        self.assertEqual(TH._scalar(10, pattern=True), 0.25)

    def test_driver_steps_patterns_at_the_pattern_ceiling(self):
        self.assertIn('_scalar(seq[seq_i % len(seq)], pattern=True)', (REPO / 'scripts' / 'thruster_link.py').read_text())

    def test_his_number_sets_the_peak(self):
        got = []
        saved = T.send_pattern, P._stopped
        T.send_pattern = lambda toy, lv, iv=250, secs=0, func=None, **k: got.append(list(lv)) or True
        P._stopped = lambda: False
        try:
            P.play('thruster', 'climb', ['12'])
            P.play('thruster', 'climb')
            P.play('thruster', 'climb', ['12', 'slow'])
        finally:
            T.send_pattern, P._stopped = saved
        self.assertEqual(max(got[0]), 12)
        self.assertEqual(max(got[1]), 20)
        self.assertEqual(max(got[2]), 12)
        self.assertEqual(len(got[0]), len(P.PRESETS['climb'][0]))

if __name__ == '__main__':
    unittest.main(verbosity=2)
