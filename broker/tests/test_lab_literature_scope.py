"""Actual saved postrollout failures; all provider replies are stubs, not live validation."""
import copy, io, json, os, pathlib, socket, subprocess, sys, tempfile, types, unittest
from unittest.mock import patch, Mock
scratch=tempfile.TemporaryDirectory(prefix='lab-literature-scope-')
os.environ.update(HOME=scratch.name,SPARK_WORKSPACE=scratch.name+'/workspace',VINTOS_SECRETS=scratch.name+'/secrets')
def forbidden(*a,**k): raise AssertionError('external operation blocked')
socket.socket.connect=forbidden;socket.create_connection=forbidden;subprocess.Popen=forbidden
sys.path.insert(0,os.environ.get('LAB_REPLAY_SCRIPTS',str(pathlib.Path(__file__).resolve().parents[2]/'scripts')))
import chemistry_lab as C, lab_sources as S, lab_repeats as R
C._ask=forbidden;C.urllib.request.urlopen=forbidden;S.open_request=forbidden
assert all(str(p).startswith(scratch.name) for p in (C.ROOT,C.STATE,C.NOTEBOOK,C.RECEIPTS,C.FAULTS,R.LOOKUPS))
assert C._ask is forbidden and S.open_request is forbidden and subprocess.Popen is forbidden
fixture=json.loads((pathlib.Path(__file__).parent/'fixtures/lab_oct11_literature_scope.json').read_text())
mscs=fixture['mscs'];soxr=fixture['soxr'];receipt=fixture['soxr_receipt'];papers=fixture['mscs_abstracts']

class LiteratureScope(unittest.TestCase):
 def test_actual_mscs_conflict_preserves_original(self):
  original=copy.deepcopy(mscs)
  result=C._ground_inquiry(mscs,client=types.SimpleNamespace(human_gene_identity=forbidden))
  self.assertEqual(result['status'],'unresolved');self.assertIn('contradicts human',result['reason'])
  self.assertEqual(mscs,original)
  self.assertEqual(S.question_entity_context(mscs,[])['question_species'],['Escherichia coli'])

 def test_actual_soxr_not_assigned_an_organism(self):
  original=copy.deepcopy(soxr)
  result=S.question_entity_context(soxr,[],literature_only=True)
  self.assertEqual(result['status'],'requires_source_assessment')
  self.assertEqual(result['taxa'],['9606']);self.assertEqual(result['selected_accessions'],[])
  self.assertEqual(soxr,original)

 def test_actual_soxr_metadata_is_missing_not_contradictory(self):
  result=C._reflect('',soxr,{'records':[],'LITERATURE':[],'additional_source':{'receipt':receipt}})
  self.assertIn('no substantive article',result['answers_question'])
  self.assertEqual(result['factual_observation'],'')
  self.assertEqual(result['entity_context_check']['status'],'requires_source_assessment')

 def test_mscs_contradiction_not_bypassed_by_literature(self):
  result=C._reflect('',mscs,{'records':[],'LITERATURE':papers})
  self.assertIn('contradicts human',result['answers_question'])

 def strain_context(self,lineage):
  # Synthetic source-shaped boundary: no lookup and no hard-coded strain mapping.
  inquiry=C._inquiry({'question':'Describe MscS in E. coli.',
      'uniprot_query':'protein_name:MscS AND organism_id:511145 AND reviewed:true'})
  row={'accession':'P0A742','protein_name':'MscS','taxon_id':511145,
       'organism':'Escherichia coli (strain K12)','organism_lineage':lineage}
  return inquiry,row

 def test_species_question_known_strain_lineage_is_consistent(self):
  inquiry,row=self.strain_context(['Bacteria','Escherichia','Escherichia coli'])
  original=copy.deepcopy(inquiry)
  result=S.question_entity_context(inquiry,[row])
  self.assertEqual(result['status'],'consistent');self.assertEqual(inquiry,original)
  self.assertEqual(result['taxa'],['511145'])

 def test_unknown_strain_lineage_is_unresolved_not_contradictory(self):
  inquiry,row=self.strain_context([])
  result=S.question_entity_context(inquiry,[row])
  self.assertEqual(result['status'],'unresolved')
  self.assertIn('species/strain relationship is unresolved','; '.join(result['issues']))
  self.assertNotIn('contradict','; '.join(result['issues']))
  # A name prefix alone is not authoritative lineage and is not used to fill it.
  self.assertEqual(C._ground_inquiry(inquiry)['status'],'not_applicable')

 def test_wrong_strain_id_is_not_rewritten_or_broadened(self):
  inquiry,row=self.strain_context(['Escherichia coli']);row['taxon_id']=83333
  result=S.question_entity_context(inquiry,[row])
  self.assertEqual(result['status'],'unresolved')
  self.assertIn('requested taxon is not established','; '.join(result['issues']))

 def test_browse_preserves_source_lineage_without_network_expansion(self):
  item={'primaryAccession':'P0A742','proteinDescription':{'recommendedName':{'fullName':{'value':'MscS'}}},
        'organism':{'taxonId':511145,'scientificName':'Escherichia coli (strain K12)',
                    'lineage':['Bacteria','Escherichia','Escherichia coli']},
        'sequence':{'value':'M'*40,'length':40}}
  with patch.object(C.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps({'results':[item]}).encode())) as fetch:
   result=C._browse('protein_name:MscS AND organism_id:511145 AND reviewed:true',1)
  self.assertEqual(fetch.call_count,1)
  self.assertEqual(result['records'][0]['organism_lineage'],item['organism']['lineage'])

 def test_protein_route_still_requires_records(self):
  inquiry=dict(soxr,browse_lane='protein')
  result=C._reflect('',inquiry,{'records':[],'LITERATURE':papers})
  self.assertIn('no retrieved record',result['answers_question'])

 def test_exact_accession_and_gene_identity_still_require_records(self):
  for query in ('accession:O43511','gene:SLC26A4 AND organism_id:9606'):
   inquiry=C._inquiry({'browse_lane':'microbiology','question':'Describe the named target.',
                      'uniprot_query':query,'source_query':soxr['source_query']})
   result=C._reflect('',inquiry,{'records':[],'LITERATURE':papers})
   self.assertIn('no retrieved record',result['answers_question'])

 def test_real_returned_pubmed_id_reaches_existing_material_reader(self):
  state={'additional_source':{'receipt':receipt}};original=copy.deepcopy(soxr)
  material=Mock(return_value={'records':[]})
  with patch.dict(sys.modules,{'chemistry_sources':types.SimpleNamespace(material=material)}):
   self.assertFalse(C._gather_material(state,soxr))
  material.assert_called_once_with(soxr,primary_pmids=['15292172'])
  self.assertEqual(soxr,original)

 def test_invalid_and_duplicate_pubmed_ids_not_passed(self):
  data=copy.deepcopy(receipt);data['records']=[{'uid':v} for v in ['bad','1','1','2','3','4']]
  material=Mock(return_value={'records':[]})
  with patch.dict(sys.modules,{'chemistry_sources':types.SimpleNamespace(material=material)}):
   C._gather_material({'additional_source':{'receipt':data}},soxr)
  self.assertEqual(material.call_args.kwargs,{'primary_pmids':['1','2','3']})

 def exercise_literature(self,inquiry,sufficient):
  original=copy.deepcopy(inquiry);observations={'records':[],'LITERATURE':papers}
  prepared=C._coverage_request(inquiry,observations)
  address=next(k for k,p in prepared[2].items() if p=='evidence.LITERATURE.0.abstract')
  quote=papers[0]['abstract'].split('. ')[0]+'.'
  responses=[{'answers_question':'yes: reader claim','factual_observation':'UNSUPPORTED READER CLAIM'},
   {'answered':True,'missing':[],'supports':[{'requirement':'original mechanism','address':address,'quote':quote}]},
   {'sufficient':sufficient,'missing':[] if sufficient else ['original species and causal premise remain unestablished'],
    'rationale':'mocked boundary verdict, not scientific validation'}]
  asks=Mock(side_effect=[json.dumps(x) for x in responses])
  with patch.object(C,'_ask',asks),patch.object(C,'_gap_text',return_value=''),patch.dict(sys.modules,{'lab_lines':types.SimpleNamespace(reflect_text=lambda _: '')}):
   result=C._reflect('',inquiry,observations)
  self.assertEqual(asks.call_count,3);self.assertEqual(inquiry,original)
  for call in asks.call_args_list[1:]:
   self.assertIn(inquiry['question'],call.args[1])
   self.assertIn('original_identity_queries',call.args[1])
  self.assertNotIn('UNSUPPORTED READER CLAIM',result['factual_observation'])
  return result

 def test_correctly_scoped_literature_reaches_exact_quote_assessment(self):
  # Historical MscS query and question, without inventing a new species filter.
  result=self.exercise_literature(fixture['earlier_mscs'],True)
  self.assertTrue(result['answers_question'].startswith('yes:'))
  self.assertEqual(result['entity_context_check']['selected_accessions'],[])
  self.assertEqual(result['entity_context_check']['status'],'requires_source_assessment')

 def test_actual_soxr_scope_and_false_premise_can_defeat_reader_yes(self):
  result=self.exercise_literature(soxr,False)
  self.assertTrue(result['answers_question'].startswith('no:'))
  self.assertIn('causal premise',result['missing_evidence'])
  self.assertEqual(result['entity_context_check']['taxa'],['9606'])

 def test_coverage_keeps_scope_and_does_not_assume_signal_binding(self):
  for req in (C._coverage_request(soxr,{'records':[],'LITERATURE':papers})[3],C._coverage_sufficiency_request(soxr,{})):
   self.assertIn('9606',req[1]);self.assertIn('premise',req[0]);self.assertIn('species',req[0])
  changed=dict(soxr,uniprot_query='protein_name:SoxR AND organism_id:562')
  self.assertEqual(C._coverage_scope(changed)['original_identity_queries'],soxr['identity_context']['original_queries'])

if __name__=='__main__':unittest.main()
