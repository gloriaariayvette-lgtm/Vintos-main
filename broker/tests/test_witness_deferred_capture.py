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
        with patch.object(S,'_publish_bytes',side_effect=[OSError('synthetic disk error'),True]):
            self.assertTrue(self.submit());self.assertTrue(self.submit());self.wait_done()
        self.assertEqual(S.COUNTERS['deferred_not_confirmed'],1)
        self.assertEqual(S.COUNTERS['deferred_written'],1)
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
