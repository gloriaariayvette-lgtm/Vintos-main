#!/usr/bin/env python3
"""Correlation and checkpoint acceptance use scratch data, never live requests."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import emotion_runtime
import request_trace
import compute_admission


class EvidenceTests(unittest.TestCase):
    def test_parallel_request_contexts_do_not_cross(self):
        async def run():
            async def task(ident):
                token = request_trace.current.set(ident)
                try:
                    await asyncio.sleep(0)
                    with patch.object(compute_admission, '_ledger', return_value=str(path)):
                        return compute_admission.record('fixture', extra={'provider_request_id': 'provider-'+ident})
                finally:
                    request_trace.current.reset(token)
            return await asyncio.gather(task('a'), task('b'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ledger.jsonl'
            self.assertTrue(path.is_relative_to(tmp))
            rows = asyncio.run(run())
            self.assertEqual([r['request_id'] for r in rows], ['a', 'b'])
            self.assertEqual([r['provider_request_id'] for r in rows], ['provider-a', 'provider-b'])
        self.assertIsNone(request_trace.current.get())

    def test_trace_contains_no_payload_or_credentials(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(request_trace, 'LOG', str(Path(tmp)/'trace.jsonl')):
            import time
            self.assertTrue(Path(request_trace.LOG).is_relative_to(tmp))
            token = request_trace.current.set('fixture')
            try:
                row = request_trace.record('/api/chat/full', 'POST', 200, time.monotonic())
            finally:
                request_trace.current.reset(token)
            self.assertEqual(set(row), {'at','request_id','route','method','status','latency_ms'})

    def test_checkpoint_match_requires_actual_parameters_and_stable_file(self):
        class Tensor:
            dtype = 'float32'
            shape = (1,)
            def __init__(self, value): self.value = value
            def detach(self): return self
            def cpu(self): return self
            def contiguous(self): return self
            def numpy(self): return self
            def tobytes(self): return self.value
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp)/'weights.pt'
            checkpoint.write_bytes(b'fixture')
            state = {'weight': Tensor(b'one')}
            engine = types.SimpleNamespace(model=types.SimpleNamespace(state_dict=lambda: state))
            loader = lambda *a, **k: {'state_dict': state}
            with patch.dict(sys.modules, {'torch': types.SimpleNamespace(load=loader)}):
                before = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
                self.assertTrue(emotion_runtime.attest(engine, checkpoint, before)['checkpoint_parameters_match'])
                checkpoint.write_bytes(b'changed')
                self.assertFalse(emotion_runtime.attest(engine, checkpoint, before)['checkpoint_parameters_match'])
            with patch.dict(sys.modules, {'torch': types.SimpleNamespace(load=lambda *a, **k: {'state_dict': {'weight': Tensor(b'two')}})}):
                before = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
                self.assertFalse(emotion_runtime.attest(engine, checkpoint, before)['checkpoint_parameters_match'])

    def test_loaded_modules_are_metadata_and_exclude_agent_room(self):
        with tempfile.TemporaryDirectory() as tmp:
            regular=Path(tmp)/'module.py'; regular.write_text('fixture')
            secret=Path(tmp)/'agent-room/private.py'; secret.parent.mkdir(); secret.write_text('private')
            modules={'fixture':types.SimpleNamespace(__file__=str(regular)), 'excluded':types.SimpleNamespace(__file__=str(secret))}
            rows=request_trace.runtime_inventory(modules)['modules']
            self.assertEqual([row['module'] for row in rows], ['fixture'])
            self.assertEqual(set(rows[0]), {'module','file','sha256'})

    def test_named_mobile_release_matches_client_source(self):
        app = ROOT.parent/'vintos-app/vintos-app/src'
        for name in ('index.html','client_lifecycle.js','avatar-bundle.js'):
            deployed=(ROOT/'clients/mobile'/name).read_bytes()
            manifest=json.loads((ROOT/'clients/mobile/source.json').read_text())
            self.assertEqual(hashlib.sha256(deployed).hexdigest(), manifest['sha256'][name])
            if app.exists():
                self.assertEqual((app/name).read_bytes(), deployed, name)


if __name__ == '__main__':
    unittest.main()
