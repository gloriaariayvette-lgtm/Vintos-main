#!/usr/bin/env python3
"""Prospective HTTP event keys; synthetic contexts, stub senders and launchers."""
import ast
import asyncio
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import request_trace as T
import turn_coordinator as C

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='forecast-event-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.assertNotIn('.vintos',self.root.parts)
        self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        self.launch=Mock(return_value='synthetic-pending')
        self.current=ContextVar('synthetic-coordinator',default=None)
        token=T.current.set(None);self.addCleanup(T.current.reset,token)
        barrier=types.SimpleNamespace(strategy_stop_requested=Mock(return_value=False),pending_stop=Mock(return_value=False),
            capsule_eligible=Mock(return_value=(False,{'clear':False})),ineligible_record=Mock(return_value={}))
        for p in (patch.object(socket.socket,'connect',self.sender),
                  patch.object(C,'_record_ineligible',Mock()),patch.object(C,'_post',self.sender),
                  patch.dict(os.environ,SPARK_WORKSPACE=str(self.root)),
                  patch.dict(sys.modules,constitutional_barrier=barrier,
                             effect_gate=types.SimpleNamespace(TurnContext=Mock(return_value=None)),
                             jepa_self_head=types.SimpleNamespace(launch_on_message=self.launch))):
            p.start();self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertIsInstance(self.sender,Mock);self.assertIsInstance(self.launch,Mock)
        tree=ast.parse((ROOT/'bin/server.py').read_text())
        chosen=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
                and n.name in ('_self_on_message','_bilateral_reply')]
        self.ns=dict(os=os,WORKSPACE=str(self.root),_test_mode_active=lambda:False)
        exec(compile(ast.Module(body=chosen,type_ignores=[]),'actual-server-boundaries','exec'),self.ns)

    def arrive(self,her='synthetic arrival',surface='chat/full',turn_id='',test_mode=False):
        return self.ns['_self_on_message'](her,surface,turn_id=turn_id,test_mode=test_mode)

    def test_shared_event_rule_preserves_existing_coordinator_keys(self):
        for event in ('synthetic-request','client:event-1',123,True,['fixture']):
            expected='t-'+hashlib.sha256(str(event).encode()).hexdigest()
            self.assertEqual(T.event_turn_id(event),expected)
            self.assertEqual(C.begin('synthetic message','phone',event_id=event).turn_id,expected)

    def test_empty_event_keeps_existing_random_coordinator_fallback(self):
        for event in (None,'',0,False):
            self.assertIsNone(T.event_turn_id(event))
            with patch.object(C.uuid,'uuid4',return_value=types.SimpleNamespace(hex='a'*32)) as create:
                self.assertEqual(C.begin('synthetic','phone',event_id=event).turn_id,'t-'+'a'*16)
                create.assert_called_once()
            T.current.set(event);self.assertEqual(T.forecast_turn_id(),'')

    def test_actual_forecast_hook_reserves_same_key_before_coordinator_runs(self):
        T.current.set('synthetic-http-request')
        with patch.object(C,'begin',side_effect=AssertionError('must not open turn early')):
            self.assertEqual(self.arrive(),'synthetic-pending')
        kwargs=self.launch.call_args.kwargs
        actual=C.begin('synthetic arrival','phone',event_id=T.current.get())
        self.assertEqual(kwargs,dict(surface='chat/full',turn_id=actual.turn_id))
        self.assertFalse(actual.duplicate_event)

    def test_missing_or_invalid_trace_never_mints_forecast_origin(self):
        for value in (None,'',False,42,{},'bad trace','ü','a'*161):
            T.current.set(value);self.arrive()
            self.assertEqual(self.launch.call_args.kwargs['turn_id'],'')
        T.current.set('a'*160);self.assertEqual(T.forecast_turn_id(),T.event_turn_id('a'*160))

    def test_existing_explicit_avatar_key_and_other_surfaces_are_unchanged(self):
        T.current.set('synthetic-http-request')
        for surface,turn in (('avatar','actual-avatar-turn'),('chat/full','explicit-turn'),('avatar',''),('voice',''),('chat/full',None),('chat/full',0)):
            self.arrive(surface=surface,turn_id=turn)
            self.assertEqual(self.launch.call_args.kwargs,dict(surface=surface,turn_id=turn))

    def test_test_mode_never_reserves_or_launches(self):
        with patch.object(T,'forecast_turn_id',side_effect=AssertionError('test mode must stop first')):
            self.assertIsNone(self.arrive(test_mode=True))
        self.launch.assert_not_called()

    def test_correlation_failure_preserves_launch_with_unknown_key(self):
        with patch.object(T,'forecast_turn_id',side_effect=RuntimeError('synthetic failure')):
            self.assertEqual(self.arrive(),'synthetic-pending')
        self.assertEqual(self.launch.call_args.kwargs['turn_id'],'')
        self.launch.assert_called_once()

    def test_launch_failure_does_not_retry_or_raise(self):
        T.current.set('synthetic-http-request');self.launch.side_effect=OSError('synthetic failure')
        self.assertIsNone(self.arrive());self.launch.assert_called_once()

    def test_actual_bilateral_wrapper_and_concurrent_arrivals_share_only_their_request(self):
        current=self.current
        class Interaction:
            def __init__(self,raw,surface,event_id=None,test_mode=False):
                self.turn=C.begin(raw,surface,event_id=event_id,test_mode=test_mode)
            def prompt(self):return ''
            def admitted(self,prompt):pass
            def complete(self,reply):return reply
            def failed(self):raise AssertionError('unexpected generation failure')
        seen={}
        self.launch.side_effect=lambda her,**kw:seen.setdefault(her,kw['turn_id'])
        async def engine(tag,messages,message,user_msg,params):
            await asyncio.sleep(0)
            return 'synthetic reply to '+user_msg
        self.ns['_bilateral_reply_engine']=engine
        async def work(key):
            token=T.current.set(key)
            try:
                self.arrive(her=key)
                reply=await self.ns['_bilateral_reply']('chatfull',[{'content':'synthetic prompt'}],key,key,{})
                return key,current.get().turn_id,reply
            finally:T.current.reset(token)
        async def both():return await asyncio.gather(work('fixture-one'),work('fixture-two'))
        with patch.dict(sys.modules,stratagem_turn=types.SimpleNamespace(Interaction=Interaction,current=current)):
            rows=asyncio.run(both())
        for key,actual,reply in rows:
            self.assertEqual(seen[key],actual);self.assertEqual(reply,'synthetic reply to '+key)
        self.assertNotEqual(rows[0][1],rows[1][1]);self.assertIsNone(T.current.get())

    def test_duplicate_request_keeps_existing_event_identity(self):
        T.current.set('synthetic-retry');self.arrive();one=self.launch.call_args.kwargs['turn_id']
        self.arrive();self.assertEqual(self.launch.call_args.kwargs['turn_id'],one)
        self.assertEqual(C.begin('synthetic','phone',event_id='synthetic-retry').turn_id,one)

    def test_reserved_key_survives_actual_pending_and_forecast_log(self):
        import test_witness_forecast_handoffs as F
        case=F.Tests('test_actual_launch_and_job_join_without_changing_saved_row')
        case.setUp();self.addCleanup(case.doCleanups)
        head=types.SimpleNamespace(**vars(case.case.sh),launch_on_message=case.case.ns['launch_on_message'])
        T.current.set('synthetic-http-request')
        with patch.dict(sys.modules,jepa_self_head=head):
            with patch('time.time',return_value=200.):path=self.arrive()
            row=case.run_job(path)
        actual=C.begin('synthetic arrival','phone',event_id=T.current.get())
        self.assertEqual(row['turn_id'],actual.turn_id)
        self.assertEqual(len(row['turn_id']),66)
        self.assertEqual(row['surface'],'chat/full')
        self.assertEqual(case.audit([row])['states']['joined'],1)
        self.assertEqual(row,json.loads(case.case.output.read_text()))

if __name__=='__main__':unittest.main()
