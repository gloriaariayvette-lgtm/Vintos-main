#!/usr/bin/env python3
"""The Lab's spin on 29 October: about 72% of 1,851 notebook rows were the same refusal again. 699 "investigation not
opened (repeat cooldown)", one a pass for a question already resting; 359 for the RT-Cas1 line alone after its UniProt
read on taxonomy 1009004 came back empty; 527 evidence_waits ("no eligible proposal"), each after a planner call; ten
plan_not_json faults that the re-ask had already repaired; Q8IWU4, a UniProt accession, refused as a PDB ID while its
record named 6XPD; a digest that said ALL_BETTER_THAN_HARTREE_FOCK and a next question naming every family member;
and 43 investigations stalled by a missing module. Scratch stores only; the planner is a stub; nothing is sent."""
import contextlib
import io
import json
import time
import types
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_lines
import chemistry_digest as D
import requeue_stalled_lab_investigations as RQ

C = sandbox.C
PHAGE = lab_lines.STANDING[0]['question']


def rows(kind=None):
    out = C._tail_jsonl(C.NOTEBOOK, nbytes=8 * 1024 * 1024)
    return [r for r in out if kind is None or r.get('kind') == kind]


def reset_lines(**phage):
    d = lab_lines._read()
    d['lines'] = [dict(l, **phage) if l['id'] == 'L-gloria-phage-rt' else l for l in d['lines']]
    d['cycle'] = 0
    lab_lines._write(d)


class Fresh(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(Path(lab_lines.STORE).is_relative_to(sandbox.SCRATCH))
        for path in (C.NOTEBOOK, lab_lines.STORE, I._path('question-cooldown.json'), C.STATE, C.FAULTS):
            Path(path).unlink(missing_ok=True)
        for old in Path(C.ROOT).glob('investigations.json.bak-requeue-*'):
            old.unlink()
        C._atomic(I._path('investigations.json'), {'investigations': []})

    def tearDown(self):
        sandbox.SEND.assert_not_called()


class CooldownSkip(Fresh):
    def setUp(self):
        super().setUp()
        reset_lines()
        until = time.time() + 3600
        C._atomic(I._path('question-cooldown.json'), {'questions': [
            {'at': C.now_iso(), 'question': PHAGE, 'until': until, 'line_id': 'L-gloria-phage-rt',
             'line_evidence': lab_lines.inputs_key(lab_lines.get('L-gloria-phage-rt'))}]})
        self.free = patch.object(lab_lines, 'FREE_EVERY', 10 ** 9)   # every cycle a line cycle
        self.free.start()

    def tearDown(self):
        self.free.stop()
        super().tearDown()

    def test_a_line_on_cooldown_is_skipped_before_anything_is_planned_or_written(self):
        ask = Mock()
        before = len(rows())
        for _ in range(12):
            self.assertIsNone(I.turn('', ask=ask))
        ask.assert_not_called()
        self.assertEqual(len(rows()), before, rows()[before:])
        self.assertEqual(rows('investigation_not_opened'), [])

    def test_it_leaves_the_cooldown_once_when_its_time_is_out(self):
        ledger = C._load(I._path('question-cooldown.json'), {})
        ledger['questions'][0]['until'] = time.time() - 1
        C._atomic(I._path('question-cooldown.json'), ledger)
        I._cooldown_sweep()
        I._cooldown_sweep()
        ended = rows('question_cooldown_ended')
        self.assertEqual(len(ended), 1, ended)
        self.assertEqual((ended[0]['line_id'], ended[0]['why']), ('L-gloria-phage-rt', 'cooldown over'))
        self.assertEqual(C._load(I._path('question-cooldown.json'), {})['questions'], [])

    def test_it_is_looked_at_again_early_only_when_its_line_has_new_evidence(self):
        I._cooldown_sweep()
        self.assertEqual(rows('question_cooldown_ended'), [])
        lab_lines.record_step('L-gloria-phage-rt', {'question': PHAGE, 'source': 'imgvr', 'result': '',
                                                    'answered': 'no: nothing'})
        I._cooldown_sweep()
        self.assertEqual(rows('question_cooldown_ended'), [], 'an empty step is not new evidence')
        lab_lines.record_step('L-gloria-phage-rt', {'question': PHAGE, 'source': 'imgvr',
                                                    'result': 'UViG 1 carries an RT beside a CRISPR array',
                                                    'answered': 'partly'})
        I._cooldown_sweep()
        ended = rows('question_cooldown_ended')
        self.assertEqual([e['why'] for e in ended], ['evidence for its line changed'])

    def test_the_refusal_that_enters_the_cooldown_keeps_the_line_evidence(self):
        Path(I._path('question-cooldown.json')).unlink()
        inv = {'id': 'I-x', 'line_id': 'L-gloria-phage-rt'}
        data = {'investigations': [inv]}
        I._refuse_repeat(data, inv, PHAGE, {'earlier': [{'investigation': 'I-old'}]})
        row = C._load(I._path('question-cooldown.json'), {})['questions'][-1]
        self.assertEqual(row['line_evidence'], lab_lines.inputs_key(lab_lines.get('L-gloria-phage-rt')))
        self.assertEqual(len(rows('investigation_refused_repeat')), 1)


class ParkedLine(Fresh):
    def setUp(self):
        super().setUp()
        reset_lines()
        self.free = patch.object(lab_lines, 'FREE_EVERY', 10 ** 9)
        self.free.start()

    def tearDown(self):
        self.free.stop()
        super().tearDown()

    def test_an_empty_required_source_parks_the_line_once_until_its_inputs_change(self):
        reason = C._empty_source_reason('browse', {
            'kind': 'source_unavailable', 'reason': 'uniprot_returned_no_records', 'fallback_reason': None,
            'executed_query': 'taxonomy_id:1009004 AND reviewed:true'})
        self.assertIn('taxonomy_id:1009004', reason)
        self.assertTrue(lab_lines.park('L-gloria-phage-rt', reason))
        self.assertTrue(lab_lines.park('L-gloria-phage-rt', reason))      # the same inputs: no second row
        self.assertEqual(len(rows('line_parked')), 1)
        held = []
        for _ in range(5):
            self.assertIsNone(lab_lines.pick(held=held))
        self.assertEqual({l['id'] for l in held}, {'L-gloria-phage-rt'})
        self.assertEqual(rows('line_unparked'), [])
        d = lab_lines._read()
        next(l for l in d['lines'] if l['id'] == 'L-gloria-phage-rt')['next_step'] = 'Read IMG/VR for RT loci'
        lab_lines._write(d)
        self.assertEqual(lab_lines.pick()['id'], 'L-gloria-phage-rt')
        self.assertEqual([r['why'] for r in rows('line_unparked')], ['its inputs changed'])

    def test_a_parked_line_is_tried_again_after_a_day_even_unchanged(self):
        lab_lines.park('L-gloria-phage-rt', 'UniProt returned no records')
        d = lab_lines._read()
        next(l for l in d['lines'] if l['id'] == 'L-gloria-phage-rt')['parked']['recheck_after'] = time.time() - 1
        lab_lines._write(d)
        self.assertEqual(lab_lines.pick()['id'], 'L-gloria-phage-rt')
        self.assertEqual([r['why'] for r in rows('line_unparked')], ['recheck due'])

    def test_a_failure_is_not_an_empty_source(self):
        self.assertIsNone(C._empty_source_reason('browse', {'kind': 'source_unavailable', 'reason': 'HTTP 500',
                                                            'fallback_reason': 'source_rejected_generated_query'}))
        self.assertIsNone(C._empty_source_reason('sources', {'kind': 'source_unavailable', 'reason': 'timeout'}))
        self.assertIn('imgvr', C._empty_source_reason('sources', {
            'kind': 'additional_source', 'records_returned': 0, 'requested_source_unanswered': True,
            'query_sent': {'source': 'imgvr', 'term': 'reverse transcriptase CRISPR'}}))


class EvidenceWait(Fresh):
    WAIT = {'kind': 'evidence_wait', 'why': 'no eligible proposal this pass: question waiting on changed evidence'}

    def test_the_first_wait_is_written_and_the_same_again_only_lengthens_it(self):
        state, now = {}, 1000.0
        note = dict(self.WAIT)
        self.assertTrue(C._quiet_wait_note(state, note, now=now))
        self.assertEqual(note['quiet_until'], now + C.QUIET_WAIT_BASE_SECONDS)
        self.assertTrue(C._quiet_wait_holds(state, now=now + 60))
        self.assertFalse(C._quiet_wait_holds(state, now=now + C.QUIET_WAIT_BASE_SECONDS + 1))
        later = now + C.QUIET_WAIT_BASE_SECONDS + 1
        self.assertFalse(C._quiet_wait_note(state, dict(self.WAIT, why='another held proposal'), now=later))
        self.assertEqual(state['quiet_wait']['until'], later + 2 * C.QUIET_WAIT_BASE_SECONDS)
        for n in range(10):
            C._quiet_wait_note(state, dict(self.WAIT), now=later)
        self.assertEqual(state['quiet_wait']['until'], later + C.QUIET_WAIT_MAX_SECONDS)
        self.assertEqual(rows(), [])
        C._quiet_wait_end(state, 'a question was admitted')
        C._quiet_wait_end(state, 'a question was admitted')
        ended = rows('evidence_wait_ended')
        self.assertEqual(len(ended), 1)
        self.assertEqual(ended[0]['passes_ending_the_same_way'], 12)
        self.assertNotIn('quiet_wait', state)

    def test_new_evidence_rechecks_early_but_not_every_pass(self):
        state, now = {}, 1000.0
        C._quiet_wait_note(state, dict(self.WAIT), now=now)
        Path(C.ROOT, 'source-receipts.jsonl').write_text('{"receipt_id": "new"}\n')
        self.assertTrue(C._quiet_wait_holds(state, now=now + 10), 'new evidence, but it was just checked')
        self.assertFalse(C._quiet_wait_holds(state, now=now + C.QUIET_WAIT_RECHECK_SECONDS + 1))
        Path(C.ROOT, 'source-receipts.jsonl').unlink()

    def test_a_single_refusal_holds_nothing_and_ends_without_a_row(self):
        state = {}
        note = {'kind': 'inquiry_refused', 'why': 'repeat: spent subject: SLC36A4'}
        self.assertTrue(C._quiet_wait_note(state, note, now=1000.0))
        self.assertFalse(C._quiet_wait_holds(state, now=1000.5))
        self.assertFalse(C._quiet_wait_note(state, dict(note), now=1001.0))     # the same refusal again: counted
        self.assertTrue(C._quiet_wait_holds(state, now=1002.0))
        self.assertTrue(C._quiet_wait_note(state, {'kind': 'inquiry_refused', 'why': 'something else'}, now=1003.0))
        self.assertEqual(len(rows('evidence_wait_ended')), 1)                   # the repeated one ended, said once
        C._quiet_wait_end(state, 'a question was admitted')
        self.assertEqual(len(rows('evidence_wait_ended')), 1)

    def test_the_lab_turn_plans_once_and_writes_once_while_it_waits(self):
        held = {'refused': 'no eligible proposal this pass: question waiting on changed evidence: repeat: x',
                'planning_wait': True, 'question': 'What links SLC36A3 and SLC36A4?'}
        orient = Mock(return_value=held)
        admit = types.ModuleType('compute_admission')
        admit.admit = lambda *a, **k: contextlib.nullcontext()
        cfg = dict(C.config(), enabled=True, forge_report_intake=False)
        with patch.dict(sys.modules, {'compute_admission': admit}), \
                patch.object(C, 'config', return_value=cfg), patch.object(C, '_orient', orient), \
                patch.object(C, 'lab_context', return_value=('', {'context_sha256': 'x'})), \
                patch.object(C, 'rotate_source_receipts', return_value=None), \
                patch.object(I, 'turn', return_value=None):
            kinds = [C.tick().get('kind') for _ in range(8)]
            self.assertEqual(orient.call_count, 1, kinds)
            self.assertEqual(kinds, ['evidence_wait'] + ['quiet_wait'] * 7)
            self.assertEqual(len(rows('evidence_wait')), 1)
            state = C._load(C.STATE, {})
            state['quiet_wait']['until'] = time.time() - 1
            C._atomic(C.STATE, state)
            self.assertEqual(C.tick().get('kind'), 'evidence_wait')            # the backoff is out: planned again
            self.assertEqual((orient.call_count, len(rows('evidence_wait'))), (2, 1))
            self.assertEqual(C._load(C.STATE, {})['quiet_wait']['passes'], 2)


class PlannerJSON(Fresh):
    GOOD = json.dumps({'browse_lane': 'protein', 'question': 'What is the fold of human ISCU?'})

    def faults(self):
        return [json.loads(l) for l in open(C.FAULTS)] if Path(C.FAULTS).exists() else []

    def test_a_repaired_reply_is_not_a_fault(self):
        replies = ['Here is my answer, in prose.', self.GOOD]
        ask = Mock(side_effect=lambda *a, **k: replies.pop(0))
        with patch.object(C, '_ask', ask):
            self.assertEqual(C._plan('Return JSON only.', 'TASK')['browse_lane'], 'protein')
        self.assertEqual(ask.call_count, 2)
        self.assertIn('the parser said: model returned no JSON object', ask.call_args.args[1])
        self.assertEqual([f for f in self.faults() if f['stage'] == 'plan_not_json'], [])

    def test_a_reply_unreadable_after_the_repair_is_one_fault(self):
        ask = Mock(return_value='prose again')
        with patch.object(C, '_ask', ask), self.assertRaises(C.ModelJSONError):
            C._plan('Return JSON only.', 'TASK')
        self.assertEqual(ask.call_count, 2)
        bad = [f for f in self.faults() if f['stage'] == 'plan_not_json']
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0]['repair_attempted'] and bad[0]['prompt_chars'])


class AccessionAsPDB(unittest.TestCase):
    def test_an_accession_is_mapped_through_its_records_pdb_cross_references(self):
        records = [{'accession': 'Q8IWU4', 'pdb_ids': ['6XPD', '6XPE']}]
        lineage, why = C._sourced_followup({'source': 'pdb', 'entry_id': 'Q8IWU4'}, records)
        self.assertIsNone(why)
        self.assertEqual((lineage['id'], lineage['mapped_from_accession'], lineage['other_entries']),
                         ('6XPD', 'Q8IWU4', ['6XPE']))

    def test_refused_only_when_that_record_has_none(self):
        lineage, why = C._sourced_followup({'source': 'pdb', 'entry_id': 'Q8IWU4'},
                                           [{'accession': 'Q8IWU4', 'pdb_ids': []}])
        self.assertIsNone(lineage)
        self.assertIn('no PDB cross-references', why)
        lineage, why = C._sourced_followup({'source': 'pdb', 'entry_id': 'P12345'},
                                           [{'accession': 'Q8IWU4', 'pdb_ids': ['6XPD']}])
        self.assertIsNone(lineage)
        self.assertIn('absent', why)


class NextQuestion(unittest.TestCase):
    def test_a_family_question_names_three_and_counts_the_rest(self):
        absent = ['SLC36A%d' % n for n in range(1, 12)]
        step = C._absent_targets_step(absent, {})
        self.assertIn('SLC36A1, SLC36A2, SLC36A3 and 8 other family members', step)
        self.assertNotIn('established target', step)
        self.assertNotIn('SLC36A4', step)
        step = C._absent_targets_step(['SLC36A4'], {'SLC36A3': 'Q495N2'})
        self.assertIn('Retrieve SLC36A4 together with SLC36A3 (Q495N2)', step)
        self.assertLess(len(C._absent_targets_step(absent * 5, {'A': 'P1'})), 300)

    def test_the_digest_says_the_verdict_as_a_sentence_and_clips_questions(self):
        self.assertEqual(D.accuracy_sentence('ALL_BETTER_THAN_HARTREE_FOCK'),
                         'every point came in below Hartree-Fock, so some correlation energy was recovered')
        out = D._recent_questions([{'next_question': 'Q ' * 400}], [], 1)
        self.assertLessEqual(len(out[0]), D.QUESTION_CHARS + 1)


class Requeue(Fresh):
    def fixture(self):
        lab_names = "3 turns in a row failed before any step: ModuleNotFoundError: No module named 'lab_names'"
        return {'investigations': [
            {'id': 'I-a', 'state': 'stalled', 'opened_at': '2026-10-29T05:31:00+00:00', 'planning_failures': 3,
             'closed_reason': lab_names, 'last_planning_error': "ModuleNotFoundError: No module named 'lab_names'",
             'question': '', 'steps': []},
            {'id': 'I-b', 'state': 'stalled', 'opened_at': '2026-10-29T06:00:00+00:00', 'planning_failures': 3,
             'closed_reason': lab_names, 'deferred_until': 5, 'question': 'q', 'steps': [{'id': 'S-1'}]},
            {'id': 'I-c', 'state': 'stalled', 'opened_at': '2026-10-29T07:00:00+00:00', 'planning_failures': 3,
             'closed_reason': "3 turns in a row failed before any step: ModuleNotFoundError: No module named 'other'"},
            {'id': 'I-d', 'state': 'stalled', 'closed_reason': '3 turns in a row failed before any step: '
                                                               'investigation planner returned no route'},
            {'id': 'I-e', 'state': 'unanswered', 'closed_reason': lab_names},
        ]}

    def run_quiet(self, **kw):
        buf = io.StringIO()
        out = RQ.run(out=lambda s: buf.write(s + '\n'), **kw)
        return out, buf.getvalue()

    def test_dry_run_counts_and_changes_nothing(self):
        C._atomic(I._path('investigations.json'), self.fixture())
        before = Path(I._path('investigations.json')).read_bytes()
        out, text = self.run_quiet()
        self.assertEqual((out['stalled'], out['stalled_by_lab_names'], out['would_reopen'], out['reopened']), (4, 2, 2, 0))
        self.assertIn('dry run', text)
        self.assertEqual(Path(I._path('investigations.json')).read_bytes(), before)
        self.assertEqual(list(Path(C.ROOT).glob('investigations.json.bak-requeue-*')), [])

    def test_apply_reopens_only_the_lab_names_stalls_once_with_a_backup(self):
        C._atomic(I._path('investigations.json'), self.fixture())
        out, _ = self.run_quiet(apply=True)
        self.assertEqual(out['reopened'], 2)
        self.assertTrue(Path(out['backup']).exists())
        by = {i['id']: i for i in C._load(I._path('investigations.json'), {})['investigations']}
        for iid in ('I-a', 'I-b'):
            self.assertEqual((by[iid]['state'], by[iid]['planning_failures']), ('open', 0))
            self.assertNotIn('closed_reason', by[iid])
            self.assertNotIn('deferred_until', by[iid])
            self.assertIn('lab_names', by[iid]['requeued']['closed_reason'])
        self.assertEqual(by['I-b']['steps'], [{'id': 'S-1'}])
        self.assertEqual([by[i]['state'] for i in ('I-c', 'I-d', 'I-e')], ['stalled', 'stalled', 'unanswered'])
        again, _ = self.run_quiet(apply=True)
        self.assertEqual(again['reopened'], 0)
        self.assertEqual(len(rows('investigations_requeued')), 1)

    def test_a_store_that_changed_underneath_is_not_written(self):
        C._atomic(I._path('investigations.json'), self.fixture())
        real = RQ._digest
        calls = []
        def moving(path):
            calls.append(path)
            return real(path) if len(calls) == 1 else 'changed'
        with patch.object(RQ, '_digest', moving):
            out, text = self.run_quiet(apply=True)
        self.assertTrue(out.get('changed_underneath'))
        self.assertIn('nothing written', text)
        self.assertEqual({i['state'] for i in C._load(I._path('investigations.json'), {})['investigations']
                          if i['id'] in ('I-a', 'I-b')}, {'stalled'})


if __name__ == '__main__': unittest.main(verbosity=2)
