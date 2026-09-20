#!/usr/bin/env python3
"""Actual optional SDK data contract with a fake client; never opens a channel."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRATCH=tempfile.TemporaryDirectory(prefix='atlas-sdk-contract-')
os.environ['HOME']=SCRATCH.name
os.environ['MPLCONFIGDIR']=SCRATCH.name+'/mpl'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import lab_atlas_worker
try:
    from alphagenome.atlas import atlas
    from alphagenome.data import genome
    import anndata
    import numpy as np
    import pandas as pd
    AVAILABLE=True
except ImportError: AVAILABLE=False


@unittest.skipUnless(AVAILABLE,'run with the pinned AlphaGenome venv for the optional SDK contract')
class SDK(unittest.TestCase):
    def test_real_anndata_preserves_variant_tracks_and_quantiles(self):
        self.assertTrue(os.environ['HOME'].startswith(SCRATCH.name))
        matrix=anndata.AnnData(X=np.array([[0.4,np.nan]]),obs=pd.DataFrame({'variant':[genome.Variant('chr1',101,'A','C')]},index=['0']),
                              var=pd.DataFrame({'name':['fixture_track','missing_track']},index=['0','1']),layers={'quantiles':np.array([[0.98,np.nan]])})
        class Client:
            def scorer_metadata(self):return {'fixture':atlas.ScorerMetadata(name='fixture',is_signed=False,track_metadata=matrix.var)}
            def query_interval(self,interval,**kwargs):
                assert interval.start==100 and interval.end==102
                assert kwargs['max_workers']==1 and kwargs['requested_scorers']==['fixture']
                return {'fixture':matrix}
        with patch.object(atlas,'create',return_value=Client()) as create, patch('socket.socket.connect',side_effect=AssertionError('live network forbidden')):
            result=lab_atlas_worker.run({'source':'atlas','assembly':'GRCh38','chromosome':'chr1','start':100,'end':102,'scorers':['fixture']},'fixture-key')
        create.assert_called_once_with('fixture-key',timeout=15)
        self.assertEqual(result['sdk_version'],'0.9.0')
        self.assertEqual(result['scores']['fixture']['quantiles'],[[0.98,None]])
        self.assertIn('101',str(result['scores']['fixture']['obs']))
        self.assertIn('fixture_track',str(result['scores']['fixture']['var']))


if __name__=='__main__':unittest.main()
