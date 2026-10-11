"""Offline address protocol tests. Scripted verdicts are not scientific acceptance."""
import copy, hashlib, json, os, pathlib, socket, sys, tempfile, unittest
from unittest.mock import patch
scratch=tempfile.TemporaryDirectory(prefix='lab-address-')
os.environ.update(HOME=scratch.name,SPARK_WORKSPACE=scratch.name+'/workspace',VINTOS_SECRETS=scratch.name+'/secrets')
def denied(*a,**k):raise AssertionError('No network or inference permitted')
socket.socket.connect=denied;socket.create_connection=denied
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_lab as C
C._ask=denied;C.urllib.request.urlopen=denied

def address_table(prompt):
 tree=json.loads(prompt.split('\nEVIDENCE:\n',1)[1]);table={}
 def walk(value,path):
  if isinstance(value,dict) and set(value)=={'address','text'}:
   table[value['address']]=path
  elif isinstance(value,dict):
   for key,child in value.items():walk(child,path+'.'+str(key))
  elif isinstance(value,list):
   for index,child in enumerate(value):walk(child,path+'.'+str(index))
 walk(tree,'evidence');return table

class Addresses(unittest.TestCase):
 def run_check(self, mutate=lambda a:a):
  obs={'LITERATURE':[{'pmid':'111','abstract':'Shared text. First source only.'},{'pmid':'222','abstract':'Shared text. Second source only.'}]}
  calls=[]
  def model(system,prompt,**kw):
   calls.append(prompt)
   if 'Independently assess' in system:
    self.assertNotIn('EVIDENCE ADDRESSES:',prompt)
    return json.dumps({'sufficient':True,'missing':[],'rationale':'Scripted sufficiency; not scientific proof.'})
   table=address_table(prompt)
   key=next(k for k,v in table.items() if v=='evidence.LITERATURE.1.abstract')
   support={'requirement':'test requirement','address':key,'quote':'Shared text.'}
   return json.dumps({'answered':True,'missing':[],'supports':[mutate(support)]})
  before=copy.deepcopy(obs)
  with patch.object(C,'_ask',side_effect=model): result=C._coverage_check({'question':'Original unchanged question'},obs)
  self.assertEqual(obs,before)
  return result,calls
 def test_exact_emitted_address_repeated_text_stays_in_selected_source(self):
  result,calls=self.run_check()
  self.assertEqual(result['supports'][0]['source_citation'],'PMID 222')
  self.assertEqual(result['supports'][0]['path'],'evidence.LITERATURE.1.abstract')
  self.assertEqual(len(calls),2)
  self.assertEqual(result['original_question'],'Original unchanged question')
  self.assertEqual(calls,self.run_check()[1])
 def test_unknown_address_rejected_without_sufficiency(self):
  result,calls=self.run_check(lambda s:dict(s,address='ev:unknown'))
  self.assertEqual(result["assessment_status"],"incomplete");self.assertEqual(len(calls),1)
 def test_real_quote_wrong_source_rejected_without_cross_record_search(self):
  result,calls=self.run_check(lambda s:dict(s,quote='First source only.'))
  self.assertEqual(result["assessment_status"],"incomplete");self.assertEqual(len(calls),1)
 def test_path_only_rejected(self):
  result,calls=self.run_check(lambda s:{'requirement':s['requirement'],'path':'LITERATURE[2].abstract','quote':s['quote']})
  self.assertEqual(result["assessment_status"],"incomplete");self.assertEqual(len(calls),1)
 def test_retained_live_response_is_rejected_not_repaired(self):
  fixtures=pathlib.Path(__file__).parent/'fixtures'
  data=json.loads((fixtures/'lab_oct11_input_retained.json').read_text())
  raw=json.loads((fixtures/'lab_oct11_coverage_retained.json').read_text())['text']
  with patch.object(C,'_ask',return_value=raw) as calls:
   self.assertEqual(C._coverage_check(data['inquiry'],data['observations'])['assessment_status'],'incomplete')
  self.assertEqual(calls.call_count,1)
 def test_retained_reader_prose_replaced_in_scripted_address_protocol(self):
  fixtures=pathlib.Path(__file__).parent/'fixtures'
  data=json.loads((fixtures/'lab_oct11_input_retained.json').read_text())
  reader=json.loads((fixtures/'lab_oct11_reader_retained.json').read_text())['text']
  old=C._json_object(json.loads((fixtures/'lab_oct11_coverage_retained.json').read_text())['text'])
  # Independently authored source mapping for this fixture only. No runtime
  # index correction or quote search; the raw live verdict remains rejected.
  pmids=['27386547','23856260','23856260','27746744','27386547']
  evidence=C.review_observations(data['inquiry'],data['observations'])
  calls=[]
  def model(system,prompt,**kw):
   calls.append(prompt)
   if 'reading sourced' in system:return reader
   if 'Independently assess' in system:
    return json.dumps({'sufficient':True,'missing':[],'rationale':'Scripted positive sufficiency, not a fresh scientific adjudication.'})
   table=address_table(prompt);supports=[]
   for item,pmid in zip(old['supports'],pmids):
    index=next(i for i,row in enumerate(evidence['LITERATURE']) if str(row['pmid'])==pmid)
    path='evidence.LITERATURE.'+str(index)+'.abstract'
    address=next(k for k,v in table.items() if v==path)
    supports.append({'requirement':item['requirement']+' chemical coordination at 3.2 Å; 5FBH at 2.1 Å','quote':item['quote'],'address':address})
   return json.dumps({'answered':True,'missing':[],'supports':supports})
  original=copy.deepcopy(data)
  with patch.object(C,'_ask',side_effect=model):result=C._reflect(data['context'],data['inquiry'],data['observations'])
  self.assertEqual(data,original);self.assertEqual(len(calls),3)
  self.assertTrue(result['answers_question'].startswith('yes:'))
  accepted=result['factual_observation']
  self.assertNotIn('3.2',accepted);self.assertNotIn('2.1',accepted)
  self.assertNotIn('5FBH',accepted);self.assertNotIn('chemical coordination',accepted)
  self.assertNotEqual(accepted,C._json_object(reader)['factual_observation'])
  self.assertEqual(result['coverage_check']['original_question'],data['inquiry']['question'])

if __name__=='__main__':unittest.main()
