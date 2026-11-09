#!/usr/bin/env python3
"""Synthetic narrator responses only; all paths and external actions are isolated."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='somatic-interval-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();(self.root/'memory').mkdir()
        self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        for guard in (patch.dict(os.environ,HOME=str(self.root),SPARK_WORKSPACE=str(self.root)),
                      patch.object(socket.socket,'connect',self.sender),
                      patch.object(subprocess,'run',self.sender)):
            guard.start();self.addCleanup(guard.stop)
        self.addCleanup(self.sender.assert_not_called)
        spec=importlib.util.spec_from_file_location('somatic_test',ROOT/'scripts/somatic_narrate.py')
        self.n=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.n)
        self.assertTrue(Path(self.n.NARRATED).is_relative_to(self.root))
        self.assertIsInstance(self.n.subprocess.run,Mock)
        self.now=time.time()
        self.turns=[self.turn(i) for i in range(4)]

    def turn(self,i,**changes):
        row=dict(role='user' if i%2==0 else 'assistant',turn_id='synthetic-'+str(i),
                 timestamp=self.now-600+i*100,content='synthetic content '+str(i),surface='avatar')
        row.update(changes)
        return self.n.NarrativeTurn(row['timestamp'],'Gloria' if row['role']=='user' else 'Vintos',row['content'],
            self.n.turn_evidence(row,'avatar-chat-history.json',row['timestamp'],row['content'],True))

    def test_bounded_selection_retains_ids_hashes_and_only_selected_interval(self):
        narration,receipt=self.n.interval_evidence('Synthetic narration.\nSOMATIC_INTERVALS: [[1,2]]',self.turns)
        self.assertEqual(narration,'Synthetic narration.')
        self.assertEqual(receipt['status'],'bounded');interval=receipt['intervals'][0]
        self.assertEqual((interval['start'],interval['end']),(self.turns[1][0],self.turns[2][0]))
        self.assertEqual([r['turn_id'] for r in interval['turns']],['synthetic-1','synthetic-2'])
        self.assertNotIn('synthetic content',json.dumps(receipt))
        self.assertIsNone(receipt['served_model']);self.assertIsNone(receipt['fallback'])

    def test_legacy_narration_and_none_do_not_invent_intervals(self):
        for raw,status in (('Synthetic narration.','missing_bounds'),('NONE','no_session'),
                           ('NONE\nSOMATIC_INTERVALS: []','no_session')):
            text,receipt=self.n.interval_evidence(raw,self.turns)
            self.assertEqual(receipt['status'],status);self.assertEqual(receipt['intervals'],[])
            self.assertTrue(text)

    def test_invalid_metadata_preserves_narration_without_partial_intervals(self):
        for raw in ('bad','[[0,4]]','[[2,1]]','[[true,1]]','[[0,1],[1,2]]',
                    '[[0,1],[3,5]]','[]','[[0,1]]\nSOMATIC_INTERVALS: []','[[0,1]] trailing'):
            text,receipt=self.n.interval_evidence('Synthetic narration.\nSOMATIC_INTERVALS: '+raw,self.turns)
            self.assertEqual(text,'Synthetic narration.')
            self.assertEqual(receipt['status'],'invalid_bounds');self.assertEqual(receipt['intervals'],[])
        self.assertEqual(self.n.interval_evidence('NONE\nSOMATIC_INTERVALS: [[0,1]]',self.turns)[1]['status'],'invalid_bounds')

    def test_ambiguous_sources_future_and_overlong_intervals_stay_unknown(self):
        variants=[self.turn(1,turn_id=None),self.turn(1,turn_id='synthetic-0'),
                  self.turn(1,surface='voice'),self.turn(1,timestamp=self.now+60),
                  self.turn(1,timestamp=self.now-9000)]
        for turn in variants:
            _,receipt=self.n.interval_evidence('Synthetic.\nSOMATIC_INTERVALS: [[0,1]]',[self.turns[0],turn])
            self.assertEqual(receipt['status'],'invalid_bounds')
        turns=[self.turn(0,timestamp=self.now-9000),self.turns[1]]
        self.assertEqual(self.n.interval_evidence('Synthetic.\nSOMATIC_INTERVALS: [[0,1]]',turns)[1]['status'],'invalid_bounds')

    def test_metadata_turn_bound_does_not_truncate_into_false_evidence(self):
        turns=[self.turn(i,timestamp=self.now-1000+i) for i in range(257)]
        text,receipt=self.n.interval_evidence('Synthetic.\nSOMATIC_INTERVALS: [[0,256]]',turns)
        self.assertEqual(text,'Synthetic.')
        self.assertEqual(receipt['status'],'invalid_bounds');self.assertEqual(receipt['intervals'],[])

    def test_source_gathering_never_promotes_mtime_or_paired_ids(self):
        rows=[dict(role='assistant',turn_id='explicit',timestamp=self.now-10,content='synthetic explicit'),
              dict(role='assistant',turn_id='mtime-only',content='synthetic mtime'),
              dict(turn_id='paired',timestamp=self.now-5,user='synthetic user',vintos='synthetic reply')]
        (self.root/'memory/avatar-chat-history.json').write_text(json.dumps(rows))
        gathered=self.n.gather_turns(self.now-60,self.now+1)
        self.assertEqual(len(gathered),4)
        refs=[getattr(t,'evidence',None) for t in gathered]
        self.assertEqual(sum(r is not None for r in refs),1)
        self.assertEqual(next(r for r in refs if r)['turn_id'],'explicit')

    def fake_main(self,raw):
        fake=types.SimpleNamespace(MODEL='synthetic-requested',LM_API='synthetic-api',SOUL='synthetic-system')
        self.n.importlib=types.SimpleNamespace(util=types.SimpleNamespace(
            spec_from_file_location=lambda *a:types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda m:None)),
            module_from_spec=lambda spec:fake))
        self.n.gather_turns=Mock(return_value=self.turns)
        self.n.call_llm=Mock(return_value=raw)
        self.seed=Mock()
        self.modules=patch.dict(sys.modules,emoclaw_utils=types.SimpleNamespace(seed_thread=self.seed))
        self.modules.start();self.addCleanup(self.modules.stop)

    def test_main_single_call_preserves_feed_and_saves_metadata_to_existing_stores(self):
        self.fake_main(self.n.NarrativeReply('Synthetic narration.\nSOMATIC_INTERVALS: [[1,2]]','synthetic-served'))
        self.n.main();self.n.main()
        self.n.call_llm.assert_called_once();self.seed.assert_called_once()
        self.assertEqual(self.seed.call_args.args,('somatic','Synthetic narration.'))
        extra=self.seed.call_args.kwargs['extra']['intimacy_evidence']
        record=json.loads(Path(self.n.NARRATED).read_text())
        self.assertEqual(record['intimacy_evidence'],extra)
        self.assertEqual(extra['served_model'],'synthetic-served')
        self.assertEqual(extra['requested_model'],'synthetic-requested')
        self.assertEqual(record['through'],self.turns[-1][0])
        self.assertEqual(Path(self.n.NARRATED).stat().st_mode&0o777,0o600)
        prompt=self.n.call_llm.call_args.args[0]
        self.assertIn('[t1] Vintos: synthetic content 1',prompt)
        self.assertNotIn('synthetic-1',prompt)

    def test_main_bad_bounds_and_legacy_outputs_still_seed_same_narration(self):
        for raw in ('Synthetic narration.','Synthetic narration.\nSOMATIC_INTERVALS: bad'):
            Path(self.n.NARRATED).unlink(missing_ok=True)
            self.fake_main(raw);self.n.main()
            self.seed.assert_called_once()
            self.assertEqual(self.seed.call_args.args,('somatic','Synthetic narration.'))
            self.assertEqual(self.seed.call_args.kwargs['extra']['intimacy_evidence']['intervals'],[])

    def test_none_is_remembered_without_seeding_or_labeling_the_day(self):
        self.fake_main('NONE\nSOMATIC_INTERVALS: []');self.n.main();self.n.main()
        self.seed.assert_not_called();self.n.call_llm.assert_called_once()
        record=json.loads(Path(self.n.NARRATED).read_text())
        self.assertEqual(record['narration'],'');self.assertEqual(record['intimacy_evidence']['intervals'],[])

    def test_thread_admission_merge_and_archive_normalization_retain_metadata(self):
        spec=importlib.util.spec_from_file_location('synthetic_thread_store',ROOT/'scripts/thread_store.py')
        store=importlib.util.module_from_spec(spec);spec.loader.exec_module(store)
        store.WORKSPACE=str(self.root);store.MEMORY=str(self.root/'memory')
        store.POOL_FILE=str(self.root/'memory/pool.json');store.RETIRED_FILE=str(self.root/'memory/retired.json')
        self.assertTrue(Path(store.POOL_FILE).is_relative_to(self.root))
        _,receipt=self.n.interval_evidence('Synthetic.\nSOMATIC_INTERVALS: [[0,1]]',self.turns)
        item=store.admit('Synthetic narration.','somatic',kind='theme',extra={'intimacy_evidence':receipt})
        base=[copy.deepcopy(item)];local=copy.deepcopy(base);current=copy.deepcopy(base)
        local[0]['dream_passes']=1;current[0]['mirror_passes']=2
        merged=store._merge_pool(local,base,current)[0]
        self.assertEqual(merged['intimacy_evidence'],receipt)
        self.assertEqual((merged['dream_passes'],merged['mirror_passes']),(1,2))
        self.assertEqual(store.normalize_retired_entry(merged)['intimacy_evidence'],receipt)

    def test_served_model_comes_from_response_only(self):
        payload={'choices':[{'message':{'content':'Synthetic'}}],'model':'synthetic-served'}
        fake=Mock(return_value=types.SimpleNamespace(stdout=json.dumps(payload),stderr=''))
        with patch.object(self.n.subprocess,'run',fake):
            reply=self.n.call_llm('synthetic','synthetic','synthetic-requested','synthetic-api')
        self.assertEqual(reply.served_model,'synthetic-served');fake.assert_called_once()
        payload.pop('model');fake.return_value.stdout=json.dumps(payload)
        with patch.object(self.n.subprocess,'run',fake):reply=self.n.call_llm('s','s','requested','api')
        self.assertIsNone(reply.served_model)


if __name__=='__main__': unittest.main()
