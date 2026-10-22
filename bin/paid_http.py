"""Content-free outbound attempt accounting at existing HTTP call sites.

Uses compute-ledger.jsonl, independently of reservation and completion rows.
The pause affects listed paid-provider hosts; local inference is untouched.
"""
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

HOSTS = {
    'api.anthropic.com': 'anthropic', 'api.openai.com': 'openai',
    'api.x.ai': 'xai', 'generativelanguage.googleapis.com': 'google',
    'api.kie.ai': 'kie', 'api.atlascloud.ai': 'atlascloud',
    'api.elevenlabs.io': 'elevenlabs', 'api.search.brave.com': 'brave',
    'openrouter.ai': 'openrouter', 'api.openrouter.ai': 'openrouter',
    'health.api.nvidia.com': 'nvidia', 'integrate.api.nvidia.com': 'nvidia',
}


def workspace():
    return Path(os.environ.get('SPARK_WORKSPACE') or Path.home() / '.vintos/workspace')


def pause_path():
    return Path.home() / '.vintos/paid-outbound.paused'


def provider(url):
    value = getattr(url, 'full_url', url)
    try: return HOSTS.get((urlsplit(str(value)).hostname or '').lower())
    except ValueError: return None


def before(url, script):
    name = provider(url)
    if not name: return
    if pause_path().exists():
        raise PermissionError('outbound paid calls paused by owner')
    # The installed bin and scripts directories share this accounting module.
    try:
        import compute_admission
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
        sys.path.insert(0, str(workspace() / 'scripts'))
        import compute_admission
    script = re.sub(r'[^A-Za-z0-9_./-]', '_', script)[:120]
    compute_admission.record(script, cls='outbound', provider=name, stage='attempt',
        extra={'epoch': datetime.now(timezone.utc).timestamp(), 'script': script}, strict=True,
        ledger_path=str(workspace() / 'memory/compute-ledger.jsonl'))


def send(transport, script, url, *args, **kwargs):
    before(url, script)
    return transport(url, *args, **kwargs)


async def asend(transport, script, url, *args, **kwargs):
    before(url, script)
    return await transport(url, *args, **kwargs)


def main(argv):
    if len(argv) >= 3 and argv[0] == 'curl' and argv[2] == '--':
        import subprocess
        for arg in argv[3:]:
            if provider(arg): before(arg, argv[1])
        return subprocess.call(['curl'] + argv[3:])
    if argv == ['pause']:
        p = pause_path(); p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) if not p.exists() else None
        if fd is not None: os.close(fd)
        print('Paid HTTP calls paused; in-flight calls may finish. Local inference continues.')
    elif argv == ['resume']:
        try: pause_path().unlink()
        except FileNotFoundError: pass
        print('Paid HTTP calls resumed.')
    elif argv == ['status']:
        print(json.dumps({'paused': pause_path().exists(), 'hosts': sorted(HOSTS)}))
    else:
        print('usage: paid_http.py pause|resume|status'); return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
