#!/usr/bin/env python3
"""The frontier-plan executor credits a planned step only for the operation that step requires (review of
7d2c897: a planned ESMFold step was marked done after a PubChem lookup, and a step whose prerequisite was skipped
was still offered). Offline: the planner model and every execution are stubs, every store is scratch, and
nothing leaves the machine."""
import json
import unittest
from unittest.mock import Mock, patch

import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_lines as L

C = sandbox.C


def choice(route, request):
    return json.dumps({'question': 'Q', 'prediction': 'P', 'plan': ['step'], 'route': route, 'request': request,
                       'step_question': 'one measurement', 'why': 'feeds the next step'})


OK = {'receipt': {'source': 'pubchem', 'records': [{'smiles': 'CCO'}]}}


class FrontierPlanExecutor(unittest.TestCase):
    def setUp(self):
        self.assertTrue(str(L.STORE).startswith(str(sandbox.SCRATCH)))      # her real lines are never touched
        self.assertTrue(str(C.ROOT).startswith(str(sandbox.SCRATCH)))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)          # and nothing can be sent
        C._atomic(I._path('investigations.json'), {'investigations': []})
        C._atomic(L.STORE, {'lines': []})
        self.record = patch.object(L, 'record_step', Mock()); self.record.start()
        self.on = patch.object(I, 'FRONTIER_PLANS', True); self.on.start()
        self.line = L.opened_by('Plan test line', 'Does a fold of this protein match its known structure?', 'test')
        self.ask = Mock()

    def tearDown(self):
        self.on.stop(); self.record.stop()
        sandbox.SEND.assert_not_called()

    def plan(self, steps):
        L.set_plan(self.line['id'], steps, 'test')
        C._atomic(I._path('investigations.json'), {'investigations': [
            {'id': 'I-t', 'opened_at': 't', 'state': 'open', 'line_id': self.line['id'], 'question': 'Q',
             'prediction': 'P', 'steps': []}]})

    def live(self):
        return L.get(self.line['id'])

    def last_step(self):
        return C._load(I._path('investigations.json'), {})['investigations'][0]['steps'][-1]

    def test_a_successful_wrong_tool_is_not_run_and_earns_no_credit(self):
        self.plan([{'objective': 'Fold the candidate', 'route': 'instrument', 'tool': 'esmfold'}])
        self.ask.return_value = choice('source', {'source': 'pubchem', 'name': 'ethanol'})
        execute = Mock(return_value=OK)
        I.turn('', ask=self.ask, execute=execute)
        execute.assert_not_called()                                           # the lookup is not run in its place
        step = self.last_step()
        self.assertEqual(step['state'], 'failed')
        self.assertIn('requires instrument/esmfold', step['error'])
        planned = self.live()['plan'][0]
        self.assertEqual((planned['state'], planned['fails']), ('pending', 1))

    def test_a_matching_retained_result_advances_and_names_its_output(self):
        self.plan([{'objective': 'Get the molecule', 'route': 'source', 'tool': 'pubchem'},
                   {'objective': 'Measure similarity', 'route': 'plugin', 'tool': 'nvmolkit.similarity',
                    'depends_on': 'step 1'}])
        self.ask.return_value = choice('source', {'source': 'pubchem', 'name': 'ethanol'})
        I.turn('', ask=self.ask, execute=Mock(return_value=OK))
        step, first = self.last_step(), self.live()['plan'][0]
        self.assertEqual(step['plan_credit'], 'done')
        self.assertEqual((first['state'], first['outcome'], first['result_step']),
                         ('done', 'operation_completed', step['id']))  # the operation completed; no finding claimed
        nxt = L.plan_for_planner(self.live())
        self.assertEqual(nxt['step_number'], 2)
        self.assertEqual(nxt['inputs_from'], [{'step_number': 1, 'investigation_step': step['id']}])

    def test_a_skipped_prerequisite_blocks_its_dependent_but_not_unrelated_work(self):
        self.plan([{'objective': 'Fold', 'route': 'instrument', 'tool': 'esmfold'},
                   {'objective': 'Compare the fold', 'route': 'instrument', 'tool': 'reference_compare',
                    'depends_on': 'the model from step 1'},
                   {'objective': 'An independent lookup', 'route': 'source', 'tool': 'pubchem'}])
        pid = L.plan_id(self.live())
        self.assertEqual(L.advance_plan(self.line['id'], pid, 0, completed=False), 'pending')
        self.assertEqual(L.advance_plan(self.line['id'], pid, 0, completed=False), 'skipped')
        plan = self.live()['plan']
        self.assertEqual([s['state'] for s in plan], ['skipped', 'blocked', 'pending'])
        self.assertNotIn('result_step', plan[1])                              # nothing is invented for it
        self.assertEqual(L.plan_for_planner(self.live())['step_number'], 3)

    def test_a_plan_replaced_during_an_attempt_takes_no_credit_from_it(self):
        self.plan([{'objective': 'Get the molecule', 'route': 'source', 'tool': 'pubchem'}])
        replacement = [{'objective': 'Fold instead', 'route': 'instrument', 'tool': 'esmfold'}]
        def execute(*a):
            L.set_plan(self.line['id'], replacement, 'frontier')               # the frontier re-plans mid-attempt
            return OK
        self.ask.return_value = choice('source', {'source': 'pubchem', 'name': 'ethanol'})
        I.turn('', ask=self.ask, execute=execute)
        self.assertEqual(self.last_step()['plan_credit'], 'stale')
        new = self.live()['plan'][0]
        self.assertEqual((new['objective'], new['state'], new['fails']), ('Fold instead', 'pending', 0))

    def test_an_unknown_outcome_is_neither_credit_nor_failure(self):
        self.plan([{'objective': 'Get the molecule', 'route': 'source', 'tool': 'pubchem'}])
        self.ask.return_value = choice('source', {'source': 'pubchem', 'name': 'ethanol'})
        I.turn('', ask=self.ask, execute=Mock(side_effect=TimeoutError('timed out after send')))
        self.assertEqual(self.last_step()['state'], 'outcome_unknown')
        self.assertNotIn('plan_credit', self.last_step())
        first = self.live()['plan'][0]
        self.assertEqual((first['state'], first['fails']), ('pending', 0))

    def test_disabled_the_lab_runs_as_before_and_the_plan_is_untouched(self):
        self.plan([{'objective': 'Fold the candidate', 'route': 'instrument', 'tool': 'esmfold'}])
        self.ask.return_value = choice('source', {'source': 'pubchem', 'name': 'ethanol'})
        execute = Mock(return_value=OK)
        with patch.object(I, 'FRONTIER_PLANS', False):
            I.turn('', ask=self.ask, execute=execute)
        execute.assert_called_once()
        self.assertNotIn('plan_ref', self.last_step())
        self.assertNotIn('planned_step', self.ask.call_args.args[1])
        first = self.live()['plan'][0]
        self.assertEqual((first['state'], first['fails']), ('pending', 0))

    def test_matching_reads_the_request_not_the_wording(self):
        ref = lambda r, t: {'route': r, 'tool': t}
        self.assertTrue(I.plan_step_matches(ref('source', 'ncbi.literature'), 'source', {'source': 'ncbi', 'operation': 'literature'}))
        self.assertFalse(I.plan_step_matches(ref('source', 'ncbi.literature'), 'source', {'source': 'ncbi', 'operation': 'protein'}))
        self.assertTrue(I.plan_step_matches(ref('imgvr', ''), 'source', {'source': 'imgvr', 'operation': 'protein_similarity'}))
        self.assertTrue(I.plan_step_matches(ref('plugin', 'nvmolkit.similarity'), 'plugin', {'plugin': 'nvmolkit', 'tool': 'similarity'}))
        self.assertFalse(I.plan_step_matches(ref('instrument', 'esmfold'), 'source', {'source': 'pubchem'}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
