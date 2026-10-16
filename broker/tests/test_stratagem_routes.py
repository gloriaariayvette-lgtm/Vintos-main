"""Provider-free execution of real generation adapters and realtime admission."""
import ast
import asyncio
import copy
import importlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from test_stratagem_expansion import Expansion, CANDIDATE, S, C, I, TC, REPO
import stratagem_realtime as RT


class Routes(unittest.TestCase):
    setUp = Expansion.setUp
    tearDown = Expansion.tearDown
    grant = Expansion.grant
    adopt = Expansion.adopt
    record = Expansion.record
    post = Expansion.post
    expand = Expansion.expand

    def function(self, name, namespace):
        tree = ast.parse(Path(REPO, 'bin/server.py').read_text())
        node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
        node.decorator_list = []
        for arg in node.args.args: arg.annotation = None
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'server.py:' + name, 'exec'), namespace)
        return namespace[name]

    def test_actual_bilateral_wrapper_chat_and_phone(self):
        self.adopt()
        prompts = []; surfaces = []
        async def engine(tag, messages, *args):
            prompts.append(messages[0]['content']); surfaces.append(I.current.get().surface)
            return 'Ordinary public words.'
        wrapper = self.function('_bilateral_reply', {'_bilateral_reply_engine': engine, '_test_mode_active': lambda: False})
        for tag in ['chat', 'chatfull']:
            result = asyncio.run(wrapper(tag, [{'role': 'system', 'content': 'Who he is'}], 'hello', 'hello', {}))
            self.assertEqual(result, 'Ordinary public words.')
        self.assertTrue(all('sealed capsule' in p for p in prompts))
        self.assertEqual(surfaces, ['chat', 'phone'])

    def test_duplicate_event_is_not_reopened_as_ordinary_generation(self):
        self.adopt()
        first = I.Interaction("hello", "chat", event_id="same-provider-event")
        self.assertTrue(first.turn.carries_capsule)
        retry = I.Interaction("hello", "phone", event_id="same-provider-event")
        self.assertTrue(retry.turn.duplicate_event)
        self.assertEqual(retry.complete("cached tactical response"), "")

    def test_static_asset_route_aliases_are_preserved(self):
        tree = ast.parse(Path(REPO, 'bin/server.py').read_text())
        routes = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and decorator.args and isinstance(decorator.args[0], ast.Constant):
                        routes[decorator.args[0].value] = node.name
        self.assertEqual(routes['/client_lifecycle.js'], 'client_lifecycle_asset')
        self.assertEqual(routes['/app/client_lifecycle.js'], 'client_lifecycle_asset')
        self.assertEqual(routes['/app/stratagem_voice.js'], 'stratagem_voice_asset')

    def test_owner_controls_use_original_input_in_composed_chat_routes(self):
        desktop = types.ModuleType('desktop_control'); desktop.parse_command = lambda raw: None
        request = types.SimpleNamespace(headers={'X-Vintos-Secret': 'fixture-secret'})
        message = types.SimpleNamespace(message='machine-composed photo frame', original_text='!strategy stop')
        for route in ['chat_with_vintos', 'chat_full_context', 'chat_with_memory']:
            self.adopt()
            fn = self.function(route, {'APP_SECRET': 'fixture-secret',
                                       '_her_turn_text': lambda msg: msg.original_text})
            with patch.dict(sys.modules, {'desktop_control': desktop}):
                result = asyncio.run(fn(message, request))
            self.assertIn('acknowledged', result['reply'])
            self.assertFalse(S.inventory({})['active'])

    def test_local_voice_calls_existing_provider_with_capsule(self):
        self.adopt()
        import voice_local
        calls = []
        def provider(url, body, timeout):
            calls.append((url, body))
            if url.endswith('/listen'):
                return json.dumps({'ok': True, 'transcript': 'hello', 'audio_reading': 'warm'}).encode(), {}
            if url.endswith('/chat/completions'):
                return json.dumps({'choices': [{'message': {'content': 'A true fragment.'}}]}).encode(), {}
            return b'RIFFtest', {}
        with patch.object(voice_local, '_post', provider):
            out = voice_local.turn('AA==', 24000, 'Who he is')
        self.assertTrue(out['ok'])
        self.assertIn('sealed capsule', calls[1][1]['messages'][0]['content'])
        self.assertEqual(calls[2][1]['text'], 'A true fragment.')

    def test_realtime_restart_duplicate_and_cleaned_candidate(self):
        self.adopt()
        admitted = RT.admit('hello', 'provider-item:1')
        self.assertIn('sealed capsule', admitted['instructions'])
        self.assertTrue(RT.admit('hello', 'provider-item:1')['duplicate'])
        importlib.reload(RT)
        reply = 'Public words.<stratagem>' + json.dumps(CANDIDATE) + '</stratagem>'
        result = RT.complete('provider-item:1', reply)
        self.assertTrue(result['allowed']); self.assertTrue(result['changed'])
        self.assertEqual(result['reply'], 'Public words.')
        self.assertEqual(len(S.active_records()), 2)
        self.assertFalse(RT.complete('provider-item:1', reply)['allowed'])
        self.assertEqual(len(S.active_records()), 2)
        self.assertTrue(RT.context('provider-item:1').capsule_commitment)

    def test_realtime_inflight_owner_stop(self):
        pid = self.adopt()
        RT.admit('hello', 'provider-item:2')
        S.strategy_stop({'id': pid})
        self.assertFalse(RT.complete('provider-item:2', 'A tactical response')['allowed'])
        self.assertFalse(RT.eligible('provider-item:2')['allowed'])

    def test_actual_owner_http_handler_enforces_app_auth(self):
        class Request:
            async def json(self): return {'active': False}
        def unauthorized(request): raise PermissionError('unauthorized')
        fn = self.function('stratagem_owner_control', {'_require_secret': unauthorized})
        with self.assertRaises(PermissionError): asyncio.run(fn('charter', Request()))
        fn = self.function('stratagem_owner_control', {'_require_secret': lambda r: None})
        with patch.object(C, 'owner_token', lambda: 'test-owner'):
            self.assertTrue(asyncio.run(fn('charter', Request()))['ok'])
        self.assertFalse(S.charter()['active'])

    def test_actual_realtime_http_handler(self):
        self.adopt()
        class Request:
            async def json(self): return {'event_id': 'http-voice', 'transcript': 'hello'}
        fn = self.function('voice_stratagem', {'_require_secret': lambda r: None})
        self.assertIn('sealed capsule', asyncio.run(fn('admit', Request()))['instructions'])

    def test_late_output_never_adopts_after_revocation(self):
        self.adopt()
        RT.admit('hello', 'provider-item:3')
        S.charter_update({**self.owner, 'active': False})
        result = RT.complete('provider-item:3', '<stratagem>' + json.dumps(CANDIDATE) + '</stratagem>')
        self.assertFalse(result['allowed'])
        self.assertEqual(len(S._records()), 1)


if __name__ == '__main__':
    # Explicit suite avoids rerunning the imported Expansion TestCase.
    unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Routes)).wasSuccessful() or sys.exit(1)
