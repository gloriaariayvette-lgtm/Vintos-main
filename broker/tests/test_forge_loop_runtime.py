#!/usr/bin/env python3
"""End-to-end local loop with actual SQLite, Atelier projection, WSGI and fake effects."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts'))
from forge_loop import Controller, Refused
from forge_loop_atelier import AtelierProjection
from forge_loop_runtime import Runtime, API, ReportBuilder, LocalModel


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='forge-runtime-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.owner='o'*40;self.worker='w'*40
        self.c=Controller(self.root/'forge.sqlite',self.owner,self.worker,'https://atelier.invalid')
        self.assertTrue(self.c.path.is_relative_to(self.root))
        self.sent=[];self.contexts=[]
        self.r=Runtime(self.c,AtelierProjection(self.root),self.build,self.send,'test-topic')
        self.assertEqual(self.r.publisher,self.send)
        self.block=patch('urllib.request.urlopen',side_effect=AssertionError('live network forbidden'))
        self.block.start();self.addCleanup(self.block.stop)
    def test_local_only_route_and_explicit_notification_transport(self):
        import ast
        tree=ast.parse((REPO/'bin/vintos_claude_shim.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='provider_chain')
        scope={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'fixture','exec'),scope)
        self.assertEqual(scope['provider_chain']({},'/gemma-aegis-local/v1/chat/completions'),['aegis_gemma'])
        with self.assertRaises(ValueError): LocalModel('http://127.0.0.1:8599/gemma-aegis/v1/chat/completions','fixture')
        from forge_loop_ntfy import NtfyPublisher
        with self.assertRaises(ValueError): NtfyPublisher('https://ntfy.invalid','fixture')
        sent=[]
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            status=200
            def read(self,n): return b'{"event":"message","topic":"fixture","id":"test"}'
        def transport(req,timeout): sent.append(req);return Response()
        publisher=NtfyPublisher('https://ntfy.invalid','fixture',anonymous=True,transport=transport)
        self.assertIs(publisher.transport,transport)
        self.assertTrue(publisher({'message':'fixture'}))
        self.assertFalse(sent[0].has_header('Authorization'))

    def test_local_model_accepts_single_json_fence_not_surrounding_prose(self):
        from contextlib import nullcontext
        class Response:
            def __init__(self,text): self.text=text
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,n): return json.dumps({'choices':[{'message':{'content':self.text}}]}).encode()
        for payload in ('{"ok":true}', '```json\n{"ok":true}\n```', '```\n{"ok":true}\n```'):
            transport=lambda *a,**k:Response(payload)
            model=LocalModel('http://127.0.0.1:1234/v1/chat/completions','fixture',transport=transport,admission=nullcontext)
            self.assertIs(model.transport,transport)
            self.assertEqual(model('fixture','fixture'),{'ok':True})
        model=LocalModel('http://127.0.0.1:1234/v1/chat/completions','fixture',transport=lambda *a,**k:Response('Prose\n```json\n{"ok":true}\n```'),admission=nullcontext)
        with self.assertRaises(ValueError): model('fixture','fixture')

    def test_three_steps_global_persistent_and_failed_attempts_count(self):
        import concurrent.futures
        projects=[self.create() for _ in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            claims=list(pool.map(lambda p:self.c.claim(self.worker,p['id'],'research_report'),projects))
        self.assertEqual(sum(c is not None for c in claims),3)
        restarted=Controller(self.root/'forge.sqlite',self.owner,self.worker,'https://atelier.invalid')
        self.assertEqual(restarted.step_budget(self.owner)['remaining'],0)
        for p,claim in zip(projects,claims):
            if claim: restarted.uncertain(self.worker,p['id'],claim['cycle_id'])
        self.assertEqual(restarted.step_budget(self.owner)['used'],3)
        with patch('forge_loop.step_day',return_value='2099-01-02'):
            self.assertEqual(restarted.step_budget(self.owner)['remaining'],3)
            untouched=next(p for p,c in zip(projects,claims) if c is None)
            self.assertIsNotNone(restarted.claim(self.worker,untouched['id'],'research_report'))
        self.assertEqual(json.loads(self.call('/api/budget')[1])['limit'],3)

    def test_step_budget_upgrade_does_not_reset_existing_cycles(self):
        p=self.create();self.r.step(p['id'])
        with self.c.db() as db: db.execute('DROP TABLE daily_steps')
        migrated=Controller(self.root/'forge.sqlite',self.owner,self.worker,'https://atelier.invalid')
        self.assertEqual(migrated.step_budget(self.owner)['used'],1)
        restarted=Controller(self.root/'forge.sqlite',self.owner,self.worker,'https://atelier.invalid')
        self.assertEqual(restarted.step_budget(self.owner)['used'],1)

    def send(self,payload):self.sent.append(payload);return True
    def build(self,claim,context):
        self.contexts.append(context)
        return {'artifact':{'report':{'text':'revision '+str(context['cycles']+1)},'evaluation':{'reveal':False}},
                'complete':context['cycles']>=1,'receipt':{'charged_cents':0,'cycle_id':claim['cycle_id']}}
    def create(self,**changes):return self.r.create(self.owner,dict(intent='Document the source',**changes))
    def call(self,path,method='GET',body=None,token=None):
        raw=json.dumps(body or {}).encode();status=[]
        out=API(self.r)({'PATH_INFO':path,'REQUEST_METHOD':method,'HTTP_AUTHORIZATION':'Bearer '+(token or self.owner),
                        'CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw)},lambda s,h:status.append(s))
        return int(status[0].split()[0]),b''.join(out)
    def test_continuous_feedback_lineage_and_outbox(self):
        p=self.create();pid=p['id']
        self.assertTrue(self.r.step(pid));self.assertTrue(self.r.step(pid));self.assertFalse(self.r.step(pid))
        self.assertEqual(self.c.status(self.owner,pid)['state'],'complete')
        self.assertEqual(self.contexts[1]['previous']['report']['text'],'revision 1')
        directory=self.root/'projects'/('forge-'+pid)
        lineage=json.loads((directory/'lineage.json').read_text())
        self.assertEqual(sorted(x['revision'] for x in lineage.values()),[1,2])
        self.assertEqual(len(list((directory/'artifacts').iterdir())),2)
        before=(directory/'events.jsonl').read_bytes();self.r.projection.sync(self.c)
        self.assertEqual(before,(directory/'events.jsonl').read_bytes())
        spec=importlib.util.spec_from_file_location('test_broker_chain',REPO/'broker/broker.py')
        broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)
        result=broker.verify_events_at(str(directory));self.assertTrue(result[0],result)
        self.r.dispatch();self.assertEqual(len(self.sent),2)
        self.r.dispatch();self.assertEqual(len(self.sent),2)
        self.assertEqual(self.sent[0]['actions'][1]['method'],'POST')
        self.assertNotIn(self.owner,json.dumps(self.sent))
    def test_private_suppression_audit(self):
        import time
        p=self.create(private=True,private_until=time.time()+600);pid=p['id']
        self.r.step(pid);self.r.dispatch();self.assertEqual(self.sent,[])
        self.assertEqual(self.call('/api/projects/'+pid+'/artifacts')[0],403)
        self.assertEqual(self.call('/api/projects/'+pid+'/audit','POST')[0],200)
        self.assertEqual(self.call('/api/projects/'+pid+'/artifacts')[0],200)
        self.r.dispatch();self.assertEqual(len(self.sent),1)
    def test_cancel_inflight_keeps_result(self):
        p=self.create();original=self.r.builder
        def cancel_then_build(claim,ctx):self.c.cancel(p['id'],p['cancel_token']);return original(claim,ctx)
        self.r.builder=cancel_then_build;self.r.step(p['id'])
        self.assertEqual(self.c.status(self.owner,p['id'])['state'],'cancelled')
        self.assertFalse(self.r.step(p['id']))
        self.assertEqual(len(self.c.artifacts(self.owner,p['id'])),1)
    def test_scoped_cancel_no_read_or_get_mutation(self):
        p=self.create();pid=p['id'];token=p['cancel_token']
        self.assertEqual(self.call('/cancel/'+pid,'GET',token=token)[0],405)
        self.assertEqual(self.call('/api/projects',token=token)[0],403)
        self.assertEqual(self.call('/cancel/'+pid,'POST',token=token)[0],200)
    def test_crash_recovery_never_replays(self):
        p=self.create();claim=self.c.claim(self.worker,p['id'],'research_report')
        self.c.recover_interrupted(self.worker)
        self.assertFalse(self.r.step(p['id']))
        self.c.reconcile(self.owner,p['id'],claim['cycle_id'],'Worker stopped; no output was produced.')
        self.assertTrue(self.r.step(p['id']))
    def test_runtime_refuses_reconcile_while_live(self):
        p=self.create()
        self.assertEqual(self.call('/api/projects/'+p['id']+'/reconcile','POST',{})[0],403)
    def test_failure_after_accept_preserves_cycle(self):
        p=self.create()
        with patch.object(self.r.projection,'sync',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):self.r.step(p['id'])
        self.assertEqual(self.c.status(self.owner,p['id'])['cycles'],1)
        self.r.projection.sync(self.c)
    def test_failed_notification_retained(self):
        p=self.create();self.r.step(p['id']);self.r.publisher=lambda item:False
        with self.assertRaises(RuntimeError):self.r.dispatch()
        self.r.publisher=self.send;self.r.dispatch();self.assertEqual(len(self.sent),1)
    def test_refuse_existing_project_adoption(self):
        p=self.create();directory=self.root/'projects'/('forge-'+p['id'])
        (directory/'.forge-owner.json').unlink()
        with self.assertRaises(ValueError):self.r.projection.sync(self.c)
    def test_local_model_only(self):
        for url in ('https://paid.example/v1','http://169.254.169.254/','http://user@127.0.0.1/'):
            with self.assertRaises(ValueError):LocalModel(url,'model')
    def test_report_completion_not_biological_proof(self):
        responses=iter([dict.fromkeys(('title','sourced_observations','hypotheses','conflicting_evidence','limitations','next_tests'),'fixture'),
                        {'complete':True,'reasons':'All sections supported or labeled speculation.','reveal':False}])
        result=ReportBuilder(lambda *args:next(responses))({'maximum_cents':0,'capability':'research_report','cycle_id':'fixture'}, {'intent':'report','previous':None})
        self.assertTrue(result['complete']);self.assertIn('not_validated',result['artifact']['truth_status'])
    def test_unknown_request_cannot_expand_authority(self):
        with self.assertRaises(Refused):self.create(capabilities=['shell'])
    def test_lab_intake_is_scoped_private_and_idempotent(self):
        from lab_sources import receipt
        self.r.intake_token='i'*40
        record=receipt('pdb',{'entry_id':'1ABC'},[{'exptl':[{'method':'fixture'}]}])
        body={'intent':'Make a sourced dossier','source_packet':{'kind':'lab_research_report','source_receipts':[record]}}
        status, raw=self.call('/api/lab-intake','POST',body,token='i'*40)
        self.assertEqual(status,200);pid=json.loads(raw)['id']
        status, raw=self.call('/api/lab-intake','POST',body,token='i'*40)
        self.assertTrue(json.loads(raw)['replayed'])
        self.assertEqual(len(self.c.projects(self.owner)),1)
        self.assertTrue(self.c.status(self.owner,pid)['private'])
        self.assertEqual(self.call('/api/projects',token='i'*40)[0],403)
        record['records'][0]['exptl'][0]['method']='tampered'
        self.assertEqual(self.call('/api/lab-intake','POST',body,token='i'*40)[0],403)
    def test_projection_is_visible_to_existing_broker_and_has_no_write_bypass(self):
        p=self.create();self.r.step(p['id'])
        spec=importlib.util.spec_from_file_location('test_broker_visibility',REPO/'broker/broker.py')
        broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)
        broker.ROOT=str(self.root);broker.HEALTH=str(self.root/'health.jsonl')
        self.assertTrue(Path(broker.ROOT).is_relative_to(self.root))
        pid='forge-'+p['id']
        self.assertIn(pid,[x['id'] for x in broker.list_projects()['projects']])
        self.assertFalse(broker.authorize_route('/make',{'id':pid})[0])
        broker._ev(pid,'looked_quietly')
        self.r.step(p['id'])
        self.assertTrue(broker.verify_events_at(str(self.root/'projects'/pid))[0])
    def test_private_projection_cannot_be_read_through_broker_doors(self):
        import time
        p=self.create(private=True,private_until=time.time()+600);self.r.step(p['id'])
        spec=importlib.util.spec_from_file_location('test_broker_private',REPO/'broker/broker.py')
        broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)
        broker.ROOT=str(self.root);broker.HEALTH=str(self.root/'health.jsonl')
        self.assertTrue(Path(broker.ROOT).is_relative_to(self.root))
        for path in ('/look/offer','/look/mint','/visit/open','/artifact','/reveal/prepare','/reveal/confirm'):
            self.assertFalse(broker.authorize_route(path,{'id':'forge-'+p['id'],'as':'gloria'})[0],path)
        self.c.end_private(self.owner,p['id'],'audit');self.r.projection.sync(self.c)
        self.assertTrue(broker.authorize_route('/look/offer',{'id':'forge-'+p['id']})[0])

    def test_model_requires_compute_admission(self):
        with self.assertRaisesRegex(Refused,'admission'):
            LocalModel('http://127.0.0.1:8599/gemma-aegis-local/v1/chat/completions','fixture')('system','user')
    def test_intake_survives_projection_failure_without_duplicate(self):
        from lab_sources import receipt
        self.r.intake_token='i'*40
        body={'source_packet':{'kind':'lab_research_report','source_receipts':[receipt('pdb',{},[{'id':'fixture'}])]}}
        with patch.object(self.r.projection,'sync',side_effect=OSError('projection unavailable')):
            with self.assertRaises(OSError):self.r.intake('i'*40,body)
        result=self.r.intake('i'*40,body)
        self.assertTrue(result['replayed']);self.assertEqual(len(self.c.projects(self.owner)),1)

    def test_named_service_bundle_check_is_standalone_and_read_only(self):
        import shutil, subprocess
        bundle=self.root/'bundle';bundle.mkdir()
        for name in (REPO/'scripts/forge-loop-files.txt').read_text().splitlines():
            shutil.copyfile(REPO/'scripts'/name,bundle/name)
        paths={}
        for name in ('owner','worker','ntfy'):
            path=self.root/name;path.write_text(name*40);path.chmod(0o600);paths[name]=str(path)
        memory=self.root/'compute';memory.mkdir()
        for name in ('.compute.lock','compute-ledger.jsonl'):(memory/name).touch()
        config={'atelier_root':str(self.root/'check-only-root'),'public_base':'https://fixture.invalid',
                'owner_token_file':paths['owner'],'worker_token_file':paths['worker'],
                'compute_memory':str(memory),'local_model_url':'http://127.0.0.1:8599/gemma-aegis-local/v1/chat/completions',
                'local_model':'fixture-local','ntfy':{'server':'https://ntfy.invalid','topic':'fixture','token_file':paths['ntfy']}}
        path=self.root/'config.json';path.write_text(json.dumps(config))
        run=subprocess.run([sys.executable,str(bundle/'forge_loop_runtime.py'),'--config',str(path),'--check'],
                           cwd=bundle,env={'HOME':str(self.root),'PATH':os.defpath,'PYTHONNOUSERSITE':'1'},
                           capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)['live_access'],'not_tested')
        self.assertFalse((self.root/'check-only-root').exists())

    def test_paid_loop_still_refused(self):
        p=self.create();self.assertIsNone(self.c.claim(self.worker,p['id'],'research_report',quote_cents=1))
        self.assertEqual(self.c.status(self.owner,p['id'])['state'],'needs_authorization')


if __name__=='__main__':unittest.main()
