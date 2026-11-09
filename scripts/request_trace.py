"""Content-free request correlation shared by HTTP and provider receipts."""
from contextvars import ContextVar
import json
import os
from pathlib import Path
import time
from store_guard import transaction

current = ContextVar('vintos_request_trace', default=None)
LOG = str(Path.home() / '.vintos/workspace/memory/request-trace.jsonl')


def completion_join(result, surface):
    """Correlation for one recorded completion, not a delivery or origin attestation."""
    import hashlib
    import uuid
    text = result.get('text')
    if not isinstance(text, str) or not text:
        return {}
    trace = current.get()
    if trace is not None and (not isinstance(trace, str) or not 0 < len(trace) <= 256):
        trace = None
    join = dict(schema='router-completion-join-v1', completion_id=uuid.uuid4().hex,
                request_trace_id=trace, caller='router:' + str(surface),
                raw_response_sha256=hashlib.sha256(text.encode()).hexdigest())
    result['ledger_join'] = join
    return dict(generation_completion_id=join['completion_id'],
                generation_response_sha256=join['raw_response_sha256'])


class ReplyJoin:
    """One invocation-local observation; selection stays with the handler."""
    def __init__(self, observer=None):
        self.observer, self.join = observer, None

    def observe(self, result):
        import copy
        import hashlib
        import re
        self.join = None
        try:
            join = result.get('ledger_join')
            text = result.get('text')
            if (result.get('status') in ('valid', 'truncated') and isinstance(text, str) and text
                    and isinstance(join, dict) and set(join) == {'schema','completion_id','request_trace_id','caller','raw_response_sha256'}
                    and join['schema'] == 'router-completion-join-v1'
                    and isinstance(join['completion_id'], str) and re.fullmatch('[0-9a-f]{32}', join['completion_id'])
                    and isinstance(join['caller'], str) and 0 < len(join['caller']) <= 256
                    and (join['request_trace_id'] is None or isinstance(join['request_trace_id'], str)
                         and 0 < len(join['request_trace_id']) <= 256)
                    and join['raw_response_sha256'] == hashlib.sha256(text.encode()).hexdigest()):
                self.join = copy.deepcopy(join)
        except Exception:
            pass
        if self.observer is not None:
            try: self.observer(result)
            except Exception: pass

    def fields(self, raw_text, stored_text):
        import hashlib
        if (not self.join or not isinstance(raw_text, str) or not isinstance(stored_text, str)
                or hashlib.sha256(raw_text.encode()).hexdigest() != self.join['raw_response_sha256']):
            return {}
        return {'generation_join': dict(self.join,
                stored_response_sha256=hashlib.sha256(stored_text.encode()).hexdigest())}


def prepare_reply_join(options):
    if (not isinstance(options, dict) or set(options) - {'observer'}
            or 'observer' in options and not callable(options['observer'])):
        raise ValueError('invalid observation options')
    observation = ReplyJoin(options.get('observer'))
    return observation, {'observer': observation.observe}


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
