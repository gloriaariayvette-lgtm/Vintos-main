"""Owner-run coordinated identity cutover; never called automatically by the audit.

prepare generates a random credential on this host without displaying it. The
approved deploy invokes activate only after its tests and dry-run exit. Code
rollback keeps the new identity and guard; it never revives a known default.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys


def home(): return Path.home()
def base(): return home()/'.vintos/security-auth'
def env_path(): return home()/'.config/vintos/house-auth.env'
def canonical_envs(): return [home()/'.vintos/vintos.env', home()/'.vintos/secrets/robot.env']


def atomic(path, text, mode=0o600):
    path=Path(path); path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary=path.with_name(path.name+'.tmp.'+str(os.getpid()))
    fd=os.open(str(temporary),os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    try:
        with os.fdopen(fd,'w') as f: f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path);os.chmod(path,mode)
    finally:
        if temporary.exists(): temporary.unlink()


def state_path(identifier):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',identifier): raise ValueError('invalid cutover identifier')
    return base()/identifier/'state.json'


def load(identifier):
    p=state_path(identifier); data=json.loads(p.read_text())
    if data.get('id')!=identifier: raise ValueError('cutover identity mismatch')
    return p,data


def save(path,state): atomic(path,json.dumps(state,indent=2)+'\n')


def read_secret(path):
    lines=[l.split('=',1)[1].strip().strip('"').strip("'") for l in Path(path).read_text().splitlines() if l.startswith('VINTOS_SECRET=')]
    if len(lines)!=1: raise ValueError('environment must contain exactly one house credential')
    import house_auth
    value=lines[0]
    if len(value)<32 or hashlib.sha256(value.encode()).hexdigest()==house_auth.LEGACY_SHA256:
        raise ValueError('new random house credential required')
    return value


def digest(path):
    p=Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def write_canonical(value):
    for p in canonical_envs():
        old=p.read_text() if p.exists() else ''
        lines=[l for l in old.splitlines() if not re.match(r'^\s*(?:export\s+)?VINTOS_SECRET\s*=',l)]
        atomic(p,'\n'.join(lines)+'\nVINTOS_SECRET='+value+'\n')


def unit_paths():
    d=home()/'.config/systemd/user'
    return [d/'vintos-server.service.d/house-auth.conf',d/'vintos-robot-bridge.service.d/house-auth.conf']


def write_units(state):
    guard=state_path(state['id']).parent/'guard/house_server_guard.py'
    env=env_path()
    def quoted(value):
        if any(c in str(value) for c in '\n\r\x00%'): raise ValueError('unsupported unit path')
        return '"'+str(value).replace('\\','\\\\').replace('"','\\"')+'"'
    common='[Service]\nEnvironmentFile='+quoted(env)+'\n'
    server='ExecStart=\nExecStart=/usr/bin/python3 '+quoted(guard)+' --server '+quoted(state['server'])+'\n'
    for p in unit_paths():
        atomic(p, common+(server if p.parent.name=='vintos-server.service.d' else ''), 0o600)


def prepare(server=None):
    server=Path(server or home()/'Vintos/server.py').resolve()
    if not server.is_file(): raise ValueError('actual server script must exist before preparing cutover')
    identifier=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4)
    directory=state_path(identifier).parent; directory.mkdir(mode=0o700,parents=True)
    os.chmod(base(),0o700)
    files=canonical_envs()+[env_path()]+unit_paths()
    state={'schema':1,'id':identifier,'status':'prepared','server':str(server),
           'created':datetime.now(timezone.utc).isoformat(),'before':[],'guard_hashes':{}}
    for i,p in enumerate(files):
        entry={'path':str(p),'sha256':digest(p),'existed':p.exists(),'mode':(p.stat().st_mode & 0o777) if p.exists() else None}
        if p.exists():
            backup=directory/('before-'+str(i));shutil.copyfile(p,backup);os.chmod(backup,0o600)
            entry['backup']=str(backup)
        state['before'].append(entry)
    guard=directory/'guard';guard.mkdir(mode=0o700)
    for name in ['house_auth.py','house_server_guard.py','house_auth_rollout.py']:
        source=Path(__file__).resolve().parent/name;dest=guard/name
        shutil.copyfile(source,dest);os.chmod(dest,0o600)
        state['guard_hashes'][name]=digest(dest)
    client=Path(__file__).resolve().parent.parent/'clients/mobile'
    for name in ['index.html','house_auth_client.js']:
        dest=guard/name;shutil.copyfile(client/name,dest);os.chmod(dest,0o600)
        state['guard_hashes'][name]=digest(dest)
    atomic(directory/'house-auth.env','VINTOS_SECRET='+secrets.token_urlsafe(48)+'\n')
    save(state_path(identifier),state)
    return identifier


def preflight(identifier=None):
    if not identifier:
        read_secret(env_path());return
    p,state=load(identifier)
    if state['status'] not in ('prepared','active','complete'): raise ValueError('cutover not prepared')
    read_secret(p.parent/'house-auth.env')
    for name,sha in state['guard_hashes'].items():
        if digest(p.parent/'guard'/name)!=sha: raise ValueError('prepared guard code changed; prepare again')
    if state['status']=='prepared':
        for row in state['before']:
            if digest(row['path'])!=row['sha256']: raise ValueError('configuration changed since preparation; prepare again')


def activate(identifier, runner=subprocess.run):
    preflight(identifier);p,state=load(identifier)
    if state['status'] in ('active','complete'): return
    value=read_secret(p.parent/'house-auth.env')
    try:
        atomic(env_path(),'VINTOS_SECRET='+value+'\n')
        write_canonical(value);write_units(state)
        # The owner-approved deploy handles restarts after file promotion.
        runner(['systemctl','--user','daemon-reload'],check=True)
    except Exception:
        for row in state['before']:
            target=Path(row['path'])
            if row['existed']:
                atomic(target,Path(row['backup']).read_text(),row['mode'])
            elif target.exists(): target.unlink()
        try: runner(['systemctl','--user','daemon-reload'],check=True)
        except Exception: pass
        raise
    state['status']='active';state['activated']=datetime.now(timezone.utc).isoformat();save(p,state)


def finalize(identifier):
    p,state=load(identifier)
    if state['status'] not in ('active','complete'): raise ValueError('cutover has not been activated')
    receipts=sorted((home()/'.vintos/deploy/releases').glob('*.json'))
    if not receipts: raise ValueError('deployment receipt missing')
    receipt=json.loads(receipts[-1].read_text())
    if receipt.get('failures'): raise ValueError('deployment receipt records failures')
    for unit in ['vintos-server','vintos-robot-bridge']:
        if receipt.get('services',{}).get(unit)!='active': raise ValueError('required service not confirmed active')
    installed={row.get('installed_at'):row.get('sha256') for row in receipt.get('files',[])}
    for target in unit_paths():
        if installed.get(str(target))!=(digest(target) or '')[:16]: raise ValueError('cutover configuration absent from release receipt')
    if receipts[-1].stat().st_mtime < datetime.fromisoformat(state['activated']).timestamp(): raise ValueError('no post-cutover deployment receipt yet')
    backup=Path(receipt['backup']).resolve();allowed=(home()/'.vintos/backups').resolve()
    if allowed not in backup.parents or not (backup/'restore.sh').is_file(): raise ValueError('unexpected rollback location')
    state.update(status='complete',release=str(receipts[-1]),rollback=str(backup/'restore.sh'));save(p,state)


def secure_rollback(identifier, runner=subprocess.run):
    p,state=load(identifier)
    value=read_secret(env_path())  # keep current valid identity, even after a later rotation
    write_canonical(value);write_units(state)
    runner(['systemctl','--user','daemon-reload'],check=True)
    runner(['systemctl','--user','restart','vintos-server.service','vintos-robot-bridge.service'],check=True)
    state['status']='rolled_back_guarded';save(p,state)


def rollback(identifier, runner=subprocess.run):
    p,state=load(identifier)
    script=Path(state.get('rollback','')).resolve()
    allowed=(home()/'.vintos/backups').resolve()
    if allowed not in script.parents or script.name!='restore.sh' or not script.is_file():
        raise ValueError('finalize the successful deploy before using this rollback')
    # The private guard/drop-ins remain in place throughout code restoration.
    runner(['bash',str(script)],check=True)
    secure_rollback(identifier,runner)


def clipboard(identifier):
    if sys.stdout.isatty(): raise ValueError('pipe enrollment directly to the trusted clipboard; never display it')
    p,state=load(identifier)
    if state['status'] not in ('active','complete','rolled_back_guarded'): raise ValueError('cutover not active')
    sys.stdout.write(read_secret(env_path()))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','preflight','activate','finalize','rollback','secure-rollback','clipboard'])
    parser.add_argument('--id',dest='identifier');parser.add_argument('--server')
    args=parser.parse_args(argv)
    try:
        if args.action=='prepare': print(prepare(args.server));return 0
        if args.action=='preflight': preflight(args.identifier)
        else:
            if not args.identifier: raise ValueError('cutover identifier required')
            {'activate':activate,'finalize':finalize,'rollback':rollback,'secure-rollback':secure_rollback,'clipboard':clipboard}[args.action](args.identifier)
        if args.action!='clipboard':print('house auth '+args.action+': OK (credential not displayed)')
        return 0
    except Exception as e:
        # Errors may come from files containing credentials: print class, not their text.
        print('house auth '+args.action+' failed: '+type(e).__name__+'; configuration kept for inspection',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
