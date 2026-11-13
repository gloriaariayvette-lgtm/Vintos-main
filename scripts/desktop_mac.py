"""Native iMac UI adapter. All execution remains on the selected Mac; never falls back to Aegis."""
import base64,json,shlex
import browser_mac

def rpc(op,**args):
 c=browser_mac.settings();cmd='exec '+shlex.quote(c['python'])+' '+shlex.quote(c['root']+'/native-client.py')
 r=browser_mac._ssh(cmd,input=json.dumps({'op':op,**args}).encode(),capture_output=True,timeout=35)
 if r.returncode:raise RuntimeError('iMac native bridge unavailable')
 d=json.loads(r.stdout.decode().strip().splitlines()[-1])
 if not d.get('ok'):raise RuntimeError('iMac '+str(d.get('error','native control failed'))+' '+json.dumps(d.get('permissions',{})))
 return d
class RemoteMacBackend:
 def __init__(self):
  p=rpc('permissions')['permissions']
  if not all(p.values()):raise RuntimeError('iMac needs macOS Accessibility and Screen Recording approval for Vintos Desktop Control: '+json.dumps(p))
 def describe(self):return rpc('describe')
 def capture(self):
  d=rpc('capture');return base64.b64decode(d['jpeg']),tuple(d['image_size']),tuple(d['desktop_size'])
 def execute(self,action,image_size):return rpc('execute',action=action,image_size=list(image_size))['result']
