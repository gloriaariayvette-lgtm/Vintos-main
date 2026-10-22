import os,json,pathlib,subprocess,urllib.request,urllib.error,hashlib,importlib.metadata,collections,re,socket,time
H=pathlib.Path.home();W=H/'.vintos/workspace';r={'at':time.time()}
def run(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=25);return {'rc':p.returncode,'out':p.stdout}
r['processes']=[]
for p in pathlib.Path('/proc').glob('[0-9]*'):
 try:
  argv=(p/'cmdline').read_bytes().split(b'\0');uid=(p/'status').read_text().split('Uid:')[1].split()[0]
  scripts=[a.decode(errors='replace') for a in argv if re.match(rb'^[/A-Za-z0-9_.-]+\.(py|sh|js)$',a)]
  if scripts:r['processes'].append({'pid':p.name,'uid':uid,'executable':pathlib.Path(argv[0].decode(errors='replace')).name,'scripts':scripts})
 except (OSError,IndexError):pass
r['installed_matches']={}
for rel in ['bin/server.py','bin/model_router.py','bin/vintos_claude_shim.py']:
 a=H/'Vintos-main'/rel;b=H/'.vintos'/rel
 r['installed_matches'][rel]={'path':str(b),'exists':b.exists(),'equal':a.exists() and b.exists() and hashlib.sha256(a.read_bytes()).digest()==hashlib.sha256(b.read_bytes()).digest()}
r['listener_owners']=run(['ss','-H','-lntp'])
# Read-only, one request per listed route, no response content retained.
r['unauthenticated_gets']=[]
for port,path in [(8500,'/api/settings/params'),(8500,'/api/desktop/status'),(8500,'/api/robot/state?frame=0'),(8500,'/health'),(8404,'/api/robot/state?frame=0'),(8624,'/health'),(8611,'/health'),(8625,'/health')]:
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=5) as q:
   data=q.read(256*1024);status=q.status
 except urllib.error.HTTPError as e:status=e.code;data=b''
 except Exception as e:status=type(e).__name__;data=b''
 r['unauthenticated_gets'].append({'port':port,'path':path,'status':status,'response_bytes_read':len(data)})
# A single upgrade then immediate close; don't read the streamed data.
s=socket.create_connection(('127.0.0.1',8500),timeout=3)
s.sendall(b'GET /ws/telemetry HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n')
raw=s.recv(4096);r['websocket_unauthenticated_status']=raw.split(b'\r\n')[0].decode(errors='replace');s.close()
r['python_packages']={d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata['Name'].lower() in ['fastapi','starlette','uvicorn','httpx','requests','urllib3','pydantic','torch','transformers','cryptography','aiohttp','websockets','pip','setuptools','safetensors']}
r['system_packages']=run(['dpkg-query','-W','-f=${Package} ${Version}\n','openssh-server','openssl','python3','libssl3t64','nginx'])
r['docker_socket']={'exists':pathlib.Path('/var/run/docker.sock').exists(),'writable':os.access('/var/run/docker.sock',os.W_OK)}
r['ssh_config']=run(['/usr/sbin/sshd','-T'])
r['ssh_config']={'rc':r['ssh_config']['rc'],'directives':[s for s in r['ssh_config']['out'].splitlines() if s.split()[0] in ['passwordauthentication','pubkeyauthentication','permitrootlogin','maxauthtries','maxsessions','loglevel','authenticationmethods','allowtcpforwarding','gatewayports']]}
r['backups']=[]
for p in sorted((H/'.vintos/backups').glob('*'))[-12:]:
 try:r['backups'].append({'name':p.name,'mtime':p.stat().st_mtime,'mode':oct(p.stat().st_mode & 0o777),'restore_script':(p/'restore.sh').exists() if p.is_dir() else None})
 except OSError:pass
r['deploy_receipt']={}
ps=sorted((H/'.vintos/deploy/releases').glob('*.json'))
if ps:
 d=json.loads(ps[-1].read_text());r['deploy_receipt']={'file':ps[-1].name,'at':d.get('at'),'git_rev':d.get('git_rev'),'files':len(d.get('files',[])),'failures':len(d.get('failures',[])),'rollback_present':bool(d.get('rollback'))}
# Environment *presence* only, and comparison booleans, never values or hashes.
r['credential_boundary']={}
for row in r['processes']:
 if any(x.endswith(('/server.py','/vintos_claude_shim.py')) for x in row['scripts']):
  try:
   env=dict(x.split(b'=',1) for x in pathlib.Path('/proc',row['pid'],'environ').read_bytes().split(b'\0') if b'=' in x)
   relevant=['VINTOS_SECRET','ANTHROPIC_API_KEY','OPENAI_API_KEY','XAI_API_KEY','GOOGLE_API_KEY']
   r['credential_boundary'][row['pid']]={'present':{k:bool(env.get(k.encode())) for k in relevant},'house_default_in_use':not bool(env.get(b'VINTOS_SECRET',b''))}
  except OSError:r['credential_boundary'][row['pid']]={'readable':False}
print(json.dumps(r,indent=2))
