"""Offline historical attribution tiers; never alter witness admission or receipts."""
from collections import Counter, defaultdict
from bisect import bisect_left, bisect_right
from datetime import datetime
import json
from zoneinfo import ZoneInfo
from witness_receipts import digest, instant, joined_identity, normalize_receipt, final_response

TIERS = ('observed', 'ledger_attributed', 'recorded_label', 'unknown')


def _name(value):
    return value if isinstance(value, str) and value.strip() == value and 0 < len(value) <= 256 else None


def _clock(value, timezone):
    try:
        return instant(value)
    except (ValueError, TypeError, OverflowError):
        if not isinstance(value, str) or timezone is None: raise ValueError('unknown clock') from None
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None: raise ValueError('invalid clock')
            candidates = set()
            for fold in (0, 1):
                aware = parsed.replace(tzinfo=timezone, fold=fold)
                epoch = aware.timestamp()
                if datetime.fromtimestamp(epoch, timezone).replace(tzinfo=None) == parsed:
                    candidates.add(instant(epoch))
            if len(candidates) != 1: raise ValueError('ambiguous or nonexistent local time')
            return candidates.pop()
        except (ValueError, TypeError, OverflowError):
            raise ValueError('unknown clock') from None


def _row_clock(row, timezone):
    values = [_clock(row[key], timezone) for key in ('ts', 'timestamp') if key in row]
    if not values or len(set(values)) != 1: raise ValueError('unknown reply clock')
    return values[0]


def _observed(row):
    copies = [row['witness_receipt']] if 'witness_receipt' in row else []
    for field in ('generation_provenance', 'provenance'):
        parent = row.get(field)
        if isinstance(parent, dict) and 'witness_receipt' in parent:
            copies.append(parent['witness_receipt'])
    receipts = [normalize_receipt(value) for value in copies]
    if not receipts or any(r != receipts[0] for r in receipts): return None
    r = receipts[0]
    if (r['status'] != 'recorded' or joined_identity(row)[0] != r['turn_id']
            or row.get('surface') != r['surface'] or not isinstance(final_response(row), str)
            or digest(final_response(row)) != r['response_sha256']):
        return None
    selected = next(a for a in r['generation']['attempts'] if a['outcome'] == 'selected')
    return selected['served_model']


def attribution(rows, ledger, config, cutoff):
    """Per-assistant-copy diagnostic. Exact IDs first; bounded nearest call otherwise.

    Caller configuration and explicit timezone interpretation are supplied evidence,
    not inferred source facts. Ledger model/provider remain recorded metadata, not
    proof of successful generation, final reply selection or clean ancestry.
    """
    if (not isinstance(rows, list) or not isinstance(ledger, list) or not isinstance(config, dict)
            or set(config) - {'surface_callers','source_surfaces','window_seconds','naive_timezone','window30_enabled'}
            or type(config.get('window30_enabled', False)) is not bool):
        raise ValueError('invalid historical attribution inputs')
    window = config.get('window_seconds')
    mapping = config.get('surface_callers')
    defaults = config.get('source_surfaces', {})
    if (type(window) not in (int,float) or not 0 < window <= 10 or not isinstance(mapping, dict)
            or not isinstance(defaults, dict) or any(not _name(k) or not isinstance(v,list) or not v
            or any(not _name(x) for x in v) or len(set(v)) != len(v) for k,v in mapping.items())
            or any(k not in ('canonical','merged','ledger','capture') or not _name(v) for k,v in defaults.items())):
        raise ValueError('invalid historical attribution configuration')
    timezone = None
    if config.get('naive_timezone') is not None:
        try: timezone = ZoneInfo(config['naive_timezone'])
        except (TypeError, ValueError, KeyError): raise ValueError('invalid attribution timezone') from None
    cutoff = instant(cutoff)
    calls, by_id, by_caller, unordered = {}, defaultdict(list), defaultdict(list), set()
    for record in ledger:
        if not isinstance(record, dict): raise ValueError('invalid compute ledger record')
        try: sha = digest(json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False))
        except (TypeError, ValueError): raise ValueError('invalid compute ledger record') from None
        if sha in calls: continue
        caller, model, provider = (_name(record.get(k)) for k in ('organ','model','provider'))
        try: at = _clock(record.get('at'), timezone)
        except ValueError: at = None
        call = dict(sha256=sha, at=at, caller=caller, model=model, provider=provider,
                    foreground=record.get('class') == 'foreground', stage=record.get('stage'),
                    identity_explicit='model_identity_evidence' in record, identity_evidence=record.get('model_identity_evidence'))
        calls[sha] = call
        if _name(record.get('provider_request_id')): by_id[record['provider_request_id']].append(call)
        if caller and call['foreground']:
            if at is None: unordered.add(caller)
            else: by_caller[caller].append(call)
    details, uses = [], defaultdict(list)
    for row in rows:
        if not isinstance(row, dict): raise ValueError('invalid historical reply')
        if row.get('role') != 'assistant': continue
        identity, _ = joined_identity(row)
        observed = _observed(row)
        labels = {row[k] for k in ('served_by','model') if _name(row.get(k))}
        label = next(iter(labels)) if len(labels) == 1 else None
        surface = row.get('surface')
        if surface is None: surface = defaults.get(row.get('_witness_adapter_kind'))
        callers = mapping.get(surface, []) if isinstance(surface,str) else []
        supplied_ids = []
        for parent in [row] + [row.get(k) for k in ('generation_provenance','provenance')]:
            if isinstance(parent,dict) and parent.get('provider_request_id') is not None:
                supplied_ids.append(parent['provider_request_id'])
        valid_ids = {_name(value) for value in supplied_ids}
        call, method, state = None, None, 'no_matching_call'
        try: at = _row_clock(row,timezone)
        except ValueError: at = None
        # A strict finalized receipt can give the diagnostic a cutoff boundary;
        # it is not substituted into the legacy time-nearest join.
        r = normalize_receipt(row.get('witness_receipt'))
        cutoff_at = at if at is not None else (r.get('finalized_at') if r['status']=='recorded' else None)
        outside = cutoff_at is not None and cutoff_at >= cutoff
        if outside:
            state = 'outside_cutoff'
        elif not callers:
            state = 'surface_caller_unmapped'
        elif supplied_ids:
            method = 'provider_request_id'
            if None in valid_ids or len(valid_ids) != 1:
                state = 'conflicting_or_invalid_provider_id'
            else:
                matches = by_id[next(iter(valid_ids))]
                if len(matches) == 1:
                    call = matches[0]
                else: state = 'ambiguous_provider_id' if matches else 'provider_id_unmatched'
        elif at is None:
            state = 'reply_clock_unavailable'
        elif any(caller in unordered for caller in callers):
            state = 'caller_has_unordered_calls'
        else:
            method = 'nearest_time'
            candidates = [c for caller in callers for c in by_caller[caller]
                          if abs(c['at']-at) <= window and c['at'] < cutoff]
            if candidates:
                nearest = min(abs(c['at']-at) for c in candidates)
                matches = [c for c in candidates if abs(c['at']-at) == nearest]
                if len(matches) == 1: call = matches[0]
                else: state = 'ambiguous_nearest_call'
        if call is not None:
            if call['caller'] not in callers or not call['foreground']:
                state = 'call_scope_mismatch'; call = None
            elif call['at'] is None:
                state = 'call_clock_unavailable'; call = None
            elif call['at'] >= cutoff:
                state = 'call_outside_cutoff'; call = None
            elif not call['model'] or not call['provider'] or call['stage'] in ('failed','attempt','reserved','released','refused','claimed'):
                state = 'call_metadata_unavailable'; call = None
            elif call['identity_explicit'] and call['identity_evidence'] not in ('response_metadata','runtime_receipt'):
                state = 'call_model_identity_unobserved'; call = None
            else: state = 'matched'
        detail = dict(copy=len(details)+1, turn_id=identity, observed_model=observed,
                      response_sha256=digest(final_response(row)) if isinstance(final_response(row),str) else None,
                      recorded_label=label, label_conflict=len(labels)>1, outside_cutoff=outside,
                      reply_clock_known=cutoff_at is not None, join=method, join_state=state,
                      ledger_sha256=call['sha256'] if call else None,
                      ledger_model=call['model'] if call else None, ledger_provider=call['provider'] if call else None)
        details.append(detail)
        if call is not None: uses[call['sha256']].append(detail)
    for matched in uses.values():
        # Duplicate copies with the same explicit turn ID may share a call;
        # different or unidentified replies cannot silently reuse one call.
        identities = {d['turn_id'] for d in matched}
        versions = {d['response_sha256'] for d in matched}
        if len(matched)>1 and (len(identities)!=1 or None in identities or len(versions)!=1 or None in versions):
            for d in matched:
                d.update(join_state='call_reused_by_distinct_or_unknown_replies',ledger_sha256=None,ledger_model=None,ledger_provider=None)
    tiers, joins, agreement, exclusions = Counter(), Counter(), Counter(), Counter()
    for d in details:
        d['tier'] = ('observed' if d['observed_model'] else 'ledger_attributed' if d['ledger_model']
                     else 'recorded_label' if d['recorded_label'] else 'unknown')
        d['label_ledger_agreement'] = ('label_conflict' if d['label_conflict'] else 'ledger_unavailable' if not d['ledger_model']
             else 'label_missing' if not d['recorded_label'] else 'agree' if d['recorded_label']==d['ledger_model'] else 'disagree')
        if d['outside_cutoff']:
            exclusions['outside_cutoff'] += 1; continue
        tiers[d['tier']] += 1; joins[d['join_state']] += 1; agreement[d['label_ledger_agreement']] += 1
    report = {'scope':'per_assistant_source_copy_not_unique_training_turns',
            'tiers':{tier:tiers[tier] for tier in TIERS},'join_states':dict(joins),
            'label_ledger_agreement':dict(agreement),'excluded':dict(exclusions),
            'assistant_copies':len(details),'copies_without_cutoff_clock':sum(not d['reply_clock_known'] for d in details),
            'unique_ledger_records_supplied':len(calls),'naive_timezone_explicitly_supplied':timezone is not None,
            'admission_effect':'none','training_effect':'none',
            'meaning':'historical model attribution only; no proof of selected successful generation, delivery or clean ancestry'}
    if config.get('window30_enabled', False):
        report['window30'] = _window30(rows, details, calls, mapping, defaults, timezone, cutoff)
    return report, details


def _window30(rows, details, calls, mapping, defaults, timezone, cutoff):
    """Separate opt-in view; all nearby replies compete, not just unmatched ones."""
    by_caller, unordered = defaultdict(list), set()
    for call in calls.values():
        if not call['foreground'] or not call['caller']:
            continue
        if call['at'] is None:
            unordered.add(call['caller'])
        elif call['at'] < cutoff:
            by_caller[call['caller']].append(call)
    for values in by_caller.values():
        values.sort(key=lambda c: (c['at'], c['sha256']))
    clocks = {caller: [c['at'] for c in values] for caller, values in by_caller.items()}
    uses, selected = defaultdict(list), {}
    assistant = [r for r in rows if r.get('role') == 'assistant']
    for index, (row, detail) in enumerate(zip(assistant, details)):
        detail['window30'] = dict(tier=detail['tier'], join_state='not_eligible_for_extension',
                                  ledger_sha256=None, ledger_model=None, ledger_provider=None)
        if detail['outside_cutoff']:
            detail['window30']['join_state'] = 'outside_cutoff'
            continue
        surface = row.get('surface')
        if surface is None:
            surface = defaults.get(row.get('_witness_adapter_kind'))
        callers = mapping.get(surface, []) if isinstance(surface, str) else []
        try: at = _row_clock(row, timezone)
        except ValueError: at = None
        candidates = {}
        if at is not None:
            for caller in callers:
                times = clocks.get(caller, [])
                values = by_caller[caller]
                for call in values[bisect_left(times, at-30):bisect_right(times, at+30)]:
                    candidates[call['sha256']] = call
        # An exact-ID match outside the time window also reserves its call.
        reserved = set(candidates)
        if detail['ledger_sha256'] is not None:
            reserved.add(detail['ledger_sha256'])
        identity = (detail['turn_id'], detail['response_sha256'])
        for sha in reserved:
            uses[sha].append((index, identity))
        if detail['join_state'] != 'no_matching_call' or detail['tier'] == 'observed':
            continue
        state, call = 'none_in_window', None
        if at is None or not callers:
            state = 'scope_or_clock_unavailable'
        elif any(caller in unordered for caller in callers):
            state = 'unordered_caller'
        elif len(candidates) > 1:
            state = 'multiple_calls_in_window'
        elif candidates:
            call = next(iter(candidates.values()))
            if (not call['model'] or not call['provider']
                    or call['stage'] in ('failed','attempt','reserved','released','refused','claimed')):
                state = 'call_metadata_unavailable'
            elif call['identity_explicit'] and call['identity_evidence'] not in ('response_metadata','runtime_receipt'):
                state = 'call_model_identity_unobserved'
            else:
                state = 'candidate'
                selected[index] = call
        detail['window30']['join_state'] = state
    for sha, contenders in uses.items():
        identities = {identity for _, identity in contenders}
        contested = len(contenders) > 1 and (len(identities) > 1 or any(None in i for i in identities))
        if contested:
            for index, _ in contenders:
                if index in selected and selected[index]['sha256'] == sha:
                    details[index]['window30']['join_state'] = 'call_contested_by_other_reply'
                    del selected[index]
    for index, call in selected.items():
        details[index]['window30'].update(tier='ledger_attributed_window30', join_state='matched_window30',
            ledger_sha256=call['sha256'], ledger_model=call['model'], ledger_provider=call['provider'])
    tiers, states, agreement = Counter(), Counter(), Counter()
    for detail in details:
        if detail['outside_cutoff']: continue
        extra = detail['window30']
        tiers[extra['tier']] += 1
        states[extra['join_state']] += 1
        if extra['tier'] == 'ledger_attributed_window30':
            comparison = ('label_conflict' if detail['label_conflict'] else
                          'label_missing' if not detail['recorded_label'] else
                          'agree' if detail['recorded_label'] == extra['ledger_model'] else 'disagree')
            agreement[comparison] += 1
    return dict(window_seconds=30, selection='sole_call_all_replies_compete',
                tiers={tier:tiers[tier] for tier in (*TIERS, 'ledger_attributed_window30')},
                join_states=dict(states), added_copies=len(selected),
                added_label_ledger_agreement=dict(agreement),
                admission_effect='none', training_effect='none',
                meaning='alternative partition of the same source copies; do not add to original tier counts')
