"""Exact failed two-call replay and presentation boundaries; no inference or network."""
import copy,json,os,pathlib,socket,subprocess,sys,tempfile,types,unittest
from unittest.mock import patch,Mock
scratch=tempfile.TemporaryDirectory(prefix='lab-partial-')
os.environ.update(HOME=scratch.name,SPARK_WORKSPACE=scratch.name+'/workspace',VINTOS_SECRETS=scratch.name+'/secrets')
def forbidden(*a,**k):raise AssertionError('external operation forbidden')
socket.socket.connect=forbidden;socket.create_connection=forbidden;subprocess.Popen=forbidden
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_lab as C,lab_sources as S
C._ask=forbidden;C.urllib.request.urlopen=forbidden;S.open_request=forbidden
assert all(str(p).startswith(scratch.name) for p in (C.ROOT,C.STATE,C.NOTEBOOK,C.RECEIPTS,C.FAULTS))
fixture=json.loads((pathlib.Path(__file__).parent/'fixtures/lab_oct11_mscs_failed_assessment.json').read_text())

def historical_prepared():
 # Exactly the request the two real responses answered, never relabel the output.
 body=fixture['coverage_request'];tree=json.loads(body['messages'][1]['content'].split('\nEVIDENCE:\n',1)[1]);strings={};addresses={}
 def unwrap(x,path):
  if isinstance(x,dict) and set(x)=={'address','text'}:
   strings[path]=x['text'];addresses[x['address']]=path;return x['text']
  if isinstance(x,dict):return {k:unwrap(v,path+'.'+k) for k,v in x.items()}
  if isinstance(x,list):return [unwrap(v,path+'.'+str(i)) for i,v in enumerate(x)]
  return x
 evidence=unwrap(tree,'evidence')
 return evidence,strings,addresses,(body['messages'][0]['content'],body['messages'][1]['content'],body['max_tokens'])

class PartialAssessment(unittest.TestCase):
 def reflect(self,prepared=None,responses=None,observations=None):
  data=copy.deepcopy(fixture['input']);before=copy.deepcopy(data)
  model=Mock(side_effect=responses or [fixture['reader']['text'],fixture['coverage']['text']])
  with patch.object(C,'_ask',model),patch.object(C,'_gap_text',return_value=''),patch.dict(sys.modules,{'lab_lines':types.SimpleNamespace(reflect_text=lambda _: '')}):
   if prepared:
    with patch.object(C,'_coverage_request',return_value=prepared):result=C._reflect('',data['inquiry'],observations or data['observations'])
   else:result=C._reflect('',data['inquiry'],observations or data['observations'])
  self.assertEqual(data,before)
  return result,model

 def test_exact_failed_pair_keeps_two_quotes_not_atlas_followup(self):
  result,model=self.reflect(historical_prepared())
  self.assertEqual(model.call_count,2);self.assertEqual(result['assessment_status'],'incomplete')
  self.assertEqual(result['evidence_status'],'partial');self.assertEqual(len(result['validated_source_excerpts']),2)
  self.assertEqual(len(result['coverage_check']['discarded_supports']),4)
  self.assertIn('source-address validation failed',result['validation_failure'])
  self.assertEqual(result['missing_evidence'],'')
  for field in ('attention','next_question','instrument_gap','speculative_reading'):self.assertEqual(result[field],'')
  self.assertNotIn('Atlas',result['factual_observation']);self.assertNotIn('hexamer',result['factual_observation'])
  self.assertEqual(result['reader_audit']['raw'],fixture['reader']['text'])
  self.assertIn('Atlas',result['reader_audit']['parsed']['next_question'])
  self.assertEqual(result['factual_observation'].count('[PMID 36499396]'),2)
  self.assertFalse(result['evidence_gap']['automatic_followup'])
  # Actual durable store round trip in scratch, with exact audit data.
  C._ensure();C._append(C.NOTEBOOK,dict(result,kind='reflection',inquiry=fixture['input']['inquiry']))
  saved=C._tail_jsonl(C.NOTEBOOK)[-1]
  self.assertEqual(saved['reader_audit'],result['reader_audit'])
  self.assertEqual(saved['validated_source_excerpts'],result['validated_source_excerpts'])

 def test_old_response_not_repaired_against_new_presentation(self):
  result,model=self.reflect()
  self.assertEqual(model.call_count,2);self.assertEqual(result['factual_observation'],'')
  self.assertEqual(len(result['coverage_check']['discarded_supports']),6)

 def test_readable_ids_and_metadata_preserve_every_original_field(self):
  data=fixture['input'];prepared=C._coverage_request(data['inquiry'],data['observations'])
  self.assertIn('PMID:12080120/abstract',prepared[2]);self.assertNotIn('PMID:12080120/journal',prepared[2])
  tree=json.loads(prepared[3][1].split('\nEVIDENCE:\n',1)[1])
  def unwrap(x):
   if isinstance(x,dict) and set(x)=={'address','text'}:return x['text']
   if isinstance(x,dict):return {k:unwrap(v) for k,v in x.items()}
   if isinstance(x,list):return [unwrap(v) for v in x]
   return x
  self.assertEqual(unwrap(tree),prepared[0])
  self.assertIsInstance(tree['LITERATURE'][2]['journal'],str)

 def test_duplicate_source_ids_remain_distinct_deterministic_and_exact(self):
  obs={'LITERATURE':[{'pmid':'7','abstract':'First text.'},{'pmid':'7','abstract':'Second text.'}]}
  p=C._coverage_request({'question':'original'},obs)
  self.assertEqual(p,C._coverage_request({'question':'original'},copy.deepcopy(obs)))
  self.assertEqual(len(p[2]),2);self.assertTrue(all(k.startswith('PMID:7/abstract#') for k in p[2]))
  address=next(k for k,v in p[2].items() if v.endswith('.0.abstract'))
  response={'answered':True,'missing':[],'supports':[{'requirement':'test','address':address,'quote':'Second text.'}]}
  with patch.object(C,'_ask',return_value=json.dumps(response)) as model:result=C._coverage_check({'question':'original'},obs)
  self.assertEqual(model.call_count,1);self.assertEqual(result['supports'],[])

 def test_scientific_summary_and_named_fields_outside_pubmed_remain_quotable(self):
  obs={'records':[{'accession':'P12345','summary':{'source':'measured by spectroscopy','year':'observed in 2024','title':'Measured conformation'},'function':'Bounded scientific finding'}],
       'additional_source':{'receipt':{'source':'reactome','records':[{'summary':{'text':'A scientific pathway summary.'}}]}}}
  p=C._coverage_request({'question':'What scientific observations were supplied?'},obs)
  paths=set(p[2].values())
  for field in ('source','year','title'):
   self.assertIn('evidence.records.0.summary.'+field,paths)
  self.assertIn('evidence.additional_source.records.0.summary.text',paths)

 def test_requested_bibliographic_facts_have_exact_addresses_and_full_check(self):
  inquiry={'question':'Which journal published this article, and what is its publication year?'}
  obs={'LITERATURE':[{'pmid':'7','journal':'Example Journal','year':'2024','abstract':'Scientific text.'}]}
  p=C._coverage_request(inquiry,obs)
  self.assertEqual(p[2]['PMID:7/journal'],'evidence.LITERATURE.0.journal')
  self.assertEqual(p[2]['PMID:7/year'],'evidence.LITERATURE.0.year')
  response={'answered':True,'missing':[],'supports':[{'requirement':'journal','address':'PMID:7/journal','quote':'Example Journal'},
              {'requirement':'publication year','address':'PMID:7/year','quote':'2024'}]}
  with patch.object(C,'_ask',side_effect=[json.dumps(response),json.dumps({'sufficient':True,'missing':[],'rationale':'Scripted metadata lookup, not mechanism.'})]) as model:
   result=C._coverage_check(inquiry,obs)
  self.assertEqual(model.call_count,2);self.assertTrue(result['answered'])

 def test_inapplicable_atlas_instructions_removed_but_real_atlas_retained(self):
  result,model=self.reflect()
  self.assertNotIn('WHAT AN ATLAS RECORD IS',model.call_args_list[0].args[0])
  obs=copy.deepcopy(fixture['input']['observations']);obs['additional_source']={'receipt':{'source':'atlas','records':[{'score':0.1}]}}
  result,model=self.reflect(observations=obs)
  self.assertIn('WHAT AN ATLAS RECORD IS',model.call_args_list[0].args[0])

 def test_failed_coverage_cannot_promote_either_positive_or_negative_reader(self):
  for verdict in ('yes: unsupported claim','no: Atlas record missing'):
   response=json.dumps({'answers_question':verdict,'factual_observation':'UNVERIFIED','next_question':'Get Atlas','attention':'Atlas'})
   result,model=self.reflect(responses=[response,'{}'])
   self.assertEqual(result['factual_observation'],'');self.assertEqual(result['missing_evidence'],'')
   self.assertEqual(result['next_question'],'');self.assertEqual(result['assessment_status'],'incomplete')

 def test_specific_negative_with_no_support_is_a_complete_coverage_verdict(self):
  inquiry={'question':'Which membrane-spanning ranges are established?'}
  obs={'records':[{'accession':'P12345','organism':'Homo sapiens'}]}
  response={'answered':False,'missing':['membrane-spanning ranges'],'supports':[]}
  with patch.object(C,'_ask',return_value=json.dumps(response)) as model:
   result=C._coverage_check(inquiry,obs)
  self.assertEqual(model.call_count,1);self.assertFalse(result['answered'])
  self.assertEqual(result['missing'],['membrane-spanning ranges']);self.assertEqual(result['supports'],[])
  self.assertNotIn('assessment_status',result)

 def test_positive_without_support_still_fails_closed(self):
  inquiry={'question':'Which membrane-spanning ranges are established?'}
  response={'answered':True,'missing':[],'supports':[]}
  with patch.object(C,'_ask',return_value=json.dumps(response)):
   result=C._coverage_check(inquiry,{'records':[{'accession':'P12345'}]})
  self.assertEqual(result['assessment_status'],'incomplete')
  self.assertIn('no source supports',result['validation_failure'])

 def test_invalid_reader_contract_is_audit_only(self):
  raw=json.dumps({'answers_question':'perhaps','factual_observation':'UNVERIFIED','next_question':'Get Atlas'})
  result,model=self.reflect(responses=[raw])
  self.assertEqual(model.call_count,1);self.assertEqual(result['factual_observation'],'')
  self.assertEqual(result['reader_audit']['raw'],raw);self.assertEqual(result['next_question'],'')

 def test_sufficiency_failure_preserves_exact_excerpts_without_full_answer(self):
  obs={'LITERATURE':[{'pmid':'1','abstract':'Exact source text.'}]};inquiry={'question':'Original question'}
  response={'answered':True,'missing':[],'supports':[{'requirement':'original','address':'PMID:1/abstract','quote':'Exact source text.'}]}
  with patch.object(C,'_ask',side_effect=[json.dumps(response),'{}']) as model:result=C._coverage_check(inquiry,obs)
  self.assertEqual(model.call_count,2);self.assertFalse(result['answered'])
  self.assertEqual(result['assessment_status'],'incomplete');self.assertEqual(len(result['supports']),1)

if __name__=='__main__':unittest.main()
