#!/usr/bin/env python3
"""Scratch-only source contracts and handoff. No real network, model, or notification."""
import io
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import types
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
        self.source_network = patch.object(sources, 'open_request',
                                           side_effect=AssertionError('live source network forbidden'))
        self.source_network.start(); self.addCleanup(self.source_network.stop)
        self.assertTrue(Path(lab.ROOT).is_relative_to(SCRATCH.name))
        self.assertTrue(Path(frontier.INTEREST).is_relative_to(SCRATCH.name))
        self.assertTrue(Path(bridge.lab.ROOT).is_relative_to(SCRATCH.name))
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
                self.assertEqual(Path(bridge.configured_sources().atlas.key_file),
                                 Path(expected['alphagenome_key_file']).resolve())

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
    def test_ncbi_microbiology_search_is_bounded_and_sourceable(self):
        def fetch(url):
            self.calls.append(url)
            if 'esearch.fcgi' in url:
                return {'esearchresult':{'count':'2','idlist':['101','102']}}, {}
            return {'result':{'101':{'uid':'101','scientificname':'Example microbe'},
                              '102':{'uid':'102','scientificname':'Other microbe'}}}, {}
        client=sources.Sources(fetch=fetch)
        result=client.query({'source':'ncbi','operation':'taxonomy','term':'colored biofilm'})
        self.assertEqual(len(result['records']),2)
        self.assertEqual(result['metadata']['database'],'taxonomy')
        self.assertEqual(result['novelty'],'not_established')
        self.assertTrue(all(url.startswith(sources.NCBI_BASE) for url in self.calls))
        self.calls.clear()
        for spec in ({'source':'ncbi','operation':'taxonomy','term':'x[All Fields]'},
                     {'source':'ncbi','operation':'assembly','taxon_id':'1);evil'},
                     {'source':'ncbi','operation':'protein','taxon_id':True,'term':'pigment'},
                     {'source':'ncbi','operation':'literature','term':'biofilm','limit':100}):
            with self.assertRaises(ValueError): client.query(spec)
        self.assertEqual(self.calls,[])

    def test_ncbi_sequence_requires_exact_accession_and_bounded_slice(self):
        def fasta(url):
            self.calls.append(url)
            return '>WP_123456789.1:1-10 example protein\nACDEFGHIKL\n'
        client=sources.Sources(fetch_sequence=fasta)
        result=client.query({'source':'ncbi_sequence','database':'protein',
                             'accession':'WP_123456789.1','start':1,'end':10})
        self.assertEqual(result['records'][0]['sequence'],'ACDEFGHIKL')
        self.assertEqual(result['metadata']['coverage'],'requested_slice_only')
        self.assertTrue(self.calls[0].startswith(sources.NCBI_BASE+'efetch.fcgi?'))
        self.calls.clear()
        for changed in ({'accession':'WP_123456789'}, {'accession':'../../secret'},
                        {'end':351}, {'start':0}, {'database':'assembly'}):
            spec={'source':'ncbi_sequence','database':'protein',
                  'accession':'WP_123456789.1','start':1,'end':10}
            with self.assertRaises(ValueError):client.query(dict(spec,**changed))
        self.assertEqual(self.calls,[])
        bad=sources.Sources(fetch_sequence=lambda u:'>WP_000000001.1 wrong\nACDE\n')
        with self.assertRaises(ValueError):bad.query({'source':'ncbi_sequence','database':'protein',
                                                       'accession':'WP_123456789.1','start':1,'end':4})

    def test_bvbrc_public_genome_and_pathway_receipts(self):
        def fetch(url):
            self.calls.append(url)
            return ([{'public':True,'genome_id':'42.1','genome_name':'Example',
                      'pathway_id':'PWY-1','pathway_name':'Pigment pathway','product':'enzyme',
                      'private_note':'must not copy'},
                     {'public':False,'genome_id':'42.2','pathway_name':'private'}], {})
        client=sources.Sources(fetch=fetch)
        genomes=client.query({'source':'bvbrc','operation':'genomes','taxon_id':42})
        paths=client.query({'source':'bvbrc','operation':'pathways','genome_id':'42.1'})
        self.assertEqual(genomes['records'][0]['genome_id'],'42.1')
        self.assertEqual(paths['records'][0]['pathway_name'],'Pigment pathway')
        self.assertEqual(len(paths['records']),1)
        self.assertNotIn('private_note',str(paths['records']))
        self.assertTrue(all(url.startswith(sources.BV_BRC_BASE) for url in self.calls))
        self.calls.clear()
        with self.assertRaises(ValueError): client.query({'source':'bvbrc','operation':'pathways','genome_id':'42.1/../secrets'})
        self.assertEqual(self.calls,[])

    def test_bvbrc_genus_follows_descendant_lineage(self):
        def fetch(url):
            self.calls.append(url)
            if 'taxon_lineage_ids' in url:
                return [{'public':True,'genome_id':'100.2','taxon_id':100,'genome_name':'Example species'}],{}
            return [],{}
        result=sources.Sources(fetch=fetch).query({'source':'bvbrc','operation':'genomes','taxon_id':42})
        self.assertEqual(result['records'][0]['genome_id'],'100.2')
        self.assertEqual(result['metadata']['taxon_match'],'descendant_lineage')
        self.assertEqual(len(self.calls),2)

    def test_microbiology_browse_reaches_reflection_without_protein_embedding(self):
        lab._ensure()
        spec={'source':'ncbi','operation':'literature','term':'colored wet surface communities'}
        lab._atomic(lab.STATE, {'phase':'browse','turns':0,'inquiry':{
            'browse_lane':'microbiology','source_query':spec,'question':'What persists on wet surfaces?'}})
        observed=sources.receipt('ncbi',spec,[{'uid':'123','summary':{'title':'A sourced observation'}}])
        fake=types.SimpleNamespace(admit=lambda *a,**k:contextlib.nullcontext())
        seen=[]
        def reflect(context,inquiry,records):
            seen.append(records)
            return {'attention':'record 123','factual_observation':'record title is present',
                    'speculative_reading':'unknown mechanism','next_question':'which taxon?'}
        with patch.dict(sys.modules,{'compute_admission':fake,
                                     'chemistry_reading':types.SimpleNamespace(settle_one=lambda **k:None)}), \
             patch.object(lab,'config',return_value={**lab.DEFAULTS,'enabled':True}), \
             patch.object(lab,'stop_requested',return_value=False), \
             patch.object(lab,'_browse',side_effect=AssertionError('protein browse not selected')), \
             patch.object(lab,'_embed_records',side_effect=AssertionError('no sequence to embed')), \
             patch.object(lab,'_reflect',side_effect=reflect), \
             patch.object(bridge,'query',return_value={'receipt':observed}):
            outcomes=[lab.tick(),lab.tick(),lab.tick()]
        self.assertEqual([x['kind'] for x in outcomes],['browse_route','additional_source','reflection'])
        self.assertEqual(seen[0]['additional_source']['receipt']['receipt_id'],observed['receipt_id'])
        self.assertEqual(lab._load(lab.STATE,{})['phase'],'orient')
        next_context,next_receipt=lab.lab_context()
        self.assertIn('RECENT LAB SOURCE',next_context)
        self.assertIn('123',next_context)
        self.assertTrue(any(x['name']=='recent_lab_source' for x in next_receipt['sources']))

    def test_gemma_can_choose_microbiology_without_named_organism_seed(self):
        selected={'browse_lane':'microbiology','source_query':{
            'source':'ncbi','operation':'literature','term':'colored wet surface communities'},
            'question':'What persists on wet surfaces?','why_now':'environmental curiosity'}
        prompts=[]
        def answer(system,prompt,**kwargs):
            prompts.append(prompt)
            return json.dumps(selected)
        with patch.object(lab,'_ask',side_effect=answer):
            inquiry=lab._orient('fixture context')
        self.assertEqual(inquiry['browse_lane'],'microbiology')
        self.assertEqual(inquiry['source_query'],selected['source_query'])
        self.assertIn('not a priority',prompts[0])
        self.assertNotIn('Serratia',prompts[0])

    def test_failed_microbiology_source_does_not_become_a_reflection(self):
        lab._ensure()
        lab._atomic(lab.STATE, {'phase':'sources','turns':0,'inquiry':{
            'browse_lane':'microbiology','source_query':{
                'source':'ncbi','operation':'taxonomy','term':'example genus'},
            'question':'Which taxon?'}})
        fake=types.SimpleNamespace(admit=lambda *a,**k:contextlib.nullcontext())
        with patch.dict(sys.modules,{'compute_admission':fake}), \
             patch.object(lab,'config',return_value={**lab.DEFAULTS,'enabled':True}), \
             patch.object(lab,'stop_requested',return_value=False), \
             patch.object(lab,'_reflect',side_effect=AssertionError('no observation to interpret')), \
             patch.object(bridge,'query',side_effect=RuntimeError('source unavailable')):
            outcome=lab.tick()
        self.assertEqual(outcome['kind'],'source_unavailable')
        self.assertEqual(lab._load(lab.STATE,{})['phase'],'orient')
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
