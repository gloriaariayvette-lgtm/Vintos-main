#!/usr/bin/env python3
"""Multi-pass room workflow: real planner/gate, fake models, Slack and every sender/store."""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types

HOME = tempfile.mkdtemp(prefix='room-work-')
os.environ['HOME'] = HOME
os.environ['SPARK_WORKSPACE'] = HOME + '/workspace'
os.environ['VINTOS_SECRETS'] = HOME + '/secrets'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
NETWORK = []
def no_network(*a, **kw):
    NETWORK.append('attempt'); raise AssertionError('suite may not send')
socket.socket.connect = no_network
socket.create_connection = no_network
subprocess.Popen = no_network
import urllib.request
urllib.request.urlopen = no_network
import room_work as W
import dot_channel as D

# Stubs installed before tick's lazy imports; no provider or real house is reachable.
modules = {
 'campaign': dict(expire_if_due=lambda: False),
 'promise_keeper': dict(threads=lambda: [], block=lambda: '', resolve=lambda *a: None),
 'make_thing': dict(untold=lambda: []),
 'lab_asks': dict(pending=lambda: []),
 'lab_keepers': dict(threads=lambda: [], CHECK=__import__('re').compile(r'CHECK: (K-\w+)(.*)')),
 'line_prospect': dict(from_room=lambda *a: ('',0), ask_the_room=lambda: ('','')),
 'lab_lines': dict(from_slack=lambda *a, **kw: {'id':'L-test'}, slack_block=lambda: ''),
}
for name, funcs in modules.items(): sys.modules[name] = types.SimpleNamespace(**funcs)
D.talking_with_gloria = lambda *a: None
D.results_pass = lambda *a, **kw: []
D.promises_pass = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('private journal is not room work'))
D.work_context = lambda: 'Operational Lab work only'
D.his_context = lambda: (_ for _ in ()).throw(AssertionError('private context was read'))
D.room_line = lambda *a: 'dot tests remaining: 10'
D.kickoff_due = lambda *a: False
D.SCHEDULE = []; D.ROTATION = ('gemma',)
D.agent_ids = lambda *a: {}
D.journal = lambda *a, **kw: True
D._guarded = lambda t: ['credential'] if 'SECRET_TEST_VALUE' in t else []
D.keep_parts_lists = lambda *a: []
D.campaign_step = no_network
D.to_wants = no_network
D.look_at_files = no_network
D.local_think = no_network
D.fable_think = no_network
D.sol_think = no_network
D.opus_think = no_network
D.grok_think = no_network
assert all(str(getattr(D,k)).startswith(HOME) for k in ('STATE','TRANSCRIPT','FOCUS_FILE','PAUSE_FILE','RESULTS_STATE','RESULTS_LOG'))
assert D.to_wants is no_network and urllib.request.urlopen is no_network
assert socket.socket.connect is no_network and subprocess.Popen is no_network
assert D.local_think is no_network and D.campaign_step is no_network

class Slack:
 def __init__(self): self.rows=[]; self.posts=[]; self.n=100; self.fail=False
 def add(self, text, user=None, thread=None):
  self.n+=1; r={'ts':str(self.n)+'.000000','user':user or D.DOT,'text':text}
  if thread:
   r['thread_ts']=thread
   for root in self.rows:
    if root['ts']==thread: root['reply_count']=root.get('reply_count',0)+1;root['latest_reply']=r['ts']
  self.rows.append(r); return r['ts']
 def __call__(self, method, params):
  if method=='auth.test':return {'user_id':'SELF'}
  if method=='conversations.history':return {'messages':list(reversed([r for r in self.rows if not r.get('thread_ts')]))}
  if method=='conversations.replies':return {'messages':[r for r in self.rows if r.get('thread_ts')==params['ts'] or r['ts']==params['ts']]}
  if method=='chat.postMessage':
   if self.fail: raise RuntimeError('uncertain transport')
   self.posts.append(params); return {'ok':True,'ts':self.add(params['text'],'SELF',params.get('thread_ts'))}
  raise AssertionError(method)

slack=Slack(); calls=[]; next_plan={}
def writer(system,user):
 calls.append((system,user)); return json.dumps(next_plan)
def tick(now=1000, day='2026-10-05'):
 return D.tick(api=slack, think=writer, fable=no_network, now=now, today=day,
               eyes=lambda *a:'', lenses={k:writer for k in ('sol','opus','opus55','fable','grok')})
def state(): return json.load(open(D.STATE))
def save(s): D._save(D.STATE,s)
def reset():
 global slack
 slack=Slack(); save({'self':'SELF','since':100,'date':'2026-10-05','sent':0,'openers':0,'slots_done':[], 'last_activity':100})
 Path(D.TRANSCRIPT).write_text('')
reset()
next_plan={'move':'handoff','goal':'Diagnose the Lab intake 403 without changing authority',
 'done_when':'Identify the exact rejecting guard from retained evidence', 'owner':'dot',
 'step':'Read the sender and receiver once; locate the exact refusal guards',
 'deliverable':'Redacted paths and line numbers, separating proven from unconfirmed',
 'use_for':'choose one discriminating check rather than repeat the same inspection'}
slack.add('Please diagnose the Lab delivery failure',user='GLORIA')
tick(); w=state()['room_work']['active']; ident=w['id']; root=w['thread']
assert w['phase']=='waiting' and w['owner']=='dot' and len(slack.posts)==1
assert '[RW-' in slack.posts[0]['text'] and 'Return:' in slack.posts[0]['text']
assert root in state()['threads']
n=len(calls); tick(1100); assert len(calls)==n and len(slack.posts)==1
# Across midnight no lost assignment, no duplicate ping.
tick(1200,'2026-10-06'); assert state()['room_work']['active']['id']==ident and len(calls)==n
# Wrong peer cannot satisfy it even when using the work ID.
s=state(); W.receive(s,[{'who':'agent','name':'Muse','ts':'104','thread':root,'text':'['+ident+'] done'}],1300)
assert not s['room_work']['active']['results']
# Same assigned peer but another thread must not satisfy it.
W.receive(s,[{'who':'dot','ts':'104','thread':'999','text':'unrelated reply'}],1300)
assert not s['room_work']['active']['results']
# Actual result arrives; no model claims needed to persist it.
text='The header syntax matches. Refused, ValueError and KeyError all become 403; which guard fired is unconfirmed.'
ts=slack.add(text,thread=root)
next_plan={'move':'handoff', 'owner':'dot','step':'Read the sender and receiver once; locate the exact refusal guards',
 'deliverable':'Redacted paths and line numbers, separating proven from unconfirmed','use_for':'pick the next check',
 'evidence':[{'ref':ts,'quote':'The header syntax matches.'}], 'decision':'The sender already uses the correct header; we need the rejecting guard.'}
tick(1400,'2026-10-06'); assert len(slack.posts)==1
assert 'already handed off' in state()['room_work']['last_gate']
# Same read is suppressed, not converted to empty agreement or a fake action.
next_plan={'move':'use','evidence':[{'ref':ts,'quote':'The header syntax matches.'}],
 'decision':'Malformed response parsing cannot explain a receiver HTTP 403; inspect its guard evidence next.',
 'next':'Check the retained intake queue count before considering a token mismatch'}
tick(1500,'2026-10-06'); assert len(slack.posts)==2
w=state()['room_work']['active']; assert w['results'][0]['used'] and w['phase']=='ready'
assert slack.posts[-1]['thread_ts']==root and 'Evidence:' in slack.posts[-1]['text']
assert 'Malformed response' in w['decisions'][-1]['decision']
# Next lens receives the same goal, decision and next own step; no topic restart.
next_plan={'move':'handoff','owner':'dot','step':'Count unfinished intake reports from the local queue without HTTP requests',
 'deliverable':'Retained queue count and timestamp, no tokens or endpoint contact',
 'use_for':'distinguish the four-report guard from an unproven token mismatch'}
tick(1600,'2026-10-06'); assert len(slack.posts)==3
assert ident in calls[-1][1] and 'Malformed response' in calls[-1][1] and 'queue count' in calls[-1][1]
assert state()['room_work']['active']['goal'].startswith('Diagnose')
# Fresh result is used to take an actual permitted action, not only another request.
ts2=slack.add('The retained intake queue contains four unfinished reports at 02:18 UTC.',thread=root)
next_plan={'move':'act','message':'LINE L-test: Four retained intake reports meet the queue limit; token mismatch remains unconfirmed.',
 'evidence':[{'ref':ts2,'quote':'The retained intake queue contains four unfinished reports'}],
 'decision':'Keep the access check; the queue is a concrete candidate and token mismatch is still unconfirmed.'}
tick(1700,'2026-10-06'); assert len(slack.posts)==4
assert state()['room_work']['active']['phase']=='review'
assert any('slack line' in x or 'line' in x for x in state()['room_work']['active']['last_receipt']['dispatch'])
# Dispatch does not count as a completed goal. It must be used as evidence next.
assert not state()['room_work']['history']
# Unrelated subject, invented reference, copied evidence, or prose-only agreement is held.
s=state()
for p in [dict(move='use',goal='Go make a completely different music piece',decision='Different now'),
          dict(move='use',evidence=[dict(ref='invented',quote='The queue contains four reports')],decision='A concrete diagnosis based on evidence'),
          dict(move='act',message='Good, that makes sense. Next pass.'),
          dict(move='handoff',owner='dot',step='Do something useful',deliverable='Anything you find',use_for='something later')]:
 assert W.validate(copy.deepcopy(s),p)
assert W.parse('Agreed, next pass.')[0] is None
# Result + finish is retained as accepted report, never independent verification.
r=s['room_work']['active']['results'][-1]
p={'move':'use','evidence':[{'ref':r['ref'],'quote':r['text'][:40]}],
 'decision':'This records the candidate guard, not proof of which guard rejected the historical request.', 'finish':True, 'acceptance':'The line records the retained queue count as a candidate, not a proven historical guard.'}
assert 'not completion evidence' in W.validate(s,p)
# A separate, attributed peer result can be accepted; it is still explicitly a report.
s['room_work']['active']['results'].append(dict(ref='peer:verified', owner='dot', text='Retained refusal code is queue_limit in the original request receipt.', used=False))
p['evidence']=[dict(ref='peer:verified', quote='Retained refusal code is queue_limit')]
p['decision']='Use the retained queue_limit refusal instead of inferring a token or header failure.'
p['acceptance']='The original request receipt names queue_limit, satisfying the exact-guard criterion.'
assert not W.validate(s,p)
W.prepare(s,p,1800); W.finish(s,{'ts':'999.0'},1801,[],'Recorded candidate, not proven root cause')
assert s['room_work']['active'] is None and s['room_work']['history'][-1]['phase']=='accepted_report'
# A stalled peer creates one timeout for a different check, not repeated pings.
stalled=copy.deepcopy(s); stalled['room_work']['active']=copy.deepcopy(w)
stalled['room_work']['active'].update(phase='waiting',check_after=2000,asked_ts='120')
stalled['_work_now']=2001
assert not W.waiting(stalled,[])
assert stalled['room_work']['active']['results'][-1]['ref']=='timeout:120'
count=len(stalled['room_work']['active']['results']);W.waiting(stalled,[])
assert len(stalled['room_work']['active']['results'])==count
# Crash before Slack acknowledgement leaves uncertainty and cannot resend blindly.
reset(); next_plan={'move':'handoff','goal':'Verify one phage repository before using it',
 'done_when':'A pinned README identifies supported genome input and limitations','owner':'grokbot',
 'step':'Find the official repository and its README for myRT',
 'deliverable':'A full URL and quoted supported input formats', 'use_for':'decide whether it fits the standing line'}
slack.add('Look up this tool',user='GLORIA'); slack.fail=True
try: tick(2000)
except RuntimeError:pass
else: raise AssertionError('expected transport failure')
assert state()['room_work']['active']['phase']=='uncertain'
n=len(calls);slack.fail=False;tick(2100);assert len(calls)==n
# Secrets cannot enter pending record, Slack or action dispatch.
reset();next_plan={'move':'handoff','goal':'Review a configuration without credentials',
'done_when':'Name the exact guard without printing any secret','owner':'dot','step':'Read SECRET_TEST_VALUE from the file',
'deliverable':'A redacted report with only guard names','use_for':'choose the next bounded local check'}
slack.add('Check config',user='GLORIA');tick(2200)
assert not slack.posts and not state()['room_work']['active']
# A first-line DO must still dispatch after the work ID is attached.
reset(); handed=[]
D.to_wants=lambda want, plan: (handed.append(want) or "handed to his wants: want-1")
next_plan={'move':'act','goal':'Make a new image for a protein comparison figure',
'done_when':'One generated figure exists for the requested comparison', 'message':'DO: I want a labeled comparison figure for these protein folds'}
slack.add('Make the comparison figure',user='GLORIA');tick(2300)
assert len(handed)==1 and 'DO:' not in slack.posts[-1]['text']
assert state()['room_work']['active']['phase']=='review'
D.to_wants=no_network
# Real tool return is available as evidence; an invented tool result is not.
p={'move':'act','message':'The two structures use different chains.',
 'goal':'Compare the two structure coordinate mappings', 'done_when':'Explain whether both outputs modeled the same chain',
 'evidence':[{'ref':'tool:current','quote':'chain A has 88 resolved residues'}],
 'decision':'Compare chain A to A; whole-complex RMSD is not a valid comparison.'}
assert W.validate({},p)
assert not W.validate({},p, 'chain A has 88 resolved residues; chain B has 0')
# Bounded work metadata cannot bypass the action lane or relational gate.
p['message']='CAMPAIGN MOVE: advance: relationship';assert W.validate({},p,'chain A has 88 resolved residues')
assert NETWORK==[], NETWORK
assert all(str(getattr(D,k)).startswith(HOME) for k in ('STATE','TRANSCRIPT','RESULTS_STATE','RESULTS_LOG'))
print('PASS room collaboration: handoff -> correlated return -> decision -> next step -> store mark; isolation asserted')
