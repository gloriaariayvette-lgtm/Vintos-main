"""Isolated boundary regressions; no real providers, filesystem stores or sends."""
import os,sys,socket,tempfile,json,copy,unittest,multiprocessing
from pathlib import Path
from unittest.mock import patch
scratch=tempfile.TemporaryDirectory()
os.environ.update(HOME=scratch.name,SPARK_WORKSPACE=scratch.name+'/workspace')
def forbidden(*a,**kw):raise AssertionError('network forbidden')
socket.socket.connect=forbidden;socket.create_connection=forbidden
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),'/home/gloria/Vintos-main/scripts']
import awaiting_evidence as E,evidence_delivery as D,room_work as R,email_commitments as M
assert str(E.store().path).startswith(scratch.name) and M.STORE.startswith(scratch.name)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=scratch.name);self.addCleanup(self.tmp.cleanup)
  self.store=E.Store(Path(self.tmp.name)/'ledger.json',self.tmp.name)
  p=patch.object(E,'store',return_value=self.store);p.start();self.addCleanup(p.stop)
  self.now=100000.;self.w={'id':'RW-01234567','goal':'ModelJSONError '+'a'*32,'goal_id':'RC-11111111','opened':self.now,'by':'owner','asks':[],'returns':[],'steps':[]}
  self.st={'room_work':{'open':[self.w],'history':[],'goal':{'id':'RC-11111111','goal':'investigate diagnostics','opened':self.now,'routes':[]}}};self.calls=[]
 def enter(self):return R.apply(self.st,'AWAIT EVIDENCE RW-01234567: original diagnostic is unavailable',self.now)[0]
 def send(self,text,now=None,owner=None):return D.send(lambda m,p:self.calls.append(p) or {'ts':'1'},{'channel':'C','text':text},now or self.now,lambda:False,owner)
 def auth(self,text,ts='1',**extra):
  m={'user':'OWNER','ts':ts,'text':text};m.update(extra);return D.authenticate(m,'OWNER','C',self.now)
 def artifact(self,raw=True,events=True):
  targets=self.store._targets(self.w);Path(targets[0]).parent.mkdir(parents=True,exist_ok=True)
  if raw:Path(targets[0]).write_text('original diagnostic response bytes')
  if events:Path(targets[1]).write_text(json.dumps({'evidence_id':'a'*32,'events':['captured']}))
  return targets
 def collect(self,now):return R.evidence_recheck(self.st,now,lambda text:self.send(text,now),lambda:False)
 def test_repeated_await_metered(self):
  self.send(self.enter());self.send(self.enter(),self.now+1);self.assertEqual(len(self.calls),1)
 def test_initial_statement_does_not_claim_unchanged(self):
  self.send(self.enter());self.assertNotIn('No change',self.calls[-1]['text'])
 def test_unchanged_after_actual_daily_check(self):
  self.send(self.enter());self.collect(self.now+E.DAY);self.assertIn('No change in the tracked local diagnostic files.',self.calls[-1]['text'])
 def test_mixed_unstructured_same_sentence_preserved(self):
  self.send(self.enter());text='RW-01234567 still lacks evidence, while independent calibration B passed.';self.send(text,self.now+1);self.assertEqual(self.calls[-1]['text'],text)
 def test_precisely_attributed_same_sentence_keeps_independent_span(self):
  self.send(self.enter());text=D.attribute('Still nothing came back.',self.w['id'])+', while independent calibration B passed.';self.send(text,self.now+1);self.assertEqual(self.calls[-1]['text'],', while independent calibration B passed.')
 def test_paraphrase_without_id_keeps_producer_attribution(self):
  self.send(self.enter())
  for text in ('Nothing new here.','Still waiting for original bytes.','The response remains missing.'):
   self.send(D.attribute(text,self.w['id']),self.now+1)
  self.assertEqual(len(self.calls),1)
 def test_work_status_producer_preserves_attribution(self):
  self.send(self.enter());text,_,_=R.apply(self.st,'WORK STATUS RW-01234567: Still no response.\nIndependent B passed.',self.now+1);self.send(text,self.now+1)
  self.assertEqual(self.calls[-1]['text'],'Independent B passed.')
 def test_marker_inside_mixed_line_preserves_surroundings(self):
  self.send(self.enter());self.send('before '+D.marker(self.w['id'])+' after',self.now+1);self.assertEqual(self.calls[-1]['text'],'before  after')
 def test_closure_and_repeat_work_share_same_reservation(self):
  self.send(self.enter())
  for text in ('WORK DROPPED RW-01234567: original evidence is unavailable','WORK: ModelJSONError '+'a'*32+' | done when: original bytes available'):
   self.send(R.apply(self.st,text,self.now+1)[0],self.now+1)
  self.assertEqual(len(self.calls),1)
 def test_email_closure_metered(self):
  self.send(self.enter());rows=[{'id':'EC-aabbccdd','state':'in work','work_id':self.w['id']}]
  with patch.object(M,'_load',return_value=rows),patch.object(M,'_save',side_effect=forbidden):text,_=M.close_lines('PROMISE DROPPED EC-aabbccdd: no response evidence exists',proved=lambda x:True)
  self.send(text,self.now+1);self.assertEqual(len(self.calls),1)
 def test_linked_waiting_promise_survives_ledger_failure(self):
  self.enter();self.store.path.write_text('{broken');rows=[{'id':'EC-aabbccdd','state':'in work','work_id':self.w['id']}]
  with patch.object(M,'_load',return_value=rows),patch.object(M,'_save',side_effect=forbidden):
   text,log=M.close_lines('PROMISE DROPPED EC-aabbccdd: no evidence exists',proved=lambda x:True,waiting_work_ids={self.w['id']})
  self.assertEqual(text,D.marker(self.w['id']));self.assertEqual(log,[])
 def test_generic_unrelated_status_cannot_unlock_waits(self):
  self.enter();self.assertIsNone(self.auth('What is the status of independent calibration?'))
 def test_explicit_all_waiting_status(self):
  self.enter();self.assertEqual(self.auth('What is the status of all waiting items?')['scope'],[self.w['id']])
 def test_ambiguous_all_waiting_status_does_not_broaden(self):
  self.enter();self.assertIsNone(self.auth('Do not show the status of all waiting items?'))
  self.assertIsNone(self.auth('What is the status of all waiting items except the Lab task?'))
 def test_explicit_item_scope(self):
  self.enter();self.assertEqual(self.auth('Status RW-01234567?')['scope'],[self.w['id']])
 def test_owner_status_moves_autonomous_window(self):
  self.send(self.enter());req=self.auth('Status RW-01234567?');at=self.now+100
  self.send(D.marker(self.w['id']),at,req);self.assertEqual(len(self.calls),2)
  self.assertEqual(self.store.read()[self.w['id']]['next_send'],at+E.DAY)
  self.send(D.marker(self.w['id']),self.now+E.DAY);self.assertEqual(len(self.calls),2)
 def test_owner_request_single_use(self):
  self.send(self.enter());req=self.auth('Status RW-01234567?');self.send(D.marker(self.w['id']),self.now+1,req);self.send(D.marker(self.w['id']),self.now+2,req);self.assertEqual(len(self.calls),2)
 def test_wrong_owner_destination_no_unlock(self):
  self.send(self.enter());req=self.auth('Status RW-01234567?',thread_ts='T');self.send(D.marker(self.w['id']),self.now+1,req);self.assertEqual(len(self.calls),1)
 def test_owner_quotes_and_spoofs_rejected(self):
  self.enter()
  for kw in ({'user':'AGENT'},{'bot_id':'bot'},{'subtype':'bot_message'}):self.assertIsNone(self.auth('!cancelwork RW-01234567',**kw))
  self.assertIsNone(self.auth('> !cancelwork RW-01234567'));req=self.auth('Status RW-01234567?');req['kind']='cancel';self.assertFalse(self.store.owner(req,'cancel',self.now))
 def test_raw_then_events_enables_inspection(self):
  self.enter();self.artifact(events=False);self.collect(self.now+E.DAY);self.assertTrue(R.evidence_waiting(self.w))
  self.artifact(raw=False);self.collect(self.now+2*E.DAY);item=self.store.read()[self.w['id']]
  self.assertEqual(item['status'],'actionable');self.assertEqual(item['next_action'],'inspect_saved_diagnostic');self.assertFalse(R.evidence_waiting(self.w))
 def test_events_then_raw_enables_inspection(self):
  self.enter();self.artifact(raw=False);self.collect(self.now+E.DAY);self.artifact(events=False);self.collect(self.now+2*E.DAY);self.assertEqual(self.store.read()[self.w['id']]['status'],'actionable')
 def test_raw_already_present_at_entry_then_events(self):
  self.artifact(events=False);self.enter();self.artifact(raw=False);self.collect(self.now+E.DAY)
  item=self.store.read()[self.w['id']];self.assertEqual(len(item['baseline']),1);self.assertEqual(item['status'],'actionable')
 def test_complete_existing_files_at_entry(self):
  self.artifact();self.enter();item=self.store.read()[self.w['id']];self.assertEqual(item['status'],'actionable');self.assertEqual(item['history'][0]['kind'],'complete_current_set_at_entry')
 def test_complete_pair_enables_without_owner_bottleneck(self):
  self.enter();self.artifact();self.collect(self.now+E.DAY);self.assertEqual(self.store.read()[self.w['id']]['status'],'actionable')
  self.assertIn('no rerun or outreach',self.w['next'])
 def test_production_collector_binds_real_came_back_path(self):
  self.enter();self.artifact()
  with patch.object(R,'came_back',wraps=R.came_back) as got:self.collect(self.now+E.DAY)
  self.assertEqual(got.call_args.kwargs['work_id'],self.w['id']);self.assertIsInstance(got.call_args.kwargs['provenance'],E.DiagnosticReceipt)
  self.assertIn('collector checked',self.w['returns'][-1]['text'])
 def test_message_dict_cannot_forge_collector(self):
  self.enter();self.artifact();R.evidence_incoming(self.st,'saved',self.now+1,work_id=self.w['id'],provenance={'collector':'lab_diagnostic_files','targets':self.store._targets(self.w)})
  self.assertEqual(self.store.read()[self.w['id']]['status'],'awaiting_evidence')
 def test_changed_files_invalidate_stale_collector_receipt(self):
  self.enter();targets=self.artifact();receipt=self.store.collect(self.w['id'],self.now+E.DAY);Path(targets[0]).write_text('changed since collector');self.assertFalse(self.store.accept(receipt,self.now+E.DAY+1))
 def test_pause_survives_arrival(self):
  self.enter();self.store.pause(self.w['id'],self.now+2*E.DAY);self.artifact();self.collect(self.now+E.DAY);self.assertEqual(self.calls,[]);self.assertEqual(R.idle(self.st,self.now+E.DAY),[])
 def test_cancel_tombstone_survives_lost_board_save(self):
  self.enter();old=copy.deepcopy(self.st);self.store.owner(self.auth('!cancelwork RW-01234567'),'cancel',self.now+1);R.evidence_sync(old);self.assertEqual(old['room_work']['open'],[])
  R.evidence_sync(old);self.assertEqual(len(old['room_work']['history']),1)
 def test_failed_ledger_write_no_false_cancellation(self):
  self.enter();req=self.auth('!cancelwork RW-01234567')
  with patch.object(E.os,'replace',side_effect=OSError('disk failure')):
   with self.assertRaises(OSError):self.store.owner(req,'cancel',self.now+1)
  self.assertEqual(self.store.read()[self.w['id']]['status'],'awaiting_evidence')
 def test_corrupt_ledger_preserves_unrelated_send_and_work(self):
  self.enter();self.store.path.write_text('{broken')
  self.send(D.marker(self.w['id'])+'\nIndependent B passed.');self.assertEqual(self.calls[-1]['text'],'Independent B passed.')
  self.assertIsNone(self.auth('Status RW-01234567?'));self.assertEqual(len(R.open_items(self.st)),1)
  R.apply(self.st,'WORK: independent calibration | done when: calibration file exists',self.now+1)
  self.assertTrue(any(w['goal']=='independent calibration' for w in R.idle(self.st,self.now+1)))
 def test_wrong_schema_ledger_preserves_unrelated_send_and_board(self):
  self.enter()
  for data in ([],{'version':1,'items':{'RW-01234567':'damaged'}}):
   self.store.path.write_text(json.dumps(data));self.send(D.marker(self.w['id'])+'\nIndependent B passed.')
   self.assertEqual(self.calls[-1]['text'],'Independent B passed.');self.assertIsNone(self.auth('Status RW-01234567?'));self.assertEqual(len(R.open_items(self.st)),1)
 def test_ledger_io_failure_does_not_block_unrelated_send(self):
  self.enter()
  with patch.object(E.Store,'_load',side_effect=E.LedgerUnavailable('fixture')):
   self.send(D.marker(self.w['id'])+'\nIndependent B passed.');self.assertEqual(self.calls[-1]['text'],'Independent B passed.');self.assertEqual(len(R.open_items(self.st)),1)
 def test_uncertain_send_reservation_is_not_retried(self):
  self.enter()
  with self.assertRaises(AssertionError):D.send(forbidden,{'channel':'C','text':D.marker(self.w['id'])},self.now,lambda:False)
  self.send(D.marker(self.w['id']),self.now+1);self.assertEqual(self.calls,[])
 def test_changed_generation_gets_one_progress_dispatch(self):
  self.send(self.enter());self.artifact(events=False);self.collect(self.now+E.DAY);count=len(self.calls)
  self.send(D.marker(self.w['id']),self.now+E.DAY+1);self.assertEqual(len(self.calls),count)
 def test_full_waiting_inventory_keeps_actionable_capacity(self):
  for i in range(R.MAX_HELD):
   w=dict(self.w,id='RW-%08x'%i,goal='ModelJSONError '+'%032x'%i);self.st['room_work']['open'].append(w);self.store.enter(w,'missing',self.now)
  self.enter();R.apply(self.st,'WORK: independent calibration | done when: file exists',self.now+1)
  self.assertTrue(any(w['goal']=='independent calibration' for w in R.idle(self.st,self.now+1)))
 def test_sole_route_retained_other_work_pressed(self):
  self.enter();self.assertNotIn('NOTHING IN HAND',R.goal_block(self.st,self.now));b=dict(self.w,id='RW-99999999',goal='other calibration',state='open');self.st['room_work']['open'].append(b)
  why=R.not_carried(self.st,'Hello.',self.now+1);self.assertIn(b['id'],why);self.assertNotIn(self.w['id'],why)
 def test_concurrent_dispatch_real_processes(self):
  self.enter();ctx=multiprocessing.get_context('fork');barrier=ctx.Barrier(6);q=ctx.Queue()
  def child():
   barrier.wait();D.send(lambda method,body:q.put(body['text']) or {'ts':'1'},{'channel':'C','text':D.marker(self.w['id'])},self.now,lambda:False)
  ps=[ctx.Process(target=child) for _ in range(6)]
  for p in ps:p.start()
  for p in ps:p.join(10);self.assertEqual(p.exitcode,0)
  self.assertIn(self.w['id'],q.get(timeout=2))
  import queue
  with self.assertRaises(queue.Empty):q.get(timeout=.1)
  self.assertEqual(sum(h['kind']=='send_reserved' for h in self.store.read()[self.w['id']]['history']),1)
 def test_concurrent_owner_status_request_is_single_use(self):
  self.send(self.enter());req=self.auth('Status RW-01234567?');ctx=multiprocessing.get_context('fork');barrier=ctx.Barrier(4);q=ctx.Queue()
  def child():
   barrier.wait();D.send(lambda method,body:q.put(body['text']) or {'ts':'1'},{'channel':'C','text':D.marker(self.w['id'])},self.now+1,lambda:False,req)
  ps=[ctx.Process(target=child) for _ in range(4)]
  for p in ps:p.start()
  for p in ps:p.join(10);self.assertEqual(p.exitcode,0)
  self.assertIn(self.w['id'],q.get(timeout=2));import queue
  with self.assertRaises(queue.Empty):q.get(timeout=.1)
  self.assertEqual(self.store.read()[self.w['id']]['next_send'],self.now+1+E.DAY)
 def test_ordinary_and_actionable_typed_statuses_preserve_content(self):
  self.enter();self.artifact();R.evidence_arrivals(self.st,self.now+1)
  text=D.attribute('Independent B passed.','RW-99999999')+' '+D.attribute('Inspection found a malformed field.',self.w['id'])
  self.send(text,self.now+2);self.assertEqual(self.calls[-1]['text'],'Independent B passed. Inspection found a malformed field.')
 def test_corrupt_ledger_uses_board_wait_attribution_only(self):
  self.enter();self.store.path.write_text('{broken')
  text=D.attribute('Still waiting.',self.w['id'])+' '+D.attribute('B passed.','RW-99999999')
  D.send(lambda m,b:self.calls.append(b),{'channel':'C','text':text},self.now,lambda:False,waiting_work_ids=R.evidence_waiting_ids(self.st))
  self.assertEqual(self.calls[-1]['text'],'B passed.')
 def test_failed_closure_persistence_restart_and_recovery(self):
  self.artifact();self.enter();old=copy.deepcopy(self.st)
  with patch.object(E.os,'replace',side_effect=OSError('failed replacement')):
   self.assertIsNone(R._close(self.st,self.w,'done','checked',self.now+1))
  self.assertEqual(self.w['closure_error'],'tracked-closure-failed');self.assertIn(self.w,self.st['room_work']['open'])
  R.evidence_sync(old);self.assertEqual(len(old['room_work']['open']),1)
  saved=self.store.path.read_bytes();self.store.path.write_text('{broken')
  self.assertIsNone(R._close(old,old['room_work']['open'][0],'done','checked',self.now+2))
  b=dict(id='RW-99999999',goal='ordinary',state='open');old['room_work']['open'].append(b)
  self.assertIsNotNone(R._close(old,b,'done','checked',self.now+2))
  self.store.path.write_bytes(saved);w=old['room_work']['open'][0]
  self.assertIsNotNone(R._close(old,w,'done','checked',self.now+3));R.evidence_sync(old)
  self.assertEqual(old['room_work']['open'],[]);self.assertEqual(self.store.read()[self.w['id']]['status'],'resolved')
 def test_arrival_inside_day_and_during_pause_no_post(self):
  self.enter();self.store.pause(self.w['id'],self.now+E.DAY);self.artifact()
  R.evidence_recheck(self.st,self.now+1,forbidden,lambda:True)
  item=self.store.read()[self.w['id']];self.assertEqual(item['status'],'actionable')
  self.assertEqual(item['next_due'],self.now+E.DAY);self.assertEqual(item['paused_until'],self.now+E.DAY)
  self.assertEqual(R.idle(self.st,self.now+1),[])
 def test_actionable_reentry_retains_lineage_and_cooldown(self):
  self.enter();self.send(D.marker(self.w['id']));self.artifact();R.evidence_arrivals(self.st,self.now+1)
  before=self.store.read()[self.w['id']];Path(before['targets'][0]).unlink()
  self.enter();after=self.store.read()[self.w['id']]
  self.assertEqual(after['status'],'awaiting_evidence');self.assertEqual(after['work'],before['work'])
  self.assertEqual(after['baseline'],before['baseline']);self.assertEqual(after['next_send'],before['next_send'])
  self.assertEqual(after['history'][:len(before['history'])],before['history']);self.assertNotIn('next_action',after)
 def test_actionable_pause_still_suppresses_typed_status(self):
  self.artifact();self.enter();self.store.pause(self.w['id'],self.now+E.DAY)
  self.send(D.attribute('Found the malformed field.',self.w['id']));self.assertEqual(self.calls,[])
 def test_failed_close_command_does_not_claim_done(self):
  self.artifact();self.enter()
  with patch.object(E.os,'replace',side_effect=OSError('disk failure')),patch.object(R,'proved',return_value=True):
   text,_,_=R.apply(self.st,'WORK DONE RW-01234567: saved /tmp/result.json',self.now+1)
  self.assertIn('Not closed:',text);self.assertIn(self.w,self.st['room_work']['open'])
 def test_missing_tracked_record_does_not_close_board(self):
  self.artifact();self.enter();self.store.path.unlink()
  self.assertIsNone(R._close(self.st,self.w,'done','checked',self.now+1))
  self.assertEqual(self.w['closure_error'],'tracked-closure-failed')
 def restart_process(self,action):
  import subprocess
  statefile=Path(self.tmp.name)/'board.json'
  code='''import sys,json,os,socket
from pathlib import Path
sys.path.insert(0,sys.argv[1])
def forbidden(*a,**kw):raise AssertionError('network forbidden')
socket.socket.connect=forbidden;socket.create_connection=forbidden
import awaiting_evidence as E,room_work as R
store=E.Store(sys.argv[2],sys.argv[3]);E.store=lambda:store
statefile=Path(sys.argv[4]);state=json.loads(statefile.read_text());wid=sys.argv[5];now=float(sys.argv[6])
action=sys.argv[7]
if action=='close_crash':
 R._close(state,next(w for w in R.board(state)['open'] if w['id']==wid),'done','saved result',now)
 assert store.read()[wid]['status']=='resolved'
 os._exit(0) # board mutation deliberately never saved
if action=='arrival_crash':
 assert store.ingest_arrival(wid,now) is not None
 os._exit(0) # committed receipt obligation; accept deliberately not called
if action=='daily_crash':
 # The early arrival scan sees no files. They appear before daily collection.
 assert store.ingest_arrival(wid,now) is None
 targets=store.read()[wid]['targets'];Path(targets[0]).parent.mkdir(parents=True,exist_ok=True)
 Path(targets[0]).write_text('arrived between early scan and daily check')
 Path(targets[1]).write_text(json.dumps({'evidence_id':Path(targets[1]).name.split('.')[0]}))
 def crash_before_accept(*a,**kw):
  item=store.read()[wid]
  assert item['pending_receipt'] and item['status']=='evidence_changed'
  assert item['next_due']==now+E.DAY
  os._exit(0)
 R.evidence_arrivals=lambda *a:None # early scan above already completed
 R.came_back=crash_before_accept
 R.evidence_recheck(state,now,forbidden,lambda:False)
 raise AssertionError('daily collector did not reach receipt handoff')
if action=='recover_close':
 R.settle=forbidden
 R.evidence_sync(state);once=json.dumps(state,sort_keys=True)
 R.evidence_sync(state);assert json.dumps(state,sort_keys=True)==once
if action=='recover_arrival':R.evidence_arrivals(state,now)
print(json.dumps(state))
'''
  p=subprocess.run([sys.executable,'-B','-c',code,str(ROOT/'scripts'),str(self.store.path),self.tmp.name,str(statefile),self.w['id'],str(self.now+2),action],capture_output=True,text=True,timeout=20)
  self.assertEqual(p.returncode,0,p.stderr)
  return json.loads(p.stdout) if p.stdout.strip() else None
 def test_process_restart_after_ledger_close_before_board_save(self):
  self.artifact();self.enter();p=Path(self.tmp.name)/'board.json';p.write_text(json.dumps(self.st))
  self.restart_process('close_crash');restored=self.restart_process('recover_close')
  self.assertEqual(restored['room_work']['open'],[])
  history=restored['room_work']['history'];self.assertEqual(len(history),1)
  self.assertEqual(history[0]['state'],'done');self.assertEqual(history[0]['closed_at'],self.now+2)
  self.assertEqual(len(restored['room_work']['goal']['routes']),1)
 def test_process_restart_replays_committed_arrival_inside_day(self):
  self.enter();self.artifact();(Path(self.tmp.name)/'board.json').write_text(json.dumps(self.st))
  self.restart_process('arrival_crash');pending=self.store.read()[self.w['id']]
  self.assertTrue(pending['pending_receipt']);self.assertEqual(pending['status'],'evidence_changed')
  restored=self.restart_process('recover_arrival');item=self.store.read()[self.w['id']]
  self.assertEqual(item['status'],'actionable');self.assertNotIn('pending_receipt',item)
  self.assertEqual(item['next_due'],self.now+E.DAY)
  self.assertEqual(len(restored['room_work']['open'][0]['returns']),1)
 def test_corrupt_ledger_preserves_actionable_pause_and_unrelated_status(self):
  self.artifact();self.enter();self.store.pause(self.w['id'],self.now+E.DAY);R.evidence_sync(self.st)
  self.store.path.write_text('{broken')
  text=D.attribute('A inspection completed.',self.w['id'])+' '+D.attribute('B passed.','RW-99999999')
  D.send(lambda m,b:self.calls.append(b),{'channel':'C','text':text},self.now,lambda:False,
         waiting_work_ids=R.evidence_waiting_ids(self.st),paused_work_ids=R.evidence_paused_ids(self.st,self.now))
  self.assertEqual(self.calls[-1]['text'],'B passed.')
 def test_process_restart_replays_due_daily_collector_receipt(self):
  self.enter();original=self.now;self.now+=E.DAY
  (Path(self.tmp.name)/'board.json').write_text(json.dumps(self.st))
  self.restart_process('daily_crash');pending=self.store.read()[self.w['id']]
  self.assertTrue(pending['pending_receipt']);self.assertEqual(pending['next_due'],original+2*E.DAY+2)
  self.now+=1;restored=self.restart_process('recover_arrival')
  item=self.store.read()[self.w['id']];self.assertEqual(item['status'],'actionable')
  self.assertNotIn('pending_receipt',item);self.assertEqual(item['next_due'],pending['next_due'])
  self.assertEqual(len(restored['room_work']['open'][0]['returns']),1)
if __name__=='__main__':unittest.main()
