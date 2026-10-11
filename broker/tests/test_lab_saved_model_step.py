"""Recorded Oct 11 selection failures recover an existing, explicit assignment offline."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lab_query_perimeter import Perimeter, C, REPO, forbidden, NET
import copy, json, shutil, unittest
from datetime import datetime, timezone
from unittest.mock import patch
import lab_repeats as R
import lab_instruments as I
import lab_lines as L
import chemistry_fold_read as F

FIXTURE = REPO/'broker/tests/fixtures/saved_model_selection_20261011.json'
MODEL = 'artifacts/esmfold/O43511-60e20d840671.pdb'

class SavedModelStep(unittest.TestCase):
    def setUp(self):
        Perimeter.setUp(self)
        self.packet = json.loads(FIXTURE.read_text())
        self.line = copy.deepcopy(self.packet['line'])
        self.stack.enter_context(patch.dict(sys.modules, {'lab_lines': L, 'lab_instruments': I}))
        self.stack.enter_context(patch.object(L, 'pick', return_value=None))
        self.stack.enter_context(patch.object(L, 'open_lines', side_effect=lambda: [self.line]))
        self.stack.enter_context(patch.object(R, '_now', return_value=datetime(2026,10,11,11,5,tzinfo=timezone.utc)))
        self.stack.enter_context(patch.object(R, 'frontier_step', return_value=None))
        self.stack.enter_context(patch.object(C, 'spent_subjects', return_value=self.packet['spent']))
        self.stack.enter_context(patch.object(C, '_browse', side_effect=forbidden))
        self.stack.enter_context(patch.object(C, '_ground_inquiry', wraps=self.original_ground))
        self.assertTrue(str(I.LAB).startswith(str(Path(C.WS))))
        self.assertTrue(str(R.LOOKUPS).startswith(str(Path(C.WS))))
        target = I.LAB/MODEL; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO/'broker/tests/fixtures/O43511-60e20d840671.pdb', target)
        Path(R.LOOKUPS).write_text(''.join(json.dumps(x)+'\n' for x in self.packet['lookups']))
        self.cftr = json.loads((REPO/'broker/tests/fixtures/cftr_coverage_deferred_20261011.json').read_text())['inquiry']
        self.cftr['planning_evidence'] = C._planning_evidence(self.cftr)
        C._append(C.NOTEBOOK, {'kind':'reflection','inquiry':dict(self.cftr, coverage_deferred=True,
            refused='coverage deferred: original question exceeds context', evidence_status='insufficient'),'coverage_deferred':True})
        self.assertIsNotNone(C._held_question(self.cftr))
        C._append(C.NOTEBOOK, self.packet['events'][-1])

    original_ground = staticmethod(C._ground_inquiry)

    def inquiry(self):
        return C._inquiry({'question':self.line['question'], 'instrument_query':{
            'skill':'fold_read','operation':'structure.read','files':[MODEL],'range':[654,729],
            'question':self.line['question']}})

    def test_recorded_failures_hand_next_free_pass_the_exact_saved_step(self):
        for event in self.packet['events']:
            with self.subTest(at=event['at']):
                Path(R.LOOKUPS).write_text(''.join(json.dumps(x)+'\n' for x in self.packet['lookups']))
                C._append(C.NOTEBOOK, event)
                with patch.object(C, '_ask', side_effect=forbidden):
                    got = C._orient('offline context')
                self.assertEqual(got['question'], self.line['question'])
                self.assertEqual(got['line_id'], self.line['id'])
                self.assertEqual(got['planning_scope']['line']['next_step'], self.line['next_step'])
                self.assertEqual(got['instrument_query']['files'], [MODEL])
                self.assertEqual(got['instrument_query']['range'], [654,729])
                self.assertIsNotNone(C._held_question(self.cftr))

    def test_seven_spent_proposals_remain_rejected(self):
        for event in self.packet['events']:
            got, _ = C._held_to_plan('', '', event['inquiry'], {}, None, None, R,
                spent={'subjects':self.packet['spent']}, replan=False)
            self.assertTrue(got.get('refused'), got)

    def test_exact_action_is_consumed_once_and_hold_is_preserved(self):
        with patch.object(C, '_ask', side_effect=forbidden):
            self.assertIsNotNone(C._next_assigned_model_step(R, {'subjects':self.packet['spent']}))
            self.assertIsNone(C._next_assigned_model_step(R, {'subjects':self.packet['spent']}))
        self.assertIsNotNone(C._held_question(self.cftr))

    def test_matching_hold_or_missing_model_budget_identity_or_range_cannot_run(self):
        baseline = copy.deepcopy(self.line)
        cases = [('missing', 'fold_read 654–729 on O43511-000000000000.'),
                 ('outside', 'fold_read 700–780 on O43511-60e20d840671.'),
                 ('ambiguous', 'fold_read 654–729 on O43511-60e20d840671. Then fetch a fold.')]
        for name, step in cases:
            self.line['next_step'] = step
            self.assertIsNone(C._next_assigned_model_step(R, {}), name)
        self.line = copy.deepcopy(baseline)
        with patch.object(I, '_runs_today', return_value={'runs':[{}]*I.DAILY_RUNS}):
            self.assertIsNone(C._next_assigned_model_step(R, {}))
        self.line['question'] = self.line['question'].replace('O43511', 'Q9H0C2')
        self.assertIsNone(C._next_assigned_model_step(R, {}))
        self.line = copy.deepcopy(baseline)
        held = dict(self.inquiry(), coverage_deferred=True, refused='coverage deferred', evidence_status='insufficient')
        held['planning_evidence'] = C._planning_evidence(held)
        C._append(C.NOTEBOOK, {'kind':'reflection','inquiry':held,'coverage_deferred':True})
        self.assertIsNotNone(C._held_question(self.inquiry()))
        self.assertIsNone(C._next_assigned_model_step(R, {}))

    def test_no_eligible_work_is_idle_and_keeps_other_question_hold(self):
        (I.LAB/MODEL).unlink()
        with patch.object(C, '_ask', return_value=json.dumps(self.cftr)):
            result = C.tick()
        self.assertEqual(result['kind'], 'evidence_wait', result)
        self.assertIsNotNone(C._held_question(self.cftr))
        self.assertEqual(NET, [])

    def test_unresolved_identity_is_not_replanned_under_assignment(self):
        with patch.object(C, '_ground_inquiry', return_value={'status':'unresolved','reason':'fixture conflict'}), \
             patch.object(C, '_ask', side_effect=forbidden):
            self.assertIsNone(C._next_assigned_model_step(R, {}))

    def test_atlas_and_frontier_turns_do_not_take_assignment_recovery(self):
        proposal = self.packet['events'][0]['inquiry']
        with patch.object(C, '_next_assigned_model_step', side_effect=forbidden), \
             patch.object(C, '_ask', return_value=json.dumps(proposal)), \
             patch.object(C, 'atlas_turn_due', return_value=True):
            C._orient('offline context')
        step = {'session_id':'offline-frontier', 'next_question':'Pendrin topology', 'subjects':['O43511'], 'left':1}
        with patch.object(R, 'frontier_step', return_value=step), \
             patch.object(C, '_next_assigned_model_step', side_effect=forbidden), \
             patch.object(C, '_ask', return_value=json.dumps(proposal)), \
             patch.object(C, '_held_to_plan', return_value=(dict(proposal, refused='offline frontier wait'),{})):
            C._orient('offline context')

    def test_tick_reads_real_saved_model_then_returns_to_selection(self):
        # No subprocess/provider: the instrument boundary invokes the real pure
        # PDB reader on the copied artifact, while the daemon owns routing/state.
        calls=[]
        def runner_for(req):
            def runner(surface, skill, question, **kwargs):
                calls.append(copy.deepcopy(req))
                result = F.summary(F.read_pdb((I.LAB/MODEL).read_text()), *req['range'])
                return {'receipt':{'receipt_id':'offline-saved-model'}, 'summary':'\n'.join(result['display']), 'files':[]}
            return runner
        reflection={'answers_question':'partial: the saved prediction covers a segment, not orientation against the membrane',
                    'factual_observation':'Offline model segment read.', 'missing_evidence':'Full protein orientation.',
                    'original_question':self.line['question'], 'next_question':'', 'line_status':'continue'}
        C._atomic(C.STATE, {'phase':'orient', 'records':[{'accession':'STALE'}],
                          'additional_source':{'receipt':{'records':[{'old':'evidence'}]}},
                          'embeddings':[{'old':'embedding'}], 'atlas_analysis':{'old':'analysis'}})
        with patch.object(C, '_ask', side_effect=forbidden), \
             patch.object(I, '_compare_runner', side_effect=runner_for), \
             patch.object(C, '_reflect', return_value=reflection) as review, \
             patch.object(C, '_gather_material', return_value=False), \
             patch.object(L, 'after_reflection', return_value=''):
            kinds=[]
            for _ in range(3): kinds.append(C.tick().get('kind'))
        self.assertEqual(kinds[0], 'inquiry', kinds)
        self.assertEqual(kinds[-1], 'reflection', kinds)
        self.assertEqual(len(calls), 1, kinds)
        self.assertEqual(calls[0]['range'], [654,729])
        evidence = review.call_args.args[2]
        self.assertEqual(evidence['records'], [])
        self.assertEqual(evidence['esmc_receipts'], [])
        self.assertIsNone(evidence['atlas_analysis'])
        self.assertIn('residues 654-729', evidence['additional_source']['receipt']['records'][0]['summary'])
        self.assertEqual(C._load(C.STATE,{})['phase'], 'orient')
        self.assertIsNotNone(C._held_question(self.cftr))
        self.assertIsNone(C._next_assigned_model_step(R, {}))
        self.assertEqual(NET, [])

if __name__=='__main__': unittest.main()

