"""Offline content binding for retained self vectors; no scoring or admission changes."""
from collections import Counter, defaultdict
import json
import math
import re
from witness_receipts import admission, digest, final_response, joined_identity, row_receipt, instant
from witness_self_artifacts import bound_source, availability_receipt


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False))


def normalized_reply(raw):
    """Versioned self-reader cleanup, checked against the actual reader in tests."""
    text = raw.strip()
    if text in ('', 'voice', '--source'):
        return ''
    paragraphs = text.split('\n\n')
    while len(paragraphs) > 1 and re.match(r'^(?:ridge|tenera|ferri):', paragraphs[-1].strip(), re.I):
        paragraphs.pop()
    return '\n\n'.join(paragraphs).strip()


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _vector(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 8192
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)
            or not any(value)):
        raise ValueError('invalid retained artifact vector')
    return fingerprint(value)


def claims(packet):
    """Extract observations only; do not infer a forecast's selected target."""
    schema = packet.get('schema')
    if schema == 'self-audit-embedding-v1':
        if packet.get('transform') != 'ledger_vintos_strip_first_400_codepoints':
            raise ValueError('unknown audit input transform')
        refs = packet.get('source_refs')
        if not isinstance(refs, list) or not 1 <= len(refs) <= 64:
            raise ValueError('invalid audit source references')
        manifest = packet.get('checkpoint')
        values = [(ref, packet) for ref in refs]
    elif schema == 'self-forecast-artifacts-v1':
        artifacts = packet.get('artifacts')
        if not isinstance(artifacts, dict):
            raise ValueError('invalid forecast artifact observations')
        refs = artifacts.get('recent_own_embeddings')
        if not isinstance(refs, list) or not 1 <= len(refs) <= 6:
            raise ValueError('invalid forecast input references')
        manifest = artifacts.get('checkpoint')
        values = []
        for ref in refs:
            if not isinstance(ref, dict) or ref.get('transform') != 'normalized_exchange_his_first_400_codepoints':
                raise ValueError('unknown forecast input transform')
            values.append((ref, ref))
    else:
        raise ValueError('unsupported self artifact packet')
    if not isinstance(manifest, dict) or not _hash(manifest.get('checkpoint_id')):
        raise ValueError('invalid retained checkpoint identity')
    for ref, value in values:
        if (not isinstance(ref, dict) or not _hash(value.get('encoder_input_sha256'))
                or type(value.get('encoder_input_chars')) is not int
                or not 1 <= value['encoder_input_chars'] <= 400):
            raise ValueError('invalid retained input identity')
        vector_sha = _vector(value.get('emb'))
        yield ref, value, manifest['checkpoint_id'], vector_sha


def join_artifacts(admitted, sources, nodes, packets, cutoff, forecasts=()):
    """Exact source digest, explicit ID/surface, final version and transform agreement.

    Even a content match is not encoder identity, training evidence or a forecast
    target association. No vectors are returned for automatic scoring consumption.
    """
    if not isinstance(packets, list) or len(packets) > 4096:
        raise ValueError('invalid artifact packet list')
    cutoff = instant(cutoff)
    targets = {row['turn_id']: row for row in admitted}
    if len(targets) != len(admitted):
        raise ValueError('duplicate admitted reply identity')
    raw_by_hash = defaultdict(list)
    for kind, rows in sources:
        if kind not in ('canonical', 'merged', 'ledger'):
            continue
        for raw in rows:
            key = fingerprint(raw)
            if kind not in [k for k, _ in raw_by_hash[key]]:
                raw_by_hash[key].append((kind, raw))
    unique = {}
    for packet in packets:
        if not isinstance(packet, dict):
            raise ValueError('invalid artifact packet')
        unique[fingerprint(packet)] = packet
    details, vectors = [], defaultdict(set)
    for packet_sha, packet in sorted(unique.items()):
        for index, (ref, value, checkpoint, vector_sha) in enumerate(claims(packet)):
            item = {'packet_sha256': packet_sha, 'reference_index': index,
                    'checkpoint_id': checkpoint, 'encoder_input_sha256': value['encoder_input_sha256'],
                    'vector_sha256': vector_sha, 'turn_id': None, 'final_response_sha256': None,
                    'state': 'missing_source_observation'}
            details.append(item)
            observed = ref.get('reply_source')
            if not isinstance(observed, dict):
                continue
            key = observed.get('source_row_sha256')
            if not _hash(key):
                item['state'] = 'invalid_source_observation'; continue
            matches = raw_by_hash.get(key, [])
            expected = 'ledger' if observed.get('source_field') == 'vintos' else 'chat'
            matches = [(k, row) for k, row in matches if (k == 'ledger') == (expected == 'ledger')]
            if not matches:
                item['state'] = 'exact_source_row_missing'; continue
            # Same raw row in canonical/merged is one version; no time/text lookup.
            kind, source = matches[0]
            field = observed.get('source_field')
            raw = source.get(field) if field in ('vintos', 'content') else None
            if not isinstance(raw, str) or not 0 < len(raw) <= 65536:
                item['state'] = 'invalid_source_reply'; continue
            normalized = normalized_reply(raw)
            bound = bound_source(observed, normalized, source.get('turn_id'))
            if (bound is None or bound['source_reply_sha256'] != digest(raw)
                    or bound['observed_turn_id'] != source.get('turn_id')
                    or bound['observed_surface'] != source.get('surface')
                    or bound['observed_turn_id'] != ref.get('observed_turn_id')
                    or ref.get('normalized_reply_sha256') != digest(normalized)):
                item['state'] = 'source_observation_mismatch'; continue
            tid, surface = bound['observed_turn_id'], bound['observed_surface']
            if not tid or not surface:
                item['state'] = 'missing_source_identity'; continue
            item['turn_id'] = tid
            target = targets.get(tid)
            if target is None:
                item['state'] = 'reply_not_admitted'; continue
            source_copy = dict(source, _witness_adapter_kind=kind)
            if kind == 'ledger':
                source_copy.update(role='assistant', content=raw)
            if admission(source_copy, nodes, cutoff) != 'eligible':
                item['state'] = 'source_copy_not_admitted'; continue
            final = final_response(target)
            if (joined_identity(source_copy)[0] != tid or surface != target.get('surface')
                    or row_receipt(source_copy) != row_receipt(target)
                    or final_response(source_copy) != final):
                item['state'] = 'final_version_mismatch'; continue
            item['final_response_sha256'] = digest(final)
            if normalized != final:
                item['state'] = 'normalization_changes_final'; continue
            encoded = normalized[:400]
            if (value['encoder_input_sha256'] != digest(encoded)
                    or value['encoder_input_chars'] != len(encoded)):
                item['state'] = 'input_transform_mismatch'; continue
            item['state'] = 'bound_full_text' if encoded == final else 'bound_excerpt'
            group = (checkpoint, tid, digest(final), value['encoder_input_sha256'])
            vectors[group].add(vector_sha)
            item['_group'] = group
    for item in details:
        group = item.pop('_group', None)
        if group is not None and len(vectors[group]) > 1:
            item['state'] = 'conflicting_vector_observations'
    states = Counter(item['state'] for item in details)
    matched = [item for item in details if item['state'] in ('bound_full_text', 'bound_excerpt')]
    return {'scope': 'content_binding_only', 'packets_supplied': len(packets), 'unique_packets': len(unique),
            'source_references': len(details), 'states': dict(sorted(states.items())),
            'checkpoint_availability_states': checkpoint_availability(list(unique.values()), forecasts, cutoff),
            'bound_unique_replies': len({item['turn_id'] for item in matched}),
            'admission_effect': 'none', 'scoring_effect': 'none', 'encoder_identity': 'unverified',
            'artifact_observation_time': 'unverified', 'forecast_target_selection': 'not_evaluated'}, details


def checkpoint_availability(packets, forecasts, cutoff):
    """Timing consistency of exact supplied records; never invent a fitting date."""
    cutoff = instant(cutoff)
    by_forecast = {fingerprint(f):f for f in forecasts if isinstance(f, dict)}
    states = Counter()
    for packet in packets:
        is_forecast = packet.get('schema') == 'self-forecast-artifacts-v1'
        manifest = packet.get('artifacts',{}).get('checkpoint') if is_forecast else packet.get('checkpoint')
        observation = availability_receipt(manifest.get('availability') if isinstance(manifest,dict) else None)
        state = observation['state']
        if state != 'observed':
            states[state] += 1; continue
        if not is_forecast:
            states['audit_snapshot_observed'] += 1; continue
        if observation['stage'] != 'parameters_loaded':
            states['parameters_not_loaded'] += 1; continue
        forecast = by_forecast.get(packet.get('forecast_row_sha256'))
        if forecast is None:
            states['exact_forecast_row_missing'] += 1; continue
        if (forecast.get('mode') != 'on_message' or not isinstance(forecast.get('self'),dict)
                or forecast['self'].get('mode') != 'on_message'
                or forecast['self'].get('checkpoint_id') != manifest.get('checkpoint_id')):
            states['forecast_identity_mismatch'] += 1; continue
        try:
            made, arrived = instant(forecast['ts']), instant(forecast['arrived_at'])
            if (made != instant(packet['forecast_at']) or arrived != instant(packet['arrived_at'])
                    or arrived > made):
                raise ValueError('inconsistent forecast clocks')
        except (KeyError,TypeError,ValueError,OverflowError):
            states['forecast_clock_mismatch'] += 1; continue
        if made >= cutoff:
            states['forecast_outside_cutoff'] += 1
        elif observation['parameters_available_by'] > made:
            states['parsed_after_logged_forecast'] += 1
        else:
            states['parsed_by_logged_forecast'] += 1
    return dict(sorted(states.items()))
