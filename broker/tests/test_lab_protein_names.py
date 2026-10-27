#!/usr/bin/env python3
"""The protein an accession is (27 October). All four investigations the Lab marked answered were about O43511, and
two of them called it "Trehalose phosphate synthase"; O43511 is pendrin (SLC26A4, human), as every cached UniProt
receipt of it says. A step question, a request's text or an investigation's question that names an accession with a
name its UniProt record (as the Lab already holds it) does not carry is now corrected in the moment, and he is told
the record's own name. Nothing is fetched for the check. Scratch stores only; every sender is blocked by the shared
sandbox and nothing runs except the stubs passed in."""
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_lines
import lab_names as N

C = sandbox.C
PENDRIN = {'accession': 'O43511', 'id': 'S26A4_HUMAN', 'protein_name': 'Pendrin', 'organism': 'Homo sapiens',
           'length': 780, 'pdb_ids': []}
PENDRIN_FULL = dict(PENDRIN, genes=[{'geneName': {'value': 'SLC26A4'}, 'synonyms': [{'value': 'PDS'}]}],
                    protein_aliases=['Sodium-independent chloride/iodide transporter', 'Solute carrier family 26 member 4'])
held = lambda accession: PENDRIN_FULL if accession == 'O43511' else None


def choice(route, request, step_question, question='What does O43511 hold in its STAS window?'):
    return json.dumps({'route': route, 'request': request, 'step_question': step_question, 'why': 'next',
                       'question': question, 'prediction': 'a helix', 'plan': ['read']})


def store():
    return C._load(I._path('investigations.json'), {})


def task_of(ask, call=-1):
    return json.JSONDecoder().raw_decode(ask.call_args_list[call].args[1])[0]


class Reading(unittest.TestCase):
    def test_the_names_he_wrote_beside_o43511_are_read(self):
        for text in ('the catalytic motifs of Trehalose phosphate synthase (O43511) in the literature',
                     'O43511 Trehalose phosphate synthase structure binding site',
                     "UniProt O43511 ('Trehalose phosphate synthase')",
                     'Trehalose phosphate synthase O43511'):
            found = N.check(text, held)
            self.assertEqual([m['said'] for m in found], ['Trehalose phosphate synthase'], text)
            self.assertIn('Pendrin', N.correct(text, found))
            self.assertNotIn('Trehalose', N.correct(text, found))

    def test_its_own_names_and_plain_mentions_are_left_alone(self):
        for text in ('Measure the STAS of human pendrin (O43511) against 8SGW', 'SLC26A4 (O43511) transport',
                     'Within the provisional O43511 window 535-729, which elements are present?',
                     'Compare the O43511 model to the 9UTC reference structure', 'O43511 (residues 535-729)',
                     'Read the fold_read output (O43511)', 'the STAS O43511 window',
                     'Is O43511 a chloride/iodide transporter?', 'PDS (O43511)'):
            self.assertEqual(N.check(text, held), [], text)

    def test_nothing_is_said_without_a_record_or_for_a_symbol_it_cannot_judge(self):
        self.assertEqual(N.check('Trehalose phosphate synthase (O43511)', lambda a: None), [])
        # the Lab's sourced record lists no genes: a gene symbol beside it is not judged
        self.assertEqual(N.check('SLC26A4 (O43511)', lambda a: PENDRIN), [])
        self.assertEqual(len(N.check('Trehalose phosphate synthase (O43511)', lambda a: PENDRIN)), 1)

    def test_he_is_told_the_record_s_own_name(self):
        message = N.message(N.check('Trehalose phosphate synthase (O43511)', held)[0])
        self.assertIn('O43511 is Pendrin (gene SLC26A4/PDS, Homo sapiens)', message)
        self.assertIn('not "Trehalose phosphate synthase"', message)


class InTheMoment(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations': []})
        C._atomic(I._path('source-throttle.json'), {})
        self.patches = [patch.multiple(lab_lines, pick=Mock(return_value=None), opened_by=Mock(return_value=None),
                                       record_step=Mock(), advance_plan=Mock(return_value='stale')),
                        patch.object(C, '_sourced_record', side_effect=lambda a: PENDRIN if a == 'O43511' else None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        sandbox.SEND.assert_not_called()

    def test_a_step_naming_o43511_as_trehalose_phosphate_synthase_is_corrected_and_he_is_told(self):
        out = {'receipt': {'source': 'pubmed_abstracts', 'records': [{'pmid': '1', 'title': 'Pendrin'}]}}
        execute = Mock(return_value=out)
        ask = Mock(return_value=choice('source', {'source': 'pubmed', 'query': 'O43511 Trehalose phosphate synthase '
                                                  'structure binding site'},
                                       'What are the catalytic motifs of Trehalose phosphate synthase (O43511)?'))
        row = I.turn('', ask=ask, execute=execute)
        self.assertEqual(row['state'], 'completed')
        sent = execute.call_args.args[1]
        self.assertEqual(sent['query'], 'O43511 Pendrin structure binding site')        # what was searched
        self.assertEqual(row['question'], 'What are the catalytic motifs of Pendrin (O43511)?')
        self.assertIn('Trehalose phosphate synthase', row['question_as_asked'])
        self.assertTrue(any('O43511 is Pendrin' in m for m in row['identity_correction']))
        inv = store()['investigations'][0]
        self.assertEqual(inv['name_corrections'][0]['accession'], 'O43511')
        I.turn('', ask=ask, execute=execute)                                          # the next planning turn
        task = task_of(ask)
        self.assertTrue(any('O43511 is Pendrin' in m for m in task['identity_corrections']))
        self.assertIn('identity_correction', task['results_so_far'][0])

    def test_an_investigation_question_naming_the_wrong_protein_is_corrected_before_planning(self):
        C._atomic(I._path('investigations.json'), {'investigations': [{
            'id': 'I-names', 'state': 'open', 'opened_at': C.now_iso(), 'steps': [], 'prediction': 'x', 'plan': [],
            'question': 'What are the structural features of Trehalose phosphate synthase (O43511)?'}]})
        ask = Mock(return_value=choice('finish', {}, 'finish'))
        with patch.object(I, '_review', return_value=({'kind': 'investigation_review'}, False)):
            I.turn('', ask=ask, execute=Mock())
        task = task_of(ask, 0)
        self.assertEqual(task['question'], 'What are the structural features of Pendrin (O43511)?')
        self.assertTrue(task['identity_corrections'])
        inv = store()['investigations'][0]
        self.assertIn('Trehalose', inv['question_as_asked'])

    def test_a_record_the_investigation_fetched_is_the_one_read(self):
        steps = [{'id': 'S-u', 'state': 'completed', 'output_file': 'investigation-outputs/S-u.json'}]
        payload = {'normalized_records': [PENDRIN_FULL]}
        I._store_result(steps[0], payload)
        self.assertEqual(I._held_record('O43511', steps)['genes'][0]['geneName']['value'], 'SLC26A4')
        self.assertIsNone(I._held_record('P99999', steps))


if __name__ == '__main__': unittest.main(verbosity=2)
