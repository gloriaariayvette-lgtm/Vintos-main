"""A thread/task-local read-only boundary for prompt candidate rendering."""
from contextlib import contextmanager
from contextvars import ContextVar
import os
import sys

_active = ContextVar("context_selection_readonly", default=False)

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
