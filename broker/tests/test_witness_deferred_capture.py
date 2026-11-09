#!/usr/bin/env python3
"""Final capture queue is bounded, volatile and isolated from serving outcomes."""
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_sink as S
import witness_capture as W
spec=importlib.util.spec_from_file_location('sink_fixture',ROOT/'broker/tests/test_witness_sink.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)

class Tests(unittest.TestCase):
    def setUp(self):
        self.fixture=F.Tests('test_production_destination_is_independent_of_workspace')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.sink=self.fixture.sink
        self.assertIsNone(S._writer)
        self.addCleanup(self.stop_writer)
        self.assertNotIn('.vintos',self.sink.parts)

    def stop_writer(self):
        if S._writer is not None:
            _,pending,thread=S._writer
            self.wait_done()
            pending.put_nowait(None);thread.join(2)
            self.assertFalse(thread.is_alive())
            S._writer=None

    def wait_done(self):
        if S._writer is None:return
        pending=S._writer[1]
        with pending.all_tasks_done:
            self.assertTrue(pending.all_tasks_done.wait_for(lambda:pending.unfinished_tasks==0,timeout=3))

    def submit(self,packet=None):
        return S.enqueue_capture(self.sink,packet or {'content':'synthetic final'})

    def packets(self):return list(self.sink.glob('capture-*.json'))

    def stalled(self):
        entered,release=threading.Event(),threading.Event()
        original=S._publish_bytes
        def write(*args,**kwargs):
            entered.set()
            if not release.wait(3):raise AssertionError('synthetic release missing')
            return original(*args,**kwargs)
        self.addCleanup(release.set)
        return entered,release,patch.object(S,'_publish_bytes',side_effect=write)

    def test_foreground_does_not_wait_for_publication_and_freezes_packet(self):
        entered,release,stub=self.stalled()
        value={'content':'synthetic original','nested':{'n':1}}
        with stub:
            self.assertTrue(self.submit(value));self.assertTrue(entered.wait(1))
            self.assertEqual(self.packets(),[])
            value['nested']['n']=99
            self.assertTrue(S._writer[2].daemon)
            release.set();self.wait_done()
        packet=json.loads(self.packets()[0].read_text())
        self.assertEqual(packet['nested']['n'],1)
        self.assertEqual(S.COUNTERS['deferred_enqueued'],1)
        self.assertEqual(S.COUNTERS['deferred_written'],1)

    def test_queue_capacity_skips_without_wait_or_eviction(self):
        entered,release,stub=self.stalled()
        with stub:
            self.assertTrue(self.submit());self.assertTrue(entered.wait(1))
            for n in range(S.DEFERRED_SLOTS):self.assertTrue(self.submit({'n':n}))
            self.assertFalse(self.submit());self.assertEqual(S._writer[1].qsize(),S.DEFERRED_SLOTS)
            release.set();self.wait_done()
        self.assertEqual(len(self.packets()),S.DEFERRED_SLOTS+1)
        self.assertEqual(S.COUNTERS['deferred_full'],1)
        status=self.fixture.status()['deferred']
        self.assertEqual(status['counts'],{'enqueued':S.DEFERRED_SLOTS+1,'written':S.DEFERRED_SLOTS+1,'full':1})
        self.assertIsNone(status['restart_loss'])
        self.assertIn('lower bounds',status['coverage'])

    def test_thirty_small_packets_survive_a_fully_stalled_writer(self):
        entered,release,stub=self.stalled()
        with stub:
            self.assertTrue(self.submit({'n':0,'content':'x'*24000}));self.assertTrue(entered.wait(1))
            for n in range(1,30):self.assertTrue(self.submit({'n':n,'content':'x'*24000}))
            self.assertEqual(S._writer[1].qsize(),29)
            self.assertEqual(self.packets(),[])
            release.set();self.wait_done()
        self.assertEqual(sorted(json.loads(p.read_text())['n'] for p in self.packets()),list(range(30)))
        self.assertEqual(self.fixture.status()['deferred']['counts'],{'enqueued':30,'written':30})

    def test_byte_budget_refuses_without_eviction_and_releases_after_get(self):
        pending=S.CaptureQueue()
        payload=b'x'*S.MAX_PACKET
        for _ in range(8):pending.put_nowait((self.sink,payload,'capture-',{}))
        with self.assertRaises(queue.Full):pending.put_nowait((self.sink,b'x','capture-',{}))
        self.assertEqual(pending.qsize(),8)
        self.assertEqual(pending.queued_bytes,S.DEFERRED_BYTES)
        self.assertEqual(pending.get_nowait()[1],payload);pending.task_done()
        pending.put_nowait((self.sink,payload,'capture-',{}))
        while not pending.empty():pending.get_nowait();pending.task_done()
        self.assertEqual(pending.queued_bytes,0)
        pending.put_nowait(None);self.assertIsNone(pending.get_nowait());pending.task_done()
        self.assertEqual(pending.queued_bytes,0)

    def test_byte_limit_rejection_uses_full_counter_and_does_not_block_next_packet(self):
        entered,release,stub=self.stalled()
        with patch.object(S,'DEFERRED_BYTES',64),stub:
            self.assertTrue(self.submit({'n':0}));self.assertTrue(entered.wait(1))
            self.assertTrue(self.submit({'content':'x'*30}))
            self.assertFalse(self.submit({'content':'x'*30}))
            self.assertEqual(S._writer[1].qsize(),1)
            release.set();self.wait_done()
        self.assertEqual(S.COUNTERS['deferred_full'],1)
        self.assertTrue(self.submit());self.wait_done()
        self.assertEqual(len(self.packets()),3)

    def test_concurrent_byte_reservations_cannot_exceed_budget(self):
        pending=S.CaptureQueue()
        accepted=[]
        def put():
            try:
                pending.put_nowait((self.sink,b'x'*S.MAX_PACKET,'capture-',{}))
                accepted.append(True)
            except queue.Full:accepted.append(False)
        threads=[threading.Thread(target=put) for _ in range(16)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(1);self.assertFalse(thread.is_alive())
        self.assertEqual(sum(accepted),8)
        self.assertEqual(pending.queued_bytes,S.DEFERRED_BYTES)
        self.assertEqual(pending.qsize(),8)

    def test_hot_disable_drops_queued_packets_without_disk_mutation(self):
        entered,release,stub=self.stalled()
        with stub:
            self.assertTrue(self.submit());self.assertTrue(entered.wait(1));self.assertTrue(self.submit())
            self.fixture.settings['enabled']=False;self.fixture.write_config()
            release.set();self.wait_done()
        self.assertEqual(list(self.sink.iterdir()),[])
        self.assertEqual(S.COUNTERS['deferred_not_confirmed'],2)

    def test_retarget_and_changed_limits_drop_observed_queue(self):
        for change in ('directory','max_files'):
            entered,release,stub=self.stalled()
            with stub:
                self.assertTrue(self.submit());self.assertTrue(entered.wait(1))
                previous=self.fixture.settings[change]
                if change=='directory':
                    other=self.fixture.root/'other';other.mkdir(mode=0o700)
                    self.fixture.settings[change]=str(other)
                else:self.fixture.settings[change]=2
                self.fixture.write_config();release.set();self.wait_done()
            self.fixture.settings[change]=previous;self.fixture.write_config()
        self.assertEqual(list(self.sink.iterdir()),[])
        self.assertEqual(list(other.iterdir()),[])

    def test_diagnostic_disk_write_stays_off_foreground(self):
        entered, release=threading.Event(),threading.Event()
        original=S._publish_bytes
        def stall_status(root,payload,*args,**kwargs):
            if payload is None:
                entered.set()
                if not release.wait(3): raise AssertionError('synthetic release missing')
            return original(root,payload,*args,**kwargs)
        try:
            with patch.object(S,'_publish_bytes',side_effect=stall_status):
                self.assertTrue(self.submit()); self.assertTrue(entered.wait(1))
                self.assertTrue(self.submit())
                release.set(); self.wait_done()
        finally: release.set()
        self.assertEqual(self.fixture.status()['deferred']['counts'],{'enqueued':2,'written':2})

    def test_counters_preserved_by_synchronous_writes_and_process_restart(self):
        self.assertTrue(self.submit());self.wait_done();self.stop_writer()
        self.assertTrue(self.fixture.publish())
        self.assertEqual(self.fixture.status()['deferred']['counts'],{'enqueued':1,'written':1})
        code="import sys;sys.path.insert(0,sys.argv[1]);import witness_sink as s;assert s.enqueue_capture(sys.argv[2],{'synthetic':True});s._writer[1].join()"
        result=subprocess.run([sys.executable,'-c',code,str(ROOT/'scripts'),str(self.sink)],capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.fixture.status()['deferred']['counts'],{'enqueued':2,'written':2})
        self.assertIsNone(self.fixture.status()['deferred']['restart_loss'])

    def test_ambiguous_status_failure_consumes_delta_without_duplicate_retry(self):
        config=S.configuration(self.sink)
        with S._writer_lock:S._note_deferred_locked(config,'full')
        original=S._atomic
        def replaced_then_failed(directory,name,payload,replace=False):
            original(directory,name,payload,replace)
            if name=='status.json':raise OSError('synthetic failure after replacement')
        with patch.object(S,'_atomic',side_effect=replaced_then_failed):S._flush_deferred()
        self.assertEqual(self.fixture.status()['deferred']['counts'],{'full':1})
        self.assertEqual(S.COUNTERS['deferred_diagnostic_unconfirmed'],1)
        S._flush_deferred()
        self.assertEqual(self.fixture.status()['deferred']['counts'],{'full':1})
        self.assertEqual(self.packets(),[])
        self.assertEqual(self.fixture.status()['counts'],{'expired':0})

    def test_diagnostic_scopes_are_bounded_and_fork_reset_discards_them(self):
        config=S.configuration(self.sink)
        for n in range(9):
            with S._writer_lock:S._note_deferred_locked(dict(config,max_files=n+1),'full')
        self.assertEqual(len(S._deferred_pending),8)
        self.assertEqual(S.COUNTERS['deferred_diagnostic_scope_full'],1)
        S._reset_after_fork()
        self.assertFalse(S._deferred_pending);self.assertFalse(S.COUNTERS)
        self.assertEqual(list(self.sink.iterdir()),[])

    def test_disabled_diagnostics_are_not_replayed_after_reenable(self):
        config=S.configuration(self.sink)
        with S._writer_lock:S._note_deferred_locked(config,'full')
        self.fixture.settings['enabled']=False;self.fixture.write_config()
        S._flush_deferred()
        self.assertEqual(list(self.sink.iterdir()),[])
        self.fixture.settings['enabled']=True;self.fixture.write_config()
        self.assertTrue(self.submit());self.wait_done()
        self.assertNotIn('full',self.fixture.status()['deferred']['counts'])

    def test_busy_diagnostic_flush_is_discarded_without_later_double_count(self):
        import fcntl
        config=S.configuration(self.sink)
        with S._writer_lock:S._note_deferred_locked(config,'full')
        fd=os.open(self.sink/'.capture.lock',os.O_RDWR|os.O_CREAT,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            S._flush_deferred()
        finally:os.close(fd)
        self.assertEqual(S.COUNTERS['deferred_diagnostic_unconfirmed'],1)
        self.assertFalse(S._deferred_pending)
        self.assertFalse((self.sink/'status.json').exists())
        self.assertTrue(self.submit());self.wait_done()
        self.assertEqual(self.fixture.status()['deferred']['counts'],{'enqueued':1,'written':1})

    def test_packet_failure_keeps_outcome_unknown_without_claiming_balance(self):
        with patch.object(S.os,'link',side_effect=OSError('synthetic packet failure')):
            self.assertTrue(self.submit());self.wait_done()
        self.assertEqual(self.packets(),[])
        deferred=self.fixture.status()['deferred']
        self.assertEqual(deferred['counts'],{'not_confirmed':1})
        self.assertIsNone(deferred['restart_loss'])
        self.assertIn('not a loss balance',deferred['coverage'])

    def test_invalid_diagnostic_values_and_unsafe_status_are_refused(self):
        for counts in ({'private-sentinel':1},{'full':True},{'full':-1},{'full':10**18}):
            self.assertFalse(S._publish_bytes(self.sink,None,'capture-',diagnostic=counts))
        self.assertEqual(list(self.sink.iterdir()),[])
        external=self.fixture.root/'external';external.write_text('{}');external.chmod(0o600)
        (self.sink/'status.json').symlink_to(external)
        self.assertFalse(S._publish_bytes(self.sink,None,'capture-',diagnostic={'full':1}))
        self.assertEqual(external.read_text(),'{}')

    def test_disabled_invalid_and_oversize_never_start_worker(self):
        for enabled in (False,1,'true'):
            self.fixture.settings['enabled']=enabled;self.fixture.write_config()
            self.assertFalse(self.submit());self.assertIsNone(S._writer)
        self.fixture.settings['enabled']=True;self.fixture.settings['max_packet_bytes']=1;self.fixture.write_config()
        self.assertFalse(self.submit());self.assertIsNone(S._writer)
        self.fixture.settings['max_packet_bytes']=S.MAX_PACKET;self.fixture.write_config()
        self.assertFalse(self.submit({'n':float('nan')}));self.assertIsNone(S._writer)

    def test_writer_exception_does_not_stop_next_packet(self):
        original=S._publish_bytes
        outcomes=iter([OSError('synthetic disk error'),True])
        def synthetic_write(root,payload,*args,**kwargs):
            if payload is None: return True
            result=next(outcomes)
            if isinstance(result,Exception): raise result
            return result
        with patch.object(S,'_publish_bytes',side_effect=synthetic_write):
            self.assertTrue(self.submit());self.assertTrue(self.submit());self.wait_done()
        self.assertEqual(S.COUNTERS['deferred_not_confirmed'],1)
        self.assertEqual(S.COUNTERS['deferred_written'],1)
        self.assertEqual(S._writer[1].queued_bytes,0)
        self.assertEqual(self.packets(),[])
        self.assertTrue(self.submit());self.wait_done();self.assertEqual(len(self.packets()),1)

    def test_worker_start_failure_and_busy_lock_are_fail_open(self):
        with patch.object(S.threading.Thread,'start',side_effect=RuntimeError('synthetic thread error')):
            self.assertFalse(self.submit());self.assertIsNone(S._writer)
        with S._writer_lock:self.assertFalse(self.submit())
        self.assertEqual(S.COUNTERS['deferred_busy'],1)
        self.assertEqual(list(self.sink.iterdir()),[])

    def test_concurrent_submitters_share_one_worker(self):
        entered,release,stub=self.stalled()
        with stub:
            self.assertTrue(self.submit());self.assertTrue(entered.wait(1))
            identity=S._writer
            threads=[threading.Thread(target=self.submit) for _ in range(16)]
            for thread in threads:thread.start()
            for thread in threads:thread.join(1);self.assertFalse(thread.is_alive())
            self.assertIs(S._writer,identity)
            self.assertLessEqual(S._writer[1].qsize(),S.DEFERRED_SLOTS)
            release.set();self.wait_done()
        self.assertLessEqual(len(self.packets()),S.DEFERRED_SLOTS+1)

    def test_final_capture_queue_does_not_claim_delivery(self):
        entered,release,stub=self.stalled()
        with stub:
            c=W.begin_shadow('synthetic-turn','synthetic-surface',100)
            c.observe({'status':'valid','text':'synthetic raw','observed_model':'fixture-model','identity_evidence':'response_metadata'})
            c.select('synthetic raw')
            self.assertTrue(W.finish_shadow(c,'synthetic final',110,defer=True))
            self.assertTrue(entered.wait(1));self.assertEqual(self.packets(),[])
            release.set();self.wait_done()
        packet=json.loads(self.packets()[0].read_text())
        self.assertEqual(packet['content'],'synthetic final')
        self.assertEqual(packet['witness_receipt']['delivery'],'unknown')
        self.assertEqual(packet['transport'],'handed_to_framework')
        self.assertEqual(self.packets()[0].stat().st_mode&0o777,0o600)

    def test_actual_handler_returns_while_writer_is_stalled(self):
        spec=importlib.util.spec_from_file_location('deferred_handler_fixture',ROOT/'broker/tests/test_witness_capture_hooks.py')
        hooks=importlib.util.module_from_spec(spec);spec.loader.exec_module(hooks)
        entered,release,stub=self.stalled()
        with stub:
            result=hooks.Tests().exercise()
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.packets(),[])
            self.assertEqual(result['reply'],'synthetic raw after postprocessing after final guard')
            release.set();self.wait_done()
        packet=json.loads(self.packets()[0].read_text())
        self.assertEqual(packet['content'],result['reply'])
        self.assertEqual(packet['witness_receipt']['delivery'],'unknown')

    def test_disk_capacity_is_not_reported_as_publication(self):
        self.fixture.settings['max_files']=1;self.fixture.write_config()
        self.assertTrue(self.submit());self.wait_done()
        self.assertTrue(self.submit());self.wait_done()
        self.assertEqual(len(self.packets()),1)
        self.assertEqual(S.COUNTERS['deferred_enqueued'],2)
        self.assertEqual(S.COUNTERS['deferred_written'],1)
        self.assertEqual(S.COUNTERS['deferred_not_confirmed'],1)

    def test_scratch_and_other_producers_remain_synchronous(self):
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH=str(self.fixture.workspace)):
            c=W.begin_shadow('synthetic-turn','synthetic-surface',100)
            c.observe({'status':'valid','text':'synthetic raw','observed_model':'fixture-model','identity_evidence':'response_metadata'})
            c.select('synthetic raw')
            self.assertTrue(W.finish_shadow(c,'synthetic final',110,defer=True))
            self.assertEqual(len(list(self.fixture.workspace.glob('capture-*.json'))),1)
            self.assertIsNone(S._writer)
        self.assertTrue(W._publish_private(self.sink,{'synthetic':True},'value-map-call-'))
        self.assertEqual(len(list(self.sink.glob('value-map-call-*.json'))),1)
        self.assertIsNone(S._writer)

    def test_process_exit_does_not_flush_or_wait_for_blocked_worker(self):
        code='''import sys,threading,time
sys.path.insert(0,sys.argv[1])
import witness_sink as S
entered=threading.Event()
def blocked(*a,**k):
 entered.set();threading.Event().wait(30)
S._publish_bytes=blocked
assert S.enqueue_capture(sys.argv[2],{'synthetic':True})
assert entered.wait(1)
print('queued_only',flush=True)
'''
        result=subprocess.run([sys.executable,'-c',code,str(ROOT/'scripts'),str(self.sink)],capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'queued_only')
        self.assertEqual(list(self.sink.iterdir()),[])

    @unittest.skipUnless(hasattr(os,'fork'),'requires fork')
    def test_fork_child_discards_parent_queue_and_lock(self):
        code='''import os,sys,threading,time
sys.path.insert(0,sys.argv[1])
import witness_sink as S
entered=threading.Event()
original=S._publish_bytes
def blocked(*a,**k):
 entered.set();threading.Event().wait(30)
S._publish_bytes=blocked
assert S.enqueue_capture(sys.argv[2],{'synthetic':'parent'})
assert entered.wait(1)
S._writer_lock.acquire()
pid=os.fork()
if pid==0:
 try:
  assert S._writer is None
  assert not S.COUNTERS
  S._publish_bytes=original
  assert S.enqueue_capture(sys.argv[2],{'synthetic':'child'})
  S._writer[1].join()
  os._exit(0)
 except BaseException:os._exit(1)
else:
 S._writer_lock.release()
 _,status=os.waitpid(pid,0)
 assert os.waitstatus_to_exitcode(status)==0
'''
        result=subprocess.run([sys.executable,'-c',code,str(ROOT/'scripts'),str(self.sink)],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(self.packets()),1)
        self.assertEqual(json.loads(self.packets()[0].read_text()),{'synthetic':'child'})

if __name__=='__main__':unittest.main()
