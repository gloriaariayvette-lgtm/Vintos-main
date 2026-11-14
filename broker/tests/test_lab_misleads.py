#!/usr/bin/env python3
"""Three ways the Lab misled its own readers (13 November), each held here on synthetic data only.

1. A structure comparison never said what the entry was, so a blind sufficiency check took "TM 0.929 against an entry"
   as an answer about flowering plants when the entry was a mouse protein. The entry's title and source organism now
   reach the receipt and the sufficiency request.
2. The closed-question placeholder was echoed back by the planner and opened as a question; its "finding" (a raw
   sequence the appraisal scored 1) was printed as what the day found.
3. A next question asking for a reference comparison with no PDB entry named cannot run, and is now marked so.

Scratch HOME and every sender blocked (test_lab_tool_routing); no structure file is parsed here."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_lines
import lab_closed_redaction as R
import lab_findings
import lab_instruments
import chemistry_reference_compare as RC

C = sandbox.C
WITHHELD = R._topic('Which specific structural features of the synthetic protein are documented?')
SPECIES_LINE = 'the entry is: Synthetic transporter bound chloride in inward state (Testus syntheticus)'

spec = importlib.util.spec_from_file_location('chemistry_digest_misleads', sandbox.REPO / 'scripts' / 'chemistry_digest.py')
D = importlib.util.module_from_spec(spec); spec.loader.exec_module(D)


class ReferenceIdentity(unittest.TestCase):
    def test_the_entry_species_reaches_the_sufficiency_request(self):
        display = ['O00001-abc.pdb vs 9ZZZ chain A, residues 6-65 of the entry (1-60 of his protein)', SPECIES_LINE,
                   'TM-score on the sequence alignment: 0.929 (by his model), 0.930 (by the entry); RMSD 1.10 A']
        display += ['helix %d-%d (entry %d-%d): mean 1.00 A from his model' % (n, n + 5, n, n + 5) for n in range(1, 400, 6)]
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, json.dumps({'ok': True, 'result': {'reference': '9ZZZ',
                                                                                          'display': display}}), '')
        runner = lab_instruments._compare_runner({'reference': '9ZZZ', 'chain': 'A', 'ref_span': [6, 65]}, run=fake_run)
        out = runner('lab', 'reference_compare', 'q', 'structure.compare',
                     [str(Path(lab_instruments.LAB) / 'artifacts' / 'esmfold' / 'O00001-abc.pdb')])
        source = lab_instruments.relay_result('reference_compare', 'structure.compare', ['artifacts/esmfold/O00001-abc.pdb'], out)
        self.assertIn(SPECIES_LINE, source['receipt']['records'][0]['summary'])   # kept inside the 1,500-character cut
        inquiry = {'question': 'Is its STAS domain similar to the same domain in flowering-plant proteins?'}
        system, prompt, _ = C._coverage_sufficiency_request(inquiry, C.review_observations(inquiry, {'additional_source': source}))
        self.assertIn('Testus syntheticus', prompt)
        self.assertIn('source organism of that entry', system)

    def test_a_comparison_with_no_entry_named_is_marked(self):
        no_id = 'Which secondary structure elements show the highest deviation from the reference structure?'
        self.assertTrue(RC.names_no_reference(no_id))
        self.assertEqual(RC.mark_unnamed_reference(no_id), no_id + ' ' + RC.NO_REFERENCE_NAMED)
        self.assertEqual(RC.mark_unnamed_reference(RC.mark_unnamed_reference(no_id)), no_id + ' ' + RC.NO_REFERENCE_NAMED)
        for fine in ('Does residues 535-729 show conservation when compared to the 9ZZZ PDB entry?',
                     'Run reference_compare against 1abc chain B over residues 1000-1200',
                     'Is the hydrophobicity of H5 higher compared to H1 or H2?',
                     'Identify the PDB structures with the highest resolution for residues 535-729', ''):
            self.assertFalse(RC.names_no_reference(fine), fine)
            self.assertEqual(RC.mark_unnamed_reference(fine), fine)
        self.assertTrue(RC.names_no_reference('Run reference_compare on residues 1000-1200 of the model'))


class WithheldQuestion(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        C._atomic(I._path('investigations.json'), {'investigations': []})
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=None), opened_by=Mock(return_value=None),
                                    record_step=Mock(), advance_plan=Mock(return_value='stale'))
        self.lines.start()

    def tearDown(self):
        self.lines.stop()
        sandbox.SEND.assert_not_called()

    def test_the_placeholder_is_recognised_in_both_forms(self):
        self.assertTrue(R.is_placeholder(R.PLACEHOLDER))
        self.assertTrue(R.is_placeholder('  ' + WITHHELD))
        self.assertFalse(R.is_placeholder('Which helices hold in 535-729?'))
        self.assertFalse(R.is_placeholder(None))

    def test_an_echoed_placeholder_does_not_replace_the_question(self):
        inv = {'id': 'I-test1', 'state': 'open', 'question': 'Which helices of the synthetic model hold between 6 and 65?',
               'steps': [], 'opened_at': C.now_iso()}
        data = {'investigations': [inv]}
        value, refused = I._settle_question(inv, {'question': WITHHELD, 'route': 'reflect', 'request': {}},
                                            data, '', Mock(), None)
        self.assertFalse(refused)
        self.assertEqual(value['question'], 'Which helices of the synthetic model hold between 6 and 65?')
        self.assertEqual(inv['question'], 'Which helices of the synthetic model hold between 6 and 65?')
        self.assertNotIn('reopened_as', inv)

    def test_a_fresh_investigation_with_only_the_placeholder_is_not_opened(self):
        inv = {'id': 'I-test2', 'state': 'open', 'question': '', 'steps': [], 'opened_at': C.now_iso()}
        data = {'investigations': [inv]}
        value, refused = I._settle_question(inv, {'question': WITHHELD, 'route': 'reflect', 'request': {}},
                                            data, '', Mock(), None)
        self.assertTrue(refused)
        self.assertIsNone(value)
        self.assertEqual(data['investigations'], [])
        with open(C.NOTEBOOK) as handle: rows = [json.loads(l) for l in handle]
        self.assertEqual(rows[-1]['kind'], 'investigation_refused_placeholder')

    def test_a_placeholder_step_question_falls_back_to_the_investigation_question(self):
        inv = {'id': 'I-test3', 'state': 'open', 'question': 'Which helices of the synthetic model hold?', 'steps': []}
        data = {'investigations': [inv]}
        C._atomic(I._path('investigations.json'), data)
        I._carry_out(data, inv, {'route': 'representation', 'step_question': WITHHELD,
                                 'request': {'records': [{'accession': 'P00001', 'sequence': 'MKTAYIAKQR' * 3}]}},
                     None, '', Mock(), Mock(side_effect=RuntimeError('not run here')), False)
        self.assertEqual(inv['steps'][-1]['question'], 'Which helices of the synthetic model hold?')


class Digest(unittest.TestCase):
    DAY = '2026-01-02'

    def test_withheld_and_thin_findings_are_not_said_as_found(self):
        notebook = [
            {'at': self.DAY + 'T01:00:00Z', 'kind': 'investigation_finding', 'question': WITHHELD,
             'result': 'MKTAYIAKQRMKTAYIAKQR [UniProt P00001]', 'appraisal': {'value': 3, 'keep': True}},
            {'at': self.DAY + 'T02:00:00Z', 'kind': 'investigation_finding', 'question': 'What is the sequence of P00002?',
             'result': 'MKTAYIAKQR [UniProt P00002]', 'appraisal': {'value': 1, 'keep': False}},
            {'at': self.DAY + 'T03:00:00Z', 'kind': 'investigation_finding', 'question': 'Which helices hold in 6-65?',
             'result': 'helices: 10-25, 50-60', 'appraisal': {'value': 2, 'keep': False}},
            {'at': self.DAY + 'T04:00:00Z', 'kind': 'investigation_finding', 'question': 'Which strand sits near 33?',
             'result': 'strand: 33-38'},                                   # no appraisal: shown as before
        ]
        with patch.object(D, '_kept', lambda day: [{'question': WITHHELD, 'finding': 'KEPT-WITHHELD'}]):
            lines = D._finding_lines(notebook, self.DAY)
        text = '\n'.join(lines)
        self.assertNotIn('investigated and closed', text)
        self.assertNotIn('P00002', text)
        self.assertNotIn('KEPT-WITHHELD', text)
        self.assertIn('helices: 10-25, 50-60', text)
        self.assertIn('strand: 33-38', text)

    def test_next_questions_say_when_no_reference_is_named(self):
        notebook = [{'next_question': 'Does the 6-65 region deviate from the reference structure?'},
                    {'next_question': WITHHELD},
                    {'next_question': 'Does the 6-65 region deviate from 9ZZZ?'}]
        got = D._recent_questions(notebook, [], n=3)
        self.assertEqual(got, ['Does the 6-65 region deviate from 9ZZZ?',
                               'Does the 6-65 region deviate from the reference structure? ' + RC.NO_REFERENCE_NAMED])

    def test_a_stored_finding_marks_its_unnamed_reference(self):
        ask = Mock(return_value='{"value": 1, "novelty": "unclear", "keep": false, "tell_gloria": false}')
        inv = {'id': 'I-test4', 'question': 'Which helices hold?', 'steps': [], 'line_id': None}
        row = lab_findings.record(inv, {'factual_observation': 'helices 10-25',
                                        'next_question': 'Compare 6-65 with the experimental structure'}, ask)
        self.assertEqual(row.get('next_question'), 'Compare 6-65 with the experimental structure ' + RC.NO_REFERENCE_NAMED)
        sandbox.SEND.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
