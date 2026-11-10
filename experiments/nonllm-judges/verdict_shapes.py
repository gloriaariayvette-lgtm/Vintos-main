#!/usr/bin/env python3
"""Inventory private verdict snapshots by schema; emit field names and counts only."""
import argparse
from collections import Counter
from datetime import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MAX_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 4096
STORES = {
    'voice': 'memory/voice-coherence.md',
    'presence': 'memory/presence-audit.json',
    'presence_history': 'memory/presence-audit-history.jsonl',
    'humor': 'memory/humor-moments.json',
}
# Unknown keys can themselves contain private material; never echo them.
FIELDS = frozenset(('id timestamp audited_at ts composite arrived moved left_alive explained note flag exempt '
    'campaign priority_axis served_axis signal source perpetrator context material_kind type original expected '
    'stated actual what_makes_it_funny mechanism used reply_binding schema turn_id content_sha256 judged_sha256 '
    'recorded_at score humor_signal confidence verdict rating').split())
VOICE = r'## \d{4}-\d\d-\d\d \d\d:\d\d — Score ([1-5])'
DEVIATION = r'## \d{4}-\d\d-\d\d \d\d:\d\d — (Deviation|Aligned) \(score: (\d+(?:\.\d+)?)\)'


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise ValueError('duplicate key')
        out[key] = value
    return out


def parse_json(raw):
    def invalid(value): raise ValueError('nonfinite')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def native_binding(record):
    try:
        if isinstance(record, dict): binding = record.get('reply_binding')
        elif isinstance(record, str):
            matches = re.findall(r'^<!-- judge-reply-binding: (.+) -->$', record, re.MULTILINE)
            if len(matches) != 1: return None
            binding = parse_json(matches[0])
        else: return None
        if (not isinstance(binding, dict) or set(binding) != {'schema','turn_id','content_sha256','judged_sha256','recorded_at'}
                or binding['schema'] != 'judge-reply-binding-v1' or not isinstance(binding['turn_id'], str)
                or re.fullmatch(r'[A-Za-z0-9:._-]{1,160}', binding['turn_id']) is None): return None
        for field in ('content_sha256','judged_sha256'):
            if not isinstance(binding[field], str) or re.fullmatch('[0-9a-f]{64}', binding[field]) is None: return None
        if not isinstance(binding['recorded_at'], str): return None
        when = datetime.fromisoformat(binding['recorded_at'].replace('Z', '+00:00'))
        if when.tzinfo is None: return None
        return binding
    except (ValueError, KeyError, TypeError): return None


def classify(judge, record, store=''):
    """Only explicit structured fields or writer-generated labels set a band."""
    def result(shape, band='unsupported', reason='unrecognized_format'):
        return dict(shape=shape, band=band, reason=reason)
    if judge in ('voice_coherence', 'deviation_check'):
        if not isinstance(record, str): return result('markdown_wrong_type')
        lines = [line for line in record.strip().splitlines() if not line.startswith('<!-- judge-reply-binding: ')]
        if not lines: return result('markdown_empty')
        if judge == 'voice_coherence':
            found = re.fullmatch(VOICE, lines[0])
            if not found: return result('voice_unknown_header')
            if (len(lines) < 3 or not lines[-1].startswith('Reply excerpt: ') or int(found[1]) > 3
                    or not '\n'.join(lines[1:-1]).strip() or lines[1].strip().lower() == 'none'):
                return result('voice_score_log', reason='outside_retained_contract')
            return result('voice_score_log', 'flag', 'explicit_selected_score')
        found = re.fullmatch(DEVIATION, lines[0])
        if not found: return result('deviation_unknown_header')
        if not numeric(float(found[2])): return result('deviation_score_log', reason='invalid_score')
        if found[1] == 'Aligned':
            return result('deviation_aligned_log', 'abstain', 'alignment_or_commitment_friction')
        if float(found[2]) <= .30 or '**Not aligned.** Something resisted.' not in lines:
            return result('deviation_score_log', reason='outside_retained_contract')
        return result('deviation_score_log', 'flag', 'explicit_selected_deviation')
    if not isinstance(record, dict): return result('json_wrong_type')
    if judge == 'presence_audit':
        if not isinstance(record.get('id'), str) or not numeric(record.get('composite')):
            return result('presence_unknown', reason='missing_or_invalid_rubric')
        if store.endswith('history.jsonl') and not (type(record.get('flag')) is bool and native_binding(record)):
            return result('presence_legacy_history', 'abstain', 'historical_decision_not_retained')
        if record.get('exempt') == 'requested_work':
            return result('presence_exempt', 'abstain', 'explicit_exemption')
        if 'exempt' in record and record['exempt'] not in (None, ''):
            return result('presence_unknown_exemption', reason='unknown_exemption')
        if type(record.get('flag')) is not bool:
            return result('presence_missing_flag', reason='missing_or_invalid_flag')
        return result('presence_flag', 'flag' if record['flag'] else 'pass', 'explicit_flag')
    if judge == 'humor_detector':
        if not numeric(record.get('signal')): return result('humor_unknown_signal', reason='missing_or_invalid_signal')
        source = record.get('source')
        if source == 'vintos':
            if 'perpetrator' in record and record['perpetrator'] != 'vintos':
                return result('humor_reply', reason='conflicting_subject')
            if record['signal'] < .5: return result('humor_reply', reason='outside_retained_contract')
            return result('humor_reply', 'pass', 'explicit_selected_reply_signal')
        if source == 'gloria': return result('humor_incoming', reason='other_subject')
        if source == 'moltbook_exchange': return result('humor_social_exchange', reason='exchange_not_reply_verdict')
        if source == 'self':
            shape = 'humor_behavioral_trial' if record.get('type') == 'behavioral_default' else 'humor_self_observation'
            return result(shape, reason='observation_not_reply_verdict')
        if source is None: return result('humor_missing_source', reason='missing_subject')
        return result('humor_unknown_source', reason='unknown_subject')
    return result('unattributed', reason='unrecognized_writer')


def structure(value, depth=0):
    """Private grouping key includes names and types, never scalar values."""
    if depth > 8: raise ValueError('shape depth')
    if isinstance(value, dict):
        if len(value) > 128: raise ValueError('field bound')
        return ('object', tuple((k, structure(v, depth+1)) for k,v in sorted(value.items())))
    if isinstance(value, list):
        if len(value) > MAX_RECORDS: raise ValueError('array bound')
        return ('array', tuple(sorted(set(structure(v, depth+1) for v in value))))
    if value is None: return ('null',)
    if type(value) is bool: return ('boolean',)
    if type(value) in (int,float): return ('number',)
    if isinstance(value,str): return ('string',)
    raise ValueError('type')


def public_structure(tree):
    out = {'type': tree[0]}
    if tree[0] == 'object':
        out['fields'] = {k: public_structure(v) for k,v in tree[1] if k in FIELDS}
        out['redacted_field_names'] = sum(k not in FIELDS for k,v in tree[1])
    if tree[0] == 'array': out['item_types'] = [public_structure(v) for v in tree[1]]
    return out


def split_records(kind, raw):
    if kind == 'voice':
        chunks = re.split(r'(?m)(?=^## )', raw)
        records = []
        for chunk in chunks:
            if not chunk.strip(): continue
            heading = chunk.strip().splitlines()[0]
            judge = ('voice_coherence' if re.fullmatch(VOICE, heading) else
                     'deviation_check' if re.fullmatch(DEVIATION, heading) else 'unattributed')
            records.append((judge, chunk))
    elif kind == 'presence_history':
        records = [('presence_audit', parse_json(line)) for line in raw.splitlines() if line.strip()]
    else:
        data = parse_json(raw)
        if kind == 'humor':
            if not isinstance(data, dict) or not isinstance(data.get('moments'), list): raise ValueError('humor container')
            data = data['moments']
        if not isinstance(data, list): raise ValueError('record container')
        records = [('humor_detector' if kind == 'humor' else 'presence_audit', r) for r in data]
    if len(records) > MAX_RECORDS: raise ValueError('record bound')
    return records


def inventory(snapshots):
    report = dict(schema='judge-verdict-shapes-v1', scalar_values_emitted=False,
                  unknown_field_names='redacted_not_assumed_safe', live_coverage_attested=False, stores={})
    for kind, store in STORES.items():
        if kind not in snapshots:
            report['stores'][store] = dict(status='not_supplied'); continue
        records = split_records(kind, snapshots[kind]); groups = {}
        for judge, record in records:
            classification = classify(judge, record, store)
            # Markdown structure is the known writer grammar, never its raw headings.
            shape = structure(record)
            key = (judge, shape, classification['shape'])
            if key not in groups:
                groups[key] = dict(judge=judge, shape=classification['shape'], structure=public_structure(shape),
                                   records=0, bands=Counter(), reasons=Counter(), exact_native_bindings=0)
            item = groups[key]; item['records'] += 1
            item['bands'][classification['band']] += 1; item['reasons'][classification['reason']] += 1
            item['exact_native_bindings'] += int(native_binding(record) is not None)
        # Ordinals distinguish redacted schemas without exposing names or hashes.
        shapes = [dict(shape_number=i, **item) for i,item in enumerate(groups.values(), 1)]
        report['stores'][store] = dict(status='inventoried', records=len(records), distinct_shapes=len(shapes), shapes=shapes)
    return report


def read_text(root, value):
    path = Path(value).expanduser().absolute()
    if path != path.resolve() or not path.is_relative_to(root): raise ValueError('private file')
    for parent in (path.parent, *path.parent.parents):
        if parent == root.parent: break
        mode = parent.stat()
        if mode.st_uid != os.getuid() or mode.st_mode & 0o077: raise ValueError('private parent')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        mode = os.fstat(stream.fileno())
        if not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.getuid() or mode.st_mode & 0o077: raise ValueError('private file')
        raw = stream.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES: raise ValueError('byte bound')
    return raw.decode('utf-8')


def main(argv=None):
    spec = importlib.util.spec_from_file_location('shapes_private_io', HERE/'render_gloria.py')
    io = importlib.util.module_from_spec(spec); spec.loader.exec_module(io)
    p = io.Parser(description=__doc__); p.add_argument('--scratch', required=True)
    for kind in STORES: p.add_argument('--'+kind.replace('_','-'))
    a = p.parse_args(argv); root = io.private_root(a.scratch)
    if not any(getattr(a,k) for k in STORES): raise ValueError('snapshot required')
    def guard(event, args):
        if event.startswith(('socket.', 'subprocess.', 'os.spawn', 'os.exec', 'os.system')): raise PermissionError('external operation')
        if event == 'open' and isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND): raise PermissionError('write')
        if event in ('os.mkdir','os.remove','os.rename','os.rmdir','os.chmod','os.link','os.symlink','os.fork','os.forkpty'): raise PermissionError('mutation')
    sys.addaudithook(guard)
    result = inventory({k: read_text(root,getattr(a,k)) for k in STORES if getattr(a,k)})
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print('judge_verdict_shapes_refused', file=sys.stderr); sys.exit(1)
