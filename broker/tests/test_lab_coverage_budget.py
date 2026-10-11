"""Coverage overflow is an explicit durable deferral, never a shortened answer."""
import copy,json,os,pathlib,shutil,socket,sys,tempfile,unittest
from unittest.mock import patch
scratch=tempfile.TemporaryDirectory(prefix='lab-budget-')
os.environ.update(HOME=scratch.name,SPARK_WORKSPACE=scratch.name+'/workspace',VINTOS_SECRETS=scratch.name+'/secrets')
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_lab as C
def denied(*a,**k):raise AssertionError('Model/network invocation forbidden')
socket.socket.connect=denied;socket.create_connection=denied;C.urllib.request.urlopen=denied;C._ask=denied

class Budget(unittest.TestCase):
 def setUp(self):
  shutil.rmtree(C.ROOT,ignore_errors=True)
  self.q={'question':'What does the supplied source establish?'}
  self.obs={'records':[],'LITERATURE':[{'pmid':'111','abstract':'Complete unique evidence.'}]}
 def test_exact_boundary_and_one_byte_over_include_stage_output(self):
  prepared=C._coverage_request(self.q,self.obs)
  request=prepared[3];cost=C._coverage_budget(request)['conservative_total']
  self.assertEqual(C._coverage_budget(request)['output_reservation'],1100)
  self.assertEqual(C._coverage_budget(C._coverage_sufficiency_request(self.q,prepared[0]))['output_reservation'],800)
  with patch.object(C,'COVERAGE_CONTEXT_BUDGET',cost):
   self.assertIsNone(C._coverage_preflight(self.q,self.obs,prepared))
  with patch.object(C,'COVERAGE_CONTEXT_BUDGET',cost-1):
   deferred=C._coverage_check(self.q,self.obs)
  self.assertTrue(deferred['coverage_deferred'])
  self.assertIn('1100 output',deferred['missing_evidence'])
 def test_full_unicode_question_and_distinct_evidence_preserved_no_call(self):
  self.q['question']+=' 漢'*17000
  self.obs['LITERATURE'].append({'pmid':'222','abstract':'Different final source, never truncate me.'})
  before=copy.deepcopy((self.q,self.obs))
  result=C._reflect('',self.q,self.obs)
  self.assertEqual(result['evidence_status'],'deferred')
  self.assertEqual(result['original_question'],self.q['question'])
  saved=json.loads(pathlib.Path(result['coverage_snapshot']).read_text())
  self.assertEqual(saved['inquiry'],self.q);self.assertEqual(saved['observations'],self.obs)
  self.assertEqual((self.q,self.obs),before)
  self.assertEqual(result['factual_observation'],'');self.assertEqual(result['next_question'],'')
 def test_same_oversized_evidence_remains_durable_without_rewrite_or_model(self):
  self.obs['LITERATURE'][0]['abstract']='Distinct content '*6000
  first=C._reflect('',self.q,self.obs);path=pathlib.Path(first['coverage_snapshot']);stat=path.stat()
  second=C._reflect('',copy.deepcopy(self.q),copy.deepcopy(self.obs))
  self.assertEqual(first,second);self.assertEqual(path.stat().st_mtime_ns,stat.st_mtime_ns)
  self.assertEqual(len(list(path.parent.glob('*.json'))),1)
 def test_new_evidence_rechecked_old_evidence_retained(self):
  oversized=copy.deepcopy(self.obs);oversized['LITERATURE'][0]['abstract']='Old large evidence '*6000
  deferred=C._reflect('',self.q,oversized)
  before=pathlib.Path(deferred['coverage_snapshot']).read_bytes()
  prepared=C._coverage_request(self.q,self.obs)
  self.assertIsNone(C._coverage_preflight(self.q,self.obs,prepared))
  address=next(k for k,v in prepared[2].items() if v=='evidence.LITERATURE.0.abstract')
  replies=[{'answered':True,'missing':[],'supports':[{'requirement':'source','address':address,'quote':'Complete unique evidence.'}]},
           {'sufficient':True,'missing':[],'rationale':'Scripted offline sufficiency.'}]
  with patch.object(C,'_ask',side_effect=[json.dumps(x) for x in replies]) as calls:
   accepted=C._coverage_check(self.q,self.obs)
  self.assertTrue(accepted['answered']);self.assertEqual(calls.call_count,2)
  self.assertEqual(pathlib.Path(deferred['coverage_snapshot']).read_bytes(),before)
 def test_independent_stage_cannot_be_silently_shortened(self):
  self.obs['LITERATURE'][0]['abstract']='Complete evidence '*2300
  prepared=C._coverage_request(self.q,self.obs)
  prompt=C._coverage_sufficiency_request(self.q,prepared[0])[1]
  self.assertEqual(json.loads(prompt.split('\nEVIDENCE:\n')[1]),prepared[0])
  deferred=C._coverage_check(self.q,self.obs)
  self.assertFalse(deferred['coverage_budget']['independent_sufficiency']['fits'])
 def test_snapshot_write_failure_cannot_fall_through_to_reader(self):
  self.obs['LITERATURE'][0]['abstract']='Overflow '*6000
  with patch.object(C,'_atomic',side_effect=OSError('disk unavailable')):
   with self.assertRaises(OSError):C._reflect('',self.q,self.obs)

if __name__=='__main__':unittest.main()
