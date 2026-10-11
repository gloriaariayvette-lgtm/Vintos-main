#!/usr/bin/env python3
"""A question that names two proteins to compare (11 October 08:43:42: "SLC26A11 ... compare to ... SLC26A4
(Pendrin)") was refused whichever way it was retrieved: one record lacked the other's name, and two records read as
"multiple retrieved targets". Each named target is now established by its own record, and nothing looser passes.
Scratch workspace; the model and every sender are stubs; sockets and processes are refused."""
from pathlib import Path
import json, os, socket, subprocess, sys, tempfile, unittest
from unittest.mock import patch
scratch = tempfile.TemporaryDirectory(prefix='lab-comparison-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/secrets')
NET = []
def forbidden(*a, **k):
    NET.append(a); raise AssertionError('External operation forbidden')
socket.socket.connect = forbidden; socket.create_connection = forbidden; subprocess.Popen = forbidden
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import chemistry_lab as C
from lab_sources import question_entity_context as entity_context
C._ask = forbidden; C.urllib.request.urlopen = forbidden

QUESTION = ('What is the structural basis for the bicarbonate/chloride exchange mechanism of SLC26A11, and how does '
            'its architecture compare to the STAS-domain-containing SLC26A4 (Pendrin)?')
ASKED = {'question': QUESTION, 'uniprot_query': 'gene:SLC26A11 AND organism_id:9606 AND reviewed:true'}
def record(accession, symbol, name, taxon=9606, organism='Homo sapiens'):
    return {'accession': accession, 'protein_name': name, 'taxon_id': taxon, 'organism': organism,
            'genes': [{'geneName': {'value': symbol}}], 'sequence_length': 606}
A11 = record('Q86WA9', 'SLC26A11', 'Anion exchange transporter')
A4 = record('O43511', 'SLC26A4', 'Pendrin')
MOUSE_A4 = record('Q9R155', 'SLC26A4', 'Pendrin', taxon=10090, organism='Mus musculus')

class Comparison(unittest.TestCase):
    def test_the_store_is_scratch_and_nothing_reaches_the_world(self):
        self.assertTrue(C.ROOT.startswith(scratch.name), C.ROOT)
        self.assertIs(C._ask, forbidden); self.assertIs(socket.socket.connect, forbidden); self.assertEqual(NET, [])

    def test_both_targets_retrieved_is_established_per_target(self):
        got = entity_context(ASKED, [A11, A4])
        self.assertEqual(got['status'], 'consistent', got)
        self.assertEqual(got['target_mapping'], {'SLC26A11': 'Q86WA9', 'SLC26A4': 'O43511'})
        self.assertEqual(got['selected_accessions'], ['O43511', 'Q86WA9'])

    def test_a_missing_second_target_stays_unresolved(self):
        got = entity_context(ASKED, [A11])
        self.assertEqual(got['status'], 'unresolved')
        self.assertIn('no retrieved record establishes SLC26A4', '; '.join(got['issues']))
        self.assertEqual(got['target_mapping'], {'SLC26A11': 'Q86WA9'})

    def test_the_second_target_in_another_species_does_not_count(self):
        got = entity_context(ASKED, [A11, MOUSE_A4])
        self.assertEqual(got['status'], 'unresolved')
        self.assertNotIn('SLC26A4', got['target_mapping'])

    def test_two_records_claiming_one_target_require_a_mapping(self):
        got = entity_context(ASKED, [A11, A4, dict(A4, accession='X99999')])
        self.assertEqual(got['status'], 'unresolved')
        self.assertIn('several retrieved records claim SLC26A4', '; '.join(got['issues']))

    def test_one_target_questions_are_unchanged(self):
        single = {'question': 'What is the structural topology of human SLC26A4 (Pendrin)?',
                  'uniprot_query': 'gene:SLC26A4 AND organism_id:9606'}
        self.assertEqual(entity_context(single, [A4])['status'], 'consistent')
        wrong = entity_context(single, [A11])
        self.assertEqual(wrong['status'], 'unresolved', wrong)
        self.assertNotIn('target_mapping', wrong)

    def test_the_refusal_names_the_target_still_to_retrieve(self):
        with patch.object(C, '_ask', forbidden):
            out = C._reflect('ctx', ASKED, {'records': [A11]})
        self.assertTrue(str(out['answers_question']).startswith('no:'), out)
        self.assertIn('SLC26A11', out['next_question']); self.assertIn('SLC26A4', out['next_question'])
        self.assertIn('one query', out['next_question'])

    def test_with_both_retrieved_the_reading_is_actually_asked(self):
        asked = []
        def model(system, user, **k):
            asked.append(system)
            if 'reading sourced' in system:
                return json.dumps({'answers_question': 'yes: both transporters retain the STAS fold',
                                   'factual_observation': 'Q86WA9 and O43511 are both retrieved human SLC26 records',
                                   'speculative_reading': '', 'next_question': 'Compare their STAS interfaces'})
            if 'evidence-coverage' in system:
                return json.dumps({'answered': True, 'missing': [], 'quotes_supported': True, 'rationale': 'both records present'})
            return json.dumps({'sufficient': True, 'missing': [], 'rationale': 'both named targets are established'})
        with patch.object(C, '_ask', model):
            out = C._reflect('ctx', ASKED, {'records': [A11, A4]})
        self.assertTrue(any('reading sourced' in s for s in asked), asked)
        self.assertEqual(out['entity_context_check']['status'], 'consistent')
        self.assertNotIn('does not establish the requested target', str(out.get('factual_observation')))

    def test_the_planner_is_told_one_query_must_return_both(self):
        source = Path(__file__).resolve().parents[2] / 'scripts' / 'chemistry_lab.py'
        self.assertIn('ONE query must return both', source.read_text())

if __name__ == '__main__':
    unittest.main()
