"""Offline regression tests: every writable path is scratch; transport is a stub."""
import asyncio
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
SCRATCH = tempfile.TemporaryDirectory(prefix='security-alarm-')
os.environ['HOME'] = SCRATCH.name
os.environ['SPARK_WORKSPACE'] = str(Path(SCRATCH.name)/'workspace')
sys.path.insert(0, str(REPO/'scripts'))
def forbidden(*a, **k): raise AssertionError('network forbidden in security suite')
socket.socket.connect = forbidden
socket.create_connection = forbidden
import paid_http as P
import security_alarm as A
import compute_admission as C
import fault_sweep as F
import deliver as D

class SecurityTests(unittest.TestCase):
    def setUp(self):
        for p in Path(SCRATCH.name).rglob('*'):
            if p.is_file(): p.unlink()
        P._last_failure.clear()
        self.mem=P.workspace()/'memory'; self.mem.mkdir(parents=True, exist_ok=True)
        self.ledger=self.mem/'compute-ledger.jsonl'
        self.now=2000000000
        self.sent=[]
        self.host={'files':{'user-crontab':'old','/home/test/.ssh/authorized_keys':'old'},'deployed':{},'release':'good.json'}
        self.sender=lambda *a, **k: self.sent.append((a,k)) or {'state':'sent'}
        self.calls=[]
        self.transport=lambda *a, **k: self.calls.append((a,k)) or 'ok'
        self.assertTrue(str(self.mem).startswith(SCRATCH.name))
        self.assertIs(socket.socket.connect, forbidden)
        self.assertEqual(P.pause_path().parent,Path(SCRATCH.name)/'.vintos')

    def rows(self, rows):
        with self.ledger.open('a') as f:
            for row in rows:f.write(json.dumps(row)+'\n')

    def attempts(self,n, provider='anthropic',at=None,script='scripts/test.py'):
        self.rows([{'class':'outbound','stage':'attempt','epoch':self.now-1 if at is None else at,
                    'provider':provider,'script':script} for _ in range(n)])

    def tick(self, **kwargs):
        return A.tend(now=kwargs.pop('now',self.now),snapshot=kwargs.pop('snapshot',self.host),
                      logins=kwargs.pop('logins',[]),sender=kwargs.pop('sender',self.sender),**kwargs)

    def test_attempt_failure_counted_before_send(self):
        def fail(*a,**k):raise TimeoutError('synthetic')
        with self.assertRaises(TimeoutError):P.send(fail,'scripts/test.py','https://api.anthropic.com/v1/messages')
        rows=[json.loads(x) for x in self.ledger.read_text().splitlines()]
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['stage'],'attempt')

    def test_no_credentials_or_prompts_recorded(self):
        P.send(self.transport,'test.py','https://api.openai.com/v1/responses?token=SENSITIVE',headers={'Authorization':'SENSITIVE'},json={'prompt':'PRIVATE'})
        text=self.ledger.read_text();self.assertNotIn('SENSITIVE',text);self.assertNotIn('PRIVATE',text)
        self.assertEqual(self.calls[0][1]['headers'],{'Authorization':'SENSITIVE'})

    def test_local_and_nonprovider_unchanged(self):
        for u in ['http://127.0.0.1:8599/v1/chat/completions','http://172.18.16.1:1234','https://example.org','https://api.openai.com.evil.test']:
            self.assertEqual(P.send(self.transport,'t',u),'ok')
        self.assertFalse(self.ledger.exists())

    def test_pause_all_paid_and_resume(self):
        P.main(['pause'])
        for host in P.HOSTS:
            with self.assertRaises(PermissionError):P.send(self.transport,'t','https://'+host+'/v1')
        self.assertEqual(self.calls,[])
        self.assertEqual(P.send(self.transport,'t','http://localhost:1234'),'ok')
        P.main(['resume']);self.assertEqual(P.send(self.transport,'t','https://api.x.ai/v1'),'ok')

    def test_async_and_request_object(self):
        async def send(*a,**k):return 42
        self.assertEqual(asyncio.run(P.asend(send,'test.py','https://api.openai.com')),42)
        import urllib.request
        P.send(self.transport,'test.py',urllib.request.Request('https://api.anthropic.com',data=b'private'))
        self.assertEqual(len(self.ledger.read_text().splitlines()),2)

    def test_persistence_failure_is_observed_and_transport_continues(self):
        old=C.record
        def fail(*a,**k):raise OSError('SENSITIVE exception detail must not escape')
        C.record=fail
        try:
            self.assertEqual(P.send(self.transport,'test.py','https://api.openai.com'),'ok')
            self.assertEqual(len(self.calls),1)
            evidence=(self.mem/'organ-failures.jsonl').read_text()
            self.assertNotIn('SENSITIVE',evidence)
            self.assertEqual(json.loads(evidence)['what'],'provider_accounting_failed')
            self.assertTrue(F.organ_failures(0))
            self.assertEqual(self.tick(now=__import__('time').time())['sent'],1)
            self.assertIn('rate UNKNOWN',self.sent[0][1]['message'])
        finally:C.record=old

    def test_fault_sink_failure_cannot_block_sync_async_or_curl(self):
        import contextlib, io
        from unittest.mock import patch
        def fail(*a,**k):raise OSError('SENSITIVE full')
        async def send(*a,**k):return 'async-ok'
        stderr=io.StringIO()
        with patch.object(C,'record',fail),patch.object(P.os,'open',fail),contextlib.redirect_stderr(stderr):
            self.assertEqual(P.send(self.transport,'test.py','https://api.openai.com'),'ok')
            self.assertEqual(asyncio.run(P.asend(send,'test.py','https://api.x.ai')),'async-ok')
            with patch('subprocess.call',lambda *a,**k:37):
                self.assertEqual(P.main(['curl','test.sh','--','https://api.anthropic.com']),37)
        self.assertIn(P.FAILURE_PREFIX,stderr.getvalue());self.assertNotIn('SENSITIVE',stderr.getvalue())

    def test_compute_import_failure_does_not_block_transport(self):
        from unittest.mock import patch
        import builtins
        original=builtins.__import__
        def importing(name,*args,**kwargs):
            if name=='compute_admission':raise ImportError('synthetic unavailable')
            return original(name,*args,**kwargs)
        with patch.object(builtins,'__import__',importing):
            self.assertEqual(P.send(self.transport,'test.py','https://api.openai.com'),'ok')
        self.assertEqual(json.loads((self.mem/'organ-failures.jsonl').read_text())['error'],'ImportError')

    def test_journal_fallback_is_raised_to_deduplicated_alarm(self):
        row={'at':self.now,'organ':'paid-http','what':'provider_accounting_failed','provider':'openai','script':'test.py','error':'OSError'}
        events=A.accounting_health(self.now,lambda args:json.dumps({'MESSAGE':P.FAILURE_PREFIX+json.dumps(row)}))
        self.assertEqual(len(events),1)
        state={}
        self.assertTrue(A.remember(state,*events[0],self.now))
        self.assertFalse(A.remember(state,*events[0],self.now+10))

    def test_journal_search_with_no_match_is_clean_not_blind(self):
        from unittest.mock import patch
        done=lambda rc,out:type('P',(),{'returncode':rc,'stdout':out})()
        with patch.object(A.subprocess,'run',lambda *a,**k:done(1,'')):
            self.assertEqual(A.run(['journalctl','--user','-g','^x']),'')
            self.assertRaises(RuntimeError,A.run,['journalctl','-u','ssh.service'])
            self.assertRaises(RuntimeError,A.run,['crontab','-l'])
        with patch.object(A.subprocess,'run',lambda *a,**k:done(2,'')):
            self.assertRaises(RuntimeError,A.run,['journalctl','--user','-g','^x'])

    def test_urllib_counts_actual_opens_and_redirects_not_preview_stub(self):
        from unittest.mock import patch
        import urllib.request
        request=urllib.request.Request('https://api.openai.com/v1')
        self.assertEqual(P.urllib_send(lambda *a,**k:'preview', 'preview.py',request),'preview')
        self.assertFalse(self.ledger.exists())
        def opened(self,http_class,req,**kwargs):return 'opened'
        with patch.object(urllib.request.AbstractHTTPHandler,'do_open',opened):
            def transport(req):
                handler=urllib.request.HTTPSHandler()
                handler.do_open(object,req)
                return handler.do_open(object,urllib.request.Request('https://api.x.ai/redirect'))
            self.assertEqual(P.urllib_send(transport,'preview.py',request),'opened')
            # Outside the active request context the hook is inert.
            urllib.request.HTTPSHandler().do_open(object,request)
        rows=[json.loads(line) for line in self.ledger.read_text().splitlines()]
        self.assertEqual([row['provider'] for row in rows],['openai','xai'])
        P.main(['pause'])
        with self.assertRaises(PermissionError):P.urllib_send(lambda *a:'must not run','preview.py',request)

    def test_concurrent_attempts_not_lost(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i:P.send(self.transport,'test.py','https://api.x.ai'),range(40)))
        self.assertEqual(len([json.loads(s) for s in self.ledger.read_text().splitlines()]),40)

    def test_no_double_count_reservations_refunds_completions(self):
        self.attempts(13)
        self.rows([{'class':'paid','stage':s,'epoch':self.now-1,'provider':'anthropic'} for s in ['reserved','claimed','released','refused']])
        self.assertEqual(A.provider_rates(self.now)[0]['rate'],13)

    def test_minute_boundary_and_future_old_rows(self):
        self.attempts(4,at=self.now-59);self.attempts(4,at=self.now-2)
        self.attempts(50,at=self.now-60);self.attempts(20,at=self.now+1)
        self.assertEqual(A.provider_rates(self.now)[0]['rate'],8)

    def test_burst_allowed_surge_once_hour_and_provider_independent(self):
        self.attempts(12);self.tick();self.assertEqual(self.sent,[])
        self.attempts(1);self.tick();self.assertEqual(len(self.sent),1)
        text=self.sent[0][1]['message']
        self.assertIn('anthropic: 13',text);self.assertIn('scripts/test.py',text);self.assertIn(A.PAUSE,text)
        self.assertTrue(self.sent[0][1]['authority']()[0])
        self.tick(now=self.now+10);self.assertEqual(len(self.sent),1)
        self.attempts(13,'openai');self.tick(now=self.now+11);self.assertEqual(len(self.sent),2)
        self.now+=3600;self.attempts(13);self.tick();self.assertEqual(len(self.sent),3)

    def test_failed_delivery_retry_does_not_repeat_success(self):
        self.attempts(13)
        self.tick(sender=lambda *a,**k:{'state':'failed'})
        self.assertEqual(len(json.loads(A.paths()[0].read_text())['pending']),1)
        self.tick(now=self.now+10);self.assertEqual(len(self.sent),1)
        self.tick(now=self.now+20);self.assertEqual(len(self.sent),1)

    def test_dry_no_writes_no_send(self):
        self.attempts(13);before=set(self.mem.iterdir())
        result=self.tick(dry=True)
        self.assertTrue(result['events']);self.assertEqual(self.sent,[]);self.assertEqual(before,set(self.mem.iterdir()))

    def test_alarm_enters_existing_fault_loop(self):
        self.attempts(13);self.tick()
        found=F.organ_failures(self.now-10)
        self.assertTrue(any(f['kind']=='provider_surge' for f in found))
        self.assertEqual(found[0]['part'],'security-alarm')
        state={};fresh=F.merge(found,state,self.now);self.assertTrue(fresh[0]['id'].startswith('F-'))

    def test_authorized_keys_and_new_unit_cron_changes(self):
        self.tick()
        changed=json.loads(json.dumps(self.host));changed['files']['/home/test/.ssh/authorized_keys']='new'
        changed['files']['/etc/systemd/system/new.service']='new';changed['files']['user-crontab']='new'
        self.tick(now=self.now+1,snapshot=changed)
        self.assertEqual(len(self.sent),3)
        kinds=[k['title'] for a,k in self.sent];self.assertTrue(any('authorized_keys_changed' in x for x in kinds))
        self.tick(now=self.now+2,snapshot=changed);self.assertEqual(len(self.sent),3)

    def test_release_mismatch_and_receipt_match(self):
        host=dict(self.host,deployed={'/fake/code.py':{'actual':'x','expected':'y','matches_release':False}})
        self.tick(snapshot=host);self.assertIn('differs from release',self.sent[0][1]['message'])
        host['deployed']['/fake/code.py']['matches_release']=True
        self.assertEqual(A.host_events(host,host),[])

    def test_unfamiliar_ssh_and_explicit_allowlist(self):
        self.tick(logins=[('cursor-1','100.1.2.3')]);self.assertEqual(len(self.sent),1)
        self.tick(now=self.now+1,logins=[('cursor-1','100.1.2.3'),('cursor-2','100.1.2.3')]);self.assertEqual(len(self.sent),1)
        A.paths()[1].write_text(json.dumps({'known_ssh_addresses':['100.9.8.7']}))
        self.tick(now=self.now+2,logins=[('cursor-3','100.9.8.7')]);self.assertEqual(len(self.sent),1)

    def test_journal_only_accepted_addresses(self):
        lines=[{'MESSAGE':'Accepted publickey for gloria from 100.1.2.3 port 22 ssh2','__CURSOR':'abc'},
               {'MESSAGE':'Failed password for user from 1.2.3.4'}, {'MESSAGE':'Accepted publickey for user from $(evil) port 4'}]
        got=A.ssh_logins(self.now,lambda cmd:'\n'.join(map(json.dumps,lines)))
        self.assertEqual(got,[('abc','100.1.2.3')])

    def test_monitor_failure_visible(self):
        old=A.host_snapshot;A.host_snapshot=lambda runner:(_ for _ in ()).throw(PermissionError())
        try:
            A.tend(now=self.now,sender=self.sender,logins=[])
            self.assertIn('Host baseline unreadable',self.sent[0][1]['message'])
        finally:A.host_snapshot=old

    def test_actual_deliver_authority_and_receipt_gate(self):
        D.RECEIPTS=str(self.mem/'delivery-receipts.json');D.POST=lambda *a,**k:204;D.SLEEP=forbidden
        self.attempts(13);self.tick(sender=D.deliver)
        rows=D.load_receipts();self.assertEqual(len(rows),1);self.assertEqual(next(iter(rows.values()))['state'],'sent')

    def test_baseline_cannot_be_trained_above_absolute_threshold(self):
        for minute in range(400,500): self.attempts(100,at=self.now-minute*60)
        self.attempts(61)
        row=A.provider_rates(self.now)[0]
        self.assertLessEqual(row['threshold'],60)
        self.tick();self.assertEqual(len(self.sent),1)

    def test_ordinary_media_polling_is_not_a_surge(self):
        self.attempts(30,provider='kie');self.attempts(30,provider='atlascloud')
        self.tick();self.assertEqual(self.sent,[])
        self.attempts(1,provider='kie');self.tick()
        self.assertEqual(len(self.sent),1);self.assertIn('kie: 31',self.sent[0][1]['message'])

    def test_corrupt_and_irrelevant_rows_do_not_count(self):
        self.ledger.write_text('broken\n[]\n{"class":"local"}\n')
        self.attempts(13);self.assertEqual(A.provider_rates(self.now)[0]['rate'],13)

    def test_normal_deploy_deferred_but_keys_still_alert(self):
        self.tick()
        changed=json.loads(json.dumps(self.host));changed['deploying']=True
        changed['files']['/home/test/.ssh/authorized_keys']='changed-during-deploy'
        changed['files']['/etc/systemd/system/new.service']='new'
        events=A.host_events(self.host,changed)
        self.assertEqual(len(events),1);self.assertEqual(events[0][1],'authorized_keys_changed')
        changed['files']['/home/test/.ssh/authorized_keys']='old'
        self.tick(now=self.now+1,snapshot=changed);self.assertEqual(self.sent,[])
        saved=json.loads(A.paths()[0].read_text());self.assertNotIn('deploying',saved['host'])

    def test_real_install_lock_is_read_only_and_detected(self):
        import fcntl
        p=Path.home()/'.vintos/deploy/security-install.lock';p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('w') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            self.assertTrue(A.deploying())
        self.assertFalse(A.deploying())

    def test_receipt_covers_new_unit(self):
        current=json.loads(json.dumps(self.host));current['release']='next.json'
        p='/etc/systemd/system/new.service';current['files'][p]='new'
        current['deployed'][p]={'matches_release':True}
        self.assertEqual(A.host_events(self.host,current),[])

    def test_no_more_than_one_delivery_within_rolling_hour_after_retry(self):
        self.attempts(13);self.tick(sender=lambda *a,**k:{'state':'failed'})
        self.tick(now=self.now+3500);self.assertEqual(len(self.sent),1)
        self.now+=3600;self.attempts(13);self.tick();self.assertEqual(len(self.sent),1)

    def test_concurrent_monitors_deliver_one(self):
        self.attempts(13)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.tick(),range(8)))
        self.assertEqual(len(self.sent),1)

    def test_curl_wrapper_retains_arguments_and_pause_stops_launch(self):
        import subprocess
        old=subprocess.call;launched=[]
        subprocess.call=lambda args:launched.append(args) or 0
        try:
            args=['curl','shell-job.sh','--','-s','https://api.x.ai/v1','-H','Authorization: PRIVATE']
            self.assertEqual(P.main(args),0);self.assertEqual(launched[0],['curl']+args[3:])
            self.assertNotIn('PRIVATE',self.ledger.read_text())
            P.main(['pause'])
            with self.assertRaises(PermissionError):P.main(args)
            self.assertEqual(len(launched),1)
        finally:subprocess.call=old

    def test_manifest_and_twins(self):
        manifest=(REPO/'scripts/deploy-atelier.sh').read_text()
        self.assertIn('security_alarm.py paid_http.py',manifest)
        self.assertIn('$SECURITY_UNIT_NAME.service',manifest)
        self.assertEqual((REPO/'scripts/paid_http.py').read_bytes(),(REPO/'bin/paid_http.py').read_bytes())
        self.assertIn('--security',(REPO/'broker/vintos-security-alarm.service').read_text())

if __name__=='__main__': unittest.main()
