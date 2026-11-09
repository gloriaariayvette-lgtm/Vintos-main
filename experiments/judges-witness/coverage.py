#!/usr/bin/env python3
"""Private, offline coverage diagnosis; never changes historical attribution."""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay as R
from witness_attribution import attribution, _clock, _row_clock, _name
from witness_receipts import digest, instant, joined_identity, final_response

WINDOWS = (10, 30, 60, 120)
MAX_BYTES = 128 * 1024 * 1024
MAX_CALLS = 250000
MAX_ROWS = 10000
BAD_STAGES = ('failed', 'attempt', 'reserved', 'released', 'refused', 'claimed')



def source_coverage(rows, cutoff, tz):
    """Count producer copies and explicit same-turn surface evidence, without repair."""
    admitted, groups, counts = [], defaultdict(list), Counter()
    excluded = 0
    for row in rows:
        if row.get('role') != 'assistant': continue
        try: at = _row_clock(row, tz)
        except ValueError: at = None
        if at is not None and at >= cutoff:
            excluded += 1
            continue
        ident, identity_state = joined_identity(row)
        admitted.append((row, ident, identity_state, at))
        if ident is not None and at is not None:
            groups[ident].append(row)
    for row, ident, identity_state, at in admitted:
        adapter = row.get('_witness_adapter_kind')
        adapter = adapter if adapter in ('canonical', 'merged', 'ledger', 'capture') else 'unknown'
        origin = row.get('source')
        origin = origin if origin in ('canonical', 'ledger') else 'absent' if origin is None else 'other'
        surface = row.get('surface')
        state = ('absent' if surface is None else 'empty' if surface == '' else
                 'declared' if _name(surface) else 'invalid')
        evidence = 'not_needed'
        if state != 'declared':
            if at is None: evidence = 'clock_unavailable'
            elif ident is None: evidence = identity_state
            elif not isinstance(row.get('content'), str) or not row['content']:
                evidence = 'stored_text_unavailable'
            else:
                peers = groups[ident]
                # Stored copies only: no trimming, device-mark stripping or
                # similarity guesses. A changed version cannot attest this copy.
                if any(peer.get('content') != row['content'] for peer in peers):
                    evidence = 'conflicting_stored_versions'
                else:
                    surfaces = {_name(peer.get('surface')) for peer in peers}
                    surfaces.discard(None)
                    if len(surfaces) > 1: evidence = 'conflicting_declared_surfaces'
                    elif surfaces: evidence = 'one_declared_surface_same_id_and_text'
                    else: evidence = 'no_declared_surface_same_id_and_text'
        counts[(adapter, origin, state, evidence)] += 1
    return dict(assistant_copies=len(admitted), excluded_at_or_after_cutoff=excluded,
                groups=[dict(adapter=a, projection_source=o, surface_state=s,
                             same_turn_evidence=e, copies=n)
                        for (a,o,s,e),n in sorted(counts.items())],
                meaning='source copies, not independent turns; explicit surface evidence is diagnostic only; no inferred surface or model attribution')


def diagnose(rows, ledger, config, cutoff):
    if not isinstance(rows, list) or len(rows) > MAX_ROWS or not isinstance(ledger, list) or len(ledger) > MAX_CALLS:
        raise ValueError('coverage input exceeds bounds')
    # Run the original rule unchanged, including exact IDs, cutoff and reuse holds.
    baseline, details = attribution(rows, ledger, config, cutoff)
    cutoff = instant(cutoff)
    tz = ZoneInfo(config['naive_timezone']) if config.get('naive_timezone') else None
    calls, all_callers, timed, unordered = {}, defaultdict(list), defaultdict(list), set()
    after_cutoff = 0
    for record in ledger:
        key = digest(json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False))
        if key in calls: continue
        calls[key] = record
        caller = _name(record.get('organ'))
        try: at = _clock(record.get('at'), tz)
        except ValueError: at = None
        if at is not None and at >= cutoff:
            after_cutoff += 1
            continue
        all_callers[caller].append((at, record))
        if record.get('class') == 'foreground' and caller:
            if at is None: unordered.add(caller)
            else: timed[caller].append((at, key, record))
    for items in timed.values(): items.sort(key=lambda v: (v[0], v[1]))
    clocks = {caller: [v[0] for v in items] for caller, items in timed.items()}

    def iso(epoch):
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch is not None else None

    callers = []
    for caller, items in sorted(all_callers.items(), key=lambda v: v[0] or ''):
        ats = sorted(at for at, _ in items if at is not None)
        callers.append(dict(caller=caller, records=len(items), clock_unavailable=sum(at is None for at, _ in items),
                            foreground=sum(r.get('class') == 'foreground' for _, r in items),
                            nonempty_model_and_provider=sum(bool(_name(r.get('model')) and _name(r.get('provider'))) for _, r in items),
                            stages=dict(Counter(_name(r.get('stage')) or 'unknown' for _, r in items)),
                            first_retained_at=iso(ats[0]) if ats else None,
                            last_retained_at=iso(ats[-1]) if ats else None,
                            largest_observed_gap_seconds=max((b-a for a,b in zip(ats, ats[1:])), default=None)))
    surfaces = Counter()
    positions = Counter()
    eligible = []
    assistant_rows = [r for r in rows if r.get('role') == 'assistant']
    for row, detail in zip(assistant_rows, details):
        if detail['outside_cutoff']: continue
        surface = row.get('surface')
        if surface is None: surface = config.get('source_surfaces', {}).get(row.get('_witness_adapter_kind'))
        mapped = config['surface_callers'].get(surface, []) if isinstance(surface, str) else []
        surface_state = 'absent' if surface is None else 'valid' if _name(surface) else 'invalid_or_empty'
        surfaces[(_name(row.get('_witness_adapter_kind')), _name(surface), surface_state, bool(mapped), detail['join_state'])] += 1
        if not mapped: continue
        try: at = _row_clock(row, tz)
        except ValueError: continue
        # Keep all clocked replies in contention, even those already matched or
        # held by exact-ID rules. They cannot be ignored to manufacture uniqueness.
        eligible.append((row, detail, mapped, at))
        if detail['join_state'] != 'no_matching_call': continue
        series = [clocks[c] for c in mapped if clocks.get(c)]
        if any(c in unordered for c in mapped): position = 'unordered_caller'
        elif not series: position = 'no_retained_foreground_calls'
        elif at < min(v[0] for v in series): position = 'before_first_retained_call'
        elif at > max(v[-1] for v in series): position = 'after_last_retained_call'
        else: position = 'within_retained_span'
        positions[position] += 1
    sensitivity = {}
    for window in WINDOWS:
        outcomes, uses = [], defaultdict(list)
        for row, detail, mapped, at in eligible:
            candidates = {}
            for caller in mapped:
                values = timed[caller]; times = clocks.get(caller, [])
                for value in values[bisect_left(times, at-window):bisect_right(times, at+window)]:
                    candidates[value[1]] = value
            state, selected = 'none_in_window', None
            if any(c in unordered for c in mapped): state = 'unordered_caller'
            elif len(candidates) > 1: state = 'multiple_calls_in_window'
            elif candidates:
                selected = next(iter(candidates))
                record = candidates[selected][2]
                state = 'sole_call_in_window'
                if not _name(record.get('model')) or not _name(record.get('provider')) or record.get('stage') in BAD_STAGES:
                    state = 'sole_call_metadata_unavailable'
                elif 'model_identity_evidence' in record and record['model_identity_evidence'] not in ('response_metadata','runtime_receipt'):
                    state = 'sole_call_identity_unobserved'
            index = len(outcomes)
            outcomes.append([detail['join_state'] == 'no_matching_call', state])
            identity = (joined_identity(row)[0], digest(final_response(row)) if isinstance(final_response(row), str) else None)
            # Every nearby call is contested, including by ambiguous or exact-ID
            # rows; diagnostic opportunities must not reuse it behind their backs.
            for key in candidates: uses[key].append((index, identity))
            if detail.get('ledger_sha256') in calls and detail['ledger_sha256'] not in candidates:
                uses[detail['ledger_sha256']].append((index, identity))
        for contenders in uses.values():
            identities = {ident for _, ident in contenders}
            if len(contenders)>1 and (len(identities)>1 or any(None in ident for ident in identities)):
                for index, _ in contenders:
                    if outcomes[index][1] == 'sole_call_in_window': outcomes[index][1] = 'call_contested_by_other_reply'
        counts = Counter(state for selected, state in outcomes if selected)
        sensitivity[str(window)] = dict(counts)
    public = dict(schema='judges-attribution-coverage-v1', baseline=baseline,
                  unmatched_span_positions=dict(positions), window_sensitivity=sensitivity,
                  unique_callers=len(all_callers), ledger_records_after_cutoff=after_cutoff,
                  effect='diagnosis_only_no_attribution_or_training_changes',
                  meaning='wider windows are opportunities for inspection, not recovered attribution; silence is not proof of a logging outage')
    public['source_coverage'] = source_coverage(rows, cutoff, tz)
    private = dict(callers=callers, surfaces=[dict(source_kind=k, surface=s, surface_state=v, mapped=m, join_state=j, copies=n)
                   for (k,s,v,m,j),n in sorted(surfaces.items(), key=lambda v: str(v[0]))],
                   date_meaning='first and last supplied retained records, not logging start or complete coverage')
    return public, private


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('scratch', 'input', 'output', 'cutoff'): parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    root = R.scratch_root(args.scratch)
    source, output = R.inside(root, args.input), R.inside(root, args.output)
    if output.exists() or output in source.parents: raise ValueError('output must be new')
    R.install_guard(root, output)
    code = R.scoring_hashes()
    code['experiments/judges-witness/coverage.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with source.open('rb') as f: raw = f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: raise ValueError('snapshot exceeds byte bound')
    bundle = R.decode_snapshot(raw)
    if bundle.get('input_kind') not in ('synthetic', 'retained_snapshot'): raise ValueError('explicit input_kind required')
    config = dict(bundle['historical_attribution'])
    ledger = config.pop('compute_ledger')
    rows = []
    for source_group in bundle['sources']:
        records = source_group['rows']
        if not isinstance(records, list) or len(records)>MAX_ROWS: raise ValueError('source exceeds row bound')
        rows.extend(R.adapt(records, source_group['kind']))
        if len(rows)>MAX_ROWS: raise ValueError('adapted rows exceed bound')
    public, private = diagnose(rows, ledger, config, args.cutoff)
    public['input_kind'] = bundle['input_kind']
    checked = R.scoring_hashes()
    checked['experiments/judges-witness/coverage.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if checked != code: raise ValueError('diagnostic source changed during run')
    os.umask(0o077)
    output.mkdir(mode=0o700)
    outputs = {}
    for name, value in (('aggregate.json', public), ('private-coverage.json', private)):
        payload = (json.dumps(value, indent=2, allow_nan=False)+'\n').encode()
        with (output/name).open('xb') as f: f.write(payload)
        outputs[name] = dict(sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload))
    manifest = R.run_manifest(raw, code, dict(cutoff=instant(args.cutoff), windows=list(WINDOWS)), outputs)
    with (output/'private-run.json').open('x') as f: json.dump(manifest, f, indent=2, allow_nan=False)
    print(json.dumps(dict(status='private_coverage_written', assistant_copies=public['baseline']['assistant_copies'])))


if __name__ == '__main__':
    try: main()
    except (ValueError, TypeError, KeyError, OSError, OverflowError):
        raise SystemExit('Coverage diagnostic failed; input details withheld') from None
