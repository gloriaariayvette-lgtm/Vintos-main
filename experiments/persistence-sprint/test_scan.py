#!/usr/bin/env python3
"""CPU training-runtime regressions, outside the NumPy-only deploy suite."""
import unittest
import os
from pathlib import Path
import tempfile
import numpy as np
import torch
from scan import SelectiveScan,states


class ScanTests(unittest.TestCase):
    def setUp(self):torch.manual_seed(12);torch.set_num_threads(1)

    def test_chunk_and_restart_parity(self):
        model=SelectiveScan(8);x=torch.randn(150,8);dt=torch.ones(150)*600
        full,h=model(x,dt);a,ha=model(x[:73],dt[:73]);b,hb=model(x[73:],dt[73:],ha)
        torch.testing.assert_close(full,torch.cat([a,b]));torch.testing.assert_close(h,hb)

    def test_prefix_causality_and_real_memory(self):
        model=SelectiveScan(8);x=np.ones((100,8),np.float32);dt=np.ones(100,np.float32)*600
        first=states(model,x,dt);x[70:]=-100
        second=states(model,x,dt)
        np.testing.assert_array_equal(first[:70],second[:70])
        self.assertGreater(float(np.max(abs(first-states(model,np.ones_like(x),dt,True)))),1e-5)

    def test_zero_start_heads_and_gap_decay(self):
        model=SelectiveScan(8);x=torch.ones(2,8)
        torch.testing.assert_close(model.emotion(torch.ones(2,32)),torch.zeros(2,77))
        h=torch.ones(24);_,short=model(x[:1],torch.tensor([1.]),h)
        _,long=model(x[:1],torch.tensor([1e9]),h)
        self.assertTrue(torch.isfinite(long).all());self.assertGreater(torch.norm(short-long),.1)
        # The text residual is also exactly zero before fitting.
        torch.testing.assert_close(model.text(torch.ones(2,24)),torch.zeros(2,32))

    def test_disk_checkpoint_restart_matches_uninterrupted(self):
        model=SelectiveScan(8);x=torch.randn(150,8);dt=torch.linspace(1,900,150)
        with torch.no_grad():
            full,h=model(x,dt);_,prefix=model(x[:73],dt[:73])
        root=Path(tempfile.mkdtemp(dir=os.environ['PERSISTENCE_SCRATCH']))
        torch.save({'weights':model.state_dict(),'state':prefix,'next_index':73},root/'checkpoint.pt')
        saved=torch.load(root/'checkpoint.pt',weights_only=True,map_location='cpu')
        restarted=SelectiveScan(8);restarted.load_state_dict(saved['weights'])
        tail,end=restarted(x[saved['next_index']:],dt[saved['next_index']:],saved['state'])
        torch.testing.assert_close(full[73:],tail);torch.testing.assert_close(h,end)

    def test_timestamp_batch_queries_precede_all_members(self):
        from run import query_rows
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
        from latent_stream_model import save
        root=Path(tempfile.mkdtemp(dir=os.environ['PERSISTENCE_SCRATCH']))
        dim=3+11+6+4
        save(root/'baseline.npz',dict(P=np.eye(8,3),mu=np.zeros(8),emo_mu=np.zeros(11),
             emo_sd=np.ones(11),W=np.ones((3,dim))*.01,Bm=np.zeros((dim,11)),
             beta=np.array(1.),gamma=np.array(0.),scale=np.array(5.)),
             dict(clock='hour',timezone='America/Chicago',val_from='2026-10-09'))
        d=dict(text_i=np.array([0,1,1,2]),text_vectors=np.eye(8)[:4],
               text_exact=np.ones(4,bool),text_source=np.array([1,4,5,1]),emo=np.zeros((3,11)))
        t=np.array([1790870000.,1790870600.,1790871200.])
        q=query_rows(d,t,root/'baseline.npz')[1]
        d['text_vectors'][1:3]*=-1;d['emo'][1]=100
        changed=query_rows(d,t,root/'baseline.npz')[1]
        np.testing.assert_array_equal(q[1],q[2])
        np.testing.assert_array_equal(q[:3],changed[:3])
        self.assertGreater(float(np.linalg.norm(q[3]-changed[3])),0)


if __name__=='__main__':unittest.main()
