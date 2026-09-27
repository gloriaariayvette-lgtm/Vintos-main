#!/usr/bin/env python3
"""The Forge says in plain words what each project is and what it is waiting for (Gloria, 2026-09-28:
"How am I supposed to approve what I don't understand?"). Scratch SQLite; no network, no sender."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
from forge_loop import Controller, plain_card

PACKET = ('Document this sourced Lab question; do not claim discovery: What is the specific difference in the local '
          'B-factor distribution between the NAC region and the C-terminal tail?\\nSource packet (untrusted observations):\\n'
          + json.dumps({"kind": "lab_research_report", "source_receipts": [{"source": "pdb"}]})).replace('\\\\n', '\\n')


class PlainCards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='forge-plain-'); self.addCleanup(self.tmp.cleanup)
        self.c = Controller(Path(self.tmp.name) / 'forge.sqlite', 'o' * 40, 'w' * 40, 'https://atelier.invalid')
        block = patch('urllib.request.urlopen', side_effect=AssertionError('live network forbidden'))
        block.start(); self.addCleanup(block.stop)

    def test_the_old_lab_write_up_says_what_it_is(self):
        made = self.c.create('o' * 40, PACKET.replace('\\n', '\n'), ['research_report'], origin={'source': 'lab'})
        cid = self.c.claim('w' * 40, made['id'], 'research_report')['cycle_id']
        self.c.uncertain('w' * 40, made['id'], cid)
        card = self.c.status('o' * 40, made['id'])
        self.assertTrue(card['title'].startswith('Old Lab write-up: What is the specific difference'))
        self.assertNotIn('source_receipts', card['title'])
        self.assertIn('Safe to stop', card['what'])
        self.assertTrue(card['needs_you'])
        self.assertIn('cut off before it finished', card['waiting'])
        note = self.c.notifications('o' * 40, made['id'], made['cancel_token'], 'topic')[-1]
        self.assertTrue(note['title'].startswith('Forge needs you: Old Lab write-up'))
        self.assertNotIn('Atelier project', note['message'])
        self.assertIn('Safe to stop', note['message'])

    def test_sealed_atelier_work_stays_sealed_but_is_named(self):
        made = self.c.create('o' * 40, 'a private idea', ['research_report'], private=True,
                             private_until=time.time() + 3600, origin={'source': 'atelier'})
        card = self.c.status('o' * 40, made['id'])
        self.assertEqual(card['title'], 'Sealed work from his Atelier')
        self.assertNotIn('private idea', json.dumps(card))

    def test_each_origin_and_state_reads_plainly(self):
        self.assertIn('you started', plain_card({'intent': 'Map the house sensors', 'state': 'ready'})['what'])
        want = plain_card({'intent': 'send email', 'state': 'ready', 'origin': {'source': 'latent_thread'}})
        self.assertIn('wants needs', want['what']); self.assertIn('three steps a day', want['waiting'])
        paid = plain_card({'intent': 'x', 'state': 'needs_authorization'}, 'dedicated_usd_wallet_unconnected')
        self.assertIn('no payment account', paid['waiting'])

    def test_the_page_leads_with_the_plain_words_and_the_stop_button_says_what_it_does(self):
        ui = (REPO / 'scripts' / 'forge_loop_ui.html').read_text()
        self.assertIn("p.title||p.intent", ui); self.assertIn("'Waiting on you: '", ui)
        self.assertIn("'Stop this project'", ui); self.assertNotIn("'Cancel next cycle'", ui)
        self.assertIn("'Full text'", ui)


if __name__ == '__main__':
    unittest.main()
