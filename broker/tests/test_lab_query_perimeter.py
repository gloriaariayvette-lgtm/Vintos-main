#!/usr/bin/env python3
"""Generated UniProt queries keep their research subject after bounded syntax normalization.

The Lab used to replace selected subjects with the wandering browse. These tests keep every operation in a scratch
workspace and verify that ordinary syntax shaping neither removes the subject nor marks the inquiry refused."""
from pathlib import Path
import contextlib, json, os, shutil, socket, subprocess, sys, tempfile, types, unittest
os.environ["VINTOS_LAB_CAMPAIGNS"] = "0"   # this suite tests the ordinary loop; test_lab_campaign tests campaigns
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

    def test_the_research_subject_is_not_replaced(self):
        shaped = C._safe_query(DENIED)
        self.assertIn('botulinum toxin', shaped)
        self.assertNotEqual(shaped, C.RANDOM_QUERY)
        self.assertIn('organism_id:1491', shaped)

    def test_an_ordinary_query_is_not_touched(self):
        self.assertIn('SLC26A4', C._safe_query('gene:SLC26A4 AND organism_id:9606'))
        self.assertEqual(C._safe_query(''), C.RANDOM_QUERY)

    def test_the_inquiry_keeps_the_query_and_is_not_marked_refused(self):
        inquiry = C._inquiry(PROPOSAL)
        self.assertEqual(inquiry['question'], QUESTION)
        self.assertIn('botulinum toxin', inquiry['uniprot_query'])
        self.assertNotIn('query_rejected', inquiry)
        self.assertNotIn('refused', inquiry)
        self.assertEqual(inquiry['source_query']['entry_id'], '3BTA')
        self.assertEqual(NET, [])

    def test_this_module_is_the_one_the_deploy_installs(self):
        manifest = (REPO / 'scripts' / 'deploy-atelier.sh').read_text()
        self.assertIn('chemistry_lab.py', manifest)
        self.assertEqual(Path(C.__file__).resolve(), (REPO / 'scripts' / 'chemistry_lab.py').resolve())
        self.assertIn('vintos-chemistry-lab', manifest)

if __name__ == '__main__':
    unittest.main()
