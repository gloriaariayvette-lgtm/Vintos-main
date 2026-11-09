#!/usr/bin/env python3
"""Execute real router branches with synthetic providers and a stubbed ledger."""
import ast
import asyncio
import contextlib
import copy
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'bin'),str(ROOT/'scripts')]
import gen_result as G
import witness_capture as W

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='router-completion-fixture-');self.addCleanup(self.tmp.cleanup)
        self.scratch=Path(self.tmp.name).resolve();self.assertNotIn('.vintos',self.scratch.parts)
        self.sender=Mock(side_effect=AssertionError('no external call'))
        p=patch.object(socket.socket,'connect',self.sender);p.start();self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called);self.assertIsInstance(self.sender,Mock)
        self.record=Mock()
        self.accounting=types.SimpleNamespace(record=self.record)
        p=patch.dict(sys.modules,compute_admission=self.accounting);p.start();self.addCleanup(p.stop)
        tree=ast.parse((ROOT/'bin/model_router.py').read_text())
        nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and
               n.name in ('_ledger','route_reply_result','route_reply')]
        self.assertEqual(len(nodes),3)
        self.a=AsyncMock(return_value=('synthetic direct reply','existing reasoning'))
        self.b=AsyncMock(return_value=('synthetic direct reply',''))
        self.fallback=AsyncMock(return_value=G.make_result('synthetic-primary',model='fixture-fallback',status='valid',text='synthetic fallback',finish_reason='stop'))
        self.last=AsyncMock(return_value=G.make_result('synthetic-last',model='fixture-last',status='valid',text='synthetic last',finish_reason='stop'))
        self.ns=dict(GR=G,profile=lambda:'mixed',_needs_provider=lambda *a:[],_consume_forced=lambda:False,
                     CLAUDE_SURFACES={'avatar','chat'},read_mode=lambda:{'mode':'sol'},sol_draft=self.a,
                     gemini_draft=self.b,SOL_MODEL='fixture-request-a',GEMINI_MODEL='fixture-request-b',
                     GEMMA_MODEL='fixture-local',_claude=self.fallback,_grok_result=self.last,
                     _reserve_provider=Mock(),has_images=lambda _:False,current_claude_model=lambda:'fixture-fallback',
                     words_left=lambda _:True,ROUTE_BUDGET_S=1,ROUTE_FLOOR_S=1)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual-router-functions','exec'),self.ns)

    def run_route(self,mode,surface='avatar',observer=None):
        self.ns['read_mode']=lambda:{'mode':mode}
        with contextlib.redirect_stdout(io.StringIO()):
            return asyncio.run(self.ns['route_reply'](surface,'synthetic system',[{'role':'user','content':'synthetic input'}],
                         {'max_tokens':123},'unused',{},'fixture-final-model',observer=observer))

    def test_each_direct_success_records_once_without_changing_reply_or_calls(self):
        for mode,provider,model,draft in [('sol','openai','fixture-request-a',self.a),('argon','google','fixture-request-b',self.b)]:
            self.record.reset_mock();self.a.reset_mock();self.b.reset_mock()
            result=self.run_route(mode)
            self.assertEqual(result,('synthetic direct reply','',mode))
            self.assertEqual(self.record.call_count,1)
            args,kwargs=self.record.call_args
            self.assertEqual(args,('router:avatar','foreground'))
            self.assertEqual(kwargs['provider'],provider);self.assertEqual(kwargs['model'],model)
            self.assertEqual(kwargs['stage'],mode);self.assertGreaterEqual(kwargs['latency_ms'],0)
            self.assertEqual(kwargs['extra']['model_identity_evidence'],'configured')
            self.assertIsNone(kwargs['extra']['provider_request_id'])
            draft.assert_awaited_once()
            self.fallback.assert_not_awaited();self.last.assert_not_awaited()
            self.assertEqual(self.a.await_count+self.b.await_count,1)
            self.assertNotIn('synthetic direct reply',str(self.record.call_args))
            self.assertNotIn('synthetic input',str(self.record.call_args))
            self.assertEqual(list(self.scratch.iterdir()),[])

    def test_logging_failure_never_causes_retry_or_fallback(self):
        self.record.side_effect=OSError('synthetic ledger failure')
        for mode in ('sol','argon'):
            self.assertEqual(self.run_route(mode)[0],'synthetic direct reply')
        self.assertEqual(self.record.call_count,2)
        self.a.assert_awaited_once();self.b.assert_awaited_once()
        self.fallback.assert_not_awaited();self.last.assert_not_awaited()

    def test_empty_or_raised_direct_call_keeps_existing_fallback(self):
        for mode,draft in [('sol',self.a),('argon',self.b)]:
            for failure in (None,RuntimeError('synthetic draft failure')):
                draft.side_effect=failure
                draft.return_value=(None,'')
                self.record.reset_mock();self.fallback.reset_mock()
                self.assertEqual(self.run_route(mode)[0],'synthetic fallback')
                self.fallback.assert_awaited_once()
                self.assertEqual(self.record.call_count,1)
                self.assertEqual(self.record.call_args.kwargs['stage'],'claude')
                self.assertNotIn('model_identity_evidence',self.record.call_args.kwargs['extra'])
            draft.side_effect=None

    def test_real_surface_is_preserved(self):
        self.run_route('argon',surface='chat')
        self.assertEqual(self.record.call_args.args,('router:chat','foreground'))

    def test_forced_route_does_not_consume_a_toggle_call(self):
        self.ns['_consume_forced']=lambda:True
        self.assertEqual(self.run_route('argon')[0],'synthetic last')
        self.a.assert_not_awaited();self.b.assert_not_awaited()
        self.assertEqual(self.record.call_args.kwargs['stage'],'grok')
        self.assertNotIn('model_identity_evidence',self.record.call_args.kwargs['extra'])

    def test_configured_label_does_not_become_observed_witness_identity(self):
        for mode in ('sol','argon'):
            capture=W.Capture('synthetic-turn','synthetic-surface',100)
            result=self.run_route(mode,observer=capture.observe)
            self.assertEqual(result[0],'synthetic direct reply')
            self.assertEqual(len(capture._attempts),1)
            self.assertIsNone(capture._attempts[0]['served_model'])
            self.assertEqual(capture._attempts[0]['identity_evidence'],'unknown')

    def test_existing_ledger_metadata_shape_is_unchanged(self):
        result=G.make_result('synthetic-provider',model='synthetic-model',status='valid',request_id='synthetic-request',text='synthetic reply',finish_reason='stop')
        before=copy.deepcopy(result)
        self.ns['_ledger'](result,'chat',0,'synthetic-stage')
        self.assertEqual(result,before)
        self.assertEqual(self.record.call_args.kwargs['extra'],{'provider_request_id':'synthetic-request','finish_reason':'stop'})

if __name__=='__main__':unittest.main()
