#!/usr/bin/env python3
"""End-to-end local loop with actual SQLite, Atelier projection, WSGI and fake effects."""
import importlib.util
import io
import json, time
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

    def test_capability_builds_and_reports_share_atomic_budget(self):
        p = self.create()
        self.assertTrue(self.c.reserve_build(self.owner, 'a'*32, 'SK-12345678')['reserved'])
        self.assertTrue(self.c.reserve_build(self.owner, 'a'*32, 'SK-12345678')['reserved'])
        self.assertEqual(self.c.step_budget(self.owner)['used'], 1)
        self.assertTrue(self.r.step(p['id']))
        self.assertTrue(self.c.reserve_build(self.owner, 'b'*32, 'SK-87654321')['reserved'])
        self.assertFalse(self.r.step(p['id']))
        self.assertFalse(self.c.reserve_build(self.owner, 'c'*32, 'SK-87654321')['reserved'])
        self.assertEqual(self.call('/api/build-reservation', 'POST', {'proposal':'SK-12345678','attempt':'d'*32},token=self.worker)[0],403)

    def test_real_gap_waits_for_install_and_respects_cancellation(self):
        row = {'proposal':'SK-12345678','want_id':'w-one','intent':'I want to email a collaborator',
               'capability':'send_email','source':'latent_thread','state':'proposed'}
        result = self.r.sync_gaps(self.owner, [row])[0]
        pid = result['id']
        self.assertEqual(self.r.sync_gaps(self.owner, [row])[0]['id'], pid)
        def model(system, user):
            return {'title':'Persistent email access','required_components':['address','inbox','authorized sending'],
                    'acceptance_tests':['test delivery to an explicitly authorized fixture recipient'],
                    'external_requirements':['provider account'], 'limitations':'No account provisioned'}
        self.r.builder = ReportBuilder(model)
        self.assertTrue(self.r.step(pid))
        self.assertEqual(self.c.status(self.owner,pid)['state'],'awaiting_capability')
        self.assertFalse(self.r.step(pid))
        row['state']='installed'
        self.r.sync_gaps(self.owner,[row])
        self.assertEqual(self.c.status(self.owner,pid)['state'],'awaiting_capability')
        row['artifact_verified']=True
        self.r.sync_gaps(self.owner,[row])
        self.assertEqual(self.c.status(self.owner,pid)['state'],'complete')
        row.update(proposal='SK-87654321',state='proposed')
        pid2=self.r.sync_gaps(self.owner,[row])[0]['id']
        self.call('/api/projects/'+pid2+'/cancel','POST',{})
        self.assertFalse(self.c.reserve_build(self.owner,'e'*32,row['proposal'])['reserved'])
        self.r.sync_gaps(self.owner,[row])
        self.assertEqual(self.c.status(self.owner,pid2)['state'],'cancelled')

    def test_source_fairness_selects_nonlab_before_another_lab_cycle(self):
        lab = self.create(origin={'source':'lab'})
        self.r.step(lab['id'])
        other = self.create(origin={'source':'absence_map'})
        self.assertEqual(self.c.ready_queue(self.worker)[0],other['id'])
        self.r.step(other['id'])
        self.assertEqual(self.c.ready_queue(self.worker)[0],lab['id'])

    def test_ended_parent_stops_gap_before_model_use(self):
        row={'proposal':'SK-12345678','want_id':'gone','intent':'Ended intention',
             'capability':'inbox','source':'latent_thread','state':'origin_ended'}
        pid=self.r.sync_gaps(self.owner,[row])[0]['id']
        self.assertFalse(self.r.step(pid))
        self.assertEqual(self.c.step_budget(self.owner)['used'],0)

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
    def test_sync_wants_skips_fully_owned_plans(self):
        # A relational want whose plan uses only installed capabilities is conversation, not Forge
        # work — it must NOT spawn a capability_assessment project. Only a want naming a missing
        # capability in a pending step is assessed.
        inv=['introspect','gloria','creative_write']
        owned={'id':'w1','want':'tell her the coffee scene','source':'thread','fingerprint':'f1',
               'steps':[{'capability':'introspect'},{'capability':'gloria'}]}
        gap={'id':'w2','want':'press my weight into her','source':'thread','fingerprint':'f2',
             'steps':[{'capability':'physical_interaction'}]}
        unplanned={'id':'w3','want':'some unplanned want','source':'thread','fingerprint':'f3','steps':[]}
        self.r.sync_wants(self.owner,[owned,gap,unplanned],inv)
        intents=[p.get('intent','') or '' for p in self.c.projects(self.owner)]
        self.assertFalse(any('coffee scene' in i for i in intents),'a fully-owned plan is not a Forge project')
        self.assertTrue(any('press my weight into her' in i for i in intents),'a missing-capability want is still assessed')
        # Gloria, 2026-09-24: the Forge maps a path to what is unreachable. A want with no plan is a want.
        self.assertFalse(any('some unplanned want' in i for i in intents),'an unplanned want is not Forge work')

    def test_projects_surface_intent_and_seal_private(self):
        # The owner UI could not show WHAT he is making because status/projects dropped `intent`.
        p=self.create();pid=p['id']
        self.assertEqual(self.c.status(self.owner,pid).get('intent'),'Document the source')
        self.assertTrue(any(r['id']==pid and r.get('intent')=='Document the source'
                            for r in self.c.projects(self.owner)))
        code,raw=self.call('/api/projects')
        self.assertEqual(code,200)
        self.assertTrue(any(r.get('intent')=='Document the source' for r in json.loads(raw)),
                        'the /api/projects wire carries the intent to the UI')
        # A private interval stays sealed: intent is None until an explicit audit, like its artifacts.
        pv=self.create(private=True,private_until=__import__('time').time()+86400);pvid=pv['id']
        self.assertIsNone(self.c.status(self.owner,pvid).get('intent'))
        self.assertTrue(self.c.status(self.owner,pvid)['private'])

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

    def test_physical_gap_becomes_reviewable_hardware_proposal(self):
        responses=iter([
            {'missing':True,'capability':'physical_interaction','note':'sense pressure on a small pad',
             'expected_output':'timestamped pressure samples','acceptance':'known weights read within tolerance',
             'execution':'external','reason':'no installed sensor or physical input'},
            {'title':'Pressure pad input','objective':'Give Vintos a bounded pressure signal',
             'parts':[{'name':'Arduino Nano','quantity':1,'rough_cost_usd':18.0,'purpose':'sample the sensor'},
                      {'name':'force-sensitive resistor','quantity':1,'rough_cost_usd':9.0,'purpose':'measure pressure'}],
             'rough_total_cost_usd':27.0,'wiring':['FSR divider to A0; common ground'],
             'firmware_sketch':'Read A0, clamp range, emit one bounded JSON sample per second.',
             'house_reporting':{'channel':'existing house MQTT bridge','payload':'pressure sample JSON',
                                'acknowledgement':'bridge returns stored receipt id'},
             'safety_limits':['USB low voltage only'],'acceptance_tests':['known weights remain within tolerance'],
             'unknowns':['sensor range needs selection']}
        ])
        builder=ReportBuilder(lambda *args:next(responses))
        claim={'maximum_cents':0,'capability':'capability_assessment','cycle_id':'fixture'}
        context={'intent':'I want to feel pressure','origin':{'inventory':['web_search'],'house_channels':['MQTT']}}
        result=builder(claim,context)
        proposal=result['artifact']['hardware_proposal']
        self.assertEqual(proposal['decision'],'gloria_accept_or_deny')
        self.assertIn('nothing_purchased',proposal['truth_status'])
        self.assertEqual(result['artifact']['capability_assessment']['hardware_proposal'],proposal)
    def test_unknown_request_cannot_expand_authority(self):
        with self.assertRaises(Refused):self.create(capabilities=['shell'])
    def test_lab_intake_is_scoped_open_and_idempotent(self):
        from lab_sources import receipt
        self.r.intake_token='i'*40
        for _ in range(4): self.create(kind='capability_brief',origin={'source':'latent_thread'})
        record=receipt('pdb',{'entry_id':'1ABC'},[{'exptl':[{'method':'fixture'}]}])
        body={'intent':'Make a sourced dossier','source_packet':{'kind':'lab_research_report','source_receipts':[record]}}
        status, raw=self.call('/api/lab-intake','POST',body,token='i'*40)
        self.assertEqual(status,200);pid=json.loads(raw)['id']
        status, raw=self.call('/api/lab-intake','POST',body,token='i'*40)
        self.assertTrue(json.loads(raw)['replayed'])
        self.assertEqual(len(self.c.projects(self.owner)),5)
        self.assertFalse(self.c.status(self.owner,pid)['private'],'only the Atelier is private; a Lab report is hers to see')
        self.assertEqual(self.call('/api/projects',token='i'*40)[0],403)
        record['records'][0]['exptl'][0]['method']='tampered'
        self.assertEqual(self.call('/api/lab-intake','POST',body,token='i'*40)[0],403)
    def keyless(self,path,method='GET',body=None):
        raw=json.dumps(body or {}).encode();status=[]
        out=API(self.r)({'PATH_INFO':path,'REQUEST_METHOD':method,'HTTP_AUTHORIZATION':'',
                        'CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw)},lambda s,h:status.append(s))
        return int(status[0].split()[0]),b''.join(out)
    def test_her_page_needs_no_key_but_machine_routes_do(self):
        # Gloria, 2026-09-24: the Forge is not private; her page should not ask for a key.
        p=self.create()
        self.assertEqual(self.keyless('/api/projects')[0],200)
        self.assertEqual(self.keyless('/api/budget')[0],200)
        status,raw=self.keyless('/api/projects','POST',{'intent':'a new Lab tool','private':True,'private_until':time.time()+3600})
        self.assertEqual(status,200)
        self.assertFalse(self.c.status(self.owner,json.loads(raw)['id'])['private'],'a keyless start is never private')
        self.assertEqual(self.keyless('/api/projects/'+p['id']+'/cancel','POST')[0],200)
        for path,method in (('/api/wants-sync','POST'),('/api/gaps-sync','POST'),('/api/build-reservation','POST'),
                            ('/api/projects/'+p['id']+'/audit','POST')):
            self.assertEqual(self.keyless(path,method,{'rows':[],'inventory':[]})[0],403,path)
        self.assertEqual(self.call('/api/projects',token='x'*40)[0],403,'a wrong key is still refused')
    def test_sealed_lab_reports_open_but_atelier_work_stays_sealed(self):
        from forge_loop_runtime import open_lab_privacy
        lab=self.create(origin={'source':'lab'},private=True,private_until=time.time()+86400)
        atelier=self.create(origin={'source':'atelier'},private=True,private_until=time.time()+86400)
        self.assertEqual(open_lab_privacy(self.c),1)
        self.assertFalse(self.c.status(self.owner,lab['id'])['private'])
        self.assertTrue(self.c.status(self.owner,atelier['id'])['private'])
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
