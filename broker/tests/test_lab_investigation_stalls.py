#!/usr/bin/env python3
"""Why investigations stalled (24-25 October): repeats of their own steps and source cooldowns were counted as
failures, and a repeat's reuse matched on question wording across different accessions. Scratch stores only; every
sender is blocked by the shared sandbox and nothing is executed except the stubs passed in."""
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_lines

C = sandbox.C


def choice(route, request, step_question='Measure the sourced protein', question='Is the RT beside the array?'):
    return json.dumps({'question': question, 'prediction': 'It is within 2 kb.', 'plan': ['inputs', 'measure'],
                       'route': route, 'request': request, 'step_question': step_question, 'why': 'next comparison'})


def store():
    return C._load(I._path('investigations.json'), {})


class Stalls(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(Path(I._path('investigations.json')).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations': []})
        C._atomic(I._path('source-throttle.json'), {})
        self.ask = Mock()
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=None), opened_by=Mock(return_value=None),
                                    record_step=Mock(), advance_plan=Mock(return_value='stale'))
        self.lines.start()

    def tearDown(self):
        self.lines.stop()
        sandbox.SEND.assert_not_called()

    # 1. a repeat of this investigation's own completed step
    def test_repeat_within_is_handed_its_output_and_never_counts_as_a_failure(self):
        self.ask.return_value = choice('source', {'source': 'pubchem', 'name': 'fixture'})
        execute = Mock(return_value={'receipt': {'source': 'pubchem', 'records': [{'SMILES': 'CCO'}]}})
        first = I.turn('', ask=self.ask, execute=execute)
        for _ in range(I.MAX_FAILED_RUN + 2):
            row = I.turn('', ask=self.ask, execute=execute)
            self.assertEqual((row['state'], row['reused_from'], row['repeat_within']), ('completed', first['id'], True))
        execute.assert_called_once()                        # never re-sent
        inv = store()['investigations'][0]
        self.assertEqual(inv['state'], 'open')              # 7 repeats did not close it as "produced nothing"
        self.assertIn('source:pubchem', self.ask.call_args.args[1].split('"already_asked"')[1][:80])
        self.assertEqual(I.next_phase({}, row, {}), 'orient')   # a repeat is not run through the phases again
        lab_lines.record_step.assert_not_called()           # nor told to the line as a new result

    def test_repeat_within_does_not_break_a_run_of_real_failures(self):
        steps = ([{'id': 'S-c', 'state': 'completed'}]
                 + [{'id': 'S-f%d' % n, 'state': 'failed', 'error': 'source_query_unavailable:HTTPError 500'}
                    for n in range(2)]
                 + [{'id': 'S-r', 'state': 'completed', 'repeat_within': True, 'reused_from': 'S-c'}]
                 + [{'id': 'S-g%d' % n, 'state': 'failed', 'error': 'source_query_unavailable:HTTPError 500'}
                    for n in range(2)])
        self.assertEqual(I._budget_spent({'steps': steps}), '')
        steps.append({'id': 'S-h', 'state': 'failed', 'error': 'source_query_unavailable:HTTPError 500'})
        self.assertTrue(I._budget_spent({'steps': steps}).startswith('5 operations in a row produced nothing'))

    def test_repeat_refused_by_the_repeat_check_takes_this_investigations_own_step(self):
        q = 'Fetch the sequence of accession P12345'
        self.ask.return_value = choice('source', {'source': 'uniprot', 'query': 'accession:P12345'}, q)
        rec = {'receipt': {'source': 'uniprot', 'records': [{'primaryAccession': 'P12345',
                                                              'sequence': {'value': 'MAAAA', 'length': 5}}]}}
        first = I.turn('', ask=self.ask, execute=lambda *a: rec)
        self.ask.return_value = choice('source', {'source': 'uniprot', 'query': 'accession:P12345', 'size': 1}, q)
        def refuse(*a): raise ValueError('no eligible saved step: you already ran this exact lookup on 2026-10-25 01:00')
        row = I.turn('', ask=self.ask, execute=refuse)
        self.assertEqual((row['state'], row['reused_from'], row.get('repeat_within')), ('completed', first['id'], True))

    # 2. waiting is not failing
    def test_source_cooldown_is_a_wait_not_a_failure(self):
        self.ask.return_value = choice('source', {'source': 'pubmed', 'query': 'phage reverse transcriptase'})
        C._atomic(I._path('source-throttle.json'), {'pubmed': time.time() + 120})
        def door(*a): raise RuntimeError(I.COOLDOWN)       # the source door's own throttle, nothing sent
        row = I.turn('', ask=self.ask, execute=door)
        self.assertEqual(row['state'], 'waiting_not_sent')
        self.assertGreater(row['retry_at'], time.time() + 60)
        calls = self.ask.call_count
        wait = I.turn('', ask=self.ask, execute=door)
        self.assertEqual(wait['kind'], 'investigation_wait')
        self.assertEqual(self.ask.call_count, calls)         # no planner call, no step, while it waits
        steps = [{'id': 'S-f%d' % n, 'state': 'failed', 'error': 'refused'} for n in range(4)]
        steps += [{'id': 'S-w%d' % n, 'state': s} for n, s in enumerate(('superseded_not_sent', 'waiting_not_sent') * 3)]
        self.assertEqual(I._budget_spent({'steps': steps}), '')
        self.assertEqual(store()['investigations'][0]['state'], 'open')

    # 3. real failures still close at five, and say why
    def test_real_failures_still_close_at_five_and_the_reason_names_the_cause(self):
        for n in range(I.MAX_FAILED_RUN):
            self.ask.return_value = choice('source', {'source': 'pubchem', 'name': 'fixture-%d' % n})
            err = ('source_query_unavailable:ValueError: unsupported Lab source' if n != 2
                   else 'no eligible saved step: unchanged unresolved identity: multiple accessions')
            I.turn('', ask=self.ask, execute=Mock(side_effect=ValueError(err)))
        inv = store()['investigations'][0]
        self.assertEqual(inv['state'], 'stalled')
        self.assertEqual(inv['closed_reason'], '5 operations in a row produced nothing: '
                         'mostly operation not offered or malformed as requested (4 of 5)')
        self.assertEqual(I.MAX_FAILED_RUN, 5)
        self.assertEqual(I.MAX_STEPS, 14)

    def test_step_budget_closure_counts_what_the_steps_were(self):
        steps = ([{'id': 'S-c%d' % n, 'state': 'completed'} for n in range(3)]
                 + [{'id': 'S-r%d' % n, 'state': 'completed', 'repeat_within': True} for n in range(6)]
                 + [{'id': 'S-w', 'state': 'superseded_not_sent'}]
                 + [{'id': 'S-f%d' % n, 'state': 'failed', 'error': 'you already asked this on 2026-10-25'} for n in range(4)])
        reason = I._budget_spent({'steps': steps})
        self.assertIn('step budget spent (14 operations) without a finish: 3 new outputs, 6 repeats', reason)
        self.assertIn('1 not sent', reason)
        self.assertIn('4 failed; failures mostly refused as a repeat with no retained output to reuse (4 of 4)', reason)

    # 4. identity: question overlap never reaches across different identifiers
    def _data(self, *steps):
        return {'investigations': [{'id': 'I-1', 'steps': list(steps)}]}

    def test_o43511_output_is_never_given_to_a_q8ech7_request(self):
        a = {'id': 'S-a', 'state': 'completed', 'tool': 'source:uniprot', 'output_file': 'x.json', 'route': 'source',
             'at': '2026-10-25T04:00', 'question': 'What is the amino acid sequence and domain architecture of protein O43511?',
             'request': {'source': 'uniprot', 'query': 'accession:O43511'}}
        b = {'id': 'S-b', 'route': 'source', 'tool': 'source:uniprot',
             'question': 'What is the amino acid sequence and domain architecture of protein Q8ECH7?',
             'request': {'source': 'uniprot', 'query': 'accession:Q8ECH7'}}
        refusal = 'you already asked this on 2026-10-25 04:00, in other words: ...'
        self.assertIsNone(I._answered_before(refusal, b, self._data(a)))
        same = dict(b, question='What is the amino acid sequence and domain architecture of protein O43511 here?',
                    request={'source': 'uniprot', 'query': 'accession:O43511'})
        self.assertIs(I._answered_before(refusal, same, self._data(a)), a)
        # the accession only in the question still separates them
        c = dict(b, request={'source': 'uniprot', 'query': 'the protein named in the question'})
        a2 = dict(a, request={'source': 'uniprot', 'query': 'the protein named in the question'})
        self.assertIsNone(I._answered_before(refusal, c, self._data(a2)))

    def test_different_organism_or_files_or_pmids_are_never_reused(self):
        base = {'state': 'completed', 'output_file': 'x.json', 'at': '2026-10-25T04:00',
                'question': 'Which reverse transcriptases sit beside CRISPR arrays in these genomes?'}
        refusal = 'you already asked this on 2026-10-25'
        for key, mine, theirs, tool, route in (
                ('organism', 'Escherichia coli', 'Shewanella oneidensis', 'source:ncbi', 'source'),
                ('files', ['artifacts/esmfold/a.pdb'], ['artifacts/esmfold/b.pdb'], 'instrument:fold_read', 'instrument'),
                ('pmids', ['31796593'], ['31796594'], 'source:pubmed', 'source')):
            a = dict(base, id='S-a', tool=tool, route=route, request={'term': 'reverse transcriptase', key: theirs})
            b = dict(base, id='S-b', tool=tool, route=route, request={'term': 'reverse transcriptase', key: mine})
            del b['state'], b['output_file']
            self.assertIsNone(I._answered_before(refusal, b, self._data(a)), key)
            self.assertIs(I._answered_before(refusal, dict(b, request=dict(a['request'])), self._data(a)), a, key)

    def test_reuse_through_a_turn_is_refused_across_accessions_and_when_the_output_lacks_the_accession(self):
        q = 'What is the amino acid sequence and domain architecture of protein %s?'
        self.ask.return_value = choice('source', {'source': 'uniprot', 'query': 'accession:O43511'}, q % 'O43511')
        rec = {'receipt': {'source': 'uniprot', 'records': [{'primaryAccession': 'O43511', 'sequence': {'value': 'MA'}}]}}
        first = I.turn('', ask=self.ask, execute=lambda *a: rec)
        data = store(); data['investigations'][0]['state'] = 'stalled'; C._atomic(I._path('investigations.json'), data)
        def refuse(*a): raise ValueError('no eligible saved step: you already asked this on 2026-10-25 04:00')
        self.ask.return_value = choice('source', {'source': 'uniprot', 'query': 'accession:Q8ECH7'}, q % 'Q8ECH7')
        with patch.object(I, '_same_question', return_value=[]):   # the reopening gate: test_lab_no_repeat
            row = I.turn('', ask=self.ask, execute=refuse)
        self.assertEqual(row['state'], 'failed')
        self.assertNotIn('reused_from', row)
        # same identifiers, but the retained output does not carry the accession asked for: not handed over
        step = {'id': 'S-new', 'request': {'source': 'uniprot', 'query': 'accession:O43511'}}
        self.assertTrue(I._carries(rec, step))
        self.assertFalse(I._carries({'receipt': {'records': [{'primaryAccession': 'P99999'}]}}, step))
        self.assertTrue(first['id'])

    # 5. a two-model read whose models were each read before (25 October: 31 such steps refused whole in a day)
    def test_each_model_of_a_multi_model_read_refused_as_a_repeat_takes_its_retained_read(self):
        a, b, c = ('artifacts/esmfold/O43511-ac5611395a4c.pdb', 'artifacts/esmfold/O43511-60e20d840671.pdb',
                   'artifacts/esmfold/O43511-920c104e94a4.pdb')
        earlier = {}
        for f in (a, b):
            self.ask.return_value = choice('instrument', {'instrument_query': {'skill': 'fold_read', 'operation':
                'structure.read', 'files': [f]}}, 'Identify the secondary structure (helix vs strand) and confidence '
                'for the C-terminal region where the STAS domain is located.')
            rec = {'receipt': {'receipt_id': 'fold_read-' + f[-20:], 'records': [{'skill': 'fold_read',
                   'inputs': [f], 'summary': 'residues 1-780: helices 700-712'}]}}
            earlier[f] = I.turn('', ask=self.ask, execute=lambda *x, rec=rec: rec)['id']
        refusal = ('no eligible saved step: you already ran this exact lookup on 2026-10-21 21:24 (instrument_query:'
                   '{"files": ["artifacts/esmfold/o43511-ac5611395a4c.pdb"], "operation": "structure.read", "skill": '
                   '"fold_); it would return the same thing')
        import lab_instruments
        q = ('Extract the helix and strand geometry for the C-terminal region (approx. residues 700-780) to check '
             'for STAS motif consistency.')
        with patch.object(C, '_inquiry', lambda d: d), \
             patch.object(C, '_held_to_plan', lambda *x, **k: ({'refused': refusal}, {})), \
             patch.object(lab_instruments, 'run', Mock(side_effect=AssertionError('nothing is read again'))):
            out = I.dispatch('instrument', {'skill': 'fold_read', 'operation': 'structure.read', 'files': [a, b],
                                            'question': q}, q, [])
            self.assertEqual([(r['file'], r['reused_from']) for r in out['reads']], [(a, earlier[a]), (b, earlier[b])])
            self.assertIn('helices 700-712', json.dumps(out['reads'][0]['result']))
            self.assertEqual(out['not_read'], [])
            # a model never read before is still refused, and never given another model's read
            out = I.dispatch('instrument', {'skill': 'fold_read', 'operation': 'structure.read', 'files': [a, c]}, q, [])
            self.assertEqual([r['file'] for r in out['reads']], [a])
            self.assertEqual([(e['file'], e['error'][:40]) for e in out['not_read']], [(c, refusal[:40])])
            with self.assertRaisesRegex(ValueError, 'you already ran this exact lookup'):
                I.dispatch('instrument', {'skill': 'fold_read', 'operation': 'structure.read', 'files': [c, c]}, q, [])

    def test_fold_reads_operation_under_the_viewer_name_is_fold_read(self):
        from lab_tool_calls import normalize_request
        got = normalize_request('instrument', {'instrument_query': {'skill': 'structure_viewer', 'operation':
                                'structure.read', 'files': ['artifacts/esmfold/O43511-60e20d840671.pdb']}})
        self.assertEqual((got['skill'], got['operation']), ('fold_read', 'structure.read'))
        for op in ('structure.analyze', None, 'no.such'):
            self.assertEqual(normalize_request('instrument', {'skill': 'structure_viewer', 'operation': op})['skill'],
                             'structure_viewer')

    def test_a_referenced_output_is_identified_by_its_content(self):
        steps = [{'id': 'S-x', 'output_sha256': 'aaa'}, {'id': 'S-y', 'output_sha256': 'aaa'},
                 {'id': 'S-z', 'output_sha256': 'bbb'}]
        shas = I._output_shas({'investigations': [{'steps': steps}]})
        ref = lambda sid: {'request': {'records': {'step': sid, 'path': ['normalized_records']}}}
        self.assertEqual(I._identity(ref('S-x'), shas), I._identity(ref('S-y'), shas))
        self.assertNotEqual(I._identity(ref('S-x'), shas), I._identity(ref('S-z'), shas))


class BudgetReview(unittest.TestCase):
    """Of 715 investigations one was ever reviewed; after the 25 October deploy four spent all 14 steps, every one
    completed, and closed unread. The planner is told the budget and what finish is, and at the budget the evidence is
    reviewed once. The review is stubbed; nothing is sent."""
    Q = 'Is the RT beside the array?'

    def setUp(self):
        self.assertTrue(Path(I._path('investigations.json')).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(Path(C.NOTEBOOK).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('source-throttle.json'), {})
        self.ask = Mock(return_value=choice('source', {'source': 'pubchem', 'name': 'last'}, question=self.Q))
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=None), opened_by=Mock(return_value=None),
                                    record_step=Mock(), advance_plan=Mock(return_value='stale'))
        self.lines.start()
        import lab_findings
        self.record = patch.object(lab_findings, 'record', Mock(return_value={'kind': 'finding', 'kept': True,
                                                                              'told_gloria': False, 'appraisal': 'ok'}))
        self.record.start()

    def tearDown(self):
        self.record.stop()
        self.lines.stop()
        sandbox.SEND.assert_not_called()

    def seed(self, n=I.MAX_STEPS - 1, state=lambda k: 'completed', repeat=lambda k: False, tool='source:pubchem'):
        steps = []
        for k in range(n):
            step = {'id': 'S-%02d' % k, 'at': '2026-10-26T00:%02d' % k, 'route': 'source', 'tool': tool,
                    'question': 'step %d' % k, 'request': {'source': 'pubchem', 'name': 'fixture-%d' % k}}
            I._store_result(step, {'receipt': {'source': 'pubchem', 'records': [{'cid': k}]}})
            step['state'] = state(k)
            if repeat(k): step.update(repeat_within=True, reused_from='S-00')
            steps.append(step)
        C._atomic(I._path('investigations.json'), {'investigations': [
            {'id': 'I-b', 'opened_at': '2026-10-26T00:00', 'state': 'open', 'line_id': None, 'question': self.Q,
             'prediction': 'within 2 kb', 'plan': [], 'steps': steps}]})
        return steps

    def last_turn(self, verdict, execute=None):
        execute = execute or (lambda *a: {'receipt': {'source': 'pubchem', 'records': [{'cid': 99}]}})
        with patch.object(C, '_reflect', return_value={'answers_question': verdict}) as reflect:
            I.turn('', ask=self.ask, execute=execute)
        return reflect, store()['investigations'][0]

    def test_planner_is_told_the_budget_and_what_finish_is(self):
        self.seed(n=3)
        sent = []
        I._plan(store()['investigations'][0], '', lambda s, p, **k: sent.append(p) or '{}')
        task, _ = json.JSONDecoder().raw_decode(sent[0])
        self.assertEqual(task['step_budget']['steps_used'], 3)
        self.assertEqual(task['step_budget']['steps_left'], I.MAX_STEPS - 3)
        self.assertEqual(task['step_budget']['new_completed_outputs'], 3)
        for words in ('finish asks for a review of the evidence so far', 'as soon as these outputs could answer',
                      'At the budget the evidence is reviewed anyway'):
            self.assertIn(words, task['step_budget']['finish'])
        self.assertNotIn('same_tool', task)                       # three in a row is not yet four

    def test_same_tool_four_times_is_named_as_advice_and_nothing_is_removed(self):
        self.seed(n=5, tool='instrument:fold_read')
        sent = []
        I._plan(store()['investigations'][0], '', lambda s, p, **k: sent.append(p) or '{}')
        task, _ = json.JSONDecoder().raw_decode(sent[0])
        self.assertIn('last 4 completed steps all used instrument:fold_read', task['same_tool'])
        self.assertIn('read_output', task['same_tool'])
        self.assertIn('finish', task['available_routes'])
        self.assertIn('instrument', task['available_routes'])     # advice only: every route is still offered
        data = store(); data['investigations'][0]['steps'][-1]['tool'] = 'source:pubmed'
        C._atomic(I._path('investigations.json'), data)
        sent.clear()
        I._plan(store()['investigations'][0], '', lambda s, p, **k: sent.append(p) or '{}')
        self.assertNotIn('same_tool', json.JSONDecoder().raw_decode(sent[0])[0])

    def test_answered_review_at_the_budget_answers_it(self):
        self.seed()
        reflect, inv = self.last_turn('yes: the outputs settle it')
        reflect.assert_called_once()
        self.assertIn('additional_source', reflect.call_args.args[2])
        self.assertEqual(inv['state'], 'answered')
        self.assertEqual(inv['finding'], {'kind': 'finding', 'kept': True, 'told_gloria': False, 'appraisal': 'ok'})
        self.assertNotIn('closed_reason', inv)
        self.assertEqual(len(inv['steps']), I.MAX_STEPS)
        rows = C._tail_jsonl(C.NOTEBOOK, nbytes=1024 * 1024)
        self.assertEqual((rows[-1]['kind'], rows[-1]['at_step_budget']), ('investigation_review', True))
        self.assertEqual(rows[-2]['kind'], 'investigation_step')

    def test_unanswered_review_at_the_budget_stays_stalled_with_the_review_attached(self):
        self.seed()
        reflect, inv = self.last_turn('no: the distance to the array was never measured')
        reflect.assert_called_once()
        self.assertEqual(inv['state'], 'stalled')
        self.assertTrue(inv['closed_reason'].startswith('step budget spent (14 operations) without a finish: 14 new'))
        self.assertTrue(inv['closed_reason'].endswith('; a review at the budget found the outputs did not answer it'))
        self.assertEqual(inv['budget_review']['answers_question'], 'no: the distance to the array was never measured')
        self.assertNotIn('finding', inv)

    def test_no_review_with_fewer_than_two_new_outputs(self):
        self.seed(repeat=lambda k: k > 0)          # one new output and twelve repeats of it
        reflect, inv = self.last_turn('yes: never asked', execute=Mock(side_effect=ValueError('unsupported Lab source')))
        reflect.assert_not_called()
        self.assertEqual(inv['state'], 'stalled')
        self.assertEqual(inv['closed_reason'], I._budget_spent(inv))
        self.assertNotIn('budget_review', inv)

    def test_no_review_with_an_unreconciled_outcome(self):
        self.seed(state=lambda k: 'outcome_unknown' if k == 3 else 'completed')
        reflect, inv = self.last_turn('yes: never asked')
        reflect.assert_not_called()
        self.assertEqual(inv['state'], 'stalled')
        self.assertNotIn('review', inv['closed_reason'])

    def test_failure_runs_still_close_without_a_review(self):
        self.seed(n=4, state=lambda k: 'failed')
        reflect, inv = self.last_turn('yes: never asked', execute=Mock(side_effect=ValueError('unsupported Lab source')))
        reflect.assert_not_called()
        self.assertTrue(inv['closed_reason'].startswith('5 operations in a row produced nothing'))


class ReferenceCompareGuidance(unittest.TestCase):
    """instrument:reference_compare failed 10 of 10 on 25 October: given a name or UniProt accession, not a PDB id."""

    def test_the_menu_says_what_reference_is_and_where_to_get_one(self):
        import lab_instruments
        with patch.object(lab_instruments, '_runs_today', return_value={'runs': []}), \
             patch.object(lab_instruments, 'artifacts', return_value=['artifacts/esmfold/O43511-ac5611395a4c.pdb']):
            block = lab_instruments.menu_block()
        line = next(l for l in block.splitlines() if l.startswith('- reference_compare'))
        for words in ('four-character PDB entry id', '1ABC', "pdb source step's records", "structure's receipt"):
            self.assertIn(words, line)

    def test_the_refusal_names_the_bad_value_and_the_hint(self):
        import chemistry_reference_compare as R
        with self.assertRaises(ValueError) as caught:
            R.validate({'reference': 'O43511', 'chain': 'A', 'ref_span': [1, 10], 'model': 'O43511'})
        text = str(caught.exception)
        for words in ('four-character PDB entry id', '1ABC', "'O43511'", "pdb source step's records"):
            self.assertIn(words, text)
        self.assertEqual(I._cause({'error': text}), 'operation not offered or malformed as requested')


if __name__ == '__main__': unittest.main(verbosity=2)
