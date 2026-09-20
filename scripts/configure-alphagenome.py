#!/usr/bin/env python3
"""Store an AlphaGenome key from a hidden terminal prompt, outside source control."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key-file',type=Path,default=Path.home()/'.config/vintos/alphagenome.key')
    args=parser.parse_args()
    path=args.key_file.expanduser().resolve()
    if path.exists():raise SystemExit('Key file already exists; no overwrite performed.')
    key=getpass.getpass('AlphaGenome API key (hidden): ').strip()
    if not key or any(c in key for c in '\r\n'):raise SystemExit('No valid key entered.')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:stream.write(key+'\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps({'alphagenome_key_file':str(path)}))
    print('Key saved. No API request was made. Set alphagenome_python to the dedicated SDK venv interpreter.')


if __name__=='__main__':main()
