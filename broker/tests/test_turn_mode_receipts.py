#!/usr/bin/env python3
"""Synthetic decision observations; no live stores, gate calls or external sends."""
import ast
import asyncio
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,Mock,patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts')]
import request_trace as T
import build_merged_chat as B


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='turn-mode-fixture-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        for p in (patch.object(socket.socket,'connect',self.sender),patch.object(T,'LOG',str(self.root/'trace.jsonl')),
                  patch.dict(os.environ,SPARK_WORKSPACE=str(self.root))):
            p.start();self.addCleanup(p.stop)
        token=T.current.set('fixture-request');self.addCleanup(T.current.reset,token)
        self.addCleanup(self.sender.assert_not_called)
        self.assertNotIn('.vintos',self.root.parts);self.assertIsInstance(self.sender,Mock)
        self.tree=ast.parse((ROOT/'bin/server.py').read_text())
        self.handler=next(n for n in self.tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='avatar_chat')

    def observation(self):
        observation=T.TurnModeDecision('fixture-turn','avatar',clock=iter([10.,11.,12.,13.]).__next__)
        result=dict(status='valid',text='synthetic reply')
        T.completion_join(result,'avatar')
        join,_=T.prepare_reply_join({});join.observe(result)
        return observation,join

    def test_no_extra_io_and_exact_gate_values_only(self):
        for answer,mode,basis in [('YES','intimate','gate_yes'),('NO','opening_everyday','gate_no'),
                                  ('YES maybe','unknown','gate_ambiguous'),('private marker','unknown','gate_ambiguous')]:
            with patch('builtins.open',side_effect=AssertionError('no observation IO')):
                obs,join=self.observation();obs.note('gate',answer,join.join)
                row=obs.fields(join.join,'synthetic reply','stored synthetic reply')['mode_receipt']
            self.assertEqual((row['mode'],row['basis']),(mode,basis))
            self.assertNotIn(answer,json.dumps(row))
            self.assertEqual((row['started_at'],row['decision_at']),(10.,11.))
            self.assertEqual((row['turn_id'],row['request_id']),('fixture-turn','fixture-request'))

    def test_unevaluated_gate_and_error_remain_unknown(self):
        obs,join=self.observation()
        row=obs.fields(join.join,'synthetic reply','synthetic reply')['mode_receipt']
        self.assertEqual((row['mode'],row['basis'],row['decision_at']),('unknown','gate_not_evaluated',None))
        obs.note('error');self.assertEqual(obs.row['basis'],'gate_error')
        obs,join=self.observation();obs.note('gate','YES',join.join);obs.note('error')
        self.assertEqual(obs.row['mode'],'intimate')

    def test_binding_rejects_other_request_reply_turn_surface_and_extra_fields(self):
        obs,join=self.observation();obs.note('gate','YES',join.join)
        row=obs.fields(join.join,'synthetic reply','synthetic reply')['mode_receipt']
        self.assertEqual(obs.fields(dict(join.join,request_trace_id='other'),'synthetic reply','synthetic reply'),{})
        self.assertEqual(obs.fields(join.join,'different','synthetic reply'),{})
        for tid,surface,text in [('other','avatar','synthetic reply'),('fixture-turn','reelroom','synthetic reply'),
                                 ('fixture-turn','avatar','other')]:
            self.assertEqual(T.mode_receipt_fields(row,tid,surface,text),{})
        for key,value in [('text','private marker'),('mode','opening_everyday'),('decision_at',float('nan')),
                          ('decision_at',9),('selected_completion_id','bad'),('basis','unrecognized')]:
            self.assertEqual(T.mode_receipt_fields(dict(row,**{key:value}),'fixture-turn','avatar','synthetic reply'),{})

    def test_existing_ids_are_required_and_concurrent_requests_do_not_cross(self):
        for tid in ('',None,'private space'):
            with self.assertRaises(ValueError):T.TurnModeDecision(tid,'avatar')
        async def one(name):
            token=T.current.set(name)
            try:
                obs,join=self.observation();await asyncio.sleep(0)
                return obs.fields(join.join,'synthetic reply','synthetic reply')['mode_receipt']['request_id']
            finally:T.current.reset(token)
        async def both():return await asyncio.gather(one('request-a'),one('request-b'))
        self.assertEqual(asyncio.run(both()),['request-a','request-b'])

    def test_environment_is_bounded_exact_bound_and_merge_preserves_receipt(self):
        obs,join=self.observation();obs.note('gate','NO',join.join)
        fields=obs.fields(join.join,'synthetic reply','synthetic reply');row=fields['mode_receipt']
        env={T.MODE_ENV:json.dumps(row)}
        self.assertEqual(T.mode_receipt_from_env(env,'fixture-turn','avatar','synthetic reply'),fields)
        for value in ('bad','x'*4097,json.dumps(dict(row,text='private marker'))):
            self.assertEqual(T.mode_receipt_from_env({T.MODE_ENV:value},'fixture-turn','avatar','synthetic reply'),{})
        merged=B.entry(dict(role='assistant',content='synthetic reply',turn_id='fixture-turn',surface='avatar',**fields),
                       'assistant','synthetic reply',20,'fixture-source')
        self.assertEqual(merged['mode_receipt'],row)
        # Execute the actual ledger insertion with synthetic entry/environment only.
        tree=ast.parse((ROOT/'scripts/interaction-ledger.py').read_text())
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.Try) and any(
            isinstance(x,ast.ImportFrom) and x.module=='request_trace' for x in n.body))
        ns=dict(entry={'turn_id':'fixture-turn','surface':'avatar'},os=types.SimpleNamespace(environ=env),vintos_said='synthetic reply')
        exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-ledger-mode-insertion','exec'),ns)
        self.assertEqual(ns['entry']['mode_receipt'],row)

    def test_actual_history_handoff_with_capture_off_binds_marks_separately(self):
        obs,join=self.observation();obs.note('gate','YES',join.join)
        # Choose the narrow metadata try, not the enclosing history workflow.
        candidates=[n for n in ast.walk(self.handler) if isinstance(n,ast.Try) and any(
            isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and isinstance(x.func.value,ast.Name)
            and x.func.value.id=='_mode_observation' and x.func.attr=='fields' for x in ast.walk(n))]
        block=min(candidates,key=lambda n:n.end_lineno-n.lineno)
        ns=dict(_mode_observation=obs,_history_join_selected=join,_history_join_raw='synthetic reply',
            reply='stored synthetic reply',_turn_marks=' synthetic mark',_history_join_fields={},_mode_writer_env={},_witness_capture=None)
        with patch('builtins.open',side_effect=AssertionError('no added file write')):
            exec(compile(ast.Module(body=[block],type_ignores=[]),'actual-history-mode-fields','exec'),ns)
        history=ns['_history_join_fields']['mode_receipt']
        ledger=json.loads(ns['_mode_writer_env'][T.MODE_ENV])
        self.assertEqual(history['receipt_id'],ledger['receipt_id'])
        self.assertNotEqual(history['response_sha256'],ledger['response_sha256'])
        self.assertTrue(T.mode_receipt_fields(history,'fixture-turn','avatar','stored synthetic reply synthetic mark'))
        self.assertTrue(T.mode_receipt_fields(ledger,'fixture-turn','avatar','stored synthetic reply'))
        post=next(n for n in ast.walk(self.handler) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
            and n.func.id=='_post_turn')
        writer=next(k.value for k in post.keywords if k.arg=='writer_env')
        self.assertTrue(any(k.arg is None and isinstance(k.value,ast.Name) and k.value.id=='_mode_writer_env' for k in writer.keywords))

    def guard(self,answers,model='claude-synthetic',broken_observer=False,route_error=False):
        obs,join=self.observation();ns={}
        async def router(*args,observer=None,**kwargs):
            if route_error:raise RuntimeError('synthetic route failure')
            result=dict(status='valid',text='synthetic rerouted reply');T.completion_join(result,'avatar')
            if observer:observer(result)
            return result['text'],'','synthetic-rerouted'
        route=AsyncMock(side_effect=router);gate=AsyncMock(side_effect=answers)
        notifications=Mock()
        ns.update(__file__='synthetic-server.py',reply='synthetic reply',_model_used=model,_history_join_selected=join,
            _mode_observation=obs,_mr=types.SimpleNamespace(gemma_call=gate,route_reply=route,arm_grok_turns=Mock(),update_mode=Mock()),
            msg=types.SimpleNamespace(message='synthetic user input'),_surface='avatar',MEMORY=str(self.root),os=os,
            datetime=__import__('datetime').datetime,paid_http=types.SimpleNamespace(send=notifications),
            messages=[{'content':'synthetic system'},{'role':'user','content':'synthetic input'}],params={},
            LM_STUDIO_API='unused',LLM_AUTH_HEADERS={},_reason=False,
            _prepare_witness=lambda *a:(None,{}),_prepare_history_join=T.prepare_reply_join)
        helper=next(n for n in ast.walk(self.handler) if isinstance(n,ast.FunctionDef) and n.name=='_mode_note')
        block=next(n for n in ast.walk(self.handler) if isinstance(n,ast.Try) and any(
            isinstance(x,ast.Import) and any(a.asname=='_gaio' for a in x.names) for x in n.body))
        exec(compile(ast.Module(body=[helper],type_ignores=[]),'actual-mode-helper','exec'),ns)
        if broken_observer:obs.note=Mock(side_effect=RuntimeError('synthetic observer failure'))
        fn=ast.AsyncFunctionDef(name='exercise',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),
            body=ast.parse('global reply, _model_used, _history_join_selected').body+[copy.deepcopy(block)],decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'actual-gate-block','exec'),ns)
        with contextlib.redirect_stdout(io.StringIO()), patch('builtins.open',side_effect=OSError('synthetic store unavailable')):
            asyncio.run(ns['exercise']())
        self.assertIsInstance(notifications,Mock)
        return obs,join,ns,gate,route,notifications

    def test_actual_gate_branches_preserve_calls_and_record_reroute_selection(self):
        cases=[(['NO'],1,0,'opening_everyday'),(['YES','ENGAGED'],2,0,'intimate'),
               (['YES','DECLINED'],2,1,'intimate'),(['YES maybe','DECLINED'],2,1,'unknown'),
               ([RuntimeError('synthetic gate failure')],1,0,'unknown'),
               (['YES',RuntimeError('synthetic judge failure')],2,0,'intimate')]
        for answers,calls,reroutes,mode in cases:
            obs,initial,ns,gate,route,notifications=self.guard(answers)
            self.assertEqual((gate.await_count,route.await_count,notifications.call_count),(calls,reroutes,reroutes))
            selected=ns['_history_join_selected']
            row=obs.fields(selected.join,ns['reply'],ns['reply'])['mode_receipt']
            self.assertEqual(row['mode'],mode)
            if reroutes:
                self.assertEqual(row['evaluated_completion_id'],initial.join['completion_id'])
                self.assertEqual(row['selected_completion_id'],selected.join['completion_id'])
                self.assertNotEqual(row['evaluated_completion_id'],row['selected_completion_id'])
                self.assertEqual(row['reroute_decision_at'],12.);self.assertEqual(row['reroute_reason'],'refusal_guard')

    def test_failed_reroute_records_decision_without_claiming_replacement(self):
        obs,initial,ns,gate,route,notifications=self.guard(['YES','DECLINED'],route_error=True)
        self.assertEqual(ns['reply'],'synthetic reply')
        self.assertIs(ns['_history_join_selected'],initial)
        row=obs.fields(initial.join,'synthetic reply','synthetic reply')['mode_receipt']
        self.assertEqual(row['reroute_decision_at'],12.)
        self.assertEqual(row['evaluated_completion_id'],row['selected_completion_id'])
        self.assertEqual(row['mode'],'intimate');route.assert_awaited_once();notifications.assert_not_called()

    def test_actual_skipped_gate_and_observer_failure_do_not_add_calls(self):
        obs,_,_,gate,route,_=self.guard([],model='synthetic-toggle-route')
        self.assertEqual(obs.row['mode'],'unknown');gate.assert_not_awaited();route.assert_not_awaited()
        _,_,ns,gate,route,_=self.guard(['YES','DECLINED'],broken_observer=True)
        self.assertEqual(ns['reply'],'synthetic rerouted reply');self.assertEqual(gate.await_count,2);route.assert_awaited_once()


if __name__=='__main__':unittest.main()
