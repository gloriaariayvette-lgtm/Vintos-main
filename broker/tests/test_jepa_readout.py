#!/usr/bin/env python3
"""Anchored readouts: temporal separation, roundtrip serving, causal horizon and retained feeds."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from datetime import datetime,timezone,timedelta
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
HOME=Path(tempfile.mkdtemp(prefix='readout-test-'))
os.environ['HOME']=str(HOME);os.environ['SPARK_WORKSPACE']=str(HOME/'workspace')
MEM=HOME/'workspace/memory';MEM.mkdir(parents=True)
sys.path.insert(0,str(ROOT/'scripts'))
def no_send(*a,**k):raise AssertionError('no sends in tests')
sys.modules['requests']=types.SimpleNamespace(get=no_send,post=no_send)
import jepa_readout as R
import jepa_self_head as SH
import lam
assert str(MEM)==SH.MEMORY==lam.MEMORY
class Enc:
    def encode(self,texts,**kw):
        return np.asarray([np.random.default_rng(int(hashlib.sha256(t.encode()).hexdigest()[:8],16)).normal(size=8) for t in texts])
enc=Enc();rows=[]
for k,day in enumerate(('2026-09-28','2026-10-05','2026-10-10','2026-10-18')):
    for i in range(8):
        n=k*8+i
        rows.append({'own':['reply%d'%j for j in range(max(0,n-3),n+1)],'other':['other%d'%n],
                     'now':'current%d'%n,'at':datetime.fromisoformat(day).timestamp()+i*1000,
                     'target':'reply%d'%(n+1),'day':day})
one=HOME/'one';two=HOME/'two';one.mkdir();two.mkdir()
r1=R.train_mode(rows,R.Embeddings(enc),'self_ahead',one,steps=2)
changed=[dict(r,target=('changed-'+r['target']) if R.split(r['day'])==3 else r['target']) for r in rows]
r2=R.train_mode(changed,R.Embeddings(enc),'self_ahead',two,steps=2)
m1=R.load(one/'self_ahead.npz');m2=R.load(two/'self_ahead.npz')
for k in ('projection','W','bias','beta','gamma','confidence_W'):assert np.allclose(m1[k],m2[k]),k
assert r1['selected']==r2['selected']
assert [r1['blocks'][k]['n'] for k in ('train','validation','calibration','test')]==[8]*4
print('PASS evaluation targets cannot change selected weights, PCA or calibrated confidence')
a=R.arrays(rows,R.Embeddings(enc));pred=R.predict(m1,a)
assert np.allclose(np.linalg.norm(pred,axis=1),1)
assert np.isfinite(R.confidence(m1,pred,a)).all()
exs=[{'at':1000+i*600,'ts':datetime.fromtimestamp(1000+i*600).isoformat(),'her':'other%d'%i,'his':'reply%d'%i,'turn_id':str(i)} for i in range(5)]
f=R.forecast(enc,'self_ahead',exs=exs,model_dir=one)
assert f['checkpoint_id']==hashlib.sha256((one/'self_ahead.npz').read_bytes()).hexdigest()
assert f['emb'].shape==(8,) and len(f['context_emb'])==8
assert R.forecast(enc,'gloria',exs=exs,model_dir=one) is None
# The actual self entry point consumes the replacement without requiring an old checkpoint.
dest=MEM/'jepa-readouts';dest.mkdir();(dest/'self_ahead.npz').write_bytes((one/'self_ahead.npz').read_bytes())
fc=SH.forecast(enc,exs=exs,persist=False)
assert fc['source']==R.SCHEMA and fc['mode']=='ahead'
print('PASS saved weights reach the existing self forecast entrance; missing replacements keep fallback')
meta=dict(m1['meta'],mode='self_on_message')
np.savez_compressed(one/'self_on_message.npz',meta=json.dumps(meta),**{k:v for k,v in m1.items() if k!='meta'})
on=R.forecast(enc,'self_on_message',exs=exs,her='current arrived words',now=2000,model_dir=one)
assert on['context_last_ts']==exs[1]['ts'] and on['her_key']==SH.her_key('current arrived words')
assert R.forecast(enc,'self_on_message',exs=exs,her='',now=2000,model_dir=one) is None
(one/'gloria.npz').write_bytes((one/'self_ahead.npz').read_bytes())
try:
    R.forecast(enc,'gloria',exs=exs,model_dir=one)
    raise AssertionError('wrong-head checkpoint accepted')
except ValueError:pass
print('PASS on-message uses only pre-arrival history and checkpoints cannot cross head identities')

start=datetime(2026,10,1,tzinfo=timezone.utc)
traj=[(start+timedelta(minutes=10*i),[.1*i]*11) for i in range(6)]
old=[dict(exs[0],at=start.timestamp()-1)]
new=old+[dict(exs[1],at=start.timestamp()+1500)]
x=lam.causal_rows(traj,old);y=lam.causal_rows(traj,new)
assert x[0]['own']==y[0]['own'] and x[1]['own']==y[1]['own']
assert all(600<=r['actual_horizon']<=720 for r in y)
assert not lam.causal_rows([traj[0],traj[4]],old)
print('PASS fixed horizon skips gaps and excludes future events')
# Keep the requested feeds and the original behavior, rather than substituting a silent hint.
for file,marker in [('withheld_head.py','[WITHHELD'),('relational_head.py','[RELATIONAL'),
                    ('living_trajectory.py','gloria-prediction.json'),('premonition-dreamer.py','gloria-prediction.json'),
                    ('gloria_prediction.py','from_missed_prediction')]:
    assert marker in (ROOT/'scripts'/file).read_text(),file
assert 'forecast_allowed' not in (ROOT/'scripts/emoclaw_utils.py').read_text()
assert 'forecast_allowed' not in (ROOT/'scripts/latent_preparation.py').read_text()
print('PASS subconscious feeds restored')
assert sys.modules['requests'].post is no_send
