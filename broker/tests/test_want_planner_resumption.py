#!/usr/bin/env python3
"""A parked planner failure must reach the existing retry door, in scratch only."""
import ast
import datetime as dt
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
TEMP = tempfile.TemporaryDirectory(prefix='want-retry-')
SCRATCH = Path(TEMP.name)
os.environ['HOME'] = str(SCRATCH)
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'scripts'))
import want_board as B

SOURCE = ast.parse((REPO/'bin/wants-router.py').read_text())
FUNCTIONS = [n for n in SOURCE.body if isinstance(n, ast.FunctionDef)
             and n.name in ('_ensure_plan', '_persist_plan_fields', '_spend')]
SEND = Mock(side_effect=AssertionError('no external action'))


class PlannerResumption(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(B.CURRENT).is_relative_to(SCRATCH))
        Path(B.CURRENT).parent.mkdir(parents=True, exist_ok=True)
        self.now = dt.datetime.now()
        self.w = {'id':'w-retry', 'want':'Measure the fixture spectrum', 'timestamp':self.now.isoformat(),
            'board':'blocked', 'plan_state':'BLOCKED', 'parked_at':self.now.isoformat(),
            'plan_block':{'block_type':'PLANNER_NO_RESULT', 'at':(self.now-dt.timedelta(hours=3)).isoformat()},
            'manually_added_metadata':'preserve me'}
        self.planner = Mock(return_value=[{'capability':'be_silent','note':'Fixture','status':'pending'}])
        self.ns = {'os':os, 'json':json, 'datetime':dt.datetime, 'MEMORY':str(Path(B.CURRENT).parent), 'log':Mock()}
        exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), 'router-retry-functions', 'exec'), self.ns)
        self.net = patch.object(socket.socket, 'connect', SEND)
        self.net.start()

    def tearDown(self):
        self.net.stop()
        SEND.assert_not_called()

    def save(self):
        Path(B.CURRENT).write_text(json.dumps([self.w]))

    def read(self):
        return json.loads(Path(B.CURRENT).read_text())[0]

    def test_due_parked_failure_reaches_ordinary_planner_and_persists_its_plan(self):
        self.save()
        B.tend(now=self.now, discussions={}, age=SEND)
        want = self.read()
        # This is the ordinary router's selection gate; a parked row never
        # reaches _ensure_plan, even though that function permits retries.
        self.assertFalse(want.get('board'))
        self.assertNotIn('unparked_at', want)  # retry eligibility is not completed work
        with patch.dict(sys.modules, {'emoclaw_utils':types.SimpleNamespace(generate_steps=self.planner)}):
            self.assertTrue(self.ns['_ensure_plan'](want))
        stored = self.read()
        self.assertEqual(stored['plan_state'], 'READY')
        self.assertEqual(stored['steps'][0]['capability'], 'be_silent')
        self.assertNotIn('plan_block', stored)
        self.assertEqual(stored['manually_added_metadata'], 'preserve me')
        self.planner.assert_called_once()

    def test_recent_planning_failure_stays_parked(self):
        self.w['plan_block']['at'] = (self.now-dt.timedelta(minutes=30)).isoformat()
        self.save()
        B.tend(now=self.now, discussions={}, age=SEND)
        self.assertEqual(self.read()['board'], 'blocked')
        self.planner.assert_not_called()

    def test_capability_block_is_not_cleared_by_a_due_planning_retry(self):
        self.w['blocked'] = {'block_type':'CAPABILITY_ABSENT','blocked_step':'fixture'}
        self.save()
        B.tend(now=self.now, discussions={}, age=SEND)
        self.assertEqual(self.read()['board'], 'blocked')
        self.assertEqual(self.read()['blocked'], self.w['blocked'])

    def test_failed_retry_is_retained_and_parked_again(self):
        self.save()
        B.tend(now=self.now, discussions={}, age=SEND)
        want = self.read()
        self.assertFalse(want.get('board'))
        self.planner.return_value = []
        with patch.dict(sys.modules, {'emoclaw_utils':types.SimpleNamespace(generate_steps=self.planner)}):
            self.assertFalse(self.ns['_ensure_plan'](want))
        B.tend(now=self.now, discussions={}, age=SEND)
        stored = self.read()
        self.assertEqual(stored['board'], 'blocked')
        self.assertEqual(stored['plan_block']['block_type'], 'PLANNER_NO_RESULT')
        self.assertFalse(stored.get('fulfilled'))
        self.assertEqual(stored['budget_used']['plan_generations'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
