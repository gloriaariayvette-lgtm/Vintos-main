#!/usr/bin/env python3
"""Real scratch stores exercise stale passes and interrupted local projections."""
import copy
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
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'bin')]


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'HOME': self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.sender = lambda *a, **k: (_ for _ in ()).throw(AssertionError('provider call in fixture'))
        self.network = patch.dict(sys.modules, {'requests': types.SimpleNamespace(post=self.sender)})
        self.network.start()
        self.addCleanup(self.network.stop)
        for name in ('store_guard', 'belief_sediment', 'pearl_engine', 'causal_self_model', 'durable_projection'):
            sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location('fixture_causality', ROOT / 'scripts/causality-engine.py')
        self.c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.c)
        self.path = Path(self.c.HYPOTHESIS_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.assertTrue(self.path.is_relative_to(self.tmp.name))
        self.assertIs(sys.modules['requests'].post, self.sender)

    def event(self, db, kind='review_flag'):
        return self.c._queue_delivery(db, kind, {'hypothesis': 'fixture'}, 'event-1')

    def test_stale_save_refuses_before_projection(self):
        db = self.c.load_existing_hypotheses()
        self.event(db)
        self.path.write_text(json.dumps({'hypotheses': [{'id': 'concurrent'}]}))
        with self.assertRaisesRegex(RuntimeError, 'obsolete pass refused'):
            self.c.save_hypotheses(db)
        self.assertEqual(json.loads(self.path.read_text())['hypotheses'], [{'id': 'concurrent'}])
        self.assertFalse((self.path.parent / 'hallucination-flags.json').exists())

    def test_failed_source_write_never_falls_back(self):
        db = self.c.load_existing_hypotheses()
        with patch.object(self.c, 'write_json', side_effect=OSError('fixture disk failure')):
            with self.assertRaises(OSError):
                self.c.save_hypotheses(db)
        self.assertFalse(self.path.exists())

    def test_corrupt_source_is_not_empty(self):
        self.path.write_text('{broken')
        with self.assertRaises(ValueError):
            self.c.load_existing_hypotheses()
        self.assertEqual(self.path.read_text(), '{broken')

    def test_failed_delivery_survives_and_retries(self):
        db = self.c.load_existing_hypotheses()
        key = self.event(db)
        with patch.object(self.c, '_deliver', side_effect=OSError('fixture destination failure')):
            self.c.save_hypotheses(db)
        self.assertEqual(db['deliveries'][key]['state'], 'pending')
        self.c.recover_deliveries()
        self.assertEqual(self.c.load_existing_hypotheses()['deliveries'][key]['state'], 'delivered')

    def test_crash_after_destination_before_ack_does_not_duplicate(self):
        db = self.c.load_existing_hypotheses()
        key = self.event(db)
        original = self.c._deliver
        def interrupted(*args):
            original(*args)
            raise OSError('fixture acknowledgement gap')
        with patch.object(self.c, '_deliver', side_effect=interrupted):
            self.c.save_hypotheses(db)
        self.c.recover_deliveries()
        rows = json.loads((self.path.parent / 'hallucination-flags.json').read_text())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['transition_id'], key)

    def test_legacy_graduated_pending_is_queued_without_review(self):
        db = self.c.load_existing_hypotheses()
        db['hypotheses'] = [{'hypothesis': 'fixture', 'graduated': True,
                             'promotion_pending': {'error': 'old failure'}}]
        self.c.graduate_hypotheses(db)
        self.assertEqual([e['kind'] for e in db['deliveries'].values()], ['belief'])

    def test_belief_retry_after_forward_failure_and_culling(self):
        import belief_sediment as b
        import causal_self_model as model
        self.assertTrue(Path(b.SEDIMENT_FILE).is_relative_to(self.tmp.name))
        with patch.object(model, 'add_entry', side_effect=OSError('fixture forwarding failure')):
            with self.assertRaises(OSError):
                b.promote_hypothesis('fixture pattern', hypothesis_id='H-1')
        before = b.load_sediment()['beliefs'][0]['evidence_count']
        b.promote_hypothesis('fixture pattern', hypothesis_id='H-1')
        self.assertEqual(b.load_sediment()['beliefs'][0]['evidence_count'], before)
        data = b.load_sediment()
        data['beliefs'] = []
        b.save_sediment(data)
        b.promote_hypothesis('fixture pattern', hypothesis_id='H-1')
        self.assertEqual(b.load_sediment()['beliefs'], [])

    def test_causal_forward_occurrence_cannot_reinforce_twice(self):
        import causal_self_model as model
        self.assertTrue(Path(model.MODEL_FILE).is_relative_to(self.tmp.name))
        args = dict(trigger='fixture', tendency='fixture tendency', occurrence_id='event-1', entry_type='belief')
        model.add_entry(**args)
        before = copy.deepcopy(model.load_model())
        model.add_entry(**args)
        self.assertEqual(model.load_model(), before)

    def test_pearl_receipt_survives_candidate_removal(self):
        import pearl_engine as pearl
        self.assertTrue(Path(pearl.CANDIDATES_FILE).is_relative_to(self.tmp.name))
        args = dict(irritant='fixture friction', irritant_type='scar', source='causality',
                    insight='fixture', declaration='fixture', transition_id='event-1')
        ident = pearl.add_candidate(**args)
        data = pearl.load_candidates()
        data['candidates'] = []
        pearl.save_candidates(data)
        self.assertEqual(pearl.add_candidate(**args), ident)
        self.assertEqual(pearl.load_candidates()['candidates'], [])


if __name__ == '__main__':
    unittest.main()
