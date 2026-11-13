"""Jev's existing CDP browser interface, executed on the owner-configured iMac over SSH."""
import json,os,shlex,subprocess
from pathlib import Path
import browser_winpy

def settings():
 p=Path(os.environ.get('SPARK_WORKSPACE',str(Path.home()/'.vintos/workspace')))/'memory/desktop-target.json'
 try:return json.loads(p.read_text())
 except FileNotFoundError:return {}
def selected():return settings().get('target')=='imac'
def _ssh(command,**kw):
 c=settings();return subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',c['ssh_host'],command],**kw)
def available():
 c=settings()
 if c.get('target')!='imac':return False
 r=_ssh('test -x '+shlex.quote(c['python'])+' && test -f '+shlex.quote(c['root']+'/browser_helper.py'),capture_output=True,timeout=10)
 return r.returncode==0
def call(op,timeout=60,**kw):
 c=settings();cmd='exec '+shlex.quote(c['python'])+' '+shlex.quote(c['root']+'/browser_helper.py')
 r=_ssh(cmd,input=json.dumps({'op':op,'port':9222,'max_elements':80,'max_text':6000,**kw}).encode(),capture_output=True,timeout=timeout)
 if r.returncode:raise RuntimeError('iMac browser helper failed: '+r.stderr.decode(errors='replace').strip().splitlines()[-1][:200])
 return json.loads(r.stdout.decode().strip().splitlines()[-1])
class MacBrowser(browser_winpy.EdgeBrowser):
 def _tab(self):
  ids=[x['id'] for x in call('tabs',timeout=15)]
  if self.tab not in ids:self.tab=ids[0] if ids else None
  return self.tab
 def _call(self,op,timeout=60,**kw):
  d=call(op,timeout=timeout,tab=self._tab(),**kw);s=d.get('state') if isinstance(d,dict) else None
  if isinstance(s,dict) and s.get('tab'):self.tab=s['tab']
  elif isinstance(d,dict) and d.get('tab'):self.tab=d['tab']
  return d
 def ensure(self):return call('ensure',timeout=35)
