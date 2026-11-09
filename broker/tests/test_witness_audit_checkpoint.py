#!/usr/bin/env python3
"""Self-audit checkpoint file races, synthetic files and stubbed send/encode paths."""
import hashlib
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
import test_witness_self_artifacts as F

R=F.R


class Tests(unittest.TestCase):
    def setUp(self):
        self.case=F.Tests('test_load_hashes_the_same_checkpoint_bytes_it_parses')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.path=self.case.path;self.raw=self.path.read_bytes()
        self.ck=hashlib.sha256(self.raw).hexdigest()
        os.utime(self.path,(30,30))
        self.seen=[];self.output=[]
        self.assertNotIn('.vintos',self.path.parts)
        self.assertIsInstance(self.case.case.enc.encode,Mock)
        self.assertIsInstance(self.case.case.sender,Mock)
        def evaluate(rows,ledger,enc,**kwargs):
            self.seen.append(kwargs)
            return [{'synthetic_score':1}]
        self.ra=types.SimpleNamespace(MEM=str(self.case.case.memory),realized_ledger=lambda:[],
            _jsonl=lambda p:[],evaluate=evaluate,_summary=lambda rows,head:rows,
            _atomic=lambda p,v:self.output.append(v))
        p=patch.dict(sys.modules,jepa_ranking_audit=self.ra);p.start();self.addCleanup(p.stop)

    def run_audit(self):return R.audit(self.case.case.enc,self.case.case.memory)

    def change_after_hash(self,remove=False):
        original=hashlib.sha256;changed=[]
        def hash_bytes(value):
            result=original(value)
            if value==self.raw and not changed:
                changed.append(True)
                if remove:self.path.unlink()
                else:
                    replacement=self.path.with_name('replacement.npz')
                    replacement.write_bytes(b'synthetic different checkpoint')
                    os.utime(replacement,(600,600));os.replace(replacement,self.path)
            return result
        return patch.object(R.hashlib,'sha256',side_effect=hash_bytes)

    def test_self_audit_cannot_pair_old_bytes_with_replacement_mtime(self):
        for capture in (False,True):
            self.path.write_bytes(self.raw);os.utime(self.path,(30,30))
            with patch.dict(os.environ,JUDGES_CAPTURE_CONFIG='',JUDGES_CAPTURE_SCRATCH=str(self.case.root) if capture else ''):
                with self.change_after_hash():result=self.run_audit()
            self.assertEqual(result['self_on_message']['checkpoint'],self.ck)
            self.assertEqual(self.seen[-1],{'checkpoint':self.ck,'trained_before':30.})
            self.assertEqual(self.path.stat().st_mtime,600.)
        self.case.case.enc.encode.assert_not_called()

    def test_deletion_after_self_snapshot_needs_no_late_stat(self):
        with self.change_after_hash(remove=True):result=self.run_audit()
        self.assertEqual(result['self_on_message']['checkpoint'],self.ck)
        self.assertEqual(self.seen[0]['trained_before'],30.)
        self.assertEqual(len(self.output),1)

    def test_static_capture_off_on_audits_match(self):
        with patch.dict(os.environ,JUDGES_CAPTURE_CONFIG='',JUDGES_CAPTURE_SCRATCH=''):
            off=self.run_audit()
        on=self.run_audit()
        self.assertEqual(off,on)
        self.assertEqual(self.seen,[{'checkpoint':self.ck,'trained_before':30.}]*2)
        self.case.case.enc.encode.assert_not_called()

    def test_changed_open_file_is_refused_before_scoring_or_report_write(self):
        original=os.fstat
        for field in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'):
            calls=[]
            def changed(fd):
                value=original(fd);calls.append(None)
                if len(calls)==2:
                    keys=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mtime','st_mode')
                    value=types.SimpleNamespace(**{k:getattr(value,k) for k in keys})
                    setattr(value,field,getattr(value,field)+1)
                return value
            with self.subTest(field=field),patch.object(R.os,'fstat',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'changed during read'):self.run_audit()
            self.assertEqual(self.seen,[]);self.assertEqual(self.output,[])
        self.case.case.enc.encode.assert_not_called()

    def test_short_read_and_nonregular_observation_are_refused(self):
        original=os.fstat
        for kind in ('size','type'):
            def invalid(fd):
                value=original(fd)
                keys=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mtime','st_mode')
                value=types.SimpleNamespace(**{k:getattr(value,k) for k in keys})
                if kind=='size':value.st_size+=1
                else:value.st_mode=0
                return value
            with patch.object(R.os,'fstat',side_effect=invalid):
                with self.assertRaises(ValueError):self.run_audit()
            self.assertEqual(self.seen,[]);self.assertEqual(self.output,[])

    def test_other_head_keeps_its_existing_path(self):
        other=self.path.with_name('gloria.npz')
        self.path.rename(other);self.path=other
        with self.change_after_hash():self.run_audit()
        self.assertEqual(self.seen[0]['trained_before'],600.)


if __name__=='__main__':unittest.main()
