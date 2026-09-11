#!/usr/bin/env python3
"""store_guard.py - a store that will not parse is quarantined and reported, never silently emptied.

Review item 47 (2026-09-10). The interaction ledger and the WAL log already quarantined a corrupt file
to .corrupt-<ts>; every other store's reader did `try: json.load() except: return default`, which
turns a torn write into an empty pool and then overwrites the evidence on the next save. This is the
one reader for those stores: a missing file is the default; a file that exists but does not parse is
copied to <path>.corrupt-<stamp>, one line goes to memory/store-quarantine.jsonl, and the default is
returned - the next save writes a fresh file, the corrupt bytes stay beside it.

    load_json(path, default)            -> the parsed object, or default (with quarantine when corrupt)
    save_json(path, obj)                -> atomic write (tmp + replace)
    quarantined(limit=20)               -> the reported events
"""
import os, json, time, shutil

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
LOG = os.path.join(MEMORY, "store-quarantine.jsonl")


def load_json(path, default, reader=""):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            raw = f.read()
        if not raw.strip():
            return default
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError) as e:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        q = "%s.corrupt-%s" % (path, stamp); k = 1
        while os.path.exists(q):
            k += 1; q = "%s.corrupt-%s-%d" % (path, stamp, k)
        try:
            shutil.copy2(path, q)
        except Exception:
            q = "(copy failed)"
        try:
            os.makedirs(MEMORY, exist_ok=True)
            with open(LOG, "a") as lf:
                lf.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "store": os.path.basename(path), "path": path,
                                     "quarantined_to": q, "error": str(e)[:200], "reader": reader}) + "\n")
        except OSError:
            pass
        print("[store-guard] %s does not parse (%s); kept at %s; serving the default" % (os.path.basename(path), str(e)[:80], os.path.basename(q)), flush=True)
        return default
    except OSError:
        return default


def save_json(path, obj, indent=2):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=indent)
    os.replace(tmp, path)


def write_json(path, obj, reader="", indent=2):
    """review 46: lock, then write atomically. The one-liner for a saver that already holds the whole
    object. Snapshot replacement only; read-modify-write callers must hold transaction(path)."""
    return locked_update(path, lambda _cur: obj, reader=reader)


def locked_update(path, mutate, default=None, reader=""):
    """review 46: the one read-modify-write for a store more than one organ writes. Under an exclusive
    flock on <path>.lock: load (quarantining a corrupt file), hand the object to `mutate`, write what it
    returns atomically. `mutate` returning None means no change and nothing is written."""
    with transaction(path):
        cur = load_json(path, default if default is not None else [], reader=reader)
        out = mutate(cur)
        if out is None:
            return cur
        save_json(path, out)
        return out


def quarantined(limit=20):
    out = []
    try:
        for ln in open(LOG):
            try: out.append(json.loads(ln))
            except Exception: pass
    except Exception:
        pass
    return out[-limit:]


if __name__ == "__main__":
    for q in quarantined():
        print("  %s %-28s -> %s (%s)" % (q["at"][:16], q["store"], os.path.basename(q["quarantined_to"]), q["error"][:60]))


from contextlib import contextmanager
import threading
_locks = {}
_state = threading.local()
@contextmanager
def transaction(path):
    """Serialize complete operations; all writes fail closed on lock failure."""
    import fcntl
    path = os.path.abspath(path)
    lock = _locks.setdefault(path, threading.RLock())
    with lock:
        held = getattr(_state, "held", set())
        if path in held:
            yield
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".lock", "a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            _state.held = held | {path}
            try: yield
            finally: _state.held = held


def serialized(path_name):
    import functools
    def wrap(fn):
        @functools.wraps(fn)
        def call(*args, **kwargs):
            with transaction(path_name() if callable(path_name) else fn.__globals__[path_name]):
                return fn(*args, **kwargs)
        return call
    return wrap


@contextmanager
def transactions(paths):
    """Acquire a declared set in stable order; never hold across an await."""
    from contextlib import ExitStack
    with ExitStack() as stack:
        for path in sorted({os.path.abspath(p) for p in paths}):
            stack.enter_context(transaction(path))
        yield


def compare_and_swap(path, expected, replacement, default=None):
    """Commit derived work only if its input snapshot is still current.

    Inference stays outside the lock. A conflict returns False, never merges
    evidence for an obsolete input. Malformed/unreadable stores fail closed.
    """
    with transaction(path):
        try:
            with open(path) as handle:
                current = json.load(handle)
        except FileNotFoundError:
            current = default
        if current != expected:
            return False
        save_json(path, replacement)
        return True
