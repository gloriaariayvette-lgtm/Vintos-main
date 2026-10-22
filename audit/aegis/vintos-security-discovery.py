import os,json,subprocess,pathlib,stat,re,hashlib,time,collections
H=pathlib.Path.home(); W=H/'.vintos/workspace'
def run(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=25); return {'rc':p.returncode,'out':p.stdout[:100000]}
def names(args): return run(args)
r={'at':time.time(),'host':run(['hostname'])['out'].strip(),'source_revision':run(['git','-C',str(H/'Vintos-main'),'rev-parse','HEAD']), 'listeners':run(['ss','-H','-lntu']), 'user_units':names(['systemctl','--user','list-units','--all','--no-legend','--plain']), 'user_unit_files':names(['systemctl','--user','list-unit-files','--no-legend']), 'system_services':names(['systemctl','list-units','--type=service','--state=running','--no-legend','--plain']), 'timers':names(['systemctl','--user','list-timers','--all','--no-legend']), 'identity':run(['id']), 'sudo_noninteractive':run(['sudo','-n','-l'])}
# sudo listing is redacted to capability names, not command argument text.
r['sudo_noninteractive']={'rc':r['sudo_noninteractive']['rc'],'unrestricted':bool(re.search(r'NOPASSWD:\s*ALL',r['sudo_noninteractive']['out'])),'lines':len(r['sudo_noninteractive']['out'].splitlines())}
cron=run(['crontab','-l']); active=[s for s in cron['out'].splitlines() if s.strip() and not s.lstrip().startswith('#') and not re.match(r'\w+=',s)]
r['cron']={'rc':cron['rc'],'active_count':len(active),'jobs':[{'schedule':' '.join(s.split()[:5]),'scripts':re.findall(r'[A-Za-z0-9_.-]+\.(?:py|sh)\b',s)} for s in active]}
r['cron_paths']=[]
for base in ['/etc/cron.d','/etc/cron.daily','/etc/cron.hourly','/etc/cron.weekly']:
 try:r['cron_paths'] += [str(p) for p in pathlib.Path(base).iterdir()]
 except OSError: pass
r['unit_controls']={}
for u in ['vintos-server.service','vintos-atelier.service','vintos-forge.service','vintos-chemistry-lab.service','vintos-plugin-gateway.service','vintos-claude-shim.service','vintos-fault-sweep.timer','vintos-fault-sweep.service','vintos-emoclaw.service']:
 scope=[] if u=='vintos-atelier.service' else ['--user']
 props=['ActiveState','FragmentPath','User','NoNewPrivileges','ProtectSystem','ProtectHome','PrivateTmp','MemoryMax','TasksMax','CPUQuotaPerSecUSec','LimitNOFILE','OnUnitActiveUSec','ReadWritePaths']
 r['unit_controls'][u]=run(['systemctl']+scope+['show',u]+['--property='+p for p in props])
r['secret_permissions']=[]
paths=[H/'.ssh',H/'.ssh/authorized_keys',H/'.config/vintos',H/'.vintos/vintos.env']
paths+=list((H/'.vintos').glob('*key*'))+list((H/'.vintos').glob('*token*'))
for p in paths:
 try:
  s=p.stat();r['secret_permissions'].append({'path':str(p),'mode':oct(stat.S_IMODE(s.st_mode)),'uid':s.st_uid,'gid':s.st_gid,'is_file':p.is_file()})
 except OSError: pass
r['ssh_effective']=run(['sshd','-T'])
r['ssh_effective']={'rc':r['ssh_effective']['rc'],'directives':[s for s in r['ssh_effective']['out'].splitlines() if s.split()[0] in ['passwordauthentication','pubkeyauthentication','permitrootlogin','maxauthtries','maxsessions','allowusers','allowgroups','loglevel','authenticationmethods','allowtcpforwarding','gatewayports']]}
r['tailscale']={}
for label,args in [('serve',['tailscale','serve','status','--json']),('funnel',['tailscale','funnel','status','--json'])]:
 g=run(args)
 try:r['tailscale'][label]={'rc':g['rc'],'config':json.loads(g['out'])}
 except ValueError:r['tailscale'][label]={'rc':g['rc'],'available':False}
r['monitor_tools']={x:run(['sh','-c','command -v '+x])['out'].strip() for x in ['auditctl','fail2ban-client','aide','restic','borg','rclone','ufw','nft','iptables','docker']}
r['backup_paths']={}
for b in [H/'.vintos/deploy',H/'.vintos/backups',H/'backups',pathlib.Path('/var/backups')]:
 try:r['backup_paths'][str(b)]=[p.name for p in b.iterdir()][:100]
 except OSError:r['backup_paths'][str(b)]='unreadable_or_absent'
# Only content-free counters from operational accounting; never prompts, messages or sealed work.
r['accounting']={}
for p in [W/'memory/compute-ledger.jsonl',W/'memory/anthropic-usage.jsonl',H/'.vintos/logs/anthropic-usage.jsonl',H/'.vintos/logs/openai-usage.jsonl']:
 out={'exists':p.exists()}; counts=collections.Counter(); minute=collections.Counter(); callers=collections.Counter(); stages=collections.Counter()
 if p.exists():
  out.update(bytes=p.stat().st_size,mtime=p.stat().st_mtime)
  with p.open() as f:
   for ln in f:
    try:d=json.loads(ln)
    except ValueError:continue
    if not isinstance(d,dict):continue
    at=str(d.get('at',d.get('ts',''))); provider=str(d.get('provider') or ('anthropic' if 'anthropic' in p.name else 'openai' if 'openai' in p.name else 'unknown'))
    stages[(provider,str(d.get('class','')),str(d.get('stage','')))]+=1
    if at[:10] in [time.strftime('%Y-%m-%d'),time.strftime('%Y-%m-%d',time.localtime(time.time()-86400))]:
     counts[provider]+=1;minute[(provider,at[:16])]+=1
     callers[(provider,str(d.get('organ') or d.get('caller') or d.get('src') or 'unattributed')[:60])]+=1
  out['counts_recent']=dict(counts);out['max_minute_recent']={k:max([v for (pv,_),v in minute.items() if pv==k] or [0]) for k in counts};out['top_callers']=[[list(k),v] for k,v in callers.most_common(20)];out['stage_counts']=[[list(k),v] for k,v in stages.items()]
 r['accounting'][str(p)]=out
r['deployed_matches']={}
for rel in ['scripts/fault_sweep.py','scripts/compute_admission.py','scripts/claude_cache.py','scripts/deliver.py','bin/vintos_claude_shim.py','bin/model_router.py','bin/server.py']:
 a=H/'Vintos-main'/rel;b=W/rel
 r['deployed_matches'][rel]={'source_exists':a.exists(),'installed_exists':b.exists(),'equal':a.exists() and b.exists() and hashlib.sha256(a.read_bytes()).digest()==hashlib.sha256(b.read_bytes()).digest()}
r['journal_access']={}
for scope in [[],['--user']]:
 q=run(['journalctl']+scope+['-n','0','--no-pager']);r['journal_access']['user' if scope else 'system']={'rc':q['rc']}
print(json.dumps(r,indent=2))
