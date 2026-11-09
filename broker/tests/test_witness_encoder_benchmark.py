#!/usr/bin/env python3
"""Bounded synthetic CPU cost tool, with scratch-only CLI and no external sends."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT/'experiments/judges-witness/benchmark_encoder.py'
spec = importlib.util.spec_from_file_location('encoder_cost_fixture', SCRIPT)
M = importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='encoder-cost-');self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve();os.chmod(self.root,0o700)
        self.sender = Mock(side_effect=AssertionError('external sender forbidden'))
        p=patch.object(socket.socket,'connect',self.sender);p.start();self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertNotIn('.vintos',self.root.parts);self.assertIsInstance(self.sender,Mock)

    def test_contiguous_and_strided_arrays_retain_same_call_contract(self):
        for layout,multiplier in (('contiguous',1),('strided',2)):
            r=M.benchmark(1,8,2,layout)
            self.assertEqual(r['input_kind'],'synthetic_cpu_arrays')
            self.assertEqual(r['logical_parameter_bytes'],1024*1024)
            self.assertEqual(r['allocated_parameter_array_bytes'],multiplier*1024*1024)
            self.assertEqual((r['encode_calls'],r['snapshot_calls']),(6,4))
            for phase in r['timings'].values():
                for metric in phase.values():
                    self.assertGreaterEqual(metric['median'],0)
                    self.assertGreaterEqual(metric['max'],metric['median'])
            encoded=json.dumps(r)
            for private in ('synthetic feature','raw_emb','invocation','parameter_before','synthetic_0'):
                self.assertNotIn(private,encoded)

    def test_invalid_options_rejected_before_allocation(self):
        for args in ((0,8,1,'contiguous'),(513,8,1,'contiguous'),(True,8,1,'contiguous'),
                     (1,3,1,'contiguous'),(1,True,1,'contiguous'),(1,8,11,'contiguous'),
                     (1,8,0,'contiguous'),(1,8,True,'contiguous'),(1,8,1,'unknown')):
            with patch.object(M,'SyntheticEncoder',side_effect=AssertionError('must validate first')):
                with self.assertRaises(ValueError):M.benchmark(*args)

    def test_unavailable_snapshots_are_not_published_as_timings(self):
        with patch.object(M.SyntheticEncoder,'state_dict',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):M.benchmark(1,1,1)

    def cli(self, output, scratch=None):
        root=self.root if scratch is None else scratch
        return subprocess.run([sys.executable,str(SCRIPT),'--scratch',str(root),'--output',str(output),
            '--mib','1','--iterations','1'],env=dict(os.environ,SPARK_WORKSPACE=str(root),
            PYTHONDONTWRITEBYTECODE='1'),text=True,capture_output=True)

    def test_cli_writes_one_private_aggregate_and_refuses_overwrite(self):
        out=self.root/'result'
        result=self.cli(out);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual({p.name for p in out.iterdir()},{'benchmark.json'})
        target=out/'benchmark.json';raw=target.read_bytes()
        data=json.loads(raw)
        self.assertEqual(target.stat().st_mode&0o777,0o600)
        self.assertEqual(out.stat().st_mode&0o777,0o700)
        self.assertEqual(len(data['code_sha256']),5)
        self.assertNotEqual(self.cli(out).returncode,0)
        self.assertEqual(target.read_bytes(),raw)

    def test_cli_guard_blocks_writes_rename_processes_and_network(self):
        source=self.root/'original';source.write_text('synthetic retained marker')
        for index,action in enumerate((
                "(root/'escape').write_text('forbidden')",
                "os.rename(root/'original', root/'renamed')",
                "subprocess.run([sys.executable, '-c', 'pass'])",
                "socket.socket().connect(('127.0.0.1', 1))")):
            code = ("import importlib.util, os, socket, subprocess, sys; from pathlib import Path; "
                    "script, location, action, out = sys.argv[1:]; root=Path(location); "
                    "spec=importlib.util.spec_from_file_location('cost',script); "
                    "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                    "m.benchmark=lambda *args: eval(action); "
                    "sys.argv=[script,'--scratch',location,'--output',out,'--mib','1']; m.main()")
            out=self.root/('guard-'+str(index))
            result=subprocess.run([sys.executable,'-c',code,str(SCRIPT),str(self.root),action,str(out)],
                env=dict(os.environ,SPARK_WORKSPACE=str(self.root),PYTHONDONTWRITEBYTECODE='1'),
                text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('PermissionError',result.stderr)
            self.assertFalse(out.exists())
        self.assertEqual(source.read_text(),'synthetic retained marker')
        self.assertFalse((self.root/'escape').exists());self.assertFalse((self.root/'renamed').exists())

    def test_cli_rejects_outside_symlink_and_live_named_scratch(self):
        self.assertNotEqual(self.cli(self.root.parent/'forbidden-benchmark').returncode,0)
        dest=self.root/'dest';dest.mkdir()
        link=self.root/'link';link.symlink_to(dest,target_is_directory=True)
        self.assertNotEqual(self.cli(link/'output').returncode,0)
        forbidden=self.root/'.vintos';forbidden.mkdir(mode=0o700)
        self.assertNotEqual(self.cli(forbidden/'output',forbidden).returncode,0)
        self.assertFalse((dest/'output').exists());self.assertFalse((forbidden/'output').exists())


if __name__ == '__main__':unittest.main()
