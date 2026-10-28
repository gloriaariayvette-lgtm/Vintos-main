#!/usr/bin/env python3
"""Run an offline entry point with denied network and scratch-only file writes."""
import os
from pathlib import Path
import runpy
import sys
import tempfile

root=Path(os.environ['PERSISTENCE_SCRATCH']).resolve()
if '.vintos' in root.parts:raise ValueError('private scratch required')
os.environ.update(HOME=str(root/'home'),TMPDIR=str(root),PYTHONDONTWRITEBYTECODE='1',CUDA_VISIBLE_DEVICES='')
tempfile.tempdir=str(root);sys.dont_write_bytecode=True
def guard(event,a):
    if event=='open' and isinstance(a[0],(str,bytes,os.PathLike)):
        mode,flags=a[1:3]
        writes=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        if writes and not Path(os.fsdecode(a[0])).resolve().is_relative_to(root):raise PermissionError('outside sprint scratch')
    if event in ('socket.connect','socket.sendto'):raise PermissionError('network denied')
sys.addaudithook(guard)
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
