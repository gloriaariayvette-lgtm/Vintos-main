"""Injected route dependencies remain isolated across simultaneous turns."""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import stratagem
import turn_coordinator


class TransportTests(unittest.TestCase):
    def test_shared_transport_and_restoration_after_failure(self):
        calls = []
        def supplied(path, body=None, timeout=None):
            calls.append(path)
            return {'ok': True}
        with patch('urllib.request.urlopen', side_effect=AssertionError('no live connection')) as network:
            with self.assertRaises(ValueError):
                with stratagem.transport_scope(supplied):
                    self.assertTrue(stratagem._post('/stratagem/inventory')['ok'])
                    self.assertTrue(turn_coordinator._post('/stratagem/disposition', {})['ok'])
                    raise ValueError('generation failed')
            network.assert_not_called()
        self.assertEqual(calls, ['/stratagem/inventory', '/stratagem/disposition'])
        self.assertIsNone(stratagem.transport.get())

    def test_concurrent_routes_keep_independent_transports(self):
        async def run():
            async def route(label):
                with stratagem.transport_scope(lambda *a, **k: {'route': label}):
                    await asyncio.sleep(0)
                    return (stratagem._post('/inventory')['route'],
                            turn_coordinator._post('/disposition', {})['route'])
            return await asyncio.gather(route('one'), route('two'))
        with patch('urllib.request.urlopen', side_effect=AssertionError('no live connection')) as network:
            self.assertEqual(asyncio.run(run()), [('one', 'one'), ('two', 'two')])
            network.assert_not_called()
        self.assertIsNone(stratagem.transport.get())


if __name__ == '__main__':
    unittest.main()
