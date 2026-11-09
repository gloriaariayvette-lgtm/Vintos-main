"""Dedicated optional shadow storage. No workspace redirection, transport or model."""
import argparse
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import re
import queue
import threading
import stat
import time
import uuid

COUNTERS = Counter()  # Process-local fallback when the sink itself cannot be written.
MAX_BYTES = 256 * 1024 * 1024
MAX_FILES = 4096
MAX_PACKET = 1024 * 1024
RETENTION = 7 * 86400
RESERVE = 8192  # Lock, status and one atomic status replacement.
PREFIXES = ('capture-', 'value-map-call-', 'value-map-build-', 'self-forecast-inputs-', 'self-forecast-clock-', 'self-forecast-artifacts-', 'self-audit-embedding-')
PACKET = re.compile(r'(?:' + '|'.join(PREFIXES) + r')[0-9a-f]{32}\.json\Z')


def private_directory(value):
    raw = Path(value).absolute()
    root = raw.resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    workspace = os.environ.get('SPARK_WORKSPACE')
    if (root != raw or not root.is_dir() or root in (Path('/'), Path.home())
            or any(x in ('.vintos', '.openclaw', '.git') for x in root.parts)):
        raise ValueError('invalid shadow destination')
    for p in [repo] + ([Path(workspace).resolve()] if workspace else []):
        if root == p or root in p.parents or p in root.parents:
            raise ValueError('invalid shadow destination')
    info = root.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('shadow destination must be owner-private')
    return root


def _read_private(path, limit):
    raw = Path(path).absolute()
    if raw.resolve(strict=True) != raw:
        raise ValueError('invalid private configuration path')
    fd = os.open(raw, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > limit):
            raise ValueError('invalid private configuration permissions')
        data = f.read(limit + 1)
    if len(data) > limit: raise ValueError('configuration too large')
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out: raise ValueError('ambiguous configuration')
            out[key] = value
        return out
    return json.loads(data, object_pairs_hook=unique)


def configuration(expected=None):
    """Absent, disabled or invalid config never enables production capture."""
    location = os.environ.get('JUDGES_CAPTURE_CONFIG')
    if not location:
        return None
    try:
        c = _read_private(location, 4096)
        if not isinstance(c, dict) or c.get('enabled') is not True:
            return None
        if set(c) != {'schema', 'enabled', 'directory', 'max_bytes', 'max_files', 'retention_seconds', 'max_packet_bytes'} or c['schema'] != 'judges-shadow-sink-v1':
            raise ValueError('invalid shadow config')
        for key, ceiling, floor in [('max_bytes',MAX_BYTES,RESERVE+1), ('max_files',MAX_FILES,1),
                                    ('retention_seconds',RETENTION,1), ('max_packet_bytes',MAX_PACKET,1)]:
            if type(c[key]) is not int or not floor <= c[key] <= ceiling:
                raise ValueError('invalid shadow limit')
        root = private_directory(c['directory'])
        if expected is not None and Path(expected) != root:
            raise ValueError('shadow destination changed')
        return dict(c, directory=root)
    except Exception:
        COUNTERS['configuration_unavailable'] += 1
        return None


def _atomic(directory, name, payload, replace=False):
    info = os.fstat(directory)
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise ValueError('unsafe publication directory')
    temporary = '.pending-' + uuid.uuid4().hex
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(payload); f.flush(); os.fsync(f.fileno())
        if replace:
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        else:
            os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
    finally:
        try: os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError: pass


def publish(root, packet, prefix):
    """Synchronous best-effort publication for existing background producers."""
    c = configuration(root)
    if c is None:
        COUNTERS['disabled_or_changed'] += 1
        return False
    try:
        payload = (json.dumps(packet, allow_nan=False) + '\n').encode()
        return _publish_bytes(root, payload, prefix, expected=c)
    except Exception:
        COUNTERS['write_failure'] += 1
        return False


def _publish_bytes(root, payload, prefix, expected=None):
    """Publish an immutable snapshot, rechecking current limits and permission."""
    c = configuration(root)
    if c is None or (expected is not None and c != expected):
        COUNTERS['disabled_or_changed'] += 1
        return False
    directory = lock = None
    try:
        if prefix not in PREFIXES: raise ValueError('unknown packet type')
        if not isinstance(payload, bytes): raise ValueError('immutable payload required')
        if len(payload) > c['max_packet_bytes']:
            COUNTERS['oversize'] += 1
            return False
        directory = os.open(c['directory'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('destination changed')
        lock = os.open('.capture.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('invalid lock')
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            COUNTERS['busy'] += 1
            return False
        # Recheck after acquiring the lock. A disabled or retargeted in-flight
        # invocation must not write a packet into the old destination.
        if configuration(root) != c:
            COUNTERS['disabled_or_changed'] += 1
            return False
        now = time.time()
        total = files = expired = 0
        with os.scandir(directory) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_FILES + 16: raise ValueError('directory entry limit')
                name = entry.name
                if name in ('.capture.lock', 'status.json'): continue
                if not (PACKET.fullmatch(name) or re.fullmatch(r'\.pending-[0-9a-f]{32}', name)):
                    raise ValueError('unmanaged sink entry')
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                    raise ValueError('unsafe sink entry')
                if now - info.st_mtime > c['retention_seconds']:
                    os.unlink(name, dir_fd=directory); expired += 1
                else:
                    total += info.st_size; files += 1
        previous = {}
        try:
            previous = _read_private(c['directory'] / 'status.json', 4096).get('counts', {})
        except FileNotFoundError: pass
        if not isinstance(previous, dict) or any(k not in ('written','capacity','expired') or type(v) is not int or not 0 <= v < 10**18 for k,v in previous.items()):
            previous = {}
        state = 'written' if files < c['max_files'] and total + len(payload) + RESERVE <= c['max_bytes'] else 'capacity'
        if configuration(root) != c:
            COUNTERS['disabled_or_changed'] += 1
            return False
        if state == 'written':
            _atomic(directory, prefix + uuid.uuid4().hex + '.json', payload)
            files += 1; total += len(payload)
        COUNTERS[state] += 1
        # Persistent counters for lock-owning operations, never a complete-stream
        # claim. Busy/invalid-path failures remain in process-local COUNTERS.
        previous[state] = previous.get(state, 0) + 1
        previous['expired'] = previous.get('expired', 0) + expired
        status = {'schema':'judges-shadow-status-v1','counts':previous,'retained_files':files,'retained_bytes':total,
                  'coverage':'lock-owning operations only; process failures and busy skips may be absent'}
        _atomic(directory, 'status.json', (json.dumps(status)+'\n').encode(), replace=True)
        os.fsync(directory)
        return state == 'written'
    except Exception:
        COUNTERS['write_failure'] += 1
        return False
    finally:
        if lock is not None: os.close(lock)
        if directory is not None: os.close(directory)


# Eight pending immutable packets plus one in flight, each at most MAX_PACKET.
# This is a volatile per-process queue, not a durability or delivery receipt.
DEFERRED_SLOTS = 8
_writer = None
_writer_lock = threading.Lock()


def _reset_after_fork():
    global _writer, _writer_lock
    _writer = None
    _writer_lock = threading.Lock()
    COUNTERS.clear()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_reset_after_fork)


def _write_queued(pending):
    while True:
        item = pending.get()
        try:
            if item is None: return
            root, payload, prefix, config = item
            try:
                ok = _publish_bytes(root, payload, prefix, expected=config)
                COUNTERS['deferred_written' if ok else 'deferred_not_confirmed'] += 1
            except Exception:
                COUNTERS['deferred_not_confirmed'] += 1
        finally:
            pending.task_done()
            item = None  # Do not retain the previous private payload while idle.
            root = payload = prefix = config = None


def enqueue_capture(root, packet):
    """True means queued only. Never wait for storage or a free queue slot.

    Used only at final chat capture. Other producers keep synchronous semantics.
    Process exit can lose queued work; no shutdown flush delays serving shutdown.
    """
    global _writer
    try:
        c = configuration(root)
        if c is None:
            COUNTERS['disabled_or_changed'] += 1
            return False
        payload = (json.dumps(packet, allow_nan=False) + '\n').encode()
        if len(payload) > c['max_packet_bytes']:
            COUNTERS['oversize'] += 1
            return False
        if not _writer_lock.acquire(blocking=False):
            COUNTERS['deferred_busy'] += 1
            return False
        try:
            if _writer is None:
                pending = queue.Queue(maxsize=DEFERRED_SLOTS)
                thread = threading.Thread(target=_write_queued, args=(pending,), name='judges-capture-writer', daemon=True)
                thread.start()
                _writer = (os.getpid(), pending, thread)
            if _writer[0] != os.getpid() or not _writer[2].is_alive():
                COUNTERS['deferred_unavailable'] += 1
                return False
            try:
                _writer[1].put_nowait((root, payload, 'capture-', c))
            except queue.Full:
                COUNTERS['deferred_full'] += 1
                return False
            COUNTERS['deferred_enqueued'] += 1
            return True
        finally:
            _writer_lock.release()
    except Exception:
        COUNTERS['deferred_unavailable'] += 1
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('enable','disable'))
    p.add_argument('--config', required=True)
    args = p.parse_args()
    path = Path(args.config).absolute()
    c = _read_private(path,4096)
    if not isinstance(c,dict) or c.get('schema') != 'judges-shadow-sink-v1':
        raise ValueError('requires a prepared private sink configuration')
    c['enabled'] = args.action == 'enable'
    if c['enabled']:
        if set(c) != {'schema','enabled','directory','max_bytes','max_files','retention_seconds','max_packet_bytes'}:
            raise ValueError('invalid shadow config')
        # Validate the full proposed configuration through the same reader before
        # publication, without changing any serving environment or workspace.
        private_directory(c['directory'])
        for key, cap, floor in [('max_bytes',MAX_BYTES,RESERVE+1),('max_files',MAX_FILES,1),
                                ('retention_seconds',RETENTION,1),('max_packet_bytes',MAX_PACKET,1)]:
            if type(c.get(key)) is not int or not floor <= c[key] <= cap: raise ValueError('invalid shadow limit')
    directory = os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: _atomic(directory,path.name,(json.dumps(c,indent=2)+'\n').encode(),replace=True)
    finally: os.close(directory)
    print('Shadow capture configuration enabled.' if c['enabled'] else 'Shadow capture configuration disabled.')

if __name__ == '__main__': main()
