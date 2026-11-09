#!/usr/bin/env python3
"""Response identity from actual draft parsers; synthetic responses and stub sends."""
import ast
import asyncio
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'bin'),str(ROOT/'scripts')]
import witness_capture as W
spec=importlib.util.spec_from_file_location('draft_router_fixture',ROOT/'broker/tests/test_witness_router_completions.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)

class Tests(unittest.TestCase):
    def setUp(self):
        self.case=F.Tests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.ns=self.case.ns
        self.root=self.case.scratch
        (self.root/'.vintos/logs').mkdir(parents=True)
        p=patch.dict(os.environ,HOME=str(self.root));p.start();self.addCleanup(p.stop)
        self.response_a={'model':'fixture-served-a','id':'fixture-response-a','status':'completed',
                         'output':[{'type':'message','content':[{'type':'output_text','text':' synthetic direct reply '}]}]}
        self.response_b={'modelVersion':'fixture-served-b','responseId':'fixture-response-b',
                         'candidates':[{'content':{'parts':[{'text':' synthetic direct reply '},{'text':'private thought sentinel','thought':True}]}}]}
        self.requests=[]
        def send(_call,_owner,request,**kwargs):
            self.requests.append(json.loads(request.data))
            return io.BytesIO(json.dumps(self.response_a).encode())
        async def asend(_call,_owner,url,**kwargs):
            self.requests.append(copy.deepcopy(kwargs['json']))
            return types.SimpleNamespace(json=lambda:copy.deepcopy(self.response_b))
        self.send=Mock(side_effect=send)
        self.asend=__import__('unittest.mock',fromlist=['AsyncMock']).AsyncMock(side_effect=asend)
        class Client:
            def __init__(self,**kwargs):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            def post(self,*args,**kwargs):raise AssertionError('real post forbidden')
        self.ns.update(__file__=str(ROOT/'bin/model_router.py'),hashlib=hashlib,os=os,json=json,paid_http=types.SimpleNamespace(send=self.send,asend=self.asend),
                       httpx=types.SimpleNamespace(AsyncClient=Client),_openai_key=lambda:'fixture-key',_env=lambda name:'fixture-key',
                       for_responses=lambda rows:rows,for_gemini=lambda rows:rows,
                       GOOGLE_USAGE_LOG=str(self.root/'usage.jsonl'))
        tree=ast.parse((ROOT/'bin/model_router.py').read_text())
        nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and
               n.name in ('_observe_draft_identity','sol_draft','gemini_draft')]
        self.assertEqual(len(nodes),3)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual-draft-parsers','exec'),self.ns)
        self.assertIs(self.ns['paid_http'].send,self.send)
        self.assertIs(self.ns['paid_http'].asend,self.asend)

    def draft(self,name,observer=None):
        return asyncio.run(self.ns[name]('synthetic system',[{'role':'user','content':'synthetic input'}],identity_observer=observer))

    def test_public_tuple_and_payload_are_unchanged_with_observation(self):
        for name in ('sol_draft','gemini_draft'):
            old=self.draft(name);old_request=self.requests[-1]
            receipt={};new=self.draft(name,receipt.update)
            self.assertEqual(old,new);self.assertEqual(new,('synthetic direct reply',''))
            self.assertEqual(old_request,self.requests[-1])
            self.assertEqual(set(receipt),{'schema','observed_model','request_id','text_sha256'})
            self.assertEqual(receipt['text_sha256'],hashlib.sha256(new[0].encode()).hexdigest())
            self.assertNotIn('synthetic direct reply',json.dumps(receipt))
            self.assertNotIn('private thought sentinel',json.dumps(receipt))
            self.assertNotIn('fixture-key',json.dumps(receipt))
        self.assertEqual(self.send.call_count,2);self.assertEqual(self.asend.await_count,2)

    def test_response_model_and_request_reach_the_same_routed_capture(self):
        for mode,model,request in [('sol','fixture-served-a','fixture-response-a'),('argon','fixture-served-b','fixture-response-b')]:
            self.case.record.reset_mock()
            capture=W.Capture('synthetic-turn','synthetic-surface',100)
            result=self.case.run_route(mode,observer=capture.observe)
            self.assertEqual(result,('synthetic direct reply','',mode))
            attempt=capture._attempts[0]
            self.assertEqual(attempt['served_model'],model)
            self.assertEqual(attempt['identity_evidence'],'response_metadata')
            self.assertEqual(attempt['provider_request_id'],request)
            capture.select(result[0])
            packet=capture.finalize(result[0],110)
            self.assertEqual(packet['observed_attempts'][0]['provider_request_id'],request)
            self.assertNotIn('provider_request_id',packet['witness_receipt']['generation']['attempts'][0])
            self.assertEqual(self.case.record.call_args.kwargs['model'],model)
            self.assertEqual(self.case.record.call_args.kwargs['extra']['provider_request_id'],request)
            self.assertEqual(self.case.record.call_args.kwargs['extra']['model_identity_evidence'],'response_metadata')
        self.assertEqual(self.send.call_count,1);self.assertEqual(self.asend.await_count,1)
        self.case.fallback.assert_not_awaited();self.case.last.assert_not_awaited()

    def test_missing_metadata_does_not_borrow_configuration(self):
        self.response_a.pop('model');self.response_a.pop('id')
        self.response_b.pop('modelVersion');self.response_b.pop('responseId')
        for mode in ('sol','argon'):
            capture=W.Capture('synthetic-turn','synthetic-surface',100)
            self.case.run_route(mode,observer=capture.observe)
            self.assertIsNone(capture._attempts[0]['served_model'])
            self.assertEqual(self.case.record.call_args.kwargs['extra']['model_identity_evidence'],'configured')
            self.assertIsNone(self.case.record.call_args.kwargs['extra']['provider_request_id'])

    def test_request_id_without_model_does_not_claim_model_identity(self):
        self.response_a.pop('model')
        capture=W.Capture('synthetic-turn','synthetic-surface',100)
        self.case.run_route('sol',observer=capture.observe)
        self.assertIsNone(capture._attempts[0]['served_model'])
        self.assertEqual(self.case.record.call_args.kwargs['extra']['provider_request_id'],'fixture-response-a')
        self.assertEqual(self.case.record.call_args.kwargs['extra']['model_identity_evidence'],'configured')

    def test_invalid_metadata_and_changed_output_do_not_bind(self):
        for value in (None,1,True,{},[], ' bad ', 'bad\nvalue','x'*257):
            self.response_a.update(model=value,id=value)
            receipt={};self.draft('sol_draft',receipt.update)
            self.assertIsNone(receipt['observed_model']);self.assertIsNone(receipt['request_id'])
        result={'text':'different synthetic text','request_id':'','model':'fixture-request'}
        receipt={'schema':'draft-response-identity-v1','observed_model':'fixture-served',
                 'request_id':'fixture-id','text_sha256':hashlib.sha256(b'original synthetic text').hexdigest()}
        before=copy.deepcopy(result)
        self.assertEqual(self.ns['_bind_draft_identity'](result,receipt),'configured')
        self.assertEqual(result,before)

    def test_observer_exception_never_changes_draft_or_adds_call(self):
        bad=Mock(side_effect=OSError('synthetic observer failure'))
        self.assertEqual(self.draft('sol_draft',bad),('synthetic direct reply',''))
        self.assertEqual(self.draft('gemini_draft',bad),('synthetic direct reply',''))
        self.assertEqual(bad.call_count,2)
        self.assertEqual(self.send.call_count,1);self.assertEqual(self.asend.await_count,1)

    def test_empty_output_emits_no_selected_identity(self):
        self.response_a['output']=[];self.response_b['candidates']=[]
        observer=Mock()
        self.assertEqual(self.draft('sol_draft',observer),(None,''))
        self.assertEqual(self.draft('gemini_draft',observer),(None,''))
        observer.assert_not_called()

    def test_failed_direct_path_does_not_leak_previous_call_metadata(self):
        self.case.run_route('sol')
        self.response_a['output']=[]
        capture=W.Capture('synthetic-next','synthetic-surface',100)
        self.assertEqual(self.case.run_route('sol',observer=capture.observe)[0],'synthetic fallback')
        self.assertNotEqual(capture._attempts[0]['served_model'],'fixture-served-a')
        self.assertNotEqual(self.case.record.call_args.kwargs['extra'].get('provider_request_id'),'fixture-response-a')

    def test_concurrent_same_text_requests_keep_distinct_identity(self):
        async def scenario():
            waiting=0;gate=asyncio.Event()
            async def concurrent(*args,**kwargs):
                nonlocal waiting
                waiting+=1;number=waiting
                if waiting==2:gate.set()
                await gate.wait()
                # The callback is passed through the actual draft parser.
                value=copy.deepcopy(self.response_b)
                value['modelVersion']='fixture-served-'+str(number)
                value['responseId']='fixture-request-'+str(number)
                return types.SimpleNamespace(json=lambda:value)
            self.asend.side_effect=concurrent
            records=[]
            async def one():
                observed=[]
                self.ns['read_mode']=lambda:{'mode':'argon'}
                result=await self.ns['route_reply']('avatar','synthetic',[],{},'unused',{},'fixture',observer=lambda r:observed.append(r))
                records.append((result,observed[0]))
            with contextlib.redirect_stdout(io.StringIO()):await asyncio.gather(one(),one())
            return records
        import contextlib
        records=asyncio.run(scenario())
        identities={(r['observed_model'],r['request_id']) for _,r in records}
        self.assertEqual(identities,{('fixture-served-1','fixture-request-1'),('fixture-served-2','fixture-request-2')})
        self.assertTrue(all(result[0]=='synthetic direct reply' for result,_ in records))

if __name__=='__main__':unittest.main()
