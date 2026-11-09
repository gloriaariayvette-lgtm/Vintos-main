"""Dedicated optional shadow storage. No workspace redirection, transport or model."""
import argparse
from collections import Counter
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
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
DEFERRED_COUNT_KEYS = ('enqueued', 'written', 'not_confirmed', 'full', 'unavailable', 'spooled', 'replayed')
RESERVE = 8192  # Lock, status and one atomic status replacement.
SPOOL_BYTES = 8 * 1024 * 1024
SPOOL_FILES = 64
SPOOL_NAME = '.capture-spool'
SPOOL_PACKET = re.compile(r'[0-9a-f]{32}\.packet\Z')
PREFIXES = ('capture-', 'value-map-call-', 'value-map-build-', 'self-forecast-inputs-', 'self-forecast-launch-', 'self-forecast-handoff-', 'self-forecast-clock-', 'self-forecast-artifacts-', 'self-audit-embedding-', 'self-fit-completion-')
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
        if set(c) - {'durable_queue'} != {'schema', 'enabled', 'directory', 'max_bytes', 'max_files', 'retention_seconds', 'max_packet_bytes'} or c['schema'] != 'judges-shadow-sink-v1':
            raise ValueError('invalid shadow config')
        if type(c.get('durable_queue',False)) is not bool:
            raise ValueError('invalid queue mode')
        if c.get('durable_queue') and (type(c.get('max_bytes')) is not int or c['max_bytes'] <= SPOOL_BYTES + RESERVE):
            raise ValueError('insufficient durable sink capacity')
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


def _publish_bytes(root, payload, prefix, expected=None, diagnostic=None, packet_id=None, retained_at=None):
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
        if retained_at is not None:
            clock = time.time()
            if (packet_id is None or type(retained_at) not in (int,float)
                    or not math.isfinite(retained_at) or retained_at<0 or not math.isfinite(clock)
                    or not 0<=clock-retained_at<=c['retention_seconds']):
                raise ValueError('invalid replay retention clock')
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
                    if retained_at is not None and info.st_mtime>retained_at:
                        os.utime(name,(retained_at,retained_at),dir_fd=directory,follow_symlinks=False)
                    os.fsync(f.fileno())
                os.fsync(directory)
                COUNTERS['already_published'] += 1
                return True
        now = time.time()
        total = files = expired = 0
        spool_reserve = SPOOL_BYTES if c.get('durable_queue') else 0
        with os.scandir(directory) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_FILES + 16: raise ValueError('directory entry limit')
                name = entry.name
                if name in ('.capture.lock', 'status.json'): continue
                if name == SPOOL_NAME:
                    child = os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
                    try: _spool_entries(child)
                    finally: os.close(child)
                    spool_reserve = SPOOL_BYTES
                    continue
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
        state = None if payload is None else ('written' if files < c['max_files'] and total + len(payload) + RESERVE + spool_reserve <= c['max_bytes'] else 'capacity')
        if configuration(root) != c:
            COUNTERS['disabled_or_changed'] += 1
            return False
        if state == 'written':
            name = prefix + (packet_id or uuid.uuid4().hex) + '.json'
            _atomic(directory, name, payload)
            if retained_at is not None:
                os.utime(name,(retained_at,retained_at),dir_fd=directory,follow_symlinks=False)
                fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
                try: os.fsync(fd)
                finally: os.close(fd)
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


def _config_sha(c):
    value = dict(c, directory=str(c['directory']))
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _spool_entries(directory):
    info = os.fstat(directory)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('unsafe spool directory')
    entries = []
    total = 0
    inodes = set()
    with os.scandir(directory) as scan:
        for index, entry in enumerate(scan):
            if index >= SPOOL_FILES + 4: raise ValueError('spool entry limit')
            if entry.name != '.lock' and not (SPOOL_PACKET.fullmatch(entry.name)
                    or re.fullmatch(r'\.pending-[0-9a-f]{32}',entry.name)):
                raise ValueError('unmanaged spool entry')
            try: info = entry.stat(follow_symlinks=False)
            except FileNotFoundError: continue  # A concurrent atomic write finished.
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError('unsafe spool entry')
            identity = (info.st_dev,info.st_ino)
            if identity not in inodes:
                total += info.st_size
                inodes.add(identity)
            if entry.name != '.lock': entries.append((entry.name,info.st_size,info.st_mtime))
    if total + RESERVE > SPOOL_BYTES: raise ValueError('spool byte limit')
    return entries, total


@contextmanager
def _spool_lock(c, create=False):
    root = directory = lock = None
    try:
        if configuration(c['directory']) != c or not c.get('durable_queue'):
            raise ValueError('durable configuration changed')
        root = os.open(c['directory'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        info = os.fstat(root)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('unsafe spool root')
        if create:
            try: os.mkdir(SPOOL_NAME,mode=0o700,dir_fd=root)
            except FileExistsError: pass
        directory = os.open(SPOOL_NAME,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root)
        _spool_entries(directory)
        lock = os.open('.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=directory)
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('unsafe spool lock')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if configuration(c['directory']) != c: raise ValueError('durable configuration changed')
        yield root, directory
    finally:
        if lock is not None: os.close(lock)
        if directory is not None: os.close(directory)
        if root is not None: os.close(root)


def _spool_read(directory, name):
    fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    with os.fdopen(fd,'rb') as f:
        info = os.fstat(f.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_PACKET+2048):
            raise ValueError('unsafe spool record')
        line = f.readline(2049)
        if len(line)>2048 or not line.endswith(b'\n'): raise ValueError('invalid spool header')
        def unique(pairs):
            out = {}
            for key,value in pairs:
                if key in out: raise ValueError('ambiguous spool header')
                out[key] = value
            return out
        header = json.loads(line,object_pairs_hook=unique)
        payload = f.read(MAX_PACKET+1)
    expected_keys = {'schema','configuration','created_at','sha256'}
    if isinstance(header,dict) and header.get('schema')=='judges-ingress-v2': expected_keys.add('prefix')
    if (not isinstance(header,dict) or set(header) != expected_keys
            or header.get('schema') not in ('judges-ingress-v1','judges-ingress-v2')
            or (header.get('schema')=='judges-ingress-v2' and header.get('prefix')!='self-forecast-launch-')
            or not isinstance(header['configuration'],str) or not re.fullmatch('[0-9a-f]{64}',header['configuration'])
            or type(header['created_at']) not in (int,float) or not math.isfinite(header['created_at']) or header['created_at']<0
            or not payload or len(payload)>MAX_PACKET
            or hashlib.sha256(payload).hexdigest()!=header['sha256']):
        raise ValueError('invalid spool record')
    return header,payload


def _stage_capture(c,payload,prefix="capture-"):
    """True confirms synced private ingress, not final publication or phone delivery."""
    try:
        if prefix not in ('capture-','self-forecast-launch-'): raise ValueError('unsupported ingress prefix')
        now = time.time()
        if not math.isfinite(now) or now<0 or not payload or len(payload)>c['max_packet_bytes']:
            raise ValueError('invalid ingress')
        header = dict(schema='judges-ingress-v1',configuration=_config_sha(c),created_at=now,
                      sha256=hashlib.sha256(payload).hexdigest())
        if prefix!='capture-': header.update(schema='judges-ingress-v2',prefix=prefix)
        record = json.dumps(header,separators=(',',':')).encode()+b'\n'+payload
        with _spool_lock(c,create=True) as (root,directory):
            entries,total = _spool_entries(directory)
            if len(entries)>=SPOOL_FILES or total+len(record)+RESERVE>SPOOL_BYTES:
                COUNTERS['spool_full'] += 1
                _note_ingress(c,'full')
                return False
            # Existing files may predate durable mode or a reduced capacity.
            # Never assume reserved headroom just because the new config asks for it.
            retained = 0
            with os.scandir(root) as scan:
                for index,entry in enumerate(scan):
                    if index>=MAX_FILES+16: raise ValueError('sink entry limit')
                    if entry.name in (SPOOL_NAME,'.capture.lock','status.json'): continue
                    if not (PACKET.fullmatch(entry.name) or re.fullmatch(r'\.pending-[0-9a-f]{32}',entry.name)):
                        raise ValueError('unmanaged sink entry')
                    try: info = entry.stat(follow_symlinks=False)
                    except FileNotFoundError: continue
                    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
                        raise ValueError('unsafe sink entry')
                    retained += info.st_size
            if retained+total+len(record)+RESERVE>c['max_bytes']:
                COUNTERS['spool_full'] += 1
                _note_ingress(c,'full')
                return False
            if configuration(c['directory']) != c: return False
            _atomic(directory,uuid.uuid4().hex+'.packet',record)
            os.fsync(directory)
            os.fsync(root)
        COUNTERS['spool_staged'] += 1
        _note_ingress(c,'spooled')
        return True
    except Exception:
        COUNTERS['spool_not_confirmed'] += 1
        _note_ingress(c,'not_confirmed')
        return False


def recover_spool(limit=8):
    """Bounded replay; disabled/changed config never publishes old ingress."""
    if type(limit) is not int or not 1<=limit<=SPOOL_FILES: raise ValueError('invalid replay limit')
    c = configuration()
    if c is None or not c.get('durable_queue'): return 0
    clock = time.time()
    if not math.isfinite(clock) or clock<0:
        COUNTERS['spool_clock_unavailable'] += 1
        return 0
    confirmed = 0
    try:
        with _spool_lock(c) as (_,directory):
            entries,_ = _spool_entries(directory)
        attempted = 0
        for name,_,mtime in sorted(entries,key=lambda row:(row[2],row[0])):
            with _spool_lock(c) as (_,directory):
                if not SPOOL_PACKET.fullmatch(name):
                    # Uncommitted temporary records are never replayed.
                    if time.time()-mtime>c['retention_seconds']:
                        os.unlink(name,dir_fd=directory);os.fsync(directory)
                    continue
                try: header,payload = _spool_read(directory,name)
                except FileNotFoundError: continue
                except (ValueError,TypeError,UnicodeError):
                    COUNTERS['spool_invalid'] += 1
                    continue
                if header['configuration'] != _config_sha(c): continue
                age = clock-header['created_at']
                if age<0: continue
                if age>c['retention_seconds']:
                    os.unlink(name,dir_fd=directory);os.fsync(directory)
                    COUNTERS['spool_expired'] += 1
                    continue
            if attempted>=limit: break
            attempted += 1
            # Do not hold the ingress lock across the slower final sink scan.
            if not _publish_bytes(c['directory'],payload,header.get('prefix','capture-'),expected=c,packet_id=name[:-7],retained_at=header['created_at']):
                continue
            with _spool_lock(c) as (_,directory):
                try: current,body = _spool_read(directory,name)
                except FileNotFoundError: continue
                if current!=header or body!=payload: raise ValueError('ingress changed during replay')
                os.unlink(name,dir_fd=directory);os.fsync(directory)
            confirmed += 1
            COUNTERS['spool_replayed'] += 1
            _note_ingress(c,'replayed')
    except FileNotFoundError: pass
    except Exception: COUNTERS['spool_replay_unconfirmed'] += 1
    return confirmed


def _note_ingress(c,key):
    if _writer_lock.acquire(blocking=False):
        try: _note_deferred_locked(c,key)
        finally: _writer_lock.release()
    else: COUNTERS['deferred_diagnostic_unconfirmed'] += 1


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
    next_recovery = time.monotonic()
    while True:
        if time.monotonic() >= next_recovery:
            # Startup and a busy volatile queue must not starve durable ingress.
            recover_spool()
            next_recovery = time.monotonic() + 0.25
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


def _ensure_writer_locked():
    global _writer
    if _writer is None:
        pending = CaptureQueue()
        thread = threading.Thread(target=_write_queued,args=(pending,),name='judges-capture-writer',daemon=True)
        thread.start()
        _writer = (os.getpid(),pending,thread)
    return _writer[0]==os.getpid() and _writer[2].is_alive()


def start_recovery():
    """Startup hook: enabled durable mode only; actual disk recovery is background."""
    c = configuration()
    if c is None or not c.get('durable_queue'): return False
    if not _writer_lock.acquire(blocking=False): return False
    try: return _ensure_writer_locked()
    except Exception:
        COUNTERS['deferred_unavailable'] += 1
        return False
    finally: _writer_lock.release()


def enqueue_capture(root, packet, *, prefix="capture-"):
    """Snapshot final chat capture or a forecast launch; neither confirms delivery.

    Default True means volatile admission without waiting for storage or a slot.
    Explicit durable mode waits for private ingress file/directory sync instead;
    True then confirms ingress, not final publication. Other producers keep their
    synchronous semantics. Neither mode adds a shutdown flush.
    """
    global _writer
    try:
        if prefix not in ('capture-','self-forecast-launch-'): return False
        c = configuration(root)
        if c is None:
            COUNTERS['disabled_or_changed'] += 1
            return False
        payload = (json.dumps(packet, allow_nan=False) + '\n').encode()
        if len(payload) > c['max_packet_bytes']:
            COUNTERS['oversize'] += 1
            return False
        if c.get('durable_queue'):
            staged = _stage_capture(c,payload) if prefix=='capture-' else _stage_capture(c,payload,prefix)
            start_recovery()  # Staging remains confirmed even if worker startup fails.
            return staged
        if not _writer_lock.acquire(blocking=False):
            COUNTERS['deferred_busy'] += 1
            return False
        try:
            if not _ensure_writer_locked():
                COUNTERS['deferred_unavailable'] += 1
                _note_deferred_locked(c, 'unavailable')
                return False
            try:
                _writer[1].put_nowait((root, payload, prefix, c))
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
        if set(c)-{'durable_queue'} != {'schema','enabled','directory','max_bytes','max_files','retention_seconds','max_packet_bytes'}:
            raise ValueError('invalid shadow config')
        if type(c.get('durable_queue',False)) is not bool or (c.get('durable_queue')
                and (type(c.get('max_bytes')) is not int or c['max_bytes']<=SPOOL_BYTES+RESERVE)):
            raise ValueError('invalid durable queue config')
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
