#!/usr/bin/env python3
"""Offline intent evidence assessor. No runtime imports, inference or feedback writes."""
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location('intent_shadow_io', Path(__file__).with_name('landings_project.py'))
L = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(L)
G = L.G
AXES = ('field', 'gloria', 'self')
VERDICTS = ('YES', 'PARTIAL', 'NO', 'HELD', 'NOT_DECLARED')
OLD = VERDICTS + ('MISSING', 'INVALID')
FAMILIES = ('mechanical', 'semantic', 'internal_state', 'unspecified')
REASONS = ('not_declared', 'legacy_shape', 'invalid_declaration', 'not_delivered', 'missing_identity',
           'ambiguous_identity', 'unknown_time', 'time_order', 'after_cutoff',
           'missing_delivery', 'delivery_mismatch', 'device_event_only', 'not_her_words',
           'no_reply', 'missing_response_join', 'ambiguous_response', 'response_mismatch',
           'invalid_window', 'missing_contract', 'contract_mismatch', 'contract_not_prior',
           'unsupported_criterion', 'missing_receipt', 'conflicting_receipt',
           'receipt_time_order', 'incomplete_observation', 'partial_not_defined', 'observed')
OPERATIONS = ('artifact_delivery', 'action_completion')


def digest(value):
    return hashlib.sha256(L.canonical(value).encode('utf-8')).hexdigest()


def text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 100000


def indexed(rows, key, limit=4096):
    if not isinstance(rows, list) or len(rows) > limit: raise ValueError('bound')
    out = {}; duplicates = 0
    for row in rows:
        if not isinstance(row, dict) or not L.identifier(row.get(key)): raise ValueError('identity')
        identity = row[key]
        if identity in out:
            if L.canonical(out[identity]) != L.canonical(row): raise ValueError('conflicting identity')
            duplicates += 1
        out[identity] = row
    return out, duplicates


def bundle(evidence, contracts):
    L.canonical(evidence); L.canonical(contracts)  # Reject nonfinite values even in ignored fields.
    if not isinstance(evidence, dict) or evidence.get('schema') != 'intent-shadow-evidence-v1': raise ValueError('evidence schema')
    if not isinstance(contracts, dict) or contracts.get('schema') != 'intent-shadow-contracts-v1': raise ValueError('contract schema')
    turns, td = indexed(evidence.get('turns'), 'id')
    receipts, rd = indexed(evidence.get('receipts'), 'id')
    items, cd = indexed(contracts.get('items'), 'id')
    by_axis = {}
    for item in items.values():
        if not L.identifier(item.get('intent_id')) or item.get('axis') not in AXES: raise ValueError('contract binding')
        key = (item['intent_id'], item['axis'])
        if key in by_axis: raise ValueError('ambiguous contract')
        if item.get('family') not in FAMILIES: raise ValueError('family')
        by_axis[key] = item
    return turns, receipts, by_axis, td + rd + cd


def original(row, axis):
    value = row.get('realized')
    value = value.get(axis) if isinstance(value, dict) else value if axis == 'field' else None
    return 'MISSING' if value is None else value if isinstance(value, str) and value in VERDICTS else 'INVALID'


def declaration(row, axis):
    target = row.get('target')
    if not isinstance(target, dict): return None, 'invalid_declaration'
    if axis == 'field':
        if target.get('criterion_abstained'): return None, 'not_declared'
        legacy_verdict = row.get('realized')
        if (row.get('status') is None and not row.get('intent_id') and not row.get('turn_id')
                and target.get('goal') in (None, '') and target.get('success_criterion') in (None, '')
                and text(target.get('field_state')) and text(target.get('enactment'))
                and (legacy_verdict is None or isinstance(legacy_verdict, str) and legacy_verdict in VERDICTS)):
            return None, 'legacy_shape'
        if not text(target.get('goal')) or not text(target.get('success_criterion')): return None, 'invalid_declaration'
        return target, ''
    value = target.get(axis)
    if value is None or value == {}: return None, 'not_declared'
    if not isinstance(value, dict) or not text(value.get('difference_intended')) or not text(value.get('enactment')):
        return None, 'invalid_declaration'
    return value, ''


def grade(row, axis, turns, receipts, contracts, ambiguous, cutoff, zone=None):
    def held(reason): return 'HELD', reason
    target, why = declaration(row, axis)
    if why: return ('NOT_DECLARED' if why == 'not_declared' else 'HELD'), why
    if row.get('status') != 'delivered': return held('not_delivered')
    iid, tid = row.get('intent_id'), row.get('turn_id')
    if not L.identifier(iid) or not L.identifier(tid): return held('missing_identity')
    if iid in ambiguous: return held('ambiguous_identity')
    if row['target'].get('intent_id') != iid: return held('missing_identity')
    try:
        selected = L.instant(row.get('timestamp'), zone)
        delivered = L.instant(row.get('delivered_at'), zone)
    except (ValueError, TypeError, OverflowError): return held('unknown_time')
    if not selected <= delivered: return held('time_order')
    if delivered >= cutoff: return held('after_cutoff')
    turn = turns.get(tid)
    if turn is None: return held('missing_delivery')
    if (turn.get('role') != 'assistant' or turn.get('kind') != 'reply' or turn.get('intent_id') != iid
            or turn.get('source') != 'delivery_receipt' or not L.hashed(turn.get('source_sha256'))
            or not text(row.get('reply')) or turn.get('text') != row['reply']): return held('delivery_mismatch')
    try:
        if L.instant(turn.get('at')) != delivered: return held('delivery_mismatch')
    except (ValueError, TypeError, OverflowError): return held('unknown_time')
    window, kind = target.get('observation_window'), target.get('evidence_type')
    if ((window, kind) not in (('this_reply', 'my_move'), ('her_next_reply', 'her_response'))
            or axis == 'gloria' and kind != 'her_response' or axis == 'self' and kind != 'my_move'):
        return held('invalid_window')
    if kind == 'her_response':
        if row.get('response_source') in ('gcs', 'reelroom_event'): return held('device_event_only')
        if not text(row.get('response_text')): return held('no_reply')
        # Explicit parentage only. Physical adjacency or text labels never establish whose turn it was.
        responses = [t for t in turns.values() if t.get('reply_to') == tid]
        if not responses: return held('missing_response_join')
        if len(responses) != 1: return held('ambiguous_response')
        response = responses[0]
        if response.get('kind') == 'device_event': return held('device_event_only')
        if response.get('role') != 'user' or response.get('kind') != 'reply': return held('not_her_words')
        if (response.get('source') != 'canonical_user_turn' or not L.hashed(response.get('source_sha256'))
                or response.get('text') != row['response_text']): return held('response_mismatch')
        try: at = L.instant(response.get('at'))
        except (ValueError, TypeError, OverflowError): return held('unknown_time')
        if at <= delivered: return held('time_order')
        if at >= cutoff: return held('after_cutoff')
    contract = contracts.get((iid, axis))
    if contract is None: return held('missing_contract')
    if (contract.get('target_sha256') != digest(row['target']) or type(contract.get('version')) is not int or contract['version'] != 1
            or contract.get('observation_window') != window or contract.get('evidence_type') != kind
            or contract.get('review_kind') != 'independent_human'
            or not L.hashed(contract.get('review_source_sha256'))): return held('contract_mismatch')
    try: reviewed = L.instant(contract.get('reviewed_at'))
    except (ValueError, TypeError, OverflowError): return held('unknown_time')
    if reviewed > selected: return held('contract_not_prior')
    # No mechanical reading of a person's internal state, or semantic criterion, is supplied.
    if contract['family'] != 'mechanical' or kind != 'my_move': return held('unsupported_criterion')
    predicate = contract.get('predicate')
    if not isinstance(predicate, dict) or predicate.get('kind') != 'terminal_receipts_all': return held('unsupported_criterion')
    conditions = predicate.get('conditions')
    if (not isinstance(conditions, list) or not 1 <= len(conditions) <= 16
            or type(predicate.get('partial_allowed')) is not bool): return held('contract_mismatch')
    expected = []
    for c in conditions:
        if (not isinstance(c, dict) or set(c) != {'operation', 'object_sha256'}
                or c['operation'] not in OPERATIONS or not L.hashed(c['object_sha256'])): return held('contract_mismatch')
        expected.append((c['operation'], c['object_sha256']))
    if len(set(expected)) != len(expected): return held('contract_mismatch')
    statuses = []
    for operation, object_hash in expected:
        matches = [r for r in receipts.values() if r.get('turn_id') == tid
                   and r.get('operation') == operation and r.get('object_sha256') == object_hash]
        if not matches: return held('missing_receipt')
        # Distinct receipts for one condition may be retries; do not select the favorable one.
        if len(matches) != 1: return held('conflicting_receipt')
        r = matches[0]
        if (r.get('intent_id') != iid or r.get('source') != 'action_receipt'
                or not L.hashed(r.get('source_sha256')) or r.get('terminal') is not True
                or r.get('status') not in ('succeeded', 'failed')): return held('incomplete_observation')
        try: at = L.instant(r.get('at'))
        except (ValueError, TypeError, OverflowError): return held('unknown_time')
        if not selected <= at <= delivered: return held('receipt_time_order')
        statuses.append(r['status'])
    succeeded = statuses.count('succeeded')
    if succeeded == len(statuses): return 'YES', 'observed'
    if succeeded == 0: return 'NO', 'observed'
    return ('PARTIAL', 'observed') if predicate['partial_allowed'] else held('partial_not_defined')


def assess(ledger, evidence, contracts, cutoff, source_zone=None):
    if not isinstance(ledger, list) or len(ledger) > 4096 or any(not isinstance(r, dict) for r in ledger): raise ValueError('ledger')
    cut = L.instant(cutoff)
    turns, receipts, rules, duplicates = bundle(evidence, contracts)
    unique = []; seen = {}; exact = set(); ambiguous = set(); owners = {}
    for row in ledger:
        raw = L.canonical(row)
        if raw in exact: duplicates += 1; continue
        exact.add(raw); unique.append(row)
        iid = row.get('intent_id'); tid = row.get('turn_id')
        if L.identifier(iid):
            if iid in seen: ambiguous.add(iid)
            seen[iid] = row
            if L.identifier(tid): owners.setdefault(tid, set()).add(iid)
    for ids in owners.values():
        if len(ids) > 1: ambiguous.update(ids)
    result = {axis: dict(verdicts={v: 0 for v in VERDICTS}, reasons={r: 0 for r in REASONS},
                        old_vs_shadow={old: {v: 0 for v in VERDICTS} for old in OLD},
                        contract_families={f: 0 for f in FAMILIES}, missing_contract=0,
                        agreement_count=0, agreement_denominator=0, agreement_rate=None) for axis in AXES}
    for row in unique:
        for axis in AXES:
            verdict, reason = grade(row, axis, turns, receipts, rules, ambiguous, cut, source_zone)
            a = result[axis]; a['verdicts'][verdict] += 1; a['reasons'][reason] += 1
            old = original(row, axis); a['old_vs_shadow'][old][verdict] += 1
            contract = rules.get((row.get('intent_id'), axis)) if L.identifier(row.get('intent_id')) else None
            if contract: a['contract_families'][contract['family']] += 1
            else: a['missing_contract'] += 1
            if old in ('YES','PARTIAL','NO') and verdict in ('YES','PARTIAL','NO'):
                a['agreement_denominator'] += 1; a['agreement_count'] += int(old == verdict)
    for a in result.values():
        if a['agreement_denominator']: a['agreement_rate'] = a['agreement_count']/a['agreement_denominator']
    return dict(schema='intent-shadow-counts-v1', rule_version=1, input_rows=len(ledger),
                distinct_rows=len(unique), duplicate_records=duplicates, ambiguous_intents=len(ambiguous), axes=result,
                shadow_only=True, source_claims_verified=False, conditional_on_supplied_contracts=True, semantic_accuracy_measured=False,
                selector_served_identity_inferred=False, grader_kind='deterministic', inference_calls=0,
                runtime_writes=0, anchors_emitted=0, labels_emitted=0, training_signals_emitted=0, policy_inputs_emitted=0)


def main(argv=None):
    p = G.Parser(description=__doc__)
    for name in ('scratch', 'ledger', 'cutoff'): p.add_argument('--'+name, required=True)
    for name in ('evidence', 'contracts', 'source-timezone'): p.add_argument('--'+name)
    args = p.parse_args(argv); root = G.private_root(args.scratch)
    def guard(event, values):
        if event.startswith(('socket.', 'subprocess.', 'os.spawn', 'os.exec', 'os.system')): raise PermissionError('external operation')
        if event == 'open' and isinstance(values[2], int) and values[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND): raise PermissionError('write')
        if event in ('os.mkdir','os.remove','os.rename','os.rmdir','os.chmod','os.link','os.symlink','os.fork','os.forkpty'): raise PermissionError('mutation')
    sys.addaudithook(guard)
    evidence = G.read(root, args.evidence) if args.evidence else dict(schema='intent-shadow-evidence-v1', turns=[], receipts=[])
    contracts = G.read(root, args.contracts) if args.contracts else dict(schema='intent-shadow-contracts-v1', items=[])
    result = assess(G.read(root, args.ledger), evidence, contracts, args.cutoff, args.source_timezone)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print('intent_shadow_refused', file=sys.stderr); sys.exit(1)
