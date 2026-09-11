#!/usr/bin/env python3
"""Behavioral regressions for the September review. Scratch stores; no real effects."""
import os,sys,json,tempfile,importlib.util,hashlib,concurrent.futures
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts'))
HOME=Path(tempfile.mkdtemp(prefix='repairs-'));os.environ['HOME']=str(HOME)
os.environ.pop('SPARK_WORKSPACE',None)
MEM=HOME/'.vintos/workspace/memory';MEM.mkdir(parents=True)
import store_guard as SG,skill_forge as SF,forge_build as FB,forge_resume as FR,print_3d as P,source_cache as SC,compute_admission as CA
R=[]
def check(name,ok):
 R.append(bool(ok));print(('PASS ' if ok else 'FAIL ')+name)
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
# Concurrent mutations actually preserve all rows.
p=MEM/'concurrent.json'
def add(i): SG.locked_update(str(p),lambda rows:rows+[i],default=[])
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(add,range(80)))
check('80 simultaneous store mutations survive',len(json.loads(p.read_text()))==80)
CA.MEMORY=str(MEM);CA.LEDGER=str(MEM/'paid.jsonl')
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: admitted=list(pool.map(lambda _:CA.reserve_paid('test','fake',units=2,cap=10)[0],range(20)))
check('concurrent paid reservations honor units and cap',sum(admitted)==5 and CA.paid_today('fake')==10)
CA.LEDGER=str(MEM)
check('failed receipt prevents paid admission',CA.reserve_paid('test','fake')[0] is False)
SC.STORE=str(MEM/'cache.json');check('failed inference remains eligible',not SC.unchanged('x','a') and not SC.unchanged('x','a'))
SC.commit('x','a');check('successful inference commits only its material',SC.unchanged('x','a') and not SC.unchanged('x','b'))
# Narrowing is semantic; unsupported changes cannot silently pass.
g=SF._narrower({'scope':{'max_hours':4,'recipients':['a','b']}},{'scope':{'max_hours':1,'recipients':['a']}})
check('approved ceilings and subsets are retained',g['scope']=={'max_hours':1,'recipients':['a']})
try:SF._narrower({'scope':{'max_hours':4}},{'scope':{'max_hours':5}});rejected=False
except ValueError:rejected=True
check('widening is refused',rejected)
check('ambiguous reviewer PASS cannot verify',FB.review({}, {},fable=lambda *a,**k:'PASS? No, FAIL: unsafe')[0] is False)
check('zero-assertion generated tests fail',FB.sandbox_test('def sample(note): return note','print("0/0")','sample')[0] is False)
check('a real capability assertion passes inside the OS boundary',FB.sandbox_test('def sample(note): return note.upper()','import sample\nassert sample.sample("hi")=="HI"','sample')[0])
marker=HOME/'escape'
code='def sample(note):\n open(%r,"w").write("escape")\n return note\n'%str(marker)
check('generated code cannot write outside its scratch',not FB.sandbox_test(code,'import sample\nassert sample.sample("hi")=="hi"','sample')[0] and not marker.exists())
marker.write_text("private fixture")
code='def sample(note):\n return open(%r).read()\n'%str(marker)
check('generated code cannot read neighboring scratch data',not FB.sandbox_test(code,'import sample\nassert sample.sample("hi")=="private fixture"','sample')[0])
# Resume failure does not retire the proposal.
old=FR._forge;oldwrite=FR._update_wants
class Forge:
 def resumable(self,*a):return [{'proposal':'p','capability':'cap','want_id':'w'}]
 def mark(self,*a):raise AssertionError('must not mark after failed save')
FR._forge=lambda:Forge();FR._update_wants=lambda f:False
check('resume retains proposal when want persistence fails',FR.resume()[0]['outcome']==FR.REFUSED)
FR._forge=old;FR._update_wants=oldwrite
check('an unrelated unblocked want is not crash recovery',FR.release({'id':'w'},'cap','p')[1]==FR.STILL_BLOCKED)
# Real STL/G-code bytes, explicit answers, no real delivery.
import types
sys.modules['deliver']=types.SimpleNamespace(deliver=lambda *a,**k:{'state':'sent'})
P.JOBS=str(MEM/'jobs.json');P.CONFIG=str(MEM/'printer.json')
Path(P.CONFIG).write_text(json.dumps({'handoff_dir':str(HOME/'handoff')}))
j=P.open_job('one mesh');jid=j['id']
check('public transitions cannot bypass approval',P.advance(jid,'draft_waiting')[0] is None)
check('arbitrary metadata cannot mint approval',P.advance(jid,'modelling',extra={'draft_approval':'fake'})[0] is None)
stl=HOME/'mesh.stl';stl.write_text('solid mesh\nvertex 0 0 0\nvertex 1 0 1\nvertex 0 1 0\nendsolid\n')
P.attach_model(jid,str(stl));j,_=P.present(jid,'draft','Review this mesh')
check('boolean-like strings cannot approve',P.answer(jid,'draft','false',digest=j['model']['sha256'])[0] is None)
check('wrong artifact digest cannot approve',P.answer(jid,'draft',True,digest='wrong')[0] is None)
j,_=P.answer(jid,'draft',True,digest=j['model']['sha256'])
gcode=HOME/'mesh.gcode';gcode.write_text('G21\nG90\nG1 X1 Y1 Z1\n')
P.attach_slice(jid,str(gcode),seconds=60,filament_mm=100,layer_mm=.2);j,_=P.present(jid,'slice','Review this toolpath')
j,why=P.answer(jid,'slice',True,digest=j['slice']['sha256'])
check('ready requires the approved toolpath on disk',j and j['state']=='ready' and Path(j['handoff_file']).read_bytes()==gcode.read_bytes())
# Elapsed work is never clipped, and the direct client has a hard local deadline.
import time, subprocess, astra_call as AC
clock=[0.0];timeouts=[];old_clock=time.monotonic
def fake_design(*args,**kwargs):
 timeouts.append(kwargs.get("timeout"));clock[0]+=180;return "import bpy"
try:
 time.monotonic=lambda:clock[0]
 for i in range(5):
  job=P.open_job("budget fixture "+str(i));P.design("fixture",job['id'],caller=fake_design)
finally:time.monotonic=old_clock
check('Astra overruns are counted rather than clipped',len(timeouts)==3 and P.astra_seconds_today()==540 and timeouts==[120.0]*3)
worker=HOME/'slow_worker.py';worker.write_text('import time;time.sleep(10)\n')
old_file,old_key=AC.__file__,AC._key;AC.__file__=str(worker);AC._key=lambda:'fixture';CA.LEDGER=str(MEM/'deadline-paid.jsonl')
t0=time.monotonic()
try:AC.call('fixture',[],timeout=.1);expired=False
except subprocess.TimeoutExpired:expired=True
finally:AC.__file__,AC._key=old_file,old_key
check('provider worker is terminated at its wall-clock deadline',expired and time.monotonic()-t0<2)
# Receipt only after successful embedding.
TV=load('taste_vector',REPO/'bin/taste-vector.py');TV.TASTE_VECTOR_FILE=str(MEM/'taste.json');TV.embed=lambda text:None
TV.update_from_signal('red','' if False else .3,occurrence_id='failed')
check('failed embedding does not consume occurrence','failed' not in TV.load_taste_vector().get('counted_occurrences',[]))
# Privacy at the serving door; selection is read-only, exposure only after admission.
import withheld_head as WH
WH.MEMORY=str(MEM);WH.OUT=str(MEM/'withheld.json');WH.HIST=str(MEM/'withheld-history.json')
Path(WH.OUT).write_text(json.dumps({'withheld':'the private phrase','source_hash':'s','lineage_id':'l','confidence':.8,'novelty':.5}))
(MEM/'withheld-lineage.json').write_text(json.dumps([{'lineage_id':'l','rep':'the private phrase','muted':True}]))
check('bound private hints never enter the prompt',WH.get_withheld_hint()=='')
(MEM/'withheld-lineage.json').write_text('[]');before=Path(WH.OUT).read_bytes();WH.get_withheld_hint();WH.get_withheld_hint()
check('rendering does not consume exposure',Path(WH.OUT).read_bytes()==before)
WH.mark_admitted('s','t');WH.mark_admitted('s','t')
check('admission counts a turn once',json.loads(Path(WH.OUT).read_text())['surfaced']==1)
assert MEM.is_relative_to(HOME)
SG.write_json(WH.HIST, [])
(MEM/'withheld-lineage.json').write_text('[]')
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 list(pool.map(lambda i: WH.commit_candidate('fixture','fixture','a concrete fixture candidate with sufficient detail',.8,'same-origin'),range(20)))
check('concurrent publication records one occurrence',len(json.loads(Path(WH.HIST).read_text()))==1)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 list(pool.map(lambda i: WH.mark_admitted('same-origin','turn-'+str(i)),range(40)))
check('all forty concurrent exposures survive in both projections',json.loads(Path(WH.HIST).read_text())[0]['surfaced']==40 and json.loads(Path(WH.OUT).read_text())['surfaced']==40)
WC=load('withheld_confirm_fixture',REPO/'scripts/withheld_confirm.py');WC.HIST=WH.HIST
import types
class Scalar:
 def max(self):return self
 def item(self):return .9
class Encoder:
 def encode(self,*a,**kw):
  assert not getattr(SG._state,'held',set())
  WH.mark_admitted('same-origin','during-embedding')
  return [1]
WC.M=Encoder();WC.util=types.SimpleNamespace(cos_sim=lambda *a:Scalar())
WC.chunks_private=lambda *a:['fixture private passage'];WC.chunks_shared=lambda *a:[]
h=json.loads(Path(WH.HIST).read_text());h[0]['ts']='2026-01-01T00:00:00';SG.write_json(WH.HIST,h)
WC.main()
check('grading preserves exposure recorded during embedding and refuses stale verdict','verdict' not in json.loads(Path(WH.HIST).read_text())[0] and json.loads(Path(WH.HIST).read_text())[0]['surfaced']==41)
UF=load('frontier_fixture',REPO/'scripts/unsaid_frontier.py');UF.FRONTIER=str(MEM/'unsaid-frontier.json');UF.LIN=str(MEM/'withheld-lineage.json')
original={'lineage_id':'l','state':'open'}
SG.write_json(UF.FRONTIER,[original]);SG.write_json(UF.LIN,[{'lineage_id':'l','origins':['a','b']}])
SG.locked_update(UF.FRONTIER,lambda rows:rows+[{'lineage_id':'new','state':'open'}])
check('privacy decision preserves concurrent frontier additions',UF.commit_decision(original,'KEEP_PRIVATE','fixture') and len(json.loads(Path(UF.FRONTIER).read_text()))==2 and json.loads(Path(UF.LIN).read_text())[0]['muted'])
check('obsolete deliberation cannot replace an already-decided frontier',not UF.commit_decision(original,'VOICE','obsolete'))
PL=load('proposition_fixture',REPO/'scripts/proposition_lineage.py');PL.MEM=str(MEM);PL.LEDGER=str(MEM/'tension-ledger.json');PL.PROPS=str(MEM/'proposition-ledger.json')
SG.write_json(PL.LEDGER,{'tensions':[{'tension_id':'T-'+str(i),'status':'SUPPORTED','history':[]} for i in range(20)]})
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 ids=list(pool.map(lambda i:PL.confirm_lineage('fixture '+str(i),['T-'+str(i)]),range(20)))
check('concurrent lineage binding allocates unique ids and preserves every mechanism',len(set(ids))==20 and len(json.loads(Path(PL.PROPS).read_text())['propositions'])==20 and all(t.get('proposition_id') for t in json.loads(Path(PL.LEDGER).read_text())['tensions']))
EU=load('emoclaw_utils',REPO/'scripts/emoclaw_utils.py')
EU.generate_steps=lambda *a,**kw:[]
EU.check_want_interference=lambda *a:None
EU.nudge_emotions=lambda *a,**kw:None
sys.modules['wants_meta']=types.SimpleNamespace(consult=lambda *a:None)
sys.modules['similarity_gate']=types.SimpleNamespace(check_want=lambda *a:None)
sys.modules['want_completion']=types.SimpleNamespace(admit=lambda *a:{'state':'ADMIT'})
sys.modules['want_stance']=types.SimpleNamespace(admit=lambda *a:None)
import requests
requests.post=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('live provider forbidden'))
want_path=MEM/'current-wants.json';SG.write_json(str(want_path),[])
a=EU.GeneratedWant('I want to paint a red mountain',{'desire':'I want to paint a red mountain','tension':'mountain provenance','source_kind':'current_desire','present_pull':'paint now','source':'fixture-a'})
b=EU.GeneratedWant('I want to listen carefully to birdsong',{'desire':'I want to listen carefully to birdsong','tension':'bird provenance','source_kind':'current_desire','present_pull':'listen now','source':'fixture-b'})
SG.write_json(str(MEM/'.pending-want-provenance.json'),{'desire':str(a),'tension':'wrong legacy provenance'})
ra=EU.express_want(a,source='fixture-a');rb=EU.express_want(b,source='fixture-b')
check('generated provenance stays with its sentence instead of the legacy global slot',ra['tension']=='mountain provenance' and rb['tension']=='bird provenance' and ra['generation_source']=='fixture-a')
check('legacy pending provenance remains untouched and unused',json.loads((MEM/'.pending-want-provenance.json').read_text())['tension']=='wrong legacy provenance')
sys.modules['subconscious_context']=types.SimpleNamespace(get_subconscious_context_compact=lambda:'')
sys.modules['subconscious_drift']=types.SimpleNamespace(get_drift_bias=lambda:'')
sys.modules['emoclaw_pressure']=types.SimpleNamespace(get_pressure_compact=lambda **kw:'')
def provider_fixture(*args,**kw):
 payload=[{'desire':'I want to trace constellations tonight','tension':'fixture pull','source_kind':'current_desire','present_pull':'tonight','pull':4}]
 return types.SimpleNamespace(json=lambda:{'choices':[{'message':{'content':json.dumps(payload)}}]})
from unittest.mock import patch
SG.write_json(str(MEM/'want-candidates.json'),[])
with patch.object(requests,'post',side_effect=provider_fixture):
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  generated=list(pool.map(lambda i:EU.generate_want('fixture trigger',source='origin-'+str(i)),range(12)))
check('concurrent generation preserves each origin and every candidate journal row',all(isinstance(w,EU.GeneratedWant) and w.provenance['source']=='origin-'+str(i) for i,w in enumerate(generated)) and len(json.loads((MEM/'want-candidates.json').read_text()))==12)
SP=load('spark_fixture',REPO/'scripts/spark_pressure.py');SP.MEMORY=str(MEM);SP.DIRECTIVE=str(MEM/'spark-pressure-directive.json');SP.EVENTS=str(MEM/'spark-pressure-events.json')
assert all(Path(p).is_relative_to(HOME) for p in [SP.DIRECTIVE,SP.EVENTS])
SP._his_replies_since=lambda *a:[]
directive={'created':'2026-01-01T00:00:00','about':'fixture stall','direction':'expand','evidence':'fixture','consumed':False}
SG.write_json(str(want_path),[]);SG.write_json(SP.DIRECTIVE,directive)
calls=[]
def candidate_fixture(**kw):
 calls.append(kw)
 return a
EU.generate_want=candidate_fixture
from unittest.mock import patch
with patch.object(SP,'compare_and_swap',return_value=False):SP.tick()
check('spark handoff admits a real row before acknowledging the directive',len(json.loads(want_path.read_text()))==1 and not json.loads(Path(SP.DIRECTIVE).read_text())['consumed'])
SP.journal_prep_block(record=True)
SP.tick()
check('spark recovers a persisted handoff without regenerating',len(calls)==1 and calls[0]['trigger_description'] and json.loads(Path(SP.DIRECTIVE).read_text())['want_id']==json.loads(want_path.read_text())[0]['id'])
SG.write_json(SP.DIRECTIVE,{**directive,'created':'2026-01-02T00:00:00'})
EU.generate_want=lambda **kw:None
SP.tick()
check('no generated want leaves the directive live',not json.loads(Path(SP.DIRECTIVE).read_text())['consumed'])
SG.write_json(SP.EVENTS,{'events':[{'fixture':True}],'last_fired':'fixture'})
SP.set_consent(True)
check('consent update preserves event history',json.loads(Path(SP.EVENTS).read_text())['events']==[{'fixture':True}])
from datetime import datetime, timedelta
SG.write_json(SP.DIRECTIVE,{'created':datetime.now().isoformat(),'mode':'demand_response','about':'fixture topic','consumed':False})
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 claims=list(pool.map(lambda _:SP.claim_outreach(),range(20)))
check('concurrent outreach claims admit one topic and label admission distinctly',sum(bool(x) for x in claims)==1 and json.loads(Path(SP.DIRECTIVE).read_text())['consumed_by']=='outreach-admission')
import threading
entered=threading.Event();release=threading.Event();claim_started=threading.Event()
SG.write_json(str(want_path),[])
SG.write_json(SP.DIRECTIVE,{'created':(datetime.now()-timedelta(hours=9)).isoformat(),'mode':'demand_response','about':'fixture competition','consumed':False})
def slow_candidate(**kw):
 entered.set();assert release.wait(3);return a
EU.generate_want=slow_candidate
def competing_claim():
 claim_started.set();return SP.claim_outreach()
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 tick_future=pool.submit(SP.tick);assert entered.wait(3)
 claim_future=pool.submit(competing_claim);assert claim_started.wait(3)
 try:
  claim_future.result(timeout=.2);waited=False
 except concurrent.futures.TimeoutError:waited=True
 finally:release.set()
 tick_future.result(timeout=3);claim_result=claim_future.result(timeout=3)
check('outreach and want formation share one consumer claim',waited and not claim_result and json.loads(Path(SP.DIRECTIVE).read_text())['consumed_by']=='want-formation')
print('%d/%d'%(sum(R),len(R)));sys.exit(0 if all(R) else 1)
