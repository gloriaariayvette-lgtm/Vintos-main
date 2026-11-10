#!/usr/bin/env python3
"""Durable ingress and restart replay, only synthetic scratch and stub transports."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_sink as S
spec=importlib.util.spec_from_file_location('spool_fixture',ROOT/'broker/tests/test_witness_sink.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)

class Tests(unittest.TestCase):
    def setUp(self):
        self.fixture=F.Tests('test_production_destination_is_independent_of_workspace')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.sink=self.fixture.sink
        S._UNKNOWN_SPOOL.clear()
        self.fixture.settings['durable_queue']=True;self.fixture.write_config()
        self.assertIsNone(S._writer)
        self.assertNotIn('.vintos',self.sink.parts)
        self.assertIsInstance(self.fixture.sender,Mock)
        self.start=S.start_recovery
        stub=patch.object(S,'start_recovery',return_value=False)
        self.start_stub=stub.start();self.addCleanup(stub.stop)
        self.addCleanup(self.stop)

    def stop(self):
        if S._writer:
            _,pending,thread=S._writer
            pending.put_nowait(None);thread.join(3)
            self.assertFalse(thread.is_alive());S._writer=None
        S._deferred_pending.clear()

    def entries(self):return list((self.sink/S.SPOOL_NAME).glob('*.packet'))
    def packets(self):return list(self.sink.glob('capture-*.json'))
    def stage(self,value=None):return S.enqueue_capture(self.sink,value or {'synthetic':'private fixture'})

    def test_stage_confirms_private_ingress_and_replays_exact_packet(self):
        value={'synthetic':'original','nested':[1,2]}
        self.assertTrue(self.stage(value));value['nested'].append(3)
        self.assertEqual(self.packets(),[]);self.assertEqual(len(self.entries()),1)
        self.assertEqual((self.sink/S.SPOOL_NAME).stat().st_mode&0o777,0o700)
        self.assertEqual(self.entries()[0].stat().st_mode&0o777,0o600)
        self.assertEqual(S.recover_spool(),1)
        self.assertEqual(self.entries(),[])
        self.assertEqual(json.loads(self.packets()[0].read_text()),{'synthetic':'original','nested':[1,2]})
        S._flush_deferred()
        self.assertEqual(self.fixture.status()['deferred']['counts'],{'spooled':1,'replayed':1})
        self.assertEqual(list(self.fixture.workspace.iterdir()),[])

    def test_v3_capture_cannot_replay_under_launch_prefix(self):
        self.assertTrue(self.stage())
        path,=self.entries();original=path.read_bytes();line,body=original.split(b'\n',1)
        header=json.loads(line);self.assertEqual(header['schema'],'judges-ingress-v3')
        header['prefix']='self-forecast-launch-'
        path.write_bytes(json.dumps(header).encode()+b'\n'+body)
        self.assertEqual(S.recover_spool(),0)
        self.assertTrue(path.exists());self.assertEqual(self.packets(),[])
        self.assertEqual(list(self.sink.glob('self-forecast-launch-*.json')),[])
        path.write_bytes(original);self.assertEqual(S.recover_spool(),1)
        self.assertEqual(len(self.packets()),1)

    def test_startup_recovery_precedes_first_queue_wait(self):
        self.assertTrue(self.stage())
        owner=self
        class Queue:
            def get(self,timeout):
                owner.assertEqual(len(owner.packets()),1)
                owner.assertEqual(owner.entries(),[])
                return None
            def task_done(self):pass
        S._write_queued(Queue())

    def test_busy_queue_cannot_starve_bounded_durable_recovery(self):
        with patch.object(S.time,'monotonic',return_value=100.0):
            for i in range(9):self.assertTrue(self.stage({'synthetic':i}))
        owner=self;clock=[100.0];gets=[]
        class Queue:
            def get(self,timeout):
                gets.append(1)
                if len(gets)==1:
                    owner.assertEqual(len(owner.entries()),1)
                    clock[0]+=.3
                    return owner.sink,b'{"synthetic":"volatile"}', 'capture-',S.configuration()
                owner.assertEqual(owner.entries(),[])
                owner.assertEqual(len(owner.packets()),10)
                return None
            def task_done(self):pass
            def empty(self):return False
        with patch.object(S.time,'monotonic',side_effect=lambda:clock[0]):S._write_queued(Queue())

    def test_configuration_failure_does_not_kill_writer_or_drop_ingress(self):
        with patch.object(S.time,'monotonic',return_value=100.0):self.assertTrue(self.stage())
        configuration=S.configuration
        failures=[True]; clock=[100.0]; owner=self
        def config(*args,**kwargs):
            if failures[0]: raise ValueError('synthetic configuration read failure')
            return configuration(*args,**kwargs)
        class Queue:
            def get(self,timeout):
                if failures[0]:
                    owner.assertEqual(S.COUNTERS['spool_replay_unconfirmed'],1)
                    owner.assertEqual(len(owner.entries()),1)
                    failures[0]=False;clock[0]+=.3
                    return owner.sink,b'{"synthetic":"volatile"}','capture-',configuration()
                owner.assertEqual(owner.entries(),[])
                owner.assertEqual(len(owner.packets()),2)
                return None
            def task_done(self): pass
            def empty(self): return False
        with patch.object(S,'configuration',side_effect=config), patch.object(S.time,'monotonic',side_effect=lambda:clock[0]):
            S._write_queued(Queue())
        self.assertEqual(S.COUNTERS['spool_replayed'],1)
        self.assertEqual(S.COUNTERS['deferred_written'],1)

    def test_new_process_recovers_on_startup_without_a_new_capture(self):
        code="import os,sys;sys.path.insert(0,sys.argv[1]);import witness_sink as s;s.start_recovery=lambda:False;assert s.enqueue_capture(sys.argv[2],{'synthetic':'restart'});os._exit(0)"
        result=subprocess.run([sys.executable,'-c',code,str(ROOT/'scripts'),str(self.sink)],capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(len(self.entries()),1)
        code="""import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import witness_sink as s
assert s.start_recovery()
for _ in range(100):
 if list(Path(sys.argv[2]).glob('capture-*.json')) and not list((Path(sys.argv[2])/s.SPOOL_NAME).glob('*.packet')):break
 time.sleep(.02)
else:raise AssertionError('recovery timeout')
assert len(list(Path(sys.argv[2]).glob('capture-*.json')))==1
"""
        result=subprocess.run([sys.executable,'-c',code,str(ROOT/'scripts'),str(self.sink)],capture_output=True,text=True,timeout=4)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(self.packets()[0].read_text()),{'synthetic':'restart'})

    def test_failure_after_publication_before_ack_retries_without_duplicate(self):
        self.assertTrue(self.stage())
        original=S.os.unlink
        def failed(name,*a,**k):
            if name.endswith('.packet'):raise OSError('synthetic ack failure')
            return original(name,*a,**k)
        with patch.object(S.os,'unlink',side_effect=failed):self.assertEqual(S.recover_spool(),0)
        self.assertEqual(len(self.entries()),1);self.assertEqual(len(self.packets()),1)
        self.assertEqual(S.recover_spool(),1)
        self.assertEqual(self.entries(),[]);self.assertEqual(len(self.packets()),1)
        self.assertEqual(self.fixture.status()['counts']['written'],1)

    def test_process_exit_after_publication_recovers_same_final_file(self):
        self.assertTrue(self.stage())
        code="""import os,sys
sys.path.insert(0,sys.argv[1]);import witness_sink as s
publish=s._publish_bytes
def stop_after_publish(*a,**k):
 result=publish(*a,**k)
 if result:os._exit(23)
 return result
s._publish_bytes=stop_after_publish
s.recover_spool()
raise AssertionError('expected process exit')
"""
        result=subprocess.run([sys.executable,'-c',code,str(ROOT/'scripts')],capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,23,result.stderr)
        self.assertEqual(len(self.entries()),1);self.assertEqual(len(self.packets()),1)
        before=self.packets()[0];body=before.read_bytes()
        self.assertEqual(S.recover_spool(),1)
        self.assertEqual(self.packets(),[before]);self.assertEqual(before.read_bytes(),body)
        self.assertEqual(self.entries(),[])
        self.assertEqual(self.fixture.status()['counts']['written'],1)

    def test_stage_sync_failure_is_unconfirmed_but_committed_record_can_recover(self):
        original=S._atomic
        def failed(*a,**k):
            original(*a,**k)
            raise OSError('synthetic failure after ingress link')
        with patch.object(S,'_atomic',side_effect=failed):self.assertFalse(self.stage())
        self.assertEqual(len(self.entries()),1)
        self.assertEqual(S.recover_spool(),1)
        self.assertEqual(S.COUNTERS['spool_staged'],0)

    def test_crashed_atomic_link_pair_counts_disk_bytes_once(self):
        self.assertTrue(self.stage());entry=self.entries()[0]
        pending=entry.parent/('.pending-'+'a'*32)
        os.link(entry,pending)
        with patch.object(S,'SPOOL_BYTES',S.RESERVE+entry.stat().st_size+1):
            self.assertEqual(S.recover_spool(),1)
        self.assertEqual(len(self.packets()),1)
        self.assertTrue(pending.exists())  # Uncommitted names are never replayed.

    def test_disable_and_changed_config_hold_ingress_without_replay(self):
        self.assertTrue(self.stage());entry=self.entries()[0];before=entry.read_bytes()
        for key,value in (('enabled',False),('durable_queue',False),('max_files',99)):
            old=self.fixture.settings[key];self.fixture.settings[key]=value;self.fixture.write_config()
            self.assertEqual(S.recover_spool(),0)
            self.assertEqual(entry.read_bytes(),before);self.assertEqual(self.packets(),[])
            self.fixture.settings[key]=old;self.fixture.write_config()
        self.assertEqual(S.recover_spool(),1)

    def test_retarget_never_moves_original_records_to_new_destination(self):
        self.assertTrue(self.stage());other=self.fixture.root/'other';other.mkdir(mode=0o700)
        self.fixture.settings['directory']=str(other);self.fixture.write_config()
        self.assertEqual(S.recover_spool(),0);self.assertEqual(list(other.iterdir()),[])
        self.assertEqual(len(self.entries()),1)

    def test_original_age_expires_and_future_clock_is_held(self):
        with patch.object(S.time,'time',return_value=100):self.assertTrue(self.stage())
        entry=self.entries()[0];head,body=entry.read_bytes().split(b'\n',1)
        header=json.loads(head);header['schema']='judges-ingress-v1';header.pop('clock');header.pop('prefix')
        entry.write_bytes(json.dumps(header).encode()+b'\n'+body)
        with patch.object(S.time,'time',return_value=99):self.assertEqual(S.recover_spool(),0)
        self.assertEqual(len(self.entries()),1)
        with patch.object(S.time,'time',return_value=101+S.RETENTION):self.assertEqual(S.recover_spool(),0)
        self.assertEqual(self.entries(),[]);self.assertEqual(self.packets(),[])
        self.assertEqual(S.COUNTERS['spool_expired'],1)

    def test_replay_retains_original_file_age_including_after_link_crash(self):
        created=time.time()-100
        with patch.object(S.time,'time',return_value=created):self.assertTrue(self.stage())
        original=S._atomic
        def fail_after_link(directory,name,payload,replace=False):
            original(directory,name,payload,replace)
            if name.startswith('capture-'):raise OSError('synthetic stop before age applied')
        with patch.object(S,'_atomic',side_effect=fail_after_link):self.assertEqual(S.recover_spool(),0)
        self.assertEqual(len(self.entries()),1)
        self.assertEqual(S.recover_spool(),1)
        self.assertAlmostEqual(self.packets()[0].stat().st_mtime,created,places=4)

    def test_changed_retention_holds_old_records_and_nonfinite_clock_is_inert(self):
        created=time.time()-100
        with patch.object(S.time,'time',return_value=created):self.assertTrue(self.stage())
        self.fixture.settings['retention_seconds']=1;self.fixture.write_config()
        self.assertEqual(S.recover_spool(),0);self.assertEqual(len(self.entries()),1)
        self.fixture.settings['retention_seconds']=S.RETENTION;self.fixture.write_config()
        for clock in (float('nan'),float('inf'),-1):
            with patch.object(S.time,'time',return_value=clock):self.assertEqual(S.recover_spool(),0)
        self.assertEqual(len(self.entries()),1);self.assertEqual(self.packets(),[])

    def test_existing_store_without_reserved_headroom_refuses_new_ingress(self):
        self.fixture.settings['max_bytes']=S.SPOOL_BYTES+S.RESERVE+100;self.fixture.write_config()
        # Synthetic files model a store filled before durable mode was selected.
        for n in range(8):
            p=self.sink/('capture-'+('%032x'%n)+'.json');p.write_bytes(b'x'*S.MAX_PACKET);p.chmod(0o600)
        self.assertFalse(self.stage());self.assertEqual(self.entries(),[])

    def test_publication_reserves_spool_budget_and_header_corruption_is_held(self):
        self.fixture.settings['max_bytes']=S.SPOOL_BYTES+S.RESERVE+100;self.fixture.write_config()
        self.assertFalse(S._publish_bytes(self.sink,b'x'*101,'capture-'))
        self.assertTrue(self.stage())
        entry=self.entries()[0];raw=entry.read_bytes();entry.write_bytes(raw.replace(b'private fixture',b'changed fixture'))
        self.assertEqual(S.recover_spool(),0);self.assertEqual(self.packets(),[])
        self.assertEqual(len(self.entries()),1)

    def test_slot_cap_and_replay_batch_limit(self):
        for n in range(S.SPOOL_FILES):self.assertTrue(self.stage({'synthetic':n}))
        self.assertFalse(self.stage());self.assertEqual(len(self.entries()),64)
        self.assertEqual(S.recover_spool(limit=3),3);self.assertEqual(len(self.entries()),61)
        self.assertTrue(self.stage());self.assertEqual(len(self.entries()),62)
        self.assertEqual(S.COUNTERS['spool_full'],1)

    def test_thirty_durable_packets_recover_after_ingress_without_worker(self):
        for n in range(30):self.assertTrue(self.stage({'n':n,'synthetic':'x'*24000}))
        self.assertEqual(len(self.entries()),30);self.assertEqual(self.packets(),[])
        self.assertEqual(S.recover_spool(limit=64),30)
        self.assertEqual(sorted(json.loads(p.read_text())['n'] for p in self.packets()),list(range(30)))
        self.assertEqual(self.entries(),[])

    def test_busy_ingress_lock_refuses_without_blocking_or_eviction(self):
        self.assertTrue(self.stage())
        c=S.configuration()
        with S._spool_lock(c):
            self.assertFalse(self.stage());self.assertEqual(S.recover_spool(),0)
        self.assertEqual(len(self.entries()),1);self.assertEqual(S.recover_spool(),1)

    def test_backward_step_recovers_same_process_ingress_with_original_timestamp(self):
        for n in range(50):
            with patch.object(S.time,'time',return_value=100),patch.object(S.time,'monotonic',return_value=10):
                self.assertTrue(self.stage({'synthetic':n}))
            with patch.object(S.time,'time',return_value=97.2),patch.object(S.time,'monotonic',return_value=10.1):
                self.assertEqual(S.recover_spool(),1)
        self.assertEqual(len(self.packets()),50);self.assertEqual(self.entries(),[])
        self.assertTrue(all(p.stat().st_mtime==100 for p in self.packets()))

    def test_same_domain_expiry_uses_monotonic_even_when_wall_is_behind(self):
        with patch.object(S.time,'time',return_value=100),patch.object(S.time,'monotonic',return_value=10):self.assertTrue(self.stage())
        with patch.object(S.time,'time',return_value=97.2),patch.object(S.time,'monotonic',return_value=11+S.RETENTION):
            self.assertEqual(S.recover_spool(),0)
        self.assertEqual(self.entries(),[]);self.assertEqual(self.packets(),[])
        self.assertEqual(S.COUNTERS['spool_expired'],1)

    def test_foreign_domain_unknown_order_is_bounded_and_retry_can_recover(self):
        with patch.object(S.time,'time',return_value=100):self.assertTrue(self.stage())
        original=self.entries()[0].read_bytes()
        with patch.object(S,'_spool_domain',return_value='0'*32+':1'),patch.object(S.time,'time',return_value=97.2):
            for _ in range(30):self.assertEqual(S.recover_spool(),0)
        self.assertEqual(S.COUNTERS['spool_unknown_order_retry'],S.UNKNOWN_ORDER_RETRIES)
        self.assertEqual(S.COUNTERS['spool_unknown_order_held'],1)
        self.assertEqual(self.entries()[0].read_bytes(),original);self.assertEqual(self.packets(),[])
        with patch.object(S,'_spool_domain',return_value='0'*32+':1'),patch.object(S.time,'time',return_value=100):
            self.assertEqual(S.recover_spool(),1)
        self.assertFalse(S._UNKNOWN_SPOOL)

    def test_invalid_same_domain_interval_never_falls_back_to_wall(self):
        with patch.object(S.time,'monotonic',return_value=100):self.assertTrue(self.stage())
        for mono in (99,float('nan'),float('inf')):
            with patch.object(S.time,'monotonic',return_value=mono):self.assertEqual(S.recover_spool(),0)
        self.assertEqual(len(self.entries()),1)
        with patch.object(S.time,'monotonic',return_value=101):self.assertEqual(S.recover_spool(),1)

    def test_durable_capture_does_not_claim_phone_delivery(self):
        capture=F.W.begin_shadow('synthetic-turn','synthetic-surface',100)
        capture.observe({'status':'valid','text':'synthetic raw','observed_model':'fixture-model','identity_evidence':'response_metadata'})
        capture.select('synthetic raw')
        self.assertTrue(F.W.finish_shadow(capture,'synthetic final',110,defer=True))
        self.assertEqual(S.recover_spool(),1)
        packet=json.loads(self.packets()[0].read_text())
        self.assertEqual(packet['content'],'synthetic final')
        self.assertEqual(packet['witness_receipt']['delivery'],'unknown')
        self.assertEqual(packet['transport'],'handed_to_framework')

    def test_operator_command_preserves_explicit_queue_mode(self):
        for action in ('disable','enable'):
            result=subprocess.run([sys.executable,str(ROOT/'scripts/witness_sink.py'),action,'--config',str(self.fixture.config)],capture_output=True,text=True,timeout=3)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIs(json.loads(self.fixture.config.read_text())['durable_queue'],True)
        self.assertEqual(list(self.sink.iterdir()),[])

    def test_byte_cap_is_independent_of_slots(self):
        with patch.object(S,'SPOOL_BYTES',S.RESERVE+1024):
            self.assertTrue(self.stage({'synthetic':'x'*200}))
            self.assertFalse(self.stage({'synthetic':'x'*800}))
        self.assertEqual(len(self.entries()),1);self.assertEqual(S.COUNTERS['spool_full'],1)

    def test_invalid_records_do_not_starve_later_valid_record(self):
        self.assertTrue(self.stage())
        for n in range(10):
            p=self.sink/S.SPOOL_NAME/(('%032x'%n)+'.packet');p.write_bytes(b'invalid');p.chmod(0o600)
            os.utime(p,(1,1))
        self.assertEqual(S.recover_spool(limit=1),1)
        self.assertEqual(len(self.entries()),10);self.assertEqual(len(self.packets()),1)
        self.assertEqual(S.COUNTERS['spool_invalid'],10)

    def test_unsafe_spool_or_record_refused_without_following_links(self):
        external=self.fixture.root/'external';external.mkdir(mode=0o700)
        (self.sink/S.SPOOL_NAME).symlink_to(external,target_is_directory=True)
        self.assertFalse(self.stage());self.assertEqual(list(external.iterdir()),[])
        (self.sink/S.SPOOL_NAME).unlink()
        self.assertTrue(self.stage());entry=self.entries()[0];entry.chmod(0o644)
        self.assertEqual(S.recover_spool(),0);self.assertFalse(self.stage())
        self.assertEqual(self.packets(),[])

    def test_sink_capacity_failure_keeps_durable_record(self):
        self.fixture.settings['max_files']=1;self.fixture.write_config()
        self.assertTrue(self.stage({'synthetic':1}));self.assertEqual(S.recover_spool(),1)
        self.assertTrue(self.stage({'synthetic':2}));self.assertEqual(S.recover_spool(),0)
        self.assertEqual(len(self.entries()),1);self.assertEqual(len(self.packets()),1)

    def test_worker_start_failure_does_not_undo_durable_ack(self):
        with patch.object(S,'start_recovery',self.start),patch.object(S.threading.Thread,'start',side_effect=RuntimeError('synthetic thread failure')):
            self.assertTrue(self.stage())
        self.assertIsNone(S._writer);self.assertEqual(len(self.entries()),1)
        self.assertEqual(S.recover_spool(),1)

    def test_actual_server_startup_hook_is_fail_open_and_scoped(self):
        tree=ast.parse((ROOT/'bin/server.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='start_judges_capture_recovery')
        fn=copy.deepcopy(fn);fn.decorator_list=[]
        ns={'os':os,'WORKSPACE':str(self.fixture.workspace)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'startup-fixture','exec'),ns)
        import asyncio
        asyncio.run(ns[fn.name]());self.start_stub.assert_called_once()
        self.start_stub.side_effect=RuntimeError('synthetic startup failure')
        asyncio.run(ns[fn.name]())
        self.assertEqual(list(self.fixture.workspace.iterdir()),[])

    def test_mode_validation_and_disabled_startup_are_inert(self):
        for value in (1,'true',None,[],{}):
            self.fixture.settings['durable_queue']=value;self.fixture.write_config()
            self.assertIsNone(S.configuration());self.assertFalse(self.start())
        self.fixture.settings['durable_queue']=True;self.fixture.settings['enabled']=False;self.fixture.write_config()
        self.assertFalse(self.start());self.assertIsNone(S._writer);self.assertEqual(list(self.sink.iterdir()),[])

if __name__=='__main__':unittest.main()
