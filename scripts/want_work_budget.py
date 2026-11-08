"""Private limits for the dedicated want lane; no providers or sends."""
import json
import os
from pathlib import Path
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULTS = {'per_want_calls': 8, 'daily_calls': 16, 'context_chars': 60000}


class WorkBlocked(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def ensure_running(ws):
    if os.path.lexists(Path(ws) / 'memory/want-work.stop'):
        raise WorkBlocked('want_lane_stopped')


def policy(ws):
    path = Path(ws) / 'memory/want-work-policy.json'
    if path.is_symlink(): raise WorkBlocked('invalid_work_policy')
    try: value = json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError): raise WorkBlocked('invalid_work_policy')
    if not isinstance(value, dict): raise WorkBlocked('invalid_work_policy')
    out = dict(DEFAULTS)
    for key, maximum in (('per_want_calls', 1000), ('daily_calls', 1000), ('context_chars', 250000)):
        n = value.get(key, out[key])
        if type(n) is not int or n < (1000 if key == 'context_chars' else 0) or n > maximum:
            raise WorkBlocked('invalid_work_policy')
        out[key] = n
    return out


def reserve(ws, request_id, attempt_id, lane, now=None):
    """Count every lane attempt, including failures; never expire an uncertain call."""
    from store_guard import transaction
    ensure_running(ws)
    limits = policy(ws)
    now = time.time() if now is None else now
    day = datetime.fromtimestamp(now, ZoneInfo('America/Chicago')).date().isoformat()
    root = Path(ws) / 'memory/want-work-control'
    if root.resolve() != root.absolute(): raise WorkBlocked('linked_work_budget')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / 'calls.json'
    if path.is_symlink() or Path(str(path)+'.lock').is_symlink(): raise WorkBlocked('linked_work_budget')
    with transaction(str(path)):
        ensure_running(ws)
        try: data = json.loads(path.read_text()) if path.exists() else {'schema':'want-work-calls-v1','calls':{}}
        except (OSError, ValueError): raise WorkBlocked('invalid_work_budget')
        if not isinstance(data, dict): raise WorkBlocked('invalid_work_budget')
        if data.get('schema') != 'want-work-calls-v1' or not isinstance(data.get('calls'), dict):
            raise WorkBlocked('invalid_work_budget')
        calls = data['calls']
        if any(not isinstance(c, dict) or not isinstance(c.get('request_id'), str)
               or not isinstance(c.get('day'), str) for c in calls.values()):
            raise WorkBlocked('invalid_work_budget')
        if attempt_id in calls: raise WorkBlocked('attempt_already_reserved')
        if sum(c['request_id'] == request_id for c in calls.values()) >= limits['per_want_calls']:
            raise WorkBlocked('per_want_call_cap')
        if sum(c['day'] == day for c in calls.values()) >= limits['daily_calls']:
            raise WorkBlocked('daily_call_cap')
        calls[attempt_id] = {'request_id':request_id,'day':day,'lane':lane,'at':now,'state':'intent'}
        temp = root / ('.calls-' + uuid.uuid4().hex)
        try:
            with os.fdopen(os.open(temp, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as f:
                json.dump(data, f, allow_nan=False); f.flush(); os.fsync(f.fileno())
            os.replace(temp, path)
            fd = os.open(root, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
        finally:
            if temp.exists(): temp.unlink()
