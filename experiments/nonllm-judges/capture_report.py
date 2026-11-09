#!/usr/bin/env python3
"""Read explicit private capture packets; emit dates, counts and coverage only."""
import argparse
from collections import Counter, defaultdict
import copy
from datetime import datetime, timedelta
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
from zoneinfo import ZoneInfo
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

R = load('capture_numerical_runner', HERE / 'run_private.py')
X = load('capture_witness_replay', HERE.parent / 'judges-witness/replay.py')
W = sys.modules['witness_receipts']
JUDGES = ('recurrence', 'grouping', 'voice', 'drift', 'humor', 'taste')
MAX_FILES = 10000
MAX_BYTES = 64 * 1024 * 1024


def sufficiency(bundle, landings, cutoff, zone, packets, private=None):
    """Count floors and conditional forecasts; never promote a count to evidence."""
    zone = bundle["timezone"] if bundle is not None else zone
    day = datetime.fromtimestamp(cutoff, ZoneInfo(zone)).date()
    start = (day - timedelta(days=7)).isoformat(); end = day.isoformat()
    recent = lambda d: start <= d < end
    # Seven complete local dates include empty dates; a partial current day is excluded.
    raw = Counter()
    for row in packets.values():
        d = datetime.fromtimestamp(W.instant(row['witness_receipt']['finalized_at']), ZoneInfo(zone)).date().isoformat()
        if recent(d) and row.get('surface') in R.P.SURFACES: raw[row['surface']] += 1
    views = {}
    data = R.adapt(bundle, cutoff) if bundle is not None else None
    for view in ('primary_10s', 'window30'):
        accepted = []; refs = set(); supplied = {}; items = {}; attempts = {}; positives = {}
        if data is not None:
            prepared, candidates, _, supplied, events, nodes, features, encoder, item_rows, _ = data
            ids = {r['id'] for r in prepared if view == 'window30' or r['primary']}
            if encoder is not None:
                accepted, _ = R.V.prepare([e for e in events if e['node_id'] in ids], nodes,
                    [f for f in features if f['node_id'] in ids], encoder, cutoff, zone)
            refs = set(supplied.get('reference_ids', [r['id'] for r in prepared if r['day'] in candidates]))
            items = {i['node_id']: i['kind'] for i in item_rows}
            for facet in ('humor', 'taste'):
                anchors = supplied.get('anchors', []) if facet == 'humor' else (landings or {}).get('anchors', [])
                positives[facet], _, _, _ = R.F.outcome_anchors(anchors, {r['id']: r for r in accepted}, items, facet, cutoff, zone)
                attempts[facet] = set(supplied.get(facet + '_attempt_ids', []))
        detail = private['views'][view] if private else None
        cells = []
        for mode in sorted(R.P.MODES):
            for surface in sorted(R.P.SURFACES):
                group = [r for r in accepted if (r['mode'], r['surface']) == (mode, surface)]
                for judge in JUDGES:
                    kinds = sorted({'message','joke'} if judge == 'humor' else R.F.TEXT_KINDS) if judge in ('humor','taste') else [None]
                    for kind in kinds:
                        target = [r for r in group if kind is None or items.get(r['id']) == kind]
                        if kind is not None: target = [r for r in target if r['id'] in attempts.get(judge, set())]
                        reference = [r for r in group if r['id'] in refs and r['day'] < end]
                        anchors_count = 0
                        if kind is not None:
                            # Both the act day and witnessed outcome day must precede a future target day.
                            reference = [r for r in group if items.get(r['id']) == kind and r['day'] < end
                                and any(a['day'] < end for a in positives[judge].get(r['id'], []))]
                            anchors_count = sum(sum(a['day'] < end for a in positives[judge][r['id']]) for r in reference)
                        n_days = len({r['day'] for r in reference})
                        recent_refs = [r for r in reference if recent(r['day'])]
                        # Positive arrival requires the outcome to have arrived in the rate window as well.
                        if kind is not None:
                            recent_refs = [r for r in recent_refs if any(recent(a['day']) for a in positives[judge][r['id']])]
                        ref_rate = len({r['day'] for r in recent_refs}) / 7
                        target_rate = len({r['day'] for r in target if recent(r['day'])}) / 7
                        base = dict(judge=judge, mode=mode, surface=surface, item_kind=kind,
                            available=dict(admitted_acts=len(group), reference_acts=len(reference), reference_days=n_days,
                                           positive_anchors=anchors_count, target_attempts=len(target)),
                            recent=dict(raw_surface_capture_replies_per_day=raw[surface]/7,
                                qualified_acts_per_day=sum(recent(r['day']) for r in group)/7,
                                reference_days_per_day=ref_rate, target_days_per_day=target_rate),
                            requirements={}, estimates=[], blockers=[])
                        if judge in ('recurrence','grouping'):
                            base['requirements'] = dict(reference_days=0, positive_anchors=0,
                                additional='reviewed_topic_assignments' if judge == 'recurrence' else 'explicit_cosine_threshold_and_frozen_features')
                            base['available'].update(reference_acts=None, reference_days=None, positive_anchors=None)
                            base['blockers'] = ['no_retained_adapter']
                            if bundle is None: base['available'] = {k:None for k in base['available']}
                            cells.append(base); continue
                        required = 2 if kind is not None else 4
                        base['requirements'] = dict(reference_days=required, minimum_reference_acts=required,
                            minimum_positive_anchors=required if kind is not None else 0,
                            target_after_reference_day=True, nondegenerate_features=True)
                        if judge == 'drift':
                            base['requirements']['sustained_shift_consecutive_days'] = 4
                            base['requirements']['shift_outcome_forecastable'] = False
                        horizons = [('similarity',2),('empirical_rank',4)] if kind is not None else [('assessment',4)]
                        if bundle is None: base['blockers'].append('missing_prepared_projection')
                        elif not group: base['blockers'].append('no_admitted_features_in_scope')
                        if not reference: base['blockers'].append('no_qualified_references')
                        for horizon, need in horizons:
                            ready = False
                            if detail is not None:
                                rows = detail['facet_receipts'][judge] if kind else detail['voice_drift_receipts'][judge]
                                ready = any(r['scope'] == ([mode,surface,kind] if kind else [mode,surface]) and
                                    (kind is None or r['status'] in (('empirical_rank',) if horizon == 'empirical_rank' else ('similarity_only','empirical_rank')))
                                    for r in rows)
                            missing = max(0,need-n_days); estimate = None; reason = 'zero_recent_qualifying_rate'
                            if ready: estimate=0; reason='scoreability_already_observed'
                            elif bundle is None: reason='missing_prepared_projection'
                            elif n_days >= need and (R.V.calibrate(reference,need) is None if need>=4
                                    else not R.V.day_balanced(reference)):
                                reason='degenerate_reference'
                            elif target_rate > 0 and (missing == 0 or ref_rate > 0):
                                # A target needs its own later local day. These are conditional arrival estimates.
                                estimate = math.ceil(missing/ref_rate) + math.ceil(1/target_rate) if missing else math.ceil(1/target_rate)
                                reason='conditional_on_same_qualified_arrival_rate'
                            base['estimates'].append(dict(level=horizon, required_reference_days=need,
                                minimum_reference_acts=need, minimum_positive_anchors=need if kind else 0,
                                missing_reference_days=missing, count_floor_met=missing==0,
                                observed_scoreable=ready, estimated_days_until_scoreable=estimate, reason=reason))
                        if bundle is None:
                            base['available'] = {k:None for k in base['available']}
                            for estimate in base['estimates']:
                                estimate['missing_reference_days'] = None; estimate['count_floor_met'] = None
                        cells.append(base)
        views[view] = cells
    return dict(schema='judge-sufficiency-counts-v1', timezone=zone, rate_window=dict(start_date=start,
        end_date_exclusive=end, calendar_days=7, partial_current_day_excluded=True), views=views,
        estimate_kind='conditional_not_a_promise',
        assumptions=['same_scope_qualified_capture_rate_continues','future_reference_designation_and_exact_positive_joins_continue',
                     'future_features_are_nondegenerate','next_target_on_later_day_not_in_reference'],
        sustained_shift_eta=None, unknown_scopes_not_promoted=True)


def report(packets, cutoff, zone='America/Chicago', bundle=None, landings=None):
    cutoff = W.instant(cutoff); tz = ZoneInfo(zone)
    if not isinstance(packets, list) or len(packets) > MAX_FILES: raise ValueError('packet bound')
    nodes = X.snapshot_nodes([('capture', packets)], [])
    groups = defaultdict(list); days = {}; packet_counts = Counter(); outside = 0
    for raw in packets:
        # Dates describe the recorded finalization, never file mtime or today's date.
        receipt = W.row_receipt(raw)
        at = W.instant(raw.get('witness_receipt', {}).get('finalized_at'))
        if at >= cutoff:
            outside += 1; continue
        day = datetime.fromtimestamp(at, tz).date().isoformat()
        packet_counts[day] += 1
        key = raw.get('turn_id')
        if not isinstance(key, str) or not key: raise ValueError('missing packet identity')
        if key in days and days[key] != day: raise ValueError('conflicting finalization day')
        days[key] = day; groups[key].append(raw)
    daily = {day: dict(date=day, packets=n, replies=0, provider_reported_served_model=0,
                      full_lineage=0, original_act_bindings=0, admission_reasons=Counter(),
                      encoder_freeze_sources={s: 0 for s in R.Q.SOURCES},
                      judges={j: dict(scored_replies=0) for j in JUDGES})
             for day, n in sorted(packet_counts.items())}
    eligible = {}; exact = {}
    for key, copies in groups.items():
        cell = daily[days[key]]; cell['replies'] += 1
        facts = [X.evidence_coverage(row, nodes) for row in copies]
        # Identical packets are harmless; conflicting copies never select a winner.
        if len({R.P.canonical(row) for row in copies}) != 1:
            cell['admission_reasons']['conflicting_packet_copies'] += 1
            continue
        raw = copies[0]; receipt = W.row_receipt(raw)
        selected = next((a for a in receipt.get('generation', {}).get('attempts', []) if a.get('outcome') == 'selected'), {})
        cell['provider_reported_served_model'] += int(all(f['served_identity'] == 'observed' for f in facts)
                                                    and selected.get('identity_evidence') == 'response_metadata')
        clean = all(f['context_lineage'] == f['final_reply_lineage'] == 'clean' for f in facts)
        cell['full_lineage'] += int(clean)
        status = W.admission(raw, nodes, cutoff)
        if status == 'eligible' and not clean: status = 'final_lineage_not_clean'
        cell['admission_reasons'][status] += 1
        if status == 'eligible':
            eligible[key] = raw; cell['original_act_bindings'] += 1
        if receipt.get('status') == 'recorded': exact[key] = receipt['response_sha256']
    scoring = 'not_assessed_missing_prepared_projection'
    qualified = {}; supplied = None; private = None
    if bundle is not None:
        # Supplemental evidence may supply caches and outcomes, never repair a denied packet.
        supplied = copy.deepcopy(bundle)
        for row in supplied['rows']:
            if row.get('role') != 'assistant': continue
            key = row.get('turn_id')
            if key in exact and (W.digest(row.get('content', '')) != exact[key]
                    or R.C.instant(row['timestamp']) != W.row_receipt(groups[key][0])['finalized_at']
                    or row.get('surface') != groups[key][0].get('surface')):
                raise ValueError('prepared reply differs from capture')
        meta = supplied.get('numerical_evidence', {})
        meta['bindings'] = [b for b in meta.get('bindings', []) if b.get('node_id') in eligible
                            and b.get('content_sha256') == exact[b['node_id']]]
        supplied['numerical_evidence'] = meta
        private, _ = R.evaluate(supplied, landings, cutoff)
        prepared, _, _, _, _, _, _, encoder, _, _ = R.adapt(supplied, cutoff)
        source = private['encoder_freeze_source']
        if encoder is not None:
            for row in prepared:
                if row['id'] in eligible and row['sha'] == exact[row['id']] and encoder['frozen_at'] < row['at']:
                    qualified[row['id']] = source
        for view in ('primary_10s', 'window30'):
            detail = private['views'][view]
            scores = {j: set() for j in JUDGES}
            voices = detail['voice_drift_receipts']['voice']
            scores['voice'] = {r['turn_id'] for r in voices}
            drift_days = {(r['day'], tuple(r['scope'])) for r in detail['voice_drift_receipts']['drift']}
            scores['drift'] = {r['turn_id'] for r in voices if (r['day'], tuple(r['scope'])) in drift_days}
            for facet in ('humor', 'taste'):
                scores[facet] = {r['attempt_id'] for r in detail['facet_receipts'][facet]
                                 if r['status'] in ('similarity_only', 'empirical_rank')}
            for cell in daily.values():
                cell.setdefault('attribution_views', {})[view] = {
                    j: dict(scored_replies=sum(key in eligible and days[key] == cell['date'] for key in ids))
                    for j, ids in scores.items()}
        scoring = 'evaluated_separate_attribution_views'
        # Primary is the headline; overlapping sensitivity counts are never added.
        for cell in daily.values(): cell['judges'] = cell['attribution_views']['primary_10s']
    elif landings is not None:
        raise ValueError('Landings requires prepared projection')
    for key, day in days.items(): daily[day]['encoder_freeze_sources'][qualified.get(key, 'unknown')] += 1
    for cell in daily.values():
        n = cell['replies']
        cell['admission_reasons'] = dict(sorted(cell['admission_reasons'].items()))
        for field in ('provider_reported_served_model', 'full_lineage', 'original_act_bindings'):
            cell[field + '_share'] = cell[field] / n if n else None
    return dict(schema='capture-coverage-counts-v1', timezone=zone, days=list(daily.values()),
                packets_outside_cutoff=outside, scoring=scoring,
                recurrence_and_grouping='not_evaluated_no_retained_adapter',
                drift_count_unit='replies_in_assessed_daily_windows_not_shift_verdicts',
                source_claims_independently_verified=False, model_calls=0,
                sufficiency=sufficiency(supplied, landings, cutoff, zone,
                    {k:v[0] for k,v in groups.items()}, private))


def private_path(root, value, directory=False):
    path = Path(value).expanduser().absolute()
    if path != path.resolve() or not path.is_relative_to(root): raise ValueError('private path required')
    for parent in (path.parent, *path.parent.parents):
        if parent == root.parent: break
        if parent.stat().st_mode & 0o077: raise ValueError('private directory required')
    mode = path.stat()
    if mode.st_uid != os.getuid() or mode.st_mode & 0o077: raise ValueError('private ownership required')
    if not (stat.S_ISDIR(mode.st_mode) if directory else stat.S_ISREG(mode.st_mode)):
        raise ValueError('wrong private input type')
    return path


def read(path, limit=MAX_BYTES):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('private regular file required')
        raw = f.read(limit + 1)
    if len(raw) > limit: raise ValueError('input size bound')
    return R.C.decode_snapshot(raw), len(raw)


def main(argv=None):
    p = R.Parser(description=__doc__)
    for key in ('scratch', 'packets', 'cutoff'): p.add_argument('--' + key, required=True)
    p.add_argument('--timezone', default='America/Chicago')
    p.add_argument('--prepared-input'); p.add_argument('--landings')
    a = p.parse_args(argv)
    root = Path(a.scratch).expanduser().absolute()
    if (root != root.resolve() or root in (Path('/'), Path.home(), REPO) or root in REPO.parents or REPO in root.parents
            or any(part in ('.vintos', '.openclaw') for part in root.parts)
            or any((parent / '.git').exists() for parent in (root, *root.parents))):
        raise ValueError('isolated private root required')
    private_path(root, root, True)
    packet_dir = private_path(root, a.packets, True)
    optional = {k: private_path(root, v) for k, v in
                (('bundle', a.prepared_input), ('landings', a.landings)) if v}
    # Imports are complete. This process performs no write, network or subprocess operation.
    def guard(event, args):
        if event.startswith(('socket.', 'subprocess.', 'os.spawn', 'os.exec', 'os.system')):
            raise PermissionError('external operation forbidden')
        if event == 'open':
            flags = args[2] if len(args) > 2 else 0
            if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                raise PermissionError('writes forbidden')
        if event in ('os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.chmod', 'os.link', 'os.symlink', 'os.fork', 'os.forkpty'):
            raise PermissionError('mutation forbidden')
    sys.addaudithook(guard)
    files = list(packet_dir.iterdir())
    if len(files) > MAX_FILES: raise ValueError('file count bound')
    packets = []; total = 0; ignored = 0
    for path in sorted(files):
        if not re.fullmatch(r'capture-[0-9a-f]{32}\.json', path.name):
            ignored += 1; continue
        value, size = read(private_path(root, path), 1024 * 1024)
        total += size
        if total > MAX_BYTES: raise ValueError('packet bytes bound')
        packets.append(value)
    extra = {k: read(v)[0] for k, v in optional.items()}
    result = report(packets, a.cutoff, a.timezone, **extra)
    result['non_capture_entries_ignored'] = ignored
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps({'error': 'capture_report_refused'}), file=sys.stderr); sys.exit(1)
