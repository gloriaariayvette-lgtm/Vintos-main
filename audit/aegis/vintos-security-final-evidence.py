import os,json,pathlib,subprocess,collections,time,re
H=pathlib.Path.home();r={'at':time.time()}
def run(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=20);return {'rc':p.returncode,'out':p.stdout[:80000]}
r['user_services_and_timers']=run(['systemctl','--user','list-units','--all','--type=service,timer,socket,path','--no-legend','--plain'])
r['system_timers']=run(['systemctl','list-timers','--all','--no-legend'])
r['actual_import_versions']={}
for name in ['requests','urllib3','cryptography']:
 m=__import__(name);r['actual_import_versions'][name]={'version':m.__version__,'file':m.__file__}
r['provider_logs_summary']={}
for file in [H/'.vintos/logs/anthropic-usage.jsonl',H/'.vintos/logs/openai-usage.jsonl']:
 keys=collections.Counter();minutes=collections.Counter();recent=0
 try:
  for line in file.open():
   try:d=json.loads(line)
   except ValueError:continue
   if not isinstance(d,dict):continue
   keys.update(d.keys());stamp=d.get('at',d.get('ts',d.get('time','')))
   try:
    from datetime import datetime
    epoch=float(stamp) if isinstance(stamp,(int,float)) else datetime.fromisoformat(stamp).timestamp()
   except (TypeError,ValueError):continue
   if epoch>time.time()-86400:minutes[int(epoch//60)]+=1;recent+=1
  r['provider_logs_summary'][file.name]={'field_names':list(keys),'calls_last24h':recent,'max_per_minute_last24h':max(minutes.values(),default=0)}
 except OSError:r['provider_logs_summary'][file.name]={'readable':False}
r['monitor_units']={}
for scope in [[],['--user']]:
 q=run(['systemctl']+scope+['list-unit-files','--no-legend'])
 r['monitor_units']['user' if scope else 'system']={'rc':q['rc'],'matching':[l for l in q['out'].splitlines() if re.search('audit|fail2ban|aide|backup|restic|borg|rsyslog|journal|security|watch|sweep',l,re.I)]}
r['log_storage_settings']={}
for p in [pathlib.Path('/etc/systemd/journald.conf')]+list(pathlib.Path('/etc/systemd/journald.conf.d').glob('*.conf')):
 try:r['log_storage_settings'][str(p)]=[l.strip() for l in p.read_text().splitlines() if re.match(r'^\s*(Storage|SystemMaxUse|RuntimeMaxUse|ForwardToSyslog|ForwardToConsole|Seal)=',l)]
 except OSError:pass
r['offhost_log_configs']=[]
for p in [pathlib.Path('/etc/rsyslog.conf')]+list(pathlib.Path('/etc/rsyslog.d').glob('*.conf')):
 try:
  text=p.read_text();r['offhost_log_configs'].append({'path':str(p),'remote_action_present':bool(re.search(r'(?m)^\s*[^#\n].*(?:@@|omfwd|omrelp)',text))})
 except OSError:pass
r['ssh_recent_summary']={}
p=run(['journalctl','-u','ssh.service','--since','24 hours ago','-o','json','--no-pager'])
counts=collections.Counter();addresses=collections.Counter()
for line in p['out'].splitlines():
 try:msg=json.loads(line).get('MESSAGE','')
 except ValueError:continue
 if not isinstance(msg,str):continue
 for label,needle in [('accepted','Accepted '),('failed','Failed '),('invalid','Invalid user')]:
  if needle in msg:counts[label]+=1
 m=re.search(r'Accepted .*? from ([0-9a-fA-F:.]+) port',msg)
 if m:addresses[m.group(1)]+=1
r['ssh_recent_summary']={'rc':p['rc'],'counts':dict(counts),'accepted_addresses':dict(addresses),'truncated':len(p['out'])>=80000}
print(json.dumps(r,indent=2))
