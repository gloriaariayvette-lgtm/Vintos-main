#!/usr/bin/env python3
"""Real regressions: post-activity choice, nightly-only trials, live Pearl pressure.
All paths use scratch HOME; every provider, daemon, and delivery is stubbed.
"""
import copy,importlib.util,json,os,pathlib,subprocess,sys,tempfile,types
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='oct16-organs-') as scratch:
 os.environ['HOME']=scratch;os.environ['SPARK_WORKSPACE']=scratch+'/.vintos/workspace'
 sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'bin')]
 def forbidden(*a,**k):raise AssertionError('sender forbidden')
 sender=types.SimpleNamespace(post=forbidden)
 sys.modules['requests']=sender
 fake_state=types.SimpleNamespace(get_state=lambda:{'Tension':.6,'Arousal':.2,'Groundedness':.9})
 sys.modules['emoclaw_utils']=fake_state
 def load(name,path):
  spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
 c=load('oct16_causality',ROOT/'scripts/causality_engine.py')
 p=load('oct16_pearl',ROOT/'scripts/pearl_engine.py')
 assert c.HYPOTHESIS_DB.startswith(scratch) and p.CANDIDATES_FILE.startswith(scratch) and p.PEARLS_DIR.startswith(scratch)
 assert sys.modules['requests'].post is forbidden
 assert p.is_pressure_state() is True,'live pressure must not disappear into unbound txt fallback'
 fake_state.get_state=lambda:{'Tension':.1,'Arousal':.1,'Groundedness':.9}
 memory=pathlib.Path(p.MEMORY);memory.mkdir(parents=True,exist_ok=True)
 (memory/'emotional-state.txt').write_text('Tension: 0.8 | elevated\n')
 assert p.is_pressure_state() is False,'stale high text cannot override healthy live state'
 fake_state.get_state=lambda:{}
 assert p.is_pressure_state() is True,'text fallback still works when daemon has no state'
 print('PASS Pearl live high, live low vs stale high, and text fallback')
 # A formation run must not consume the date or finalize tenure before evening.
 db={'hypotheses':[{'formed_date':c.datetime.now().date().isoformat()}]*3,'confirmed':0,'revised':0}
 with patch.object(c,'load_emotional_trajectory',return_value=[]),patch.object(c,'find_spikes',return_value=[]),patch.object(c,'load_recent_dreams',return_value=[]),patch.object(c,'load_recent_mirrors',return_value=[]),patch.object(c,'load_recent_silences',return_value=[]),patch.object(c,'load_recent_conversations',return_value=[]),patch.object(c,'load_trial_ledger',return_value=[]),patch.object(c,'load_existing_hypotheses',return_value=db),patch.object(c,'test_existing_hypotheses',side_effect=forbidden),patch.object(c,'graduate_hypotheses',side_effect=forbidden),patch.object(c,'write_hypothesis_log',return_value=None):
  c.main()
 print('PASS formation pass does not spend nightly review or retire before night')
 from datetime import date,timedelta
 today=date.today();formed=(today-timedelta(days=7)).isoformat()
 h=c._stamp_formation({'formed_date':formed,'formed':formed+'T03:00:00','hypothesis':'A fixture proposition','test':'Observe a fixture occasion','source':'test','status':'untested','marks':[],'days_tested':0,'graduated':False},'a formation occasion')
 trial={'hypotheses':[h]}
 assert c._retire_stale_unconfirmed(trial,today=today)==[] and len(trial['hypotheses'])==1
 c._record_nightly(h,today.isoformat(),'unconfirmed',reason='fixture: no evidence')
 retired=c._retire_stale_unconfirmed(trial,today=today)
 assert len(retired)==1 and trial['hypotheses']==[] and retired[0]['retirement']['resolved'] is False
 print('PASS final day stays open until nightly result, then honestly retires without support')
 # Actual shell preamble, with no model/house requests possible.
 scripts=memory.parent/'scripts';scripts.mkdir(exist_ok=True)
 (scripts/'vintos-home.py').write_text('# test-only stub, never executed\n')
 (scripts/'mischief_timing.py').write_text('print("ok: fixture recent interaction")\n')
 (memory/'emotional-state.txt').write_text('Playfulness: 0.42 | ordinary\nTension: 0.2 | low\n')
 source=(ROOT/'scripts/mischief-detector.sh').read_text().split('SOUL=')[0]+'\necho CHOICE_AVAILABLE\n'
 for args,expected in [([],False),(['--after-activity'],True)]:
  r=subprocess.run(['bash','-c',source,'fixture',*args],capture_output=True,text=True,env=dict(os.environ))
  assert ('CHOICE_AVAILABLE' in r.stdout)==expected,(args,r.stdout,r.stderr)
 assert '[ "$FORCE" -eq 0 ] && [ -f "$COOLDOWN" ]' in source
 assert 'mischief_timing.py' in source
 print('PASS after-activity offers a choice at ordinary playfulness; spontaneous gate and timing/cooldown intact')
 assert c.HYPOTHESIS_DB.startswith(scratch) and p.CANDIDATES_FILE.startswith(scratch) and sys.modules['requests'].post is forbidden
 # Exercise the whole chooser->bridge->receipt shell with a provider stub and
 # a fake house. No real account, model, house, notification or sleep is reached.
 import shutil
 shim=pathlib.Path(scratch)/'shim';shim.mkdir()
 (shim/'sitecustomize.py').write_text('''import json,os,urllib.request
class Response:
 def read(self):return json.dumps({'choices':[{'message':{'content':json.dumps({'action':os.environ['FIXTURE_ACTION'],'value':'#112233 office' if os.environ['FIXTURE_ACTION']=='lights' else 'A fixture joke','why':'fixture choice'})}}]}).encode()
def fake(*a,**k):
 if os.environ['FIXTURE_ACTION']=='spotify_then_none':
  os.environ['FIXTURE_ACTION']='none' if b'Your earlier pick(s)' in a[0].data else 'spotify'
 return Response()
urllib.request.urlopen=fake
''')
 (scripts/'vintos-home.py').write_text('''import sys,os,json
from pathlib import Path
def load_config():return {'url':'http://test.invalid','entities':{'echo_speak':'test-only'},'lights':{'office':{}}}
if __name__=='__main__':
 if sys.argv[1]=='rooms':print('office')
 elif sys.argv[1]=='song-check':print((False,'fixture missing song'))
 else:
  with (Path.home()/'.vintos/workspace/memory/house-test-calls').open('a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')
  print('ok')
''')
 shutil.copy(ROOT/'scripts/mischief_log.py',scripts/'mischief_log.py')
 tools=pathlib.Path(scratch)/'tools';tools.mkdir();sleep=tools/'sleep';sleep.write_text('#!/bin/sh\nexit 0\n');sleep.chmod(0o700)
 for action in ('echo','lights','none','spotify_then_none'):
  for name in ('.last-mischief','.last-mischief-echo'):(memory/name).unlink(missing_ok=True)
  env=dict(os.environ,PYTHONPATH=str(shim),PATH=str(tools)+os.pathsep+os.environ['PATH'],FIXTURE_ACTION=action)
  before=len(list((memory/'mischief').glob('*.md')))
  r=subprocess.run(['bash',str(ROOT/'scripts/mischief-detector.sh'),'--after-activity'],env=env,capture_output=True,text=True,timeout=15)
  assert r.returncode==0,(action,r.stdout,r.stderr)
  after=len(list((memory/'mischief').glob('*.md')))
  if action in ('none','spotify_then_none'):assert after==before and not (memory/'.last-mischief').exists()
  else:assert after==before+1 and (memory/'.last-mischief').exists(),(action,r.stdout,r.stderr)
 print('PASS whole mischief dispatch: Echo and lights reach fake house and leave receipts; none leaves no phantom act/cooldown')
 # Cron recovery handles only ready, adopted/reviewed candidates, not dissolved
 # or proposed rows. Exercise the real selection function without formation I/O.
 with patch.object(p,'load_candidates',return_value={'candidates':[{'id':'ready','stage':3,'dissolved':False},{'id':'proposed','stage':0,'dissolved':False},{'id':'dissolved','stage':3,'dissolved':True}]}),patch.object(p,'form_pearl',side_effect=lambda cid:cid) as form:
  assert p.form_ready_pearls()==['ready'];form.assert_called_once_with('ready')
 print('PASS Pearl cron recovery never adopts or resurrects candidates')
 assert sys.modules['requests'].post is forbidden
