#!/usr/bin/env python3
import os,sys,tempfile,importlib.util,json,time
from pathlib import Path
R=[]
def check(name,ok):R.append(bool(ok));print(('PASS ' if ok else 'FAIL ')+name)
repo=Path(__file__).resolve().parents[2];sys.path.insert(0,str(repo/'scripts'))
root=Path(tempfile.mkdtemp());os.environ['HOME']=str(root)
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
M=load('music',repo/'scripts/dream-music.py');M.MUSIC=str(root/'music');Path(M.MUSIC).mkdir();M.LOG=str(Path(M.MUSIC)/'music.json')
M.generate=lambda *a,**k:(_ for _ in ()).throw(AssertionError('recovery must not generate'))
M._landing_begin('task-1','Saved task',0,{'source':'prompt.md','style':'fixture'})
M.poll=lambda tid:[]
check('unfinished render remains pending',M.resume_landings()==[] and len(M.pending_landings())==1)
M.poll=lambda tid:[{'file':'fixture://bytes','duration':2}]
def download(url,path):Path(path).write_bytes(b'fixture audio');return True
M.dl=download
check('recovery polls and lands the existing task',M.resume_landings()==['task-1'])
check('recovered task keeps source metadata',M.load_log()['generated'][0]['source']=='prompt.md' and M.load_log()['processed_files']==['prompt.md'])
check('recovery is idempotent',M.resume_landings()==[] and len(M.load_log()['generated'])==1)
# Read coverage is an interval union for a specific file revision.
S=load('study',repo/'bin/study_chat.py');source=root/'source';source.mkdir();file=source/'a.py';file.write_text('a\nb\nc\nd\n')
S.ROOTS={'src':str(source)}
state={};S._session=lambda:state;S._session_save=lambda d:state.update(d);S.session_open=lambda what:state
S.session_note_read('src/a.py',3,4,4)
check('last line alone does not mean whole file read',not state['cursor']['src/a.py']['complete'])
S.session_note_read('src/a.py',1,2,4)
check('joined intervals establish complete coverage',state['cursor']['src/a.py']['complete'])
file.write_text('changed\nb\nc\nd\n')
check('editing a covered file invalidates coverage',S.session_coverage()['read_whole']==[])
# Prompt renderers keep stores byte-identical; counters move after actual admission.
import joke_fermentation as J,curiosity_debt as C,unsaid_questions as U,unsaid_frontier as F
now=time.time()
J.F=str(root/'jokes.json');Path(J.F).write_text(json.dumps([{'id':'j','seed':'a particular funny line','ripe_at':now-10,'fired':False}]))
C.PATH=str(root/'curiosity.json');Path(C.PATH).write_text(json.dumps([{'id':'q','question':'What is beside the lamp?','pull':.9,'created':now-4000}]))
U.F=str(root/'unsaid.json');Path(U.F).write_text(json.dumps([{'id':'u','q':'Did it rain?','turns':5,'created':now,'asked':False}]))
F.FRONTIER=str(root/'frontier.json');Path(F.FRONTIER).write_text(json.dumps([{'lineage_id':'l','state':'voiced_intent','his_word':'I want to speak','intention_surfaced':0}]))
for path,fn in [(J.F,J.callback_block),(C.PATH,C.block),(U.F,U.block),(F.FRONTIER,F.block)]:
 before=Path(path).read_bytes();text=fn();check('pure preview '+Path(path).name,bool(text) and Path(path).read_bytes()==before)
text=J.callback_block();J.admit_block(text,'turn');J.admit_block(text,'turn')
check('callback admission is counted once',json.loads(Path(J.F).read_text())[0]['offer_count']==1)
# Mixed-checkpoint histories cannot be relabelled as the current checkpoint.
import types,calibration as CAL
from datetime import datetime
CAL.MODEL=str(root/'model.pt');Path(CAL.MODEL).write_bytes(b'fixture weights');os.utime(CAL.MODEL,(now-1000,now-1000))
checkpoint=CAL.checkpoint_fingerprint()
sys.modules['jepa_predictor']=types.SimpleNamespace(encoder=lambda:types.SimpleNamespace(encode=lambda *a,**k:[[1,0],[0,1]]))
A=load('audit',repo/'scripts/jepa_calibration_audit.py');A.MEM=str(root);A.HIST=str(root/'predictions.jsonl');A.OUT=str(root/'audit.json')
history=[];ledger=[]
for i in range(30):
 ts=now-500+i
 history.append({'ts':ts,'iso':datetime.fromtimestamp(ts).isoformat(),'checkpoint_id':checkpoint if i<9 else 'other',
                 'gloria':{'confidence':.5,'decode_similarity':.2,'emb':[1,0]},'self':{'confidence':.5,'decode_similarity':.2,'emb':[0,1]}})
 ledger.append({'timestamp':datetime.fromtimestamp(ts+.5).isoformat(),'gloria':'heard','vintos':'said'})
Path(A.HIST).write_text(''.join(json.dumps(h)+'\n' for h in history));(root/'interaction-ledger.json').write_text(json.dumps(ledger))
A.main();audit=json.loads(Path(A.OUT).read_text())
check('audit excludes predictions from other weights',audit['n_joined']==9 and audit['checkpoint']==checkpoint)
check('constant confidence is not fabricated rank correlation',audit['g']['monotonicity_conf_vs_err'] is None)
print('%d/%d'%(sum(R),len(R)));sys.exit(0 if all(R) else 1)
