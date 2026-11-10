#!/usr/bin/env python3
"""Every toy at home answers to one Lovense app on her phone, and a command to one toy can end what another is
playing (9 November: the Ferri and the Mission went quiet a second after each other whenever he ran both). One toy
alone still gets its hardware Pattern; two at once are stepped here with stopPrevious=0 so neither can silence the
other. The hub and every sender are stubs; sockets are refused; scratch HOME."""
import os, socket, sys, tempfile, threading, time, unittest
from pathlib import Path
scratch = tempfile.TemporaryDirectory(prefix='toys-one-app-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/x')
def refused(self, *a, **k):
    raise OSError('this suite reaches nothing')
socket.socket.connect = refused
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
import requests
def _no_send(*a, **k):
    raise requests.ConnectionError('this suite reaches nothing')
requests.post = requests.get = _no_send
import toy_link as T, device_patterns as P

class OneApp(unittest.TestCase):
    def setUp(self):
        self.saved = (T.send, T.send_pattern, T.connected, P._stopped)
        self.sends, self.patterns, self.lock = [], [], threading.Lock()
        def send(toy, level, seconds=0, context=None, permit=None, effect_digest=None, stop_previous=None):
            with self.lock: self.sends.append((toy, level, stop_previous))
            return True
        def send_pattern(toy, strengths, interval_ms=250, seconds=0, func=None, context=None, permit=None, effect_digest=None):
            with self.lock: self.patterns.append(toy)
            return True
        T.send, T.send_pattern = send, send_pattern
        T.connected = lambda toy, strict=False: toy in ('mission', 'tenera')
        P._stopped = lambda: False
        P._threads.clear(); P._loops.clear(); P._hw.clear()

    def tearDown(self):
        P._stop_local('both')
        time.sleep(0.4)
        T.send, T.send_pattern, T.connected, P._stopped = self.saved

    def ticks(self, toy):
        with self.lock: return [s for s in self.sends if s[0] == toy and s[1]]

    def test_one_toy_alone_keeps_its_hardware_pattern(self):
        self.assertTrue(P.play('mission', 'climb'))
        self.assertEqual(self.patterns, ['mission'])
        self.assertIn('mission', P._hw)

    def test_a_second_toy_moves_both_to_steps_that_leave_each_other_alone(self):
        P.play('mission', 'climb')
        out = {}
        self.assertTrue(P.play('tenera', 'cake', outcome=out))
        self.assertEqual(self.patterns, ['mission'])          # no second hardware Pattern to cancel the first
        self.assertEqual(out['status'], 'started')
        time.sleep(1.4)
        for toy in ('mission', 'tenera'):
            got = self.ticks(toy)
            self.assertGreaterEqual(len(got), 2, toy)
            self.assertTrue(all(sp == 0 for _, _, sp in got), got)
        self.assertNotIn('mission', P._hw)

    def test_both_is_stepped_for_every_toy_there(self):
        self.assertTrue(P.play('both', 'wave1'))
        self.assertEqual(self.patterns, [])
        time.sleep(1.0)
        self.assertTrue(self.ticks('mission')); self.assertTrue(self.ticks('tenera'))
        self.assertFalse(self.ticks('ridge'))                 # not switched on: no loop for it

    def test_a_stop_ends_the_steps(self):
        P.play('both', 'high')
        time.sleep(0.6)
        P._stop_local('both')
        time.sleep(0.6)
        n = len(self.ticks('mission'))
        time.sleep(0.9)
        self.assertEqual(len(self.ticks('mission')), n)

    def test_a_steady_level_beside_a_playing_toy_leaves_it_alone(self):
        P.play('mission', 'climb')
        P.play('tenera', 'steady', [12])
        with self.lock: last = [s for s in self.sends if s[0] == 'tenera'][-1]
        self.assertEqual(last, ('tenera', 12, 0))

if __name__ == '__main__':
    unittest.main(verbosity=2)
