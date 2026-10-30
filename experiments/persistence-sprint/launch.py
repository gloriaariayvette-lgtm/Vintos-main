#!/usr/bin/env python3
"""Run an offline entry point with denied network and scratch-only file writes."""
import os
from pathlib import Path
import runpy
import sys
import tempfile

root=Path(os.environ['PERSISTENCE_SCRATCH']).resolve()
if '.vintos' in root.parts or root == Path('/') or not root.is_dir():raise ValueError('private scratch required')
os.umask(0o077)
os.environ.update(HOME=str(root/'home'),TMPDIR=str(root),PYTHONDONTWRITEBYTECODE='1',CUDA_VISIBLE_DEVICES='')
tempfile.tempdir=str(root);sys.dont_write_bytecode=True
def inside(path, dir_fd=None):
    if dir_fd not in (None, -1):raise PermissionError('directory descriptors denied')
    if not isinstance(path,(str,bytes,os.PathLike)):
        raise PermissionError('path required for mutation')
    if not Path(os.fsdecode(path)).resolve().is_relative_to(root):
        raise PermissionError('outside sprint scratch')

def guard(event,a):
    if event=='open' and isinstance(a[0],(str,bytes,os.PathLike)):
        mode,flags=a[1:3]
        writes=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        if writes and not Path(os.fsdecode(a[0])).resolve().is_relative_to(root):raise PermissionError('outside sprint scratch')
    if event in ('os.remove','os.rmdir','os.mkdir','os.chmod','os.chown','os.utime','os.truncate'):
        inside(a[0])
        if event in ('os.remove','os.rmdir') and len(a)>1:inside(a[0],a[1])
        if event in ('os.mkdir','os.chmod') and len(a)>2:inside(a[0],a[2])
        if event in ('os.chown','os.utime') and len(a)>3:inside(a[0],a[3])
    if event=='os.rename':
        inside(a[0],a[2]);inside(a[1],a[3])
    if event in ('os.symlink','os.link'):raise PermissionError('links denied in scratch runner')
    if event in ('socket.connect','socket.sendto','socket.bind'):raise PermissionError('network denied')
    if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','pty.spawn'):
        raise PermissionError('child processes denied in scratch runner')
sys.addaudithook(guard)
sys._persistence_guard_root=str(root)
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
