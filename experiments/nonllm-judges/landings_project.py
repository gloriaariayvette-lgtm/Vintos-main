#!/usr/bin/env python3
"""Project authorized private Landings snapshots; no live-store discovery or calls."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from zoneinfo import ZoneInfo
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('landings_private_io', HERE/'render_gloria.py')
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
TEXT = {'message': 'message', 'joke': 'joke', 'journal': 'entry'}
LIMIT = 4096


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha(value): return hashlib.sha256(value.encode()).hexdigest()
def hashed(value): return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)
def identifier(value): return isinstance(value, str) and 0 < len(value) <= 256


def instant(value, source_zone=None):
    if not isinstance(value, str): raise ValueError('explicit timestamp required')
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is not None: return d.astimezone(timezone.utc).timestamp()
    if source_zone is None: raise ValueError('source timezone unknown')
    tz = ZoneInfo(source_zone)
    candidates = set()
    for fold in (0, 1):
        utc = d.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc)
        if utc.astimezone(tz).replace(tzinfo=None) == d: candidates.add(utc.timestamp())
    if len(candidates) != 1: raise ValueError('ambiguous or nonexistent local time')
    return next(iter(candidates))


def bindings_index(bindings):
    if not isinstance(bindings, dict) or set(bindings) != {'schema', 'items'} or bindings['schema'] != 'landings-item-bindings-v1': raise ValueError('binding schema')
    if not isinstance(bindings['items'], list) or len(bindings['items']) > 512: raise ValueError('binding bound')
    index = {}; nodes = {}
    fields = {'surface', 'ref', 'node_id', 'content_sha256', 'finalized_at', 'identity_source_sha256'}
    for item in bindings['items']:
        if (not isinstance(item, dict) or set(item) != fields or item['surface'] not in TEXT
                or not identifier(item['ref']) or not identifier(item['node_id'])
                or not hashed(item['content_sha256']) or not hashed(item['identity_source_sha256'])): raise ValueError('binding')
        key = (item['surface'], item['ref']); normalized = dict(item, finalized_at=instant(item['finalized_at']))
        if key in index and index[key] != normalized: raise ValueError('conflicting item binding')
        if item['node_id'] in nodes and nodes[item['node_id']] != key: raise ValueError('ambiguous original identity')
        index[key] = normalized; nodes[item['node_id']] = key
    return index


def project(records, bindings, cutoff, source_zone=None):
    cutoff = instant(cutoff)
    if source_zone is not None: ZoneInfo(source_zone)
    if not isinstance(records, list) or len(records) > LIMIT: raise ValueError('record bound')
    index = bindings_index(bindings); seen = {}; latest = {}; poisoned = set(); counts = Counter()
    for row in records:
        counts['input_records'] += 1
        if (not isinstance(row, dict) or not identifier(row.get('id')) or not identifier(row.get('ref'))
                or not isinstance(row.get('surface'), str)): raise ValueError('record identity')
        encoded = canonical(row); rid = row['id']; key = (row['surface'], row['ref'])
        if rid in seen:
            if seen[rid] != encoded: raise ValueError('conflicting rating identity')
            counts['duplicate_records'] += 1; continue
        seen[rid] = encoded
        try: observed = instant(row.get('at'), source_zone)
        except (ValueError, TypeError, OverflowError):
            poisoned.add(key); counts['unknown_observation_time'] += 1; continue
        if observed >= cutoff: counts['at_or_after_cutoff'] += 1; continue
        if key in latest:
            counts['superseded_records'] += 1
            if observed < latest[key][1]:
                poisoned.add(key); counts['backward_item_clock'] += 1
        latest[key] = (row, observed, sha(encoded))
    anchors = []
    for key, (row, observed, record_hash) in latest.items():
        if key in poisoned: counts['items_with_unknown_order'] += 1; continue
        kind, ref = key
        if kind not in TEXT: counts['unsupported_media_or_kind'] += 1; continue
        if row.get('rating') != 'landed': counts['not_landed'] += 1; continue
        if not isinstance(row.get('why'), str) or not row['why'].strip(): counts['invalid_native_rating'] += 1; continue
        piece = row.get('piece'); made = row.get('made')
        if (not isinstance(piece, dict) or piece.get('type') != kind or not isinstance(piece.get('text'), str)
                or not 0 < len(piece['text']) <= 10000 or not isinstance(made, dict)
                or made.get(TEXT[kind]) != piece['text']):
            counts['missing_or_conflicting_frozen_text'] += 1; continue
        binding = index.get(key)
        if binding is None: counts['missing_exact_item_binding'] += 1; continue
        content_hash = sha(piece['text'])
        if binding['content_sha256'] != content_hash: counts['full_content_mismatch'] += 1; continue
        if not binding['finalized_at'] <= observed: counts['rating_before_original_act'] += 1; continue
        node = binding['node_id']
        # Hash namespacing keeps native long IDs within the downstream 256-character bound.
        anchors.append(dict(evidence_id='landings-'+sha(row['id']), node_id=node, content_sha256=content_hash,
            actor='owner', witnessed=True, observed_at=observed, source='landings', value='landed',
            link=dict(kind='exact_item', item_id=node, item_sha256=content_hash, item_kind=kind),
            source_record_sha256=record_hash))
    counts['projected_positive_anchors'] = len(anchors)
    summary = dict(schema='landings-project-counts-v1', counts=dict(sorted(counts.items())),
        policy='latest_recorded_rating_per_item_before_cutoff', source_claims_independently_verified=False,
        private_text_in_output=False, model_calls=0)
    return dict(schema='landings-projection-v1', anchors=anchors), summary


def read_jsonl(root, value):
    path = Path(value).expanduser().absolute()
    if path != path.resolve() or not path.is_relative_to(root): raise ValueError('private input')
    for parent in (path.parent, *path.parent.parents):
        if parent == root.parent: break
        info = parent.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077: raise ValueError('private parent')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077: raise ValueError('private file')
        data = f.read(G.MAX_BYTES+1)
    if len(data) > G.MAX_BYTES: raise ValueError('input too large')
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out: raise ValueError('duplicate key')
            out[key] = value
        return out
    def invalid(value): raise ValueError('nonfinite value')
    rows = []
    for line in data.decode('utf-8').splitlines():
        if not line.strip(): continue
        rows.append(json.loads(line, object_pairs_hook=unique, parse_constant=invalid))
        if len(rows) > LIMIT: raise ValueError('record bound')
    return rows


def main(argv=None):
    parser = G.Parser(description=__doc__)
    for key in ('scratch', 'snapshot', 'bindings', 'cutoff', 'output'): parser.add_argument('--'+key, required=True)
    parser.add_argument('--source-timezone')
    args = parser.parse_args(argv); root = G.private_root(args.scratch)
    output = Path(args.output).expanduser().absolute(); parent = output.parent
    if output != output.resolve() or parent.parent != root or parent.exists() or output.name != 'landings-projection.json':
        raise ValueError('new private output directory required')
    output_fd = None
    # Only this new directory/file can be written. Existing inputs are never writable.
    def guard(event, values):
        if event.startswith(('socket.', 'subprocess.', 'os.spawn', 'os.exec', 'os.system')): raise PermissionError('external operation')
        if event == 'open' and isinstance(values[2], int) and values[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            if values[0] != output_fd and (not isinstance(values[0], str) or Path(values[0]).absolute() != output): raise PermissionError('write')
        if event == 'os.mkdir' and Path(values[0]).absolute() != parent: raise PermissionError('mkdir')
        if event in ('os.remove', 'os.rename', 'os.rmdir', 'os.chmod', 'os.link', 'os.symlink', 'os.fork', 'os.forkpty'): raise PermissionError('mutation')
    sys.addaudithook(guard)
    records = read_jsonl(root, args.snapshot); bindings = G.read(root, args.bindings)
    result, summary = project(records, bindings, args.cutoff, args.source_timezone)
    payload = (canonical(result)+'\n').encode()
    parent.mkdir(mode=0o700)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    output_fd = fd
    with os.fdopen(fd, 'wb') as f:
        f.write(payload); f.flush(); os.fsync(f.fileno())
    print(json.dumps(summary, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print('landings_projection_refused', file=sys.stderr); sys.exit(1)
