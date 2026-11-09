#!/usr/bin/env python3
"""Synthetic provider, durable limit, crash and continuation tests; no real sends."""
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import want_agent as A
import want_working_thread as W
import want_work_budget as B
from journal_wants import source_receipt


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='want-control-test-');self.addCleanup(self.temp.cleanup)
        self.ws=Path(self.temp.name).resolve();(self.ws/'memory').mkdir()
        self.assertNotIn('.vintos',self.ws.parts)
        env=patch.dict(os.environ,SPARK_WORKSPACE=str(self.ws));env.start();self.addCleanup(env.stop)
        self.want=dict(id='fixture-want',want='I want to run a synthetic analysis and export the result.',source='email')
        self.want.update(source_receipt('email','fixture-mail',self.want['want']))
        self.want['agent_work']=dict(request_id='WA-'+'a'*24,goal_sha256=A.fingerprint(self.want['want']),
            created_at=time.time(),status='in_work',thread='fixture-thread',work_id='RW-fixture')
        self.work=dict(id='RW-fixture',want_id=self.want['id'],want_request_id=self.want['agent_work']['request_id'])
        W.load(self.want,self.work,self.ws,'Synthetic identity')
        self.calls=[]
    def writer(self,s,u):
        self.calls.append((s,u))
        text=json.dumps({'message':'Synthetic next step.','accept':False})
        return dict(text=text,observations=[dict(text=text,status='valid',identity_evidence='response_metadata',
                    observed_model='fixture-served',requested_model='fixture-request')])
    def gen(self, trigger='fixture', writer=None):
        return W.generate(self.want,self.work,self.ws,'opening',trigger,'Fixture instruction',writer or self.writer)
    def config(self, **values):
        (self.ws/'memory/want-work-policy.json').write_text(json.dumps(values))
    def ledger(self):
        return json.loads((self.ws/'memory/want-work-control/calls.json').read_text())['calls']

    def test_caps_count_both_lanes_across_days_and_wants(self):
        self.config(per_want_calls=2,daily_calls=2)
        B.reserve(self.ws,'one','a','subscription',100000)
        B.reserve(self.ws,'one','b','openai',100001)
        with self.assertRaisesRegex(B.WorkBlocked,'daily_call_cap'): B.reserve(self.ws,'two','c','openai',100002)
        with self.assertRaisesRegex(B.WorkBlocked,'per_want_call_cap'): B.reserve(self.ws,'one','d','subscription',200000)
        B.reserve(self.ws,'two','c','subscription',200000)
        self.assertEqual(len(self.ledger()),3)

    def test_budget_reservations_are_atomic_and_private(self):
        self.config(per_want_calls=2,daily_calls=2)
        gate=threading.Barrier(6)
        def attempt(i):
            gate.wait()
            try: B.reserve(self.ws,'one',str(i),'fixture');return True
            except B.WorkBlocked:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            self.assertEqual(sum(pool.map(attempt,range(6))),2)
        self.assertEqual(len(self.ledger()),2)
        self.assertEqual((self.ws/'memory/want-work-control/calls.json').stat().st_mode & 0o777,0o600)

    def test_stop_and_zero_cap_prevent_writer(self):
        stop=self.ws/'memory/want-work.stop';stop.touch()
        with self.assertRaisesRegex(B.WorkBlocked,'stopped'):self.gen()
        self.assertEqual(self.calls,[])
        stop.unlink();self.config(per_want_calls=0)
        with self.assertRaisesRegex(B.WorkBlocked,'per_want'):self.gen()
        self.assertEqual(self.calls,[])

    def test_duplicate_reservation_and_corrupt_policy_never_reset_budget(self):
        B.reserve(self.ws,'one','same','fixture')
        with self.assertRaisesRegex(B.WorkBlocked,'already_reserved'):B.reserve(self.ws,'one','same','fixture')
        self.config(daily_calls=True)
        with self.assertRaises(B.WorkBlocked):B.reserve(self.ws,'one','new','fixture')
        self.assertEqual(len(self.ledger()),1)
        (self.ws/'memory/want-work-policy.json').unlink()
        (self.ws/'memory/want-work-control/calls.json').write_text('{broken')
        with self.assertRaises(B.WorkBlocked):B.reserve(self.ws,'one','new','fixture')
        self.assertEqual((self.ws/'memory/want-work-control/calls.json').read_text(),'{broken')

    def test_invalid_response_never_repeats_provider(self):
        def bad(s,u):self.calls.append(1);return dict(text='{invalid',observations=[])
        for _ in range(2):
            with self.assertRaises(B.WorkBlocked):self.gen(writer=bad)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(next(iter(W.load(self.want,self.work,self.ws)['generations'].values()))['state'],'response_observed')

    def test_response_saved_before_done_is_recovered_without_call(self):
        real=W._mutate
        def fail_done(w,work,ws,change,identity=None):
            if change.__name__=='done':raise OSError('synthetic final-store interruption')
            return real(w,work,ws,change,identity)
        with patch.object(W,'_mutate',fail_done):
            with self.assertRaises(OSError):self.gen()
        self.assertEqual(self.gen()['message'],'Synthetic next step.')
        self.assertEqual(len(self.calls),1)

    def test_uncertain_call_is_not_retried_after_old_lease(self):
        def lost(s,u):self.calls.append(1);raise RuntimeError('synthetic uncertain transport')
        with self.assertRaises(RuntimeError):self.gen(writer=lost)
        with patch.object(W.time,'time',return_value=time.time()+3600):
            with self.assertRaisesRegex(B.WorkBlocked,'interrupted'):self.gen(writer=lost)
        self.assertEqual(len(self.calls),1)

    def test_subscription_failure_uses_existing_fallback_same_context_and_evidence(self):
        import claude_sub, astra_call
        calls=[]
        def sub(model,system,user,**kw):calls.append(('subscription',system,user));raise RuntimeError('fixture unavailable')
        def fallback(system,messages,observer=None,**kw):
            calls.append(('openai',system,messages[0]['content']))
            packet=self.writer(system,messages[0]['content'])['observations'][0]
            packet['lane']='openai';observer(packet);return packet['text']
        with patch.object(claude_sub,'ask',sub),patch.object(astra_call,'call',fallback):
            W.generate(self.want,self.work,self.ws,'opening','route','Fixture',W.ask)
        self.assertEqual([c[0] for c in calls],['subscription','openai'])
        self.assertEqual(calls[0][1:],calls[1][1:])
        self.assertEqual([r['lane'] for r in self.ledger().values()],['subscription','openai'])
        record=next(iter(W.load(self.want,self.work,self.ws)['generations'].values()))
        self.assertEqual(record['capture']['witness_receipt']['generation']['attempts'][-1]['served_model'],'fixture-served')
        self.assertEqual(record['capture']['selected_lane'],'openai')

    def test_subscription_success_has_unknown_identity_and_no_api_call(self):
        import claude_sub, astra_call
        text=json.dumps(dict(message='Synthetic subscription reply',accept=False))
        with patch.object(claude_sub,'ask',return_value=text),patch.object(astra_call,'call',side_effect=AssertionError('fallback forbidden')):
            W.generate(self.want,self.work,self.ws,'opening','sub','Fixture',W.ask)
        record=next(iter(W.load(self.want,self.work,self.ws)['generations'].values()))
        self.assertIsNone(record['capture']['witness_receipt']['generation']['attempts'][0]['served_model'])
        self.assertEqual(record['capture']['selected_lane'],'subscription')
        self.assertEqual(len(self.ledger()),1)

    def test_second_lane_cannot_exceed_combined_cap(self):
        import claude_sub, astra_call
        self.config(per_want_calls=1)
        with patch.object(claude_sub,'ask',side_effect=RuntimeError('fixture')),patch.object(astra_call,'call',side_effect=AssertionError('over cap')):
            with self.assertRaisesRegex(B.WorkBlocked,'per_want'):W.generate(self.want,self.work,self.ws,'opening','cap','Fixture',W.ask)
        self.assertEqual(len(self.ledger()),1)

    def test_observer_persistence_failure_cannot_restart_successful_fallback(self):
        import claude_sub, astra_call
        real=W._mutate;calls=[]
        def broken(w,work,ws,change,identity=None):
            if change.__name__=='save' and calls:raise OSError('synthetic response persistence failure')
            return real(w,work,ws,change,identity)
        def fallback(s,messages,observer=None,**kw):
            calls.append(1);packet=self.writer(s,messages[0]['content'])['observations'][0];packet['lane']='openai'
            observer(packet);return packet['text']
        with patch.object(claude_sub,'ask',side_effect=RuntimeError('fixture')),patch.object(astra_call,'call',fallback),patch.object(W,'_mutate',broken):
            with self.assertRaisesRegex(B.WorkBlocked,'interrupted'):W.generate(self.want,self.work,self.ws,'opening','crash','Fixture',W.ask)
        with self.assertRaisesRegex(B.WorkBlocked,'interrupted'):W.generate(self.want,self.work,self.ws,'opening','crash','Fixture',W.ask)
        self.assertEqual(len(calls),1)

    def test_context_continuation_preserves_original_events_and_resumes(self):
        self.config(context_chars=2600)   # room for the want and its turns left (9 November)
        W.append(self.want,self.work,self.ws,'agent:1','dot','Synthetic history. '*200)
        original=copy.deepcopy(W.load(self.want,self.work,self.ws)['events'])
        with self.assertRaisesRegex(B.WorkBlocked,'context_needs'):self.gen()
        self.assertEqual(self.calls,[])
        W.continue_context(self.want,self.work,self.ws,'The synthetic input was inspected; export remains.','agent:1')
        self.gen()
        data=W.load(self.want,self.work,self.ws)
        self.assertEqual(data['events'][:len(original)],original)
        self.assertIn('export remains',self.calls[0][1]);self.assertNotIn('Synthetic history. '*200,self.calls[0][1])
        self.assertIn(self.want['want'],self.calls[0][1])

    def test_block_notice_is_durable_and_failed_delivery_retries(self):
        calls=[]
        def notify(key,msg):calls.append(key);return {'state':'sent'}
        for _ in range(2):W.notify_block(self.want,self.work,self.ws,'context_needs_continuation',notify)
        self.assertEqual(len(calls),1)
        W.notify_block(self.want,self.work,self.ws,'per_want_call_cap',lambda *a:{'state':'failed'})
        W.notify_block(self.want,self.work,self.ws,'per_want_call_cap',notify)
        self.assertEqual(len(calls),2)

    def test_new_interrupted_call_gets_notice_without_repeating_old_notice(self):
        calls=[]
        def notify(key,message): calls.append((key,message)); return {'state':'sent'}
        def report():
            W.notify_block(self.want,self.work,self.ws,'interrupted_call_needs_review',notify,
                           phase='opening',trigger='fixture')
        first=self.interrupted(); report(); report()
        self.assertEqual(len(calls),1); self.assertIn(first,calls[0][1])
        W.append(self.want,self.work,self.ws,'fixture:boundary','dot','Synthetic retained context.')
        W.continue_context(self.want,self.work,self.ws,'Synthetic summary.','fixture:boundary')
        report(); self.assertEqual(len(calls),1)
        (self.ws/'memory/want-work.stop').touch()
        W.reconcile(self.want,self.work,self.ws,first,'failed','Synthetic operator confirmed stopped failure.')
        (self.ws/'memory/want-work.stop').unlink()
        second=self.interrupted(); report(); report()
        self.assertNotEqual(first,second)
        self.assertEqual(len(calls),2); self.assertIn(second,calls[1][1])
        self.assertNotEqual(calls[0][0],calls[1][0])

    def test_context_notice_tracks_changed_summary_at_same_boundary(self):
        calls=[]
        def notify(key,message): calls.append(key); return {'state':'sent'}
        W.append(self.want,self.work,self.ws,'fixture:boundary','dot','Synthetic retained context.')
        for summary in ('Synthetic first summary.','Synthetic revised summary.'):
            W.continue_context(self.want,self.work,self.ws,summary,'fixture:boundary')
            for _ in range(2):
                W.notify_block(self.want,self.work,self.ws,'context_needs_continuation',notify)
        self.assertEqual(len(calls),2); self.assertNotEqual(calls[0],calls[1])

    def test_call_notice_failure_retries_same_identity_and_backoff_stays_quiet(self):
        calls=[]; call=self.interrupted()
        def notify(key,message):
            calls.append((key,message)); return {'state':'failed' if len(calls)==1 else 'sent'}
        for _ in range(3):
            W.notify_block(self.want,self.work,self.ws,'response_needs_review',notify,
                           phase='opening',trigger='fixture')
        self.assertEqual(len(calls),2); self.assertEqual(calls[0],calls[1]); self.assertIn(call,calls[0][1])
        W.notify_block(self.want,self.work,self.ws,'provider_retry_backoff',notify,phase='opening',trigger='fixture')
        self.assertEqual(len(calls),2)

    def test_same_event_concurrent_generation_calls_writer_once(self):
        started=threading.Event();release=threading.Event()
        def slow(s,u):
            started.set();self.assertTrue(release.wait(3));return self.writer(s,u)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(self.gen,writer=slow)
            self.assertTrue(started.wait(3))
            try:
                with self.assertRaises(B.WorkBlocked):self.gen()
            finally:release.set()
            self.assertEqual(future.result()['message'],'Synthetic next step.')
        self.assertEqual(len(self.calls),1)

    def test_continuation_cli_reads_only_bound_file_and_retains_history(self):
        import contextlib,io
        W.append(self.want,self.work,self.ws,'agent:1','dot','Fixture long history')
        root=A.directory(self.want['agent_work']['request_id'],self.ws)
        summary=root/'.continuation-summary.txt';summary.write_text('Fixture explicit summary')
        (self.ws/'memory/current-wants.json').write_text(json.dumps([self.want]))
        state=self.ws/'memory/dot-channel';state.mkdir()
        (state/'state.json').write_text(json.dumps({'room_work':{'open':[self.work]}}))
        args=['want_agent.py','continue-context',self.want['agent_work']['request_id'],
              '--summary-file',str(summary),'--through-event','agent:1']
        out=io.StringIO()
        with patch.object(sys,'argv',args),contextlib.redirect_stdout(out):A.main()
        self.assertEqual(json.loads(out.getvalue()),{'continued':True,'covered_events':1})
        self.assertEqual(W.load(self.want,self.work,self.ws)['events'][0]['text'],'Fixture long history')
        changed=list(args);changed[4]=str(self.ws/'outside.txt')
        with patch.object(sys,'argv',changed),contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):A.main()

    def test_fallback_direct_receipt_uses_response_model_only(self):
        import astra_call as C
        class Response:
            def __init__(self,value):self.value=value
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self):return json.dumps(self.value).encode()
        for actual in ('fixture-wire-model',None):
            with patch.object(C,'_key',return_value='fixture'),patch.object(C,'_openai_usage',lambda *a:None), \
                 patch.object(C.paid_http,'send',return_value=Response(dict(status='completed',output_text='Fixture',model=actual))):
                packet=C._direct_call('Fixture',[],return_receipt=True)
            self.assertEqual(packet['observed_model'],actual)
            self.assertEqual(packet['identity_evidence'],'response_metadata' if actual else 'unknown')

    def test_accounted_fallback_worker_retains_old_string_contract_and_metadata(self):
        import astra_call as C, compute_admission as admission
        reserves=[];observed=[];payloads=[]
        packet=dict(text='Fixture answer',status='valid',observed_model='fixture-served',identity_evidence='response_metadata')
        def run(args,**kw):
            payload=json.loads(kw['input']);payloads.append(payload)
            return types.SimpleNamespace(returncode=0,stdout=json.dumps(packet) if payload.get('return_receipt') else 'Fixture answer',stderr='')
        def reserve(*args,**kw):reserves.append(kw);return True,'fixture'
        with patch.object(C,'_key',return_value='synthetic-key'),patch.object(subprocess,'run',run),patch.object(admission,'reserve_paid',reserve):
            self.assertEqual(C.call('system',[],observer=observed.append),'Fixture answer')
            self.assertEqual(C.call('system',[]),'Fixture answer')
        self.assertEqual(observed,[packet]);self.assertEqual(len(reserves),2)
        self.assertTrue(payloads[0]['return_receipt']);self.assertNotIn('return_receipt',payloads[1])

    def interrupted(self):
        with self.assertRaises(B.WorkBlocked):
            self.gen(writer=lambda *a: (_ for _ in ()).throw(RuntimeError('synthetic interrupted call')))
        data=W.load(self.want,self.work,self.ws)
        return next(iter(data['generations'].values()))['request_id']

    def test_reconcile_observed_finishes_locally_and_keeps_budget(self):
        call=self.interrupted(); before=copy.deepcopy(self.ledger())
        response=json.dumps({'message':'Recovered synthetic response.','accept':False})
        with self.assertRaises(ValueError): W.reconcile(self.want,self.work,self.ws,call,'observed','Fixture evidence',response)
        (self.ws/'memory/want-work.stop').touch()
        W.reconcile(self.want,self.work,self.ws,call,'observed','Fixture evidence',response)
        W.reconcile(self.want,self.work,self.ws,call,'observed','Fixture evidence',response)
        with self.assertRaises(ValueError): W.reconcile(self.want,self.work,self.ws,call,'failed','Different evidence')
        (self.ws/'memory/want-work.stop').unlink()
        answer=self.gen(writer=lambda *a:self.fail('recovered response called provider'))
        self.assertEqual(answer['message'],'Recovered synthetic response.')
        self.assertEqual(self.ledger(),before)
        rec=next(iter(W.load(self.want,self.work,self.ws)['generations'].values()))
        self.assertEqual(rec['reconciliation']['prior']['state'],'uncertain')
        self.assertIsNone(rec['capture']['witness_receipt']['generation']['attempts'][0]['served_model'])

    def test_exact_writer_inputs_persist_before_call_and_survive_restart(self):
        from witness_capture import Capture
        captured=[]
        def writer(system,user):
            rec=next(iter(W.load(self.want,self.work,self.ws)['generations'].values()))
            self.assertEqual(rec['state'],'running')
            self.assertEqual(rec['handler_input']['system'],system)
            self.assertEqual(rec['handler_input']['messages'],[{'role':'user','content':user}])
            captured.append(copy.deepcopy(rec))
            return self.writer(system,user)
        with patch.object(Capture,'finalize',side_effect=RuntimeError('synthetic local crash')):
            with self.assertRaises(RuntimeError): self.gen(writer=writer)
        before=copy.deepcopy(self.ledger())
        W.append(self.want,self.work,self.ws,'fixture:new','dot','Later synthetic context must not replace original input.')
        self.gen(writer=lambda *a:self.fail('restart repeated provider'))
        rec=next(iter(W.load(self.want,self.work,self.ws)['generations'].values()))
        packet=rec['capture']; expected=Capture(rec['request_id'],'want_work',rec['at'])
        expected.request(**captured[0]['handler_input'],at=rec['at'])
        expected_packet=expected.finalize('fixture',time.time())
        self.assertEqual(packet['requests'],expected_packet['requests'])
        attempt=packet['witness_receipt']['generation']['attempts'][0]
        self.assertEqual(attempt['request_id'],packet['requests'][0]['request_id'])
        self.assertEqual(attempt['input_sha256'],packet['requests'][0]['input_sha256'])
        self.assertEqual(packet['input_scope'],'writer_arguments')
        self.assertEqual(packet['response_origin'],'adapter_result')
        self.assertEqual(packet['witness_receipt']['delivery'],'unknown')
        self.assertFalse(packet['reply_node']['complete'])
        serialized=json.dumps(packet)
        for value in self.calls[0]: self.assertNotIn(value,serialized)
        self.assertEqual(self.ledger(),before)
        self.assertEqual(len(self.calls),1)

    def test_legacy_observed_response_never_reconstructs_input(self):
        from witness_capture import Capture
        with patch.object(Capture,'finalize',side_effect=RuntimeError('synthetic local crash')):
            with self.assertRaises(RuntimeError): self.gen()
        def legacy(data):
            next(iter(data['generations'].values())).pop('handler_input')
        W._mutate(self.want,self.work,self.ws,legacy)
        self.gen(writer=lambda *a:self.fail('legacy recovery repeated provider'))
        packet=next(iter(W.load(self.want,self.work,self.ws)['generations'].values()))['capture']
        self.assertEqual(packet['requests'],[])
        self.assertEqual(packet['input_scope'],'unknown')
        self.assertIsNone(packet['witness_receipt']['generation']['attempts'][0].get('request_id'))

    def test_operator_recovery_cannot_attest_attempted_lane_or_input_binding(self):
        call=self.interrupted(); (self.ws/'memory/want-work.stop').touch()
        def attempted(data):
            next(iter(data['generations'].values()))['active_lane']='subscription'
        W._mutate(self.want,self.work,self.ws,attempted)
        response=json.dumps({'message':'Synthetic operator recovery.','accept':False})
        W.reconcile(self.want,self.work,self.ws,call,'observed','Fixture evidence',response)
        # Also handle records reconciled before the explicit origin field existed.
        def legacy(data):
            obs=next(iter(data['generations'].values()))['result']['observations'][0]
            self.assertEqual(obs['lane'],'unknown')
            obs['lane']='subscription'; obs.pop('origin')
        W._mutate(self.want,self.work,self.ws,legacy)
        (self.ws/'memory/want-work.stop').unlink()
        self.gen(writer=lambda *a:self.fail('operator recovery repeated provider'))
        packet=next(iter(W.load(self.want,self.work,self.ws)['generations'].values()))['capture']
        self.assertEqual(packet['response_origin'],'operator_recovery')
        self.assertEqual(packet['selected_lane'],'unknown')
        self.assertEqual(len(packet['requests']),1)
        attempt=packet['witness_receipt']['generation']['attempts'][0]
        self.assertIsNone(attempt.get('request_id'))
        self.assertIsNone(attempt['served_model'])

    def test_reconcile_failed_preserves_history_and_consumed_attempts(self):
        call=self.interrupted(); (self.ws/'memory/want-work.stop').touch()
        W.reconcile(self.want,self.work,self.ws,call,'failed','Operator verified no response and stopped worker.')
        (self.ws/'memory/want-work.stop').unlink(); self.gen()
        self.assertEqual(len(self.ledger()),2)
        rec=next(iter(W.load(self.want,self.work,self.ws)['generations'].values()))
        self.assertEqual(rec['reconciliation_history'][0]['call_id'],call)
        (self.ws/'memory/want-work.stop').touch()
        with self.assertRaises(ValueError): W.reconcile(self.want,self.work,self.ws,rec['request_id'],'failed','Cannot reopen completed call.')

    def test_reconcile_cli_uses_private_files_and_prints_no_response(self):
        call=self.interrupted(); (self.ws/'memory/want-work.stop').touch()
        (self.ws/'memory/current-wants.json').write_text(json.dumps([self.want]))
        path=self.ws/'memory/dot-channel';path.mkdir()
        (path/'state.json').write_text(json.dumps({'room_work':{'open':[self.work]}}))
        root=A.directory(self.want['agent_work']['request_id'],self.ws)
        (root/'.evidence.txt').write_text('Synthetic operator evidence.')
        response=json.dumps({'message':'Private synthetic recovered output.','accept':False})
        (root/'.response.txt').write_text(response)
        import io
        from contextlib import redirect_stdout
        args=['want_agent.py','reconcile',self.want['agent_work']['request_id'],'--call',call,
              '--outcome','observed','--confirm-stopped','--evidence-file',str(root/'.evidence.txt'),
              '--response-file',str(root/'.response.txt')]
        output=io.StringIO()
        with patch.object(sys,'argv',args),redirect_stdout(output): A.main()
        self.assertEqual(json.loads(output.getvalue()),{'reconciled':True,'outcome':'observed'})
        self.assertNotIn('Private',output.getvalue())

if __name__=='__main__':unittest.main()
