#!/usr/bin/env python3
"""Offline characterization, not a production fix. Run directly with python3 -B.

Real orient/plan/narrow/inquiry/held gate/repeat code; only model responses,
identity resolution and unrelated work queues/menus are scripted. No live state.
"""
import contextlib
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import urllib.request

REPO = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / 'scripts'))
_write_root = None


def audit(event, args):
    """Fail closed even if a later import introduces an un-repointed store."""
    if _write_root is None:
        return
    if event in ('socket.connect', 'socket.sendto', 'subprocess.Popen', 'os.system'):
        raise AssertionError('external action forbidden: ' + event)
    paths = []
    if event == 'open':
        path, mode, flags = args
        if (flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            paths = [path]
    elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.truncate'):
        paths = [args[0]]
    elif event in ('os.rename', 'os.link', 'os.symlink'):
        paths = list(args[:2])
    for path in paths:
        if isinstance(path, int):
            continue
        if not Path(os.fsdecode(path)).resolve().is_relative_to(_write_root):
            raise AssertionError('write outside scratch HOME: ' + str(path))


sys.addaudithook(audit)


def proposal(name='KaiC', question=None, **extra):
    return dict(browse_lane='protein',
                question=question or ('What function is annotated for %s?' % name),
                uniprot_query='protein_name:"%s" AND reviewed:true' % name,
                source_query=None, plugin_query=None, **extra)


class Replay(unittest.TestCase):
    def setUp(self):
        global _write_root
        self.tmp = tempfile.TemporaryDirectory(prefix='lab-refusals-replay-')
        self.root = Path(self.tmp.name).resolve()
        _write_root = self.root
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.dict(os.environ, {
            'HOME': str(self.root), 'SPARK_WORKSPACE': str(self.root / '.vintos/workspace'),
            'VINTOS_ELIOT_REQUIRED': '0'}))
        self.no_send = Mock(side_effect=AssertionError('sender/network/process forbidden'))
        for obj, attr in ((socket.socket, 'connect'), (socket.socket, 'connect_ex'),
                          (socket.socket, 'sendto'), (socket, 'create_connection'),
                          (urllib.request, 'urlopen'), (subprocess, 'Popen'), (os, 'system')):
            self.stack.enter_context(patch.object(obj, attr, self.no_send))
        # Never import a provider/sender to obtain its real client.
        mocks = {name: types.SimpleNamespace(**{attr: self.no_send for attr in
                 ('get', 'post', 'request', 'Session', 'Client', 'OpenAI', 'Anthropic', 'send', 'deliver', 'ntfy')})
                 for name in ('requests', 'httpx', 'openai', 'anthropic', 'deliver', 'ntfy')}
        for name, attrs in {
            'plugin_catalog': {'prompt_instructions': lambda *a: ''},
            'claude_connector_catalog': {'prompt_instructions': lambda *a: ''},
            'lab_genome_mining': {'campaign_instructions': lambda: ''},
            'lab_instruments': {'menu_block': lambda: ''},
            'lab_keepers': {'block': lambda **k: ''},
            'lab_asks': {'block': lambda: ''},
        }.items():
            mocks[name] = types.SimpleNamespace(**attrs)
        self.stack.enter_context(patch.dict(sys.modules, mocks))
        # Reload to bind every module store to this test's HOME before executing it.
        for name in ('chemistry_lab', 'lab_repeats', 'lab_lines', 'lab_sources', 'lab_claim_evidence'):
            module = importlib.import_module(name)
            importlib.reload(module)
        self.C = sys.modules['chemistry_lab']
        self.R = sys.modules['lab_repeats']
        self.L = sys.modules['lab_lines']
        self.stack.enter_context(patch.object(self.C, '_eliot', None))
        self.stack.enter_context(patch.object(self.L, 'STANDING', []))
        for name in ('_next_assigned_archive_step', '_next_assigned_model_step',
                     '_next_fitting_deferred_coverage', '_next_sourced_record', '_next_evidence_work',
                     '_strategy_change', '_planning_hold'):
            self.stack.enter_context(patch.object(self.C, name, return_value=None))
        self.stack.enter_context(patch.object(self.C, '_ground_inquiry', return_value={'status': 'not_applicable'}))
        self.stack.enter_context(patch.object(self.C, '_existing_model_read', side_effect=lambda x: x))
        self.stack.enter_context(patch.object(self.C, '_on_line', side_effect=lambda x, *a: x))
        self.stack.enter_context(patch.object(self.C, 'atlas_turn_due', return_value=False))
        self.stack.enter_context(patch.object(self.C, '_atlas_scorer_hint', return_value=''))
        self.stack.enter_context(patch.object(self.R, 'frontier_step', return_value=None))
        self.ask = self.stack.enter_context(patch.object(self.C, '_ask', side_effect=AssertionError('unscripted model')))
        Path(self.C.ROOT).mkdir(parents=True, exist_ok=True)
        self.C.remember_spent(['KaiC'])
        self.assertTrue(all(Path(p).is_relative_to(self.root) for p in
            (self.C.ROOT, self.C.SPENT, self.C.STATE, self.C.NOTEBOOK, self.C.QUESTION_EDITS,
             self.C.RECEIPTS, self.C.FAULTS, self.C.ELIOT_LOG, self.R.LOOKUPS, self.L.STORE, self.L.LOCK)))
        self.assertIs(socket.socket.connect, self.no_send)
        self.assertIs(urllib.request.urlopen, self.no_send)
        self.assertIs(sys.modules['requests'].post, self.no_send)
        self.assertIs(self.C._ask, self.ask)

    def tearDown(self):
        global _write_root
        try:
            self.no_send.assert_not_called()
        finally:
            self.stack.close()
            _write_root = None
            self.tmp.cleanup()

    def script(self, *answers):
        self.ask.side_effect = [json.dumps(a) if isinstance(a, dict) else a for a in answers]

    def ledger(self):
        return self.C._jsonl(self.R.LOOKUPS)

    def test_01_main_spent_path_has_three_calls_one_terminal_refusal(self):
        self.script(proposal(), proposal(), proposal())
        got = self.C._orient('offline empty context')
        self.assertIn('repeat: spent subject:', got['refused'])
        self.assertEqual(self.ask.call_count, 3)
        self.assertEqual(len(self.ledger()), 1)
        prompts = [c.args[1] for c in self.ask.call_args_list]
        self.assertTrue(all('SPENT FOR TODAY' in p and 'KaiC' in p for p in prompts))
        self.assertIn('You chose a spent subject again', prompts[1])
        self.assertIn('REFUSED, IT IS A REPEAT', prompts[2])
        self.assertIn('Ask ONE thing', prompts[0])
        self.assertIn('Include three claim types', prompts[0])
        print('MEASURE main: 3 planner calls, 1 logged refusal; spent list in all 3 prompts')

    def test_02_json_repair_doubles_main_calls(self):
        self.script('prose', proposal(), 'prose', proposal(), 'prose', proposal())
        self.assertIn('spent subject:', self.C._orient('offline')['refused'])
        self.assertEqual(self.ask.call_count, 6)

    def test_03_fresh_path_omits_spent_list_and_requests_three_claims(self):
        self.script(proposal(), proposal(), proposal())
        got = self.C._fresh_free_inquiry(self.R, {'subjects': ['KaiC']})
        self.assertFalse(got.get('refused'))
        self.assertEqual(self.ask.call_count, 3)
        self.assertEqual(sum(bool(r.get('refused')) for r in self.ledger()), 3)
        for c in self.ask.call_args_list:
            self.assertNotIn('KaiC', c.args[1])
            self.assertNotIn('SPENT FOR TODAY', c.args[1])
            self.assertIn('source-backed relationship', c.args[1])
        print('MEASURE fresh: 3 planner calls, 3 lookup-ledger refusals, fixed-queue acceptance; no spent list')

    def test_04_question_only_matching_matrix(self):
        cases = [
            ('direct target', proposal(), True),
            ('negated comparison', proposal('lysozyme', 'Which features are annotated for lysozyme, excluding KaiC?'), True),
            ('unrelated background', proposal('lysozyme', 'After the KaiC work, which features are annotated for lysozyme?'), True),
            ('hyphen component', proposal('lysozyme', 'Which features of lysozyme are KaiC-independent?'), True),
            ('substring control', proposal('lysozyme', 'Which features are annotated for KaiC2?'), False),
            ('fresh control', proposal('lysozyme'), False),
            ('PDB exemption', dict(proposal(), source_query={'source': 'pdb', 'entry_id': '1ABC'}), False),
            ('instrument exemption', dict(proposal(), instrument_query={'skill': 'fold_read'}), False),
        ]
        refusals = 0
        for label, value, expected in cases:
            with self.subTest(label=label):
                Path(self.R.LOOKUPS).unlink(missing_ok=True)
                inquiry = self.C._inquiry(value)
                self.assertEqual(self.C.spent_retrieval(inquiry, {'subjects': ['KaiC']}), expected)
                got, _ = self.C._held_to_plan('', '', inquiry, value, None, None, self.R,
                                             spent={'subjects': ['KaiC']}, replan=False)
                self.assertEqual('spent subject:' in got.get('refused', ''), expected)
                refusals += bool(got.get('refused'))
        self.assertEqual(refusals, 4)
        print('MEASURE matrix: 4/8 spent refusals, including 3 question-only mentions; synthetic, not a live rate')

    def test_05_open_line_exempts_spent_but_not_identical_lookup(self):
        line = self.L.opened_by('KaiC work', 'Which function is annotated for KaiC?', 'offline fixture')
        value = proposal(line_id=line['id'])
        inquiry = self.C._inquiry(value)
        first, _ = self.C._held_to_plan('', '', inquiry, value, None, None, self.R,
                                       spent={'subjects': ['KaiC']}, replan=False)
        self.assertNotIn('refused', first)
        second, _ = self.C._held_to_plan('', '', inquiry, value, None, None, self.R,
                                        spent={'subjects': ['KaiC']}, replan=False)
        self.assertIn('exact lookup', second['refused'])

    def test_06_reported_compound_shape_survives_real_plan(self):
        question = ('What are the specific structural hallmarks, documented cellular roles, '
                    'and source-backed relationships of lysozyme?')
        self.script(proposal('lysozyme', question))
        got = self.C._plan('offline', 'offline')
        self.assertEqual(got['question'], question)
        self.assertFalse(self.C.second_ask(question))
        self.assertEqual(self.C.concrete_ask(question), question)

    def test_07_actual_evidence_tree_retains_small_sourced_payload(self):
        inquiry = proposal('lysozyme')
        observations = {'records': [{'accession': 'P00698', 'function': 'Hydrolyzes cell wall peptidoglycan.'}],
                        'LITERATURE': [{'pmid': '123', 'abstract': 'This fixture reports catalytic activity.'}]}
        evidence, strings, addresses, request = self.C._coverage_request(inquiry, observations)
        self.assertIn('Hydrolyzes cell wall peptidoglycan.', request[1])
        self.assertIn('This fixture reports catalytic activity.', request[1])
        self.assertTrue(any('function' in p for p in addresses.values()))
        self.assertTrue(any('abstract' in p for p in addresses.values()))

    def test_08_negative_checker_is_terminal_without_independent_sufficiency(self):
        inquiry = proposal('lysozyme')
        observations = {'records': [{'accession': 'P00698', 'function': 'Hydrolyzes cell wall peptidoglycan.'}]}
        self.script({'answered': False, 'missing': ['fixture: claimed missing function'], 'supports': []})
        got = self.C._coverage_check(inquiry, observations)
        self.assertFalse(got['answered'])
        self.assertIsNone(got['independent_sufficiency'])
        self.assertEqual(self.ask.call_count, 1)

    def test_09_write_guard_rejects_unrepointed_store(self):
        with self.assertRaisesRegex(AssertionError, 'write outside scratch HOME'):
            open('/tmp/lab-refusals-forbidden-write', 'w')

    def test_10_tick_writes_one_refusal_row_after_three_plans(self):
        self.script(proposal(), proposal(), proposal())
        cfg = dict(self.C.config(), enabled=True, forge_report_intake=None)
        with patch.dict(sys.modules, {
            'compute_admission': types.SimpleNamespace(admit=lambda *a, **k: contextlib.nullcontext()),
            'atelier_lab_lean': types.SimpleNamespace(today=lambda: None),
        }), patch.object(self.C, 'config', return_value=cfg), \
                patch.object(self.C, 'lab_context', return_value=('offline', {})), \
                patch.object(self.C, 'rotate_source_receipts'), \
                patch.object(self.C, '_note_graded'):
            outcome = self.C.tick()
        self.assertEqual(outcome['kind'], 'inquiry_refused')
        rows = self.C._jsonl(self.C.NOTEBOOK)
        self.assertEqual(len(rows), 1)
        self.assertIn('spent subject:', rows[0]['why'])
        self.assertEqual(rows[0]['truth_status'], 'refused_before_any_source_call')
        self.assertEqual(self.ask.call_count, 3)

    def test_11_probe_reports_unknowns_and_question_only_count(self):
        import importlib.util
        import io
        spec = importlib.util.spec_from_file_location('readonly_probe', REPO / 'scripts/probe_lab_refusals_readonly.py')
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        self.C._append(self.C.NOTEBOOK, {
            'at': self.C.now_iso(), 'kind': 'inquiry_refused',
            'why': 'repeat: spent subject: this retrieval already ended without an answer (KaiC)',
            'inquiry': proposal('lysozyme', 'After KaiC, which features does lysozyme have?')})
        before = {p: p.read_bytes() for p in Path(self.C.ROOT).rglob('*') if p.is_file()}
        out = io.StringIO()
        # The suite's audit guard remains installed. Avoid leaving the probe's
        # permanent write ban installed in this test runner during scratch cleanup.
        with patch.object(sys, 'argv', ['probe', '--lab-root', self.C.ROOT]), \
                patch.object(sys, 'addaudithook') as install, contextlib.redirect_stdout(out):
            probe.main()
            install.assert_called_once_with(probe.readonly)
        values = [json.loads(line) for line in out.getvalue().splitlines()]
        row = next(r for r in values if r['type'] == 'spent_refusal')
        self.assertEqual(row['planner_first_or_replan'], 'unknown_attempt_not_recorded')
        self.assertEqual(row['pairs'][0]['in_actual_planner_spent_prompt'], 'unknown_prompt_not_recorded')
        self.assertEqual(values[-1]['all_named_matches_question_only'], 1)
        self.assertEqual(values[-1]['spent_refusal_rows'], 1)
        self.assertFalse(values[-1]['files_changed_during_read'])
        self.assertEqual(before, {p: p.read_bytes() for p in Path(self.C.ROOT).rglob('*') if p.is_file()})
        with self.assertRaises(RuntimeError):
            probe.readonly('open', ('ignored', 'w', os.O_WRONLY))
        with self.assertRaises(RuntimeError):
            probe.readonly('socket.connect', ())

    def test_12_feature_fallback_is_broadened_after_planning(self):
        self.script(proposal(), proposal(), proposal())
        inquiry = self.C._fresh_free_inquiry(self.R, {'subjects': ['KaiC']})
        self.assertIn('curated record of myoglobin list?', inquiry['question'])
        record = {'accession': 'P02144', 'protein_name': 'Myoglobin', 'organism': 'Homo sapiens'}
        resolved, records, receipt = self.C._resolve_free_record_discovery(inquiry, [record])
        self.assertEqual(resolved['question'], self.C._record_connection_question('Myoglobin', 'P02144'))
        self.assertEqual(resolved['uniprot_query'], 'accession:P02144')
        self.assertEqual(resolved['identity_queries'], ['accession:P02144'])
        self.assertEqual(records, [record])
        self.assertEqual(receipt['accession'], 'P02144')
        self.assertIn('relationship', resolved['question'])
        self.assertEqual(self.ask.call_count, 3)  # grounding adds no model call

    def test_13_existing_connection_question_is_not_silently_narrowed(self):
        original = self.C._record_connection_question('myoglobin')
        inquiry = self.C._inquiry(proposal('myoglobin', original))
        record = {'accession': 'P02144', 'protein_name': 'Myoglobin', 'organism': 'Homo sapiens'}
        resolved, _, _ = self.C._resolve_free_record_discovery(inquiry, [record])
        self.assertEqual(resolved['question'], self.C._record_connection_question('Myoglobin', 'P02144'))
        self.ask.assert_not_called()

    def test_14_dead_ends_counts_attempts_without_individual_negative_reviews(self):
        inquiries = [{'kind': 'inquiry', 'inquiry': proposal(name)}
                     for name in ('lysozyme', 'myoglobin', 'KaiC')]
        dead = self.C.dead_ends(inquiries)
        self.assertEqual(dead['count'], 3)
        self.assertIn('KaiC', dead['subjects'])
        self.assertEqual(self.C.dead_ends(inquiries + [{'kind': 'reflection', 'answers_question': 'yes: fixture'}])['count'], 0)

    def test_15_frontier_measurement_step_accepts_same_subject_lookup(self):
        step = {'subjects': ['SLC26A4'], 'next_question':
                'Measure RMSD of the SLC26A4 model against its experimental reference.'}
        lookup = proposal('SLC26A4', 'What documented cellular role does SLC26A4 have?')
        self.assertTrue(self.R.on_frontier(lookup, step))
        self.assertFalse(self.R.on_frontier(proposal('lysozyme'), step))

    def test_16_new_instrument_choice_is_routed_to_browse_first(self):
        value = proposal('myoglobin', 'Measure helix ranges in the saved myoglobin model.',
                         instrument_query={'skill': 'fold_read', 'operation': 'structure.read',
                                           'files': ['artifacts/esmfold/P02144-fixture.pdb'], 'range': [1, 100]})
        inquiry = self.C._inquiry(value)
        cfg = dict(self.C.config(), enabled=True, forge_report_intake=None)
        with patch.dict(sys.modules, {
            'compute_admission': types.SimpleNamespace(admit=lambda *a, **k: contextlib.nullcontext()),
            'atelier_lab_lean': types.SimpleNamespace(today=lambda: None),
        }), patch.object(self.C, 'config', return_value=cfg), \
                patch.object(self.C, 'lab_context', return_value=('offline', {'context_sha256': 'fixture'})), \
                patch.object(self.C, 'rotate_source_receipts'), \
                patch.object(self.C, '_note_graded'), patch.object(self.C, '_orient', return_value=inquiry):
            outcome = self.C.tick()
        self.assertEqual(outcome['next_phase'], 'browse')
        self.assertEqual(self.C._load(self.C.STATE, {})['inquiry']['instrument_query']['skill'], 'fold_read')

    def test_17_question_split_keeps_ambiguous_and_mixed_separate(self):
        import importlib.util
        import io
        spec = importlib.util.spec_from_file_location('readonly_probe', REPO / 'scripts/probe_lab_refusals_readonly.py')
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        questions = [
            ('documented_fact_lookup', 'What documented cellular role does KaiC have?', 'no: missing role'),
            ('new_measurement_question', 'Measure helix ranges in the saved model.', 'yes: fixture'),
            ('mixed', 'Measure RMSD and establish the documented cellular role.', 'no: missing role'),
            ('unclear', 'What should we explore next?', 'not assessed: fixture'),
        ]
        audit = probe.QuestionAudit()
        with contextlib.redirect_stdout(io.StringIO()):
            for i, (expected, q, verdict) in enumerate(questions):
                inquiry = proposal('KaiC', q)
                self.assertEqual(probe.classify(inquiry)['kind'], expected)
                audit.observe(i*3, {'kind': 'inquiry', 'inquiry': inquiry})
                if expected == 'new_measurement_question':
                    audit.observe(i*3+1, {'kind': 'additional_source', 'query_sent': {'skill': 'fold_read'}, 'receipt_id': 'measure-1'})
                else:
                    audit.observe(i*3+1, {'kind': 'source_read', 'source': 'UniProtKB REST'})
                audit.observe(i*3+2, {'kind': 'reflection', 'inquiry': inquiry, 'answers_question': verdict})
        summary = audit.summary()
        for kind, _, verdict in questions:
            self.assertEqual(summary[kind]['accepted_question_share_percent'], 25)
            self.assertEqual(summary[kind]['review_verdicts'][probe.verdict_category(verdict)], 1)
        self.assertEqual(summary['documented_fact_lookup']['source_operation_events']['uniprot_browse'], 1)
        self.assertEqual(summary['new_measurement_question']['source_operation_events'], {})
        self.assertEqual(summary['new_measurement_question']['instrument_result_events'], 1)
        # An incidental measuring route does not turn a documented question into a new finding.
        doc = dict(proposal(question=questions[0][1]), instrument_query={'operation': 'structure.measure'})
        self.assertEqual(probe.classify(doc)['kind'], 'documented_fact_lookup')


if __name__ == '__main__':
    unittest.main(verbosity=2)
