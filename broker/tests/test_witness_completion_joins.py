#!/usr/bin/env python3
"""Synthetic selected-completion correlation, with no provider or live-store access."""
import ast
import asyncio
import copy
import hashlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'bin')]
import request_trace as T
import witness_attribution as A
import build_merged_chat as B
from test_witness_router_completions import Tests as RouterCase


class Tests(unittest.TestCase):
    def setUp(self):
        self.case = RouterCase('test_each_direct_success_records_once_without_changing_reply_or_calls')
        self.case.setUp(); self.addCleanup(self.case.doCleanups)
        token = T.current.set('synthetic-http-request'); self.addCleanup(T.current.reset, token)
        self.assertTrue(hasattr(self.case.record, 'mock_calls'))
        self.assertNotIn('.vintos', self.case.scratch.parts)
        self.config = dict(window_seconds=10, window30_enabled=True, surface_callers={'avatar':['router:avatar']})

    def routed(self):
        observation, options = T.prepare_reply_join({})
        result = self.case.run_route('sol', observer=options['observer'])
        args, kw = self.case.record.call_args
        call = dict(at=10, organ=args[0], provider=kw['provider'], model=kw['model'],
                    stage=kw['stage'], request_id=T.current.get(), **{'class':args[1]}, **kw['extra'])
        # This synthetic provider supplied no response identity; explicitly mark
        # one here only in tests exercising correlation independently of identity.
        call['model_identity_evidence'] = 'response_metadata'
        text = result[0]
        row = dict(role='assistant',content=text,turn_id='synthetic-turn',surface='avatar',timestamp=150,
                   **observation.fields(text,text))
        return observation, row, call

    def test_same_key_in_real_router_record_and_merged_history_joins_far_apart(self):
        _, row, call = self.routed()
        row = B.entry(row,'assistant',row['content'],150,'synthetic-copy')
        self.assertEqual(row['generation_join']['completion_id'],call['generation_completion_id'])
        report, details = A.attribution([row],[call],self.config,200)
        self.assertEqual(details[0]['join'],'generation_completion_id')
        self.assertEqual(details[0]['tier'],'ledger_attributed')
        self.assertEqual(report['window30']['added_copies'],0)
        self.assertNotIn(row['content'], str(self.case.record.call_args))

    def test_same_http_request_and_same_text_still_get_different_completion_keys(self):
        first, row1, call1 = self.routed()
        second, row2, call2 = self.routed()
        self.assertNotEqual(call1['generation_completion_id'],call2['generation_completion_id'])
        self.assertEqual(call1['request_id'],call2['request_id'])
        row2['turn_id']='other-synthetic-turn'
        report, details = A.attribution([row1,row2],[call1,call2],self.config,200)
        self.assertEqual(report['tiers']['ledger_attributed'],2)
        self.assertEqual(len({d['ledger_sha256'] for d in details}),2)

    def test_match_method_counts_partition_only_retained_matches(self):
        _, exact, call = self.routed()
        provider = dict(role='assistant',content='synthetic provider reply',turn_id='provider-turn',
                        surface='avatar',timestamp=160,provider_request_id='synthetic-provider-request')
        nearby = dict(role='assistant',content='synthetic nearby reply',turn_id='nearby-turn',
                      surface='avatar',timestamp=170)
        provider_call = dict(at=30,organ='router:avatar',model='synthetic-model',provider='synthetic-provider',
                             provider_request_id=provider['provider_request_id'],**{'class':'foreground'})
        nearby_call = dict(at=170,organ='router:avatar',model='synthetic-model',provider='synthetic-provider',
                          **{'class':'foreground'})
        rows = [exact, copy.deepcopy(exact), provider, nearby, dict(nearby, timestamp=200)]
        ledger = [call, copy.deepcopy(call), provider_call, nearby_call]
        before = copy.deepcopy((rows, ledger, self.config))
        report, _ = A.attribution(rows, ledger, self.config, 200)
        self.assertEqual(report['matched_methods'],dict(generation_completion_id=2,provider_request_id=1,nearest_time=1))
        self.assertEqual(sum(report['matched_methods'].values()),report['join_states']['matched'])
        self.assertEqual(report['excluded'],{'outside_cutoff':1})
        self.assertEqual((rows, ledger, self.config),before)
        # An exact key claimed by another distinct turn is no longer a match.
        rows.append(dict(exact,turn_id='other-exact-turn'))
        report, _ = A.attribution(rows,ledger,self.config,200)
        self.assertEqual(report['matched_methods'],dict(generation_completion_id=0,provider_request_id=1,nearest_time=1))
        # A conflicting ledger copy also removes all exact-key matches.
        report, _ = A.attribution([exact],[call,dict(call,model='other')],self.config,200)
        self.assertEqual(sum(report['matched_methods'].values()),0)

    def test_missing_or_conflicting_completion_never_falls_back_to_time(self):
        _, row, call = self.routed()
        nearby = dict(call,at=150,generation_completion_id='0'*32)
        for calls in ([nearby],[call,dict(call,model='other-model')]):
            report, details = A.attribution([row],calls,self.config,200)
            self.assertEqual(report['tiers']['ledger_attributed'],0)
            self.assertEqual(report['window30']['added_copies'],0)
        for key,value in [('request_id','other-request'),('generation_response_sha256','0'*64)]:
            report, details = A.attribution([row],[dict(call,**{key:value})],self.config,200)
            self.assertEqual(details[0]['join_state'],'completion_binding_mismatch')

    def test_postprocessing_is_explicit_and_changed_history_is_held(self):
        observation,row,call=self.routed()
        raw=row['content']; row['content']=raw+' synthetic device mark'
        row.update(observation.fields(raw,row['content']))
        self.assertEqual(A.attribution([row],[call],self.config,200)[0]['tiers']['ledger_attributed'],1)
        row['content']+=' changed later'
        self.assertEqual(A.attribution([row],[call],self.config,200)[1][0]['join_state'],'invalid_completion_join')
        self.assertEqual(observation.fields('wrong raw',raw),{})

    def test_provider_id_mismatch_and_configured_identity_stay_held(self):
        _,row,call=self.routed()
        row['provider_request_id']='different-provider-id'
        self.assertEqual(A.attribution([row],[call],self.config,200)[1][0]['join_state'],'completion_provider_id_mismatch')
        row.pop('provider_request_id');call['model_identity_evidence']='configured'
        self.assertEqual(A.attribution([row],[call],self.config,200)[1][0]['join_state'],'call_model_identity_unobserved')

    def test_observer_failure_and_missing_origin_never_change_reply(self):
        callback=Mock(side_effect=ValueError('synthetic observer failure'))
        observation,options=T.prepare_reply_join({'observer':callback})
        answer=self.case.run_route('sol',observer=options['observer'])
        self.assertTrue(observation.fields(answer[0],answer[0]));callback.assert_called_once()
        observation.observe({'status':'valid','text':answer[0]})
        self.assertEqual(observation.fields(answer[0],answer[0]),{})
        self.case.record.side_effect=OSError('synthetic disk failure')
        self.assertEqual(self.case.run_route('sol',observer=options['observer']),answer)

    def test_actual_handler_selects_invocation_and_binds_saved_history(self):
        tree=ast.parse((ROOT/'bin/server.py').read_text())
        handler=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='avatar_chat')
        helper=next(n for n in ast.walk(handler) if isinstance(n,ast.FunctionDef) and n.name=='_prepare_history_join')
        routes=sorted([n for n in ast.walk(handler) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Await)
                       and isinstance(n.value.value,ast.Call) and isinstance(n.value.value.func,ast.Attribute)
                       and n.value.value.func.attr=='route_reply'],key=lambda n:n.lineno)
        prepares=sorted([n for n in ast.walk(handler) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call)
                         and isinstance(n.value.func,ast.Name) and n.value.func.id=='_prepare_history_join'],key=lambda n:n.lineno)
        selects=sorted([n for n in ast.walk(handler) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Name)
                        and n.value.id=='_history_join_candidate'],key=lambda n:n.lineno)
        self.assertEqual((len(routes),len(prepares),len(selects)),(3,3,3))
        router=types.SimpleNamespace(route_reply=self.case.ns['route_reply'])
        ns=dict(_mr=router,_witness_kwargs={},messages=[{'content':'synthetic system'},{'role':'user','content':'synthetic input'}],
                params={},LM_STUDIO_API='unused',LLM_AUTH_HEADERS={},_reason=False,_again=[])
        # Execute each actual route/preparation/selection fragment in its order.
        for prepare,route,select in zip(prepares,routes,selects):
            self.assertLess(prepare.lineno,route.lineno);self.assertLess(route.lineno,select.lineno)
            ns['_witness_kwargs']={}
            fn=ast.AsyncFunctionDef(name='exercise',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),
                body=ast.parse('_witness_kwargs = {}').body + [helper,prepare,route,select,ast.Return(value=ast.Name(id='_history_join_selected',ctx=ast.Load()))],decorator_list=[])
            module=ast.fix_missing_locations(ast.Module(body=copy.deepcopy([fn]),type_ignores=[]))
            exec(compile(module,'actual-handler-join','exec'),ns)
            selected=asyncio.run(ns['exercise']())
            raw= 'synthetic direct reply'
            self.assertTrue(selected.fields(raw,raw))
        append=next(n for n in ast.walk(handler) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
                    and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name)
                    and n.value.func.value.id=='av_history' and n.value.func.attr=='append'
                    and any(isinstance(k,ast.Constant) and k.value=='served_by' for k in n.value.args[0].keys))
        ns.update(av_history=[],reply=raw,_turn_marks='',_model_used='synthetic-route',_prov_envelope=None,
                  _history_join_fields=selected.fields(raw,raw))
        exec(compile(ast.Module(body=[append],type_ignores=[]),'actual-history-append','exec'),ns)
        self.assertEqual(ns['av_history'][0]['generation_join']['completion_id'],selected.join['completion_id'])

    def test_actual_repeat_decision_keeps_only_accepted_completion(self):
        tree=ast.parse((ROOT/'bin/server.py').read_text())
        handler=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='avatar_chat')
        helper=next(n for n in ast.walk(handler) if isinstance(n,ast.FunctionDef) and n.name=='_prepare_history_join')
        repeat=next(n for n in ast.walk(handler) if isinstance(n,ast.Try) and any(
            isinstance(x,ast.If) and isinstance(x.test,ast.Call) and isinstance(x.test.func,ast.Name)
            and x.test.func.id=='_same_as_last_reply' for x in n.body))
        for second, expected in (('synthetic accepted','second'),('synthetic repeat',None),(RuntimeError('synthetic failure'),'first')):
            observations=[]
            async def router(*args,observer=None,**kw):
                text='synthetic repeat' if not observations else second
                if isinstance(text,Exception): raise text
                result=dict(status='valid',text=text)
                T.completion_join(result,'avatar');observations.append(result['ledger_join'])
                if observer:observer(result)
                return text,'','synthetic-route'
            ns=dict(_mr=types.SimpleNamespace(route_reply=router),_prepare_witness=lambda *a:(None,{}),
                    _same_as_last_reply=lambda text, history:text=='synthetic repeat',av_history=[],
                    messages=[{'content':'synthetic system'},{'role':'user','content':'synthetic input'}],
                    params={},LM_STUDIO_API='unused',LLM_AUTH_HEADERS={},_reason=False)
            prefix=ast.parse('''_first, options = _prepare_history_join({})
reply, _claude_reasoning, _model_used = await _mr.route_reply(observer=options['observer'])
_history_join_selected = _first
_witness_selected = None
''').body
            suffix=ast.parse('return reply, _history_join_selected').body
            fn=ast.AsyncFunctionDef(name='exercise',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),
                body=[helper]+prefix+[repeat]+suffix,decorator_list=[])
            exec(compile(ast.fix_missing_locations(ast.Module(body=copy.deepcopy([fn]),type_ignores=[])),'actual-repeat','exec'),ns)
            reply,selected=asyncio.run(ns['exercise']())
            if expected is None:
                self.assertIsNone(selected);self.assertEqual(reply,'')
            else:
                self.assertEqual(selected.join,observations[-1])
                self.assertTrue(selected.fields(reply,reply))

    def test_concurrent_request_trace_and_completion_identity_are_independent(self):
        async def run(trace):
            token=T.current.set(trace)
            try:
                observation, options=T.prepare_reply_join({})
                await asyncio.sleep(0)
                result=dict(status='valid',text='same synthetic text')
                T.completion_join(result,'avatar');options['observer'](result)
                await asyncio.sleep(0)
                return observation.join
            finally:T.current.reset(token)
        async def both():return await asyncio.gather(run('first-request'),run('second-request'))
        first,second=asyncio.run(both())
        self.assertEqual((first['request_trace_id'],second['request_trace_id']),('first-request','second-request'))
        self.assertNotEqual(first['completion_id'],second['completion_id'])


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    sys.exit(not result.wasSuccessful())
