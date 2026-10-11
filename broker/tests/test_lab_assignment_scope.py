"""Revived work keeps its own planning scope, so its refusal cannot hold the assignment (2026-10-11: an unrelated
Gasdermin refusal was stamped with the stored-receipt audit's scope, and the audit was then held as exhausted). And
the Lab reaches Aegis's local Gemma only, never the shim's fallbacks. Scratch workspace; every model and source is a
stub; sockets and processes are refused."""
from pathlib import Path
import json, os, socket, subprocess, sys, tempfile, types, unittest
from unittest.mock import patch
scratch = tempfile.TemporaryDirectory(prefix='lab-assignment-scope-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/secrets')
os.environ.pop('CHEM_LAB_LLM_URL', None)
def forbidden(*a, **k): raise AssertionError('External operation forbidden')
socket.socket.connect = forbidden; socket.create_connection = forbidden; subprocess.Popen = forbidden
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import chemistry_lab as C
C._ask = forbidden; C.urllib.request.urlopen = forbidden
assert C.ROOT.startswith(scratch.name)

AUDIT = {'id': 'L-audit01', 'question': 'Audit the stored receipts for Q86SQ4 CUB: which are verified, stored only',
         'next_step': 'read the stored receipts only; no new retrieval'}
GASDERMIN = {'question': 'What does Gasdermin D pore assembly need?', 'requested_question': 'Gasdermin D pores',
             'uniprot_query': 'GSDMD', 'strategy_resolution': {'reason': 'continued_another_self_authored_unresolved_step'}}

class AssignmentScope(unittest.TestCase):
    def setUp(self):
        os.makedirs(C.ROOT, exist_ok=True)
        with open(C.NOTEBOOK, 'w') as f:
            f.write(json.dumps({'kind': 'inquiry_refused', 'inquiry': {'question': 'earlier'}}) + '\n')
        import lab_repeats as real
        repeats = types.SimpleNamespace(frontier_step=lambda: None, on_frontier=lambda *a: True, record=lambda *a, **k: None,
                                        **{k: getattr(real, k) for k in dir(real) if k.isupper() or k.startswith('_A')})
        lines = types.SimpleNamespace(pick=lambda: dict(AUDIT))
        self.mods = patch.dict(sys.modules, {'lab_repeats': repeats, 'lab_lines': lines}); self.mods.start()
        for name, value in (('dead_ends', lambda: {'subjects': []}), ('remember_spent', lambda *a: None),
                            ('spent_subjects', lambda: []), ('atlas_turn_due', lambda *a: False),
                            ('repeats_dead_end', lambda *a: False),
                            ('_next_evidence_work', lambda *a: dict(GASDERMIN)),
                            ('_held_to_plan', lambda s, t, inq, v, *a, **k: (dict(inq), v))):
            p = patch.object(C, name, value); p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.mods.stop)

    def test_revived_work_is_not_stamped_with_the_assignment(self):
        got = C._orient('context')
        self.assertEqual(got['question'], GASDERMIN['question'])
        scope = got['planning_scope']
        self.assertNotIn('line', scope, scope)
        self.assertEqual(scope['followup_of'], 'gasdermin d pores')

    def test_its_refusal_does_not_hold_the_assignment(self):
        refused = dict(C._orient('context'), refused='insufficient sources', evidence_status='insufficient')
        with open(C.NOTEBOOK, 'a') as f:
            f.write(json.dumps({'kind': 'inquiry_refused', 'inquiry': refused}) + '\n')
        audit_scope = {'line': {k: AUDIT[k] for k in ('id', 'question', 'next_step')}, 'frontier': None,
                       'lean': None, 'atlas': False}
        repeats = sys.modules['lab_repeats']
        self.assertIsNone(C._planning_hold(audit_scope, repeats, {'subjects': []}, None))

    def test_the_assignments_own_refusal_still_holds_it(self):
        audit_scope = {'line': {k: AUDIT[k] for k in ('id', 'question', 'next_step')}, 'frontier': None,
                       'lean': None, 'atlas': False}
        own = {'question': AUDIT['question'], 'refused': 'stored receipts insufficient', 'evidence_status': 'insufficient',
               'planning_scope': audit_scope}
        own['planning_evidence'] = C._planning_evidence(own)
        with open(C.NOTEBOOK, 'a') as f:
            f.write(json.dumps({'kind': 'inquiry_refused', 'inquiry': own}) + '\n')
        with patch.object(C, '_strategy_change', lambda *a: None):
            held = C._planning_hold(audit_scope, sys.modules['lab_repeats'], {'subjects': []}, None)
        self.assertTrue(held and held.get('planning_wait'), held)

    def test_local_gemma_only(self):
        self.assertIn('/gemma-aegis-local/', C.LLM_URL)

if __name__ == '__main__':
    unittest.main()
