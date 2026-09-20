#!/usr/bin/env python3
"""Scratch-only source contracts and handoff. No real network, model, or notification."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'scripts'))
SCRATCH = tempfile.TemporaryDirectory(prefix='lab-sources-test-')
os.environ['HOME'] = SCRATCH.name
os.environ['SPARK_WORKSPACE'] = SCRATCH.name+'/workspace'
import lab_sources as sources
import chemistry_sources as bridge
import chemistry_lab as lab
import chemistry_frontier_bridge as frontier


class Tests(unittest.TestCase):
    def setUp(self):
        self.network = patch('urllib.request.urlopen', side_effect=AssertionError('live network forbidden'))
        self.network.start(); self.addCleanup(self.network.stop)
        self.assertTrue(Path(lab.ROOT).is_relative_to(SCRATCH.name))
        self.assertTrue(Path(frontier.INTEREST).is_relative_to(SCRATCH.name))
        self.calls = []
    def test_real_config_retains_source_and_intake_settings(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH.name) as tmp:
            config=Path(tmp)/'config.json'
            expected={'alphagenome_key_file':str(Path(tmp)/'key'),
                      'alphagenome_python':str(Path(tmp)/'python'),
                      'atlas_anchors':[{'chromosome':'chr1'}],
                      'forge_report_intake':{'url':'http://127.0.0.1:8612/api/lab-intake','token_file':str(Path(tmp)/'intake')}}
            config.write_text(json.dumps(expected))
            with patch.object(lab,'CONFIG',str(config)):
                actual=lab.config()
                self.assertEqual({k:actual[k] for k in expected},expected)
                self.assertEqual(bridge.configured_sources().atlas.key_file,expected['alphagenome_key_file'])

    def fetch(self, url):
        self.calls.append(url)
        if 'uniprot' in url: return {'results':[{'primaryAccession':'P12345'}]}, {'X-UniProt-Release':'test-release'}
        if 'rcsb' in url: return {'exptl':[{'method':'X-RAY DIFFRACTION'}]}, {}
        return {'activities':[{'standard_value':'10','standard_units':'nM','standard_relation':'>','assay_type':'F'}]}, {}
    def client(self): return sources.Sources(fetch=self.fetch)
    def test_uniprot_local_validation(self):
        with self.assertRaises(ValueError): self.client().query({'source':'uniprot','query':'organism:human'})
        self.assertEqual(self.calls, [])
        result=self.client().query({'source':'uniprot','query':'protein_name:actin AND organism_id:9606'})
        self.assertEqual(result['metadata']['release'],'test-release')
    def test_bounded_queries(self):
        for q in ('length:[40 TO 350', 'protein_name:"abc', '\nreviewed:true'):
            with self.assertRaises(ValueError): sources.validate_uniprot(q)
        with self.assertRaises(ValueError): self.client().query({'source':'uniprot','query':'reviewed:true','limit':100})
    def test_structure_experimental(self):
        result=self.client().query({'source':'pdb','entry_id':'1abc'})
        self.assertEqual(result['records'][0]['exptl'][0]['method'],'X-RAY DIFFRACTION')
        with self.assertRaises(ValueError): sources.Sources(fetch=lambda u:({},{})).query({'source':'pdb','entry_id':'1abc'})
    def test_no_generated_urls(self):
        for source,field in [('pdb','entry_id'),('chembl','target_id')]:
            with self.assertRaises(ValueError):self.client().query({'source':source,field:'../../metadata'})
        self.assertEqual(self.calls, [])
    def test_chembl_preserves_assay(self):
        result=self.client().query({'source':'chembl','target_id':'CHEMBL123'})
        self.assertEqual(result['records'][0]['standard_relation'],'>')
        self.assertEqual(result['records'][0]['assay_type'],'F')
        self.assertEqual(result['novelty'],'not_established')
    def test_atlas_typed_bounded_source(self):
        spec={'source':'atlas','assembly':'GRCh38','chromosome':'chr1','start':100,'end':102,'scorers':['fixture']}
        client=sources.Sources(atlas=lambda q:{'scores':{'fixture':{'scores':[[0.8]]}},'sdk_version':'fixture','scorer_metadata':{}})
        result=client.query(spec)
        self.assertEqual(result['metadata']['evidence'],'precomputed_model_prediction')
        for change in ({'start':True},{'end':999},{'assembly':'GRCh37'},{'chromosome':'chr99'}):
            with self.assertRaises(ValueError):client.query(dict(spec,**change))
        with self.assertRaises(RuntimeError):self.client().query(spec)
    def test_cosmic_explicit_access_gap(self):
        with self.assertRaisesRegex(RuntimeError,'licensed'):self.client().query({'source':'cosmic'})
    def test_source_receipt_collision_report_path(self):
        result=bridge.query({'source':'pdb','entry_id':'1abc'},client=self.client(),question='Compare construct differences')
        rid=result['receipt']['receipt_id'];packet=bridge.report_packet([rid])
        self.assertEqual(packet['source_receipts'][0]['receipt_id'],rid)
        self.assertEqual(packet['novelty'],'not_established')
        desc=sources.collision_descriptor(result['receipt'])
        self.assertNotIn('vector',desc)
        self.assertEqual(desc['evidence_standing'],'eligible_as_text_collision_source_only')
        self.assertIn('requires_sourced_gene',result['candidate']['followups']['esmc_esmfold'])
        with self.assertRaises(ValueError):bridge.report_packet(['missing'])
    def test_database_reads_disabled(self):
        with patch.object(lab,'config',return_value={'allow_public_database_reads':False}):
            with self.assertRaises(RuntimeError):bridge.query({'source':'pdb','entry_id':'1abc'},client=self.client())
        self.assertEqual(self.calls,[])
    def test_local_analysis_receipt_reaches_report_packet(self):
        import contextlib, types
        import chemistry_genomic
        lab._ensure()
        lab._atomic(lab.STATE, {'phase':'atlas_genome','additional_source':{'receipt':{'receipt_id':'a'*64}}})
        cfg={**lab.DEFAULTS,'enabled':True,'atlas_evo2_enabled':True}
        result={'ok':True,'run_id':'fixture-run','model':'fixture-evo2','variant_delta':0.001,
                'truth_status':'evo2_model_likelihood_delta_not_functional_effect'}
        fake=types.SimpleNamespace(admit=lambda *a,**k:contextlib.nullcontext())
        with patch.object(lab,'config',return_value=cfg), patch.object(lab,'stop_requested',return_value=False), \
             patch.object(chemistry_genomic,'analyze',return_value=result), \
             patch.dict(sys.modules,{'compute_admission':fake,'chemistry_probe':types.SimpleNamespace(record_evo2_run=lambda x:None)}):
            self.assertTrue(lab.tick()['ok'])
        state=lab._load(lab.STATE,{})
        packet=bridge.report_packet([state['atlas_analysis_receipt']])
        self.assertEqual(packet['source_receipts'][0]['records'][0]['run_id'],'fixture-run')
        self.assertEqual(packet['source_receipts'][0]['metadata']['evidence'],'local_model_likelihood_not_functional_validation')

    def test_oversize_http_reply(self):
        class Reply(io.BytesIO): headers={}
        with self.assertRaises(ValueError):sources.fetch_json('https://example.invalid',transport=lambda *a,**k:Reply(b'x'*(sources.MAX_BYTES+1)))


if __name__=='__main__':unittest.main()
