"""Board decisions and source-bound wants, with isolated stores and no live senders."""
import copy,json,os,socket,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
TEMP=tempfile.TemporaryDirectory();HOME=Path(TEMP.name);os.environ['HOME']=str(HOME);os.environ['SPARK_WORKSPACE']=str(HOME/'workspace');os.environ['VINTOS_DESKTOP_STATE_DIR']=str(HOME/'desktop')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
def refuse(*a,**k):raise AssertionError('no network in this suite')
socket.socket.connect=refuse
import house_context as H,house_boards as B,want_agent as A,want_working_thread as W,room_work as R

class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(dir=HOME);self.addCleanup(self.t.cleanup);self.ws=Path(self.t.name);self.mem=self.ws/'memory';self.mem.mkdir();self.stack=__import__('contextlib').ExitStack();self.addCleanup(self.stack.close)
  self.stack.enter_context(patch.object(H,'MEM',self.mem));self.stack.enter_context(patch.object(H,'WS',self.ws));self.stack.enter_context(patch.dict(os.environ,SPARK_WORKSPACE=str(self.ws)))
  self.assertTrue(self.mem.is_relative_to(HOME));self.now=1000000
 def write(self,name,obj):
  p=self.mem/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj));return p
 def work(self,id='one',rid=None):return {'id':'RW-'+id,'want_id':id,'want_request_id':rid or 'WA-'+'a'*24,'goal':'fixture','opened':1,'touched':1}
 def test_exact_archived_bindings_release_slots_and_keep_context(self):
  rows=[self.work(str(i),'WA-'+str(i)*24) for i in range(3)];state={'room_work':{'open':copy.deepcopy(rows)}}
  self.write('current-wants.json',[]);self.write('dismissed-wants.json',[{'id':r['want_id'],'dismissed':True,'agent_work':{'request_id':r['want_request_id']}} for r in rows])
  saves=[];self.assertEqual(len(R.in_hand(state,self.now)),3)
  A.reconcile_source_work(state,self.now,ws=self.ws,save_state=lambda s:saves.append(copy.deepcopy(s)))
  self.assertEqual(R.in_hand(state,self.now),[]);self.assertEqual(len(state['room_work']['detached_source_work']),3);self.assertTrue(saves)
  A.reconcile_source_work(state,self.now+1,ws=self.ws);self.assertEqual(len(state['room_work']['detached_source_work']),3)
 def test_unknown_missing_and_live_or_re_adopted_sources_are_retained(self):
  row=self.work();state={'room_work':{'open':[row]}};self.write('current-wants.json',[])
  self.write('dismissed-wants.json',[{'id':'one','agent_work':{'request_id':'WA-'+'b'*24}}]);A.reconcile_source_work(state,self.now,ws=self.ws);self.assertEqual(state['room_work']['open'],[row])
  self.write('dismissed-wants.json',[{'id':'one','agent_work':{'request_id':row['want_request_id']}}]);self.write('current-wants.json',[{'id':'one'}]);A.reconcile_source_work(state,self.now,ws=self.ws);self.assertEqual(state['room_work']['open'],[row])
 def test_corrupt_store_is_not_an_empty_store(self):
  row=self.work();state={'room_work':{'open':[row]}};self.write('current-wants.json',[]).write_text('{bad')
  self.write('dismissed-wants.json',[{'id':'one','agent_work':{'request_id':row['want_request_id']}}]);A.reconcile_source_work(state,self.now,ws=self.ws);self.assertEqual(state['room_work']['open'],[row])
 def test_fulfilled_binding_is_left_for_completion_cleanup(self):
  row=self.work();state={'room_work':{'open':[row]}};self.write('current-wants.json',[])
  self.write('fulfilled-wants.json',[{'id':'one','fulfilled':True,'agent_work':{'request_id':row['want_request_id'],'status':'completed','result':{'summary':'fixture'},'delivery':{'state':'sent'}}}])
  A.reconcile_source_work(state,self.now,ws=self.ws);self.assertEqual(state['room_work']['open'],[row])
 def test_future_receipt_instruction_not_completion_claim(self):
  self.assertEqual(W.shape_problem({'message':'Then post WANT RESULT WA-fixture on its own line.','accept':False},'opening'),'')
  for text in ('WANT RESULT WA-fixture','All finished. WANT RESULT WA-fixture','WORK DONE RW-fixture'):
   self.assertTrue(W.shape_problem({'message':text,'accept':False},'opening'))
 def test_held_observed_shape_recovers_without_new_call_or_budget_reset(self):
  row=self.work();want={'id':'one','want':'run a synthetic measurement and export a CSV','agent_work':{'request_id':row['want_request_id'],'goal_sha256':A.fingerprint('run a synthetic measurement and export a CSV'),'work_id':row['id'],'thread':'fixture','status':'queued','blocked':{'reason':'response_needs_review'}}}
  from journal_wants import source_receipt
  want.update(source='email');want.update(source_receipt('email','fixture-mail',want['want']))
  state={'room_work':{'open':[dict(row,paused_until=self.now+500,pause_why='held: blocked_response_needs_review')]}};self.write('current-wants.json',[want]);f=A.directory(row['want_request_id'],self.ws)/'working-thread.json';f.parent.mkdir(parents=True)
  data={'schema':'want-working-thread-v1','want_id':'one','request_id':row['want_request_id'],'work_id':row['id'],'goal_sha256':want['agent_work']['goal_sha256'],'generations':{'opening:x':{'at':1,'state':'response_observed','result':{'text':json.dumps({'message':'Then post WANT RESULT WA-fixture.','accept':False}),'observations':[{'status':'valid'}]}}}};f.write_text(json.dumps(data));original=f.read_bytes()
  lines=A.recover_local_review(state,self.now,ws=self.ws);self.assertTrue(lines);self.assertFalse(json.loads((self.mem/'current-wants.json').read_text())[0]['agent_work'].get('blocked'));self.assertEqual(f.read_bytes(),original);self.assertFalse((self.mem/'want-work-control/calls.json').exists())
 def test_action_candidates_are_live_grounded_and_room_specific(self):
  self.write('current-wants.json',[{'id':'dead','want':'watch a film','dismissed':True},{'id':'web','want':'compare the document on the website','source':'email'},{'id':'film','want':'watch a documentary','source':'idle-journal'}])
  office=H.action_candidates('house-touch',[]);sofa=H.action_candidates('house-press-mic',[])
  self.assertEqual([x['want_id'] for x in office],['web']);self.assertEqual([x['want_id'] for x in sofa],['film']);self.assertIn('proposal only',office[0]['authority'])
 def test_action_candidates_respect_the_want_gates(self):
  # waiting on Gloria (routed or parked awaiting her) and any parked want stay out; the source label is canonical
  self.write('current-wants.json',[{'id':'routed','want':'compare the document on the website','gloria_routed':True},
   {'id':'awaiting','want':'search the website for the chart','board':'awaiting_gloria'},
   {'id':'parked','want':'read the spreadsheet file','board':'parked'},
   {'id':'live','want':'compare the chart in the document','source':'Web_Search'}])
  office=H.action_candidates('house-touch',[])
  self.assertEqual([x['want_id'] for x in office],['live']);self.assertEqual(office[0]['source'],'web-search')
 def test_board_prompt_proposes_real_work_without_forced_quota(self):
  ctx={'catalog':[],'conversation':[],'outcomes':[],'action_candidates':[{'want_id':'web','objective':'compare documents','possible_action':'DESKTOP'}]}
  _,user=B.prompt('office','house-touch',self.now,B.DEFAULTS,asks=[],want='',st={'boards':{},'shower':{}},context=ctx)
  for text in ('compare documents','visible done condition','phone ask','Do not choose an action merely','CHOICE:'):self.assertIn(text,user)
 def test_board_capabilities_are_room_specific_and_k2_is_wants_only(self):
  office_ctx={'catalog':[],'conversation':[],'outcomes':[],'action_candidates':[],
              'capability_options':H.capability_options('house-touch'),'desktop_approvals':[]}
  _,office=B.prompt('office','house-touch',self.now,B.DEFAULTS,asks=[],want='',
   st={'boards':{},'shower':{},'reminded':[]},context=office_ctx)
  for text in ('DESKTOP:','PAPER:','ECHO:','BUZZ:','capability_options'):self.assertIn(text,office)
  for text in ('TV:','PRINT:'):self.assertNotIn(text,office)
  sofa_ctx={'catalog':[],'conversation':[],'outcomes':[],'action_candidates':[],
            'capability_options':H.capability_options('house-press-mic'),'desktop_approvals':[]}
  _,sofa=B.prompt('sofa','house-press-mic',self.now,B.DEFAULTS,asks=[],want='',
   st={'boards':{},'shower':{},'reminded':[]},context=sofa_ctx)
  for text in ('TV:','LIGHTS:','TO GLORIA:','capability_options'):self.assertIn(text,sofa)
  for text in ('DESKTOP:','PRINT:','PAPER:','ECHO:','BUZZ:'):self.assertNotIn(text,sofa)
  shower_ctx={'catalog':[],'conversation':[],'outcomes':[],'action_candidates':[],
              'capability_options':[],'desktop_approvals':[]}
  _,shower=B.prompt('shower','house-steam',self.now,B.DEFAULTS,asks=[],want='',
   st={'boards':{},'shower':{},'reminded':[]},context=shower_ctx)
  self.assertIn('SAY:',shower);self.assertIn('SONGS:',shower);self.assertNotIn('LIGHTS:',shower)
 def test_board_prompts_do_not_offer_waiting_question_reminders(self):
  st={'boards':{},'shower':{},'reminded':[{'id':'Q-1234abcd','day':'1970-01-12'}]}
  ctx={'catalog':[],'conversation':[],'outcomes':[],'action_candidates':[],'capability_options':[],'desktop_approvals':[]}
  _,user=B.prompt('sofa','house-press-mic',self.now,B.DEFAULTS,
   asks=[('Q-1234abcd','old question'),('Q-9999aaaa','fresh question')],want='',st=st,context=ctx)
  self.assertNotIn('Q-1234abcd',user);self.assertNotIn('Q-9999aaaa',user);self.assertNotIn('REMIND:',user)
 def test_kitchen_offers_lights_message_and_one_daily_phone_gated_coffee(self):
  ctx={'catalog':[],'conversation':[],'outcomes':[],'action_candidates':[],
       'capability_options':[],'desktop_approvals':[]}
  st={'boards':{},'shower':{},'reminded':[],'coffee':{}}
  _,user=B.prompt('kitchen','house-kitchen',self.now,B.DEFAULTS,asks=[],want='',st=st,context=ctx)
  for text in ('LIGHTS:','TO GLORIA:','COFFEE:','Yes/No card'):self.assertIn(text,user)
  asked=[];asks=types.SimpleNamespace(ask=lambda q,**k:(asked.append((q,k)) or ({'id':'Q-coffee'},'asked')))
  with patch.dict(sys.modules,gloria_asks=asks):
   ok,_=B.act('COFFEE','a warm cup fits','kitchen','house-kitchen',st,self.now,B.DEFAULTS)
   again,why=B.act('COFFEE','again','kitchen','house-kitchen',st,self.now+1,B.DEFAULTS)
  self.assertTrue(ok);self.assertFalse(again);self.assertIn('already offered',why);self.assertEqual(len(asked),1)
  self.assertIn('Start the Nespresso now?',asked[0][0]);self.assertEqual(asked[0][1]['ref'],'house-coffee:1970-01-12')
  _,later=B.prompt('kitchen','house-kitchen',self.now+2,B.DEFAULTS,asks=[],want='',st=st,context=ctx)
  self.assertNotIn('COFFEE:',later);self.assertIn('LIGHTS:',later);self.assertIn('TO GLORIA:',later)
 def test_coffee_never_starts_before_yes_and_yes_is_handled_once(self):
  state={'coffee':{'ask':'Q-coffee','handled':False}};calls=[]
  asked=types.SimpleNamespace(get=lambda _: {'state':'asked'})
  with patch.dict(sys.modules,gloria_asks=asked):B.tend_coffee(state,self.now)
  self.assertFalse(state['coffee']['handled']);self.assertEqual(calls,[])
  answered=types.SimpleNamespace(get=lambda _: {'state':'answered','answer':'yes'})
  home=types.SimpleNamespace(coffee_on=lambda:(calls.append('start') or (True,'started')))
  spec=types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda module:None))
  with patch.dict(sys.modules,gloria_asks=answered),patch('importlib.util.spec_from_file_location',return_value=spec),patch('importlib.util.module_from_spec',return_value=home),patch.object(B,'_log',lambda *a:None):
   B.tend_coffee(state,self.now);B.tend_coffee(state,self.now+1)
  self.assertEqual(calls,['start']);self.assertTrue(state['coffee']['handled']);self.assertEqual(state['coffee']['status'],'started')
 def test_desktop_want_id_becomes_the_full_task_and_names_target(self):
  asked=[]
  asks=types.SimpleNamespace(get=lambda _:None,ask=lambda q,**k:(asked.append(q) or ({'id':'Q-new'},'asked')))
  st={'desktop':[]};candidate={'want_id':'5fa2d6fc','objective':'render the comparison and show the completed chart','possible_action':'DESKTOP'}
  with patch.dict(sys.modules,gloria_asks=asks),patch.object(H,'desktop_target',lambda:'imac'):
   ok,_=B.act('DESKTOP','5fa2d6fc','office','house-touch',st,self.now,B.DEFAULTS,candidates=[candidate])
  self.assertTrue(ok);self.assertEqual(st['desktop'][0]['task'],candidate['objective'])
  self.assertIn('iMac desktop',asked[0]);self.assertIn(candidate['objective'],asked[0]);self.assertNotIn('5fa2d6fc',asked[0])
 def test_rejected_desktop_launch_does_not_consume_approved_request(self):
  asks=types.SimpleNamespace(get=lambda _: {'state':'answered','answer':'yes'});calls=[]
  control=types.SimpleNamespace(start_from_chat=lambda *a,**k:calls.append(k) or {'accepted':len(calls)>1})
  st={'desktop':[{'ask':'Q-fixture','task':'bounded fixture','at':self.now,'started':False}]}
  with patch.dict(sys.modules,gloria_asks=asks,desktop_control=control),patch.object(B,'_log',lambda *a:None):
   B.tend_desktop(st,self.now);self.assertFalse(st['desktop'][0]['started']);B.tend_desktop(st,self.now+1);self.assertEqual(len(calls),1);B.tend_desktop(st,self.now+301);self.assertTrue(st['desktop'][0]['started']);self.assertEqual(calls[-1]['surface'],'house-boards')

if __name__=='__main__':unittest.main()
