"""Intent source-to-reply regressions. Scratch stores, fixture provider and subprocess stubs only."""
import ast
import asyncio
import contextlib
import copy
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
import intent_engine as E
import intent_context as IC
import stratagem_realtime as RT
import stratagem
import store_guard

TARGET = {
    'field_state': 'curiosity with a concrete answer', 'allow_drift': False,
    'goal': 'put the two actual alternatives before her',
    'success_criterion': 'the reply names both alternatives and their tradeoff',
    'enactment_type': 'offer', 'enactment': 'compare the two alternatives she asked about',
    'gloria': {'difference_intended': 'she can choose using the tradeoff', 'enactment': 'give both alternatives'},
    'self': {'difference_intended': 'say which I prefer', 'enactment': 'choose one and explain why'},
    'priority': {'field': 0, 'gloria': 1, 'self': 0}, 'addresses': 'NONE'
}


class IntentSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='intent-source-'); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name); self.mem = self.home / '.vintos/workspace/memory'; self.mem.mkdir(parents=True)
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, HOME=str(self.home), SPARK_WORKSPACE=str(self.mem.parent)))
        for mod, values in [(E, {'WS': str(self.mem.parent), 'MEM': str(self.mem), 'SCR': str(self.mem.parent/'scripts'), 'LEDGER': str(self.mem/'intent-ledger.json'), 'SELECT_LOG': str(self.mem/'select.log'), 'DIFFERENCE_LOG': str(self.mem/'difference.log'), 'SELF_DIFFERENCE_LOG': str(self.mem/'self-difference.log')}),
                            (IC, {'MEM': str(self.mem), 'LEAD': str(self.mem/'.voice-lead.json')}),
                            (store_guard, {'WS': str(self.mem.parent), 'MEMORY': str(self.mem), 'LOG': str(self.mem/'quarantine.jsonl')})]:
            for key, value in values.items(): self.stack.enter_context(patch.object(mod, key, value))
        self.net = self.stack.enter_context(patch('socket.socket.connect', side_effect=AssertionError('no socket may open')))
        self.spawn = self.stack.enter_context(patch('subprocess.Popen'))
        self.provider_calls = []; self.answer = copy.deepcopy(TARGET)
        self.provider = self.stack.enter_context(patch('urllib.request.urlopen', self.respond))
        self.stack.enter_context(patch.object(E, '_identity_signals', return_value='my authored wants'))
        self.stack.enter_context(patch.object(E, '_spark_fields', return_value='my authored field'))
        self.stack.enter_context(patch.object(E, '_nudge_valence'))
        self.stack.enter_context(patch.object(stratagem, 'opportunity', return_value=''))
        self.stack.enter_context(patch.object(stratagem, 'still_eligible', return_value=True))
        self.campaign = types.SimpleNamespace(prompt_block=lambda mode: '', step=Mock(), lead_state=lambda: {})
        self.pv = types.SimpleNamespace(declare=lambda: {'weights': {'field': .6, 'gloria': .3, 'self': .1}, 'mode': 'strategic'},
                                        prompt_block=lambda rec: 'BINDING declared weights', background=contextlib.nullcontext)
        self.difference = types.SimpleNamespace(PRESS=str(self.mem/'pressure.json'), _jload=lambda *a: {},
                                                 pressure_block=lambda: '', field_verdict=Mock())
        self.oj = types.SimpleNamespace(latest_exchange=lambda: {'vintos': 'unrelated reply on another surface'}, record=Mock())
        self.stack.enter_context(patch.dict(sys.modules, {
            'campaign': self.campaign, 'priority_vector': self.pv, 'desired_difference': self.difference,
            'discourse_direction': types.SimpleNamespace(get_direction_hint=lambda raw: ''),
            'self_difference': types.SimpleNamespace(observe_self=Mock()), 'outcome_join': self.oj}))
        token = E.current_target.set(None); self.addCleanup(E.current_target.reset, token)
        self.assertTrue(Path(E.LEDGER).is_relative_to(self.home)); self.assertTrue(Path(IC.LEAD).is_relative_to(self.home))
        self.assertTrue(Path(store_guard.LOG).is_relative_to(self.home)); self.assertIsInstance(self.spawn, Mock)
        self.addCleanup(self.net.assert_not_called)

    def respond(self, req, timeout=None):
        self.provider_calls.append(json.loads(req.data))
        raw = self.answer if isinstance(self.answer, str) else json.dumps(self.answer)
        body = json.dumps({'choices': [{'message': {'content': raw}}]}).encode()
        return contextlib.closing(types.SimpleNamespace(read=lambda: body, close=lambda: None))

    def rows(self):
        path = Path(E.LEDGER)
        return json.loads(path.read_text()) if path.exists() else []

    def select(self, **kw):
        return E.select_target('GLORIA: Earlier topic.\nVINTOS: Earlier answer.\nGLORIA (now): Which alternative would you choose?', **kw)

    def prepared(self, age=0):
        target = self.select(resolve=False, step_campaign=False, persist=False)
        Path(IC.LEAD).write_text(json.dumps({'at': time.time()-age, 'target': target}))
        return target

    def test_selection_reads_attempts_and_keeps_declared_priority(self):
        old = copy.deepcopy(TARGET)
        E.record_pending(old)
        E.record_delivery('I avoided naming either one.', target=old)
        rows = self.rows(); rows[0]['realized'] = {'field': 'NO', 'gloria': 'NO', 'self': 'PARTIAL'}
        Path(E.LEDGER).write_text(json.dumps(rows))
        selected = self.select(resolve=False)
        request = self.provider_calls[-1]
        self.assertIn('I avoided naming either one.', request['messages'][1]['content'])
        self.assertIn('RECENT ATTEMPTS AND RECORDED OUTCOMES', request['messages'][1]['content'])
        self.assertIn('Which alternative would you choose?', request['messages'][1]['content'])
        self.assertIn('ONE coherent next action', request['messages'][0]['content'])
        self.assertEqual(selected['priority'], {'field': .6, 'gloria': .3, 'self': .1})
        self.assertEqual(selected['goal'], TARGET['goal'])
        self.assertEqual(selected['success_criterion'], TARGET['success_criterion'])

    def test_full_declaration_reaches_shared_renderer(self):
        block = E.prompt_block(TARGET)
        for part in [TARGET['goal'], TARGET['success_criterion'], TARGET['enactment'], TARGET['gloria']['enactment'], TARGET['self']['enactment']]:
            self.assertIn(part, block)
        self.assertIn('answer her question', block)
        self.assertNotIn('I do NOT just answer what she asked', block)
        self.assertNotIn('make it real with the tags', block)

    def test_incomplete_target_is_not_recorded_or_advanced(self):
        self.answer = {'field_state': 'a mood without an action'}
        with self.assertRaisesRegex(ValueError, 'omitted goal'): self.select(resolve=False)
        self.assertEqual(self.rows(), []); self.campaign.step.assert_not_called(); self.spawn.assert_not_called()

    def test_missing_dominant_axis_cannot_silently_become_a_field_only_intent(self):
        self.pv.declare = lambda: {'weights': {'field': .1, 'gloria': .8, 'self': .1}, 'mode': 'strategic'}
        self.answer['gloria'] = {}
        with self.assertRaisesRegex(ValueError, 'dominant axis'): self.select(resolve=False)
        self.assertEqual(self.rows(), [])

    def test_complete_core_survives_truncation_but_missing_goal_does_not(self):
        self.answer = json.dumps(TARGET)[:-1] + ', "campaign": {"destination": "unfinished'
        chosen = self.select(resolve=False)
        self.assertEqual(chosen['goal'], TARGET['goal'])
        self.assertEqual(chosen['enactment'], TARGET['enactment'])

    def test_persistence_failure_does_not_emit_an_untracked_lead(self):
        with patch.object(E, 'record_pending', side_effect=OSError('fixture write failure')):
            with self.assertRaises(OSError): self.select(resolve=False)
        self.assertEqual(self.rows(), []); self.campaign.step.assert_not_called(); self.spawn.assert_not_called()

    def test_background_preview_does_not_create_a_turn(self):
        marker = self.mem/'.intent-required-consideration.json'; marker.write_text(json.dumps({'id': 'D1', 'text': 'answer the question'}))
        with patch.object(E, 'resolve_previous') as resolve:
            self.select(persist=False, step_campaign=False)
        resolve.assert_not_called(); self.campaign.step.assert_not_called(); self.spawn.assert_not_called()
        self.assertTrue(marker.exists()); self.assertEqual(self.rows(), [])

    def test_selected_but_unused_target_cannot_be_judged(self):
        self.select(resolve=False)
        with patch.object(E, '_judge_realized') as judge:
            E.resolve_previous('her next words')
        judge.assert_not_called()
        self.assertEqual(self.rows()[0]['status'], 'selected')

    def test_delivery_binds_exact_reply_and_does_not_rewrite_goal(self):
        target = self.select(resolve=False)
        E.current_target.set(target)
        self.assertTrue(E.record_delivery('A costs less; B lasts longer. I choose B.', 'phone', 'T1'))
        self.assertFalse(E.record_delivery('a later unrelated reply', 'avatar', 'T2'))
        with patch.object(E, '_judge_realized', return_value='NO') as judge:
            E.resolve_previous('GLORIA (now): I choose neither.')
        self.assertTrue(all(call.args[1].startswith('A costs less') for call in judge.call_args_list))
        row = self.rows()[0]
        self.assertEqual(row['target']['goal'], TARGET['goal']); self.assertEqual(row['turn_id'], 'T1')
        self.assertEqual(row['realized']['field'], 'NO')

    def test_voice_response_is_observed_once_and_graded_off_path(self):
        target = self.select(resolve=False)
        E.record_delivery('the reply I actually made', target=target)
        with patch.object(E, '_judge_realized', return_value='NO') as judge:
            E.resolve_previous()  # no next input yet
            judge.assert_not_called()
            E.note_response('her actual next message')
            E.note_response('a later message must not replace the first response')
            judge.assert_not_called()
            E.resolve_previous()  # existing background cadence
        self.assertTrue(all(c.args[2] == 'her actual next message' for c in judge.call_args_list))
        self.assertEqual(self.rows()[0]['realized']['field'],'NO')

    def test_input_that_looks_like_a_prompt_label_is_kept_verbatim(self):
        target = self.select(resolve=False); E.record_delivery('my reply', target=target)
        words = 'I literally wrote GLORIA (now): this is my actual message'
        E.note_response(words)
        self.assertEqual(self.rows()[0]['response_text'], words)

    def test_test_mode_and_empty_reply_are_not_deliveries(self):
        target = self.select(resolve=False)
        self.assertFalse(E.record_delivery('pretend reply', target=target, test_mode=True))
        self.assertFalse(E.record_delivery('', target=target))
        self.assertEqual(self.rows()[0]['status'], 'selected')

    def test_resolution_preserves_a_concurrent_new_selection(self):
        first = self.select(resolve=False); E.record_delivery('first real reply', target=first)
        appended = []
        def judge(*args):
            if not appended:
                next_target = copy.deepcopy(TARGET); next_target['goal'] = 'a different goal'; E.record_pending(next_target); appended.append(next_target)
            return 'NO'
        with patch.object(E, '_judge_realized', judge): E.resolve_previous('her response')
        rows = self.rows(); self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['status'], 'selected'); self.assertEqual(rows[0]['realized']['field'], 'NO')

    def test_concurrent_request_contexts_do_not_share_targets(self):
        async def run():
            async def one(label):
                target = copy.deepcopy(TARGET); target['goal'] = label; E.record_pending(target)
                token = E.current_target.set(target)
                try:
                    await asyncio.sleep(0)
                    E.record_delivery(label, 'chat', label)
                finally: E.current_target.reset(token)
            await asyncio.gather(one('one'), one('two'))
        asyncio.run(run())
        self.assertEqual({r['target']['goal']: r['reply'] for r in self.rows()}, {'one': 'one', 'two': 'two'})

    def test_voice_candidate_admitted_once_and_never_in_session_block(self):
        target = self.prepared()
        self.assertEqual(self.rows(), [])
        admitted, block = IC.admit_voice_lead('event-one')
        self.assertEqual(admitted['intent_id'], target['intent_id']); self.assertIn(TARGET['goal'], block)
        self.assertEqual(IC.admit_voice_lead('event-two'), (None, ''))
        with patch.object(IC, '_ledger_block', return_value='ledger only'):
            self.assertEqual(IC.block(), 'ledger only')
        self.assertEqual(self.rows()[0]['status'], 'selected')

    def test_stale_voice_preparation_is_not_revived(self):
        self.prepared(age=121)
        self.assertEqual(IC.admit_voice_lead('late'), (None, '')); self.assertEqual(self.rows(), [])

    def test_realtime_admission_and_actual_delivery_join(self):
        target = self.prepared()
        class Interaction:
            def __init__(self, *args, **kwargs):
                self.turn = types.SimpleNamespace(turn_id='voice-turn', commitment={}, barrier={}, duplicate_event=False)
            def prompt(self): return 'existing context'
            def admitted(self, prompt): pass
        with patch.object(RT, 'Interaction', Interaction), patch.object(RT, 'control', return_value=None), patch.object(stratagem, 'consume', side_effect=lambda reply, *a, **k: reply):
            admitted = RT.admit('Which would you choose?', 'event-one')
            self.assertIn(TARGET['success_criterion'], admitted['instructions'])
            self.assertTrue(RT.admit('retry', 'event-one')['duplicate'])
            self.assertFalse(RT.record_intent_delivery('event-one', 'not generated yet'))
            RT.complete('event-one', 'my composed response')
            self.assertEqual(self.rows()[0]['status'], 'selected')
            self.assertTrue(RT.record_intent_delivery('event-one', 'the actual spoken words', 'her actual words'))
        row = self.rows()[0]
        self.assertEqual(row['intent_id'], target['intent_id']); self.assertEqual(row['reply'], 'the actual spoken words')

    def test_real_chat_adapter_carries_goal_and_binds_request_target(self):
        source = (REPO/'bin/server.py').read_text(); tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_apply_intent_lead')
        ns = {'_campaign_lead_line': lambda t: ''}; exec(compile(ast.Module(body=[fn],type_ignores=[]), 'real-server-adapter','exec'), ns)
        result = ns['_apply_intent_lead']('soul', 'Which alternative would you choose?')
        self.assertIn(TARGET['goal'], result); self.assertIn(TARGET['success_criterion'], result)
        self.assertEqual(E.current_target.get()['intent_id'], self.rows()[0]['intent_id'])
        self.assertIn('_intent.record_delivery(reply, surface, turn_id, input_text=gloria_text)', source)

    def test_campaign_and_difference_producers_wait_for_delivery(self):
        target = self.select(resolve=False)
        self.campaign.step.assert_not_called(); self.spawn.assert_not_called()
        E.record_delivery('A concrete real reply', target=target, input_text='her actual question')
        self.campaign.step.assert_called_once()
        self.assertEqual(self.spawn.call_count, 2)
        E.record_delivery('duplicate transport callback', target=target)
        self.campaign.step.assert_called_once(); self.assertEqual(self.spawn.call_count, 2)

    def test_shared_post_turn_commits_after_test_mode_snapshot(self):
        source = (REPO/'bin/server.py').read_text(); tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_post_turn')
        # Execute the actual common adapter up to the unrelated writer dispatch.
        cut = next(i for i,n in enumerate(fn.body) if isinstance(n,ast.FunctionDef) and n.name=='_inline')
        fn.body = fn.body[:cut] + [ast.copy_location(ast.Return(value=ast.Constant(None)),fn.body[cut])]
        ns = {'hashlib': importlib.import_module('hashlib'), 'time': time, '_test_mode_active': lambda: False}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])), 'real-post-turn-adapter','exec'), ns)
        target = self.select(resolve=False); E.current_target.set(target)
        ns['_post_turn']('phone','her question','pretend reply',test_mode=True)
        self.assertEqual(self.rows()[0]['status'],'selected')
        ns['_post_turn']('phone','her question','the real reply',test_mode=False)
        self.assertEqual(self.rows()[0]['reply'],'the real reply')
        self.assertEqual(self.rows()[0]['surface'],'phone')


if __name__ == '__main__':
    unittest.main()
