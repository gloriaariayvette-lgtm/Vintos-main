#!/usr/bin/env python3
"""An unreconciled step names itself, a step never sent is told apart, and only a receipt settles the rest.

All stores are scratch copies; every sender is blocked (test_lab_tool_routing's sandbox)."""
from datetime import datetime, timezone
import hashlib
import json
import time
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
        self.began = C.now_iso()            # the notebook is shared by every test: rows from this one only
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
        request = {'skill': 'nvmolkit', 'operation': 'similarity', 'question': QUESTION}
        self.open_with(self.relay_step(dispatched_at='2026-10-30T08:41:16+00:00', dispatch_marker=1,
                                       tool='instrument:nvmolkit', request=request, executed_request=request),
                       {'id': 'S-done', 'at': C.now_iso(), 'state': 'completed', 'route': 'source', 'tool': 'source:pubmed'})
        with self.assertRaises(I.Unreconciled) as caught:
            self.finish()
        text = str(caught.exception)
        self.assertLessEqual(len(text), 240)                  # the fault line keeps 240 characters
        for part in ('cannot finish with an unreconciled execution outcome', 'I-35a4ddf4394f', 'S-889709144f5b',
                     '1 of 2', 'instrument:nvmolkit similarity', 'outcome_unknown since 2026-10-30T08:43:18Z',
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


    # -- a relay step sent and never settled: an incomplete finish after the relay's send timeout (F-2d7df745e8) --
    def notebook(self, kind):
        return [r for r in C._jsonl(C.NOTEBOOK) if r.get('kind') == kind and str(r.get('at')) >= self.began]

    def sent(self, seconds_ago):
        return datetime.fromtimestamp(time.time() - seconds_ago, timezone.utc).isoformat()

    def test_relay_step_past_send_timeout_finishes_incomplete_and_a_late_receipt_settles_it_once(self):
        # remote completion after local failure: the relay ran, the Lab lost the reply, the receipt lands later
        self.open_with(self.relay_step(dispatched_at=self.sent(3600), dispatch_marker=1))
        self.ask.return_value = self.choice('source', {'source': 'pubchem', 'name': 'fixture'})
        I.turn('', ask=self.ask, execute=lambda *a: {'receipt': {'source': 'pubchem', 'records': [{'smiles': 'CCO'}]}})
        with patch.object(C, '_reflect', return_value={'answers_question': 'no: the pocket measure is missing'}) as reflect:
            row = self.finish()
        reflect.assert_called_once()                          # reviewed with what there is
        left_out = reflect.call_args.args[2]['outputs_not_reviewed']
        self.assertEqual([x['step'] for x in left_out], ['S-889709144f5b'])
        self.assertEqual(left_out[0]['reason'], I.UNSETTLED_REASON)
        self.assertEqual((row['incomplete'], row['unsettled']), (True, ['S-889709144f5b']))
        inv = self.stored()[0]
        self.assertEqual((inv['incomplete'], inv['unsettled']), (True, ['S-889709144f5b']))
        self.assertEqual(inv['steps'][0]['state'], 'outcome_unknown')   # not settled by finishing
        review = dict(inv['last_review'])
        self.write_receipt()
        for _ in range(3):                                    # reconciled again and again: one entry
            I.reconcile('I-35a4ddf4394f')
            ledger = Path(plugin_gateway.MEMORY) / 'plugin-receipts.jsonl'
            ledger.touch()
        inv = self.stored()[0]
        step = inv['steps'][0]
        self.assertEqual(step['state'], 'completed')
        self.assertTrue(step['reconciled']['late'])
        late = self.notebook('late_receipt')
        self.assertEqual(len(late), 1)
        self.assertEqual((late[0]['investigation'], late[0]['step']), ('I-35a4ddf4394f', 'S-889709144f5b'))
        self.assertEqual(inv['last_review'], review)          # the incomplete review is kept, not redone
        self.assertEqual(inv['unsettled'], ['S-889709144f5b'])

    def test_all_missing_review_claims_no_answer(self):
        self.open_with(self.relay_step(dispatched_at=self.sent(3600), dispatch_marker=1))
        with patch.object(C, '_reflect') as reflect:
            row = self.finish()
        reflect.assert_not_called()                           # nothing to read, so the model is not asked
        self.assertTrue(row['answers_question'].startswith('no:'))
        self.assertFalse(row['reviewed'])
        inv = self.stored()[0]
        self.assertEqual(inv['state'], 'unanswered')
        self.assertNotIn('finding', inv)
        self.assertIn('finished incomplete', inv['closed_reason'])
        self.assertEqual(inv['steps'][0]['state'], 'outcome_unknown')

    def test_interrupted_between_reply_and_receipt_finishes_incomplete_without_resending(self):
        self.open_with(self.relay_step(state='started', dispatched_at=self.sent(3600), dispatch_marker=1))
        execute = Mock()
        self.ask.return_value = self.choice('finish', {})
        with patch.object(C, '_reflect') as reflect:
            I.turn('', ask=self.ask, execute=execute)
        execute.assert_not_called()
        reflect.assert_not_called()
        inv = self.stored()[0]
        self.assertEqual(inv['steps'][0]['state'], 'outcome_unknown')
        self.assertEqual(inv['unsettled'], ['S-889709144f5b'])

    def test_relay_step_within_send_timeout_defers_and_waiting_is_not_a_failure(self):
        self.open_with(self.relay_step(dispatched_at=self.sent(60), dispatch_marker=1))
        row = self.finish()
        self.assertEqual((row['kind'], row['state']), ('investigation_wait', 'finish_deferred'))
        inv = self.stored()[0]
        self.assertAlmostEqual(inv['deferred_until'], time.time() - 60 + plugin_gateway.SKILL_TIMEOUT, delta=5)
        self.assertEqual(int(inv.get('planning_failures') or 0), 0)
        self.assertEqual(inv['state'], 'open')
        self.assertEqual(self.ask.call_count, 1)
        self.assertIsNone(I.turn('', ask=self.ask))           # set aside until then: no re-proposal every turn
        self.assertEqual(self.ask.call_count, 1)

    def test_the_wait_counts_from_the_send_not_from_a_later_interruption(self):
        # sent an hour ago, found interrupted just now: the hour counts
        self.open_with(self.relay_step(dispatched_at=self.sent(3600), dispatch_marker=1, state_at=C.now_iso()))
        with patch.object(C, '_reflect'):
            self.assertEqual(self.finish()['kind'], 'investigation_review')
        # sent a minute ago, its state stamped an hour ago: it waits
        self.open_with(self.relay_step(dispatched_at=self.sent(60), dispatch_marker=1, state_at=self.sent(3600)))
        self.assertEqual(self.finish()['state'], 'finish_deferred')
        # a send time that cannot be read waits for a receipt, as before
        for bad in ('not a time', '2026-10-30T08:41:16'):
            with self.subTest(bad):
                self.open_with(self.relay_step(dispatched_at=bad, dispatch_marker=1))
                with self.assertRaises(I.Unreconciled):
                    self.finish()

    def test_a_non_relay_unknown_still_blocks_a_mixed_finish(self):
        self.open_with(self.relay_step(dispatched_at=self.sent(3600), dispatch_marker=1),
                       {'id': 'S-exp', 'at': C.now_iso(), 'state': 'outcome_unknown', 'route': 'experiment',
                        'tool': 'experiment:bell', 'request_sha256': 'exp', 'state_at': C.now_iso(),
                        'dispatched_at': self.sent(3600), 'dispatch_marker': 1})
        with patch.object(C, '_reflect') as reflect:
            with self.assertRaisesRegex(I.Unreconciled, 'S-exp'):
                self.finish()
        reflect.assert_not_called()
        inv = self.stored()[0]
        self.assertNotIn('incomplete', inv)
        self.assertEqual([s['state'] for s in inv['steps']], ['outcome_unknown', 'outcome_unknown'])

    def test_unreadable_or_ambiguous_receipt_after_an_incomplete_finish_settles_nothing(self):
        self.open_with(self.relay_step(dispatched_at=self.sent(3600), dispatch_marker=1))
        self.finish()
        self.write_receipt()
        with patch.object(I, '_relay_receipt', side_effect=ValueError('unreadable')):
            self.assertEqual(I.reconcile('I-35a4ddf4394f')['reconciled'], [])
        ledger = Path(plugin_gateway.MEMORY) / 'plugin-receipts.jsonl'
        with open(ledger, 'a') as stream:                     # the same arguments again under another id
            row = json.loads(ledger.read_text().splitlines()[0]); row['receipt_id'] = 'f' * 64
            stream.write(json.dumps(row) + '\n')
        self.assertEqual(I.reconcile('I-35a4ddf4394f')['reconciled'], [])
        self.assertEqual(self.stored()[0]['steps'][0]['state'], 'outcome_unknown')
        self.assertEqual(self.notebook('late_receipt'), [])

    def test_identical_request_in_another_investigation_stays_held_after_an_incomplete_finish(self):
        request = {'skill': 'structure_viewer', 'operation': 'structure.measure', 'files': MODEL, 'question': QUESTION}
        self.open_with()
        self.ask.return_value = self.choice('instrument', request)
        I.turn('', ask=self.ask, execute=Mock(side_effect=TimeoutError('timed out after send')))
        data = C._load(I._path('investigations.json'), {})
        held = data['investigations'][0]['steps'][0]
        self.assertEqual(held['state'], 'outcome_unknown')
        held['dispatched_at'] = self.sent(3600)
        C._atomic(I._path('investigations.json'), data)
        self.finish()
        first = self.stored()[0]
        self.assertEqual((first['state'], first['unsettled']), ('unanswered', [held['id']]))
        data = C._load(I._path('investigations.json'), {})
        data['investigations'].append({'id': 'I-second', 'opened_at': C.now_iso(), 'state': 'open',
                                       'question': 'Which residues coordinate halide?', 'prediction': 'p', 'steps': []})
        C._atomic(I._path('investigations.json'), data)
        execute = Mock()
        self.ask.return_value = self.choice('instrument', request)
        row = I.turn('', ask=self.ask, execute=execute)
        execute.assert_not_called()
        self.assertEqual(row['state'], 'failed')
        self.assertIn('reconcile it before repeating', row['error'])
        self.assertIn(held['id'], row['error'])


if __name__ == '__main__':
    unittest.main()
