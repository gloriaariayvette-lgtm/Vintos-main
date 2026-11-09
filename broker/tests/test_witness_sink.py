#!/usr/bin/env python3
"""Dedicated sink tested only in disposable private directories; no sends."""
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_sink as S
import witness_capture as W

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='witness-sink-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.sink=self.root/'sink';self.sink.mkdir(mode=0o700)
        self.workspace=self.root/'workspace';self.workspace.mkdir(mode=0o700)
        self.config=self.root/'config.json'
        self.settings=dict(schema='judges-shadow-sink-v1',enabled=True,directory=str(self.sink),
            max_bytes=S.MAX_BYTES,max_files=100,retention_seconds=S.RETENTION,max_packet_bytes=S.MAX_PACKET)
        self.write_config()
        self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        for p in (patch.dict(os.environ,JUDGES_CAPTURE_CONFIG=str(self.config),JUDGES_CAPTURE_SCRATCH='',SPARK_WORKSPACE=str(self.workspace)),
                  patch.object(socket.socket,'connect',self.sender)):
            p.start();self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        S.COUNTERS.clear()
        self.assertNotIn('.vintos',self.sink.parts);self.assertIsInstance(self.sender,Mock)

    def write_config(self):
        self.config.write_text(json.dumps(self.settings));self.config.chmod(0o600)

    def publish(self):return S.publish(self.sink,{'schema':'synthetic-packet','content':'synthetic output'},'capture-')
    def packets(self):return list(self.sink.glob('capture-*.json'))
    def status(self):return json.loads((self.sink/'status.json').read_text())

    def test_unconfigured_disabled_and_malformed_are_inert(self):
        with patch.dict(os.environ,JUDGES_CAPTURE_CONFIG=''):
            self.assertIsNone(W.begin_shadow('synthetic-turn','synthetic-surface',100))
        for enabled in (False,'true',1,None):
            self.settings['enabled']=enabled;self.write_config()
            self.assertIsNone(W.begin_shadow('synthetic-turn','synthetic-surface',100))
            self.assertFalse(self.publish())
        self.config.write_text('{invalid')
        self.assertFalse(self.publish());self.assertEqual(list(self.sink.iterdir()),[])

    def test_production_destination_is_independent_of_workspace(self):
        before=dict(os.environ)
        self.assertTrue(self.publish());self.assertEqual(os.environ,before)
        self.assertEqual(list(self.workspace.iterdir()),[])
        self.assertEqual(len(self.packets()),1)
        self.assertEqual(self.status()['counts']['written'],1)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in self.sink.iterdir()))

    def test_existing_capture_and_off_output_are_unchanged(self):
        capture=W.begin_shadow('synthetic-turn','synthetic-surface',100)
        self.assertIsNotNone(capture)
        capture.observe({'status':'valid','text':'synthetic raw','observed_model':'fixture-model','identity_evidence':'response_metadata'})
        capture.select('synthetic raw')
        self.assertTrue(W.finish_shadow(capture,'synthetic final',110))
        packet=json.loads(self.packets()[0].read_text())
        self.assertEqual(packet['content'],'synthetic final')
        self.assertEqual(packet['witness_receipt']['delivery'],'unknown')
        self.assertEqual(packet['reply_node']['influence'],'unknown')
        self.assertEqual(list(self.workspace.iterdir()),[])

    def test_hot_disable_discards_inflight_capture(self):
        capture=W.begin_shadow('synthetic-turn','synthetic-surface',100)
        self.settings['enabled']=False;self.write_config()
        with self.assertRaises(ValueError):W.finish_shadow(capture,'synthetic final',110)
        self.assertFalse(self.publish());self.assertEqual(self.packets(),[])

    def test_retarget_does_not_publish_old_invocation(self):
        other=self.root/'other';other.mkdir(mode=0o700)
        self.settings['directory']=str(other);self.write_config()
        self.assertFalse(self.publish());self.assertEqual(list(other.iterdir()),[])

    def test_directory_and_config_permissions_and_symlinks_fail_closed(self):
        self.sink.chmod(0o755);self.assertFalse(self.publish());self.sink.chmod(0o700)
        self.config.chmod(0o644);self.assertFalse(self.publish());self.config.chmod(0o600)
        link=self.root/'link';link.symlink_to(self.sink,target_is_directory=True)
        self.settings['directory']=str(link);self.write_config();self.assertFalse(S.publish(link,{},'capture-'))
        self.settings['directory']=str(self.sink);self.write_config()
        configlink=self.root/'config-link';configlink.symlink_to(self.config)
        with patch.dict(os.environ,JUDGES_CAPTURE_CONFIG=str(configlink)):self.assertFalse(self.publish())

    def test_workspace_repo_home_and_live_named_directories_are_rejected(self):
        live=self.root/'.vintos';live.mkdir(mode=0o700)
        for target in (self.workspace,ROOT,Path.home(),self.root,live):
            with self.assertRaises(ValueError):S.private_directory(str(target))

    def test_capacity_skips_instead_of_evicting_current_packets(self):
        self.settings['max_files']=1;self.write_config()
        self.assertTrue(self.publish());first=self.packets()[0].read_bytes()
        self.assertFalse(self.publish());self.assertEqual(self.packets()[0].read_bytes(),first)
        self.assertEqual(self.status()['counts'],{'written':1,'capacity':1,'expired':0})

    def test_byte_cap_and_packet_cap(self):
        self.settings['max_bytes']=S.RESERVE+1;self.write_config()
        self.assertFalse(self.publish());self.assertEqual(self.status()['counts']['capacity'],1)
        self.settings['max_bytes']=S.MAX_BYTES;self.settings['max_packet_bytes']=1;self.write_config()
        self.assertFalse(self.publish());self.assertEqual(S.COUNTERS['oversize'],1)

    def test_retention_only_expires_owned_managed_packets(self):
        self.assertTrue(self.publish());old=self.packets()[0]
        os.utime(old,(time.time()-S.RETENTION-10,)*2)
        self.assertTrue(self.publish());self.assertFalse(old.exists())
        self.assertEqual(len(self.packets()),1);self.assertEqual(self.status()['counts']['expired'],1)

    def test_unmanaged_and_symlink_entries_are_never_removed(self):
        unknown=self.sink/'keep.txt';unknown.write_text('synthetic keep');unknown.chmod(0o600)
        self.assertFalse(self.publish());self.assertEqual(unknown.read_text(),'synthetic keep')
        unknown.unlink()
        external=self.root/'external';external.write_text('synthetic outside')
        link=self.sink/('capture-'+'a'*32+'.json');link.symlink_to(external)
        self.assertFalse(self.publish());self.assertTrue(link.is_symlink())
        self.assertEqual(external.read_text(),'synthetic outside')

    def test_nonblocking_lock_skips_without_altering_service(self):
        lock=self.sink/'.capture.lock';fd=os.open(lock,os.O_RDWR|os.O_CREAT,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertFalse(self.publish());self.assertEqual(S.COUNTERS['busy'],1)
        finally:os.close(fd)
        self.assertEqual(self.packets(),[])

    def test_atomic_failure_cleans_pending_file(self):
        with patch.object(S.os,'link',side_effect=OSError('synthetic failure')):
            self.assertFalse(self.publish())
        self.assertEqual(self.packets(),[]);self.assertEqual(list(self.sink.glob('.pending-*')),[])
        self.assertEqual(S.COUNTERS['write_failure'],1)

    def test_scratch_mode_takes_precedence_and_keeps_original_contract(self):
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH=str(self.workspace)):
            c=W.begin_shadow('synthetic-turn','synthetic-surface',100)
            self.assertTrue(W.finish_shadow(c,'synthetic final',110))
        self.assertEqual(self.packets(),[])
        self.assertEqual(len(list(self.workspace.glob('capture-*.json'))),1)

    def test_real_self_job_uses_dedicated_sink_and_preserves_forecast(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('production_source_fixture',ROOT/'broker/tests/test_witness_source_clocks.py')
        fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        case=fixture.Tests('test_numeric_chat_clock_survives_legacy_naive_format_without_changing_row')
        case.setUp()
        try:
            with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH='',JUDGES_CAPTURE_CONFIG=str(self.config)):
                enabled=case.job()
                self.settings['enabled']=False;self.write_config()
                disabled=case.job()
            self.assertEqual(enabled,disabled)
            self.assertEqual(len(list(self.sink.glob('self-forecast-inputs-*.json'))),1)
            self.assertEqual(len(list(self.sink.glob('self-forecast-clock-*.json'))),1)
            self.assertEqual(case.packets(),[])
        finally:case.doCleanups()

    def test_oversized_or_unknown_packet_is_not_published(self):
        self.assertFalse(S.publish(self.sink,{},'unknown-'))
        self.assertFalse(S.publish(self.sink,{'bad':float('nan')},'capture-'))
        self.assertEqual(self.packets(),[])

    def test_invalid_limits_and_unsafe_status_are_not_accepted(self):
        for key,value in [('max_files',True),('max_bytes',S.MAX_BYTES+1),('retention_seconds',0),('max_packet_bytes',S.MAX_PACKET+1)]:
            old=self.settings[key];self.settings[key]=value;self.write_config()
            self.assertFalse(self.publish());self.settings[key]=old
        self.write_config()
        outside=self.root/'outside-status';outside.write_text('{}');outside.chmod(0o600)
        (self.sink/'status.json').symlink_to(outside)
        self.assertFalse(self.publish());self.assertEqual(self.packets(),[])
        self.assertEqual(outside.read_text(),'{}')

    def test_cross_process_writers_never_exceed_capacity(self):
        self.settings['max_files']=2;self.write_config()
        code="import sys;sys.path.insert(0,sys.argv[1]);import witness_sink as s;from pathlib import Path;s.publish(Path(sys.argv[2]),{'schema':'synthetic-packet'},'capture-')"
        jobs=[subprocess.Popen([sys.executable,'-c',code,str(ROOT/'scripts'),str(self.sink)],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(6)]
        for job in jobs:
            out,err=job.communicate(timeout=10);self.assertEqual(job.returncode,0,err)
        self.assertLessEqual(len(self.packets()),2)
        self.assertGreater(len(self.packets()),0)
        self.assertEqual(self.status()['counts']['written'],len(self.packets()))

    def test_operator_switch_changes_only_prepared_config(self):
        for action in ('disable','enable'):
            proc=subprocess.run([sys.executable,str(ROOT/'scripts/witness_sink.py'),action,'--config',str(self.config)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(json.loads(self.config.read_text())['enabled'],action=='enable')
            self.assertEqual(self.config.stat().st_mode&0o777,0o600)
        self.assertEqual(list(self.sink.iterdir()),[]);self.assertEqual(list(self.workspace.iterdir()),[])

if __name__=='__main__':unittest.main()
