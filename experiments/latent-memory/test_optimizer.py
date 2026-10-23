#!/usr/bin/env python3
"""Archived optimizer regressions; require the offline training environment.

Moved unchanged from the broker suite so deployment requires only NumPy and
requests. These synthetic checks are not a new experiment or evaluation and
are not part of the registered fresh evaluation. The episodic design is closed.
"""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location('memory_optimizer', Path(__file__).with_name('replay.py'))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


class Tests(unittest.TestCase):
    def test_01_zero_correction_and_budget(self):
        rows=[]
        for i in range(12):
            v=np.eye(8)[i%8]
            rows.append(dict(y=v,query=v,source='inner',memory={'episodic':np.zeros((3,8))}))
        a=R.fit_text(rows,'episodic',1.,5.)
        np.testing.assert_array_equal(a,np.zeros(3));self.assertLessEqual(a.sum(),.25+1e-8)

    def test_16_useful_memory_fit_is_nonzero_and_constrained(self):
        rows=[]
        for i in range(8):
            v=np.eye(8)[i];m=np.zeros((3,8));m[0]=v
            rows.append(dict(y=v,query=np.zeros(8),source='inner',memory={'episodic':m}))
        a=R.fit_text(rows,'episodic',1.,5.)
        self.assertGreater(a[0],.1);self.assertTrue(np.all(a>=0));self.assertLessEqual(a.sum(),.25000001)

if __name__ == '__main__':
    unittest.main()
