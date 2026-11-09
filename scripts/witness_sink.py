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
DEFERRED_COUNT_KEYS = ('enqueued', 'written', 'not_confirmed', 'full', 'unavailable')
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


def _publish_bytes(root, payload, prefix, expected=None, diagnostic=None, packet_id=None):
    """Publish an immutable snapshot, rechecking current limits and permission."""
    c = configuration(root)
    if c is None or (expected is not None and c != expected):
        COUNTERS['disabled_or_changed'] += 1
        return False
    directory = lock = None
    try:
        if prefix not in PREFIXES: raise ValueError('unknown packet type')
        if packet_id is not None and (not isinstance(packet_id,str)
                or not re.fullmatch(r'[0-9a-f]{32}',packet_id) or diagnostic is not None or payload is None):
            raise ValueError('invalid replay publication')
        if diagnostic is not None and (not isinstance(diagnostic, dict) or any(
                k not in DEFERRED_COUNT_KEYS or type(v) is not int or not 0 <= v < 10**18
                for k,v in diagnostic.items())):
            raise ValueError('invalid deferred diagnostic')
        if not isinstance(payload, bytes) and not (payload is None and diagnostic):
            raise ValueError('immutable payload required')
        if payload is not None and len(payload) > c['max_packet_bytes']:
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
        # A durable ingress record can retry its stable name after an uncertain
        # publication outcome. Never replace conflicting or unsafe evidence.
        if packet_id is not None:
            name = prefix + packet_id + '.json'
            try:
                existing = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                with os.fdopen(existing,'rb') as f:
                    info = os.fstat(f.fileno())
                    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != len(payload)
                            or f.read(len(payload)+1) != payload):
                        raise ValueError('conflicting replay publication')
                    if configuration(root) != c:
                        COUNTERS['disabled_or_changed'] += 1
                        return False
                    os.fsync(f.fileno())
                os.fsync(directory)
                COUNTERS['already_published'] += 1
                return True
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
        previous_status = {}
        try:
            previous_status = _read_private(c['directory'] / 'status.json', 4096)
        except FileNotFoundError: pass
        if not isinstance(previous_status, dict): raise ValueError('invalid status')
        previous = previous_status.get('counts', {})
        deferred = previous_status.get('deferred', {}).get('counts', {})
        if not isinstance(deferred, dict) or any(k not in DEFERRED_COUNT_KEYS or type(v) is not int
                or not 0 <= v < 10**18 for k,v in deferred.items()):
            raise ValueError('invalid deferred status')
        for key, value in (diagnostic or {}).items():
            deferred[key] = min(10**18-1, deferred.get(key, 0) + value)
        if not isinstance(previous, dict) or any(k not in ('written','capacity','expired') or type(v) is not int or not 0 <= v < 10**18 for k,v in previous.items()):
            previous = {}
        state = None if payload is None else ('written' if files < c['max_files'] and total + len(payload) + RESERVE <= c['max_bytes'] else 'capacity')
        if configuration(root) != c:
            COUNTERS['disabled_or_changed'] += 1
            return False
        if state == 'written':
            _atomic(directory, prefix + (packet_id or uuid.uuid4().hex) + '.json', payload)
            files += 1; total += len(payload)
        if state is not None: COUNTERS[state] += 1
        # Persistent counters for lock-owning operations, never a complete-stream
        # claim. Busy/invalid-path failures remain in process-local COUNTERS.
        if state is not None: previous[state] = previous.get(state, 0) + 1
        previous['expired'] = previous.get('expired', 0) + expired
        status = {'schema':'judges-shadow-status-v1','counts':previous,'retained_files':files,'retained_bytes':total,
                  'coverage':'lock-owning operations only; process failures and busy skips may be absent'}
        if deferred:
            status['deferred'] = dict(counts=deferred, restart_loss=None,
                coverage='persisted lower bounds; unflushed observations, busy skips and process-exit losses are unknown; counts are not a loss balance')
        _atomic(directory, 'status.json', (json.dumps(status)+'\n').encode(), replace=True)
        os.fsync(directory)
        return state is None or state == 'written'
    except Exception:
        COUNTERS['write_failure'] += 1
        return False
    finally:
        if lock is not None: os.close(lock)
        if directory is not None: os.close(directory)


# Up to 64 pending packets, with eight MiB of serialized payload plus one in flight.
# This is a volatile per-process queue, not a durability or delivery receipt.
DEFERRED_SLOTS = 64
DEFERRED_BYTES = 8 * MAX_PACKET


class CaptureQueue(queue.Queue):
    """FIFO bounded by both packet count and bytes; hooks run under Queue's mutex."""
    def __init__(self):
        self.queued_bytes = 0
        self.byte_limit = DEFERRED_BYTES
        super().__init__(maxsize=DEFERRED_SLOTS)

    def _put(self, item):
        size = 0 if item is None else len(item[1])
        if self.queued_bytes + size > self.byte_limit:
            raise queue.Full
        super()._put(item)
        self.queued_bytes += size

    def _get(self):
        item = super()._get()
        if item is not None:
            self.queued_bytes -= len(item[1])
        return item


_writer = None
_writer_lock = threading.Lock()
_deferred_pending = {}  # At most eight configuration-scoped scalar counter batches.


def _note_deferred_locked(config, key):
    identity = tuple(sorted(config.items()))
    if identity not in _deferred_pending:
        if len(_deferred_pending) >= 8:
            COUNTERS['deferred_diagnostic_scope_full'] += 1
            return
        _deferred_pending[identity] = (config, Counter())
    _deferred_pending[identity][1][key] += 1


def _take_deferred(config):
    with _writer_lock:
        entry = _deferred_pending.pop(tuple(sorted(config.items())), None)
    return dict(entry[1]) if entry else None


def _flush_deferred():
    # Claim once before I/O. Failed/ambiguous writes are never retried, because a
    # replace may have succeeded before fsync failed. Undercount instead of double count.
    with _writer_lock:
        batches = list(_deferred_pending.values())
        _deferred_pending.clear()
    for config, counts in batches:
        try:
            ok = _publish_bytes(config['directory'], None, 'capture-', expected=config, diagnostic=dict(counts))
        except Exception: ok = False
        if not ok: COUNTERS['deferred_diagnostic_unconfirmed'] += 1


def _reset_after_fork():
    global _writer, _writer_lock, _deferred_pending
    _writer = None
    _writer_lock = threading.Lock()
    _deferred_pending = {}
    COUNTERS.clear()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_reset_after_fork)


def _write_queued(pending):
    while True:
        try: item = pending.get(timeout=0.25)
        except queue.Empty:
            _flush_deferred()
            continue
        try:
            if item is None: return
            root, payload, prefix, config = item
            try:
                diagnostic = _take_deferred(config)
                ok = _publish_bytes(root, payload, prefix, expected=config, diagnostic=diagnostic)
            except Exception: ok = False
            outcome = 'written' if ok else 'not_confirmed'
            COUNTERS['deferred_' + outcome] += 1
            with _writer_lock: _note_deferred_locked(config, outcome)
            if pending.empty(): _flush_deferred()
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
                pending = CaptureQueue()
                thread = threading.Thread(target=_write_queued, args=(pending,), name='judges-capture-writer', daemon=True)
                thread.start()
                _writer = (os.getpid(), pending, thread)
            if _writer[0] != os.getpid() or not _writer[2].is_alive():
                COUNTERS['deferred_unavailable'] += 1
                _note_deferred_locked(c, 'unavailable')
                return False
            try:
                _writer[1].put_nowait((root, payload, 'capture-', c))
            except queue.Full:
                COUNTERS['deferred_full'] += 1
                _note_deferred_locked(c, 'full')
                return False
            COUNTERS['deferred_enqueued'] += 1
            _note_deferred_locked(c, 'enqueued')
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
