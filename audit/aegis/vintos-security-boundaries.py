import ast,pathlib,json,urllib.request,urllib.error,subprocess,os,hashlib,time,stat,re
H=pathlib.Path.home();r={'at':time.time()};source=H/'Vintos/server.py';t=ast.parse(source.read_text());default=None
for n in t.body:
 if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='APP_SECRET' for x in n.targets) and isinstance(n.value,ast.Call) and len(n.value.args)>1 and isinstance(n.value.args[1],ast.Constant):default=n.value.args[1].value
r['default_credential_read_test']={'default_found_in_source':default is not None}
if default:
 for label,key in [('wrong','security-audit-invalid'),('source_default',default)]:
  q=urllib.request.Request('http://127.0.0.1:8500/api/desktop/status',headers={'X-Vintos-Secret':key})
  try:
   with urllib.request.urlopen(q,timeout=5) as v:status=v.status
  except urllib.error.HTTPError as e:status=e.code
  except Exception as e:status=type(e).__name__
  r['default_credential_read_test'][label+'_status']=status
r['source_runtime_hashes']={}
for a,b in [(H/'Vintos/server.py',H/'Vintos-main/bin/server.py'),(H/'Vintos/model_router.py',H/'Vintos-main/bin/model_router.py'),(H/'Vintos-main/bin/vintos_claude_shim.py',H/'Vintos-main/bin/vintos_claude_shim.py')]:
 r['source_runtime_hashes'][str(a)]={'exists':a.exists(),'matches_checkout':a.exists() and b.exists() and hashlib.sha256(a.read_bytes()).digest()==hashlib.sha256(b.read_bytes()).digest()}
r['distribution_revisions']={}
for name in ['python3-requests','python3-urllib3','python3-cryptography']:
 p=subprocess.run(['dpkg-query','-W','-f=${Version}',name],capture_output=True,text=True);r['distribution_revisions'][name]={'rc':p.returncode,'version':p.stdout}
r['package_paths']={}
for mod in ['requests','urllib3','cryptography','torch','fastapi','starlette']:
 try:
  spec=__import__('importlib.util',fromlist=['find_spec']).find_spec(mod);r['package_paths'][mod]=spec.origin if spec else None
 except Exception:r['package_paths'][mod]=None
r['netrc_present']=(H/'.netrc').exists()
r['docker_group_socket_metadata']={'mode':oct(pathlib.Path('/var/run/docker.sock').stat().st_mode & 0o777)}
r['backup_cron_scripts']=[]
p=subprocess.run(['crontab','-l'],capture_output=True,text=True)
for line in p.stdout.splitlines():
 if line.strip() and not line.lstrip().startswith('#') and re.search('backup|restore|snapshot',line,re.I):r['backup_cron_scripts'].append({'schedule':' '.join(line.split()[:5]),'scripts':re.findall(r'[A-Za-z0-9_.-]+\.(?:py|sh)\b',line)})
r['ssh_directives_source']={}
for f in [pathlib.Path('/etc/ssh/sshd_config')]+list(pathlib.Path('/etc/ssh/sshd_config.d').glob('*.conf')):
 try:r['ssh_directives_source'][str(f)]=[l.strip() for l in f.read_text().splitlines() if re.match(r'(?i)^\s*(PasswordAuthentication|PubkeyAuthentication|PermitRootLogin|MaxAuthTries|MaxSessions|AuthenticationMethods|AllowTcpForwarding|GatewayPorts|LogLevel)\s',l)]
 except OSError:r['ssh_directives_source'][str(f)]='unreadable'
r['unprivileged_firewall_visibility']={}
for args in [['nft','list','ruleset'],['iptables','-S']]:
 p=subprocess.run(args,capture_output=True,text=True);r['unprivileged_firewall_visibility'][args[0]]={'rc':p.returncode,'rule_lines':len(p.stdout.splitlines())}
print(json.dumps(r,indent=2))
