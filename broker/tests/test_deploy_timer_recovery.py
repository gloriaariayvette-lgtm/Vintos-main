#!/usr/bin/env python3
"""Execute timer confirmation and generated rollback with fake systemctl only."""
import os,sys,tempfile,subprocess
from pathlib import Path
R=[]
def check(name,ok):R.append(bool(ok));print(('PASS ' if ok else 'FAIL ')+name)
repo=Path(__file__).resolve().parents[2];src=(repo/'scripts/deploy-atelier.sh').read_text()
root=Path(tempfile.mkdtemp());home=root/'home';backup=root/'backup';backup.mkdir();units=home/'.config/systemd/user';units.mkdir(parents=True)
bindir=root/'bin';bindir.mkdir();log=root/'commands'
ctl=bindir/'systemctl';ctl.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$CTL_LOG"
case "$*" in
 *is-enabled*) printf '%s\\n' "$OLD_ENABLED";;
 *is-active*) printf '%s\\n' "$OLD_ACTIVE";;
 *show*) printf 'Id=vintos-skill-surf.timer\\nActiveState=active\\nNextElapseUSecRealtime=%s\\n' "$NEXT";;
esac
''');ctl.chmod(0o755)
env=dict(os.environ,HOME=str(home),PATH=str(bindir)+':'+os.defpath,CTL_LOG=str(log),OLD_ENABLED='disabled',OLD_ACTIVE='inactive',NEXT='')
a=src.index('confirm_timer()');b=src.index('\n}',a)+2
fn=src[a:b]
for next_value,expected in [('',False),('0',False),('n/a',False),('Fri 2026-09-18 12:00:00 UTC',True)]:
 p=subprocess.run(['bash','-c','say(){ :; }; flag(){ :; };\n'+fn+'\nconfirm_timer --user vintos-skill-surf'],env=dict(env,NEXT=next_value),capture_output=True)
 check('timer elapse '+repr(next_value), (p.returncode==0)==expected)
a=src.index('_surf_enabled=');b=src.index('# Record the service/process state',a);block=src[a:b]
for existing in (False,True):
 for unit in units.iterdir():unit.unlink()
 if existing:
  for ext in ('service','timer'):(units/('vintos-skill-surf.'+ext)).write_text('original '+ext)
 restore=backup/'restore.sh';restore.write_text('#!/bin/bash\nset -e\n')
 script='SURF_UNIT_NAME=vintos-skill-surf\nBACKUP='+str(backup)+'\ndie(){ exit 99; };\n'+block+'\ntrue\n'
 p=subprocess.run(['bash','-c',script],env=dict(env,OLD_ENABLED='enabled' if existing else 'disabled',OLD_ACTIVE='active' if existing else 'inactive'),capture_output=True)
 check('backup constructed '+str(existing),p.returncode==0)
 for ext in ('service','timer'):(units/('vintos-skill-surf.'+ext)).write_text('new release')
 log.write_text('');p=subprocess.run(['bash',str(restore)],env=env,capture_output=True)
 check('restore exits cleanly '+str(existing),p.returncode==0)
 check('restores originals or removes new files '+str(existing), all((units/('vintos-skill-surf.'+ext)).read_text()=='original '+ext for ext in ('service','timer')) if existing else not any(units.iterdir()))
 commands=log.read_text()
 check('rollback never starts the oneshot '+str(existing),'start vintos-skill-surf.service' not in commands and 'restart vintos-skill-surf' not in commands)
 check('restores timer activation '+str(existing),('start vintos-skill-surf.timer' in commands)==existing)

# A runtime import alias must retain its link while its canonical target changes.
assert env["HOME"] == str(home)
a=src.index('canonical_dest()');b=src.index('\n}',a)+2
canonical=src[a:b]
target=home/'actual module.py';target.write_text('old')
alias=home/'alias.py';alias.symlink_to(target)
payload=root/'payload.py';payload.write_text('new')
command=canonical+'\nresolved="$(canonical_dest "$ALIAS")"; install -m 644 "$PAYLOAD" "$resolved"'
p=subprocess.run(['bash','-c',command],env=dict(env,ALIAS=str(alias),PAYLOAD=str(payload)),capture_output=True)
check('promotion preserves the import alias and updates its target',p.returncode==0 and alias.is_symlink() and target.read_text()=='new')
check('the importable causal model is explicitly manifested','causal-self-model.py causal_self_model.py' in src)

print('%d/%d'%(sum(R),len(R)));sys.exit(0 if all(R) else 1)
