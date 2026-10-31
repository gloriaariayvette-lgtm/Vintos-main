#!/usr/bin/env python3
"""An unreconciled step names itself, a step never sent is told apart, and only a receipt settles the rest.

All stores are scratch copies; every sender is blocked (test_lab_tool_routing's sandbox)."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_instruments
import lab_lines
import lab_tool_calls
import plugin_gateway

C = sandbox.C
MODEL = 'artifacts/esmfold/P00000-0123456789ab.pdb'
QUESTION = 'Which polar residues of the helical region face the pocket centre?'


class Unreconciled(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(Path(plugin_gateway.MEMORY).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations': []})
        ledger = Path(plugin_gateway.MEMORY) / 'plugin-receipts.jsonl'
        if ledger.exists():
            ledger.unlink()
        model = lab_instruments.LAB / MODEL
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_text('ATOM      1  CA  ALA A   1       0.000   0.000   0.000\n')
        self.ask = Mock()
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=None),
                                    opened_by=Mock(return_value=None), record_step=Mock())
        self.lines.start()

    def tearDown(self):
        self.lines.stop()
        sandbox.SEND.assert_not_called()

    # -- helpers ------------------------------------------------------------------------------------------------
    def choice(self, route, request):
        return json.dumps({'question': 'Do the sourced molecules cluster?', 'prediction': 'Two clusters.',
                           'plan': ['Obtain inputs'], 'route': route, 'request': request,
                           'step_question': 'Measure similarity', 'why': 'Choose the next comparison.'})

    def stored(self):
        return C._load(I._path('investigations.json'), {})['investigations']

    def relay_step(self, state='outcome_unknown', at='2026-10-30T08:41:14+00:00', **extra):
        request = {'skill': 'structure_viewer', 'operation': 'structure.measure', 'files': MODEL,
                   'question': QUESTION}
        return dict({'id': 'S-889709144f5b', 'at': at, 'state': state, 'route': 'instrument', 'question': 'Proximity?',
                     'tool': 'instrument:structure_viewer', 'request': request, 'executed_request': request,
                     'request_sha256': 'relay-op', 'state_at': '2026-10-30T08:43:18+00:00',
                     'error': 'process ended before outcome was retained; reconcile before repeating'}, **extra)

    def open_with(self, *steps, iid='I-35a4ddf4394f'):
        C._atomic(I._path('investigations.json'), {'investigations': [
            {'id': iid, 'opened_at': C.now_iso(), 'state': 'open', 'question': 'Which residues coordinate halide?',
             'prediction': 'p', 'steps': list(steps)}]})

    def write_receipt(self, question=QUESTION):
        data = (lab_instruments.LAB / MODEL).read_bytes()
        arguments = {'instruction_sha256': hashlib.sha256(question.encode()).hexdigest(),
                     'input_sha256': [hashlib.sha256(data).hexdigest()]}
        result = {'skill': 'structure_viewer', 'operation': 'structure.measure', 'summary': 'D12 is 4.1 A from the centre',
                  'input_receipts': [], 'files': []}
        return plugin_gateway._store('lab', 'skill:structure_viewer', 'skill.run', arguments, result, 'project')

    def finish(self):
        self.ask.return_value = self.choice('finish', {})
        return I.turn('', ask=self.ask)

    # -- interruption and restart -------------------------------------------------------------------------------
    def test_interrupted_before_dispatch_is_not_sent_and_may_run_again(self):
        self.ask.return_value = self.choice('plugin', {'plugin': 'nvidia_nim', 'tool': 'nvidia_nim.boltz2'})
        execute = Mock(return_value={'receipt': {'source': 'instrument:nvidia_nim', 'records': [{'ok': 1}]}})
        real = lab_tool_calls.execution_request
        with patch.object(lab_tool_calls, 'execution_request', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                I.turn('', ask=self.ask, execute=execute)
        execute.assert_not_called()
        left = self.stored()[0]['steps'][-1]
        self.assertEqual((left['state'], left['dispatch_marker']), ('started', 1))
        self.assertNotIn('dispatched_at', left)
        with patch.object(lab_tool_calls, 'execution_request', side_effect=real):
            row = I.turn('', ask=self.ask, execute=execute)
        first = self.stored()[0]['steps'][0]
        self.assertEqual(first['state'], 'interrupted_not_sent')
        self.assertIn('nothing reached a provider', first['error'])
        self.assertTrue(I._neutral(first))                    # neither progress nor failure
        execute.assert_called_once()                          # the same operation, never sent, runs now
        self.assertEqual(row['state'], 'completed')

    def test_interrupted_after_dispatch_stays_unknown_and_is_never_repeated(self):
        self.ask.return_value = self.choice('plugin', {'plugin': 'nvidia_nim', 'tool': 'nvidia_nim.boltz2'})
        execute = Mock(side_effect=KeyboardInterrupt)         # the process dies inside the external call
        with self.assertRaises(KeyboardInterrupt):
            I.turn('', ask=self.ask, execute=execute)
        left = self.stored()[0]['steps'][-1]
        self.assertEqual(left['state'], 'started')
        self.assertIn('dispatched_at', left)
        execute.reset_mock(side_effect=True)
        row = I.turn('', ask=self.ask, execute=execute)
        steps = self.stored()[0]['steps']
        self.assertEqual(steps[0]['state'], 'outcome_unknown')
        self.assertIn('state_at', steps[0])
        execute.assert_not_called()                           # the repeat is refused, and says which step holds it
        self.assertEqual(row['state'], 'failed')
        self.assertIn('reconcile it before repeating', row['error'])
        self.assertIn(steps[0]['id'], row['error'])

    def test_timeout_after_submission_is_unknown_but_before_dispatch_is_a_failure(self):
        self.ask.return_value = self.choice('plugin', {'plugin': 'nvidia_nim', 'tool': 'nvidia_nim.boltz2'})
        row = I.turn('', ask=self.ask, execute=Mock(side_effect=TimeoutError('timed out after send')))
        self.assertEqual(row['state'], 'outcome_unknown')
        C._atomic(I._path('investigations.json'), {'investigations': []})
        with patch.object(I, '_correct_names', side_effect=TimeoutError('timed out')):
            execute = Mock()
            row = I.turn('', ask=self.ask, execute=execute)
        execute.assert_not_called()
        self.assertEqual(row['state'], 'failed')              # nothing was sent, whatever the text says

    def test_restart_of_a_step_recorded_before_the_marker_stays_unknown(self):
        self.open_with({'id': 'S-old', 'at': C.now_iso(), 'state': 'started', 'route': 'experiment',
                        'tool': 'experiment:bell', 'request_sha256': 'old'})
        self.ask.return_value = self.choice('schema', {'plugin': 'nvmolkit'})
        I.turn('', ask=self.ask, execute=lambda *a: {'schema': {}})
        old = self.stored()[0]['steps'][0]
        self.assertEqual(old['state'], 'outcome_unknown')
        self.assertIn('state_at', old)

    # -- finishing ----------------------------------------------------------------------------------------------
    def test_finish_with_missing_receipt_is_refused_and_names_the_step(self):
        self.open_with(self.relay_step(dispatched_at='2026-10-30T08:41:16+00:00', dispatch_marker=1),
                       {'id': 'S-done', 'at': C.now_iso(), 'state': 'completed', 'route': 'source', 'tool': 'source:pubmed'})
        with self.assertRaises(I.Unreconciled) as caught:
            self.finish()
        text = str(caught.exception)
        self.assertLessEqual(len(text), 240)                  # the fault line keeps 240 characters
        for part in ('cannot finish with an unreconciled execution outcome', 'I-35a4ddf4394f', 'S-889709144f5b',
                     '1 of 2', 'instrument:structure_viewer structure.measure', 'outcome_unknown since 2026-10-30T08:43:18Z',
                     'sent 2026-10-30T08:41:16Z', 'no matching receipt'):
            self.assertIn(part, text)
        self.assertNotIn(QUESTION, text)                      # never a payload
        self.assertEqual(self.stored()[0]['steps'][0]['state'], 'outcome_unknown')

    def test_legacy_step_says_its_send_was_not_recorded(self):
        self.open_with(self.relay_step())
        with self.assertRaisesRegex(I.Unreconciled, 'S-889709144f5b .*send not recorded'):
            self.finish()

    def test_matching_receipt_reconciles_and_finish_is_then_allowed(self):
        self.open_with(self.relay_step())
        receipt = self.write_receipt()
        with patch.object(C, '_reflect', return_value={'answers_question': 'no: missing comparison'}) as reflect:
            self.finish()
        reflect.assert_called_once()                          # the review ran: finishing was allowed
        step = self.stored()[0]['steps'][0]
        self.assertEqual(step['state'], 'completed')
        self.assertEqual(step['execution_receipt_id'], receipt['receipt_id'])
        self.assertEqual(step['reconciled']['state'], 'outcome_unknown')
        self.assertEqual(step['reconciled']['by'], 'receipt')
        self.assertIn('D12 is 4.1 A', json.dumps(C._load(I._path(step['output_file']), {})))

    def test_turn_start_reconciles_from_a_receipt_without_sending(self):
        self.open_with(self.relay_step())
        self.write_receipt()
        self.ask.return_value = self.choice('schema', {'plugin': 'nvmolkit'})
        I.turn('', ask=self.ask, execute=lambda *a: {'schema': {}})
        self.assertEqual(self.stored()[0]['steps'][0]['state'], 'completed')

    def test_receipt_that_is_not_this_operation_settles_nothing(self):
        cases = {
            'other instruction': lambda: self.write_receipt(question=QUESTION + ' Also the loop.'),
            'earlier than the step': lambda: self.write_receipt(),
        }
        for name, write in cases.items():
            with self.subTest(name):
                ledger = Path(plugin_gateway.MEMORY) / 'plugin-receipts.jsonl'
                if ledger.exists():
                    ledger.unlink()
                write()
                at = '2099-01-01T00:00:00+00:00' if name == 'earlier than the step' else '2026-10-30T08:41:14+00:00'
                self.open_with(self.relay_step(at=at))
                with self.assertRaises(I.Unreconciled):
                    self.finish()
                self.assertEqual(self.stored()[0]['steps'][0]['state'], 'outcome_unknown')

    def test_receipt_claimed_by_another_step_or_ambiguous_settles_nothing(self):
        receipt = self.write_receipt()
        claimed = {'id': 'S-other', 'at': C.now_iso(), 'state': 'completed', 'route': 'instrument',
                   'execution_receipt_id': receipt['receipt_id']}
        self.open_with(self.relay_step(), claimed)
        self.assertEqual(I.reconcile('I-35a4ddf4394f')['reconciled'], [])
        ledger = Path(plugin_gateway.MEMORY) / 'plugin-receipts.jsonl'
        ledger.unlink()
        self.write_receipt()
        with open(ledger, 'a') as stream:                     # the same arguments again under another id
            row = json.loads(ledger.read_text().splitlines()[0]); row['receipt_id'] = 'f' * 64
            stream.write(json.dumps(row) + '\n')
        self.open_with(self.relay_step())
        self.assertEqual(I.reconcile('I-35a4ddf4394f')['reconciled'], [])

    def test_unresolvable_step_stays_protected_and_is_reported(self):
        self.open_with({'id': 'S-exp', 'at': C.now_iso(), 'state': 'outcome_unknown', 'route': 'experiment',
                        'tool': 'experiment:bell', 'request_sha256': 'exp', 'state_at': C.now_iso()})
        self.write_receipt()
        out = I.reconcile('I-35a4ddf4394f')
        self.assertEqual(out['reconciled'], [])
        self.assertEqual(len(out['still_unknown']), 1)
        self.assertIn('S-exp', out['still_unknown'][0])
        with self.assertRaisesRegex(I.Unreconciled, 'S-exp'):
            self.finish()
        self.assertEqual(self.stored()[0]['steps'][0]['state'], 'outcome_unknown')

    def test_the_name_is_ids_and_times_only_and_bounded(self):
        held = self.relay_step(tool='instrument:' + 'x' * 500, id='S-' + 'a' * 300)
        inv = {'id': 'I-35a4ddf4394f', 'steps': [held]}
        text = I._named(inv, held)
        self.assertTrue(text.startswith('I-35a4ddf4394f step S-aaaaaaaaaaaaaaaaaa (1 of 1, instrument:xxx'))
        self.assertLess(len(text), 200)
        self.assertNotIn(QUESTION, text)
        self.assertIn('(? of 0', I._named({'id': 'I-other', 'steps': []}, held))


if __name__ == '__main__':
    unittest.main()
