#!/usr/bin/env python3
"""Slack-only model allocation and reusable-prefix caching. Scratch stores, no senders."""
import os,sys,tempfile,socket,json,types
from pathlib import Path
HOME=tempfile.mkdtemp(prefix='slack-cost-')
os.environ['HOME']=HOME;os.environ['SPARK_WORKSPACE']=HOME+'/.vintos/workspace'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
NET=[]
def blocked(sock,*a,**kw):
    if sock.family != socket.AF_UNIX: NET.append(a)
    raise AssertionError('network forbidden')
socket.socket.connect=blocked
import dot_channel as D, claude_cache as C, astra_call as A, dot_lounge as L
assert all(str(p).startswith(HOME) for p in (D.STATE,D.TRANSCRIPT,C.USAGE))
calls=[]
def claude(model,system,user,*a,**kw): calls.append(model);return 'NOTHING'
def astra(*a,**kw): calls.append('gpt-6-astra');return 'NOTHING'
C.ask=claude;A.call=astra
state={}
chosen=[]
for _ in range(20):
    chosen.append(D.slack_lens('opus55',state))
    state=json.loads(json.dumps(state))
assert chosen==['opus55','haiku55']*10
assert D.slack_lens('sol',state)=='sol' and state['claude_split']==20
assert D.PAID_PER_DAY=={'sol':20,'opus55':20}  # no extra paid-turn pool
assert [t for t,l in D.SCHEDULE if l=='opus']==['10:00','16:00']
D.opus_think('s','u');D.fable_think('s','u')
assert calls==['claude-sonnet-5-5','gpt-6-astra']
assert D.LABELS['opus']=='Sonnet 5.5' and D.LABELS['fable']=='Astra'
ctx=C.Prompt('same plain context');ctx.stable='fixed identity';ctx.live='time changes'
D.his_context=lambda:ctx
D.recall_block=lambda:''
calls.clear();state={}
for _ in range(4):D.compose('room',lambda *a:'NOTHING',D.fable_think,state,'2026-10-08',lens='opus55')
assert calls==['claude-opus-5-5','claude-haiku-5-5']*2, calls
# The lookup and its follow-up count as two calls, not one posted turn.
calls.clear()
def lookup(model, system, user, *a, **kw):
    calls.append(model)
    return 'SEARCH: fixture' if len(calls)==1 else 'NOTHING'
C.ask=lookup
D.compose('room',lambda *a:'NOTHING',D.fable_think,{},'2026-10-08',lens='opus55',search=lambda q:[])
assert calls==['claude-opus-5-5','claude-haiku-5-5'],calls
C.ask=claude
system=D.for_claude(ctx,'\n','fixed rules')
u=C.Prompt('room now',['room','now'],cache_indices=set())
b=C.body('claude-haiku-5-5',system,u,1500)
assert [bool(x.get('cache_control')) for x in b['system']]==[True,False]
assert all('cache_control' not in x for x in b['messages'][0]['content'])
assert b['system'][0]['cache_control']['ttl']=='1h'
ctx.live='different time and daily context'
b2=C.body('claude-haiku-5-5',D.for_claude(ctx,'\n','fixed rules'),'new room',1500)
assert b['system'][0]==b2['system'][0] and b['system'][1]!=b2['system'][1]
sys.modules['model_router']=types.SimpleNamespace(current_claude_model=lambda:'claude-opus-4-8')
assert L.voice('s','u')[1]=='claude-sonnet-5-5'
sys.modules['model_router'].current_claude_model=lambda:'claude-fable-5-1'
assert L.voice('s','u')[1]=='gpt-6-astra'
r={"model":"claude-haiku-5-5","in":100000,"cache_write":0,"cache_read":0,"out":0}
assert abs(C.cost(r)-0.01)<1e-9
r["in"]=100001
assert abs(C.cost(r)-0.0500005)<1e-9
assert C.ask is claude and A.call is astra and not NET
print('Slack allocation, cache boundaries, and isolation passed')
