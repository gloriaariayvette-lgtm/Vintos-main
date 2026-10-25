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
        row = I.turn('', ask=self.ask, execute=refuse)
        self.assertEqual(row['state'], 'failed')
        self.assertNotIn('reused_from', row)
        # same identifiers, but the retained output does not carry the accession asked for: not handed over
        step = {'id': 'S-new', 'request': {'source': 'uniprot', 'query': 'accession:O43511'}}
        self.assertTrue(I._carries(rec, step))
        self.assertFalse(I._carries({'receipt': {'records': [{'primaryAccession': 'P99999'}]}}, step))
        self.assertTrue(first['id'])

    def test_a_referenced_output_is_identified_by_its_content(self):
        steps = [{'id': 'S-x', 'output_sha256': 'aaa'}, {'id': 'S-y', 'output_sha256': 'aaa'},
                 {'id': 'S-z', 'output_sha256': 'bbb'}]
        shas = I._output_shas({'investigations': [{'steps': steps}]})
        ref = lambda sid: {'request': {'records': {'step': sid, 'path': ['normalized_records']}}}
        self.assertEqual(I._identity(ref('S-x'), shas), I._identity(ref('S-y'), shas))
        self.assertNotEqual(I._identity(ref('S-x'), shas), I._identity(ref('S-z'), shas))


if __name__ == '__main__': unittest.main(verbosity=2)
