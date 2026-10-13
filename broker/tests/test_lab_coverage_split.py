"""Over-budget coverage is assessed in parts, not deferred (2026-10-13).

Evidence over Gemma's 35k budget was always deferred, and deferred work rarely came back: 93 passes and 48 reviews on
13 October. Now evidence that can be split is assessed part by part with the same checker; only supports quoted
verbatim at their exact address are kept, and the verdict and the independent sufficiency assessment are made on
those verified excerpts. Nothing is dropped or shortened to make it fit. What cannot be split is still deferred.

Isolation: HOME and SPARK_WORKSPACE are throwaway; sockets and urlopen raise; the model is a scripted stub."""
import json,os,pathlib,socket,sys,tempfile,unittest
from unittest.mock import patch
scratch=tempfile.TemporaryDirectory(prefix='lab-split-')
os.environ.update(HOME=scratch.name,SPARK_WORKSPACE=scratch.name+'/workspace',VINTOS_SECRETS=scratch.name+'/secrets')
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_lab as C
def denied(*a,**k):raise AssertionError('Model/network invocation forbidden')
socket.socket.connect=denied;socket.create_connection=denied;C.urllib.request.urlopen=denied;C._ask=denied

class Split(unittest.TestCase):
    def setUp(self):
        self.assertTrue(C.ROOT.startswith(scratch.name))
        self.q={'question':'Does the supplied literature show that KaiC phosphorylation cycles with a 24 hour period?'}
        # six articles, each well under the budget, together well over it
        self.obs={'records':[],'LITERATURE':[{'pmid':str(100+i),'abstract':('Filler sentence %d. '%i)*900+
                  ('KaiC phosphorylation oscillates with a period of about 24 hours.' if i==4 else '')} for i in range(6)]}
        self.prepared=C._coverage_request(self.q,self.obs)

    def test_too_big_whole_but_splittable(self):
        self.assertFalse(C._coverage_budget(self.prepared[3])['fits'])
        parts=C._coverage_parts(self.prepared)
        self.assertIsNotNone(parts); self.assertGreaterEqual(len(parts),2)
        self.assertTrue(all(C._coverage_budget(p)['fits'] for p in parts))
        # every article lands in exactly one part, whole
        joined=''.join(p[1] for p in parts)
        for a in self.obs['LITERATURE']: self.assertEqual(joined.count(a['abstract']),1)
        self.assertIsNone(C._coverage_deferral(self.q,self.obs,self.prepared))

    def test_parts_then_verdict_on_verified_excerpts(self):
        parts=C._coverage_parts(self.prepared)
        address=next(k for k,v in self.prepared[2].items() if v=='evidence.LITERATURE.4.abstract')
        support={'requirement':'24 hour period','address':address,'quote':'KaiC phosphorylation oscillates with a period of about 24 hours.'}
        fake={'requirement':'x','address':address,'quote':'a sentence that is not in the source'}
        replies=[]
        for p in parts:
            hit=address in p[1]
            replies.append({'answered':hit,'missing':[] if hit else ['period'],'supports':[support,fake] if hit else []})
        replies.append({'answered':True,'missing':[],'supports':[support]})
        replies.append({'sufficient':True,'missing':[],'rationale':'the excerpt states the period'})
        seen=[]
        def ask(system,prompt,max_tokens=500,temperature=0.75):
            seen.append(prompt); return json.dumps(replies[len(seen)-1])
        with patch.object(C,'_ask',side_effect=ask):
            result=C._coverage_check(self.q,self.obs)
        self.assertTrue(result['answered'],result)
        self.assertEqual(result['split_parts'],len(parts))
        self.assertEqual(len(seen),len(parts)+2)
        self.assertIn('verified_excerpts',seen[-2]); self.assertIn('verified_excerpts',seen[-1])
        self.assertNotIn('not in the source',seen[-2])           # an unverified quote never reaches the verdict
        self.assertTrue(all(C._coverage_budget(('',s,1100))['fits'] for s in seen))

    def test_no_support_in_any_part_is_a_plain_no(self):
        parts=C._coverage_parts(self.prepared)
        with patch.object(C,'_ask',side_effect=[json.dumps({'answered':False,'missing':['the period'],'supports':[]}) for _ in parts]):
            result=C._coverage_check(self.q,self.obs)
        self.assertFalse(result['answered']); self.assertEqual(result['missing'],['the period'])
        self.assertEqual(result['method'],'split_coverage_no_verified_support')

    def test_one_item_too_big_alone_is_still_deferred(self):
        self.obs['LITERATURE'][0]['abstract']='Distinct content '*6000
        prepared=C._coverage_request(self.q,self.obs)
        self.assertIsNone(C._coverage_parts(prepared))
        self.assertTrue(C._coverage_deferral(self.q,self.obs,prepared)['coverage_deferred'])

if __name__=='__main__':
    unittest.main()
