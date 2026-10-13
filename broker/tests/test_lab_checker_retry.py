"""A rejected checker answer is asked once more, with the reason (2026-10-13).

53 Lab reviews ended on a rejected checker answer, most for a quote or an address a little off. The checker is now
asked once more, told exactly what was rejected; the new answer is judged by the same rules and nothing in the first
is repaired or carried over. A model that did not answer at all (timeout) is not asked again.

Isolation: HOME and SPARK_WORKSPACE are throwaway; sockets and urlopen raise; the model is a scripted stub."""
import json,os,pathlib,socket,sys,tempfile,unittest
from unittest.mock import patch
scratch=tempfile.TemporaryDirectory(prefix='lab-retry-')
os.environ.update(HOME=scratch.name,SPARK_WORKSPACE=scratch.name+'/workspace',VINTOS_SECRETS=scratch.name+'/secrets')
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_lab as C
def denied(*a,**k):raise AssertionError('Model/network invocation forbidden')
socket.socket.connect=denied;socket.create_connection=denied;C.urllib.request.urlopen=denied;C._ask=denied

Q={'question':'What does the supplied source say about the period?'}
OBS={'LITERATURE':[{'pmid':'111','abstract':'The rhythm has a period of about 24 hours.'}]}

class Retry(unittest.TestCase):
    def setUp(self):
        self.assertTrue(C.ROOT.startswith(scratch.name))
        self.address=next(k for k,v in C._coverage_request(Q,OBS)[2].items() if v=='evidence.LITERATURE.0.abstract')

    def test_a_corrected_second_answer_completes_the_review(self):
        bad={'answered':True,'missing':[],'supports':[{'requirement':'period','address':self.address,'quote':'a period of exactly one day'}]}
        good={'answered':True,'missing':[],'supports':[{'requirement':'period','address':self.address,'quote':'a period of about 24 hours'}]}
        suff={'sufficient':True,'missing':[],'rationale':'the abstract states the period'}
        prompts=[]
        def ask(system,prompt,**k):
            prompts.append(prompt); return json.dumps([bad,good,suff][len(prompts)-1])
        with patch.object(C,'_ask',side_effect=ask):
            result=C._coverage_check(Q,OBS)
        self.assertTrue(result['answered']);self.assertNotIn('assessment_status',result)
        self.assertIn('source-address validation failed',result['first_attempt_failure'])
        self.assertIn('YOUR PREVIOUS ANSWER WAS REJECTED',prompts[1]);self.assertIn('quote_not_in_cited_source',prompts[1])
        self.assertEqual(result['supports'][0]['quote'],'a period of about 24 hours')   # the second answer's own quote

    def test_a_model_that_did_not_answer_is_not_asked_again(self):
        good={'answered':True,'missing':[],'supports':[{'requirement':'period','address':self.address,'quote':'a period of about 24 hours'}]}
        with patch.object(C,'_ask',side_effect=[json.dumps(good),TimeoutError('sufficiency timeout')]) as model:
            result=C._coverage_check(Q,OBS)
        self.assertEqual(model.call_count,2);self.assertEqual(result['assessment_status'],'incomplete')

if __name__=='__main__':
    unittest.main()
