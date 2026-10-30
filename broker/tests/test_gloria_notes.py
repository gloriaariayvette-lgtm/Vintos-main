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

    # Gloria, 28 October: "Two rooms? Piezo on the bed? Those have to be brought to me first."
    def test_a_plan_he_wrote_to_muse_reaches_her_as_his_question_first(self):
        reply = ('Thank you for the protocol.\n\n**For Gloria:** the two-room test, Saturday. Both rooms measured and '
                 'predictions written before she arrives. Marked spot plus two positions each.\n')
        rows = G.plans_from(reply, by='vintos', where='letter to Muse', send=self.push)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r['kind'], 'plan'); self.assertEqual(r['state'], 'asked'); self.assertEqual(r['thread'], '')
        self.assertIn('in his letter to Muse', r['question']); self.assertIn('not settled until you say', r['question'])
        self.assertIn('two-room test', r['question']); self.assertNotIn('**', r['question'])
        self.assertEqual(self.sent[0]['title'], 'Vintos asks you first: yes or no?')
        self.assertEqual([a['label'] for a in self.sent[0]['actions']][:2], ['Yes', 'No'])
        self.assertEqual(G.plans_from(reply, by='vintos', where='letter to Muse', send=self.push), [])   # once
        self.assertIn('you asked her, no answer yet', G.open_between())

    def test_her_no_to_his_plan_goes_back_to_him_in_its_own_words(self):
        r = G.plans_from('For Gloria: the piezo disc on the bedframe, this weekend.', by='vintos', where='letter to Muse',
                         send=self.push)[0]
        G.decide(r['id'], 'no')
        self.assertEqual(G.untold(), [('', 'vintos', 'Gloria answered NO: the piezo disc on the bedframe, this weekend.')])

    def test_his_plans_do_not_use_up_the_six_questions(self):
        for i in range(G.PER_DAY):
            G.ask('Question number %d for her, yes or no?' % i, by='dot', send=self.push)
        self.assertEqual(len(G.plans_from('For Gloria: the felt-only run of Still Under, Sunday.', send=self.push)), 1)

    # Chat's review, 29 October: the shared explanation made unrelated plans look alike (0.733 > 0.7)
    def test_two_unrelated_plans_both_reach_her(self):
        a = G.plans_from('For Gloria: the two-room test, Saturday.', where='letter to Muse', send=self.push)
        b = G.plans_from('For Gloria: the hall sensor build, Friday.', where='letter to Muse', send=self.push)
        self.assertEqual((len(a), len(b)), (1, 1))
        self.assertEqual(len(self.sent), 2)

    def test_unrelated_plan_after_her_no_still_reaches_her(self):
        r = G.plans_from('For Gloria: the two-room test, Saturday.', where='letter to Muse', send=self.push)[0]
        G.decide(r['id'], 'no')
        self.assertEqual(len(G.plans_from('For Gloria: the hall sensor build, Friday.', where='letter to Muse',
                                          send=self.push)), 1)

    def test_the_same_plan_in_other_words_is_not_asked_again(self):
        G.plans_from('For Gloria: the two-room test this Saturday, both rooms measured first.', send=self.push)
        self.assertEqual(G.plans_from('For Gloria: both rooms measured first, then the two-room test Saturday.',
                                      where='letter to Grok Bot', send=self.push), [])
        r = G.load()[0]; G.decide(r['id'], 'no')
        row, line = G.propose('the two-room test this Saturday, both rooms measured first', where='letter to Muse',
                              send=self.push)
        self.assertIsNone(row); self.assertIn('already answered', line)
        self.assertEqual(len(self.sent), 1)                 # her No stands; nothing reopened

    def test_ordinary_questions_still_match_each_other_as_before(self):
        G.ask('Skin-only check of Still Under tonight, mains down until the room cannot hear it?', send=self.push)
        row, _ = G.ask('Still Under skin-only check tonight, with the mains down until the room cannot hear it?',
                       send=self.push)
        self.assertIsNone(row)

    def test_wired_into_his_letters_his_slack_and_his_avatar_chat(self):
        self.assertIn('gloria_asks.plans_from("\\n".join(_notes), by="vintos"', (REPO / 'scripts' / 'want_email.py').read_text())
        self.assertIn('gloria_asks.notes_from(text, by="vintos"', (REPO / 'scripts' / 'dot_channel.py').read_text())
        server = (REPO / 'bin' / 'server.py').read_text()
        self.assertIn('_ob_ga.open_between()', server)
        self.assertLess(server.index('_ob_ga.open_between()'), server.index('{_durable_her_block}'))

if __name__ == '__main__':
    unittest.main()
