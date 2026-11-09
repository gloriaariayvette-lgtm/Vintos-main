"""Content-free request correlation shared by HTTP and provider receipts."""
from contextvars import ContextVar
import json
import os
from pathlib import Path
import time
from store_guard import transaction

current = ContextVar('vintos_request_trace', default=None)
LOG = str(Path.home() / '.vintos/workspace/memory/request-trace.jsonl')


def event_turn_id(event_id):
    """Existing coordinator event-key rule; no event means no reserved identity."""
    import hashlib
    return "t-" + hashlib.sha256(str(event_id).encode()).hexdigest() if event_id else None


def forecast_turn_id():
    """Reserve the current HTTP event key without opening or authenticating a turn."""
    import re
    trace = current.get()
    if not isinstance(trace, str) or re.fullmatch(r"[A-Za-z0-9:._-]{1,160}", trace) is None:
        return ""
    return event_turn_id(trace)


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


MODE_ENV = 'VINTOS_TURN_MODE_RECEIPT'
MODE_FIELDS = {'schema','receipt_id','turn_id','request_id','surface','started_at','decision_at',
               'mode','basis','reroute_decision_at','reroute_reason','evaluated_completion_id','selected_completion_id',
               'raw_response_sha256','response_sha256'}


class TurnModeDecision:
    """In-memory observation of the existing gate; never calls, routes or writes."""
    def __init__(self, turn_id, surface, clock=time.time):
        import re
        import uuid
        request_id=current.get()
        if (not isinstance(turn_id,str) or re.fullmatch(r'[A-Za-z0-9:._-]{1,160}',turn_id) is None
                or not isinstance(request_id,str) or re.fullmatch(r'[A-Za-z0-9:._-]{1,160}',request_id) is None
                or surface not in ('avatar','reelroom')):
            raise ValueError('mode observation needs existing turn and request identities')
        self.clock=clock
        self.row=dict(schema='turn-mode-decision-v1',receipt_id=uuid.uuid4().hex,turn_id=turn_id,
            request_id=request_id,surface=surface,started_at=clock(),decision_at=None,mode='unknown',
            basis='gate_not_evaluated',reroute_decision_at=None,reroute_reason=None,evaluated_completion_id=None)

    def note(self, event, value=None, join=None):
        if event=='gate':
            answer=value.strip().upper() if isinstance(value,str) else ''
            self.row.update(decision_at=self.clock(),mode={'YES':'intimate','NO':'opening_everyday'}.get(answer,'unknown'),
                basis={'YES':'gate_yes','NO':'gate_no'}.get(answer,'gate_ambiguous'),
                evaluated_completion_id=(join or {}).get('completion_id'))
        elif event=='reroute':self.row.update(reroute_decision_at=self.clock(),reroute_reason='refusal_guard')
        elif event=='error' and self.row['decision_at'] is None:
            self.row.update(decision_at=self.clock(),basis='gate_error')

    def fields(self, join, raw_text, stored_text):
        import hashlib
        if (not isinstance(join,dict) or join.get('request_trace_id')!=self.row['request_id']
                or not isinstance(raw_text,str) or not isinstance(stored_text,str)
                or join.get('raw_response_sha256')!=hashlib.sha256(raw_text.encode()).hexdigest()):return {}
        receipt=dict(self.row,selected_completion_id=join.get('completion_id'),
            raw_response_sha256=join['raw_response_sha256'],response_sha256=hashlib.sha256(stored_text.encode()).hexdigest())
        return mode_receipt_fields(receipt,self.row['turn_id'],self.row['surface'],stored_text)


def mode_receipt_fields(receipt, turn_id, surface, text):
    """Validate content-free fields and exact stored-reply binding; no trust inference."""
    import hashlib
    import math
    import re
    if not isinstance(receipt,dict) or set(receipt)!=MODE_FIELDS or not isinstance(text,str):return {}
    if (receipt['schema']!='turn-mode-decision-v1' or receipt['turn_id']!=turn_id or receipt['surface']!=surface
            or surface not in ('avatar','reelroom')
            or any(not isinstance(receipt[k],str) or re.fullmatch(r'[A-Za-z0-9:._-]{1,160}',receipt[k]) is None for k in ('turn_id','request_id'))
            or any(not isinstance(receipt[k],str) or re.fullmatch(r'[0-9a-f]{32}',receipt[k]) is None for k in ('receipt_id','selected_completion_id'))
            or receipt['evaluated_completion_id'] is not None and (not isinstance(receipt['evaluated_completion_id'],str)
                or re.fullmatch(r'[0-9a-f]{32}',receipt['evaluated_completion_id']) is None)
            or not isinstance(receipt['raw_response_sha256'],str) or re.fullmatch(r'[0-9a-f]{64}',receipt['raw_response_sha256']) is None
            or receipt['response_sha256']!=hashlib.sha256(text.encode()).hexdigest()):return {}
    expected={'gate_not_evaluated':'unknown','gate_error':'unknown','gate_ambiguous':'unknown',
              'gate_yes':'intimate','gate_no':'opening_everyday'}
    if not isinstance(receipt['basis'],str) or receipt['basis'] not in expected or receipt['mode']!=expected[receipt['basis']]:return {}
    for key in ('started_at','decision_at','reroute_decision_at'):
        value=receipt[key]
        if value is None and key!='started_at':continue
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:return {}
    if (receipt['basis']=='gate_not_evaluated')!=(receipt['decision_at'] is None):return {}
    if receipt['decision_at'] is not None and receipt['decision_at']<receipt['started_at']:return {}
    if receipt['reroute_decision_at'] is not None and (receipt['decision_at'] is None or receipt['reroute_decision_at']<receipt['decision_at']):return {}
    if receipt['reroute_reason']!=('refusal_guard' if receipt['reroute_decision_at'] is not None else None):return {}
    if receipt['reroute_decision_at'] is not None and receipt['basis'] not in ('gate_yes','gate_ambiguous'):return {}
    if receipt['basis'] in ('gate_yes','gate_no','gate_ambiguous') and receipt['evaluated_completion_id'] is None:return {}
    return {'mode_receipt':dict(receipt)}


def mode_receipt_from_env(environ, turn_id, surface, text):
    try:
        raw=environ.get(MODE_ENV,'')
        if not isinstance(raw,str) or not 0<len(raw)<=4096:return {}
        return mode_receipt_fields(json.loads(raw),turn_id,surface,text)
    except Exception:return {}


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
