#!/usr/bin/env python3
"""A step is recorded on the line it is about (12 October: the Pendrin-versus-Prestin line carried verified SLC26A11
claims and a next step about AQP1 versus AQP3, because each cycle was appended to whatever line it started under).
Routing, not refusal: a step about other proteins goes to the line about them, or to none, and its cycle stays in the
notebook either way. A step that names no protein, or one the line names, is recorded as before.
Scratch workspace; nothing is sent; sockets are refused."""
from pathlib import Path
import json, os, socket, sys, tempfile, unittest
scratch = tempfile.TemporaryDirectory(prefix='lab-line-ownership-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/secrets')
NET = []
def forbidden(*a, **k):
    NET.append(a); raise AssertionError('External operation forbidden')
socket.socket.connect = forbidden; socket.create_connection = forbidden
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import lab_lines as L

PP = {'id': 'L-pp', 'state': 'open', 'title': 'Pendrin versus Prestin', 'question': 'How does SLC26A4 differ from SLC26A5?', 'steps': []}
AQ = {'id': 'L-aq', 'state': 'open', 'title': 'Aquaporins', 'question': 'AQP1 versus AQP3 water permeation', 'steps': []}
CLAIM = {'requirement': 'topology', 'quote': 'ten TM helices', 'source_citation': 'PMID:1'}

class Ownership(unittest.TestCase):
    def setUp(self):
        self.assertTrue(str(L.STORE).startswith(scratch.name) and str(L.LOCK).startswith(scratch.name), L.STORE)
        L._write({'lines': [json.loads(json.dumps(PP)), json.loads(json.dumps(AQ))]})

    def line(self, line_id):
        return next(l for l in L.load()['lines'] if l['id'] == line_id)

    def test_the_store_is_scratch_and_nothing_reaches_the_world(self):
        self.assertEqual(NET, [])

    def test_entities_are_genes_and_accessions_not_words(self):
        self.assertEqual(L._entities('Compare SLC26A4 with O43511 and AQP1 in human cells'), {'SLC26A4', 'O43511', 'AQP1'})
        self.assertEqual(L._entities('What does a cell do?'), set())

    def test_a_step_about_the_line_is_recorded_on_it(self):
        got = L.record_step('L-pp', {'question': 'Which STAS residues of SLC26A5 bind chloride?', 'result': 'x', 'supports': [CLAIM]})
        self.assertEqual(got['id'], 'L-pp'); self.assertEqual(len(self.line('L-pp')['steps']), 1)

    def test_a_step_that_names_no_protein_stays_where_it_started(self):
        got = L.record_step('L-pp', {'question': 'What does the evidence say so far?', 'result': 'x'})
        self.assertEqual(got['id'], 'L-pp')

    def test_a_step_about_other_proteins_goes_to_the_line_about_them(self):
        got = L.record_step('L-pp', {'question': 'AQP1 against AQP3 selectivity', 'result': 'x', 'next': 'AQP3 pore radius', 'supports': [CLAIM]})
        self.assertEqual(got['id'], 'L-aq')
        self.assertEqual(self.line('L-pp')['steps'], [])                       # the Pendrin line is untouched
        self.assertNotIn('AQP3', str(self.line('L-pp').get('next_step') or ''))
        self.assertEqual(len(self.line('L-aq')['steps']), 1)

    def test_a_step_about_proteins_no_line_names_is_recorded_on_none(self):
        self.assertIsNone(L.record_step('L-pp', {'question': 'SLC26A11 bicarbonate exchange', 'result': 'x', 'supports': [CLAIM]}))
        self.assertEqual(self.line('L-pp')['steps'], []); self.assertEqual(self.line('L-aq')['steps'], [])

    def test_evidence_about_one_protein_never_satisfies_another_line(self):
        L.record_step('L-pp', {'question': 'SLC26A11 transport', 'result': 'x', 'supports': [CLAIM]})
        self.assertEqual(L.claim_state(self.line('L-pp'))['established'], [])

    def test_a_closed_line_is_not_a_destination(self):
        d = L.load(); next(l for l in d['lines'] if l['id'] == 'L-aq')['state'] = 'dropped'; L._write(d)
        self.assertIsNone(L.record_step('L-pp', {'question': 'AQP1 against AQP3', 'result': 'x'}))

    def test_after_reflection_acts_on_the_line_the_step_was_routed_to(self):
        note = {'inquiry': {'question': 'AQP1 against AQP3 selectivity'}, 'factual_observation': 'x', 'answers_question': 'no', 'line_status': 'dropped: spent'}
        out = L.after_reflection('L-pp', note)
        self.assertIn('L-aq', out)
        self.assertEqual(self.line('L-pp')['state'], 'open')                   # his verdict was about aquaporins
        self.assertEqual(self.line('L-aq')['state'], 'dropped')

if __name__ == '__main__':
    unittest.main()
