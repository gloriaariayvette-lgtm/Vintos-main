#!/usr/bin/env python3
"""Exact agent-result completion through the real ending door; synthetic stores only."""
import copy
import builtins
import threading
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import want_agent as A
import want_completion as C
import want_artifact_guard as G
import emoclaw_utils as E
from journal_wants import source_receipt


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='want-ending-test-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.ws = self.home/'.vintos/workspace'; self.mem = self.ws/'memory'; self.mem.mkdir(parents=True)
        self.assertTrue(self.ws.is_relative_to(self.home))
        self.assertNotEqual(self.home, Path.home().resolve())
        self.nudges = []; self.children = []; self.plans = []
        def nudge(*args, **kwargs): self.nudges.append((args, kwargs))
        def child(*args, **kwargs):
            self.children.append((args, kwargs))
            for key in ('stdout','stderr'):
                if hasattr(kwargs.get(key), 'close'): kwargs[key].close()
            return None
        original_open = builtins.open
        def scratch_open(path, *args, **kwargs):
            if path == '/tmp/wants-ambitions-log.log': path = self.home/'worker.log'
            return original_open(path, *args, **kwargs)
        patches = [patch.object(builtins, 'open', scratch_open),
                   patch.dict(os.environ, HOME=str(self.home), SPARK_WORKSPACE=str(self.ws)),
                   patch.object(E, 'nudge_emotions', nudge), patch.object(subprocess, 'Popen', child),
                   patch.dict(sys.modules, plan=types.SimpleNamespace(reopen_on_evidence=lambda *a, **k:self.plans.append(1) or []))]
        for obj, name, value in ((C,'WS',str(self.ws)),(C,'MEMORY',str(self.mem)),
                (C,'WANTS',str(self.mem/'current-wants.json')),(C,'COMPLETIONS',str(self.mem/'want-completions.jsonl')),
                (C,'DISMISSED',str(self.mem/'dismissed-wants.json')),(G,'WS',str(self.ws)),(G,'MEMORY',str(self.mem)),
                (E,'TXT_FILE',str(self.mem/'emotional-state.txt')),(E,'SOCK_PATH',str(self.home/'no-emotion.sock')),
                (E,'PID_FILE',str(self.home/'no-emotion.pid'))):
            patches.append(patch.object(obj,name,value))
        for p in patches: p.start(); self.addCleanup(p.stop)
        self.assertIs(E.nudge_emotions, nudge); self.assertIs(subprocess.Popen, child)
        self.assertEqual(Path(C.WANTS).parent, self.mem)
        w = dict(id='fixture-want', want='I want to export a checked synthetic score.', source='idle-journal')
        w.update(source_receipt('journal','fixture-source',w['want']))
        self.write([w]); A.request(w, ws=self.ws)
        self.version('first')
        self.snapshot = copy.deepcopy(self.current()[0])

    def write(self, rows): (self.mem/'current-wants.json').write_text(json.dumps(rows))
    def current(self): return json.loads((self.mem/'current-wants.json').read_text())
    def version(self, name):
        rows = self.current(); w = rows[0]; a = w['agent_work']
        root = A.directory(a['request_id'], self.ws); root.mkdir(parents=True,exist_ok=True)
        artifact = root/(name+'.txt'); artifact.write_text('Synthetic checked output '+name)
        result = dict(schema=A.SCHEMA,request_id=a['request_id'],goal_sha256=a['goal_sha256'],status='completed',
                      summary='Synthetic '+name,acceptance='Fixture check passed.',artifacts=[dict(
                          path=str(artifact.relative_to(self.ws)),sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())])
        (root/'result.json').write_text(json.dumps(result))
        digest = A.result_digest(result)
        a.update(result=result,result_sha256=digest,stage_result_sha256=digest,status='result_ready',
                 publication={'url':'https://example.invalid/'+name}, delivery={'state':'sent','artifact_id':'fixture-'+name})
        self.write(rows)

    def complete(self, want=None):
        return C.complete(want or self.snapshot,'fulfilled','agent-work',note='Synthetic completion.')

    def assert_held(self, result):
        self.assertNotEqual(result['result'], 'fulfilled')
        self.assertEqual(len(self.current()),1)
        self.assertFalse((self.mem/'fulfilled-wants.json').exists())
        self.assertEqual(self.nudges,[]); self.assertEqual(self.children,[]); self.assertEqual(self.plans,[])

    def test_exact_version_archives_through_actual_fulfillment(self):
        result = self.complete()
        self.assertEqual(result['result'],'fulfilled'); self.assertEqual(self.current(),[])
        archive = json.loads((self.mem/'fulfilled-wants.json').read_text())
        self.assertEqual(archive[0]['agent_work']['result_sha256'],self.snapshot['agent_work']['result_sha256'])
        self.assertEqual(len(self.nudges),1); self.assertEqual(len(self.children),1)

    def test_late_revision_cannot_be_completed_by_earlier_snapshot(self):
        self.version('second')
        self.assert_held(self.complete())
        self.assertEqual(self.current()[0]['agent_work']['result']['summary'],'Synthetic second')

    def test_missing_exact_id_never_falls_back_to_same_text(self):
        rows=self.current(); rows[0]['id']='different-fixture-want'; self.write(rows)
        self.assert_held(self.complete())

    def test_unknown_result_version_is_not_completion_evidence(self):
        snapshot=copy.deepcopy(self.snapshot); snapshot['agent_work'].pop('result_sha256')
        self.assert_held(self.complete(snapshot))

    def test_current_delivery_must_belong_to_the_same_version(self):
        rows=self.current(); rows[0]['agent_work']['stage_result_sha256']='0'*64; self.write(rows)
        self.assert_held(self.complete())

    def test_result_hash_does_not_override_changed_manifest(self):
        rows=self.current(); rows[0]['agent_work']['result']['summary']='Changed synthetic manifest'; self.write(rows)
        self.assert_held(self.complete())

    def test_missing_current_want_does_not_claim_completion(self):
        self.write([])
        self.assertNotEqual(self.complete()['result'],'fulfilled')
        self.assertEqual(self.nudges,[]); self.assertEqual(self.children,[]); self.assertEqual(self.plans,[])


    def test_ambiguous_id_is_not_completed(self):
        rows=self.current(); rows.append(copy.deepcopy(rows[0])); self.write(rows)
        result=self.complete()
        self.assertNotEqual(result['result'],'fulfilled')
        self.assertEqual(len(self.current()),2); self.assertEqual(self.nudges,[])
        self.assertFalse((self.mem/'fulfilled-wants.json').exists())

    def test_missing_delivery_or_source_is_not_completion(self):
        for field in ('delivery', 'source_refs'):
            with self.subTest(field=field):
                row=copy.deepcopy(self.snapshot)
                (row['agent_work'] if field=='delivery' else row).pop(field)
                self.write([row]); self.assert_held(self.complete())

    def test_revision_writer_cannot_enter_between_comparison_and_archive(self):
        import store_guard as S
        attempted=threading.Event(); entered=threading.Event(); errors=[]
        def writer():
            try:
                attempted.set()
                def update(rows):
                    entered.set()
                    return rows+[{'id':'unrelated-fixture','want':'Unrelated retained fixture.'}]
                S.locked_update(C.WANTS, update, default=[])
            except Exception as exc: errors.append(exc)
        thread=threading.Thread(target=writer)
        match=C._agent_result_matches
        def observe(*args):
            self.assertIn(os.path.abspath(C.WANTS), S._state.held)
            thread.start(); self.assertTrue(attempted.wait(1))
            self.assertFalse(entered.wait(.05))
            return match(*args)
        try:
            with patch.object(C,'_agent_result_matches',observe): result=self.complete()
        finally:
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive()); self.assertEqual(errors,[])
        self.assertEqual(result['result'],'fulfilled'); self.assertTrue(entered.is_set())
        self.assertEqual([w['id'] for w in self.current()],['unrelated-fixture'])


if __name__ == '__main__': unittest.main()
