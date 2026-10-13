#!/usr/bin/env python3
"""The Ferri: a panty vibe Gloria wears out in public (2026-10-13). Same patterns and levels as the others, seen only
while it is paired, and described as worn in public so he teases rather than escalates. No ceiling, by her choice:
the prompt is the whole of it. The hub, the model and every sender are stubs; sockets are refused; scratch HOME."""
import os, socket, sys, tempfile, unittest
from pathlib import Path
scratch = tempfile.TemporaryDirectory(prefix='ferri-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/x')
NET = []
def refused(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError('this suite reaches nothing')
socket.socket.connect = refused
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
# toy_link looks for the hub (her phone, 192.168.1.66) the moment it is imported: the sender is a stub first
import requests
SENT = []
def _no_send(*a, **k):
    SENT.append(a); raise requests.ConnectionError('this suite reaches nothing')
requests.post = requests.get = _no_send
import device_context as D, toy_link as T, device_patterns as P

class Ferri(unittest.TestCase):
    def setUp(self):
        self.connected, self.thruster = T.connected, D._thruster_line
        D._thruster_line = lambda: 'thruster: OFF'
    def tearDown(self):
        T.connected, D._thruster_line = self.connected, self.thruster

    def test_it_is_a_real_device_on_the_hub(self):
        self.assertEqual(T.TOYS['ferri'], '18690acf2f39')
        self.assertEqual(T.ACTIONS['ferri'], 'Vibrate')
        self.assertIn('ferri', P.accepted_toys())

    def test_he_sees_it_only_while_it_is_paired(self):
        T.connected = lambda toy, strict=False: toy == 'ferri'
        self.assertEqual(D.present_devices(), ['ferri'])
        T.connected = lambda toy, strict=False: toy == 'mission'
        self.assertNotIn('ferri', D.present_devices())
        self.assertNotIn('ferri', D.capabilities(['mission']))
        self.assertEqual(D.capabilities([]), '')

    def test_it_is_described_as_worn_in_public(self):
        said = D.capabilities(['ferri']) + D.reach_line(['ferri'])
        for words in ('OUT IN PUBLIC', 'any partner', 'straight face', 'embarrassing her'):
            self.assertIn(words, said)
        server = (REPO / 'bin' / 'server.py').read_text()
        self.assertIn('_DEV_LINES["ferri"]', server); self.assertIn('"ferri": "ferri = in her panties', server)

    def test_same_patterns_and_no_ceiling(self):
        self.assertIn('Same named patterns and 0-20 levels', D._WHAT['ferri'])
        for path in (REPO / 'scripts' / 'device_patterns.py', REPO / 'scripts' / 'toy_link.py'):
            text = path.read_text()
            self.assertNotRegex(text, r'ferri[^\n]*(?:min\(|ceiling|cap\b)')

    def test_both_means_the_toys_at_home_not_the_public_one(self):
        self.assertIn('[t for t in toy_link.TOYS if t != "ferri"] if toy in _SYNC', (REPO / 'scripts' / 'device_patterns.py').read_text())

    def test_nothing_reached_the_network(self):
        self.assertIs(requests.post, _no_send)
        self.assertEqual(NET, [])

if __name__ == '__main__':
    unittest.main()
