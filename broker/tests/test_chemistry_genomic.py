#!/usr/bin/env python3
"""No network or GPU: check exact Atlas variant and GRCh38 reference binding."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
SCRATCH=tempfile.TemporaryDirectory(prefix='genomic-test-')
os.environ['HOME']=SCRATCH.name;os.environ['SPARK_WORKSPACE']=SCRATCH.name+'/workspace'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_genomic as g
import chemistry_evo2 as evo

class Tests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(evo.RUNS).is_relative_to(SCRATCH.name))
        self.block=patch('socket.socket.connect',side_effect=AssertionError('network forbidden'))
        self.block.start();self.addCleanup(self.block.stop)
        self.v={'chromosome':'chr1','position':1000,'reference_bases':'A','alternate_bases':'C'}
        self.r={'source':'atlas','metadata':{'assembly':'GRCh38'},'receipt_id':'f'*64,'retrieved_at':'fixture',
                'records':{'fixture':{'variants':[self.v], 'quantiles':[[0.99]]}}}
    def fetch(self,url):
        self.assertIn('1:745..1256:1',url);self.assertIn('GRCh38',url)
        return {'id':'chromosome:GRCh38:1:745:1256:1','seq':'A'*512},{}
    def test_exact_observed_variant_and_coordinate_conversion(self):
        p=g.prepare(self.r,fetch=self.fetch)
        self.assertEqual(p['variant_offset'],255)
        self.assertEqual(p['atlas_variant']['alternate_bases'],'C')
        self.assertEqual(g.validate_payload(p),'A'*512)
    def test_assembly_and_allele_mismatch_refused(self):
        for row in ({'id':'chromosome:GRCh37:1:745:1256:1','seq':'A'*512},
                    {'id':'chromosome:GRCh38:1:745:1256:1','seq':'C'*512}):
            with self.assertRaises(ValueError):g.prepare(self.r,fetch=lambda url:(row,{}))
    def test_never_rank_incomparable_raw_scores(self):
        self.r['records']['fixture'].pop('quantiles')
        self.r['records']['fixture']['scores']=[[999]]
        with self.assertRaises(ValueError):g.choose_variant(self.r)
    def test_existing_nonhuman_lane_not_silently_widened(self):
        p=g.prepare(self.r,fetch=self.fetch)
        with self.assertRaises(ValueError):evo._validate_payload(p)
        p['variant_offset']=0
        with self.assertRaises(ValueError):g.validate_payload(p)
    def test_default_does_not_unload_gemma(self):
        with self.assertRaisesRegex(RuntimeError,'not enabled'):g.analyze(self.r)

if __name__=='__main__':unittest.main()
