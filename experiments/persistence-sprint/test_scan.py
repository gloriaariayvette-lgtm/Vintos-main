#!/usr/bin/env python3
"""CPU training-runtime regressions, outside the NumPy-only deploy suite."""
import unittest
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


if __name__=='__main__':unittest.main()
