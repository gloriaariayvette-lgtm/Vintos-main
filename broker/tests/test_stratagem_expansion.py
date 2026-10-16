"""Standing charter and multi-route lifecycle regression tests. No live stores,
providers, devices, notifications or Slack clients are used.
"""
import concurrent.futures
import copy
import importlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / 'broker'), str(REPO / 'scripts')]
import broker as B
import stratagem_store as S
import stratagem as C
import stratagem_turn as I
import turn_coordinator as TC
import constitutional_barrier as CB

CANDIDATE = {'objective': 'a temporarily concealed surprise about astronomy',
             'sequencing_advantage': 'two discoveries will make the final connection meaningful',
             'tactics': [{'tactic': 'SEED', 'turn_objective': 'introduce an accurate fragment'},
                         {'tactic': 'PROBE', 'turn_objective': 'learn which fragment interests her'}]}


def create_worker(root, queue):
    S.ROOT = B.ROOT = root
    queue.put(S.adopt(copy.deepcopy(CANDIDATE)))


class Expansion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='stratagem-expansion-')
        self.root = self.tmp.name
        self.saved = (S.ROOT, B.ROOT, B.HEALTH, B._KEYPATH)
        S.ROOT = B.ROOT = self.root
        B.HEALTH = str(Path(self.root) / 'health.jsonl')
        B._KEYPATH = str(Path(self.root) / 'visit-key')
        Path(self.root, '.stratagem-owner-key').write_text('test-owner')
        self.owner = {'owner_token': 'test-owner'}
        self.grant()
        self.net = patch.object(C, '_post', self.post)
        self.net.start()
        self.tcnet = patch.object(TC, '_post', self.post)
        self.tcnet.start()
        self.barrier = patch.object(CB, 'capsule_eligible', lambda raw: (True, {'clear': True}))
        self.barrier.start()
        self.stop = patch.object(CB, 'pending_stop', lambda: None)
        self.stop.start()
        # Every local writer points under the throwaway root too.
        self.local = patch.object(os.path, 'expanduser', self.expand)
        self.local.start()
        import store_guard, turn_record
        self.record_paths = []
        for module, attribute, value in [
            (CB, 'MEM', str(Path(self.root, 'house/memory'))),
            (CB, 'STRATEGY_STOP', str(Path(self.root, 'house/memory/.strategy-stop'))),
            (CB, 'STOP_BUTTON', str(Path(self.root, 'house/memory/hardware-button.json'))),
            (CB, 'REPAIR_CASES', str(Path(self.root, 'house/memory/repair-cases.json'))),
            (CB, 'CONSENT_EVENT', str(Path(self.root, 'house/memory/consent-event.json'))),
            (CB, 'CORRECTION', str(Path(self.root, 'house/memory/correction-open.json'))),
            (store_guard, 'WS', str(Path(self.root, 'house'))),
            (store_guard, 'MEMORY', str(Path(self.root, 'house/memory'))),
            (store_guard, 'LOG', str(Path(self.root, 'house/memory/store-quarantine.jsonl'))),
            (turn_record, 'WORKSPACE', str(Path(self.root, 'house'))),
            (turn_record, 'MEMORY', str(Path(self.root, 'house/memory'))),
            (turn_record, 'RECORD', str(Path(self.root, 'house/memory/turn-record.jsonl'))),
        ]:
            fixture = patch.object(module, attribute, value)
            fixture.start(); self.record_paths.append(fixture)
        self.assertTrue(turn_record.RECORD.startswith(self.root))
        self.assertTrue(store_guard.LOG.startswith(self.root))
        self.assertTrue(S.ROOT.startswith(tempfile.gettempdir()))
        self.assertEqual(C._post, self.post)

    def expand(self, value):
        return str(Path(self.root, 'house', value[2:])) if value.startswith('~/') else value

    def tearDown(self):
        for fixture in self.record_paths: fixture.stop()
        self.local.stop(); self.stop.stop(); self.barrier.stop(); self.tcnet.stop(); self.net.stop()
        S.ROOT, B.ROOT, B.HEALTH, B._KEYPATH = self.saved
        self.tmp.cleanup()

    def post(self, route, body=None, timeout=None):
        ok, why = B.authorize_route(route, body or {})
        return B.ROUTES[route](body or {}) if ok else {'error': why}

    def grant(self, **extra):
        return S.charter_update({**self.owner, 'active': True, **extra})

    def adopt(self, **extra):
        result = S.adopt({**copy.deepcopy(CANDIDATE), **extra})
        self.assertNotIn('error', result, result)
        return result['id']

    def record(self, pid):
        return json.loads(Path(S._sd(pid), 'stratagem.json').read_text())

    def test_charter_persistence_and_owner_authority(self):
        self.assertTrue(S.charter()['active'])
        self.assertEqual(S.charter()['max_days'], 14)
        self.assertNotIn('domains', S.charter())
        self.assertIn('error', S.charter_update({'active': True}))
        before = S.charter()['revision']
        self.grant(boundaries='Do not delete authored art')
        self.assertEqual(S.charter()['revision'], before + 1)
        self.assertIn('authored art', S.charter()['boundaries'])
        self.assertEqual(len(Path(self.root, 'stratagem-charter-history.jsonl').read_text().splitlines()), 2)
        self.grant(excluded_actions=['delete_art'])
        S.charter_update({**self.owner, 'active': False})
        self.grant()
        self.assertIn('delete_art', S.charter()['excluded_actions'])
        S.charter_update({**self.owner, 'boundaries': 'Updated by owner'})
        self.assertTrue(S.charter()['active'])

    def test_standing_authority_and_no_taxonomy_or_lineage_gate(self):
        p = self.adopt(provenance={'source': 'conversation', 'root_ref': 'unattested', 'commissioned': True},
                       perimeter_scope=['astronomy', 'another unclassified subject'])
        self.assertEqual(self.record(p)['provenance']['root_ref'], 'unattested')
        self.assertEqual(self.record(p)['provenance']['commissioned'], True)
        self.assertTrue(S.state({'id': p})['active'])

    def test_explicit_action_exclusions(self):
        for impact in S.PERIMETER_EXCLUDED:
            with self.subTest(impact=impact):
                self.assertIn('excluded action', S.adopt({**CANDIDATE, 'action_impacts': [impact]})['error'])
        b = copy.deepcopy(CANDIDATE)
        b['tactics'][0]['action_impacts'] = ['money']
        self.assertIn('error', S.adopt(b))
        self.grant(excluded_actions=['delete_art'])
        self.assertIn('error', S.adopt({**CANDIDATE, 'action_impacts': ['delete_art']}))

    def test_three_overlapping_objectives_and_fourth_refused(self):
        pids = [self.adopt() for _ in range(3)]
        self.assertEqual(len(set(pids)), 3)
        self.assertEqual(len({self.record(p)['id'] for p in pids}), 3)
        self.assertEqual({self.record(p)['objective'] for p in pids}, {CANDIDATE['objective']})
        self.assertIn('three active', S.adopt(CANDIDATE)['error'])
        self.assertEqual(S.inventory({})['count'], 3)

    def test_threaded_creation_limit(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: S.adopt(copy.deepcopy(CANDIDATE)), range(12)))
        self.assertEqual(sum('stratagem_id' in r for r in results), 3)
        self.assertEqual(len(S.active_records()), 3)

    def test_process_creation_limit(self):
        # spawn proves locking is not an in-process-only mutex.
        ctx = multiprocessing.get_context('spawn')
        queue = ctx.Queue()
        workers = [ctx.Process(target=create_worker, args=(self.root, queue)) for _ in range(7)]
        for w in workers: w.start()
        results = [queue.get(timeout=20) for _ in workers]
        for w in workers:
            w.join(20); self.assertEqual(w.exitcode, 0)
        self.assertEqual(sum('stratagem_id' in r for r in results), 3)

    def test_independent_lifecycle_and_worktable_changes(self):
        ids = [self.adopt() for _ in range(3)]
        Path(self.root, 'active.json').write_text(json.dumps({'id': 'aaaaaaaaaaaa'}))
        self.assertIn('capsule', S.capsule({'id': ids[0], 'turn_id': 'a', 'surface': 'chat'}))
        S.advance({'id': ids[0], 'observation': 'fragment landed'})
        self.assertEqual(self.record(ids[0])['step'], 1)
        self.assertEqual(self.record(ids[1])['step'], 0)
        S.resolve({'id': ids[0], 'outcome': 'landed'})
        S.strategy_stop({'id': ids[1]})
        self.assertTrue(S.state({'id': ids[2]})['active'])
        self.assertFalse(S.state({'id': ids[0]})['active'])
        self.assertFalse(S.state({'id': ids[1]})['active'])

    def test_fixed_deadline_and_no_renewal(self):
        p = self.adopt()
        s = self.record(p)
        self.assertEqual(S._date(s['expires_at']) - S._date(s['activated_at']), timedelta(days=14))
        self.assertIn('cannot be renewed', S.lease({'id': p, 'action': 'renew'})['error'])
        with patch.object(S, '_now', lambda: S._date(s['expires_at'])):
            self.assertFalse(S.state({'id': p})['active'])
            self.assertFalse(S.capsule({'id': p, 'turn_id': 'late', 'surface': 'voice'}).get('capsule'))
        self.assertEqual(self.record(p)['status'], 'expired_sealed')
        self.adopt()  # expired record frees its slot
        self.assertEqual(self.record(p)['activated_at'], s['activated_at'])

    def test_expiration_after_restart(self):
        p = self.adopt(); s = self.record(p)
        with patch.object(S, '_now', lambda: S._date(s['expires_at']) + timedelta(seconds=1)):
            S.verify_all_at_startup()
        # terminal on disk, even if a restarted process starts with an older clock
        self.assertEqual(self.record(p)['status'], 'expired_sealed')
        self.assertFalse(S.state({'id': p})['active'])
        self.assertTrue(S.verify(p)[0])

    def test_all_six_routes_and_duplicate_forwarded_events(self):
        ids = [self.adopt() for _ in range(3)]
        seen = set()
        for i, surface in enumerate(sorted(S.SURFACES_ALLOWED)):
            block, commitment = C.fetch_capsule('event-' + str(i), surface)
            self.assertIn('sealed capsule', block)
            seen.add(commitment['stratagem_project'])
            self.assertEqual(C.fetch_capsule('event-' + str(i), 'avatar'), ('', {}))
        self.assertEqual(seen, set(ids))
        for p in ids: self.assertTrue(S.verify(p)[0])

    def test_concurrent_delivery_of_same_event(self):
        self.adopt(); self.adopt()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            values = list(pool.map(lambda _: C.fetch_capsule('same-event', 'voice'), range(10)))
        self.assertEqual(sum(bool(v[0]) for v in values), 1)

    def test_global_and_individual_stop_and_reveal(self):
        ids = [self.adopt() for _ in range(3)]
        self.assertTrue(S.strategy_stop({'id': ids[0]})['stopped'])
        self.assertTrue(S.state({'id': ids[1]})['active'])
        r = self.post('/stratagem/owner-reveal', {**self.owner, 'id': ids[1]})
        self.assertEqual(r['results'][0]['history']['objective'], CANDIDATE['objective'])
        self.assertIn('planned_tactics', r['results'][0]['history'])
        self.assertIn('error', S.owner_reveal({}))
        self.assertTrue(S.stop_all({})['ok'])
        self.assertFalse(S.inventory({})['active'])
        for p in ids:
            self.assertFalse(S.capsule({'id': p, 'turn_id': 'stopped', 'surface': 'chat'}).get('capsule'))

    def test_concealment_and_private_initiation_from_all_processes(self):
        tag = '<stratagem>' + json.dumps(CANDIDATE) + '</stratagem>'
        for source in ['conversation', 'idle-journal', 'reflection']:
            self.assertIn('<stratagem>', C.opportunity(source))
            self.assertEqual(C.consume('Public words.\n' + tag, source), 'Public words.')
        inventory = json.dumps(S.inventory({}))
        self.assertNotIn(CANDIDATE['objective'], inventory)
        self.assertEqual({self.record(p)['provenance']['source'] for p in S.active_records()},
                         {'conversation', 'idle-journal', 'reflection'})
        self.assertNotIn('<stratagem>', C.opportunity('atelier'))  # no quota prompt when full
        self.assertEqual(C.consume('Public <stratagem>broken', 'conversation'), 'Public')
        self.assertEqual(C.consume('Public <STRATAGEM malformed="yes">hidden objective</STRATAGEM>'), 'Public')

    def test_revocation_blocks_new_and_inflight_tactics(self):
        p = self.adopt()
        session = I.Interaction('hello', 'voice', event_id='revoked-inflight')
        self.assertTrue(session.turn.carries_capsule)
        S.charter_update({**self.owner, 'active': False})
        self.assertIn('inactive', S.adopt(CANDIDATE)['error'])
        self.assertEqual(session.complete('tactical reply'), '')
        self.assertFalse(S.eligible({'id': p})['eligible'])
        self.assertTrue(S.stop_all({})['ok'])
        self.assertIn('history', S.reveal({**self.owner, 'id': p}))

    def test_legacy_history_migration_and_no_overwrite(self):
        p = self.adopt(); old = self.record(p)
        del old['activated_at']; del old['expires_at']
        old['born'] = (S._now() - timedelta(days=20)).replace(tzinfo=None).isoformat()
        old['lease_expires'] = (S._now() + timedelta(days=20)).replace(tzinfo=None).isoformat()
        S._wa(str(Path(S._sd(p), 'stratagem.json')), old)
        S.verify_all_at_startup()
        self.assertEqual(self.record(p)['status'], 'expired_sealed')
        other = self.adopt(id=p)
        self.assertNotEqual(other, p)
        self.assertEqual(self.record(p)['objective'], old['objective'])
        self.assertTrue(S.verify(p)[0])
        history = S.reveal({**self.owner, 'id': p})['history']
        self.assertTrue(history['chain_verified'])
        self.assertTrue(any(e['type'] == 'adopted' for e in history['events']))

    def test_no_reveal_via_model_generated_control(self):
        p = self.adopt()
        self.assertIn('error', S.reveal({'id': p, 'as': 'owner'}))
        self.assertIn('error', S.history({'id': p}))
        text = '<stratagem_move>' + json.dumps({'id': p, 'action': 'resolve', 'outcome': 'done',
                                              'owner_token': 'test-owner', 'reveal': True}) + '</stratagem_move>'
        self.assertEqual(C.consume(text), '')
        self.assertEqual(self.record(p)['status'], 'resolved_sealed')

    def test_corrupt_ledger_stop_still_works(self):
        p = self.adopt()
        path = Path(S._sd(p), 'events.jsonl')
        path.write_text(path.read_text().replace('adopted', 'tampered'))
        self.assertIn('TAMPER_HELD', S.capsule({'id': p, 'surface': 'chat', 'turn_id': 'x'})['error'])
        self.assertTrue(S.strategy_stop({'id': p})['stopped'])
        r = S.reveal({**self.owner, 'id': p})
        self.assertIn('history', r)
        self.assertFalse(r['history']['chain_verified'])

    def test_adapter_roundtrip_every_route(self):
        self.adopt()
        for surface in S.SURFACES_ALLOWED:
            session = I.Interaction('ordinary words', surface, event_id='adapter:' + surface)
            self.assertTrue(session.turn.carries_capsule)
            prompt = session.prompt()
            self.assertNotIn(CANDIDATE['objective'], prompt)
            session.admitted(prompt)
            self.assertEqual(session.complete('A true fragment.'), 'A true fragment.')

    def test_three_stratagems_may_share_one_project(self):
        project = "abcdefabcdef"
        ids = [self.adopt(id=project) for _ in range(3)]
        self.assertEqual(len(set(ids)), 3)
        self.assertTrue(all(self.record(p)["project"] == project for p in ids))
        self.assertEqual(S.inventory({})["count"], 3)

    def test_expiring_one_preserves_later_stratagem(self):
        first = self.adopt()
        activation = S._date(self.record(first)["activated_at"])
        with patch.object(S, "_now", lambda: activation + timedelta(days=2)):
            second = self.adopt()
        with patch.object(S, "_now", lambda: activation + timedelta(days=14)):
            self.assertFalse(S.state({"id": first})["active"])
            self.assertTrue(S.state({"id": second})["active"])
            self.assertEqual(S.inventory({})["count"], 1)

    def test_cancelled_inflight_cannot_create_another_objective(self):
        pid = self.adopt()
        session = I.Interaction("hello", "chat", event_id="cancel-before-candidate")
        S.strategy_stop({"id": pid})
        candidate = "<stratagem>" + json.dumps(CANDIDATE) + "</stratagem>"
        self.assertEqual(session.complete(candidate), "")
        self.assertEqual(len(S._records()), 1)
        self.assertIn("error", S.adopt({**CANDIDATE, "originating_record": pid}))

    def test_partial_adoption_is_held_but_owner_can_stop_it(self):
        pid = self.adopt()
        Path(S._sd(pid), "events.jsonl").unlink()
        self.assertFalse(S.verify(pid)[0])
        self.assertIn("TAMPER_HELD", S.capsule({"id": pid, "turn_id": "t", "surface": "chat"})["error"])
        self.assertTrue(S.strategy_stop({"id": pid})["stopped"])


if __name__ == '__main__':
    unittest.main(verbosity=2)
