#!/usr/bin/env python3
"""Naming the operation, and being told no (26 October). After the day's 25th instrument run the planner was shown no
instrument at all, and 42 of her instrument requests that evening named one from memory under keys of her own; 24
more were "unknown route" for a connector or a source named as the route. Now the exact names are always in front of
her, an unambiguous near-miss is read as what it names, and a name the Lab does not have is told to her with the exact
choices and asked again in the same turn: it is a step only if that answer is not a real operation either. Scratch
stores only; every sender is blocked by the shared sandbox and nothing runs except the stubs passed in."""
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_instruments
import lab_lines
from lab_tool_calls import normalize_instrument, canonical

C = sandbox.C
MODEL = 'artifacts/esmfold/O43511-ac5611395a4c.pdb'


def choice(route, request, step_question='Read the model over the STAS window'):
    return json.dumps({'route': route, 'request': request, 'step_question': step_question, 'why': 'next',
                       'question': 'Is the STAS fold kept?', 'prediction': 'yes', 'plan': ['read']})


def store():
    return C._load(I._path('investigations.json'), {})


def notebook(kind):
    return [r for r in C._tail_jsonl(C.NOTEBOOK, nbytes=4 * 1024 * 1024) if r.get('kind') == kind]


def task_of(ask):
    return json.JSONDecoder().raw_decode(ask.call_args.args[1])[0]


class Base(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(Path(lab_instruments.LEDGER).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations': []})
        C._atomic(I._path('source-throttle.json'), {})
        model = Path(C.ROOT) / MODEL
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_text('ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 90.00           C\n')
        if Path(lab_instruments.LEDGER).exists():
            Path(lab_instruments.LEDGER).unlink()
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=None), opened_by=Mock(return_value=None),
                                    record_step=Mock(), advance_plan=Mock(return_value='stale'))
        self.lines.start()

    def tearDown(self):
        self.lines.stop()
        sandbox.SEND.assert_not_called()

    def use_up_runs(self):
        lab_instruments.LEDGER.write_text(json.dumps({'date': lab_instruments._runs_today()['date'],
                                                      'runs': [{'skill': 'fold_read'}] * lab_instruments.DAILY_RUNS}))


class TheListIsInFrontOfHer(Base):
    def test_the_planner_sees_the_exact_skill_names_operations_and_files(self):
        menu = I._menu()['instruments']
        self.assertEqual(menu['runs_left_today'], lab_instruments.DAILY_RUNS)
        self.assertEqual(menu['skills']['fold_read']['operations'], ['structure.read'])
        self.assertEqual(menu['skills']['fold_read']['files'], [MODEL])
        self.assertIn('structure.analyze', menu['skills']['structure_viewer']['operations'])
        self.assertIn('skill', menu['request'])

    def test_with_no_run_left_it_says_so_and_still_names_them(self):
        self.use_up_runs()
        self.assertEqual(lab_instruments.menu_block(), '')            # the orient prompt's block, as before
        menu = I._menu()['instruments']
        self.assertEqual(menu['runs_left_today'], 0)
        self.assertIn('No instrument run is left today', menu['state'])
        self.assertIn('fold_read', menu['skills'])

    def test_the_compact_menu_keeps_the_names(self):
        sent = []
        with patch.object(C, '_plan_chars', return_value=9000):
            I._plan({'id': 'I-x', 'question': 'q', 'steps': []}, '', lambda s, p, **k: sent.append(p) or '{}')
        task = json.JSONDecoder().raw_decode(sent[0])[0]
        self.assertIn('routes', task['tools'])
        self.assertEqual(task['tools']['instruments']['skills']['fold_read'], ['structure.read'])


class NearMisses(Base):
    def test_unambiguous_near_misses_are_read_as_what_they_name(self):
        cases = [({'instrument': 'fold_read', 'files': [MODEL]}, 'fold_read', 'structure.read'),
                 ({'instrument': 'Fold-Read', 'artifact': MODEL}, 'fold_read', 'structure.read'),
                 ({'fold_read': {'files': [MODEL], 'range': [1, 9]}}, 'fold_read', 'structure.read'),
                 ({'skill': 'structure viewer', 'operation': 'analyze', 'files': [MODEL]}, 'structure_viewer',
                  'structure.analyze'),
                 ({'instrument': 'structure.analyze', 'files': [MODEL]}, 'structure_viewer', 'structure.analyze'),
                 ({'skill': 'fold_read', 'structure_id': 'O43511'}, 'fold_read', 'structure.read')]
        for request, skill, op in cases:
            got = normalize_instrument(request)
            self.assertEqual((got.get('skill'), got.get('operation')), (skill, op), request)
            self.assertEqual(got.get('files'), [MODEL], request)

    def test_nothing_is_guessed_between_candidates(self):
        got = normalize_instrument({'instrument': 'structure_viewer', 'files': [MODEL]})
        self.assertEqual((got.get('skill'), got.get('operation')), ('structure_viewer', None))   # three operations
        got = normalize_instrument({'operation': 'structure_viewer'})
        self.assertEqual((got.get('skill'), got.get('operation')), ('structure_viewer', None))
        self.assertIsNone(canonical('viewer', ['structure_viewer', 'sequence_viewer']))
        got = normalize_instrument({'skill': 'fold_read', 'artifact': 'artifacts/esmfold/not-listed.pdb'})
        self.assertNotIn('files', got)

    def test_the_protein_design_heading_is_unwrapped(self):
        call = {'tool': 'predict_structure_boltz', 'sequence': 'ACDEFGHIKLMNPQRSTVWY', 'source_receipt_id': 'a' * 64}
        self.assertEqual(normalize_instrument({'protein_design_mcp': call}), call)

    def test_routes_the_planner_really_wrote(self):
        cases = [({'route': 'sources', 'request': {'pubmed': 'x'}}, 'source'),
                 ({'route': 'Read-Output', 'request': {'reference': {'step': 'S-1', 'path': []}}}, 'read_output'),
                 ({'route': 'boltz', 'request': {'boltz_estimate_structure_and_binding': {'sequences': ['A']}}}, 'plugin'),
                 ({'route': 'genomic_intelligence', 'request': {'operation': 'predict_enhancer', 'region': 'x'}}, 'plugin'),
                 ({'route': 'account', 'request': {'tool': 'boltz.boltz_get_account_context'}}, 'plugin')]
        for value, route in cases:
            got = I._coerce_route(value)
            self.assertEqual(got['route'], route, value)
        got = I._coerce_route(cases[2][0])
        self.assertEqual(got['request'], {'plugin': 'boltz', 'tool': 'boltz.boltz_estimate_structure_and_binding',
                                          'arguments': {'sequences': ['A']}})
        got = I._coerce_route(cases[3][0])
        self.assertEqual((got['request']['tool'], got['request']['arguments']),
                         ('genomic_intelligence.predict_enhancer', {'region': 'x'}))
        for unknown in ({'route': 'reflect', 'request': {}},
                        {'route': 'nvidia_nim', 'request': {'operation': 'boltz2.boltz_estimate_structure_and_binding'}}):
            self.assertEqual(I._coerce_route(unknown), unknown)

    def test_an_instrument_request_that_names_only_a_source_or_experiment_goes_there(self):
        self.assertEqual(I._other_door({'source': 'pdb', 'entry_id': '8SGW', 'operation': 'structure_evidence'})[0],
                         'source')
        self.assertEqual(I._other_door({'experiment': 'protein', 'parameters': {}})[0], 'experiment')
        self.assertIsNone(I._other_door({'skill': 'fold_read', 'source': 'pdb'}))
        self.assertIsNone(I._other_door({'source': 'local', 'operation': 'structure_viewer'}))


if __name__ == '__main__': unittest.main(verbosity=2)
