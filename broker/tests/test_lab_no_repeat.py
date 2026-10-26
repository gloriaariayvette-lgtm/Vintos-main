#!/usr/bin/env python3
"""Stop repeating (26 October). 53 of 58 investigations opened that day asked, word for word, a question an earlier
one had closed on; after being told a proposal repeated, the planner proposed a repeat again 158 times in 243. Now:
the same question is asked once more with what came of it before, for a different question or a narrower variant
naming what changes, and is otherwise not opened and rests on a cooldown; a re-plan says why at the end of the prompt
with the exact operation not to return; a lookup refused as asked before carries what that asking got. Scratch stores
only; every sender is blocked by the shared sandbox and nothing runs except the stubs passed in."""
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_lines

C = sandbox.C
PHAGE = 'Which bacteriophage genomes carry a reverse transcriptase beside a CRISPR array or Cas genes?'


def choice(route, request, question=PHAGE, **extra):
    return json.dumps(dict({'route': route, 'request': request, 'step_question': 'one input', 'why': 'next',
                            'question': question, 'prediction': 'some do', 'plan': ['a']}, **extra))


def store():
    return C._load(I._path('investigations.json'), {})


def notebook(kind):
    return [r for r in C._tail_jsonl(C.NOTEBOOK, nbytes=4 * 1024 * 1024) if r.get('kind') == kind]


def closed(question, state='unanswered', tools=('source:imgvr',)):
    steps = [{'id': 'S-%d' % n, 'state': 'completed', 'tool': t, 'route': 'source'} for n, t in enumerate(tools)]
    return {'id': 'I-old%d' % len(question), 'opened_at': C.now_iso(), 'state': state, 'question': question,
            'closed_reason': '3 reviews found the outputs did not answer it', 'steps': steps,
            'last_review': {'missing_evidence': 'specific phage genomes', 'next_question': 'which IMG/VR genomes'}}


class Base(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(I._path('question-cooldown.json')).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations': [closed(PHAGE)]})
        C._atomic(I._path('source-throttle.json'), {})
        C._atomic(I._path('question-cooldown.json'), {})
        self.line = {'id': 'L-phage', 'question': PHAGE}
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=self.line), opened_by=Mock(return_value=None),
                                    record_step=Mock(), advance_plan=Mock(return_value='stale'))
        self.lines.start()
        self.execute = Mock(return_value={'receipt': {'source': 'pubchem', 'records': [{'cid': 1}]}})

    def tearDown(self):
        self.lines.stop()
        sandbox.SEND.assert_not_called()


class SameQuestion(Base):
    def test_the_same_question_is_asked_once_with_what_came_of_it_and_refused_if_unchanged(self):
        ask = Mock(return_value=choice('source', {'source': 'pubchem', 'name': 'x'}))
        self.assertIsNone(I.turn('', ask=ask, execute=self.execute))
        self.assertEqual(ask.call_count, 1)
        task = json.JSONDecoder().raw_decode(ask.call_args.args[1])[0]
        earlier = task['replanning']['earlier'][0]
        self.assertEqual((earlier['missing_evidence'], earlier['tools_used']), ('specific phage genomes', ['source:imgvr']))
        self.assertEqual([i['id'] for i in store()['investigations']], ['I-old%d' % len(PHAGE)])   # not opened
        self.execute.assert_not_called()
        self.assertEqual(notebook('investigation_refused_repeat')[-1]['like'], ['I-old%d' % len(PHAGE)])
        # on the cooldown now: the next pick of that line asks nothing at all
        ask2 = Mock()
        self.assertIsNone(I.turn('', ask=ask2, execute=self.execute))
        ask2.assert_not_called()
        self.assertEqual(notebook('investigation_not_opened')[-1]['why'], 'question on the repeat cooldown')

    def test_a_different_question_opens(self):
        other = 'Do IMG/VR phage reverse transcriptases cluster with retron or DGR families by sequence similarity?'
        ask = Mock(return_value=choice('source', {'source': 'pubchem', 'name': 'x'}, question=other))
        row = I.turn('', ask=ask, execute=self.execute)
        self.assertEqual(row['state'], 'completed')
        inv = store()['investigations'][-1]
        self.assertEqual((inv['question'], inv['reopened_as'], inv['line_id']), (other, 'a different question', 'L-phage'))

    def test_a_narrower_variant_naming_a_new_tool_opens_and_the_same_variant_again_does_not(self):
        narrower = {'changes': 'tool', 'what': 'rt_locus_screen'}
        ask = Mock(return_value=choice('source', {'source': 'pubchem', 'name': 'x'}, narrower=narrower))
        row = I.turn('', ask=ask, execute=self.execute)
        self.assertEqual(row['state'], 'completed')
        inv = store()['investigations'][-1]
        self.assertEqual(inv['narrower'], narrower)
        self.assertTrue(inv['question'].endswith('Narrowed: a new tool, rt_locus_screen.'))
        inv.update(state='stalled')
        data = store(); data['investigations'][-1] = inv; C._atomic(I._path('investigations.json'), data)
        self.assertIsNone(I.turn('', ask=ask, execute=self.execute))          # that variant was done
        self.assertEqual(len(store()['investigations']), 2)

    def test_a_narrower_that_names_nothing_new_is_not_one(self):
        earlier = [closed(PHAGE)]
        self.assertIsNone(I._valid_narrower({'changes': 'tool', 'what': 'imgvr'}, earlier))      # already used
        self.assertIsNone(I._valid_narrower({'changes': 'tool', 'what': 'a better search'}, earlier))
        self.assertIsNone(I._valid_narrower({'changes': 'mood', 'what': 'imgvr'}, earlier))
        self.assertIsNone(I._valid_narrower({'changes': 'cohort', 'what': 'bacteriophage genomes'}, earlier))
        self.assertEqual(I._valid_narrower({'changes': 'accession', 'what': 'UViG IMGVR_UViG_2504643020_000001'},
                                           earlier)['changes'], 'accession')
        self.assertEqual(I._valid_narrower({'changes': 'cohort', 'what': 'Lactococcus prophages from dairy isolates'},
                                           earlier)['changes'], 'cohort')

    def test_free_cycle_questions_are_checked_after_the_first_reply(self):
        lab_lines.pick.return_value = None
        ask = Mock(side_effect=[choice('source', {'source': 'pubchem', 'name': 'x'}),
                                choice('source', {'source': 'pubchem', 'name': 'x'}, question='How long are STAS helices '
                                       'in the O43511 ESMFold model compared with the deposited 8SGW entry?')])
        row = I.turn('', ask=ask, execute=self.execute)
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(ask.call_count, 2)
        self.assertIn('8SGW', store()['investigations'][-1]['question'])

    def test_similar_wording_about_other_identifiers_is_another_question(self):
        self.assertTrue(I._alike(PHAGE, PHAGE.replace('?', '.')))
        self.assertFalse(I._alike('What are the STAS helices of O43511?', 'What are the STAS helices of Q8ECH7?'))
        old = closed(PHAGE); old['opened_at'] = '2026-09-01T00:00:00+00:00'
        self.assertEqual(I._same_question(PHAGE, None, {'investigations': [old]}), [])        # past the window


class Reasks(Base):
    def setUp(self):
        super().setUp()
        lab_lines.pick.return_value = None
        C._atomic(I._path('investigations.json'), {'investigations': []})

    def test_a_reask_ends_with_the_refusal_and_the_operation_not_to_return(self):
        first = choice('source', {'source': 'pubchem', 'name': 'fixture'}, question='Is CCO the fixture?')
        I.turn('', ask=Mock(return_value=first), execute=self.execute)
        ask = Mock(side_effect=[first, choice('source', {'source': 'pubchem', 'name': 'another'}, question='Is CCO the fixture?')])
        I.turn('', ask=ask, execute=self.execute)
        prompt, kwargs = ask.call_args.args[1], ask.call_args.kwargs
        tail = prompt[prompt.index('YOUR LAST PROPOSAL WAS NOT RUN'):]
        self.assertIn('Do NOT return this operation again', tail)
        self.assertIn('"name": "fixture"', tail)
        self.assertIn('Already done in this investigation', tail)
        self.assertNotIn('plan', json.JSONDecoder().raw_decode(prompt)[0])
        self.assertEqual(kwargs['temperature'], 0.7)

    def test_a_lookup_refused_as_asked_before_carries_what_that_asking_got(self):
        asked = 'Which phage proteins near CRISPR arrays are reverse transcriptases?'
        prior = {'id': 'I-p', 'opened_at': C.now_iso(), 'state': 'stalled', 'closed_reason': 'step budget spent',
                 'question': 'other', 'steps': [{'id': 'S-p1', 'at': C.now_iso(), 'route': 'source', 'tool': 'source:ncbi',
                                                 'state': 'completed', 'question': asked, 'summary': '12 RT proteins found',
                                                 'request': {'source': 'ncbi', 'term': 'RT'}}]}
        C._atomic(I._path('investigations.json'), {'investigations': [prior]})
        ask = Mock(side_effect=[choice('source', {'source': 'ncbi', 'operation': 'protein', 'term': 'RT'}, question='q one two three'),
                                choice('source', {'source': 'pubchem', 'name': 'x'}, question='q one two three')])
        def door(route, request, *a):
            if request.get('source') == 'ncbi':
                raise ValueError('no eligible saved step: you already asked this on 2026-10-26 15:00, in other words: ' + asked)
            return {'receipt': {'source': 'pubchem', 'records': [{}]}}
        row = I.turn('', ask=ask, execute=door)
        self.assertEqual(row['state'], 'completed')
        got = json.JSONDecoder().raw_decode(ask.call_args.args[1])[0]['replanning']['earlier_result']
        self.assertEqual((got['investigation'], got['step'], got['its_output']), ('I-p', 'S-p1', '12 RT proteins found'))
        self.assertIn('stalled', got['that_investigation_closed'])


if __name__ == '__main__': unittest.main(verbosity=2)
