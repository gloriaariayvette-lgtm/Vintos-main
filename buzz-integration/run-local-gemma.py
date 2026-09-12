#!/usr/bin/env python3
"""Local-only user runner: no new account and no paid provider credentials.

Bubblewrap exposes only binaries, TLS roots and this agent's private workspace.
The owner key, live house and other agent homes are not mounted.
"""
from pathlib import Path
import json,os
h=Path.home();identity=h/'.config/buzz/agents/gemma'
workspace=h/'.local/share/buzz-gemma';workspace.mkdir(parents=True,exist_ok=True)
source=h/'repos/buzz/target/debug/buzz-acp'
binaries=h/'.local/opt/buzz/0.5.23/usr/bin'
public=json.loads((identity/'public.json').read_text())
env={'HOME':'/workspace','PATH':'/app:/usr/bin:/bin',
 'BUZZ_PRIVATE_KEY':(identity/'key.hex').read_text().strip(),
 'BUZZ_AUTH_TAG':(identity/'auth.json').read_text().strip(),
 'BUZZ_RELAY_URL':'ws://100.72.225.119:8792','BUZZ_ACP_AGENT_OWNER':public['owner'],
 'BUZZ_AGENT_PROVIDER':'openai','OPENAI_COMPAT_API_KEY':'local-only','OPENAI_COMPAT_API':'chat',
 'OPENAI_COMPAT_BASE_URL':'http://100.79.177.103:1234/v1','BUZZ_AGENT_MODEL':'gemma-4-26b-a4b-it-uncensored'}
args=['bwrap','--unshare-all','--share-net','--die-with-parent','--new-session']
for path in ['/usr','/lib','/lib64','/etc/ssl','/etc/resolv.conf','/etc/hosts']:
 if Path(path).exists():args+=['--ro-bind',path,path]
args+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/app',
 '--ro-bind',str(source),'/app/buzz-acp','--ro-bind',str(binaries/'buzz-agent'),'/app/buzz-agent',
 '--ro-bind',str(binaries/'buzz'),'/app/buzz','--ro-bind',str(binaries/'buzz-dev-mcp'),'/app/buzz-dev-mcp',
 '--ro-bind',str(h/'repos/vintos/buzz-integration/agents.json'),'/app/agents.json',
 '--bind',str(workspace),'/workspace','--chdir','/workspace','--clearenv']
for k,v in env.items():args+=['--setenv',k,v]
manifest=json.loads((h/'repos/vintos/buzz-integration/agents.json').read_text())
prompt=next(row['instructions'] for row in manifest if row['id']=='gemma')
args+=['/app/buzz-acp','--channels','9c8a20c4-9d1c-4ebe-8895-6745d38b4515,57ab7a2f-b925-4e7d-bfbd-471c305b8c57',
 '--agent-command','/app/buzz-agent','--agent-args=','--mcp-command','/app/buzz-dev-mcp',
 '--model','gemma-4-26b-a4b-it-uncensored','--respond-to','owner-signed','--allowed-respond-to','owner-signed',
 '--subscribe','mentions','--agents','1','--lazy-pool','--idle-pool-sleep','300',
 '--heartbeat-interval','0','--session-policy','thread','--multiple-event-handling','queue',
 '--idle-timeout','180','--max-turn-duration','600','--system-prompt',prompt]
os.execvp(args[0],args)
