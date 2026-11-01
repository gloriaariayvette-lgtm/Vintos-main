#!/usr/bin/env python3
"""Rereading material is not a repeat (Gloria, 1 November). A fold_read of a range an earlier read covered, or the
exact same fold_read, is allowed; a repeated question and a repeated external lookup are still refused."""
import json, os, tempfile, unittest
from datetime import datetime, timezone
WS = tempfile.mkdtemp(prefix='vintos-reread-'); os.environ['SPARK_WORKSPACE'] = WS
import lab_repeats as R

MODEL = 'artifacts/esmfold/Q86WA9-4e6734bae284.pdb'
NOW = datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)


def row(lookup, question, at='2026-10-30T05:19:15+00:00'):
    return {'at': at, 'lookup': lookup, 'question': question, 'words': sorted(R._words(question))}


class Reread(unittest.TestCase):
    def setUp(self):
        os.makedirs(R.ROOT, exist_ok=True)
        whole = R.lookup_key({'instrument_query': {'skill': 'fold_read', 'operation': 'structure.read',
                                                   'files': [MODEL], 'range': [None, None]}})
        uni = R.lookup_key({'source_query': {'source': 'pdb', 'operation': 'search_accession', 'accession': 'Q86WA9'}})
        rows = [row(whole, 'What is the domain layout of pendrin, its STAS domain and transmembrane helices?'),
                row(uni, 'Which PDB entries exist for the sweet taste receptor T1R2 accession?')]
        with open(R.LOOKUPS, 'w') as f:
            f.write(''.join(json.dumps(r) + '\n' for r in rows))

    def ask(self, q, **query):
        return R.repeat(dict(question=q, **query), now=NOW)

    def test_reading_a_covered_range_again_is_allowed(self):
        req = {'skill': 'fold_read', 'operation': 'structure.read', 'files': [MODEL], 'range': [1, 460]}
        self.assertEqual(self.ask('Secondary structure and confidence of the T1R2 extracellular domain residues 1-460?',
                                  instrument_query=req), '')

    def test_the_exact_same_read_is_allowed(self):
        req = {'skill': 'fold_read', 'operation': 'structure.read', 'files': [MODEL], 'range': [None, None]}
        self.assertEqual(self.ask('Read the whole T1R2 model again for its helix and strand map', instrument_query=req), '')

    def test_a_repeated_question_is_still_refused(self):
        req = {'skill': 'fold_read', 'operation': 'structure.read', 'files': [MODEL], 'range': [None, None]}
        why = self.ask('What is the domain layout of pendrin, its STAS domain and transmembrane helices?',
                       instrument_query=req)
        self.assertTrue(why, 'a word-for-word repeated question must still be refused')

    def test_a_repeated_external_lookup_is_still_refused(self):
        why = self.ask('PDB entries for Q86WA9 sweet receptor, listed?',
                       source_query={'source': 'pdb', 'operation': 'search_accession', 'accession': 'Q86WA9'})
        self.assertIn('you already ran this exact lookup', why)


if __name__ == '__main__':
    unittest.main()
