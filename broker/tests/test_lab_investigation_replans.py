#!/usr/bin/env python3
"""Why investigations never reached answers (26 October): most of every step budget went on repeating the
investigation's own steps, every reference_compare named no PDB entry, the planner's reply copied the task and named
no route, and a frontier plan's step was refused for the very request it asked for. A proposal that cannot add
anything is now re-planned once, in the same turn, before anything is sent. Scratch stores only; every sender is
blocked by the shared sandbox and nothing is executed except the stubs passed in."""
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_lines

C = sandbox.C
MODEL = 'artifacts/esmfold/O43511-ac5611395a4c.pdb'


def choice(route, request, step_question='Measure the sourced protein', question='Is the RT beside the array?'):
    return json.dumps({'route': route, 'request': request, 'step_question': step_question, 'why': 'next comparison',
                       'question': question, 'prediction': 'It is within 2 kb.', 'plan': ['inputs', 'measure']})


def store():
    return C._load(I._path('investigations.json'), {})


def notebook(kind):
    return [r for r in C._tail_jsonl(C.NOTEBOOK, nbytes=4 * 1024 * 1024) if r.get('kind') == kind]


class Base(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(Path(I._path('investigations.json')).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(Path(C.NOTEBOOK).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations': []})
        C._atomic(I._path('source-throttle.json'), {})
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=None), opened_by=Mock(return_value=None),
                                    record_step=Mock(), advance_plan=Mock(return_value='stale'))
        self.lines.start()

    def tearDown(self):
        self.lines.stop()
        sandbox.SEND.assert_not_called()


class Repeats(Base):
    def test_an_own_repeat_takes_no_step_and_the_planner_is_handed_its_output_and_asked_again(self):
        first, again = (choice('source', {'source': 'pubchem', 'name': 'fixture'}),
                        choice('source', {'source': 'pubchem', 'name': 'another'}))
        out = {'receipt': {'source': 'pubchem', 'records': [{'SMILES': 'CCO'}]}}
        execute = Mock(return_value=out)
        done = I.turn('', ask=Mock(return_value=first), execute=execute)
        ask = Mock(side_effect=[first, again])
        row = I.turn('', ask=ask, execute=execute)
        self.assertEqual(ask.call_count, 2)
        task = json.JSONDecoder().raw_decode(ask.call_args.args[1])[0]
        self.assertIn(done['id'], task['replanning']['why_not_run'])
        self.assertIn('CCO', task['replanning']['earlier_output'])      # the earlier output, handed to it
        self.assertEqual(task['replanning']['proposed'], 'source:pubchem')
        self.assertEqual(task['context'], '')
        self.assertEqual((row['state'], row.get('repeat_within'), row['request']['name']), ('completed', None, 'another'))
        inv = store()['investigations'][0]
        self.assertEqual([s['request']['name'] for s in inv['steps']], ['fixture', 'another'])   # no step spent on it
        self.assertEqual(inv['replans'], 1)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(notebook('investigation_replan')[-1]['why'], 'repeat_within')

    def test_a_planner_that_only_repeats_is_still_closed_at_the_step_budget(self):
        same = choice('source', {'source': 'pubchem', 'name': 'fixture'})
        ask, execute = Mock(return_value=same), Mock(return_value={'receipt': {'source': 'pubchem', 'records': [{}]}})
        for _ in range(I.MAX_STEPS):
            I.turn('', ask=ask, execute=execute)
        inv = store()['investigations'][0]
        self.assertEqual(inv['state'], 'stalled')
        self.assertEqual(len(inv['steps']), I.MAX_STEPS)
        self.assertTrue(inv['closed_reason'].startswith('step budget spent (14 operations)'))
        replans = min(I.MAX_REPLANS, I.MAX_STEPS - 1)            # each repeat told once, within the allowance
        self.assertEqual(inv['replans'], replans)
        execute.assert_called_once()                             # never re-sent
        self.assertEqual(ask.call_count, I.MAX_STEPS + replans)  # at most one re-plan a turn

    def test_a_repeat_refused_before_sending_with_nothing_retained_is_replanned_not_failed(self):
        ask = Mock(side_effect=[choice('source', {'source': 'ncbi', 'operation': 'protein', 'term': 'RT'}),
                                choice('source', {'source': 'pubchem', 'name': 'other'})])
        def door(route, request, *a):
            if request.get('source') == 'ncbi':
                raise ValueError('no eligible saved step: you already ran this exact lookup on 2026-10-25 09:17')
            return {'receipt': {'source': 'pubchem', 'records': [{'cid': 1}]}}
        row = I.turn('', ask=ask, execute=door)
        self.assertEqual((row['state'], row['tool']), ('completed', 'source:pubchem'))
        self.assertEqual([s['state'] for s in store()['investigations'][0]['steps']], ['completed'])
        self.assertIn('you already ran this exact lookup', json.dumps(json.JSONDecoder().raw_decode(
            ask.call_args.args[1])[0]['replanning']))

    def test_refused_again_after_the_replan_it_fails_as_before(self):
        ask = Mock(return_value=choice('source', {'source': 'ncbi', 'operation': 'protein', 'term': 'RT'}))
        door = Mock(side_effect=ValueError('no eligible saved step: you already asked this on 2026-10-22 04:04'))
        row = I.turn('', ask=ask, execute=door)
        self.assertEqual(row['state'], 'failed')
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(door.call_count, 2)                     # each refused at the door, nothing sent


class NoRoute(Base):
    ECHO = json.dumps({'question': 'Is the RT beside the array?', 'prediction': 'within 2 kb',
                       'plan': ['a', 'b', 'c'], 'context': 'the turn context, copied ' * 20})

    def test_a_reply_that_copied_the_task_is_asked_once_more_without_the_context(self):
        ask = Mock(side_effect=[self.ECHO, choice('source', {'source': 'pubchem', 'name': 'x'})])
        row = I.turn('the turn context', ask=ask, execute=lambda *a: {'receipt': {'source': 'pubchem', 'records': [{}]}})
        self.assertEqual(row['state'], 'completed')
        task = json.JSONDecoder().raw_decode(ask.call_args.args[1])[0]
        self.assertIn('context, plan, prediction, question', task['replanning'])
        self.assertEqual(task['context'], '')
        self.assertEqual(store()['investigations'][0].get('planning_failures'), 0)

    def test_still_no_route_is_refused_and_names_the_fields_it_had(self):
        row = I.turn('', ask=Mock(return_value=self.ECHO), execute=Mock())
        self.assertEqual(row['kind'], 'investigation_refused')
        self.assertEqual(row['why'], 'investigation planner returned no route (its reply had only: context, plan, '
                                     'prediction, question)')

    def test_an_unreadable_reply_is_asked_once_more(self):
        ask = Mock(side_effect=['```json\nno object at all', choice('source', {'source': 'pubchem', 'name': 'x'})])
        row = I.turn('', ask=ask, execute=lambda *a: {'receipt': {'source': 'pubchem', 'records': [{}]}})
        self.assertEqual(row['state'], 'completed')
        with self.assertRaises(C.ModelJSONError):
            I.turn('', ask=Mock(return_value='still no object'), execute=Mock())

    def test_the_contract_and_example_put_route_first(self):
        sent = []
        I._plan({'id': 'I-x', 'question': 'q', 'steps': []}, '', lambda s, p, **k: sent.append(p) or '{}')
        task = json.JSONDecoder().raw_decode(sent[0])[0]
        self.assertEqual(list(task['return'])[0], 'route')
        self.assertIn('the shape is {"route":"source","request"', sent[0])
        self.assertEqual(task['available_routes'], list(I.ROUTES))

    def test_route_shapes_the_planner_really_returns(self):
        req = {'files': [MODEL], 'range': [1, 9]}
        cases = [({'route': ['instrument'], 'request': {'skill': 'fold_read'}}, 'instrument', {'skill': 'fold_read'}),
                 ({'route': 'instrument:fold_read', 'request': req}, 'instrument', dict(req, skill='fold_read')),
                 ({'route': 'fold_read', 'request': req}, 'instrument', dict(req, skill='fold_read')),
                 ({'route': 'titrate', 'request': {'parameters': {}}}, 'experiment', {'parameters': {}, 'experiment': 'titrate'}),
                 ({'tool': 'pubmed', 'request': {'query': 'x'}}, 'pubmed', {'query': 'x'}),
                 ({'next_operation': {'route': 'source', 'request': {'source': 'pubchem', 'name': 'x'}}},
                  'source', {'source': 'pubchem', 'name': 'x'}),
                 ({'instrument_query': {'skill': 'fold_read'}}, 'instrument', {'skill': 'fold_read'}),
                 ({'request': {'source': 'uniprot', 'query': 'accession:O43511'}}, 'source',
                  {'source': 'uniprot', 'query': 'accession:O43511'}),
                 ({'request': {'reference': {'step': 'S-1', 'path': []}}}, 'read_output', {'reference': {'step': 'S-1', 'path': []}})]
        for value, route, request in cases:
            got = I._coerce_route(value)
            self.assertEqual((got['route'], got['request']), (route, request), value)
            self.assertTrue(got['_route_inferred'])
        for ambiguous in ({'route': 'source|instrument'}, {'route': ['source', 'instrument']}, {'question': 'q'},
                          {'route': 'no_such_route'}):
            self.assertEqual(I._coerce_route(ambiguous), ambiguous)
        plain = {'route': 'source', 'request': {}}
        self.assertIs(I._coerce_route(plain), plain)


class MeasurementView(Base):
    def test_a_full_prompt_still_carries_one_line_of_the_measurement_view(self):
        import lab_measurement
        view = {'contract': {'revision': 2, 'status': 'frozen', 'hypothesis': 'STAS helix 700-712 persists'},
                'disagreements': [{'a': 1}, {'b': 2}], 'big': 'x' * 400000}
        sent = []
        with patch.object(lab_measurement, 'planner_view', return_value=view):
            I._plan({'id': 'I-x', 'question': 'q', 'steps': []}, '', lambda s, p, **k: sent.append(p) or '{}')
        task = json.JSONDecoder().raw_decode(sent[0])[0]
        self.assertEqual(task['measurement'], 'frozen contract rev 2 (frozen): STAS helix 700-712 persists; '
                                              '2 open disagreement(s) between your readings to measure between')


class PlannedSteps(Base):
    def test_an_instrument_named_with_its_operation_is_the_planned_step(self):
        req = {'skill': 'fold_read', 'operation': 'structure.read', 'files': [MODEL]}
        for tool in ('fold_read.structure.read', 'fold_read structure.read', 'fold_read', 'structure.read'):
            self.assertTrue(I.plan_step_matches({'route': 'instrument', 'tool': tool}, 'instrument', req), tool)
        self.assertFalse(I.plan_step_matches({'route': 'instrument', 'tool': 'reference_compare.structure.compare'},
                                             'instrument', req))

    def test_another_operation_than_the_planned_one_is_replanned_once(self):
        planned = {'line_id': 'L-1', 'plan_id': 'P-1', 'step_index': 1, 'step_number': 2, 'route': 'experiment',
                   'tool': 'titrate'}
        wrong = json.loads(choice('source', {'source': 'bvbrc', 'operation': 'genomes', 'term': 'x'}))
        right = json.loads(choice('experiment', {'experiment': 'titrate', 'parameters': {}}))
        replies = iter([dict(wrong, _planned=planned), dict(right, _planned=planned)])
        execute = Mock(return_value={'ok': True, 'measured': 1})
        with patch.object(I, 'FRONTIER_PLANS', True), patch.object(I, '_plan', lambda *a, **k: next(replies)):
            row = I.turn('', ask=Mock(), execute=execute)
        self.assertEqual((row['state'], row['tool']), ('completed', 'experiment:titrate'))
        self.assertEqual(execute.call_args.args[0], 'experiment')
        self.assertEqual(len(store()['investigations'][0]['steps']), 1)


class ReferenceCompare(Base):
    def setUp(self):
        super().setUp()
        model = Path(C.ROOT) / MODEL
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_text('ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 90.00           C\n')

    def seed(self, pdb_ids, read=()):
        steps = []
        uni = {'id': 'S-u', 'at': '2026-10-26T00:00', 'route': 'source', 'tool': 'source:uniprot', 'question': 'record',
               'request': {'source': 'uniprot', 'query': 'accession:O43511'}}
        I._store_result(uni, {'receipt': {'source': 'uniprot', 'records': []},
                              'normalized_records': [{'accession': 'O43511', 'pdb_ids': list(pdb_ids)}]})
        steps.append(uni)
        for n, entry in enumerate(read):
            pdb = {'id': 'S-p%d' % n, 'at': '2026-10-26T00:0%d' % (n + 1), 'route': 'source', 'tool': 'source:pdb',
                   'question': 'entry', 'request': {'source': 'pdb', 'entry_id': entry}}
            I._store_result(pdb, {'receipt': {'source': 'pdb', 'records': [{'entry_id': entry}]}})
            steps.append(pdb)
        C._atomic(I._path('investigations.json'), {'investigations': [
            {'id': 'I-r', 'opened_at': '2026-10-26T00:00', 'state': 'open', 'line_id': None,
             'question': 'Does the STAS domain fold as in the deposited structure?', 'prediction': 'yes', 'plan': [],
             'steps': steps}]})

    def compare(self, **extra):
        return choice('instrument', {'instrument_query': dict({'skill': 'reference_compare', 'operation':
                      'structure.compare', 'files': [MODEL]}, **extra)}, 'Compare the model with the deposited entry')

    def test_the_one_entry_this_investigation_holds_is_the_reference(self):
        self.seed(['8SGW', '7WL2'], read=['8SGW'])
        execute = Mock(return_value={'receipt': {'source': 'instrument:reference_compare', 'records': [{'summary': 'TM 0.8'}]}})
        row = I.turn('', ask=Mock(return_value=self.compare(chain='C', ref_span=[535, 729])), execute=execute)
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(execute.call_args.args[1]['reference'], '8SGW')
        self.assertEqual(row['executed_request']['reference'], '8SGW')

    def test_of_several_entries_one_is_used_and_named_and_none_is_refused_before_execution(self):
        # 27 October (Gloria): several held entries are no longer a refusal; one is used and he is told which
        self.seed(['8SGW', '7WL2'])
        execute = Mock(return_value={'receipt': {'source': 'instrument:reference_compare', 'records': [{'summary': 'TM'}]}})
        ask = Mock(return_value=self.compare(ref_span=[535, 729]))
        row = I.turn('', ask=ask, execute=execute)
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(execute.call_args.args[1]['reference'], '8SGW')
        self.assertIn('others: 7WL2', row['resolved'])
        C._atomic(I._path('investigations.json'), {'investigations': []})
        self.seed([])
        execute = Mock(side_effect=AssertionError('nothing runs'))
        row = I.turn('', ask=ask, execute=execute)
        self.assertEqual(row['state'], 'refused_not_sent')
        self.assertIn('No PDB entry for O43511 is held here', row['error'])
        for _ in range(I.MAX_FAILED_RUN + 1):
            I.turn('', ask=ask, execute=execute)
        inv = store()['investigations'][0]
        self.assertEqual(inv['state'], 'open')                   # not "5 operations in a row produced nothing"
        self.assertEqual(I._budget_spent(inv), '')

    def test_a_missing_span_is_an_input_refusal_too(self):
        self.seed(['8SGW'])
        row = I.turn('', ask=Mock(return_value=self.compare()), execute=Mock(side_effect=AssertionError('no run')))
        self.assertEqual(row['state'], 'refused_not_sent')
        self.assertIn('ref_span must be', row['error'])
        self.assertEqual(row['executed_request']['reference'], '8SGW')

    def test_the_instrument_refuses_a_bad_compare_before_it_takes_a_daily_run(self):
        import lab_instruments
        runner = Mock(side_effect=AssertionError('never run'))
        before = len(lab_instruments._runs_today()['runs'])
        with self.assertRaisesRegex(ValueError, 'reference must be a four-character PDB entry id'):
            lab_instruments.run({'skill': 'reference_compare', 'operation': 'structure.compare', 'files': [MODEL],
                                 'question': 'Compare the model with the entry'}, runner=runner)
        self.assertEqual(len(lab_instruments._runs_today()['runs']), before)
        runner.assert_not_called()


if __name__ == '__main__': unittest.main(verbosity=2)
