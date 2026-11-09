#!/usr/bin/env python3
"""Render a short judges page from aggregate counts; never load replies or score."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import sys
from zoneinfo import ZoneInfo
sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
MAX_BYTES = 4 * 1024 * 1024
MODES = ('everyday', 'intimate')
SURFACES = ('avatar', 'reelroom', 'voice', 'journal', 'action')
DESCRIPTIONS = {
    'recurrence': ('Returning themes', 'Notices themes he returns to over time.',
                   'Uses his own past words and reviewed topic links.'),
    'grouping': ('Related threads', 'Suggests which unfinished threads may belong together.',
                 'Uses his own past threads; it never merges or deletes them.'),
    'voice': ('Familiar voice', 'Compares a reply with the way he has written before.',
              'Uses his own past replies, keeping different conversation styles separate.'),
    'drift': ('Changes over time', 'Watches for lasting changes across days, rather than one unusual reply.',
              'Uses his own past replies; a comparison is not a verdict that he has changed.'),
    'humor': ('Humor', 'Compares a joke with earlier jokes you responded to warmly.',
              'Uses your clearly linked “haha” reactions and 4–5★ humor ratings.'),
    'taste': ('Taste', 'Compares a written item with things that have landed for you before.',
              'Uses your “landed” marks in Landings; silence is not a negative rating.'),
}


def instant(value):
    if not isinstance(value, str): raise ValueError('date required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None: raise ValueError('offset required')
    return result.astimezone(timezone.utc)


def count(value):
    if type(value) is not int or not 0 <= value <= 10**9: raise ValueError('count required')
    return value


def scope_keys(judge):
    kinds = ('message', 'joke') if judge == 'humor' else ('message', 'joke', 'journal') if judge == 'taste' else (None,)
    return {(m, s, k) for m in MODES for s in SURFACES for k in kinds}


def states(report):
    suff = report.get('sufficiency')
    rows = []
    if suff is not None:
        if not isinstance(suff, dict) or suff.get('schema') != 'judge-sufficiency-counts-v1': raise ValueError('sufficiency schema')
        rows = suff['views']['primary_10s']
        if not isinstance(rows, list) or len(rows) > 200: raise ValueError('scope bound')
    selected = {j: {} for j in DESCRIPTIONS}
    for row in rows:
        judge = row['judge']; key = (row['mode'], row['surface'], row['item_kind'])
        if judge not in selected or key not in scope_keys(judge) or key in selected[judge]: raise ValueError('scope mismatch')
        selected[judge][key] = row
    result = {}
    for judge in DESCRIPTIONS:
        if judge in ('recurrence', 'grouping'):
            result[judge] = 'Waiting for data and review. Estimate: not available yet.'
            continue
        ready = 0; estimates = []; level = 'similarity' if judge in ('humor', 'taste') else 'assessment'
        for row in selected[judge].values():
            levels = {}
            for item in row['estimates']:
                name = item['level']
                if name not in ('assessment', 'similarity', 'empirical_rank') or name in levels: raise ValueError('estimate level')
                levels[name] = item
            if level not in levels: continue
            item = levels[level]; scored = item['observed_scoreable']; days = item['estimated_days_until_scoreable']
            if type(scored) is not bool: raise ValueError('score flag')
            if days is not None: count(days)
            if scored:
                if days != 0 or item['reason'] != 'scoreability_already_observed' or report['scoring'] != 'evaluated_separate_attribution_views':
                    raise ValueError('scoreability mismatch')
                ready += 1
            elif days is not None:
                if days == 0 or item['reason'] != 'conditional_on_same_qualified_arrival_rate' or report['scoring'] != 'evaluated_separate_attribution_views': raise ValueError('estimate mismatch')
                estimates.append(days)
        total = len(scope_keys(judge))
        if ready:
            result[judge] = f'Scoring in {ready} of {total} areas; others are waiting.' if ready < total else f'Scoring in all {total} areas.'
            result[judge] += ' Estimate: already scoring there; no date promised for the rest.' if ready < total else ' Estimate: already scoring.'
        else:
            result[judge] = 'Waiting for data. '
            if estimates:
                first = min(estimates)
                result[judge] += f'Earliest estimate: about {first} more day' + ('s' if first != 1 else '') + ' for one area; other areas may take longer or remain unknown.'
            else: result[judge] += 'Estimate: not enough evidence to give a date yet.'
    return result


def render(report=None, health=None):
    if report is None:
        if health is not None: raise ValueError('health needs snapshot')
        heading = 'Template — no private counts have been loaded.'
        capture = 'Capture: last-24-hour count unknown; sink status unknown.'
        status = states({})
    else:
        if report.get('schema') != 'capture-coverage-counts-v1': raise ValueError('coverage schema')
        if report.get('scoring') not in ('evaluated_separate_attribution_views', 'not_assessed_missing_prepared_projection'):
            raise ValueError('scoring state')
        cutoff = instant(report['cutoff_at']) if 'cutoff_at' in report else None
        heading = ('Snapshot: ' + cutoff.astimezone(ZoneInfo('America/Chicago')).strftime('%b %d, %Y at %H:%M %Z') + '.') if cutoff else 'Snapshot time not recorded in these counts.'
        window = report.get('capture_window'); packets = 'count unknown'
        if window is not None:
            if (cutoff is None or window['hours'] != 24 or type(window['hours']) is not int
                    or instant(window['end_exclusive']) != cutoff
                    or instant(window['start_inclusive']) != cutoff-timedelta(hours=24)
                    or window['complete_stream_attested'] is not False): raise ValueError('capture window')
            packets = str(count(window['retained_packets'])) + ' retained packets'
        sink = 'sink status unknown'
        if health is not None:
            if health.get('schema') != 'judge-sink-health-counts-v1': raise ValueError('health schema')
            enabled = health.get('enabled'); observed = instant(health['observed_at'])
            if type(enabled) not in (bool, type(None)) or cutoff is None or observed > cutoff: raise ValueError('health observation')
            if enabled is not None:
                when = observed.astimezone(ZoneInfo('America/Chicago')).strftime('%b %d %H:%M %Z')
                sink = 'sink last observed ' + ('on' if enabled else 'off') + ' (' + when + ')'
        capture = 'Capture: ' + packets + ' in the last 24 hours; ' + sink + '.'
        status = states(report)
    lines = ['# A quiet look at the judges', '', heading, '', capture, '',
             'For every judge: no verdicts on his feelings, and no changes to his replies, memory or choices.', '',
             '“Scoring” means an offline comparison in this snapshot. Areas keep conversation styles and reply types separate.', '']
    for judge, (title, watches, learns) in DESCRIPTIONS.items():
        lines.extend([f'**{title}** — {watches} {learns}', status[judge], ''])
    lines.extend(['Estimates assume the same pace of usable evidence continues. They are not deadlines. Ordinary use can fill the gaps; there is nothing you need to send for a test.', ''])
    return '\n'.join(lines)


def private_root(value):
    root = Path(value).expanduser().absolute()
    if (root != root.resolve() or root in (Path('/'), Path.home(), REPO) or root in REPO.parents or REPO in root.parents
            or any(p in ('.vintos', '.openclaw') for p in root.parts)
            or any((p/'.git').exists() for p in (root, *root.parents))): raise ValueError('private scratch required')
    mode = root.stat()
    if not stat.S_ISDIR(mode.st_mode) or mode.st_uid != os.getuid() or mode.st_mode & 0o077: raise ValueError('private root')
    return root


def read(root, value):
    path = Path(value).expanduser().absolute()
    if path != path.resolve() or not path.is_relative_to(root): raise ValueError('private file')
    for parent in (path.parent, *path.parent.parents):
        if parent == root.parent: break
        mode = parent.stat()
        if mode.st_uid != os.getuid() or mode.st_mode & 0o077: raise ValueError('private parent')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        mode = os.fstat(stream.fileno())
        if not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.getuid() or mode.st_mode & 0o077: raise ValueError('private regular file')
        raw = stream.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES: raise ValueError('size bound')
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: raise ValueError('duplicate key')
            result[key] = value
        return result
    def invalid(value): raise ValueError('invalid constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


class Parser(argparse.ArgumentParser):
    def error(self, message): raise ValueError('arguments refused')


def main(argv=None):
    p = Parser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--counts'); group.add_argument('--template', action='store_true')
    p.add_argument('--scratch'); p.add_argument('--sink-health')
    a = p.parse_args(argv)
    if a.template:
        if a.scratch or a.sink_health: raise ValueError('template takes no inputs')
        print(render(), end=''); return
    if not a.scratch: raise ValueError('private scratch required')
    root = private_root(a.scratch)
    def guard(event, args):
        if event.startswith(('socket.', 'subprocess.', 'os.spawn', 'os.exec', 'os.system')): raise PermissionError('external operation')
        if event == 'open' and isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND): raise PermissionError('write')
        if event in ('os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.chmod', 'os.link', 'os.symlink', 'os.fork', 'os.forkpty'): raise PermissionError('mutation')
    sys.addaudithook(guard)
    print(render(read(root, a.counts), read(root, a.sink_health) if a.sink_health else None), end='')


if __name__ == '__main__':
    try: main()
    except Exception:
        print('judges_page_refused', file=sys.stderr); sys.exit(1)
