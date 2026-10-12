#!/usr/bin/env python3
"""Two causes of wasted Lab passes on 12 October, both in the Lab's own shaping rather than in what it was told.

04:00, a fault: the query "taxonomy_id:9606 AND reviewed:true AND (protein_name:SLC26A1 OR AND protein_name:SLC26A2)"
was refused by UniProt and sent the cycle to a fault redirect. The OR AND was written by _safe_query itself: its
missing-AND insertion did not count OR as an operator.

The final hour, 256 spent-subject refusals, nearly all SLC26A10-A15: a spent subject was named one at a time, so the
planner walked the family. The family is now named in the planning prompt. Nothing is refused that was not refused
before; this only changes what the planner is told and how a query is spelled.

Scratch workspace; the model and every source are stubs; sockets and processes are refused."""
from pathlib import Path
import json, os, socket, subprocess, sys, tempfile, types, unittest
from unittest.mock import patch
scratch = tempfile.TemporaryDirectory(prefix='lab-query-syntax-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/secrets')
os.environ.pop('CHEM_LAB_LLM_URL', None)
NET = []
def forbidden(*a, **k):
    NET.append(a); raise AssertionError('External operation forbidden')
socket.socket.connect = forbidden; socket.create_connection = forbidden; subprocess.Popen = forbidden
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import chemistry_lab as C
C.urllib.request.urlopen = forbidden

FAULTED = 'taxonomy_id:9606 AND reviewed:true AND (protein_name:SLC26A1 OR AND protein_name:SLC26A2)'

class QuerySyntax(unittest.TestCase):
    def test_the_store_is_scratch_and_nothing_reaches_the_world(self):
        self.assertTrue(C.ROOT.startswith(scratch.name), C.ROOT)
        self.assertIs(socket.socket.connect, forbidden); self.assertEqual(NET, [])

    def test_an_or_no_longer_has_and_inserted_after_it(self):
        shaped = C._safe_query('(gene:SLC26A4 OR gene:SLC26A5) AND organism_id:9606')
        self.assertNotIn('OR AND', shaped)
        self.assertIn('(gene:SLC26A4 OR gene:SLC26A5)', shaped)

    def test_the_query_that_faulted_is_valid_now(self):
        shaped = C._safe_query(FAULTED)
        self.assertNotIn('OR AND', shaped); self.assertNotIn('AND AND', shaped)
        self.assertIn('protein_name:SLC26A1 OR protein_name:SLC26A2', shaped)

    def test_a_doubled_operator_keeps_the_first(self):
        self.assertNotIn('AND AND', C._safe_query('gene:ABCA1 AND AND organism_id:9606'))
        self.assertIn('OR', C._safe_query('(gene:A1 OR AND gene:B2)'))

    def test_a_missing_and_is_still_inserted(self):
        self.assertIn('gene:SLC26A4 AND organism_id:9606', C._safe_query('gene:SLC26A4 organism_id:9606'))

    def test_an_ordinary_query_is_unchanged_in_substance(self):
        for query in ('accession:O43511', 'protein_name:"calcium sensing receptor" AND taxonomy_id:9606 AND reviewed:true'):
            shaped = C._safe_query(query)
            self.assertNotIn('AND AND', shaped); self.assertNotIn('OR AND', shaped)
            self.assertIn(query.split(' AND ')[0], shaped)

class SpentFamilies(unittest.TestCase):
    def test_two_members_name_the_family_and_one_does_not(self):
        self.assertEqual(C.spent_families(['SLC26A3', 'SLC26A11', 'HFE']), [('SLC26A', ['SLC26A11', 'SLC26A3'])])
        self.assertEqual(C.spent_families(['SLC26A3']), [])
        self.assertEqual(C.spent_families(['CFTR', 'AQP1']), [])

    def test_several_families_are_each_named(self):
        self.assertEqual([p for p, _m in C.spent_families(['TRPV1', 'TRPV4', 'SLC26A9', 'SLC26A11'])],
                         ['SLC26A', 'TRPV'])

    def test_the_planner_is_told_the_family_is_spent(self):
        os.makedirs(C.ROOT, exist_ok=True)
        Path(C.ROOT, 'question-holds.json').unlink(missing_ok=True)
        open(C.NOTEBOOK, 'w').close()
        import lab_repeats as real
        repeats = types.SimpleNamespace(canonical_lookup=real.canonical_lookup, lookup_key=real.lookup_key,
                                        frontier_step=lambda: None, on_frontier=lambda *a: True,
                                        record=lambda *a, **k: None, recent_lookups=lambda: [],
                                        **{k: getattr(real, k) for k in dir(real) if k.isupper() or k.startswith('_A')})
        lines = types.SimpleNamespace(pick=lambda: None, orient_text=lambda line: '', tests_block=lambda: '')
        spent = {'subjects': ['SLC26A3', 'SLC26A11'], 'questions': [], 'count': 0}
        asked = []
        def ask(system, task):
            asked.append(task)
            return json.dumps({'browse_lane': 'protein', 'question': 'How does human CFTR gate?',
                               'uniprot_query': 'gene:CFTR AND organism_id:9606', 'line_id': None, 'new_line': None})
        with patch.dict(sys.modules, {'lab_repeats': repeats, 'lab_lines': lines}), \
                patch.object(C, 'dead_ends', return_value=dict(spent)), \
                patch.object(C, 'remember_spent', lambda *a: None), \
                patch.object(C, 'spent_subjects', lambda: []), \
                patch.object(C, 'atlas_turn_due', return_value=False), \
                patch.object(C, 'repeats_dead_end', return_value=False), \
                patch.object(C, '_next_evidence_work', return_value=None), \
                patch.object(C, '_held_to_plan', lambda s, t, inq, v, *a, **k: (dict(inq), v)), \
                patch.object(C, '_ask', ask):
            got = C._orient('context')
        self.assertEqual(len(asked), 1)
        task = asked[0]
        self.assertIn('SLC26A3', task)                       # the members are still named
        self.assertIn('WHOLE FAMILY IS SPENT', task)         # and so is the family
        self.assertIn('SLC26A*', task)
        self.assertIn('members not listed above', task)
        self.assertNotIn('refused', got)                     # naming a family refuses nothing
        self.assertEqual(got['question'], 'How does human CFTR gate?')
        self.assertEqual(NET, [])

if __name__ == '__main__':
    unittest.main()
