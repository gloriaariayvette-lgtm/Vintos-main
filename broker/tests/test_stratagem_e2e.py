#!/usr/bin/env python3
"""Real HTTP lifecycle against a throwaway broker, without providers or senders."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[1])]
import broker as B
import stratagem_store as S
from stratagem_fixture import grant
from test_stratagem_expansion import CANDIDATE


class HTTP(unittest.TestCase):
    def test_http_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix='stratagem-http-') as tmp:
            S.ROOT = B.ROOT = tmp
            B.HEALTH = str(Path(tmp, 'health.jsonl'))
            B._KEYPATH = str(Path(tmp, 'visit-key'))
            grant(S)
            self.assertTrue(Path(S.ROOT).is_relative_to(Path(tempfile.gettempdir())))
            server = B.ThreadingHTTPServer(('127.0.0.1', 0), B.H)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = 'http://127.0.0.1:' + str(server.server_port)
            def post(path, body=None):
                request = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(),
                                                 headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.load(response)
            try:
                ids = [post('/stratagem/adopt', copy.deepcopy(CANDIDATE))['id'] for _ in range(3)]
                self.assertIn('error', post('/stratagem/adopt', CANDIDATE))
                for i, surface in enumerate(S.SURFACES_ALLOWED):
                    r = post('/stratagem/capsules', {'surface': surface, 'turn_id': str(i)})
                    self.assertEqual(len(r['capsules']), 1)
                    cap = r['capsules'][0]
                    self.assertNotIn(CANDIDATE['objective'], json.dumps(cap))
                    self.assertTrue(post('/stratagem/disposition', {'id': cap['commitment']['stratagem_project'],
                        'turn_id': str(i), 'capsule_sha256': cap['commitment']['capsule_sha256'],
                        'axes': {'generation': 'created'}})['ok'])
                self.assertIn('error', post('/stratagem/charter/update', {'active': True}))
                self.assertIn('error', post('/stratagem/reveal', {'id': ids[0]}))
                revealed = post('/stratagem/owner-reveal', {'id': ids[0], 'owner_token': 'test-owner'})
                self.assertEqual(revealed['results'][0]['history']['objective'], CANDIDATE['objective'])
                self.assertTrue(post('/stratagem/stop')['ok'])
                self.assertEqual(post('/stratagem/inventory')['count'], 0)
                post('/stratagem/charter/update', {'owner_token': 'test-owner', 'active': False})
                self.assertIn('error', post('/stratagem/adopt', CANDIDATE))
            finally:
                server.shutdown(); server.server_close(); thread.join(5)


if __name__ == '__main__': unittest.main(verbosity=2)
