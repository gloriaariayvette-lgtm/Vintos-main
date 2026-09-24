#!/usr/bin/env python3
"""Store a JGI Data Portal session token without printing it."""
import getpass
import json
import os
from pathlib import Path

TOKEN = Path.home()/'.config/vintos/jgi-token'


def main():
    value = getpass.getpass('JGI Data Portal session token (hidden): ').strip()
    if len(value) < 20 or any(c.isspace() for c in value):
        raise SystemExit('Refusing an empty, short, or whitespace-bearing token.')
    TOKEN.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(TOKEN.parent, 0o700)
    temporary = TOKEN.with_suffix('.tmp')
    temporary.write_text(value + '\n')
    os.chmod(temporary, 0o600)
    os.replace(temporary, TOKEN)
    print(json.dumps({'jgi_token_file': str(TOKEN), 'mode': '0600',
                      'next': 'python3 imgvr_store.py restore'}))


if __name__ == '__main__':
    main()
