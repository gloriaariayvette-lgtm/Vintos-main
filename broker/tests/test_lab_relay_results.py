#!/usr/bin/env python3
"""A relay instrument's readable results reach the finish review (30 October).

A structure_viewer measure wrote halide-coordination-report.md and measurement-evidence.json, and the step kept only
their names and a 463-character summary, so the finish review could never find the question answered. Here the
report's text is kept (bounded, sha-checked), quoted at its own address, and the investigation finishes; a script
the instrument wrote, or a file altered since, is not kept. Scratch stores; the model and checker are stubs."""
import hashlib
import os
import tempfile
import unittest
import test_lab_finish_review_evidence as F
import lab_instruments

REPORT = ('Halide coordination report. ' + F.FOLD_TEXT + ' Distances measured on the deposited model.')


def write(root, name, text):
    data = text.encode()
    path = os.path.join(root, hashlib.sha256(data).hexdigest() + '-' + name)
    with open(path, 'wb') as stream:
        stream.write(data)
    return path


class RelayKeepsItsResults(F.Base):
    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp(dir=str(F.sandbox.SCRATCH))

    def relay_step(self, files, summary='measured 3 distances; see the report'):
        step = {'id': 'S-%012d' % 9, 'at': F.C.now_iso(), 'state': 'started', 'route': 'instrument',
                'question': 'measure the STAS region', 'tool': 'instrument:structure_viewer',
                'request': {'skill': 'structure_viewer', 'operation': 'structure.measure', 'files': [F.MODEL]}}
        out = lab_instruments.relay_result('structure_viewer', 'structure.measure', [F.MODEL],
                                           {'receipt': {'receipt_id': 'sv-1'}, 'summary': summary, 'files': files})
        F.I._store_result(step, out)
        return step, out

    def test_the_report_text_is_kept_and_the_finish_review_answers_from_it(self):
        files = [write(self.root, 'halide-coordination-report.md', REPORT),
                 write(self.root, 'analyze_structure.py', 'print("a script, not a result")')]
        step, out = self.relay_step(files)
        rec = out['receipt']['records'][0]
        self.assertEqual([r['file'].split('-', 1)[1] for r in rec['results']], ['halide-coordination-report.md'])
        self.assertIn(F.QUOTE, rec['results'][0]['text'])
        self.assertEqual(len(rec['outputs']), 2)
        inv, row = self.finish([step])
        self.assertEqual(inv['state'], 'answered', row.get('answers_question'))
        self.assertIn('results.0.text', row['coverage_check']['supports'][0]['path'])

    def test_summary_only_is_what_used_to_happen_and_it_cannot_answer(self):
        step, out = self.relay_step([])
        self.assertNotIn('results', out['receipt']['records'][0])
        inv, row = self.finish([step])
        self.assertNotEqual(inv['state'], 'answered')

    def test_a_file_altered_since_it_was_written_is_not_kept(self):
        path = write(self.root, 'measurement-evidence.json', '{"distance": 3.1}')
        with open(path, 'a') as stream:
            stream.write(' tampered')
        self.assertEqual(lab_instruments._result_texts([path]), [])

    def test_bounds_hold(self):
        big = [write(self.root, 'r%d.md' % n, ('x%d ' % n) * 4000) for n in range(5)]
        texts = lab_instruments._result_texts(big)
        self.assertTrue(all(len(t['text']) <= lab_instruments.RESULT_TEXT_CHARS for t in texts))
        self.assertLessEqual(sum(len(t['text']) for t in texts), lab_instruments.RESULT_TEXT_TOTAL)
        self.assertIn('truncated_from_chars', texts[0])

    def test_a_missing_file_is_skipped(self):
        self.assertEqual(lab_instruments._result_texts([os.path.join(self.root, 'gone.md')]), [])


if __name__ == '__main__':
    unittest.main()
