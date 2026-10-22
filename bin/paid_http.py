"""Content-free outbound attempt accounting at existing HTTP call sites.

Uses compute-ledger.jsonl, independently of reservation and completion rows.
The pause affects listed paid-provider hosts; local inference is untouched.
"""
import contextvars
import threading
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


FAILURE_PREFIX = 'VINTOS_SECURITY_ACCOUNTING_FAILURE '
_last_failure = {}


def accounting_failure(name, script, error):
    """Health evidence, never another call ledger or a reason to block transport."""
    try:
        now = datetime.now(timezone.utc).timestamp()
        if now - _last_failure.get(name, -1e20) < 60: return
        _last_failure[name] = now
        row = {'at': now, 'organ': 'paid-http', 'what': 'provider_accounting_failed',
               'provider': name, 'script': script, 'error': type(error).__name__,
               'why': name + ' outbound accounting failed; calls continue; script ' + script + '; ' + type(error).__name__}
        # Journald is the fallback when the workspace volume cannot accept writes.
        try: print(FAILURE_PREFIX + json.dumps(row), file=sys.stderr, flush=True)
        except Exception: pass
        path = workspace() / 'memory/organ-failures.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'w') as stream: stream.write(json.dumps(row) + '\n')
    except Exception:
        pass


def check_pause(url, script):
    name = provider(url)
    if not name: return
    try:
        paused = pause_path().exists()
    except Exception as error:
        accounting_failure(name, script, error)
        paused = False
    if paused:
        raise PermissionError('outbound paid calls paused by owner')


def before(url, script):
    name = provider(url)
    if not name: return
    script = re.sub(r'[^A-Za-z0-9_./-]', '_', str(script))[:120]
    check_pause(url, script)
    try:
        # Strict persistence detects loss; its failure is observational, not admission.
        try:
            import compute_admission
        except ImportError:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
            sys.path.insert(0, str(workspace() / 'scripts'))
            import compute_admission
        compute_admission.record(script, cls='outbound', provider=name, stage='attempt',
            extra={'epoch': datetime.now(timezone.utc).timestamp(), 'script': script}, strict=True,
            ledger_path=str(workspace() / 'memory/compute-ledger.jsonl'))
    except Exception as error:
        accounting_failure(name, script, error)


def send(transport, script, url, *args, **kwargs):
    before(url, script)
    return transport(url, *args, **kwargs)


async def asend(transport, script, url, *args, **kwargs):
    before(url, script)
    return await transport(url, *args, **kwargs)


_urllib_script = contextvars.ContextVar('paid_urllib_script', default=None)
_urllib_lock = threading.Lock()


def urllib_send(transport, script, request, *args, **kwargs):
    """Count urllib HTTP attempts, including redirects, at its actual opener.

    A preview's supplied transport can return without opening a connection; that
    is not an outbound HTTP attempt and must not mutate the call ledger.
    """
    script = re.sub(r'[^A-Za-z0-9_./-]', '_', str(script))[:120]
    check_pause(request, script)
    try:
        import urllib.request
        with _urllib_lock:
            original = urllib.request.AbstractHTTPHandler.do_open
            if not getattr(original, '_vintos_paid_attempt', False):
                def opening(self, http_class, req, **connection):
                    active = _urllib_script.get()
                    if active is not None: before(req, active)
                    return original(self, http_class, req, **connection)
                opening._vintos_paid_attempt = True
                urllib.request.AbstractHTTPHandler.do_open = opening
    except Exception as error:
        name = provider(request)
        if name: accounting_failure(name, script, error)
    token = _urllib_script.set(script)
    try: return transport(request, *args, **kwargs)
    finally: _urllib_script.reset(token)


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
