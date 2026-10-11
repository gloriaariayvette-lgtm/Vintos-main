#!/usr/bin/env python3
"""A query the Lab perimeter refuses is recorded, not quietly swapped for a generic one (audit B01).

A denied query used to be replaced by the wandering browse (RANDOM_QUERY) while the question was kept, so the Lab
retrieved unrelated proteins and the original question could then only be refused for not being established. The
perimeter still holds — the denied text is never sent — and the refusal is now explicit: the question as asked, the
query requested, why it was refused, and that no source was queried. Driven through tick(), the path the daemon
runs. Scratch workspace; the model and every source are stubs; sockets and processes are refused."""
from pathlib import Path
import contextlib, json, os, shutil, socket, subprocess, sys, tempfile, types, unittest
from unittest.mock import patch
scratch = tempfile.TemporaryDirectory(prefix='lab-perimeter-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/secrets')
NET = []
def forbidden(*a, **k):
    NET.append(a); raise AssertionError('External operation forbidden')
socket.socket.connect = forbidden; socket.create_connection = forbidden; subprocess.Popen = forbidden
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
import chemistry_lab as C
C.urllib.request.urlopen = forbidden

DENIED = 'protein_name:"botulinum toxin" AND organism_id:1491'
QUESTION = 'What is the structural basis of the botulinum toxin light chain protease?'
PROPOSAL = {'browse_lane': 'protein', 'question': QUESTION, 'uniprot_query': DENIED,
            'source_query': {'source': 'pdb', 'entry_id': '3BTA'}, 'line_id': None, 'new_line': None}
MODULES = {'compute_admission': types.SimpleNamespace(admit=lambda *a, **k: contextlib.nullcontext()),
           'chemistry_reading': types.SimpleNamespace(settle_one=lambda **k: None),
           'chemistry_taste': types.SimpleNamespace(observe_reflection=lambda note: None),
           'atelier_lab_lean': types.SimpleNamespace(today=lambda: None),
           'plugin_catalog': types.SimpleNamespace(prompt_instructions=lambda *a: ''),
           'claude_connector_catalog': types.SimpleNamespace(prompt_instructions=lambda *a: ''),
           'lab_genome_mining': types.SimpleNamespace(campaign_instructions=lambda: ''),
           'lab_keepers': types.SimpleNamespace(block=lambda **k: ''),
           'lab_asks': types.SimpleNamespace(block=lambda: ''),
           'lab_instruments': types.SimpleNamespace(menu_block=lambda: '', run=forbidden)}

class Perimeter(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(C.WS, ignore_errors=True); C._ensure()
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(sys.modules, MODULES))
        self.stack.enter_context(patch.object(C, 'config', return_value=dict(C.DEFAULTS, enabled=True, evo2_enabled=False)))
        self.stack.enter_context(patch.object(C, 'stop_requested', return_value=False))
        self.stack.enter_context(patch.object(C, 'lab_context', return_value=('offline context', {'context_sha256': 'offline'})))
        self.stack.enter_context(patch.object(C, 'atlas_turn_due', return_value=False))
        self.stack.enter_context(patch.object(C, 'dead_ends', return_value={'subjects': [], 'questions': [], 'count': 0}))
        # the human-identity grounding reads UniProt; it has its own suite (test_lab_gene_grounding.py)
        self.stack.enter_context(patch.object(C, '_ground_inquiry', return_value={'status': 'not_applicable'}))
        self.stack.enter_context(patch.object(C, '_existing_model_read', side_effect=lambda x: x))
        lines = types.SimpleNamespace(pick=lambda: None, orient_text=lambda line: '', tests_block=lambda: '',
                                      get=lambda _: None, reflect_text=lambda _: '', after_reflection=lambda *a: '')
        self.stack.enter_context(patch.dict(sys.modules, {'lab_lines': lines}))

    def test_the_store_is_scratch_and_nothing_reaches_the_world(self):
        self.assertTrue(C.ROOT.startswith(scratch.name), C.ROOT)
        self.assertIs(socket.socket.connect, forbidden); self.assertEqual(NET, [])

    def test_the_perimeter_still_holds_and_the_denied_text_is_never_sent(self):
        self.assertIn('toxin', C.query_denied(DENIED))
        self.assertNotIn('toxin', C._safe_query(DENIED))
        self.assertTrue(C._safe_query(DENIED).startswith('reviewed:true'))

    def test_an_ordinary_query_is_not_touched(self):
        self.assertIsNone(C.query_denied('gene:SLC26A4 AND organism_id:9606'))
        self.assertIsNone(C.query_denied(''))          # no query asked is not a refusal
        self.assertIn('SLC26A4', C._safe_query('gene:SLC26A4 AND organism_id:9606'))

    def test_the_daemon_tick_records_the_refusal_and_retrieves_nothing(self):
        with patch.object(C, '_ask', return_value=json.dumps(PROPOSAL)), \
                patch.object(C, '_browse', side_effect=forbidden), \
                patch.object(C, '_strategy_change', return_value=None), \
                patch.object(C, '_next_evidence_work', return_value=None):
            result = C.tick()
        self.assertEqual(result['kind'], 'inquiry_refused', result)
        note = C._tail_jsonl(C.NOTEBOOK)[-1]
        self.assertEqual(note['question'], QUESTION)                     # the question is kept as asked
        rejected = note['inquiry']['query_rejected']
        self.assertEqual(rejected['requested_query'], DENIED)            # what it meant to retrieve
        self.assertIn('toxin', rejected['reason'])                       # why it did not
        self.assertIsNone(rejected['executed_query'])                    # and that nothing stood in for it
        self.assertIsNone(rejected['source_queried'])
        self.assertEqual(note['truth_status'], 'refused_before_any_source_call')
        self.assertIsNone(note['inquiry']['source_query'])               # no other route was taken either
        self.assertEqual(C._load(C.STATE, {}).get('phase'), 'orient')    # the cycle ends; the next pass plans again
        self.assertEqual(NET, [])

    def test_the_refusal_does_not_hold_the_next_pass(self):
        with patch.object(C, '_ask', return_value=json.dumps(PROPOSAL)), patch.object(C, '_browse', side_effect=forbidden), \
                patch.object(C, '_strategy_change', return_value=None), patch.object(C, '_next_evidence_work', return_value=None):
            C.tick()
        allowed = dict(PROPOSAL, question='What is the topology of human Pendrin?',
                       uniprot_query='gene:SLC26A4 AND organism_id:9606', source_query=None)
        with patch.object(C, '_ask', return_value=json.dumps(allowed)) as model, \
                patch.object(C, '_strategy_change', return_value=None):
            self.assertEqual(C.tick()['kind'], 'inquiry')
        self.assertEqual(model.call_count, 1)

    def test_this_module_is_the_one_the_deploy_installs(self):
        manifest = (REPO / 'scripts' / 'deploy-atelier.sh').read_text()
        self.assertIn('chemistry_lab.py', manifest)
        self.assertEqual(Path(C.__file__).resolve(), (REPO / 'scripts' / 'chemistry_lab.py').resolve())
        self.assertIn('vintos-chemistry-lab', manifest)

if __name__ == '__main__':
    unittest.main()
