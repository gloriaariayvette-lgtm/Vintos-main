#!/usr/bin/env python3
"""11 October 09:15, HSP90AA1: 8 KB of records and abstracts sat beside a 1.37 MB numeric payload in the instrument
receipt, and the reading was deferred at an estimated 1,487,450 tokens against a 32,000 budget. A long run of numbers
is now named rather than written out, as a long sequence already is; every word of evidence is kept, and the array
stays whole in its source receipt. Scratch workspace; the model and every sender are stubs; sockets and processes
are refused."""
from pathlib import Path
import copy, json, os, socket, subprocess, sys, tempfile, unittest
from unittest.mock import patch
scratch = tempfile.TemporaryDirectory(prefix='lab-numeric-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/secrets')
NET = []
def forbidden(*a, **k):
    NET.append(a); raise AssertionError('External operation forbidden')
socket.socket.connect = forbidden; socket.create_connection = forbidden; subprocess.Popen = forbidden
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import chemistry_lab as C
C._ask = forbidden; C.urllib.request.urlopen = forbidden

QUESTION = ('What are the structural features of the human HSP90AA1 chaperone protein, specifically the dimerization '
            'domain and its role in scaffolding client proteins?')
ASKED = {'question': QUESTION, 'uniprot_query': 'gene:HSP90AA1 AND organism_id:9606 AND reviewed:true'}
ABSTRACT = 'Complex conformational dynamics are essential for function of the Hsp90 chaperone. ' * 14
FUNCTION = 'Molecular chaperone that promotes the maturation and structural maturation of client proteins. ' * 12
def observations(values=120000):
    return {'records': [{'accession': 'P07900', 'protein_name': 'Heat shock protein HSP 90-alpha', 'taxon_id': 9606,
                         'organism': 'Homo sapiens', 'genes': [{'geneName': {'value': 'HSP90AA1'}}], 'function': FUNCTION}],
            'LITERATURE': [{'pmid': '31206022', 'title': 'Hsp90 middle domain phosphorylation', 'abstract': ABSTRACT}],
            'embedding_coverage': ['P07900 embedded whole chain'],
            'additional_source': {'receipt': {'source': 'instrument', 'receipt_id': 'rc-0911',
                                              'records': [{'per_residue_scores': [0.5] * values, 'note': 'kept'}]},
                                  'instrument_result': {'vector': [[0.1] * 320] * 3, 'small': [1, 2, 3], 'flags': [True, None]}}}

class NumericPayload(unittest.TestCase):
    def test_the_store_is_scratch_and_nothing_reaches_the_world(self):
        self.assertTrue(C.ROOT.startswith(scratch.name), C.ROOT)
        self.assertIs(C._ask, forbidden); self.assertIs(socket.socket.connect, forbidden); self.assertEqual(NET, [])

    def test_a_long_run_of_numbers_is_named_with_its_length_and_receipt(self):
        evidence = C.review_observations(ASKED, observations())
        named = evidence['additional_source']['records'][0]['per_residue_scores']
        self.assertIn('120000 numeric values', named); self.assertIn('rc-0911', named)
        self.assertIn('complete array in source receipt', named)

    def test_the_array_itself_is_left_whole_in_its_receipt(self):
        source = observations(); before = copy.deepcopy(source)
        C.review_observations(ASKED, source)
        self.assertEqual(source, before)   # the receipt the Lab stores is not edited
        self.assertEqual(len(source['additional_source']['receipt']['records'][0]['per_residue_scores']), 120000)

    def test_every_word_of_evidence_is_kept(self):
        evidence = C.review_observations(ASKED, observations())
        self.assertEqual(evidence['LITERATURE'][0]['abstract'], ABSTRACT)
        self.assertEqual(evidence['LITERATURE'][0]['pmid'], '31206022')
        self.assertEqual(evidence['records'][0]['function'], FUNCTION)
        self.assertEqual(evidence['additional_source']['records'][0]['note'], 'kept')
        self.assertEqual(evidence['embedding_coverage'], ['P07900 embedded whole chain'])

    def test_short_arrays_and_non_numbers_are_written_out_as_before(self):
        evidence = C.review_observations(ASKED, observations())
        result = evidence['additional_source']['instrument_result']
        self.assertEqual(result['small'], [1, 2, 3])
        self.assertEqual(result['flags'], [True, None])          # booleans and nulls are not numbers
        self.assertIn('960 numeric values, shape 3', result['vector'])   # nested rows are counted whole
        mixed = C.review_observations(ASKED, {'additional_source': {'receipt': {'records': [{'x': [1, 2, 'text'] + [3] * 100}]}}})
        self.assertEqual(mixed['additional_source']['records'][0]['x'][2], 'text')

    def test_the_reading_is_asked_instead_of_deferred(self):
        asked = []
        def model(system, user, **k):
            asked.append(system)
            if 'reading sourced' in system:
                return json.dumps({'answers_question': 'yes: the dimerization domain is the C-terminal domain',
                                   'factual_observation': 'P07900 function describes client maturation',
                                   'speculative_reading': '', 'next_question': 'Compare the C-terminal interface'})
            if 'evidence-coverage' in system:
                return json.dumps({'answered': True, 'missing': [], 'quotes_supported': True, 'rationale': 'records and abstract present'})
            return json.dumps({'sufficient': True, 'missing': [], 'rationale': 'the question is addressed'})
        with patch.object(C, '_ask', model):
            out = C._reflect('ctx', ASKED, observations())
        self.assertNotEqual(out.get('evidence_status'), 'deferred', out)
        self.assertFalse(out.get('coverage_deferred'), out)
        self.assertTrue(any('reading sourced' in s for s in asked), asked)

    def test_without_the_payload_nothing_about_budgeting_changed(self):
        plain = observations(values=0)
        plain['additional_source']['receipt']['records'][0].pop('per_residue_scores')
        evidence = C.review_observations(ASKED, plain)
        self.assertEqual(evidence['LITERATURE'][0]['abstract'], ABSTRACT)
        prepared = C._coverage_request(ASKED, plain)
        self.assertIsNone(C._coverage_preflight(ASKED, plain, prepared))

if __name__ == '__main__':
    unittest.main()
