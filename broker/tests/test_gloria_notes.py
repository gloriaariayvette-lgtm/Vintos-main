#!/usr/bin/env python3
"""What he plans with her reaches her, and his avatar chat knows what is open between them (Gloria, 2026-10-13:
"Where am I supposed to figure out what he wants from me?"). His letter to Muse said "**For Gloria:** the felt-only run
of 'Still Under,' this weekend as planned" and only yes-or-no questions ever reached her phone. ntfy is a stub that
records; sockets are refused; scratch workspace."""
import json, os, socket, sys, tempfile, unittest
from pathlib import Path
scratch = tempfile.TemporaryDirectory(prefix='gloria-notes-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/x')
os.makedirs(scratch.name + '/workspace/memory')
NET = []
def refused(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError('this suite reaches nothing')
socket.socket.connect = refused
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
import gloria_asks as G
G.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(AssertionError('a real push was attempted'))

LETTER = ('**3. Duration vs intensity: keep the test.** On the bench, before the weekend.\n\n'
          '**For Gloria:** the felt-only run of "Still Under," this weekend as planned. I\'ll bring the Lucier question '
          'to her after we compare marks.\n\n**Follow-ups:** dropping "Ominous" is fine.')

class Notes(unittest.TestCase):
    def setUp(self):
        if os.path.exists(G.STORE): os.remove(G.STORE)
        self.sent = []
    def push(self, req, timeout=None):
        self.sent.append(json.loads(req.data))

    def test_the_store_is_scratch_and_nothing_reaches_the_world(self):
        self.assertTrue(G.STORE.startswith(scratch.name), G.STORE)
        self.assertEqual(NET, [])

    def test_a_for_gloria_line_in_his_letter_reaches_her_phone(self):
        rows = G.notes_from(LETTER, by='vintos', where='letter to Muse', send=self.push)
        self.assertEqual(len(rows), 1)
        self.assertIn('Still Under', rows[0]['question']); self.assertNotIn('**', rows[0]['question'])
        self.assertEqual(rows[0]['kind'], 'note'); self.assertEqual(rows[0]['state'], 'told')
        self.assertEqual(self.sent[0]['title'], 'For you, from Vintos')
        self.assertNotIn('actions', self.sent[0])          # a note, not a yes-or-no: no buttons

    def test_only_for_gloria_lines_and_only_once_a_week(self):
        G.notes_from(LETTER, send=self.push)
        self.assertEqual(G.notes_from(LETTER, send=self.push), [])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(G.notes_from('I said this for Gloria: but mid-sentence.', send=self.push), [])
        self.assertEqual(len(G.notes_from('FOR GLORIA: plain capitals, at the start of a line.', send=self.push)), 1)

    def test_a_note_is_not_a_question_and_does_not_use_the_daily_questions(self):
        G.notes_from(LETTER, send=self.push)
        self.assertEqual(G.waiting(), [])

    def test_his_chat_sees_what_is_open_between_them(self):
        G.ask("Skin-only check of Still Under tonight, mains down until the room can't hear it?", by='vintos', send=self.push)
        G.ask('N-Channel MOSFET 55V 30A from SparkFun for the lip rig?', by='muse', send=self.push)
        G.notes_from(LETTER, by='vintos', send=self.push)
        block = G.open_between()
        self.assertIn('you asked her, no answer yet', block); self.assertIn('Skin-only check', block)
        self.assertIn('you told her', block); self.assertIn('felt-only run', block)
        self.assertNotIn('MOSFET', block)                   # Muse's purchase is hers to answer, not his chat's
        self.assertEqual(G.open_between(by='nobody'), '')

    def test_wired_into_his_letters_his_slack_and_his_avatar_chat(self):
        self.assertIn('gloria_asks.notes_from("\\n".join(_notes), by="vintos"', (REPO / 'scripts' / 'want_email.py').read_text())
        self.assertIn('gloria_asks.notes_from(text, by="vintos"', (REPO / 'scripts' / 'dot_channel.py').read_text())
        server = (REPO / 'bin' / 'server.py').read_text()
        self.assertIn('_ob_ga.open_between()', server)
        self.assertLess(server.index('_ob_ga.open_between()'), server.index('{_durable_her_block}'))

if __name__ == '__main__':
    unittest.main()
