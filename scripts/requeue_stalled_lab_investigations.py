#!/usr/bin/env python3
"""One-off repair, 2026-10-29: reopen the Lab investigations a missing module stalled.

On 29 October lab_names was not installed, and every investigation turn failed before its first step with
"ModuleNotFoundError: No module named 'lab_names'". Three such turns in a row close an investigation as stalled
(lab_investigations.MAX_PLANNING_FAILURES), so investigations opened through the day were closed for a fault of the
house, not of their question. lab_names is installed now. This reopens ONLY those: state stalled, closed for that
reason. Each goes back to open with its failure counter reset, its closing reason kept under `requeued`, and nothing
else about it changed. Investigations stalled for any other reason are left as they are.

Idempotent: a reopened investigation is open, so a second run finds nothing to do. With --apply the store is
copied beside itself first (investigations.json.bak-requeue-<stamp>), and the write is made under the Lab's lock,
only if the store did not change since it was read (the Lab writes it between turns; run again if it did).

    python3 scripts/requeue_stalled_lab_investigations.py            # counts only; changes nothing
    python3 scripts/requeue_stalled_lab_investigations.py --apply    # reopens them, after a backup
    python3 scripts/requeue_stalled_lab_investigations.py --apply --limit 10   # at most ten, oldest first
"""
import argparse
import collections
import hashlib
import os
import shutil
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import chemistry_lab as lab          # noqa: E402  the Lab's own store helpers and lock
import lab_investigations as inv     # noqa: E402

REASON = "No module named 'lab_names'"


def matches(investigation):
    """Stalled by the missing lab_names module, and by nothing else."""
    if not isinstance(investigation, dict) or investigation.get('state') != 'stalled':
        return False
    closed = str(investigation.get('closed_reason') or '')
    last = str(investigation.get('last_planning_error') or '')
    return ('failed before any step' in closed and 'ModuleNotFoundError' in closed and REASON in closed
            and (not last or (('ModuleNotFoundError' in last) and REASON in last)))


def _digest(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def plan(data, limit=None):
    """(to reopen, counts): the matching investigations, oldest first, and a tally of every state."""
    rows = [i for i in data.get('investigations', []) if isinstance(i, dict)]
    found = sorted((i for i in rows if matches(i)), key=lambda i: str(i.get('opened_at') or ''))
    stalled = [i for i in rows if i.get('state') == 'stalled']
    counts = {'investigations': len(rows), 'by_state': dict(collections.Counter(str(i.get('state')) for i in rows)),
              'stalled': len(stalled), 'stalled_by_lab_names': len(found),
              'stalled_for_other_reasons': len(stalled) - len(found),
              'opened_between': [found[0].get('opened_at'), found[-1].get('opened_at')] if found else None}
    if limit is not None:
        found = found[:max(0, int(limit))]
    counts['would_reopen'] = len(found)
    return found, counts


def reopen(investigation, at):
    """Back to open: the failure counter reset, the closing reason kept, nothing else touched."""
    investigation['requeued'] = {'at': at, 'from_state': investigation.get('state'),
                                 'closed_reason': investigation.get('closed_reason'),
                                 'planning_failures': investigation.get('planning_failures'),
                                 'by': 'requeue_stalled_lab_investigations'}
    investigation['state'] = 'open'
    investigation['planning_failures'] = 0
    for key in ('closed_reason', 'last_planning_error', 'deferred_until'):
        investigation.pop(key, None)


def run(apply=False, limit=None, out=print):
    path = inv._path('investigations.json')
    before = _digest(path)
    data = lab._load(path, {'investigations': []}) or {'investigations': []}
    found, counts = plan(data, limit)
    out('store: %s' % path)
    for key in ('investigations', 'by_state', 'stalled', 'stalled_by_lab_names', 'stalled_for_other_reasons',
                'opened_between', 'would_reopen'):
        out('  %s: %s' % (key, counts[key]))
    if not apply:
        out('dry run: nothing changed (add --apply to reopen them)')
        return dict(counts, applied=False, reopened=0)
    if not found:
        out('nothing to reopen')
        return dict(counts, applied=True, reopened=0)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    with lab._locked():
        if _digest(path) != before:
            out('the store changed while it was read; nothing written. Run again.')
            return dict(counts, applied=False, reopened=0, changed_underneath=True)
        backup = path + '.bak-requeue-' + stamp
        shutil.copy2(path, backup)
        ids = {i['id'] for i in found}
        at = lab.now_iso()
        for investigation in data['investigations']:
            if isinstance(investigation, dict) and investigation.get('id') in ids and matches(investigation):
                reopen(investigation, at)
        inv._save(data)
        lab._append(lab.NOTEBOOK, {'at': at, 'kind': 'investigations_requeued', 'count': len(ids),
                                   'reason': 'stalled by ModuleNotFoundError: ' + REASON, 'backup': os.path.basename(backup),
                                   'truth_status': 'operator_control'})
    out('reopened %d; backup at %s' % (len(found), backup))
    return dict(counts, applied=True, reopened=len(found), backup=backup)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--apply', action='store_true', help='reopen them (a backup is made first)')
    parser.add_argument('--limit', type=int, default=None, help='reopen at most this many, oldest first')
    args = parser.parse_args(argv)
    run(apply=args.apply, limit=args.limit)
    return 0


if __name__ == '__main__':
    sys.exit(main())
