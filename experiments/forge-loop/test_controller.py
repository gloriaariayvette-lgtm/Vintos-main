import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from controller import Controller, ControlAPI, ControlWSGI, Refused
from adapters import UnconnectedUSDWallet, publish_pending

OWNER='owner-'+'a'*40
WORKER='worker-'+'b'*40

class LoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.c=Controller(Path(self.tmp.name)/'atelier/loop.sqlite', OWNER, WORKER, 'https://fixture.invalid')
        self.assertTrue(self.c.path.is_relative_to(Path(self.tmp.name).resolve()))
        self.messages=[]
        self.send=lambda message:self.messages.append(message) or True
        self.assertEqual(self.send.__name__, '<lambda>')
    def create(self, **kw):
        return self.c.create(OWNER, 'Make a useful artifact', ['skill'], **kw)
    def test_continuous_feedback_and_completion(self):
        p=self.create();seen=[]
        def build(claim, context):
            seen.append(context['previous'])
            return dict(artifact={'iteration':context['cycles']+1},complete=context['cycles']==2,receipt={'charged_cents':0})
        self.assertEqual(self.c.drive(WORKER,p['id'],lambda c:{'capability':'skill'},build),'complete')
        self.assertEqual(seen,[None,{'iteration':1},{'iteration':2}])
        self.assertEqual(self.c.status(OWNER,p['id'])['cycles'],3)
    def test_cancel_inflight_keeps_artifact_but_prevents_next_cycle(self):
        p=self.create();calls=[]
        def build(claim, context):
            calls.append(claim)
            self.c.cancel(p['id'],p['cancel_token'])
            return dict(artifact={'kept':True},complete=False,receipt={'charged_cents':0})
        self.assertEqual(self.c.drive(WORKER,p['id'],lambda c:{'capability':'skill'},build),'cancelled')
        self.assertEqual(len(calls),1)
        self.assertEqual(len(self.c.end_private(OWNER,p['id'],'audit')),1)
    def test_scoped_post_cancel_and_no_read_authority(self):
        p=self.create();other=self.create();api=ControlAPI(self.c)
        self.assertEqual(api.handle('GET','/cancel/'+p['id'],'Bearer '+p['cancel_token'])[0],405)
        self.assertEqual(api.handle('POST','/cancel/'+other['id'],'Bearer '+p['cancel_token'])[0],403)
        self.assertEqual(api.handle('POST','/cancel/'+p['id'],'Bearer '+p['cancel_token'])[0],200)
        with self.assertRaises(Refused):self.c.status(p['cancel_token'],p['id'])
    def test_private_suppression_audit_and_no_deletion(self):
        p=self.create(private=True,private_until=time.time()+60)
        claim=self.c.claim(WORKER,p['id'],'skill')
        self.c.accept(WORKER,p['id'],claim['cycle_id'],{'secret':'draft'},False,{'charged_cents':0})
        self.assertEqual(publish_pending(self.c,OWNER,p['id'],p['cancel_token'],'fixture',self.send),0)
        self.assertNotIn('intent',self.c.status(OWNER,p['id']))
        audit=self.c.end_private(OWNER,p['id'],'audit');self.assertIn('draft',audit[0]['artifact'])
        self.assertEqual(publish_pending(self.c,OWNER,p['id'],p['cancel_token'],'fixture',self.send),1)
        self.assertNotIn('draft',json.dumps(self.messages))
        self.assertEqual(self.messages[0]['actions'][1]['method'],'POST')
        self.assertEqual(publish_pending(self.c,OWNER,p['id'],p['cancel_token'],'fixture',self.send),0)
    def test_paid_loop_never_falls_back_to_household_budget(self):
        p=self.create(ceiling_cents=500)
        self.assertIsNone(self.c.claim(WORKER,p['id'],'skill',100,wallet=UnconnectedUSDWallet()))
        self.assertEqual(self.c.status(OWNER,p['id'])['state'],'needs_authorization')
    def test_authority_boundaries_hold(self):
        for plan in [{'capability':'ungranted'},{'capability':'skill','recurring':True},{'capability':'skill','quote_cents':1}]:
            p=self.create();self.assertIsNone(self.c.claim(WORKER,p['id'],**plan))
        with self.assertRaises(Refused):self.c.create(WORKER,'x',['skill'])
        with self.assertRaises(Refused):self.c.create(OWNER,'x',['skill'],ceiling_cents=True)
    def test_competing_claims_and_restart_do_not_duplicate(self):
        p=self.create()
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            claims=list(pool.map(lambda _:self.c.claim(WORKER,p['id'],'skill'),range(4)))
        self.assertEqual(sum(x is not None for x in claims),1)
        restarted=Controller(self.c.path,OWNER,WORKER,'https://fixture.invalid')
        self.assertIsNone(restarted.claim(WORKER,p['id'],'skill'))
    def test_uncertain_outcome_is_not_automatically_retried(self):
        p=self.create()
        def fail(*a):raise TimeoutError('provider outcome unknown')
        with self.assertRaises(TimeoutError):self.c.drive(WORKER,p['id'],lambda c:{'capability':'skill'},fail)
        self.assertEqual(self.c.context(WORKER,p['id'])['state'],'reconciliation_required')
    def test_private_expiry_and_abandonment(self):
        p=self.create(private=True,private_until=time.time()+60)
        with self.c.db() as db:
            row=self.c._get(db,p['id']);row['private_until']=time.time()-1;self.c._save(db,row)
        self.assertFalse(self.c.status(OWNER,p['id'])['private'])
        self.c.end_private(WORKER,p['id'],'abandoned')
        self.assertIsNone(self.c.claim(WORKER,p['id'],'skill'))
    def test_unconfirmed_notification_remains_pending(self):
        p=self.create();self.c.claim(WORKER,p['id'],'ungranted')
        with self.assertRaises(RuntimeError):publish_pending(self.c,OWNER,p['id'],p['cancel_token'],'fixture',lambda _:False)
        self.assertEqual(len(self.c.notifications(OWNER,p['id'],p['cancel_token'],'fixture')),1)

    def test_owner_can_authorize_new_scope_but_cannot_restart_cancelled(self):
        p=self.create();self.c.claim(WORKER,p['id'],'new')
        with self.assertRaises(Refused):self.c.authorize(WORKER,p['id'],['new'],0)
        self.c.authorize(OWNER,p['id'],['new'],0)
        self.assertIsNotNone(self.c.claim(WORKER,p['id'],'new'))
        self.c.cancel(p['id'],p['cancel_token'])
        with self.assertRaises(Refused):self.c.authorize(OWNER,p['id'],['new'],0)
    def test_duplicate_accept_does_not_duplicate_artifact_or_spend(self):
        p=self.create();claim=self.c.claim(WORKER,p['id'],'skill')
        args=(WORKER,p['id'],claim['cycle_id'],{'v':1},True,{'charged_cents':0})
        self.c.accept(*args)
        with self.assertRaises(Refused):self.c.accept(*args)
        self.assertEqual(self.c.status(OWNER,p['id'])['cycles'],1)
    def test_wsgi_private_status_and_cancel(self):
        p=self.create(private=True,private_until=time.time()+60);api=ControlWSGI(self.c)
        def request(method,path,token=''):
            statuses=[]
            body=b''.join(api({'REQUEST_METHOD':method,'PATH_INFO':path,'HTTP_AUTHORIZATION':'Bearer '+token},lambda status,headers:statuses.append(status)))
            return statuses[0],json.loads(body)
        self.assertTrue(request('GET','/projects/'+p['id'])[0].startswith('403'))
        status,body=request('GET','/projects/'+p['id'],OWNER)
        self.assertNotIn('intent',body)
        self.assertTrue(request('POST','/cancel/'+p['id'],p['cancel_token'])[0].startswith('200'))
    def test_forge_review_failure_becomes_next_cycle_feedback(self):
        from adapters import ForgeSandboxBuilder
        builder=ForgeSandboxBuilder(lambda *a,**k:json.dumps({'module':'def skill(note): return note','test':'assert True'}),
                                    lambda *a,**k:'FAIL: incomplete acceptance',lambda *a: {'complete':True})
        result=builder({'capability':'skill','maximum_cents':0},{'intent':'fixture','previous':None})
        self.assertFalse(result['complete']);self.assertFalse(result['artifact']['verified'])
        self.assertIn('incomplete',result['artifact']['review'])

if __name__=='__main__':unittest.main()
