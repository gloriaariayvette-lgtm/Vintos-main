#!/usr/bin/env python3
"""What the Lab's last day showed (27 October), each fixed where it happened:

- 25 instrument runs a day was spent by mid-afternoon. 100 now; the relay instruments, each a model turn on
  the Mac (and Biohub's metered ESM calls), keep their 25 inside it.
- source:pdb failed 27 of 27 ("PDB entry ID required") and reference_compare 31 of 31: he names structures by protein,
  accession or several ids. Each is now resolved to one entry first, and he is told which was used; no deposited
  structure is said as that.
- "not offered" (48), "unknown investigation route" (31), instrument:None (47): an obvious alias is read as the real
  instrument, and a refusal names the instruments and routes there are right now, one line each.
- KeyError 'candidate': a path into a stored output that is not there now says which fields there are.
- 73 steps waited on a source cooling down: the planner is shown which source cools until when, and a request to one
  is asked again before anything waits.

Scratch stores only; every sender is blocked by the shared sandbox and nothing runs except the stubs passed in."""
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_instruments
import lab_lines
from lab_sources import Sources
from lab_tool_calls import normalize_instrument, normalize_source, execution_request

C = sandbox.C
MODEL = 'artifacts/esmfold/O43511-ac5611395a4c.pdb'


def choice(route, request, step_question='Read the model over the STAS window'):
    return json.dumps({'route': route, 'request': request, 'step_question': step_question, 'why': 'next',
                       'question': 'Is the STAS fold kept?', 'prediction': 'yes', 'plan': ['read']})


def store():
    return C._load(I._path('investigations.json'), {})


def task_of(ask, call=-1):
    return json.JSONDecoder().raw_decode(ask.call_args_list[call].args[1])[0]


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

    def runs(self, skill, n):
        lab_instruments.LEDGER.write_text(json.dumps({'date': lab_instruments._runs_today()['date'],
                                                      'runs': [{'skill': skill}] * n}))


class DailyCap(Base):
    def test_a_hundred_runs_a_day_and_the_relay_keeps_its_twenty_five(self):
        self.assertEqual((lab_instruments.DAILY_RUNS, lab_instruments.RELAY_DAILY_RUNS), (100, 25))
        self.runs('structure_viewer', 25)
        self.assertEqual((lab_instruments.runs_left(), lab_instruments.relay_runs_left()), (75, 0))
        with self.assertRaises(PermissionError) as told:
            lab_instruments.run({'skill': 'structure_viewer', 'operation': 'structure.analyze', 'files': [MODEL],
                                 'question': 'which residues line the pore'}, runner=sandbox.SEND)
        self.assertIn('fold_read', str(told.exception))                  # the local ones still run, and he is told
        menu = lab_instruments.planner_menu()
        self.assertNotIn('structure_viewer', menu['skills'])
        self.assertIn('fold_read', menu['skills'])
        self.assertIn('relay_state', menu)
        self.assertIn('fold_read', lab_instruments.menu_block())
        self.assertNotIn('- structure_viewer', lab_instruments.menu_block())
        why, _ = I._offer_problem('instrument', {'skill': 'structure_viewer', 'operation': 'structure.analyze',
                                                 'files': [MODEL]})
        self.assertIn('no run left today', why)
        out = lab_instruments.run({'skill': 'derived_compare', 'operation': 'structure.compare_refolds', 'files': [],
                                   'question': 'how far do the refolds sit'},
                                  runner=lambda *a, **k: {'receipt': {'receipt_id': 'r'}, 'summary': 'ok', 'files': []})
        self.assertEqual(out['receipt']['source'], 'instrument:derived_compare')

    def test_at_a_hundred_nothing_more_runs(self):
        self.runs('fold_read', 100)
        self.assertEqual(lab_instruments.menu_block(), '')
        with self.assertRaises(PermissionError):
            lab_instruments.run({'skill': 'derived_compare', 'operation': 'structure.compare_refolds', 'files': [],
                                 'question': 'how far do the refolds sit'}, runner=sandbox.SEND)


class RealNames(Base):
    def test_obvious_aliases_are_read_as_the_real_instrument(self):
        cases = [
            ({'tool': 'reference_compare.structure.compare', 'model_id': MODEL, 'reference_id': 'artifacts/reference/9UTC.cif',
              'chain_id': 'A', 'ref_span': '535-729'},
             {'skill': 'reference_compare', 'operation': 'structure.compare', 'files': [MODEL], 'reference': '9UTC',
              'chain': 'A', 'ref_span': [535, 729]}),
            ({'also': {'chain': 'A', 'ref_span': '1-780', 'reference': '8SGW'}, 'files': [MODEL],
              'operation': 'structure.compare'},
             {'skill': 'reference_compare', 'operation': 'structure.compare', 'files': [MODEL], 'reference': '8SGW',
              'chain': 'A', 'ref_span': [1, 780]}),
            ({'skill': 'reference_compare', 'files': [MODEL], 'files_reference': '8SGW', 'chain': 'A',
              'operation': 'structure.compare'},
             {'skill': 'reference_compare', 'operation': 'structure.compare', 'files': [MODEL], 'reference': '8SGW',
              'chain': 'A'}),
            ({'skill': 'structure.measure', 'files': [MODEL]},
             {'skill': 'structure_viewer', 'operation': 'structure.measure', 'files': [MODEL]}),
            ({'instrument': 'structure_viewer', 'query': MODEL, 'operation': 'structure.analyze'},
             {'skill': 'structure_viewer', 'operation': 'structure.analyze', 'files': [MODEL]}),
            ({'instrument': 'structure.analyze', 'target': MODEL},
             {'skill': 'structure_viewer', 'operation': 'structure.analyze', 'files': [MODEL]}),
            ({'instrument': 'fold_read', 'artifact': MODEL, 'region': '535-729'},
             {'skill': 'fold_read', 'operation': 'structure.read', 'files': [MODEL], 'range': [535, 729]}),
        ]
        for given, want in cases:
            got = normalize_instrument(given)
            self.assertEqual({k: got.get(k) for k in want}, want, given)
        ref = {'step': 'S-1', 'path': ['embeddings', 0, 'artifact']}
        self.assertEqual(normalize_instrument({'fold_read': ref})['files'], [ref])
        self.assertEqual(execution_request('instrument', {'skill': 'fold_read', 'files': ['memory/chemistry-lab/' + MODEL]})
                         ['files'], [MODEL])
        self.assertEqual(I._coerce_route({'route': 'structure.analyze', 'request': {'files': [MODEL]}})['route'],
                         'instrument')

    def test_a_refusal_names_the_instruments_there_are_right_now_one_line_each(self):
        with self.assertRaises(lab_instruments.NotOffered) as told:
            lab_instruments.validate({'skill': 'structure_viewer', 'files': [MODEL], 'question': 'what is in this model'})
        text = str(told.exception)
        self.assertTrue(text.startswith('instrument or operation not offered in the Lab (structure_viewer, no operation'))
        for name in ('fold_read [structure.read]: helices, strands', 'reference_compare [structure.compare]',
                     'structure_viewer [structure.analyze | structure.measure | structure.render_image]', MODEL,
                     'run(s) left today'):
            self.assertIn(name, text)
        self.assertLess(len(text), 1800)

    def test_an_unknown_route_is_told_with_every_route_and_what_it_does(self):
        text = str(I.unknown_route('reflect'))
        self.assertIn("unknown investigation route 'reflect'", text)
        for route in I.ROUTES:
            self.assertIn(route + ': ', text)
        self.assertIn('fold_read', text)
        why, choices = I._offer_problem('reflect', {})
        self.assertTrue(any(line.startswith('read_output: ') for line in choices['what_each_does']))

    def test_told_twice_the_step_keeps_the_whole_list(self):
        ask = Mock(return_value=choice('instrument', {'skill': 'structure_viewer', 'files': [MODEL]}))
        execute = Mock(side_effect=lambda route, request, *a: lab_instruments.validate(request))
        row = I.turn('', ask=ask, execute=execute)
        self.assertEqual(row['state'], 'failed')
        self.assertIn('fold_read [structure.read]', row['error'])
        self.assertGreater(len(row['error']), 300)


class MissingFields(Base):
    def test_a_path_that_is_not_there_says_what_is(self):
        out = {'receipt': {'source': 'pubmed_abstracts', 'records': [{'pmid': '42509233'}]}}
        execute = Mock(return_value=out)
        first = I.turn('', ask=Mock(return_value=choice('source', {'source': 'pubmed', 'query': 'SLC26A11 STAS'})),
                       execute=execute)
        bad = {'reference': {'step': first['id'], 'path': ['candidate', 'assessment', 'finding']}}
        good = {'reference': {'step': first['id'], 'path': ['receipt', 'records', 0]}}
        with self.assertRaises(I.MissingField) as told:
            I.resolve(bad['reference'], store()['investigations'][0]['steps'])
        self.assertIn('no "candidate" at path []', str(told.exception))
        self.assertIn('its fields there are: receipt', str(told.exception))
        ask = Mock(side_effect=[choice('read_output', bad), choice('read_output', good)])
        row = I.turn('', ask=ask, execute=execute)
        self.assertEqual(row['state'], 'completed')
        self.assertIn('its fields there are: receipt', task_of(ask)['replanning']['why_not_run'])
        self.assertEqual(len(store()['investigations'][0]['steps']), 2)
        ask = Mock(return_value=choice('read_output', bad))
        row = I.turn('', ask=ask, execute=execute)                   # told twice: a step, refused, not a crash
        self.assertEqual(row['state'], 'refused_not_sent')
        self.assertNotEqual(row['error'], "'candidate'")
        with self.assertRaises(I.MissingField):
            I.resolve({'step': first['id'], 'path': ['receipt', 'records', 5]}, store()['investigations'][0]['steps'])


class Cooling(Base):
    def test_the_planner_is_shown_which_source_cools_until_when(self):
        until = time.time() + 45
        C._atomic(I._path('source-throttle.json'), {'pubmed_abstracts': until, 'uniprot': time.time() - 5})
        note = I.cooling_note()
        self.assertEqual(list(note['sources']), ['pubmed_abstracts'])
        self.assertIn(time.strftime('%H:%M:%S UTC', time.gmtime(until)), note['sources']['pubmed_abstracts'])
        ask = Mock(return_value=choice('finish', {}))
        with patch.object(I, '_review', return_value=({'kind': 'investigation_review'}, False)):
            I.turn('', ask=ask, execute=Mock())
        self.assertIn('pubmed_abstracts', task_of(ask, 0)['cooling_sources']['sources'])

    def test_a_request_to_a_cooling_source_is_asked_again_before_anything_waits(self):
        C._atomic(I._path('source-throttle.json'), {'pubmed': time.time() + 50})
        out = {'receipt': {'source': 'uniprot', 'records': []}}
        execute = Mock(return_value=out)
        ask = Mock(side_effect=[choice('source', {'source': 'pubmed', 'query': 'pendrin STAS'}),
                                choice('source', {'source': 'uniprot', 'query': 'accession:O43511'})])
        row = I.turn('', ask=ask, execute=execute)
        replanning = task_of(ask)['replanning']
        self.assertIn('source pubmed is cooling down until', replanning['why_not_run'])
        self.assertIn('uniprot', replanning['valid_choices']['sources_ready_now'])
        self.assertNotIn('pubmed', replanning['valid_choices']['sources_ready_now'])
        self.assertEqual(row['tool'], 'source:uniprot')
        self.assertEqual([c.args[1]['source'] for c in execute.call_args_list], ['uniprot'])   # pubmed never sent
        self.assertEqual(C._load(I._path('source-throttle.json'), {})['pubmed'] > time.time(), True)  # spacing kept


class PdbEntries(Base):
    def rcsb(self, entries_by_query):
        sent = []
        def fetch(url):
            sent.append(url)
            if url.startswith('https://search.rcsb.org/'):
                body = json.loads(__import__('urllib.parse').parse.parse_qs(url.split('?', 1)[1])['json'][0])
                key = json.dumps(body['query'], sort_keys=True)
                ids = next((v for k, v in entries_by_query.items() if k in key), [])
                return {'result_set': [{'identifier': i} for i in ids], 'total_count': len(ids)}, {}
            entry = url.rsplit('/', 1)[1]
            return {'rcsb_id': entry, 'exptl': [{'method': 'ELECTRON MICROSCOPY'}]}, {}
        return Sources(fetch=fetch, fetch_structure=sandbox.SEND), sent

    def test_names_accessions_and_lists_resolve_to_one_entry_and_say_which(self):
        src, sent = self.rcsb({'O43511': ['7WL2', '7WL7', '7WL8'], 'pendrin': ['7WK1'], 'trehalose': []})
        out = src.query(normalize_source({'source': 'pdb', 'query': '6AO4, 6KMZ, 6KN0, 6VFE, 7Z1X'}))
        self.assertEqual(out['query']['entry_id'], '6AO4')
        self.assertIn('6KMZ', out['metadata']['entry_resolution']['note'])
        out = src.query(normalize_source({'source': 'pdb', 'entry_id': 'O43511'}))
        self.assertEqual(out['query']['entry_id'], '7WL2')
        self.assertEqual(out['metadata']['entry_resolution']['via'], 'RCSB entries mapped to UniProt O43511')
        self.assertIn('7WL7', out['metadata']['entry_resolution']['note'])
        out = src.query(normalize_source({'source': 'pdb', 'pdb_ids': ['8SGW', '7WK1']}))
        self.assertEqual(out['query']['entry_id'], '8SGW')
        out = src.query(normalize_source({'source': 'pdb', 'query': 'human pendrin'}))
        self.assertEqual(out['query']['entry_id'], '7WK1')
        with self.assertRaises(ValueError) as told:
            src.query(normalize_source({'source': 'pdb', 'query': 'trehalose phosphate synthase archaeal'}))
        self.assertIn('no deposited structure', str(told.exception))
        self.assertTrue(all(u.startswith(('https://search.rcsb.org/', 'https://data.rcsb.org/')) for u in sent))

    def test_the_step_s_own_words_are_no_archive_argument(self):
        spec = normalize_source({'source': 'pdb', 'entry_id': '9UTC', 'operation': 'structure_evidence',
                                 'question': 'Retrieve 9UTC to confirm it is pendrin-related'})
        self.assertEqual(spec, {'source': 'pdb', 'entry_id': '9UTC', 'operation': 'structure_evidence'})

    def test_the_resolved_entry_is_told_with_the_step(self):
        step = {'id': 'S-pdb'}
        I._store_result(step, {'receipt': {'source': 'pdb', 'records': [{}], 'metadata': {'entry_resolution': {
            'note': 'O43511 named no PDB entry; RCSB lists 3, and 7WL2 (its first) was used.'}}}})
        self.assertIn('7WL2', step['resolved'])

    def test_a_compare_s_reference_is_worked_out_and_named(self):
        request = {'skill': 'reference_compare', 'operation': 'structure.compare', 'files': [MODEL], 'chain': 'A',
                   'ref_span': [535, 729], 'question': 'Compare the O43511 model to the 9UTC reference structure'}
        got, why, note = I._reference_input(request, [])
        self.assertEqual((got['reference'], why), ('9UTC', ''))
        self.assertIn('read from the question', note)
        request = dict(request, question='Compare the model with its deposited structure', reference='O43511')
        with patch.object(C, '_sourced_record', return_value={'accession': 'O43511', 'pdb_ids': []}), \
                patch.object(I, '_rcsb_entries_for', return_value=(['7WL2', '7WL7'], '')):
            got, why, note = I._reference_input(request, [])
        self.assertEqual((got['reference'], why), ('7WL2', ''))
        self.assertIn('7WL7', note)
        with patch.object(C, '_sourced_record', return_value={'accession': 'O43511', 'pdb_ids': []}), \
                patch.object(I, '_rcsb_entries_for', return_value=([], '')):
            got, why, note = I._reference_input(request, [])
        self.assertIn('no deposited structure', why)
        with patch.object(C, '_sourced_record', return_value={'accession': 'O43511', 'pdb_ids': ['8SGW', '7WL2']}):
            got, why, note = I._reference_input(request, [])
        self.assertEqual(got['reference'], '8SGW')
        self.assertIn('7WL2', note)

    def test_the_rcsb_lookup_for_a_compare_keeps_the_pdb_spacing(self):
        C._atomic(I._path('source-throttle.json'), {'pdb': time.time() + 30})
        found, why = I._rcsb_entries_for('O43511')
        self.assertIsNone(found)
        self.assertIn('cooling', why)


if __name__ == '__main__': unittest.main(verbosity=2)
