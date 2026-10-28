#!/usr/bin/env python3
"""End-to-end synthetic closed-week evaluation; never opens actual fresh inputs."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import torch
import data as D
import evaluate as E
from scan import SelectiveScan

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from latent_stream_model import save


class Evaluation(unittest.TestCase):
    def test_complete_synthetic_week_and_repeat_refusal(self):
        root=Path(tempfile.mkdtemp(dir=os.environ['PERSISTENCE_SCRATCH']))
        seal=root/'seal';seal.mkdir()
        t=D.boundary('2026-10-31')+np.arange(7*144+6)*600.
        t=t[t<D.boundary('2026-11-07')]
        n=len(t);emo=np.tile(np.arange(11,dtype=np.float32),(n,1))*.01
        text=np.eye(8,dtype=np.float32)[np.arange(n)%8]
        source=np.zeros((n,12),np.float32);source[:,0]=1;numeric=np.zeros((n,12),np.float32)
        np.savez(root/'events.npz',t=t,emo=emo,text=text,source=source,numeric=numeric,
                 text_i=np.arange(n),text_vectors=text,text_source=np.ones(n,dtype=int),text_exact=np.ones(n,bool))
        dim=3+11+6+4
        params=dict(P=np.eye(8,3),mu=np.zeros(8),emo_mu=np.zeros(11),emo_sd=np.ones(11),
                    W=np.zeros((3,dim)),Bm=np.zeros((dim,11)),beta=np.array(1.),gamma=np.array(0.),scale=np.array(5.))
        save(seal/'incumbent.npz',params,dict(clock='hour',timezone=str(D.TZ),val_from='2026-10-09'))
        shutil.copyfile(seal/'incumbent.npz',seal/'present-refit.npz')
        present=D.features(t,source,emo,text,numeric,0,stats=(np.zeros(11),np.ones(11)))[0]
        model=SelectiveScan(present.shape[1]+32)
        candidates=[]
        for k in range(1,9):
            p=seal/('candidate-'+str(k));p.mkdir();torch.save(model.state_dict(),p/'scan.pt')
            a=dict(projection=np.eye(8,3),projection_mu=np.zeros(8),emotion_mu=np.zeros(11),emotion_sd=np.ones(11),
                   text_W=np.zeros((24,3)),alpha=np.array(0.),climatology=emo[0])
            for h in D.HORIZONS:
                for name,width in [('present',present.shape[1]),('history',36),('selective',24),('reset',24)]:
                    a[str(h)+'_'+name]=np.zeros((width,11))
            np.savez(p/'readouts.npz',**a)
            np.savez(p/'schedule.npz',prob=np.ones((288,12))/12,log_gap=np.ones(288))
            candidates.append(dict(round=k,anchor_history=k>=6,files={f:D.sha(p/f) for f in ('scan.pt','readouts.npz','schedule.npz')}))
        exp=seal/'code/experiments/persistence-sprint';exp.mkdir(parents=True)
        for p in Path(__file__).parent.glob('*.py'):shutil.copyfile(p,exp/p.name)
        scripts=seal/'code/scripts';scripts.mkdir()
        for name in ('latent_stream_model.py','latent_stream_linear.py','latent_stream_replay.py'):
            shutil.copyfile(Path(__file__).resolve().parents[2]/'scripts'/name,scripts/name)
        manifest=dict(week=['2026-10-31','2026-11-07'],sealed_at='2026-10-28T06:00:00-05:00',
                      code={str(p.relative_to(seal/'code')):D.sha(p) for p in (seal/'code').rglob('*.py')},
                      incumbent_sha256=D.sha(seal/'incumbent.npz'),present_refit_sha256=D.sha(seal/'present-refit.npz'),
                      candidates=candidates,selected_primary=7,primary_horizon=21600,ci_quantiles=[.001,.999],
                      bootstrap_samples=100,min_primary_targets=300,min_days=7,practical_gain=.05,text_relative_floor=.99)
        D.write_json(seal/'manifest.json',manifest)
        args=argparse.Namespace(sealed=str(seal),snapshot=str(root/'events.npz'),out=str(root/'result'))
        class Closed(datetime):
            @classmethod
            def now(cls,tz=None):return cls(2026,11,7,8,tzinfo=tz)
        with patch.object(D,'datetime',Closed):
            E.score(args)
            with self.assertRaises(FileExistsError):E.score(args)
        import json
        report=json.loads((root/'result/fresh-report.json').read_text())
        self.assertEqual(len(report['candidates']),8)
        self.assertFalse(report['primary_passes'])
        self.assertTrue(report['candidates']['7']['emotion']['21600']['enough_data'])
        self.assertTrue((seal/'evaluation-attempt.json').exists())


if __name__=='__main__':
    torch.set_num_threads(1)
    unittest.main()
