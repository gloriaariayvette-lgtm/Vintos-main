#!/usr/bin/env python3
"""Scratch-only export/causality/feed tests. Every sender is stubbed; no live stores."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import time
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[2]
ROOT=Path(tempfile.mkdtemp(prefix='latent-feed-test-'))
os.environ['HOME']=str(ROOT)
os.environ['SPARK_WORKSPACE']=str(ROOT/'.vintos/workspace')
os.environ['TZ']='America/Chicago';time.tzset()
MEM=ROOT/'.vintos/workspace/memory';MEM.mkdir(parents=True)
sys.path.insert(0,str(REPO/'scripts'))
NET=[]
def no_network(*a,**k):
    NET.append(True);raise AssertionError('tests cannot send')
socket.socket.connect=no_network
import types
requests=types.SimpleNamespace(get=no_network,post=no_network)
sys.modules["requests"]=requests
import numpy as np
import latent_stream_export as E
import latent_stream_model as M
import latent_feed as F
import jepa_predictor as JP

class Encoder:
    def encode(self,texts,**kwargs):
        out=[]
        for text in texts:
            seed=int(hashlib.sha256(str(text).encode()).hexdigest()[:8],16)
            v=np.random.default_rng(seed).normal(size=24);out.append(v/np.linalg.norm(v))
        return np.asarray(out,np.float32)

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.enc=Encoder();cls.events=[]
        rng=np.random.default_rng(14)
        for day in range(30):
            for k in range(3):
                t=datetime(2026,9,24,tzinfo=timezone.utc)+timedelta(days=day,hours=k*4)
                v=cls.enc.encode(['topic-%d-%d'%(day,k)])[0]
                cls.events.append({'t':t,'source':'inner','vec':v.tolist()})
                cls.events.append({'t':t+timedelta(minutes=10),'source':'emotion','emo':rng.uniform(.2,.8,11).tolist()})
        cls.out=ROOT/'export';cls.out.mkdir()
        cls.choice={'history':False,'dz':8,'clock':'hour','lam':.01,'emotion_lam':10}
        cls.report=E.export_fit(cls.events,cls.out,cls.choice,'America/Chicago',{'kind':'synthetic'},steps=4)

    def setUp(self):
        for p in MEM.iterdir():
            if p.is_dir():shutil.rmtree(p)
            else:p.unlink()
        (MEM/'jepa-readouts').mkdir()
        shutil.copy(self.out/'present-moment.npz',MEM/'jepa-readouts/present-moment.npz')
        meta={'schema':'anchored-readout-v1','mode':'gloria','report':{'confidence':{'calibration_n':14}}}
        np.savez_compressed(MEM/'jepa-readouts/gloria.npz',meta=json.dumps(meta),projection=np.eye(24,8),
                            beta=1.,gamma=0.,W=np.zeros((8,43)),bias=np.zeros(8),confidence_W=np.array([.4,0,0,0,0]))
        self.now=time.time()
        self.exs=[{'at':self.now-600,'ts':datetime.fromtimestamp(self.now-600).isoformat(),
                   'her':'The seed packets are beside the garden gate.',
                   'his':'I remember the green beans and the watering can.', 'turn_id':'test-turn'}]
        self.thread='There is an unfinished sketch of the garden gate and the row of beans.'
        F.atomic(MEM/'unfinished-threads.json',[{'timestamp':datetime.fromtimestamp(self.now-900,timezone.utc).isoformat(),'thread':self.thread}])
        F.atomic(MEM/'emotion-trajectory-dense.json',[{'t':datetime.fromtimestamp(self.now-300,timezone.utc).isoformat(),'v':[.5]*11}])
        self.exchange_patch=patch.object(F,'_exchange_rows',lambda mem:self.exs)
        self.exchange_patch.start();self.addCleanup(self.exchange_patch.stop)

    def refresh(self,now=None):return F.refresh(enc=self.enc,memory=MEM,exs=self.exs,now=now or self.now)

    def test_01_export_parity_and_timezone(self):
        self.assertTrue(self.report['parity']['passed'])
        self.assertTrue(self.report['parity']['ranks_identical'])
        model=M.Model(self.out/'present-moment.npz');state=M.State(model)
        for e in E.read_snapshot(self.out/'events.npz')[:30]:state.advance(e)
        before=state.features()
        os.environ['TZ']='UTC';time.tzset()
        self.assertTrue(np.array_equal(before,state.features()))
        os.environ['TZ']='America/Chicago';time.tzset()
        self.assertTrue(np.array_equal(before,M.State(model,state.dump()).features()))

    def test_02_duplicates_backfill_and_causality(self):
        model=M.Model(self.out/'present-moment.npz');state=M.State(model)
        events=E.read_snapshot(self.out/'events.npz')
        state.advance(events[0]);state.advance(events[1]);before=state.dump()
        self.assertIsNone(state.advance(events[1]));self.assertIsNone(state.advance(events[0]))
        self.assertEqual(before,state.dump())
        other=M.State(model,before);other.advance(dict(events[2],vec=(-np.array(events[2]['vec'])).tolist()))
        self.assertEqual(before,state.dump())
        self.assertEqual(state.advance(events[2])['before_cursor'],before['cursor'])
        with self.assertRaises(ValueError):M.stamp('2026-10-01T12:00:00')

    def test_03_no_future_fit_leakage(self):
        altered=[dict(e) for e in self.events]
        for e in altered:
            if e['t'].astimezone().date().isoformat()>='2026-10-13':
                if 'vec'in e:e['vec']=(-np.array(e['vec'])).tolist()
                if 'emo'in e:e['emo']=(1-np.array(e['emo'])).tolist()
        dest=ROOT/'altered';dest.mkdir(exist_ok=True)
        E.export_fit(altered,dest,self.choice,'America/Chicago',{'kind':'synthetic'},steps=4)
        a,b=M.Model(self.out/'present-moment.npz'),M.Model(dest/'present-moment.npz')
        for k in a.a:self.assertTrue(np.array_equal(a.a[k],b.a[k]),k)

    def test_04_packet_two_channels_and_coalescing(self):
        self.assertEqual(self.refresh()['status'],'updated')
        p=F.load(MEM/'latent-feed.json');self.assertEqual(set(p['channels']),{'stream','gloria'})
        b=(MEM/'latent-feed-state.json').read_bytes()
        with patch.object(self.enc,'encode',side_effect=AssertionError('no repeated encoding')):
            self.assertEqual(self.refresh()['status'],'unchanged')
        self.assertEqual(b,(MEM/'latent-feed-state.json').read_bytes())
        text,r=F.evidence('trajectory',MEM,now=self.now)
        self.assertIn('TRAINED CONTEXT',text);self.assertEqual(r['frame_id'],p['frame_id'])
        self.assertIn('not certainty about intent',text)
        self.assertNotIn(self.thread,(MEM/'latent-feed.json').read_text())

    def test_05_missing_malformed_stale_and_wrong_checkpoint(self):
        original='ORIGINAL FEED\n'+('existing context '*200)
        self.assertEqual(F.append_context(original,'novelty',MEM),original)
        self.refresh();p=F.load(MEM/'latent-feed.json')
        good=F.append_context(original,'novelty',MEM);self.assertTrue(good.startswith(original));self.assertGreater(len(good),len(original))
        F.atomic(MEM/'latent-feed.json',[]);self.assertEqual(F.append_context(original,'novelty',MEM),original)
        p['generated_at']=self.now-F.TTL-1;F.atomic(MEM/'latent-feed.json',p)
        self.assertEqual(F.append_context(original,'novelty',MEM),original)
        p['generated_at']=self.now
        for c in p['channels'].values():c['checkpoint_id']='wrong'
        F.atomic(MEM/'latent-feed.json',p)
        self.assertEqual(F.append_context(original,'novelty',MEM),original)

    def test_06_removed_source_and_derived_dream(self):
        self.exs.clear()
        self.refresh();text,_=F.evidence('withheld',MEM,now=self.now)
        self.assertIn(self.thread,text)
        F.atomic(MEM/'unfinished-threads.json',[])
        self.assertNotIn(self.thread,F.evidence('withheld',MEM,now=self.now)[0])
        self.refresh(now=self.now+1)
        st=F.load(MEM/'latent-feed-state.json')
        self.assertNotIn(F.digest([JP.EMB_MODEL,self.thread]),F.load(MEM/'latent-feed-embeddings.json'))
        F.atomic(MEM/'unfinished-threads.json',[{'timestamp':datetime.fromtimestamp(self.now-100,timezone.utc).isoformat(),'thread':'A generated imagined possibility that did not happen','dream_only':True}])
        self.assertFalse(any(e['source']=='thread' for e in F.read_events(MEM,self.exs)))

    def test_07_pending_gloria_attribution_across_emotion_ticks(self):
        self.refresh();frame=F.load(MEM/'latent-feed.json')['frame_id']
        dense=F.load(MEM/'emotion-trajectory-dense.json')
        dense.append({'t':datetime.fromtimestamp(self.now+10,timezone.utc).isoformat(),'v':[.51]*11})
        F.atomic(MEM/'emotion-trajectory-dense.json',dense);self.refresh(now=self.now+11)
        her='The green beans need another row beside the path.'
        self.exs.append({'at':self.now+20,'ts':datetime.fromtimestamp(self.now+20).isoformat(),'her':her,'his':'We can mark out the new row.','turn_id':'test-turn-2'})
        self.refresh(now=self.now+21)
        out=F.missed_evidence(frame,her,self.now+20,MEM)
        self.assertIn('MATCHED NEXT-TURN',out)
        self.assertEqual('',F.missed_evidence(frame,'wrong text',self.now+20,MEM))
        self.assertEqual('',F.missed_evidence('wrong frame',her,self.now+20,MEM))
        rows=F.load(MEM/'latent-feed-state.json')['outcomes']
        ids=[o['id'] for o in rows if o.get('target')=='next_gloria_turn']
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(self.refresh(now=self.now+22)['status'],'unchanged')

    def test_08_context_arrives_before_generation_and_preserves_original(self):
        self.refresh()
        import gloria_prediction as GP,latent_preparation as LP,withheld_head as WH
        CALLS=[]
        def post(url,json=None,**kw):
            CALLS.append(json['messages'][1]['content'])
            class Response:
                def json(self):return {'choices':[{'message':{'content':'{"predicted":"She will discuss the next row.","confidence":0.2,"novelty":0.3,"content":"I am ready to hear about the next row.","withheld":"He kept the unfinished sketch of the garden gate to himself.","deliberate":0.7}'}}]}
            return Response()
        rows=[{'role':'user','content':self.exs[0]['her'],'timestamp':self.exs[0]['ts']},
              {'role':'assistant','content':self.exs[0]['his'],'timestamp':self.exs[0]['ts']}]
        F.atomic(MEM/'chat-history-merged.json',rows)
        with patch.object(requests,'post',post):
            GP.main();LP.voice(.4,.3,'existing hint','existing posture');WH.main()
        self.assertEqual(len(CALLS),3)
        self.assertTrue(all('TRAINED CONTEXT' in c for c in CALLS))
        self.assertIn('RECENT CONVERSATION:',CALLS[0]);self.assertIn('existing posture',CALLS[1]);self.assertIn('BEING:',CALLS[2])
        gp=F.load(GP.OUT);self.assertEqual(gp['prose_confidence'],.2);self.assertIn('latent_grounding',gp)
        self.assertEqual(F.load(WH.OUT)['confidence'],.7)

    def test_09_premonition_relational_and_novelty_preserve_original(self):
        spec=importlib.util.spec_from_file_location('dream_test',REPO/'scripts/premonition-dreamer.py')
        dream=importlib.util.module_from_spec(spec);spec.loader.exec_module(dream)
        import relational_head as RH,emoclaw_utils as EU
        F.atomic(MEM/'gloria-prediction.json',{'predicted':'The next row of beans.'})
        F.atomic(MEM/'relational.json',{'moving':True,'trajectory':.4,'novelty':.6,'p_value':.01})
        F.atomic(MEM/'jepa-prediction.json',{'source':'jepa','self':{'novelty':.3,'confidence':.8}})
        F.atomic(MEM/'living-trajectory.json',{'self_trajectory':{'declared':['Finish the garden sketch']}})
        original=[dream.gather_present(),RH.get_relational_hint(),EU._novelty_directive()]
        self.refresh()
        extra=[dream.gather_present(),RH.get_relational_hint(),EU._novelty_directive()]
        for a,b in zip(original,extra):
            self.assertTrue(a);self.assertTrue(b.startswith(a));self.assertIn('TRAINED CONTEXT',b)
        with patch.object(F,'append_context',side_effect=RuntimeError('offline')):
            self.assertEqual(original,[dream.gather_present(),RH.get_relational_hint(),EU._novelty_directive()])

    def test_10_reading_keeps_call_count_and_original_words(self):
        import reading as R
        calls=[]
        with patch.object(R,'_ask',side_effect=lambda a,b:calls.append(b) or 'An alternative about the garden.\nAnother about the tools.'),patch.object(R,'open_reading',return_value='id') as op:
            self.assertEqual(R.from_missed_prediction('old prediction','actual words',evidence_context='\nMATCHED EVIDENCE'),'id')
            self.assertEqual(len(calls),1);self.assertIn('old prediction',calls[0]);self.assertIn('actual words',calls[0]);self.assertIn('MATCHED EVIDENCE',calls[0])
            self.assertEqual(op.call_count,1)

    def test_11_retrieval_uses_only_past_candidates(self):
        r=E.retrieval_audit(self.out/'present-moment.npz',self.out/'events.npz')
        self.assertTrue(r['all_candidates_before_target'])
        self.assertEqual(set(r['means']),{'recent_context','last_text_retrieval','trained_retrieval'})
        self.assertEqual(r['anchor_budget'],2)
        self.assertGreater(r['n'],0)

    def test_12_corrupt_optional_head_does_not_lose_stream(self):
        (MEM/'jepa-readouts/gloria.npz').write_bytes(b'invalid checkpoint')
        F.atomic(MEM/'latent-feed-embeddings.json',[])
        self.assertEqual(self.refresh()['status'],'updated')
        p=F.load(MEM/'latent-feed.json')
        self.assertIn('stream',p['channels']);self.assertNotIn('gloria',p['channels'])
        self.assertIn('gloria',p['channel_errors'])
        self.assertIn('TRAINED CONTEXT',F.evidence('trajectory',MEM,now=self.now)[0])

    def test_13_background_tick_keeps_sampling_and_never_waits(self):
        import emotion_densifier as D,subprocess
        python=MEM.parent/'emotion_model/.venv/bin/python3';python.parent.mkdir(parents=True,exist_ok=True);python.touch()
        with patch.object(subprocess,'Popen',return_value=types.SimpleNamespace(pid=1)) as pop:
            self.assertEqual(F.launch_refresh(MEM)['status'],'launched')
            self.assertTrue(pop.call_args.kwargs['start_new_session'])
            self.assertEqual(pop.call_args.kwargs['env']['CUDA_VISIBLE_DEVICES'],'')
            self.assertEqual(pop.call_args.args[0][-1],'--refresh')
        with patch.object(D,'live_state',return_value={'emotion_vector':[.5]*11}),patch.object(F,'launch_refresh') as launch:
            before=(MEM/'emotion-trajectory-dense.json').read_bytes()
            D.main()
            self.assertEqual((MEM/'emotion-trajectory-dense.json').read_bytes(),before)
            self.assertEqual(launch.call_count,1)
        with patch.object(D,'live_state',side_effect=OSError('offline')),patch.object(F,'launch_refresh') as launch:
            D.main();self.assertEqual(launch.call_count,1)

    def test_14_gloria_outcomes_use_the_trained_target_view(self):
        self.refresh();p=F.load(MEM/'latent-feed.json');frame=p['frame_id'];g=p['channels']['gloria']
        her=('The garden row is ready and the seeds are here. '*15)+('A different topic about the workshop. '*15)
        self.exs.append({'at':self.now+20,'ts':datetime.fromtimestamp(self.now+20).isoformat(),'her':her,'his':'I can see the rows.','turn_id':'long-turn'})
        self.refresh(now=self.now+21)
        rows=F.load(MEM/'latent-feed-state.json')['outcomes']
        matched=next(r for r in rows if r.get('frame_id')==frame and r.get('target')=='next_gloria_turn')
        vec=self.enc.encode([her[:400]])[0];vec=vec/np.linalg.norm(vec)
        expected=float(1-np.asarray(g['query'])@vec)
        self.assertAlmostEqual(matched['text_error'],expected,places=6)
        self.assertEqual(matched['embedding_view'],'her_words[:400]')
        self.assertNotAlmostEqual(expected,float(1-np.asarray(g['query'])@self.enc.encode([' '.join(her.split())[:1500]])[0]),places=3)

    def test_15_isolation_and_export_guard(self):
        self.assertTrue(str(MEM).startswith(str(ROOT)));self.assertIs(requests.post,no_network);self.assertEqual(NET,[])
        with self.assertRaises(ValueError):E.safe_output(MEM/'bad-export')
        with self.assertRaises(ValueError):E.export_fit(self.events,ROOT,dict(self.choice,history=True),'UTC',{},steps=1)

if __name__=='__main__':unittest.main()
