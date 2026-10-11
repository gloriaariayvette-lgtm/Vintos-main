"""The actual saved O43511 archive request reaches its source, without replaying a completed fold."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_lab_query_perimeter import Perimeter,C,REPO,forbidden,NET
import copy,json,shutil,unittest
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
from urllib.error import HTTPError
import lab_sources as S
import lab_lines as L
import lab_repeats as R
import lab_instruments as I
import chemistry_sources as CS

QUESTION='What is the precise mapping of the pendrin (O43511) protein domains, specifically the STAS domain and its orientation relative to the transmembrane helices?'
STEP='Query the structure archive by UniProt accession O43511. Return only entry identifiers, mapped accession, organism, experimental method, reported resolution, construct coverage and modeled residue coverage. Explicitly exclude P58743/7LGU from direct pendrin evidence; report unavailable coverage fields as unavailable rather than inferring them.'
SPEC={'source':'pdb','operation':'search_accession','accession':'O43511','exclude_accessions':['P58743'],'exclude_entries':['7LGU'],'limit':4}

# Deliberately synthetic transport payloads; identifiers are fixtures, not a
# claim that a real PDB entry contains O43511. No biological API is contacted.
def payloads():
    return {
      'search':{'total_count':3,'result_set':[{'identifier':'7LGU_1'},{'identifier':'1ABC_1'},{'identifier':'2ABC_1'}]},
      'polymer_entity/1ABC/1':{'rcsb_polymer_entity_container_identifiers':{'entry_id':'1ABC','entity_id':'1','asym_ids':['A'],
          'reference_sequence_identifiers':[{'database_name':'UniProt','database_accession':'O43511','reference_sequence_coverage':0.5}]},
          'rcsb_entity_source_organism':[{'ncbi_taxonomy_id':9606,'scientific_name':'Homo sapiens'}],
          'entity_poly':{'rcsb_sample_sequence_length':5},
          'rcsb_polymer_entity_align':[{'reference_database_name':'UniProt','reference_database_accession':'O43511',
              'aligned_regions':[{'entity_beg_seq_id':1,'ref_beg_seq_id':535,'length':5}]}]},
      'polymer_entity/2ABC/1':{'rcsb_polymer_entity_container_identifiers':{'entry_id':'2ABC','entity_id':'1',
          'reference_sequence_identifiers':[{'database_name':'UniProt','database_accession':'P58743'}]}},
      'entry/1ABC':{'rcsb_id':'1ABC','exptl':[{'method':'ELECTRON MICROSCOPY'}],'rcsb_entry_info':{'resolution_combined':[3.2]}},
      'polymer_entity_instance/1ABC/A':{'rcsb_polymer_entity_instance_container_identifiers':{
          'entry_id':'1ABC','entity_id':'1','asym_id':'A','auth_to_entity_poly_seq_mapping':['535','536','?','538','539']}}
    }

class ArchiveAssignment(unittest.TestCase):
    original_ground=staticmethod(C._ground_inquiry)
    def setUp(self):
        Perimeter.setUp(self)
        self.line={'id':'L-fd723427','state':'open','question':QUESTION,'next_step':STEP}
        self.stack.enter_context(patch.dict(sys.modules,{'lab_lines':L,'lab_instruments':I}))
        self.stack.enter_context(patch.object(L,'pick',return_value=None))
        self.stack.enter_context(patch.object(L,'open_lines',side_effect=lambda:[self.line]))
        self.stack.enter_context(patch.object(R,'frontier_step',return_value=None))
        self.stack.enter_context(patch.object(C,'spent_subjects',return_value=['Pendrin','STAS','O43511']))
        self.stack.enter_context(patch.object(C,'_ground_inquiry',wraps=self.original_ground))
        self.stack.enter_context(patch.object(C,'_browse',side_effect=forbidden))
        self.cftr=json.loads((REPO/'broker/tests/fixtures/cftr_coverage_deferred_20261011.json').read_text())['inquiry']
        self.cftr.update(refused='coverage deferred',evidence_status='insufficient',coverage_deferred=True)
        self.cftr['planning_evidence']=C._planning_evidence(self.cftr)
        C._append(C.NOTEBOOK,{'kind':'reflection','inquiry':self.cftr,'coverage_deferred':True})
        C._append(C.NOTEBOOK,{'kind':'inquiry_refused','inquiry':{'question':'spent SLC26 proposal'}})
        self.data=payloads();self.calls=[]
        self.client=S.Sources(fetch=self.fetch)
        self.assertTrue(str(R.LOOKUPS).startswith(C.WS));self.assertEqual(NET,[])

    def fetch(self,url):
        self.calls.append(url)
        if url.startswith('https://search.rcsb.org/rcsbsearch/v2/query?'):
            q=json.loads(parse_qs(urlparse(url).query)['json'][0])
            self.assertEqual(q['return_type'],'polymer_entity')
            self.assertEqual(q['query']['nodes'][1]['parameters']['value'],'O43511')
            self.assertEqual(q['request_options']['results_content_type'],['experimental'])
            return copy.deepcopy(self.data['search']),{}
        prefix='https://data.rcsb.org/rest/v1/core/'
        self.assertTrue(url.startswith(prefix),url)
        value=self.data[url[len(prefix):]]
        if isinstance(value,Exception):raise value
        return copy.deepcopy(value),{}

    def test_exact_saved_question_and_requirements_are_admitted(self):
        with patch.object(C,'_ask',side_effect=forbidden):got=C._orient('offline context')
        self.assertEqual(got['question'],QUESTION);self.assertEqual(got['source_query'],SPEC)
        self.assertEqual(got['line_id'],self.line['id'])
        self.assertEqual(got['planning_scope']['line']['next_step'],STEP)
        self.assertIsNotNone(C._held_question(self.cftr))
        self.assertIsNone(C._next_assigned_archive_step(R,{}))

    def test_metadata_mapping_excludes_wrong_target_without_claiming_uniprot_numbering(self):
        got=self.client.query(SPEC);self.assertEqual(len(got['records']),1)
        rec=got['records'][0];self.assertEqual(rec['mapped_accession'],'O43511')
        self.assertEqual(rec['construct_coverage']['alignment_regions'][0]['ref_beg_seq_id'],535)
        cov=rec['modeled_residue_coverage'][0]
        self.assertEqual(cov['modeled_entity_intervals'],[[1,2],[4,5]])
        self.assertIn('not asserted to be UniProt',cov['numbering'])
        self.assertEqual(len(got['metadata']['excluded_or_mismatched']),2)
        self.assertFalse(any('/7LGU/' in x for x in self.calls))

    def test_missing_coverage_stays_unavailable(self):
        self.data['polymer_entity/1ABC/1'].pop('rcsb_polymer_entity_align')
        self.data['polymer_entity_instance/1ABC/A']=HTTPError('fixture',404,'missing',{},None)
        self.data['entry/1ABC'].pop('rcsb_entry_info')
        got=self.client.query(SPEC)['records'][0]
        self.assertEqual(got['construct_coverage']['status'],'unavailable')
        self.assertEqual(got['modeled_residue_coverage'][0]['status'],'unavailable')
        self.assertIsNone(got['resolution_angstroms'])

    def test_wrong_entry_or_chain_identity_is_rejected(self):
        for field,key,value in [('entry/1ABC','rcsb_id','9XYZ'),
             ('polymer_entity_instance/1ABC/A','rcsb_polymer_entity_instance_container_identifiers',{'entry_id':'9XYZ'})]:
            old=copy.deepcopy(self.data);self.data[field][key]=value
            with self.assertRaisesRegex(ValueError,'identity'):self.client.query(SPEC)
            self.data=old

    def test_empty_search_is_not_an_error_or_biological_absence(self):
        self.data['search']={'result_set':[],'total_count':0}
        got=self.client.query(SPEC);self.assertEqual(got['records'],[])
        self.assertIn('not an assertion of biological absence',got['metadata']['meaning'])

    def test_documented_empty_http_response_is_recognized_only_for_archive_search(self):
        class Empty:
            status=204;headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b''
        transport=lambda *a,**k:Empty()
        result,_=S.fetch_json('https://search.rcsb.org/rcsbsearch/v2/query?json=fixture',transport=transport)
        self.assertEqual(result,{'result_set':[],'total_count':0})
        with self.assertRaises(ValueError):S.fetch_json('https://data.rcsb.org/rest/v1/core/entry/1ABC',transport=transport)

    def test_real_reflection_guard_uses_archive_identity_without_inventing_scientific_coverage(self):
        inquiry=C._inquiry({'question':QUESTION,'source_query':SPEC})
        evidence={'records':[],'additional_source':{'receipt':self.client.query(SPEC)},'LITERATURE':[]}
        with patch.object(C,'_ask',return_value=json.dumps({'answers_question':'partial','factual_observation':'',
                'missing_evidence':'orientation unavailable','next_question':''})) as model:
            result=C._reflect('offline context',inquiry,evidence)
        self.assertGreater(model.call_count,0,result)
        self.assertFalse((result.get('coverage_check') or {}).get('answered'))
        wrong=copy.deepcopy(evidence);wrong['additional_source']['receipt']['records'][0]['mapped_accession']='P58743'
        with patch.object(C,'_ask',side_effect=forbidden):rejected=C._reflect('offline context',inquiry,wrong)
        self.assertIn('requested target',rejected['missing_evidence'])

    def test_two_sequential_passes_do_not_reissue_completed_search_or_fold(self):
        folder=I.ARTIFACTS/'fold-read';folder.mkdir(parents=True)
        shutil.copyfile(REPO/'broker/tests/fixtures/completed_pendrin_654_729.json',folder/'done.json')
        reflection={'answers_question':'partial: archive mapping is available; domain orientation remains unresolved',
            'factual_observation':'Offline fixture reports an exact accession mapping.',
            'original_question':QUESTION,'missing_evidence':'Orientation is not established by metadata.',
            'next_question':'','line_status':'continue'}
        with patch.object(C,'_ask',side_effect=forbidden), \
             patch.object(CS,'configured_sources',return_value=self.client), \
             patch.object(CS,'offer_report',return_value=None), \
             patch.object(C,'_gather_material',return_value=False), \
             patch.object(C,'_reflect',return_value=reflection) as review, \
             patch.object(L,'after_reflection',return_value=''), \
             patch.object(I,'run',side_effect=forbidden):
            self.assertEqual([C.tick().get('kind') for _ in range(3)],['inquiry','additional_source','reflection'])
        first_calls=len(self.calls)
        self.assertEqual(review.call_args.args[1]['question'],QUESTION)
        self.assertEqual(review.call_args.args[2]['additional_source']['receipt']['records'][0]['mapped_accession'],'O43511')
        C._append(C.NOTEBOOK,{'kind':'inquiry_refused','inquiry':{'question':'another spent proposal'}})
        with patch.object(C,'_ask',return_value=json.dumps(self.cftr)), patch.object(I,'run',side_effect=forbidden):
            self.assertEqual(C.tick()['kind'],'evidence_wait')
        self.assertEqual(len(self.calls),first_calls)
        self.assertIsNotNone(C._held_question(self.cftr));self.assertEqual(NET,[])

if __name__=='__main__':unittest.main()
