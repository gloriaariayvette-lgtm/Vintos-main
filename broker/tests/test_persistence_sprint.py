#!/usr/bin/env python3
"""NumPy-only offline contracts: synthetic data, scratch stores, denied sends."""
from datetime import datetime
import importlib.util
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
import numpy as np

ROOT=Path(tempfile.mkdtemp(prefix='persistence-test-'))
os.environ.update(HOME=str(ROOT/'home'),SPARK_WORKSPACE=str(ROOT),PERSISTENCE_SCRATCH=str(ROOT))
def denied(*a,**k):raise AssertionError('no sends in offline sprint tests')
socket.socket.connect=denied
folder=Path(__file__).resolve().parents[2]/'experiments/persistence-sprint'
spec=importlib.util.spec_from_file_location('persistence_data',folder/'data.py')
D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)


class Contracts(unittest.TestCase):
    def setUp(self):
        self.assertIs(socket.socket.connect,denied)
        self.assertTrue(ROOT.is_relative_to(Path(tempfile.gettempdir())))

    def test_horizons_are_real_unique_readings(self):
        t=np.arange(0,7200,60.);mask=np.arange(len(t))%10==0
        pairs=D.horizon_pairs(t,mask,600)
        self.assertEqual(len(np.unique(pairs[:,1])),len(pairs))
        self.assertTrue(mask[pairs].all());np.testing.assert_array_equal(np.diff(t[pairs],axis=1),600)

    def test_no_missing_reading_interpolation(self):
        self.assertEqual(len(D.horizon_pairs(np.array([0.,5000.,20000.]),np.ones(3,bool),600)),0)

    def test_split_excludes_crossing_outcomes(self):
        p=np.array([[0,1],[1,2],[2,3]])
        np.testing.assert_array_equal(D.split_pairs(p,np.arange(4)*600,600,1800),[[1,2]])

    def test_future_extension_preserves_pairs(self):
        t=np.arange(40)*600.
        a=D.horizon_pairs(t,np.ones(40,bool),600)
        b=D.horizon_pairs(np.r_[t,24000],np.ones(41,bool),600)
        np.testing.assert_array_equal(a,b[:len(a)])

    def test_no_optimistic_ties(self):
        np.testing.assert_array_equal(D.ranks(np.ones((3,3)),np.arange(3)),[3,3,3])

    def test_scratch_rejects_live_or_parent(self):
        for p in (ROOT,ROOT.parent,Path('/home/gloria/.vintos/workspace')):
            with self.assertRaises(ValueError):D.scratch(p)

    def test_projection_fits_training_only(self):
        rng=np.random.default_rng(4);x=rng.normal(size=(30,8));t=np.arange(30)
        _,mu,p=D.projected_text(x,np.ones(30,bool),10,t,4)
        x[10:]*=10000
        _,mu2,p2=D.projected_text(x,np.ones(30,bool),10,t,4)
        np.testing.assert_array_equal(mu,mu2);np.testing.assert_array_equal(p,p2)

    def test_future_does_not_change_prefix_features(self):
        t=np.arange(40)*600.+D.boundary('2026-10-01')
        e=np.tile(np.arange(11),(40,1)).astype(float);x=np.ones((40,8));s=np.zeros((40,12));n=np.zeros((40,12))
        a=D.features(t,s,e,x,n,t[10])
        e[30:]+=100;x[30:]*=-100;n[30:]+=100
        b=D.features(t,s,e,x,n,t[10])
        for u,v in zip(a[:4],b[:4]):np.testing.assert_array_equal(u[:30],v[:30])

    def test_gap_is_not_a_continuous_emotion_observation(self):
        e=np.array([np.zeros(11),np.ones(11),np.ones(11)])
        t=np.array([0,600,100000.])+D.boundary('2026-10-01')
        a=D.features(t,np.zeros((3,12)),e,np.zeros((3,8)),np.zeros((3,12)),t[-1]+1)
        # Capped 720-second support, not the entire quiet interval.
        self.assertLess(a[1][-1,-1],.02)

    def test_day_boundaries_respect_dst(self):
        self.assertEqual(D.boundary('2026-11-02')-D.boundary('2026-11-01'),25*3600)

    def test_round_check_blocks_are_disjoint(self):
        blocks=[(D.boundary(r[2]),D.boundary(r[3])) for r in D.ROUNDS]
        for a,b in zip(blocks,blocks[1:]):self.assertLessEqual(a[1],b[0])

    def test_ridge_can_choose_zero_residual(self):
        np.testing.assert_array_equal(D.ridge(np.eye(5),np.zeros((5,11))),np.zeros((5,11)))

    def make_seal(self):
        p=Path(tempfile.mkdtemp(dir=ROOT));(p/'code').mkdir()
        (p/'code/fixture.py').write_text('fixture only')
        (p/'incumbent.npz').write_bytes(b'fixture');(p/'present-refit.npz').write_bytes(b'fixture')
        m=dict(week=['2026-10-31','2026-11-07'],sealed_at='2026-10-28T06:00:00-05:00',
               code={'fixture.py':D.sha(p/'code/fixture.py')},candidates=[],
               incumbent_sha256=D.sha(p/'incumbent.npz'),present_refit_sha256=D.sha(p/'present-refit.npz'))
        D.write_json(p/'manifest.json',m)
        return p,m

    def test_early_evaluation_consumes_no_attempt(self):
        p,m=self.make_seal()
        with self.assertRaisesRegex(ValueError,'not closed'):
            D.begin_evaluation(p,m,datetime(2026,11,6,tzinfo=D.TZ))
        self.assertFalse((p/'evaluation-attempt.json').exists())

    def test_exactly_one_attempt_even_for_failure(self):
        p,m=self.make_seal();now=datetime(2026,11,7,tzinfo=D.TZ)
        D.begin_evaluation(p,m,now)
        with self.assertRaises(FileExistsError):D.begin_evaluation(p,m,now)

    def test_altered_code_refuses_before_attempt(self):
        p,m=self.make_seal();(p/'code/fixture.py').write_text('altered fixture')
        with self.assertRaisesRegex(ValueError,'code mismatch'):
            D.begin_evaluation(p,m,datetime(2026,11,7,tzinfo=D.TZ))
        self.assertFalse((p/'evaluation-attempt.json').exists())

    def test_late_seal_refused(self):
        p,m=self.make_seal();m['sealed_at']='2026-10-31T00:00:00-05:00'
        with self.assertRaisesRegex(ValueError,'late seal'):
            D.begin_evaluation(p,m,datetime(2026,11,7,tzinfo=D.TZ))

    def test_interval_is_paired_and_uses_worst_control(self):
        values=np.tile([1.,2.],(14,1));days=np.repeat(np.arange(7),2)
        np.testing.assert_array_equal(D.paired_interval(values,days,[.001,.999],200),[1.,1.])

    def test_fixed_feature_stats_ignore_future_emotion(self):
        e=np.ones((3,11));t=np.arange(3)*600.+D.boundary('2026-11-01')
        stats=(np.zeros(11),np.ones(11));s=np.zeros((3,12));x=np.zeros((3,8));n=np.zeros((3,12))
        a=D.features(t,s,e,x,n,0,stats=stats)
        np.testing.assert_array_equal(a[-2],stats[0]);np.testing.assert_array_equal(a[-1],stats[1])


if __name__=='__main__':unittest.main()
