#!/usr/bin/env python3
"""Chained autonomous turns with real persistence and all senders blocked."""
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_lines

C = sandbox.C


class Investigations(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations':[]})
        self.ask = Mock()
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=None),
                                   opened_by=Mock(return_value=None), record_step=Mock())
        self.lines.start()

    def tearDown(self):
        self.lines.stop()
        sandbox.SEND.assert_not_called()

    def choice(self, route, request):
        return json.dumps({'question':'Do these sourced molecules form distinct similarity clusters?',
            'prediction':'Two clusters at the selected cutoff.', 'plan':['Obtain inputs','Compute similarity'],
            'route':route, 'request':request, 'step_question':'Measure molecular similarity',
            'why':'Use this result to choose the next comparison.'})

    def test_output_becomes_next_input_across_turns(self):
        self.ask.side_effect = [self.choice('source', {'source':'pubchem','name':'fixture'}),
                                self.choice('plugin', {})]
        def source(route, request, question, steps):
            return {'receipt':{'source':'pubchem','records':[{'smiles':'CCO'}, {'smiles':'CCN'}]}}
        first = I.turn('context', ask=self.ask, execute=source)
        ref = {'step':first['id'], 'path':['receipt','records']}
        self.ask.side_effect = [self.choice('plugin', {'plugin':'nvmolkit','tool':'nvmolkit.similarity',
                                                      'arguments':{'molecules':ref}})]
        seen = []
        def measure(route, request, question, steps):
            seen.append(I.resolve(request, steps))
            return {'receipt':{'source':'instrument:nvmolkit','records':[{'similarity':0.4}]}}
        second = I.turn('new context', ask=self.ask, execute=measure)
        self.assertEqual(first['investigation'], second['investigation'])
        self.assertEqual(seen[0]['arguments']['molecules'], [{'smiles':'CCO'}, {'smiles':'CCN'}])
        self.assertEqual(second['input_refs'], [ref])
        self.assertIn(first['id'], self.ask.call_args.args[1])
        self.assertEqual(second['origin'], 'autonomous_lab')

    def test_modified_output_is_not_silently_used(self):
        self.ask.return_value = self.choice('source', {'source':'pubchem','name':'fixture'})
        row = I.turn('', ask=self.ask, execute=lambda *a:{'records':['CCO']})
        C._atomic(I._path(row['output_file']), {'records':['different']})
        with self.assertRaisesRegex(ValueError, 'output changed'):
            I.resolve({'step':row['id'],'path':['records']}, [row])

    def test_screen_is_a_chosen_step_without_reserved_turns(self):
        self.ask.return_value = self.choice('campaign', {})
        execute = Mock(return_value={'kind':'campaign_screen','protein':'RETURNED.1'})
        row = I.turn('', ask=self.ask, execute=execute)
        self.assertEqual(row['route'], 'campaign')
        execute.assert_called_once()
        self.assertFalse(C._campaign_due({'turns':0}, {'campaigns':True}))
        self.assertFalse(C._campaign_due({'turns':2}, {'campaigns':True}))

    def test_failure_is_saved_as_next_step_context_without_retry(self):
        self.ask.return_value = self.choice('plugin', {'plugin':'nvidia_nim','tool':'nvidia_nim.boltz2'})
        execute = Mock(side_effect=TimeoutError('unknown outcome'))
        row = I.turn('', ask=self.ask, execute=execute)
        self.assertEqual(row['state'], 'failed')
        execute.assert_called_once()
        self.assertEqual(self.ask.call_count, 1)
        stored = C._load(I._path('investigations.json'), {})
        self.assertIn('unknown outcome', stored['investigations'][0]['steps'][-1]['error'])

    def test_finish_uses_existing_scientific_review(self):
        self.ask.return_value = self.choice('source', {'source':'pubchem','name':'fixture'})
        I.turn('', ask=self.ask, execute=lambda *a:{'receipt':{'source':'pubchem','records':[{'smiles':'CCO'}]}})
        self.ask.return_value = self.choice('finish', {})
        with patch.object(C, '_reflect', return_value={'answers_question':'no: missing comparison'}) as reflect:
            I.turn('', ask=self.ask)
            self.assertIn('additional_source', reflect.call_args.args[2])
        self.assertEqual(C._load(I._path('investigations.json'), {})['investigations'][0]['state'], 'open')
        with patch.object(C, '_reflect', return_value={'answers_question':'yes: verified fixture'}):
            I.turn('', ask=self.ask)
        self.assertEqual(C._load(I._path('investigations.json'), {})['investigations'][0]['state'], 'answered')


if __name__ == '__main__': unittest.main(verbosity=2)
