#!/usr/bin/env python3
"""9 Oct regressions: equivalent lookups and oversized local Slack prompts. Fully isolated."""
import json,os,pathlib,socket,sys,tempfile,types
from datetime import datetime, timezone
root=pathlib.Path(__file__).resolve().parents[2]
home=tempfile.mkdtemp(prefix='lab-slack-followup-')
os.environ['HOME']=home;os.environ['SPARK_WORKSPACE']=home+'/workspace';os.environ['VINTOS_SECRETS']=home+'/secrets'
net=[]
def no_net(*a,**k):net.append(True);raise AssertionError('network forbidden')
socket.socket.connect=no_net
sys.path.insert(0,str(root/'scripts'))
import lab_repeats as L
import dot_channel as D
import chemistry_lab as C
assert all(str(p).startswith(home) for p in (L.LOOKUPS,L.SESSIONS,D.STATE,D.TRANSCRIPT,C.NOTEBOOK))
assert socket.socket.connect is no_net
q1='reviewed:true AND (protein_name:SLC26A2 AND reviewed:true AND taxonomy_id:9606)'
q2='taxonomy_id:9606 AND reviewed:true AND protein_name:"SLC26A2"'
assert L.lookup_key({'uniprot_query':q1}) == L.lookup_key({'source_query':{'source':'uniprot','query':q2}})
assert L.uniprot_key('gene:a OR gene:b') != L.uniprot_key('gene:a AND gene:b')
assert L.uniprot_key('gene:a AND NOT gene:b') != L.uniprot_key('gene:a AND gene:b')
assert L.uniprot_key('taxonomy_id:9606 AND gene:a') != L.uniprot_key('taxonomy_id:10090 AND gene:a')
os.makedirs(L.ROOT,exist_ok=True)
with open(L.LOOKUPS,'w') as f:
 f.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'lookup':'uniprot:'+q1.lower(),'words':[]})+'\n')
assert 'exact lookup' in L.repeat({'source_query':{'source':'uniprot','query':q2},'question':'Another wording'})
# Changing attached literature used to hide repeated reads of the same protein.
for i in range(5): C._append(C.NOTEBOOK, {'kind':'reflection','source_accessions':['P50443','PMID-'+str(i)]})
assert C.journal_source_saturated(['P50443'])
assert not C.journal_source_saturated(['NEW-PROTEIN'])
# A 32k overflow should be prevented before any request, with rules and newest message intact.
rules=D.rules_for('gemma')
system=D.for_claude('old context 😃 '*15000,'\n\n',rules)
user='old conversation '*8000+' LATEST: only say diagnostic-ok'
a,b=D.local_prompt(system,user,700)
assert rules in a and b.endswith('LATEST: only say diagnostic-ok')
assert len((a+b).encode('utf-8'))+700+2048 <= 32000
assert 'older context omitted' in a
assert D.local_prompt('short system','short user',700) == ('short system','short user')
sent=[]
def post(url,**kw):
 sent.append(kw['json']);return types.SimpleNamespace(json=lambda:{'choices':[{'message':{'content':'diagnostic-ok'}}]})
sys.modules['requests']=types.SimpleNamespace(post=post)
assert sys.modules['requests'].post is post
assert D.local_think(system,user)=='diagnostic-ok'
payload=sent[0]
assert sum(len(m['content'].encode('utf-8')) for m in payload['messages'])+payload['max_tokens']+2048 <=32000
assert not net
print('PASS: equivalent-query replay, historical keys, OR/NOT separation, 32k prompt bound, intact rules, no network')
