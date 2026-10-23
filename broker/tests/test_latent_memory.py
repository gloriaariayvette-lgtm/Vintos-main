#!/usr/bin/env python3
"""Scratch-only experiment contracts; no provider, live store, or sender access."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
import numpy as np

ROOT=Path(tempfile.mkdtemp(prefix='latent-memory-test-'))
os.environ.update(HOME=str(ROOT/'home'),SPARK_WORKSPACE=str(ROOT),LATENT_MEMORY_SCRATCH=str(ROOT))
REPO=Path(__file__).resolve().parents[2]
def deny(*a,**k):raise AssertionError('no network or senders in tests')
socket.socket.connect=deny
spec=importlib.util.spec_from_file_location('memory_experiment',REPO/'experiments/latent-memory/replay.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
from latent_stream_model import save,Model,State


def make_model():
    dim=8;dz=3;hdim=dz+11+6+2+2
    path=ROOT/'incumbent.npz'
    arrays=dict(P=np.eye(dim,dz),mu=np.zeros(dim),emo_mu=np.zeros(11),emo_sd=np.ones(11),
                W=np.zeros((dz,hdim)),Bm=np.zeros((hdim,11)),beta=np.array(1.),gamma=np.array(0.),scale=np.array(5.))
    save(path,arrays,{'clock':'hour','timezone':'America/Chicago'})
    return Model(path)


def event(i,at,source='inner',vec=None):
    if source=='emotion':return {'id':str(i),'t':at,'source':source,'emo':np.ones(11)*(.2+i*.001),'lam_features':[1.,i*.001]}
    v=np.eye(8)[i%8] if vec is None else np.asarray(vec)
    return {'id':str(i),'t':at,'source':source,'vec':v,'t_exact':True,'template_id':'form' if i%2 else ''}


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert ROOT.is_relative_to(Path(tempfile.gettempdir()))
        assert socket.socket.connect is deny
        cls.model=make_model();cls.at=datetime(2026,10,1,tzinfo=R.TZ)

    def test_01_zero_correction_and_budget(self):
        rows=[]
        for i in range(12):
            v=np.eye(8)[i%8]
            rows.append(dict(y=v,query=v,source='inner',memory={'episodic':np.zeros((3,8))}))
        a=R.fit_text(rows,'episodic',1.,5.)
        np.testing.assert_array_equal(a,np.zeros(3));self.assertLessEqual(a.sum(),.25+1e-8)

    def test_02_old_bank_admission_and_cap(self):
        bank=R.Bank(8)
        es=[event(i,self.at+timedelta(hours=i)) for i in range(30)]
        bank.add(es);v,refs=bank.vectors(np.ones(8),es[-1]['t'],'episodic','f')
        self.assertTrue(refs)
        self.assertTrue(all(int(x)<23 for x in refs))
        bank.add([event(3000+i,self.at+timedelta(days=20,minutes=i)) for i in range(2050)])
        self.assertEqual(len(bank.items),2048)
        _,refs=bank.vectors(np.ones(8),self.at+timedelta(days=40),'episodic','f')
        self.assertEqual(refs,[])

    def test_03_same_time_no_target_leak(self):
        es=[event(0,self.at),event(1,self.at+timedelta(hours=10)),event(2,self.at+timedelta(hours=10))]
        a=R.replay(R.clean_events(es),self.model,('episodic',))[0]
        altered=[dict(e) for e in es];altered[1]['vec']=-es[1]['vec']
        b=R.replay(R.clean_events(altered),self.model,('episodic',))[0]
        for x,y in zip(a,b):
            np.testing.assert_array_equal(x['query'],y['query'])
            np.testing.assert_array_equal(x['memory']['episodic'],y['memory']['episodic'])
        np.testing.assert_array_equal(a[0]['query'],a[1]['query'])
        self.assertFalse(a[0]['exact'])

    def test_04_permutation_duplicates_and_future(self):
        es=[event(0,self.at),event(1,self.at+timedelta(hours=8)),event(2,self.at+timedelta(hours=8))]
        one=R.replay(R.clean_events(es),self.model,('episodic',))[0]
        two=R.replay(R.clean_events(es[::-1]+[es[0],event(3,self.at+timedelta(days=3))]),self.model,('episodic',))[0]
        for x,y in zip(one,two):np.testing.assert_array_equal(x['query'],y['query'])
        self.assertEqual(len(one),2)

    def test_05_random_is_deterministic_and_group_matched(self):
        bank=R.Bank(8);es=[event(i,self.at+timedelta(hours=i),source=('her','inner','thread')[i%3]) for i in range(60)]
        bank.add(es)
        for seed in range(10):
            a,ar=bank.vectors(np.ones(8),es[-1]['t'],'random_%d'%seed,'frame')
            b,br=bank.vectors(np.ones(8),es[-1]['t'],'random_%d'%seed,'frame')
            np.testing.assert_array_equal(a,b);self.assertEqual(ar,br);self.assertEqual(len(ar),len(set(ar)))

    def test_06_fixed_horizon_and_no_repeated_target(self):
        es=[event(i,self.at+timedelta(seconds=t),'emotion') for i,t in enumerate([0,30,600,700,1300,4000])]
        _,rows,_=R.replay(es,self.model,('episodic',))
        self.assertEqual(len({r['target_at'] for r in rows}),len(rows))
        self.assertTrue(all(600<=r['target_at']-r['at']<=720 for r in rows))

    def test_07_emotion_gaps_not_invented(self):
        dense=[(0,np.zeros(11)),(600,np.ones(11)),(1200,np.ones(11))]
        missing=[(0,np.zeros(11)),(100000,np.ones(11))]
        a=R.emotion_features(dense,np.ones(11));b=R.emotion_features(missing,np.ones(11))
        self.assertLess(b[11],a[11]);self.assertEqual(b[-1],1.)

    def test_08_split_crossing_removed(self):
        ts=[dict(day=d) for d in ('2026-10-08','2026-10-09','2026-10-11','2026-10-22')]
        es=[dict(day='2026-10-08',target_day='2026-10-09'),dict(day='2026-10-09',target_day='2026-10-09')]
        t,e=R.blocks(ts,es);self.assertEqual([len(x) for x in t],[1,1,1,1]);self.assertEqual([len(x) for x in e],[0,1,0,0])

    def test_09_forget_rebuild_removes_episode(self):
        es=[event(i,self.at+timedelta(hours=i*8)) for i in range(12)]
        bank=R.Bank(8);bank.add([e for e in es if e['id']!='0'])
        _,refs=bank.vectors(np.eye(8)[0],es[-1]['t'],'episodic','f');self.assertNotIn('0',refs)

    def test_10_incumbent_restart_and_query_rank_parity(self):
        s=State(self.model)
        for i in range(8):s.advance(event(i,self.at+timedelta(hours=i)))
        restored=State(self.model,s.dump())
        np.testing.assert_allclose(self.model.query(s),self.model.query(restored))
        candidates=np.eye(8)
        np.testing.assert_array_equal(np.argsort(self.model.scores(s,candidates)),np.argsort(candidates@self.model.query(s)))

    def test_11_scratch_guard_and_no_future_inputs(self):
        with self.assertRaises(ValueError):R.scratch_output(ROOT.parent/'not-authorized')
        path=ROOT/'future.npz'
        np.savez(path,rows=json.dumps([dict(id='future',t='2026-10-23T00:00:00-05:00',source='inner')]),X=np.ones((1,8)),E=np.zeros((1,11)),is_text=[True],is_emotion=[False])
        with self.assertRaisesRegex(ValueError,'cutoff'):R.load_events(path)

    def test_12_no_early_evaluation(self):
        sealed=ROOT/'sealed';sealed.mkdir(exist_ok=True)
        np.savez(sealed/'frozen.npz',x=np.ones(1))
        R.write_json(sealed/'manifest.json',dict(code_sha256=R.sha(R.__file__),incumbent_sha256=self.model.checkpoint_id,frozen_sha256=R.sha(sealed/'frozen.npz')))
        with self.assertRaisesRegex(ValueError,'not closed'):R.evaluate([],self.model,sealed,ROOT,now=self.at)
        self.assertFalse((sealed/'evaluation-attempt.json').exists())

    def test_13_bootstrap_pairing_and_missing(self):
        values=np.column_stack([np.ones(7),np.ones(7)*2]);values[0,1]=np.nan
        samples=R.bootstrap(values,[str(i) for i in range(7)])
        np.testing.assert_allclose(samples[:,0],1.)
        np.testing.assert_allclose(samples[:,1],2.)

    def test_14_fit_frozen_dimensions_and_partial_lam(self):
        rows=[]
        for i in range(30):
            rows.append(dict(h=np.array([1.,i/30]),m=np.array([i/30]),current=np.zeros(11),y=np.ones(11)*i/30,
                             incumbent=np.zeros(11),trend=np.zeros(11),lam_h=[1.,i/30] if i%2 else None,target_day='2026-10-10'))
        fit=R.emotion_fit(rows,np.ones(11),1.)
        report=R.emotion_metrics(rows,fit,np.ones(11))
        self.assertEqual(report['lam_coverage'],15);self.assertIn('lam_matched_subset',report)
        self.assertTrue(np.isfinite(report['lam']['mse']))

    def test_15_end_to_end_selection_does_not_read_refit_scores(self):
        events=[];n=0
        for d in (1,2,8,9,10,11,12,16,22):
            for k in range(4):
                at=datetime(2026,10,d,8,tzinfo=R.TZ)+timedelta(minutes=10*k)
                events += [event(n,at,'her' if d>=16 else 'inner'),event(n+1,at,'emotion')];n+=2
        out=ROOT/'fit';out.mkdir(exist_ok=True)
        with patch.object(R,'fit_text',return_value=np.zeros(3)) as fit:
            report=R.develop_and_refit(R.clean_events(events),self.model,out,'input','code')
        manifest=json.loads((out/'manifest.json').read_text())
        self.assertGreater(manifest['refit_sources']['her'],0)
        self.assertEqual(manifest['fresh'],['2026-10-23','2026-10-30'])
        self.assertEqual(report['fresh_evaluation'],'not run')
        self.assertNotIn('test',report)
        self.assertFalse(manifest['eligible_for_fresh']['text'])
        self.assertEqual(fit.call_args_list[-1].args[0][-1]['day'],'2026-10-22')

    def test_16_useful_memory_fit_is_nonzero_and_constrained(self):
        rows=[]
        for i in range(8):
            v=np.eye(8)[i];m=np.zeros((3,8));m[0]=v
            rows.append(dict(y=v,query=np.zeros(8),source='inner',memory={'episodic':m}))
        a=R.fit_text(rows,'episodic',1.,5.)
        self.assertGreater(a[0],.1);self.assertTrue(np.all(a>=0));self.assertLessEqual(a.sum(),.25000001)

    def test_17_fresh_insufficient_is_terminal_and_no_repeat(self):
        sealed=ROOT/'empty-sealed';sealed.mkdir()
        np.savez(sealed/'frozen.npz',x=[1.])
        R.write_json(sealed/'manifest.json',dict(code_sha256=R.sha(R.__file__),incumbent_sha256=self.model.checkpoint_id,
                     frozen_sha256=R.sha(sealed/'frozen.npz'),sealed_at='2026-10-22T20:00:00-05:00'))
        result=R.evaluate([],self.model,sealed,ROOT,now=datetime(2026,10,30,tzinfo=R.TZ))
        self.assertEqual(result['status'],'insufficient')
        with self.assertRaises(FileExistsError):R.evaluate([],self.model,sealed,ROOT,now=datetime(2026,10,30,tzinfo=R.TZ))

    def test_18_collector_refuses_fresh_before_opening_sources(self):
        import runpy
        class Frozen(datetime):
            @classmethod
            def now(cls,tz=None):return cls(2026,10,22,tzinfo=tz)
        args=['collect.py','--through','2026-10-29','--source-memory','/must-not-open',
              '--cache','/must-not-open','--lam','/must-not-open','--encoder','/must-not-open']
        with patch('datetime.datetime',Frozen),patch.object(sys,'argv',args):
            with self.assertRaisesRegex(ValueError,'fresh block is not closed'):
                runpy.run_path(str(REPO/'experiments/latent-memory/collect.py'),run_name='__main__')

if __name__=='__main__':unittest.main()
