"""Content-free request correlation shared by HTTP and provider receipts."""
from contextvars import ContextVar
import json
import os
from pathlib import Path
import time
from store_guard import transaction

current = ContextVar('vintos_request_trace', default=None)
LOG = str(Path.home() / '.vintos/workspace/memory/request-trace.jsonl')


def record(path, method, status, started):
    row = {'at': time.time(), 'request_id': current.get(), 'route': path,
           'method': method, 'status': status, 'latency_ms': round((time.monotonic()-started)*1000)}
    with transaction(LOG):
        with open(LOG, 'a') as handle:
            handle.write(json.dumps(row) + '\n')
    return row


def runtime_inventory(modules=None):
    """Loaded file identities only; never source bodies or agent-room internals."""
    import hashlib
    import sys
    rows = []
    for name, module in sorted(list((sys.modules if modules is None else modules).items())):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if 'agent-room' in path.parts:
            continue
        try:
            rows.append({'module': name, 'file': str(path),
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        except OSError:
            continue
    return {'schema': 'loaded-python-1', 'pid': os.getpid(), 'at': time.time(), 'modules': rows}


_inventory_written = False

def record_inventory_once():
    global _inventory_written
    if not _inventory_written:
        from store_guard import write_json
        write_json(str(Path(LOG).with_name('server-loaded-modules.json')), runtime_inventory())
        _inventory_written = True
