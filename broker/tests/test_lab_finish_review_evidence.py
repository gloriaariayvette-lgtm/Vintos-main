#!/usr/bin/env python3
"""The finish review judges an investigation on its retained instrument outputs (30 October).

Structural and instrument investigations did 8-14 steps of real work and never finished: every finish review came back
supports=[] and discarded_supports=[] with the question restated as missing. Here:
- a fold-read investigation whose instrument text is in its retained output files is reviewed on that text, the
  stubbed checker quotes it at its emitted address, both assessments agree, and the investigation is answered;
- with those outputs kept from the checker the same fixture comes back supports=[], now with a diagnostic that says
  no quotable evidence reached the checker, so the mode is never again mistaken for an unanswerable question;
- an output whose file is missing or no longer matches its output_sha256 is left out and named, never trusted, and
  the rest is still reviewed (it used to fail the whole review); per-step and total bounds hold;
- a differently worded request that comes back with an earlier step's execution receipt is marked same_receipt_as,
  is not counted as a new output, and is shown to the planner as already held, with its receipt;
- an error kept to its bound keeps the end of its traceback, not a progress bar.

Scratch HOME and stores; every sender is blocked by the shared sandbox; the model and the checker are stubs."""
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_instruments
import lab_findings
import lab_lines
import chemistry_sources

C = sandbox.C

QUESTION = 'What is the orientation of the pendrin (O43511) STAS domain relative to the transmembrane helices?'
MODEL = 'artifacts/esmfold/O43511-ac5611395a4c.pdb'
FOLD_TEXT = ('fold_read on O43511 residues 535-729: the STAS domain sits beneath the transmembrane gate, its beta sheet '
             'packed against helix TM14 on the cytoplasmic face; mean pLDDT 81.2.')
QUOTE = 'its beta sheet packed against helix TM14 on the cytoplasmic face'
COMPARE_TEXT = ('reference_compare O43511 model vs 8SGW chain A: RMSD 2.1 angstroms over 640 C-alpha atoms; the STAS '
                'domain of the deposited entry is likewise cytoplasmic.')
PENDRIN = {'accession': 'O43511', 'id': 'S26A4_HUMAN', 'protein_name': 'Pendrin', 'taxon_id': 9606,
           'organism': 'Homo sapiens', 'genes': [{'geneName': {'value': 'SLC26A4'}, 'synonyms': [{'value': 'PDS'}]}],
           'function': 'Sodium-independent transporter of chloride and iodide.', 'sequence': 'MAAPGGRSEPPQLPEY',
           'length': 16}


def relay(skill, text, receipt):
    return lab_instruments.relay_result(skill, 'structure.read', [MODEL], {'receipt': {'receipt_id': receipt},
                                                                         'summary': text})


def stored(n, skill, text, receipt):
    step = {'id': 'S-%012d' % n, 'at': C.now_iso(), 'state': 'started', 'route': 'instrument',
            'question': '%s on the STAS region' % skill, 'tool': 'instrument:' + skill,
            'request': {'skill': skill, 'operation': 'structure.read', 'files': [MODEL]}}
    I._store_result(step, relay(skill, text, receipt))
    return step


def investigation(steps):
    return {'id': 'I-finishreview', 'state': 'open', 'question': QUESTION, 'prediction': '', 'plan': [],
            'steps': steps, 'line_id': None}


class Checker:
    """The reader says yes; the coverage checker quotes the fold-read text wherever it is emitted with an address,
    and says what is missing when it is not; the sufficiency check agrees with what it is shown."""
    def __init__(self):
        self.prompts = []

    def __call__(self, system, prompt, **k):
        if system.startswith('You are Vintos reading'):
            return json.dumps({'answers_question': 'yes: the fold read places it', 'attention': 'STAS',
                               'factual_observation': 'o', 'speculative_reading': '', 'next_question': 'n',
                               'instrument_gap': ''})
        if 'evidence-coverage checker' in system:
            evidence = prompt.partition('\nEVIDENCE:\n')[2]
            self.prompts.append(evidence)
            hit = re.search(r'\{"address":"([^"]+)","text":"[^"]*' + re.escape(QUOTE), evidence)
            if not hit:
                return json.dumps({'answered': False, 'missing': [QUESTION], 'supports': []})
            return json.dumps({'answered': True, 'missing': [], 'supports': [
                {'requirement': 'STAS orientation', 'address': hit[1], 'quote': QUOTE}]})
        if system.startswith('Independently'):
            ok = QUOTE in prompt
            return json.dumps({'sufficient': ok, 'missing': [] if ok else [QUESTION],
                               'rationale': 'the fold read states it' if ok else 'not shown'})
        return '{}'


class Base(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations': []})
        C._atomic(I._path('source-throttle.json'), {})
        self.checker = Checker()
        self.found = Mock(return_value={'kind': 'finding', 'kept': True, 'told_gloria': False, 'appraisal': None})
        for p in (patch.object(C, '_ask', self.checker), patch.object(C, '_sourced_record', lambda a: dict(PENDRIN)),
                  patch.object(lab_findings, 'record', self.found),
                  patch.object(chemistry_sources, 'configured_sources', lambda: {}),
                  patch.multiple(lab_lines, pick=Mock(return_value=None), opened_by=Mock(return_value=None),
                                 record_step=Mock(), advance_plan=Mock(return_value='stale'))):
            p.start(); self.addCleanup(p.stop)
        self.steps = [stored(1, 'fold_read', FOLD_TEXT, 'fold_read-O43511-1'),
                      stored(2, 'reference_compare', COMPARE_TEXT, 'reference_compare-8SGW-1')]

    def tearDown(self):
        sandbox.SEND.assert_not_called()

    def finish(self, steps=None):
        inv = investigation(self.steps if steps is None else steps)
        data = {'investigations': [inv]}
        C._atomic(I._path('investigations.json'), data)
        row = I._carry_out(data, inv, {'route': 'finish'}, None, '', Mock(), None, False)
        return inv, row


class FinishSeesTheOutputs(Base):
    def test_the_review_quotes_the_instrument_text_and_the_investigation_finishes(self):
        inv, row = self.finish()
        self.assertEqual(inv['state'], 'answered', row.get('answers_question'))
        self.assertTrue(C.review_answered(row))
        self.assertTrue(row['answers_question'].startswith('yes'))
        support = row['coverage_check']['supports'][0]
        self.assertEqual(support['quote'], QUOTE)
        # the address is the step's own retained output, at the instrument's own text
        self.assertEqual(support['path'], 'evidence.additional_source.records.0.result.receipt.records.0.summary')
        self.assertIn(FOLD_TEXT, self.checker.prompts[0])
        self.assertIn(COMPARE_TEXT, self.checker.prompts[0])
        self.assertNotIn('coverage_diagnostic', row)
        self.assertNotIn('outputs_not_reviewed', row)
        self.found.assert_called_once()

    def test_without_the_outputs_the_same_fixture_cites_nothing_and_says_so(self):
        # what the diagnosis described: the same review with none of the outputs' text in front of the checker
        empty = {'records': [], 'LITERATURE': [], 'prior_validated_evidence': [],
                 'additional_source': {'receipt': {'source': 'investigation', 'records': []}}}
        obs = I._with_named_records(QUESTION, self.steps, empty)
        row = C._reflect('', {'question': QUESTION}, obs)
        self.assertFalse(C.review_answered(row))
        cover = row['coverage_check']
        self.assertEqual((cover['supports'], cover['discarded_supports']), ([], []))
        self.assertEqual(cover['missing'], [QUESTION])
        self.assertNotIn(FOLD_TEXT, self.checker.prompts[0])
        self.assertTrue(row['coverage_diagnostic'].startswith(C.NO_QUOTABLE_EVIDENCE), row['coverage_diagnostic'])
        self.assertEqual(cover['quotable_output_leaves'], 0)

    def test_an_unanswered_finish_carries_the_diagnostic_to_the_investigation(self):
        def blind(system, prompt, **k):
            if 'evidence-coverage checker' in system:
                return json.dumps({'answered': False, 'missing': [QUESTION], 'supports': []})
            return self.checker(system, prompt, **k)
        with patch.object(C, '_ask', blind):
            inv, row = self.finish()
        self.assertEqual(inv['state'], 'open')
        self.assertEqual(inv['last_review']['coverage_diagnostic'], row['coverage_diagnostic'])
        self.assertTrue(row['coverage_diagnostic'].startswith('the checker cited none of the'))

    def test_when_no_output_can_be_used_the_review_is_refused_not_run_on_nothing(self):
        with patch.object(I, '_retained_output', lambda s: (None, 0, 'retained output file missing')):
            with self.assertRaisesRegex(ValueError, 'no retained output could be reviewed'):
                self.finish()
        self.assertEqual(self.checker.prompts, [])

    def test_with_nothing_quotable_at_all_the_diagnostic_is_exact(self):
        cover = {'answered': False, 'missing': [QUESTION], 'supports': [], 'discarded_supports': []}
        self.assertEqual(C._coverage_diagnostic(cover, ({}, {}, {}, None))['coverage_diagnostic'],
                         C.NO_QUOTABLE_EVIDENCE)
        self.assertEqual(C._coverage_diagnostic(dict(cover, discarded_supports=[{'reason': 'x'}]), None), {})

    def test_a_checker_that_was_offered_the_outputs_and_cited_none_is_told_apart(self):
        cover = {'answered': False, 'missing': ['x'], 'supports': [], 'discarded_supports': []}
        addresses = {'source/summary#1': 'evidence.additional_source.records.0.result.receipt.records.0.summary',
                     'UniProt:O43511/function': 'evidence.records.0.function'}
        out = C._coverage_diagnostic(cover, ({}, {}, addresses, None))
        self.assertEqual(out['coverage_diagnostic'],
                         'the checker cited none of the 2 quotable leaves it was offered (1 from retained outputs)')

    def test_the_evidence_rules_are_unchanged_a_quote_from_elsewhere_is_still_refused(self):
        def wrong(system, prompt, **k):
            if 'evidence-coverage checker' in system:
                hit = re.search(r'\{"address":"([^"]+)","text":"[^"]*' + re.escape(QUOTE), prompt)
                return json.dumps({'answered': True, 'missing': [], 'supports': [
                    {'requirement': 'r', 'address': hit[1], 'quote': 'the STAS domain points into the membrane'}]})
            return self.checker(system, prompt, **k)
        with patch.object(C, '_ask', wrong):
            inv, row = self.finish()
        self.assertEqual(inv['state'], 'open')
        self.assertFalse(C.review_answered(row))


class UntrustedOutputs(Base):
    def test_a_changed_output_is_left_out_and_named_and_the_rest_is_reviewed(self):
        path = I._path(self.steps[1]['output_file'])
        changed = relay('reference_compare', 'the STAS domain faces the extracellular side', 'reference_compare-8SGW-1')
        C._atomic(path, changed)
        inv, row = self.finish()
        self.assertEqual(row['outputs_not_reviewed'],
                         [{'step': self.steps[1]['id'], 'output_file': self.steps[1]['output_file'],
                           'reason': 'retained output does not match its recorded sha256'}])
        self.assertNotIn('extracellular', self.checker.prompts[0])
        self.assertIn(FOLD_TEXT, self.checker.prompts[0])
        self.assertEqual(inv['state'], 'answered')

    def test_before_this_a_changed_output_failed_the_whole_review(self):
        C._atomic(I._path(self.steps[1]['output_file']), {'tampered': True})
        with self.assertRaises(ValueError):
            I.resolve({'step': self.steps[1]['id'], 'path': []}, self.steps)   # what the review used to call

    def test_a_missing_output_file_is_left_out(self):
        os.remove(I._path(self.steps[0]['output_file']))
        inv, row = self.finish()
        self.assertEqual([x['reason'] for x in row['outputs_not_reviewed']], ['retained output file missing'])
        self.assertNotIn(FOLD_TEXT, self.checker.prompts[0])
        self.assertEqual(inv['state'], 'open')     # what answered it is gone, and nothing stands in for it

    def test_per_step_and_total_bounds_hold(self):
        size = len(json.dumps(C._load(I._path(self.steps[0]['output_file']), None), sort_keys=True,
                              ensure_ascii=False).encode())
        with patch.object(I, 'REVIEW_OUTPUT_BYTES', size - 1):
            obs = I._observations(self.steps)
        self.assertEqual(obs['additional_source']['receipt']['records'], [])
        self.assertTrue(all('over the %d a review loads for one step' % (size - 1) in x['reason']
                            for x in obs['outputs_not_reviewed']))
        with patch.object(I, 'REVIEW_TOTAL_BYTES', size + 1):
            obs = I._observations(self.steps)
        self.assertEqual([r['step'] for r in obs['additional_source']['receipt']['records']], [self.steps[0]['id']])
        self.assertEqual([x['step'] for x in obs['outputs_not_reviewed']], [self.steps[1]['id']])
        self.assertIn('in all', obs['outputs_not_reviewed'][0]['reason'])
        self.assertLess(I.REVIEW_OUTPUT_BYTES, I.REVIEW_TOTAL_BYTES)


class SameReceipt(Base):
    def test_a_differently_worded_request_with_an_earlier_receipt_is_already_held(self):
        ask = Mock()
        execute = Mock(return_value={'receipt': {'receipt_id': 'cached-1', 'source': 'pubchem',
                                                 'records': [{'SMILES': 'CCO'}]}})
        for name in ('ethanol', 'ethyl alcohol', 'grain alcohol'):
            ask.return_value = json.dumps({'question': 'Is ethanol polar?', 'prediction': 'yes', 'plan': ['a'],
                                           'route': 'source', 'request': {'source': 'pubchem', 'name': name},
                                           'step_question': 'look up ' + name, 'why': 'w'})
            C._atomic(I._path('source-throttle.json'), {})
            I.turn('', ask=ask, execute=execute)
        self.assertEqual(execute.call_count, 3)                       # each was really sent
        steps = C._load(I._path('investigations.json'), {})['investigations'][0]['steps']
        self.assertEqual([s.get('same_receipt_as') for s in steps], [None, steps[0]['id'], steps[0]['id']])
        self.assertEqual([I._new_output(s) for s in steps], [True, False, False])
        # what the planner reads next
        ask.reset_mock(); ask.return_value = '{}'
        try:
            I._plan({'id': 'I-x', 'question': 'q', 'steps': steps}, '', ask)
        except Exception:
            pass
        task = json.JSONDecoder().raw_decode(ask.call_args.args[1])[0]
        held = [r for r in task['retained_outputs'] if r.get('already_held')]
        self.assertEqual([r['already_held'] for r in held], [{'as': steps[0]['id'], 'receipt': 'cached-1'}] * 2)
        self.assertEqual(task['step_budget']['new_completed_outputs'], 1)
        shown = [r for r in task['results_so_far'] if r.get('same_receipt_as')]
        self.assertTrue(shown and all(r['execution_receipt_id'] == 'cached-1' for r in shown))

    def test_the_budget_closure_does_not_count_them_as_new(self):
        steps = ([{'id': 'S-a', 'state': 'completed', 'execution_receipt_id': 'r1'}]
                 + [{'id': 'S-b%d' % n, 'state': 'completed', 'execution_receipt_id': 'r1', 'same_receipt_as': 'S-a'}
                    for n in range(9)]
                 + [{'id': 'S-c%d' % n, 'state': 'completed', 'execution_receipt_id': 'r%d' % (n + 2)} for n in range(4)])
        reason = I._budget_spent({'steps': steps})
        self.assertIn('without a finish: 5 new outputs, 0 repeats', reason)
        self.assertIn('9 returned a receipt an earlier step already held', reason)

    def test_marking_needs_a_receipt_and_leaves_repeats_to_their_own_mark(self):
        inv = {'steps': [{'id': 'S-a', 'state': 'completed', 'execution_receipt_id': None},
                         {'id': 'S-b', 'state': 'completed', 'execution_receipt_id': None},
                         {'id': 'S-c', 'state': 'completed', 'execution_receipt_id': 'r', 'repeat_within': True},
                         {'id': 'S-d', 'state': 'failed', 'execution_receipt_id': 'r'},
                         {'id': 'S-e', 'state': 'completed', 'execution_receipt_id': 'r'}]}
        self.assertIsNone(I._mark_same_receipt(inv, inv['steps'][1]))
        self.assertIsNone(I._mark_same_receipt(inv, inv['steps'][2]))
        self.assertEqual(I._mark_same_receipt(inv, inv['steps'][4]), 'S-c')   # S-c's output is held, S-d failed
        self.assertNotIn('same_receipt_as', inv['steps'][3])


class ErrorTail(unittest.TestCase):
    TQDM = ('Fetching 4 files:   0%|          | 0/4 [00:00<?, ?it/s]\rFetching 4 files:  50%|█████     | 2/4 '
            '[00:01<00:01, 1.9it/s]\rFetching 4 files: 100%|██████████| 4/4 [00:02<00:00, 1.9it/s]\n'
            + 'Loading weights: 100%|██████████| 213/213 [00:03<00:00, 70.1it/s]\n' * 4
            + 'Traceback (most recent call last):\n  File "esmc_worker.py", line 88, in <module>\n'
            '    out = model.encode(protein)\nRuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB')

    def test_progress_output_is_dropped_and_the_traceback_end_is_kept(self):
        before = ('ESMC adapter failed: ' + self.TQDM)[:300]        # the head, as it was kept
        self.assertNotIn('CUDA out of memory', before)
        kept = C.bounded_error('ESMC adapter failed: ' + self.TQDM, 300)
        self.assertLessEqual(len(kept), 300)
        self.assertTrue(kept.startswith('ESMC adapter failed:\nTraceback (most recent call last)'), kept)
        self.assertTrue(kept.endswith('RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB'), kept)
        self.assertNotIn('|██', kept)
        # the stored shape seen live: a bare bar, then the traceback cut off after seven characters
        self.assertEqual(C.without_progress('|██████████| 3/3 [00:01<00:00,  2.1it/s]\nTraceback (most recent'),
                         'Traceback (most recent')
        self.assertEqual(C.without_progress('a | b | 1/2 of the run'), 'a | b | 1/2 of the run')

    def test_a_long_error_keeps_its_start_and_its_end(self):
        text = 'source refused: ' + 'x' * 1000 + ' ValueError: the end'
        kept = C.bounded_error(text, 300)
        self.assertLessEqual(len(kept), 300)
        self.assertTrue(kept.startswith('source refused: '))
        self.assertTrue(kept.endswith('ValueError: the end'))
        self.assertEqual(C.bounded_error('short error'), 'short error')

    def test_the_esmc_adapter_drops_progress_before_its_tail(self):
        done = Mock(returncode=1, stderr=self.TQDM, stdout='')
        with patch.object(C.os.path, 'isfile', lambda p: True), patch.object(C.subprocess, 'run', return_value=done):
            with self.assertRaises(RuntimeError) as caught:
                C._embed_records([])
        self.assertNotIn('it/s', str(caught.exception))
        self.assertIn('CUDA out of memory', str(caught.exception))

    def test_a_failed_step_keeps_the_traceback_tail(self):
        steps = []
        inv = {'id': 'I-err', 'state': 'open', 'question': 'q', 'steps': steps}
        data = {'investigations': [inv]}
        C._atomic(I._path('investigations.json'), data)
        with patch.multiple(lab_lines, record_step=Mock(), advance_plan=Mock(return_value='stale')):
            row = I._carry_out(data, inv, {'route': 'representation', 'request': {'records': []}}, None, '', Mock(),
                               Mock(side_effect=RuntimeError('ESMC adapter failed: ' + self.TQDM)), False)
        self.assertEqual(row['state'], 'failed')
        self.assertIn('CUDA out of memory', row['error'])
        self.assertNotIn('it/s', row['error'])


if __name__ == '__main__':
    unittest.main()
