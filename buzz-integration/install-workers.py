#!/usr/bin/env python3
"""Explicit root installer for four isolated Buzz workers. Never starts model work."""
import json, os, pathlib, pwd, shutil, subprocess, shlex
P=pathlib.Path
SOURCE=P('/home/gloria')
DEST=P('/opt/buzz-aegis')
CONFIG=P('/etc/buzz-aegis')
assert os.geteuid()==0, 'Run as root on Aegis'
DEST.mkdir(mode=0o755,exist_ok=True); CONFIG.mkdir(mode=0o700,exist_ok=True)
# Separate copies: worker users cannot traverse Gloria's home or access owner keys.
for src,name in [(SOURCE/'.local/opt/buzz/0.5.23/usr/bin','bin'),(SOURCE/'.local/opt/buzz-runtimes','runtimes')]:
 shutil.copytree(src,DEST/name,dirs_exist_ok=True,symlinks=True)
shutil.copy2(SOURCE/'repos/buzz/target/debug/buzz-acp',DEST/'bin/buzz-acp')
manifest=json.loads(P('/tmp/codex-buzz-agents.json').read_text())
secrets={}
for line in (SOURCE/'.vintos/vintos.env').read_text().splitlines():
 k,sep,v=line.partition('=')
 if sep and k.strip() in ('OPENAI_API_KEY','XAI_API_KEY'):
  words=shlex.split(v,comments=True)
  if words: secrets[k.strip()]=words[0]
secrets['ANTHROPIC_API_KEY']=(SOURCE/'.vintos/anthropic-key').read_text().strip().strip('\"\'')
for row in manifest:
 ident=row['id']; user='buzz-'+ident
 try: account=pwd.getpwnam(user)
 except KeyError:
  subprocess.run(['useradd','--system','--user-group','--home-dir','/var/lib/'+user,'--create-home','--shell','/usr/sbin/nologin',user],check=True)
  account=pwd.getpwnam(user)
 home=P('/var/lib')/user
 workspace=home/'workspace';workspace.mkdir(mode=0o700,exist_ok=True)
 for p in (home,workspace): os.chown(p,account.pw_uid,account.pw_gid)
 # Seed independent checkouts without granting GitHub or live-host credentials.
 for repo_name in ('vintos','plithra-app','vintos-app'):
  source_repo=SOURCE/'repos'/repo_name
  target=workspace/repo_name
  if not target.exists():
   subprocess.run(['git','clone','--no-local',str(source_repo),str(target)],check=True,stdout=subprocess.DEVNULL)
   # Retain a public origin URL, never a host-local writable origin.
   origin=subprocess.check_output(['git','-C',str(source_repo),'remote','get-url','origin'],text=True).strip()
   if not origin.startswith(('https://github.com/','git@github.com:')): raise ValueError('unexpected repository origin')
   subprocess.run(['git','-C',str(target),'remote','set-url','origin',origin],check=True)
   subprocess.run(['chown','-R',user+':'+user,str(target)],check=True)
 context=workspace/'CONTEXT.md'
 if not context.exists():
  context.write_text('# Working context\n\nNo task has been approved or started. Await Gloria in Buzz.\n')
  os.chown(context,account.pw_uid,account.pw_gid)
 ledger=workspace/'ledger.jsonl'
 if not ledger.exists(): ledger.touch(mode=0o600);os.chown(ledger,account.pw_uid,account.pw_gid)
 prompt=CONFIG/(ident+'.md');prompt.write_text(row['instructions']);prompt.chmod(0o644)
 # Root-owned provider/identity credentials enter only the corresponding process.
 identity=SOURCE/'.config/buzz/agents'/ident
 public=json.loads((identity/'public.json').read_text())
 env={'HOME':str(home),'PATH':'/opt/buzz-aegis/bin:/opt/buzz-aegis/runtimes/node_modules/.bin:/usr/local/bin:/usr/bin:/bin',
 'BUZZ_PRIVATE_KEY':(identity/'key.hex').read_text().strip(), 'BUZZ_AUTH_TAG':(identity/'auth.json').read_text().strip(),
 'BUZZ_RELAY_URL':'ws://100.72.225.119:8792', 'BUZZ_ACP_AGENT_OWNER':public['owner']}
 if ident=='gemma':
  env.update(BUZZ_AGENT_PROVIDER='openai',OPENAI_COMPAT_BASE_URL='http://172.18.16.1:1234/v1',OPENAI_COMPAT_API='chat',OPENAI_COMPAT_API_KEY='local-only',BUZZ_AGENT_MODEL=row['model'])
 elif ident=='codex': env['OPENAI_API_KEY']=secrets['OPENAI_API_KEY']
 elif ident=='claude': env.update(ANTHROPIC_API_KEY=secrets['ANTHROPIC_API_KEY'],CLAUDE_CODE_SUBAGENT_MODEL='opus')
 else: env['XAI_API_KEY']=secrets['XAI_API_KEY']
 envpath=CONFIG/(ident+'.env')
 # systemd quoted EnvironmentFile assignments; no shell evaluation.
 envpath.write_text('\n'.join(k+'='+json.dumps(v,ensure_ascii=False) for k,v in env.items())+'\n');envpath.chmod(0o600)
 command={'gemma':'/opt/buzz-aegis/bin/buzz-agent','codex':'/opt/buzz-aegis/runtimes/node_modules/.bin/codex-acp','claude':'/opt/buzz-aegis/runtimes/node_modules/.bin/claude-agent-acp','grok':'/opt/buzz-aegis/runtimes/node_modules/.bin/grok'}[ident]
 args='agent,stdio' if ident=='grok' else ''
 # Prompt is passed as systemd credential, readable only within this service.
 unit=f'''[Unit]
Description=Buzz {row['name']} (owner-approved tasks)
After=network-online.target docker.service
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=3
[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={workspace}
EnvironmentFile={envpath}
LoadCredential=instructions:{prompt}
ExecStart=/opt/buzz-aegis/bin/buzz-acp --channels 9c8a20c4-9d1c-4ebe-8895-6745d38b4515,57ab7a2f-b925-4e7d-bfbd-471c305b8c57 --agent-command {command} --agent-args={args} --model {row['model']} --respond-to owner-signed --allowed-respond-to owner-signed --subscribe mentions --agents 1 --lazy-pool --heartbeat-interval 0 --session-policy thread --multiple-event-handling queue --max-turn-duration 1800 --system-prompt-file %d/instructions
Restart=on-failure
RestartSec=15
TimeoutStopSec=30
KillMode=control-group
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths={home}
InaccessiblePaths=/home/gloria /mnt/c -{workspace}/vintos/agent-room -{workspace}/vintos/.git/objects/info/alternates
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
UMask=0077
TasksMax=256
MemoryMax=4G
CPUQuota=200%
[Install]
WantedBy=multi-user.target
'''
 (P('/etc/systemd/system')/(user+'.service')).write_text(unit)
 print('installed',user,'model',row['model'],'not started')
subprocess.run(['systemctl','daemon-reload'],check=True)
