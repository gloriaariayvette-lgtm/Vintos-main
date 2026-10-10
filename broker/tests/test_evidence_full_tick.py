"""Existing fully isolated channel fixture plus waiting-state send/control checks."""
import pathlib,runpy,sys,time,json
from unittest.mock import patch
root=pathlib.Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'scripts'),'/home/gloria/Vintos-main/scripts']
import room_work as R,awaiting_evidence as E,evidence_delivery as F
with patch.object(sys,'exit',side_effect=lambda code:None if code==0 else (_ for _ in ()).throw(AssertionError(code))):
 g=runpy.run_path(str(root/'broker/tests/test_room_work.py'))
D=g['D'];S=g['S'];reply=g['reply'];tick=g['tick'];now=2000.
D._save(D.CONFIG_FILE,{'owner_user_id':g['GLORIA']})
st=json.load(open(D.STATE))
w={'id':'RW-01234567','goal':'ModelJSONError '+'a'*32,'done_when':'recover bytes','by':'owner','opened':now,'asks':[],'returns':[],'steps':[],'goal_id':'RC-11111111'}
st['room_work']={'open':[w],'history':[],'goal':{'id':'RC-11111111','goal':'diagnose missing parser evidence','done_when':'recover bytes','opened':now,'routes':[]}}
E.store().enter(w,'original bytes unavailable',now);R.evidence_sync(st);E.store().statement(w['id'],now);D._save(D.STATE,st)
reply['text']=F.attribute('The response still has not arrived.',w['id'])+'\nWORK: independent calibration for the goal | done when: calibration file exists'
S.add(g['DOT'],'Tell me about the independent calibration.');before=len(S.posted)
with patch.object(time,'time',return_value=now+10):out=tick(now+10)
assert len(S.posted)==before+1,(out,S.posted[before:])
assert w['id'] not in S.posted[-1]['text'] and 'independent calibration' in S.posted[-1]['text'],S.posted[-1]
print('PASS full tick preserves unrelated mixed-message text while metering the gap')
reply['text']=F.marker(w['id'])
S.add(g['GLORIA'],'What is the status of RW-01234567?');before=len(S.posted)
with patch.object(time,'time',return_value=now+20):out=tick(now+20)
assert len(S.posted)==before+1,(out,S.posted[before:])
assert 'RW-01234567' in S.posted[-1]['text']
print('PASS full tick authenticates owner status at the final send')
S.add(g['GLORIA'],next(iter(D.SIGNS))+' !cancelwork RW-01234567')
with patch.object(time,'time',return_value=now+30):out=tick(now+30)
assert E.store().read()[w['id']]['status']!='cancelled',out
print('PASS full tick rejects signed-agent cancellation through owner account')
S.add(g['GLORIA'],'!cancelwork RW-01234567');reply['text']='The independent calibration remains available.'
with patch.object(time,'time',return_value=now+40):out=tick(now+40)
assert E.store().read()[w['id']]['status']=='cancelled',out
assert not any(x['id']==w['id'] for x in json.load(open(D.STATE))['room_work']['open'])
print('PASS full tick applies verified owner cancellation and persists its tombstone')
assert not g['NET'],g['NET']
print('PASS no real network or model calls')

# Generic status about a different task must not turn into a broadcast of waits.
st=json.load(open(D.STATE));w2=dict(w,id='RW-22222222',goal='ModelJSONError '+'b'*32,state='open',returns=[],asks=[],steps=[])
st['room_work']['open'].append(w2);E.store().enter(w2,'diagnostic files missing',now+50);R.evidence_sync(st);E.store().statement(w2['id'],now+50);D._save(D.STATE,st)
S.add(g['GLORIA'],'What is the status of independent calibration?');reply['text']='WORK: independent calibration for the goal | done when: calibration file exists';before=len(S.posted)
with patch.object(time,'time',return_value=now+60):out=tick(now+60)
assert not any(w2['id'] in p['text'] for p in S.posted[before:]),S.posted[before:]
print('PASS generic owner status does not broadcast an unrelated waiting item')

# This is the production tick -> local collector -> came_back -> accept path.
# The artifact is a saved fixture, no external call, model run or owner gate.
targets=E.store().read()[w2['id']]['targets'];pathlib.Path(targets[0]).parent.mkdir(parents=True,exist_ok=True)
pathlib.Path(targets[0]).write_text('saved local response fixture')
pathlib.Path(targets[1]).write_text(json.dumps({'evidence_id':'b'*32,'events':['captured']}))
S.add(g['DOT'],'Continue the independent calibration.');due=now+50+E.DAY
with patch.object(R,'came_back',wraps=R.came_back) as returned,patch.object(time,'time',return_value=due):out=tick(due)
assert returned.call_args.kwargs['work_id']==w2['id'],returned.call_args_list
assert isinstance(returned.call_args.kwargs['provenance'],E.DiagnosticReceipt)
item=E.store().read()[w2['id']];assert item['status']=='actionable' and item['next_action']=='inspect_saved_diagnostic',item
live=json.load(open(D.STATE));kept=next(x for x in live['room_work']['open'] if x['id']==w2['id'])
assert kept['returns'] and 'collector checked' in kept['returns'][-1]['text'],kept
assert 'no rerun or outreach' in kept['next']
assert not g['NET'],g['NET']
print('PASS production tick authorizes only local inspection from a bound saved diagnostic receipt')

# Arrival inside the daily window is ingested even before the conversational hold.
st=json.load(open(D.STATE));w3=dict(w,id='RW-33333333',goal='ModelJSONError '+'c'*32,state='open',returns=[],asks=[],steps=[])
st['room_work']['open'].append(w3);E.store().enter(w3,'missing fixture',due+1);E.store().pause(w3['id'],due+E.DAY)
R.evidence_sync(st);D._save(D.STATE,st)
targets=E.store().read()[w3['id']]['targets']
pathlib.Path(targets[0]).write_text('arrived during posting hold')
pathlib.Path(targets[1]).write_text(json.dumps({'evidence_id':'c'*32}))
def forbidden_call(*a,**kw):raise AssertionError('paused tick must not call Slack or model')
with patch.object(D,'talking_with_gloria',return_value=2):
 out=D.tick(api=forbidden_call,think=forbidden_call,now=due+2)
assert out[0].startswith('holding:') and E.store().read()[w3['id']]['status']=='actionable',out
kept=next(x for x in json.load(open(D.STATE))['room_work']['open'] if x['id']==w3['id'])
assert kept['paused_until']==due+E.DAY and kept['returns']
print('PASS production tick persists immediate local arrival during conversational and item pauses without posting')
