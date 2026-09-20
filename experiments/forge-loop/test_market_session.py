import copy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import time
import unittest
from taskmarket import ReadOnlyMarket, micro_usdc, screen, task_digest
from work_session import WorkSession


def fixture():
    task={'id':'0x'+'1'*64,'status':'open','phase':'active','mode':'bounty',
          'reward':'5000000','expiryTime':datetime.fromtimestamp(time.time()+7200,timezone.utc).isoformat(),
          'submissionWindowOpen':True,'stakeRequired':False,'taskVisibility':'public','platformFeeBps':500}
    assessment={'task_sha256':task_digest(task),'capability':'extract','required_tools':['parser'],
                'acceptance_check':'schema-v1','public_inputs_only':True,'external_effects':False,
                'cost_micro':0,'seconds':60,'probe':{'passed':True,'task_sha256':task_digest(task),
                'runtime_sha256':'fixture-runtime','at':time.time()}}
    inventory={'extract':{'enabled':True,'runtime_sha256':'fixture-runtime','tools':['parser'],'acceptance_checks':['schema-v1']}}
    return task,assessment,inventory


class Lab:
    def __init__(self):self.owner=None;self.restored=0;self.fail_restore=False;self.quiet=True
    def status(self):return {'enabled':True,'checkpoint':'fixture'}
    def pause(self,owner):self.owner=owner;return {'owner':owner,'quiescent':self.quiet}
    def restore(self,owner,before):
        if self.fail_restore:raise RuntimeError('fixture restore failure')
        assert self.owner in (None,owner)
        self.owner=None;self.restored+=1
        return {'restored':True,'enabled':before['enabled']}


class MarketTests(unittest.TestCase):
    def test_exact_units_and_read_only_discovery(self):
        self.assertEqual(micro_usdc('5000000'),5000000)
        for bad in ['5.0','1e6','-1',5,True]:
            with self.assertRaises(ValueError):micro_usdc(bad)
        calls=[];market=ReadOnlyMarket(lambda url:calls.append(url) or {'tasks':[]})
        market.discover();self.assertTrue(calls[0].startswith('https://api.taskmarket.dev/api/tasks?'))
        with self.assertRaises(ValueError):market.detail('../../wallet')
        self.assertFalse(hasattr(market,'submit'))
    def test_probe_not_model_confidence_admits_trial(self):
        t,a,i=fixture();self.assertTrue(screen(t,a,i)['eligible_local_trial'])
        a['probe']['passed']=False;a['confidence']=1
        self.assertFalse(screen(t,a,i)['eligible_local_trial'])
    def test_task_changes_runtime_changes_and_cost_refuse(self):
        for kind in ['task','runtime','cost','tools','deadline','stake']:
            t,a,i=fixture()
            if kind=='task':t['reward']='10'
            elif kind=='runtime':i['extract']['runtime_sha256']='different'
            elif kind=='cost':a['cost_micro']=1
            elif kind=='tools':a['required_tools']=['shell-on-host']
            elif kind=='deadline':a['seconds']=99999
            else:t['stakeRequired']=True
            self.assertFalse(screen(t,a,i)['eligible_local_trial'],kind)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.lab=Lab();self.messages=[];self.t,self.a,self.i=fixture()
        self.session=WorkSession(Path(self.tmp.name)/'session.json',self.lab,
             lambda p:self.messages.append(p) or True,cancel_url='https://fixture.invalid/cancel/x',cancel_token='fixture')
        self.assertTrue(self.session.path.is_relative_to(Path(self.tmp.name).resolve()))
        self.assertEqual(self.session.notify.__name__,'<lambda>')
    def run_session(self,perform=None,cancelled=lambda:False):
        return self.session.run(lambda:[self.t],lambda t:self.a,self.i,
              perform or (lambda t,**kw:{'artifact_sha256':'fixture','submitted':False}),cancelled)
    def test_work_restores_lab_and_builds_cancel_notifications(self):
        state=self.run_session();self.assertEqual(self.lab.restored,1)
        self.assertFalse(state['restore_due']);self.assertEqual(len(state['results']),1)
        self.assertTrue(all(p['actions'][0]['method']=='POST' for p in self.messages))
        self.assertIn('lab_restored',[e['kind'] for e in state['events']])
    def test_worker_failure_still_restores(self):
        def fail(*a,**k):raise RuntimeError('fixture worker failure')
        with self.assertRaises(RuntimeError):self.run_session(fail)
        self.assertEqual(self.lab.restored,1)
    def test_cancel_prevents_work_and_restores(self):
        state=self.run_session(cancelled=lambda:True)
        self.assertEqual(state['results'],[]);self.assertEqual(self.lab.restored,1)
    def test_restore_failure_survives_restart_and_recovers(self):
        self.lab.fail_restore=True
        with self.assertRaises(RuntimeError):self.run_session()
        import json
        state=json.loads(self.session.path.read_text());self.assertTrue(state['restore_due'])
        self.lab.fail_restore=False
        recovered=self.session.recover();self.assertFalse(recovered['restore_due'])
    def test_no_work_without_quiescent_checkpoint(self):
        self.lab.quiet=False;called=[]
        with self.assertRaises(RuntimeError):self.run_session(lambda *a,**k:called.append(1))
        self.assertEqual(called,[]);self.assertEqual(self.lab.restored,1)
    def test_notification_failure_does_not_prevent_restoration(self):
        def unavailable(*a):raise OSError('fixture notification unavailable')
        self.session.notify=unavailable;state=self.run_session()
        self.assertFalse(state['restore_due']);self.assertTrue(all(not e['sent'] for e in state['events']))

    def test_next_session_preserves_previous_receipts(self):
        first=self.run_session();self.run_session()
        self.assertTrue((self.session.path.parent/'sessions'/(first['id']+'.json')).exists())

class NotificationTests(unittest.TestCase):
    def test_transport_uses_explicit_topic_and_receipt(self):
        from ntfy_transport import NtfyPublisher
        import json
        calls=[]
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'{"event":"message","topic":"fixture","id":"id"}'
        def transport(request,timeout):
            calls.append((request,timeout));return Response()
        publish=NtfyPublisher('https://fixture.invalid','fixture','fixture-token',transport=transport)
        self.assertTrue(publish({'title':'Lab restored'}))
        self.assertEqual(json.loads(calls[0][0].data)['topic'],'fixture')
        self.assertEqual(calls[0][1],10)
        with self.assertRaises(ValueError):NtfyPublisher('http://fixture.invalid','fixture','token')

if __name__=='__main__':unittest.main()
