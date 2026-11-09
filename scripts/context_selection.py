"""A thread/task-local read-only boundary for prompt candidate rendering."""
from contextlib import contextmanager
from contextvars import ContextVar
import os
import sys

_active = ContextVar("context_selection_readonly", default=False)
_reads = ContextVar("context_selection_reads", default=None)


def observe_store_read(path, state, raw=None):
    """Hash an already completed guarded read; never reopen or classify its origin."""
    current = _reads.get()
    if current is None:
        return
    try:
        if len(current[0]) >= 64:
            _reads.set((current[0], True, current[2]))
            return
        import hashlib
        name = os.fsencode(os.fspath(path))
        record = {"resource_sha256": hashlib.sha256(name).hexdigest(), "state": state}
        hashed_chars = current[2]
        if isinstance(raw, str):
            if len(raw) + hashed_chars > 4194304:
                record["version_state"] = "over_limit"
            else:
                record["decoded_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
                hashed_chars += len(raw)
        _reads.set((current[0] + (record,), current[1], hashed_chars))
    except Exception:
        _reads.set((current[0], True, current[2]))


@contextmanager
def observe_reads():
    """Bounded context-local metadata, opt-in by the caller; no text or paths retained."""
    parent = _reads.get()
    token = _reads.set(((), False, parent[2] if parent is not None else 0))
    def snapshot():
        records, truncated, hashed_chars = _reads.get()
        return {"schema": "guarded-reads-v1", "coverage": "guarded_json_only",
                "reads": [dict(r) for r in records], "truncated": truncated}
    try:
        yield snapshot
    finally:
        records, truncated, hashed_chars = _reads.get()
        _reads.reset(token)
        parent = _reads.get()
        if parent is not None:
            combined = parent[0] + records
            _reads.set((combined[:64], parent[1] or truncated or len(combined) > 64, hashed_chars))

def _audit(event, args):
    if not _active.get(): return
    denied = event in {"os.remove","os.rename","os.mkdir","os.rmdir","os.truncate","os.chmod","os.chown","os.link","os.symlink","subprocess.Popen","os.system","socket.connect","socket.bind"}
    if event == "open":
        mode, flags = args[1:3]
        denied = any(c in str(mode or "") for c in "wax+") or bool((flags or 0) & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
    if denied: raise PermissionError("prompt selection cannot perform " + event)

sys.addaudithook(_audit)

@contextmanager
def readonly():
    token=_active.set(True)
    try: yield
    finally: _active.reset(token)
