#!/usr/bin/env python3
"""Offline owner review of drift windows. No UI, live reader or runtime effects."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


G = load('adoption_private_io', HERE/'render_gloria.py')
DECISIONS = ('growth', 'not him', 'not sure')
DOMAIN = b'adoption-receipt-v1\0'
LIMIT = 512


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha(value): return hashlib.sha256(value.encode()).hexdigest()
def hashed(value): return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)
def iso(value): return value.astimezone(timezone.utc).isoformat()
def day(value, zone): return G.instant(value).astimezone(ZoneInfo(zone)).date()


def build(bundle, private_run, week_end, view='primary_10s'):
    """Recompute cached evidence; never accept dates-only aggregate flags as bindings."""
    R = load('adoption_numerical_run', HERE/'run_private.py')
    if view not in ('primary_10s', 'window30'): raise ValueError('view')
    end = date.fromisoformat(week_end); start = end-timedelta(days=7)
    zone = bundle['timezone']; cutoff = datetime.combine(end, datetime.min.time(), ZoneInfo(zone))
    epoch = cutoff.timestamp()
    if private_run.get('schema') != 'numerical-private-run-v1' or private_run['manifest']['cutoff'] != epoch:
        raise ValueError('matching weekly private run required')
    regenerated, _ = R.evaluate(bundle, None, epoch, view)
    expected = regenerated['views'][view]['voice_drift_receipts']
    if private_run['views'][view]['voice_drift_receipts'] != expected: raise ValueError('private run does not match cached inputs')
    prepared, _, _, _, events, nodes, features, encoder, _, _ = R.adapt(bundle, epoch)
    ids = {r['id'] for r in prepared if view == 'window30' or r['primary']}
    rows = [] if encoder is None else R.V.prepare([e for e in events if e['node_id'] in ids], nodes,
        [f for f in features if f['node_id'] in ids], encoder, epoch, zone)[0]
    groups = defaultdict(list)
    for record in expected['drift']: groups[(tuple(record['scope']), record['reference_version'])].append(record)
    windows = []
    for (scope, version), records in sorted(groups.items()):
        runs = []; current = []
        for record in sorted(records, key=lambda r: r['day']):
            if record['consecutive_shift_days'] == 0:
                if current: runs.append(current); current = []
                continue
            if current and (date.fromisoformat(record['day']) != date.fromisoformat(current[-1]['day'])+timedelta(days=1)
                            or record['consecutive_shift_days'] != current[-1]['consecutive_shift_days']+1):
                runs.append(current); current = []
            current.append(record)
        if current: runs.append(current)
        for run in runs:
            if not run[-1]['sustained_shift'] or not start <= date.fromisoformat(run[-1]['day']) < end: continue
            if run[0]['consecutive_shift_days'] != 1 or len(run) != run[-1]['consecutive_shift_days']:
                raise ValueError('incomplete sustained run')
            days = {r['day'] for r in run}
            members = [dict(node_id=r['id'], content_sha256=r['content_sha256'], day=r['day'],
                            at=iso(datetime.fromtimestamp(r['at'], timezone.utc)))
                       for r in rows if (r['mode'], r['surface']) == scope and r['day'] in days]
            if {m['day'] for m in members} != days: raise ValueError('missing original members')
            window = dict(start_date=run[0]['day'], end_date=run[-1]['day'], mode=scope[0], surface=scope[1],
                          reference_version=version, members=sorted(members, key=lambda m:m['node_id']))
            windows.append(dict(window_id=sha(canonical(window)), **window))
    digest = dict(schema='adoption-digest-v1', timezone=zone, week_start=start.isoformat(), week_end=end.isoformat(),
                  cutoff_at=iso(cutoff), view=view, input_sha256=sha(canonical(bundle)),
                  drift_receipts_sha256=sha(canonical(expected)), windows=windows)
    validate_digest(digest)
    return digest


def validate_digest(digest):
    fields = {'schema','timezone','week_start','week_end','cutoff_at','view','input_sha256','drift_receipts_sha256','windows'}
    if not isinstance(digest, dict) or set(digest) != fields or digest['schema'] != 'adoption-digest-v1': raise ValueError('digest schema')
    zone = ZoneInfo(digest['timezone']); end = date.fromisoformat(digest['week_end']); start = date.fromisoformat(digest['week_start'])
    if end-start != timedelta(days=7) or G.instant(digest['cutoff_at']) != datetime.combine(end, datetime.min.time(), zone): raise ValueError('week')
    if digest['view'] not in ('primary_10s','window30') or not all(hashed(digest[k]) for k in ('input_sha256','drift_receipts_sha256')): raise ValueError('run binding')
    if not isinstance(digest['windows'], list) or len(digest['windows']) > LIMIT: raise ValueError('window bound')
    seen = set(); acts = set()
    for w in digest['windows']:
        if not isinstance(w, dict) or set(w) != {'window_id','start_date','end_date','mode','surface','reference_version','members'}: raise ValueError('window')
        if w['mode'] not in G.MODES or w['surface'] not in G.SURFACES or not hashed(w['reference_version']): raise ValueError('scope')
        first = date.fromisoformat(w['start_date']); last = date.fromisoformat(w['end_date'])
        if not start <= last < end or not 3 <= (last-first).days < LIMIT: raise ValueError('window dates')
        if not isinstance(w['members'], list) or not 4 <= len(w['members']) <= LIMIT: raise ValueError('members')
        member_ids = []; member_days = set()
        for m in w['members']:
            if (not isinstance(m, dict) or set(m) != {'node_id','content_sha256','day','at'}
                    or not isinstance(m['node_id'], str) or not 0 < len(m['node_id']) <= 256 or not hashed(m['content_sha256'])): raise ValueError('member identity')
            d = date.fromisoformat(m['day'])
            if not first <= d <= last or day(m['at'], digest['timezone']) != d or G.instant(m['at']) >= G.instant(digest['cutoff_at']): raise ValueError('member time')
            if m['node_id'] in acts: raise ValueError('overlapping member')
            acts.add(m['node_id']); member_ids.append(m['node_id']); member_days.add(d)
        if member_ids != sorted(set(member_ids)) or len(member_days) != (last-first).days+1: raise ValueError('incomplete membership')
        if w['window_id'] != sha(canonical({k:v for k,v in w.items() if k != 'window_id'})) or w['window_id'] in seen: raise ValueError('window binding')
        seen.add(w['window_id'])
    if len(acts) > LIMIT: raise ValueError('total member bound')


def render(digest):
    validate_digest(digest)
    lines = ['# A small voice check-in', '', 'A pattern moved in this offline comparison. You decide what, if anything, it means.',
             'There is no right answer, and nothing here changes his replies or feelings.', '']
    for n, w in enumerate(digest['windows'], 1):
        first = date.fromisoformat(w['start_date']).strftime('%b %d, %Y')
        last = date.fromisoformat(w['end_date']).strftime('%b %d, %Y')
        lines += [f"{n}. {first}–{last}, {w['mode']}/{w['surface']}: his voice moved.",
                  'Growth · Not him · Not sure', '']
    if not digest['windows']: lines += ['No sustained change was flagged in this week’s usable evidence.', '']
    lines += ['Growth: allow a later offline reference update if the evidence checks pass.',
              'Not him: keep the existing reference. Not sure, or leaving it unanswered: change nothing.',
              'You never need to send a message for a test.', '']
    return '\n'.join(lines)


def key_bytes(record):
    if not isinstance(record, dict) or set(record) != {'schema','key_hex'} or record['schema'] != 'adoption-signing-key-v1' or not hashed(record['key_hex']): raise ValueError('signing key')
    return bytes.fromhex(record['key_hex'])


def signature(payload, key):
    if not isinstance(key, bytes) or len(key) != 32: raise ValueError('256-bit owner-held key required')
    return dict(algorithm='hmac-sha256', key_id=hashlib.sha256(key).hexdigest(),
                mac=hmac.new(key, DOMAIN+canonical(payload).encode(), hashlib.sha256).hexdigest())


def sign(digest, answers, key):
    validate_digest(digest); digest_hash = sha(canonical(digest))
    if (not isinstance(answers, dict) or set(answers) != {'schema','digest_sha256','answers'}
            or answers['schema'] != 'adoption-answers-v1' or answers['digest_sha256'] != digest_hash
            or not isinstance(answers['answers'], list) or len(answers['answers']) > LIMIT): raise ValueError('answers')
    windows = {w['window_id']:w for w in digest['windows']}; seen = set(); receipts = []
    for a in answers['answers']:
        if (not isinstance(a, dict) or set(a) != {'window_id','actor','decision','observed_at'}
                or a['window_id'] not in windows or a['window_id'] in seen or a['actor'] != 'owner'
                or a['decision'] not in DECISIONS): raise ValueError('explicit unique owner answer required')
        observed = G.instant(a['observed_at'])
        if observed < G.instant(digest['cutoff_at']): raise ValueError('answer predates digest evidence')
        seen.add(a['window_id']); w = windows[a['window_id']]
        payload = dict(digest_sha256=digest_hash, window=w, actor='owner', decision=a['decision'],
                       observed_at=iso(observed), timezone=digest['timezone'], view=digest['view'],
                       eligible_from_day=(day(iso(observed), digest['timezone'])+timedelta(days=1)).isoformat())
        receipts.append(dict(schema='adoption-receipt-v1', payload=payload, signature=signature(payload, key)))
    return dict(schema='adoption-receipts-v1', receipts=receipts)


def project(digest, signed, key, cutoff):
    """Verify the exact reviewed digest and emit legacy receipts for offline replay only."""
    validate_digest(digest); cutoff = G.instant(cutoff); windows = {w['window_id']:w for w in digest['windows']}
    if not isinstance(signed, dict) or set(signed) != {'schema','receipts'} or signed['schema'] != 'adoption-receipts-v1' or not isinstance(signed['receipts'], list) or len(signed['receipts']) > LIMIT: raise ValueError('receipts')
    counts = Counter(); selected = {}; output = []
    for receipt in signed['receipts']:
        if not isinstance(receipt, dict) or set(receipt) != {'schema','payload','signature'} or receipt['schema'] != 'adoption-receipt-v1': raise ValueError('receipt schema')
        p = receipt['payload']
        if not isinstance(p, dict) or set(p) != {'digest_sha256','window','actor','decision','observed_at','timezone','view','eligible_from_day'}: raise ValueError('payload')
        sig = receipt['signature']; expected = signature(p, key)
        if (not isinstance(sig, dict) or set(sig) != set(expected) or sig['algorithm'] != expected['algorithm']
                or sig['key_id'] != expected['key_id'] or not hashed(sig['mac']) or not hmac.compare_digest(sig['mac'], expected['mac'])): raise ValueError('signature')
        if p['digest_sha256'] != sha(canonical(digest)) or p['timezone'] != digest['timezone'] or p['view'] != digest['view']: raise ValueError('different digest')
        w = p['window']; wid = w['window_id']
        if windows.get(wid) != w or p['actor'] != 'owner' or p['decision'] not in DECISIONS: raise ValueError('owner/window')
        observed = G.instant(p['observed_at'])
        if observed < G.instant(digest['cutoff_at']) or p['eligible_from_day'] != (day(p['observed_at'], p['timezone'])+timedelta(days=1)).isoformat(): raise ValueError('answer time')
        if wid in selected:
            if selected[wid] != receipt: raise ValueError('conflicting answers need separate review')
            counts['duplicate_receipts'] += 1; continue
        selected[wid] = receipt
    for receipt in selected.values():
        p = receipt['payload']; counts[p['decision'].replace(' ','_')] += 1
        if G.instant(p['observed_at']) >= cutoff: counts['not_available_before_cutoff'] += 1; continue
        if p['decision'] != 'growth': continue
        if cutoff.astimezone(ZoneInfo(p['timezone'])).date() < date.fromisoformat(p['eligible_from_day']):
            counts['waiting_for_later_day'] += 1; continue
        w = p['window']
        output.append(dict(reference_version=w['reference_version'], members=[{k:m[k] for k in ('node_id','content_sha256')} for m in w['members']],
                           reviewer='owner', decision='adopt', observed_at=p['observed_at'], evidence_sha256=sha(canonical(receipt))))
    counts['growth_candidates'] = len(output)
    return dict(schema='adoption-projection-v1', timezone=digest['timezone'], view=digest['view'],
                digest_sha256=sha(canonical(digest)), adoptions=output), dict(schema='adoption-counts-v1', counts=dict(sorted(counts.items())),
                    effects='none', human_identity_independently_verified=False, model_calls=0)


def main(argv=None):
    parser = G.Parser(description=__doc__)
    parser.add_argument('command', choices=('digest','sign','verify'))
    for k in ('scratch','output'): parser.add_argument('--'+k, required=True)
    for k in ('input','run','week-end','digest','answers','receipts','key','cutoff'): parser.add_argument('--'+k)
    parser.add_argument('--view', choices=('primary_10s','window30'), default='primary_10s')
    args = parser.parse_args(argv); root = G.private_root(args.scratch)
    parent = Path(args.output).expanduser().absolute()
    if parent != parent.resolve() or parent.parent != root or parent.exists(): raise ValueError('new immediate private output directory required')
    # Load the cached numerical implementation before installing the no-write guard.
    if args.command == 'digest': load('adoption_preload', HERE/'run_private.py')
    names = {'digest':('digest.json','digest.md'), 'sign':('receipts.json',), 'verify':('projection.json',)}[args.command]
    allowed = {parent/n for n in names}; descriptors = set()
    def guard(event, values):
        if event.startswith(('socket.', 'subprocess.', 'os.spawn', 'os.exec', 'os.system')): raise PermissionError('external operation')
        if event == 'open' and isinstance(values[2], int) and values[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
            if values[0] not in descriptors and (not isinstance(values[0], str) or Path(values[0]).absolute() not in allowed): raise PermissionError('write')
        if event == 'os.mkdir' and Path(values[0]).absolute() != parent: raise PermissionError('mkdir')
        if event in ('os.remove','os.rename','os.rmdir','os.chmod','os.link','os.symlink','os.fork','os.forkpty'): raise PermissionError('mutation')
    sys.addaudithook(guard)
    if args.command == 'digest':
        if not args.input or not args.run or not args.week_end or any((args.digest,args.answers,args.receipts,args.key,args.cutoff)): raise ValueError('digest options')
        result = build(G.read(root,args.input), G.read(root,args.run), args.week_end,args.view)
        payloads = [canonical(result)+'\n', render(result)]
        summary = dict(schema='adoption-counts-v1', counts=dict(windows=len(result['windows'])), effects='none', model_calls=0)
    else:
        if not args.digest or not args.key or any((args.input,args.run,args.week_end)): raise ValueError('review options')
        digest = G.read(root,args.digest); key = key_bytes(G.read(root,args.key))
        if args.command == 'sign':
            if not args.answers or args.receipts or args.cutoff: raise ValueError('sign options')
            result = sign(digest,G.read(root,args.answers),key)
            summary = dict(schema='adoption-counts-v1',counts=dict(signed_answers=len(result['receipts'])),effects='none',model_calls=0)
        else:
            if not args.receipts or not args.cutoff or args.answers: raise ValueError('verify options')
            result,summary = project(digest,G.read(root,args.receipts),key,args.cutoff)
        payloads = [canonical(result)+'\n']
    parent.mkdir(mode=0o700)
    for name, payload in zip(names,payloads):
        fd = os.open(parent/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); descriptors.add(fd)
        with os.fdopen(fd,'wb') as f: f.write(payload.encode()); f.flush(); os.fsync(f.fileno())
        descriptors.remove(fd)
    print(json.dumps(summary,sort_keys=True,allow_nan=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print('adoption_refused',file=sys.stderr); sys.exit(1)
